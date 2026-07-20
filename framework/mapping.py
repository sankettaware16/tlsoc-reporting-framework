"""
Field-map verification against the live Elasticsearch mapping.

Onboarding a datasource means guessing, for every logical field, whether
the concrete field is aggregatable as-is or needs its `.keyword` subfield.
Guessing wrong fails at REPORT time with either an empty table or a
"Fielddata is disabled on [x]" error, which is a slow and confusing way to
find out.

`framework check-fields` answers it directly: it reads the mapping of the
datasource's index pattern and reports, per logical field, whether the
mapping supports the declared usage - and what to write instead when it
does not.
"""

AGGREGATABLE_TYPES = {
    "keyword", "ip", "long", "integer", "short", "byte", "double", "float",
    "half_float", "scaled_float", "date", "boolean", "constant_keyword",
    "flattened", "version", "unsigned_long",
}

OK = "OK"
FIX = "FIX"
MISSING = "MISSING"
UNUSABLE = "UNUSABLE"


def flatten_mapping(mapping_response):
    """
    Merge the mappings of every index the pattern matched into
    {dotted field: {"type": str, "keyword_sub": bool}}.

    Indices are usually one-per-day with identical mappings; merging keeps
    the check meaningful when an older index differs (the stricter answer
    wins, since a query spans them all).
    """
    out = {}

    def walk(props, prefix=""):
        for name, spec in (props or {}).items():
            path = prefix + name
            if "properties" in spec:
                walk(spec["properties"], path + ".")
                continue
            ftype = spec.get("type", "object")
            has_kw = any(sub.get("type") == "keyword"
                         for sub in (spec.get("fields") or {}).values())
            prev = out.get(path)
            if prev is None:
                out[path] = {"type": ftype, "keyword_sub": has_kw}
            else:
                # Disagreement between indices: keep the weaker capability
                # so the report is not built on an assumption that holds
                # for only part of the window.
                if prev["type"] != ftype:
                    prev["type"] = "text" if "text" in (prev["type"], ftype) \
                        else prev["type"]
                prev["keyword_sub"] = prev["keyword_sub"] and has_kw

    for index_mapping in (mapping_response or {}).values():
        walk((index_mapping.get("mappings") or {}).get("properties"))
    return out


def check_field(concrete, fields):
    """
    Verify one declared concrete field against the flattened mapping.

    Returns (status, detail, suggestion).
    """
    base = concrete[: -len(".keyword")] if concrete.endswith(".keyword") \
        else concrete
    declared_keyword = concrete.endswith(".keyword")
    info = fields.get(base)

    if info is None:
        return (MISSING,
                f"'{base}' is not in the mapping",
                "check the field name, or drop it from the datasource")

    ftype = info["type"]

    if declared_keyword:
        if info["keyword_sub"]:
            return (OK, f"{ftype} + .keyword subfield", None)
        if ftype in AGGREGATABLE_TYPES:
            return (FIX,
                    f"'{base}' is {ftype} and has NO .keyword subfield",
                    base)
        return (UNUSABLE,
                f"'{base}' is {ftype} with no .keyword subfield",
                None)

    if ftype in AGGREGATABLE_TYPES:
        return (OK, ftype, None)
    if info["keyword_sub"]:
        return (FIX,
                f"'{base}' is {ftype}; aggregations need the keyword "
                f"subfield",
                f"{base}.keyword")
    return (UNUSABLE,
            f"'{base}' is {ftype} with no .keyword subfield - cannot be "
            f"aggregated",
            None)


def check_datasource(es_client, datasource):
    """
    Returns (rows, index_count). Each row:
        {logical, concrete, status, detail, suggestion}
    Raises whatever the ES client raises when the index cannot be read.
    """
    response = es_client.indices.get_mapping(index=datasource.index)
    response = dict(response)
    fields = flatten_mapping(response)
    rows = []
    for logical, concrete in sorted(datasource.fields.items()):
        status, detail, suggestion = check_field(concrete, fields)
        rows.append({"logical": logical, "concrete": concrete,
                     "status": status, "detail": detail,
                     "suggestion": suggestion})
    return rows, len(response)
