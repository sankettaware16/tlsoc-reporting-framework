"""
Offline backend: executes the same compiled queries over NDJSON sample files
(one JSON document per line, as produced by the foss-soc parsing engine).

Purpose:
  * develop and preview report definitions with zero infrastructure
    (`--backend local --sample log_samples/nginx_sample.json`)
  * regression-test the framework: both backends consume the same filter IR,
    so a report that renders correctly here renders identically from ES.

It implements exactly the aggregation semantics the ES backend uses:
whole-value wildcard matching, case-insensitive by default, hour-snapped
gap-free date histograms in the report timezone, filters-agg with an
other-bucket, and "missing" handling on terms aggregations.
"""
import datetime
import fnmatch
import ipaddress
import json
import re
from collections import Counter, defaultdict

from ..registry import SEVERITY_RANK
from ..window import parse_ts
from .es import normalize_signature_rows


def _dig(doc, dotted):
    if dotted.endswith(".keyword"):
        dotted = dotted[: -len(".keyword")]
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _values(doc, field):
    """Field value(s) as a list; ES treats array fields as multi-valued."""
    v = _dig(doc, field)
    if v is None:
        return []
    if isinstance(v, list):
        return [x for x in v if x is not None]
    return [v]


def _wc_regex(pattern, ci):
    rx = fnmatch.translate(pattern)
    return re.compile(rx, re.IGNORECASE if ci else 0)


# ---------------------------------------------------------------------------
# IR -> predicate
# ---------------------------------------------------------------------------
def ir_to_predicate(ir):
    if ir is None:
        return lambda doc: True
    kind = ir[0]
    if kind == "all":
        preds = [ir_to_predicate(c) for c in ir[1]]
        return lambda doc: all(p(doc) for p in preds)
    if kind == "any":
        preds = [ir_to_predicate(c) for c in ir[1]]
        return lambda doc: any(p(doc) for p in preds)
    if kind == "none":
        preds = [ir_to_predicate(c) for c in ir[1]]
        return lambda doc: not any(p(doc) for p in preds)
    if kind == "term":
        _, field, value = ir
        return lambda doc: any(v == value or str(v) == str(value)
                               for v in _values(doc, field))
    if kind == "terms":
        _, field, values = ir
        vset = set(values) | {str(v) for v in values}
        return lambda doc: any(v in vset or str(v) in vset
                               for v in _values(doc, field))
    if kind == "ip_in":
        # Mirrors Elasticsearch's CIDR-aware terms query on an ip field, so
        # offline previews classify addresses exactly like a live run.
        _, field, cidrs = ir
        nets = []
        for entry in cidrs:
            try:
                nets.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                continue

        def _in_nets(doc):
            for v in _values(doc, field):
                try:
                    addr = ipaddress.ip_address(str(v))
                except ValueError:
                    continue
                if any(addr in net for net in nets):
                    return True
            return False

        return _in_nets
    if kind == "wildcard":
        _, field, patterns, ci = ir
        regexes = [_wc_regex(p, ci) for p in patterns]
        return lambda doc: any(rx.match(str(v))
                               for v in _values(doc, field)
                               for rx in regexes)
    if kind == "prefix":
        _, field, prefixes, ci = ir
        pfx = [p.lower() for p in prefixes] if ci else list(prefixes)
        if ci:
            return lambda doc: any(str(v).lower().startswith(p)
                                   for v in _values(doc, field) for p in pfx)
        return lambda doc: any(str(v).startswith(p)
                               for v in _values(doc, field) for p in pfx)
    if kind == "range":
        _, field, ops = ir

        def _cmp(doc):
            for v in _values(doc, field):
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                ok = True
                if "gte" in ops and not x >= ops["gte"]:
                    ok = False
                if "gt" in ops and not x > ops["gt"]:
                    ok = False
                if "lte" in ops and not x <= ops["lte"]:
                    ok = False
                if "lt" in ops and not x < ops["lt"]:
                    ok = False
                if ok:
                    return True
            return False
        return _cmp
    if kind == "exists":
        _, field = ir
        return lambda doc: bool(_values(doc, field))
    raise ValueError(f"unknown IR node: {ir[0]}")


class LocalBackend:
    def __init__(self, sample_paths, datasource, window):
        self.window = window
        self.ts_field = datasource.resolve("timestamp") or "@timestamp"
        self.docs = []
        for path in ([sample_paths] if isinstance(sample_paths, str)
                     else sample_paths):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = _dig(doc, self.ts_field)
                    try:
                        doc["_ts"] = parse_ts(ts) if ts else None
                    except (ValueError, TypeError):
                        doc["_ts"] = None
                    self.docs.append(doc)

    def max_timestamp(self):
        stamps = [d["_ts"] for d in self.docs if d["_ts"]]
        return max(stamps) if stamps else None

    # -- doc selection ------------------------------------------------------
    def _in_window(self, doc, which):
        w = self.window
        if doc["_ts"] is None:
            return False
        if which == "previous":
            return w.prev_start <= doc["_ts"] < w.prev_end
        return w.start <= doc["_ts"] < w.end

    def _select(self, cq):
        pred = ir_to_predicate(cq.filter_ir)
        return [d for d in self.docs
                if self._in_window(d, cq.window) and pred(d)]

    # -- sub-aggs -----------------------------------------------------------
    def _subagg_value(self, sub, docs):
        if sub.kind == "filter":
            pred = ir_to_predicate(sub.filter_ir)
            return sum(1 for d in docs if pred(d))
        if sub.kind == "cardinality":
            return len({v for d in docs for v in _values(d, sub.field)})
        if sub.kind in ("sum", "avg", "min", "max"):
            nums = []
            for d in docs:
                for v in _values(d, sub.field):
                    try:
                        nums.append(float(v))
                    except (TypeError, ValueError):
                        pass
            if sub.kind == "sum":
                return int(sum(nums))
            if not nums:
                return 0
            if sub.kind == "avg":
                return sum(nums) / len(nums)
            return min(nums) if sub.kind == "min" else max(nums)
        if sub.kind == "top_terms":
            counts = Counter()
            for d in docs:
                vals = _values(d, sub.field)
                if not vals and sub.missing is not None:
                    vals = [sub.missing]
                for v in vals:
                    counts[str(v)] += 1
            keys = [k for k, _ in counts.most_common(sub.size)]
            if not keys:
                return "-"
            return keys[0] if sub.size == 1 else sub.join.join(keys)
        raise ValueError(sub.kind)

    def _row(self, cq, key, docs, key_name="key"):
        row = {key_name: key, "count": len(docs)}
        for name, sub in cq.sub_aggs.items():
            row[name] = self._subagg_value(sub, docs)
        return row

    # -- execution ----------------------------------------------------------
    def execute(self, cq):
        return getattr(self, f"_run_{cq.kind}")(cq)

    def _run_count(self, cq):
        return len(self._select(cq))

    def _run_cardinality(self, cq):
        docs = self._select(cq)
        return len({v for d in docs for v in _values(d, cq.field)})

    def _agg_scalar(self, cq, fn):
        nums = []
        for d in self._select(cq):
            for v in _values(d, cq.field):
                try:
                    nums.append(float(v))
                except (TypeError, ValueError):
                    pass
        return fn(nums)

    def _run_sum(self, cq):
        return self._agg_scalar(cq, lambda ns: int(sum(ns)))

    def _run_avg(self, cq):
        return self._agg_scalar(cq, lambda ns: sum(ns) / len(ns) if ns else 0)

    def _run_min(self, cq):
        return self._agg_scalar(cq, lambda ns: min(ns) if ns else 0)

    def _run_max(self, cq):
        return self._agg_scalar(cq, lambda ns: max(ns) if ns else 0)

    def _run_terms(self, cq):
        groups = defaultdict(list)
        for d in self._select(cq):
            vals = _values(d, cq.field)
            if not vals:
                if cq.missing is None:
                    continue
                vals = [cq.missing]
            for v in vals:
                groups[v].append(d)
        rows = [self._row(cq, k, ds) for k, ds in groups.items()]
        if cq.order_by:
            rows.sort(key=lambda r: -(r.get(cq.order_by) or 0))
        else:
            rows.sort(key=lambda r: -r["count"])
        return rows[: cq.size]

    def _run_date_histogram(self, cq):
        w = self.window
        buckets = defaultdict(list)
        for d in self._select(cq):
            local = d["_ts"].astimezone(w.tz)
            buckets[local.replace(minute=0, second=0,
                                  microsecond=0)].append(d)
        rows = []
        cur = w.start.astimezone(w.tz)
        end = w.end.astimezone(w.tz)
        while cur < end:
            docs = buckets.get(cur, [])
            row = self._row(cq, cur.isoformat(), docs, key_name="ts")
            row["label"] = cur.strftime("%H:%M")
            rows.append(row)
            cur += datetime.timedelta(hours=1)
        return rows

    def _run_range_buckets(self, cq):
        docs = self._select(cq)
        out = {}
        for r in cq.ranges:
            lo, hi = r.get("from"), r.get("to")
            n = 0
            for d in docs:
                for v in _values(d, cq.field):
                    try:
                        x = float(v)
                    except (TypeError, ValueError):
                        continue
                    if (lo is None or x >= lo) and (hi is None or x < hi):
                        n += 1
                        break
            out[r["key"]] = n
        return out

    def _run_signature_categories(self, cq):
        docs = self._select(cq)
        preds = {key: ir_to_predicate(("wildcard", cq.category_field,
                                       cat["patterns"], True))
                 for key, cat in cq.pack.categories.items()}
        buckets = {}
        matched_any = set()
        for key, pred in preds.items():
            hit = [d for d in docs if pred(d)]
            matched_any.update(id(d) for d in hit)
            buckets[key] = hit
        raw = {k: {"doc_count": len(v), "_docs": v}
               for k, v in buckets.items()}
        if cq.other_bucket:
            other = [d for d in docs if id(d) not in matched_any]
            raw["_other"] = {"doc_count": len(other), "_docs": other}

        def flatten(cq_, b):
            return self._row(cq_, None, b["_docs"])
        return normalize_signature_rows(cq, raw, flatten)

    def _run_samples(self, cq):
        docs = sorted(self._select(cq),
                      key=lambda d: d["_ts"] or datetime.datetime.min.replace(
                          tzinfo=datetime.timezone.utc),
                      reverse=True)[: cq.size]
        rows = []
        for d in docs:
            row = {}
            for logical, concrete in cq.sample_fields.items():
                row[logical] = _dig(d, concrete)
            rows.append(row)
        return rows
