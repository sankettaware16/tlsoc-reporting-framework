"""
Elasticsearch backend: compiles the shared filter IR into query DSL,
executes, and normalizes responses into the backend-neutral shapes
documented in backends/__init__.py.
"""
import datetime

from ..registry import SEVERITY_RANK
from ..window import Window


# ---------------------------------------------------------------------------
# IR -> DSL
# ---------------------------------------------------------------------------
def ir_to_dsl(ir):
    if ir is None:
        return {"match_all": {}}
    kind = ir[0]
    if kind == "all":
        return {"bool": {"must": [ir_to_dsl(c) for c in ir[1]]}}
    if kind == "any":
        return {"bool": {"should": [ir_to_dsl(c) for c in ir[1]],
                         "minimum_should_match": 1}}
    if kind == "none":
        return {"bool": {"must_not": [ir_to_dsl(c) for c in ir[1]]}}
    if kind == "term":
        return {"term": {ir[1]: ir[2]}}
    if kind == "terms":
        return {"terms": {ir[1]: ir[2]}}
    if kind == "wildcard":
        _, field, patterns, ci = ir
        clauses = [{"wildcard": {field: {"value": p, "case_insensitive": ci}}}
                   for p in patterns]
        if len(clauses) == 1:
            return clauses[0]
        return {"bool": {"should": clauses, "minimum_should_match": 1}}
    if kind == "prefix":
        _, field, prefixes, ci = ir
        clauses = [{"prefix": {field: {"value": p, "case_insensitive": ci}}}
                   for p in prefixes]
        if len(clauses) == 1:
            return clauses[0]
        return {"bool": {"should": clauses, "minimum_should_match": 1}}
    if kind == "range":
        return {"range": {ir[1]: ir[2]}}
    if kind == "exists":
        return {"exists": {"field": ir[1]}}
    raise ValueError(f"unknown IR node: {ir[0]}")


class ESBackend:
    def __init__(self, settings, datasource, window):
        from elasticsearch import Elasticsearch
        es_cfg = settings["elasticsearch"]
        kwargs = {
            "basic_auth": (es_cfg["user"], es_cfg["password"]),
            "request_timeout": es_cfg.get("request_timeout", 120),
        }
        if es_cfg.get("ca_cert"):
            kwargs["ca_certs"] = es_cfg["ca_cert"]
        elif not es_cfg.get("verify_certs", True):
            kwargs["verify_certs"] = False
        self.es = Elasticsearch(es_cfg["host"], **kwargs)
        self.index = datasource.index
        self.ts_field = datasource.resolve("timestamp") or "@timestamp"
        self.window = window

    # -- plumbing ----------------------------------------------------------
    def _time_filter(self, which):
        w = self.window
        if which == "previous":
            gte, lt = w.prev_start, w.prev_end
        else:
            gte, lt = w.start, w.end
        return {"range": {self.ts_field: {"gte": Window.iso(gte),
                                          "lt": Window.iso(lt)}}}

    def _query(self, cq):
        must = [self._time_filter(cq.window)]
        if cq.filter_ir is not None:
            must.append(ir_to_dsl(cq.filter_ir))
        return {"bool": {"must": must}}

    def _search(self, body):
        return self.es.search(index=self.index, body=body)

    @staticmethod
    def _subagg_dsl(sub):
        if sub.kind == "cardinality":
            return {"cardinality": {"field": sub.field,
                                    "precision_threshold": 40000}}
        if sub.kind in ("sum", "avg", "min", "max"):
            return {sub.kind: {"field": sub.field}}
        if sub.kind == "filter":
            return {"filter": ir_to_dsl(sub.filter_ir)}
        if sub.kind == "top_terms":
            terms = {"field": sub.field, "size": sub.size}
            if sub.missing is not None:
                terms["missing"] = sub.missing
            return {"terms": terms}
        raise ValueError(sub.kind)

    @staticmethod
    def _subagg_value(sub, bucket):
        agg = bucket[sub.name]
        if sub.kind == "filter":
            return agg["doc_count"]
        if sub.kind == "top_terms":
            keys = [str(b["key"]) for b in agg["buckets"]]
            if not keys:
                return "-"
            return keys[0] if sub.size == 1 else sub.join.join(keys)
        val = agg.get("value")
        if sub.kind == "cardinality":
            return int(val or 0)
        if sub.kind == "sum":
            return int(val or 0)
        return val or 0

    def _subaggs_dsl(self, cq):
        return {name: self._subagg_dsl(sub)
                for name, sub in cq.sub_aggs.items()}

    def _flatten(self, cq, bucket, key_name="key"):
        row = {key_name: bucket.get("key_as_string", bucket.get("key")),
               "count": bucket["doc_count"]}
        for name, sub in cq.sub_aggs.items():
            row[name] = self._subagg_value(sub, bucket)
        return row

    # -- execution ---------------------------------------------------------
    def execute(self, cq):
        return getattr(self, f"_run_{cq.kind}")(cq)

    def _run_count(self, cq):
        return self.es.count(index=self.index,
                             body={"query": self._query(cq)})["count"]

    def _run_scalar(self, cq, agg):
        body = {"size": 0, "query": self._query(cq), "aggs": {"out": agg}}
        val = self._search(body)["aggregations"]["out"]["value"]
        return int(val or 0) if cq.kind in ("cardinality", "sum") \
            else (val or 0)

    def _run_cardinality(self, cq):
        return self._run_scalar(cq, {"cardinality": {
            "field": cq.field, "precision_threshold": 40000}})

    def _run_sum(self, cq):
        return self._run_scalar(cq, {"sum": {"field": cq.field}})

    def _run_avg(self, cq):
        return self._run_scalar(cq, {"avg": {"field": cq.field}})

    def _run_min(self, cq):
        return self._run_scalar(cq, {"min": {"field": cq.field}})

    def _run_max(self, cq):
        return self._run_scalar(cq, {"max": {"field": cq.field}})

    def _run_terms(self, cq):
        terms = {"field": cq.field, "size": cq.size}
        if cq.missing is not None:
            terms["missing"] = cq.missing
        if cq.order_by:
            terms["order"] = {cq.order_by: "desc"}
        body = {
            "size": 0,
            "query": self._query(cq),
            "aggs": {"out": {"terms": terms,
                             "aggs": self._subaggs_dsl(cq)}},
        }
        res = self._search(body)
        return [self._flatten(cq, b)
                for b in res["aggregations"]["out"]["buckets"]]

    def _run_date_histogram(self, cq):
        w = self.window
        hist = {
            "field": self.ts_field,
            "calendar_interval": cq.interval,
            "time_zone": str(w.tz),
            "min_doc_count": 0,
            "extended_bounds": {
                "min": Window.iso(w.start),
                "max": Window.iso(w.end - datetime.timedelta(minutes=1)),
            },
        }
        body = {"size": 0, "query": self._query(cq),
                "aggs": {"out": {"date_histogram": hist,
                                 "aggs": self._subaggs_dsl(cq)}}}
        res = self._search(body)
        rows = []
        for b in res["aggregations"]["out"]["buckets"]:
            row = self._flatten(cq, b, key_name="ts")
            ks = b.get("key_as_string", "")
            row["label"] = ks[11:16] if len(ks) >= 16 else str(b.get("key"))
            rows.append(row)
        return rows

    def _run_range_buckets(self, cq):
        body = {
            "size": 0, "query": self._query(cq),
            "aggs": {"out": {"range": {"field": cq.field,
                                       "ranges": cq.ranges}}},
        }
        res = self._search(body)
        return {b["key"]: b["doc_count"]
                for b in res["aggregations"]["out"]["buckets"]}

    def _run_signature_categories(self, cq):
        filters = {}
        for key, cat in cq.pack.categories.items():
            filters[key] = ir_to_dsl(("wildcard", cq.category_field,
                                      cat["patterns"], True))
        agg = {"filters": {"filters": filters}}
        if cq.other_bucket:
            agg["filters"]["other_bucket"] = True
            agg["filters"]["other_bucket_key"] = "_other"
        body = {"size": 0, "query": self._query(cq),
                "aggs": {"out": {**agg, "aggs": self._subaggs_dsl(cq)}}}
        res = self._search(body)
        buckets = res["aggregations"]["out"]["buckets"]
        return normalize_signature_rows(cq, buckets, self._flatten)

    def _run_samples(self, cq):
        body = {
            "size": cq.size,
            "track_total_hits": False,
            "sort": [{self.ts_field: {"order": "desc"}}],
            "_source": list(cq.sample_fields.values()),
            "query": self._query(cq),
        }
        res = self._search(body)
        rows = []
        for h in res["hits"]["hits"]:
            src = h.get("_source", {})
            row = {}
            for logical, concrete in cq.sample_fields.items():
                row[logical] = _dig(src, concrete)
            rows.append(row)
        return rows


def _dig(doc, dotted):
    """Fetch a dotted path from a nested dict; tolerate .keyword suffixes."""
    if dotted.endswith(".keyword"):
        dotted = dotted[: -len(".keyword")]
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def normalize_signature_rows(cq, buckets, flatten):
    """Shared between backends: category metadata + severity ordering."""
    rows = []
    meta = dict(cq.pack.categories)
    meta["_other"] = {
        "title": "Uncategorised signature match",
        "severity": "low",
        "why": ("Matched the combined pattern set but no single category — "
                "a pattern in this pack has no home. If this row is "
                "non-zero, a category is mis-scoped."),
    }
    for key, cat in meta.items():
        b = buckets.get(key)
        if not b or not b.get("doc_count"):
            continue
        row = flatten(cq, b)
        row.update({"key": key, "title": cat["title"],
                    "severity": cat["severity"], "why": cat["why"]})
        rows.append(row)
    rows.sort(key=lambda r: (SEVERITY_RANK.get(r["severity"], 9),
                             -r["count"]))
    return rows
