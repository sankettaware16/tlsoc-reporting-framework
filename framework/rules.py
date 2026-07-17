"""
Rule engine: computed metrics, insights, actions and badges.

Everything narrative in a report is data, not code:

    computed:
      - name: error_rate
        expr: "pct(q.err_4xx + q.err_5xx, q.total_requests)"

    insights:
      - when: "q.total_requests == 0"
        text: "No traffic was recorded... verify the pipeline."
        stop: true              # suppress all following insights

    actions:
      - when: "c.served_probes > 0"
        priority: P1
        owner: "SOC + Web team"
        text: "Confirm why probe paths returned 2xx: {{ ... }}"

    badges:
      - id: health
        label: Service health
        levels:
          - {when: "c.error_rate >= params.error_rate_crit",
             text: CRITICAL, color: red}
          - {text: HEALTHY, color: green}    # no `when` = default

`when`/`expr` are Jinja2 expressions; `text` is a Jinja2 template. Both see:
    q         query results        c       computed values
    params    merged parameters    window  the reporting window
    ds        datasource meta      helpers pct/delta_pct/human_int/...
"""
from jinja2 import Environment

from .formats import FILTERS, human_bytes, human_int, pct, delta_pct

_env = Environment()
_env.filters.update(FILTERS)

HELPERS = {
    "pct": pct,
    "delta_pct": delta_pct,
    "human_int": human_int,
    "human_bytes": human_bytes,
    "min": min,
    "max": max,
    "len": len,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "sum": sum,
}


class RuleError(Exception):
    pass


def eval_expr(expr, context):
    try:
        fn = _env.compile_expression(expr, undefined_to_none=True)
        return fn(**{**HELPERS, **context})
    except Exception as e:
        raise RuleError(f"expression failed: {expr!r}: {e}") from e


def render_text(template_str, context):
    tmpl = _env.from_string(template_str)
    return tmpl.render(**{**HELPERS, **context})


def run_computed(computed_specs, context):
    """Sequential: later entries see earlier ones through `c`."""
    c = context.setdefault("c", {})
    errors = []
    for item in (computed_specs or []):
        name, expr = item["name"], item["expr"]
        try:
            c[name] = eval_expr(expr, context)
        except RuleError as e:
            c[name] = None
            errors.append(f"computed '{name}': {e}")
    return errors


def run_insights(insight_specs, context):
    out, errors = [], []
    for rule in (insight_specs or []):
        try:
            if rule.get("when") is not None and \
                    not eval_expr(rule["when"], context):
                continue
            out.append(render_text(rule["text"], context).strip())
            if rule.get("stop"):
                break
        except RuleError as e:
            errors.append(f"insight: {e}")
    return out, errors


def run_actions(action_specs, context):
    out, errors = [], []
    for rule in (action_specs or []):
        try:
            if rule.get("when") is not None and \
                    not eval_expr(rule["when"], context):
                continue
            out.append({
                "priority": rule.get("priority", "P3"),
                "owner": render_text(rule.get("owner", ""), context),
                "text": render_text(rule["text"], context).strip(),
            })
        except RuleError as e:
            errors.append(f"action: {e}")
    out.sort(key=lambda a: a["priority"])
    return out, errors


BADGE_COLORS = {
    "red": "#bc4749",
    "amber": "#f3a712",
    "green": "#90be6d",
    "grey": "#94a3b8",
}


def run_badges(badge_specs, context):
    out, errors = [], []
    for badge in (badge_specs or []):
        chosen = None
        for level in badge.get("levels", []):
            try:
                if level.get("when") is None or \
                        eval_expr(level["when"], context):
                    chosen = level
                    break
            except RuleError as e:
                errors.append(f"badge '{badge.get('id')}': {e}")
        if chosen:
            out.append({
                "id": badge.get("id"),
                "label": badge.get("label", ""),
                "text": chosen.get("text", ""),
                "color": BADGE_COLORS.get(chosen.get("color"),
                                          chosen.get("color", "#94a3b8")),
            })
    return out, errors
