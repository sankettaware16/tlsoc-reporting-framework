"""
Post-query row transforms, referenced from a query's `transforms:` list.

    transforms:
      - classify_ip: {}                    # adds scope / note / location
      - cluster_paths: {depth: 4}          # roll paths up by prefix
      - min_count: {value: 500}            # keep rows with count >= value
      - limit: {size: 10}

Transforms are deliberately generic: they know nothing about nginx or
moodle. Anything source-specific (campus CIDRs, known bot prefixes) comes
in through params.
"""
import ipaddress

_RFC1918 = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]


def classify_ip_value(ip_str, params):
    """Return (scope, note): INTERNAL / BOT / EXTERNAL."""
    for pfx, name in (params.get("bot_ip_prefixes") or {}).items():
        if str(ip_str).startswith(pfx):
            return ("BOT", name)
    try:
        ip = ipaddress.ip_address(str(ip_str))
    except ValueError:
        return ("EXTERNAL", "")
    for net in _RFC1918:
        if ip in net:
            return ("INTERNAL", "private range")
    for cidr in (params.get("internal_cidrs") or []):
        try:
            if ip in ipaddress.ip_network(cidr):
                return ("INTERNAL", "org range")
        except ValueError:
            continue
    return ("EXTERNAL", "")


def t_classify_ip(rows, opts, params):
    ip_key = opts.get("ip_key", "key")
    for r in rows:
        scope, note = classify_ip_value(r.get(ip_key), params)
        r["scope"] = scope
        r["note"] = note
        city = r.get(opts.get("city_key", "city"))
        country = r.get(opts.get("country_key", "country"))
        parts = [p for p in (city, country) if p and p != "-"]
        if scope == "INTERNAL":
            r["location"] = "Internal"
        elif scope == "BOT":
            r["location"] = note
        else:
            r["location"] = ", ".join(parts) or "Unknown"
    return rows


def t_cluster_paths(rows, opts, params):
    """
    Roll per-path rows up by the first `depth` path segments. Individually
    listed error paths hide storms (hundreds of unique generated URLs under
    one prefix at a few hits each); bucketing makes the cluster one row.
    """
    depth = int(opts.get("depth", 4))
    path_key = opts.get("path_key", "key")
    out = {}
    for r in rows:
        segs = [s for s in str(r.get(path_key, "")).split("/") if s]
        prefix = "/" + "/".join(segs[:depth]) + \
            ("/…" if len(segs) > depth else "")
        e = out.setdefault(prefix, {"key": prefix, "count": 0, "paths": 0})
        e["count"] += r.get("count", 0)
        e["paths"] += 1
        for extra_key in opts.get("collect", []):
            vals = set(str(r.get(extra_key, "")).split(", ")) - {"", "-"}
            got = set(str(e.get(extra_key, "")).split(", ")) - {"", "-"}
            e[extra_key] = ", ".join(sorted(got | vals))
    rows = sorted(out.values(), key=lambda r: -r["count"])
    return rows


def t_min_count(rows, opts, params):
    threshold = opts.get("value", 0)
    key = opts.get("key", "count")
    return [r for r in rows if (r.get(key) or 0) >= threshold]


def t_limit(rows, opts, params):
    return rows[: int(opts.get("size", 10))]


def t_derive_pct(rows, opts, params):
    """Add a percentage column: to = num / den * 100 (per row)."""
    num, den, to = opts.get("num"), opts.get("den", "count"), opts["to"]
    for r in rows:
        d = r.get(den) or 0
        r[to] = (r.get(num) or 0) / d * 100 if d else 0.0
    return rows


def t_flag_match(rows, opts, params):
    """
    Record WHICH configured term classified this row (e.g. which bot
    user-agent substring hit). Middle-truncated cells can hide the evidence;
    naming the matched term makes an over-broad entry visible.
    """
    key = opts.get("key", "key")
    to = opts.get("to", "matched")
    terms = [str(t).lower() for t in params.get(opts["terms_param"], [])]
    fallbacks = [str(v) for v in params.get(opts.get("fallback_param", ""),
                                            [])]
    for r in rows:
        val = str(r.get(key, "")).lower()
        hit = next((t for t in terms if t in val), None)
        if hit is None and (str(r.get(key)) in fallbacks
                            or str(r.get(key)) == "(no user-agent)"):
            hit = "no user-agent sent"
        r[to] = hit or "-"
    return rows


def t_sort(rows, opts, params):
    key = opts.get("key", "count")
    reverse = bool(opts.get("desc", True))
    return sorted(rows, key=lambda r: (r.get(key) is None, r.get(key)),
                  reverse=reverse)


TRANSFORMS = {
    "classify_ip": t_classify_ip,
    "cluster_paths": t_cluster_paths,
    "min_count": t_min_count,
    "limit": t_limit,
    "sort": t_sort,
    "derive_pct": t_derive_pct,
    "flag_match": t_flag_match,
}


def apply_transforms(rows, transform_specs, params):
    for spec in (transform_specs or []):
        if isinstance(spec, str):
            name, opts = spec, {}
        else:
            name, opts = next(iter(spec.items()))
            opts = opts or {}
        fn = TRANSFORMS.get(name)
        if fn is None:
            raise ValueError(f"unknown transform '{name}'")
        if not isinstance(rows, list):
            raise ValueError(f"transform '{name}' needs row results")
        rows = fn(rows, opts, params)
    return rows
