"""
Declarative query specs -> executable form.

A report's `queries:` block is written against LOGICAL fields and named
parameters. This module resolves both and compiles each filter into a small
intermediate representation (IR) that the two backends share:

    backends/es.py     IR -> Elasticsearch bool DSL
    backends/local.py  IR -> python predicate over sample JSON docs

Keeping one IR means a report previewed offline against log_samples/*.json
behaves identically against the live cluster.

Filter grammar (recursive):
    all:  [ ... ]                 every clause must match        (bool.must)
    any:  [ ... ]                 at least one must match        (bool.should)
    none: [ ... ]                 none may match                 (bool.must_not)

Leaf clauses (all take `field: <logical name>` unless noted):
    equals: <value>               exact match
    in: [v, ...]                  any of the values
    in_param: <param>             any of the values in a list param
    ip_in_param: <param>          IP falls inside any CIDR/address in a list
                                  param (needs an `ip`-mapped field; the
                                  section degrades if the field is a keyword)
    wildcard: "<pat>" | [pats]    ES wildcard, case-insensitive by default
    wildcard_param: <param>       patterns from a list param, used verbatim
    contains_param: <param>       list param terms wrapped as *term*
    suffix_param: <param>         list param suffixes wrapped as *suffix
    prefix: "<p>" | [ps]          path prefix, case-insensitive by default
    prefix_param: <param>         prefixes from a list param
    range: {gte/gt/lte/lt: n}     numeric / date range
    exists: true                  field present

Signature clause (no `field:`; the pack declares its own target field):
    signatures: <pack name>
    severities: [critical, high]  optional subset
    category: <key>               optional single category

Any string value may reference params: a value that IS "$name" is replaced
by the param's value (any type); "${name}" inside a string interpolates.
"""


class UnmappedFieldError(Exception):
    def __init__(self, logical):
        self.logical = logical
        super().__init__(f"logical field '{logical}' is not mapped "
                         f"by this datasource")


class SpecError(Exception):
    pass


# ---------------------------------------------------------------------------
# IR node constructors (plain tuples keep both backends trivial)
# ---------------------------------------------------------------------------
def _all(children):
    return ("all", children)


def _any(children):
    return ("any", children)


def _none(children):
    return ("none", children)


class QueryContext:
    """Everything needed to compile a spec for one (report, datasource) run."""

    def __init__(self, datasource, signatures, params, window):
        self.datasource = datasource
        self.signatures = signatures
        self.params = params
        self.window = window

    # -- params ------------------------------------------------------------
    def param(self, name):
        if name not in self.params:
            raise SpecError(f"unknown param '{name}'")
        return self.params[name]

    def expand(self, value):
        """Recursive $param / ${param} substitution."""
        if isinstance(value, str):
            if value.startswith("$") and not value.startswith("${"):
                return self.param(value[1:])
            if "${" in value:
                out = value
                for k, v in self.params.items():
                    out = out.replace("${%s}" % k, str(v))
                return out
            return value
        if isinstance(value, list):
            return [self.expand(v) for v in value]
        if isinstance(value, dict):
            return {k: self.expand(v) for k, v in value.items()}
        return value

    # -- fields --------------------------------------------------------------
    def field(self, logical):
        concrete = self.datasource.resolve(logical)
        if not concrete:
            raise UnmappedFieldError(logical)
        return concrete

    def signature_pack(self, name):
        if name not in self.signatures:
            raise SpecError(f"unknown signature pack '{name}'")
        return self.signatures[name]


def _as_list(v):
    return v if isinstance(v, list) else [v]


# ---------------------------------------------------------------------------
# filter spec -> IR
# ---------------------------------------------------------------------------
def compile_filter(spec, ctx):
    if spec is None:
        return None
    spec = ctx.expand(spec)
    return _compile_node(spec, ctx)


def _compile_node(node, ctx):
    if isinstance(node, list):
        return _all([_compile_node(n, ctx) for n in node])
    if not isinstance(node, dict):
        raise SpecError(f"filter clause must be a mapping, got: {node!r}")

    combos = [k for k in ("all", "any", "none") if k in node]
    if combos:
        children = []
        for key in combos:
            sub = [_compile_node(n, ctx) for n in _as_list(node[key])]
            if key == "all":
                children.extend(sub)
            elif key == "any":
                children.append(_any(sub))
            else:
                children.append(_none(sub))
        return children[0] if len(children) == 1 else _all(children)

    if "signatures" in node:
        pack = ctx.signature_pack(node["signatures"])
        patterns = pack.patterns(severities=node.get("severities"),
                                 category=node.get("category"))
        field = ctx.field(pack.target_field)
        return ("wildcard", field, patterns, True)

    logical = node.get("field")
    if not logical:
        raise SpecError(f"filter clause needs 'field': {node!r}")
    field = ctx.field(logical)
    ci = node.get("case_insensitive", True)

    if "equals" in node:
        return ("term", field, node["equals"])
    if "in" in node:
        return ("terms", field, _as_list(node["in"]))
    if "in_param" in node:
        return ("terms", field, list(ctx.param(node["in_param"])))
    if "ip_in_param" in node:
        return ("ip_in", field, list(ctx.param(node["ip_in_param"])))
    if "wildcard" in node:
        return ("wildcard", field, _as_list(node["wildcard"]), ci)
    if "wildcard_param" in node:
        return ("wildcard", field, list(ctx.param(node["wildcard_param"])), ci)
    if "contains_param" in node:
        terms = [f"*{t}*" for t in ctx.param(node["contains_param"])]
        return ("wildcard", field, terms, ci)
    if "suffix_param" in node:
        terms = [f"*{t}" for t in ctx.param(node["suffix_param"])]
        return ("wildcard", field, terms, ci)
    if "prefix" in node:
        return ("prefix", field, _as_list(node["prefix"]), ci)
    if "prefix_param" in node:
        return ("prefix", field, list(ctx.param(node["prefix_param"])), ci)
    if "range" in node:
        return ("range", field, dict(node["range"]))
    if "exists" in node:
        return ("exists", field)
    raise SpecError(f"unrecognised filter clause: {node!r}")


# ---------------------------------------------------------------------------
# query spec -> CompiledQuery
# ---------------------------------------------------------------------------
SCALAR_KINDS = {"count", "cardinality", "sum", "avg", "min", "max"}
BUCKET_KINDS = {"terms", "date_histogram", "range_buckets",
                "signature_categories"}
ALL_KINDS = SCALAR_KINDS | BUCKET_KINDS | {"samples"}

SUBAGG_KINDS = {"cardinality", "sum", "avg", "min", "max", "filter",
                "top_terms"}


class CompiledQuery:
    """A fully resolved query: concrete fields, expanded params, IR filter."""

    def __init__(self, name, spec, ctx):
        spec = ctx.expand(spec)
        self.name = name
        self.spec = spec
        self.kind = spec.get("kind")
        if self.kind not in ALL_KINDS:
            raise SpecError(f"query '{name}': unknown kind '{self.kind}'")
        self.window = spec.get("window", "current")
        if self.window not in ("current", "previous"):
            raise SpecError(f"query '{name}': window must be "
                            f"current|previous")
        self.filter_ir = compile_filter(spec.get("filter"), ctx)
        self.optional = bool(spec.get("optional"))

        self.field = None
        if self.kind in ("cardinality", "sum", "avg", "min", "max",
                         "terms", "range_buckets"):
            self.field = ctx.field(spec["field"])

        self.size = int(spec.get("size", 10))
        self.missing = spec.get("missing")
        self.order_by = spec.get("order_by")          # sub-agg name or None
        self.ranges = spec.get("ranges")
        self.interval = spec.get("interval", "hour")

        self.pack = None
        self.other_bucket = spec.get("other_bucket", True)
        if self.kind == "signature_categories":
            self.pack = ctx.signature_pack(spec["pack"])
            self.category_field = ctx.field(self.pack.target_field)

        self.sample_fields = None
        if self.kind == "samples":
            # logical -> concrete, silently dropping unmapped ones so a
            # samples table degrades per-column instead of failing whole.
            self.sample_fields = {}
            for logical in spec.get("fields", []):
                concrete = ctx.datasource.resolve(logical)
                if concrete:
                    self.sample_fields[logical] = concrete

        # Sub-aggs on unmapped fields are dropped (the table column shows
        # "-") instead of failing the whole query - one datasource missing
        # e.g. `service` must not cost every other column of the table.
        self.sub_aggs = {}
        self.dropped_sub_aggs = []
        for sub_name, sub in (spec.get("sub_aggs") or {}).items():
            try:
                self.sub_aggs[sub_name] = CompiledSubAgg(name, sub_name,
                                                         sub, ctx)
            except UnmappedFieldError:
                self.dropped_sub_aggs.append(sub_name)


class CompiledSubAgg:
    def __init__(self, qname, name, spec, ctx):
        self.name = name
        self.kind = spec.get("kind")
        if self.kind not in SUBAGG_KINDS:
            raise SpecError(f"query '{qname}': sub-agg '{name}' has "
                            f"unknown kind '{self.kind}'")
        self.field = None
        if self.kind in ("cardinality", "sum", "avg", "min", "max",
                         "top_terms"):
            self.field = ctx.field(spec["field"])
        self.size = int(spec.get("size", 1))
        self.join = spec.get("join", ", ")
        self.missing = spec.get("missing")
        self.filter_ir = None
        if self.kind == "filter":
            self.filter_ir = compile_filter(spec.get("filter"), ctx)
            if self.filter_ir is None:
                raise SpecError(f"query '{qname}': filter sub-agg "
                                f"'{name}' needs a filter")


def compile_query(name, spec, ctx):
    return CompiledQuery(name, spec, ctx)
