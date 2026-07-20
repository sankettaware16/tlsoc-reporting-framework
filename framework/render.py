"""
Section renderer: resolves each `sections:` entry of a report definition
into fully-prepared widget data (formatted cells, generated SVG) and renders
the final HTML through templates/framework/.

Widget catalogue (section `type:`):
    heading     kpi_row     insights    actions     text
    timeseries  donut       bars        table       samples
    row         (two half-width child sections side by side)

Every section supports:
    show_if:            expression - section is dropped when falsy
    show_note_if:       expression - the note is dropped when falsy, while
                        the widget itself still renders
    skip_if_unmapped:   [logical fields] - dropped when the datasource
                        does not map them (graceful degradation)
"""
import datetime

from jinja2 import Environment, FileSystemLoader

from . import charts
from .formats import (FILTERS, ellipsize, fmt_local_dt, human_bytes,
                      human_int, pct)
from .rules import RuleError, eval_expr, render_text
from .settings import TEMPLATE_DIR

SEV_COLORS = {"critical": "#bc4749", "high": "#e07a5f",
              "medium": "#f3a712", "low": "#94a3b8"}


def make_env():
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR),
                      autoescape=False)
    env.filters.update(FILTERS)
    return env


# ---------------------------------------------------------------------------
# cell / value formatting
# ---------------------------------------------------------------------------
def format_value(value, fmt, tz=None):
    if value is None or value == "":
        return "-"
    if fmt == "int":
        return human_int(value)
    if fmt == "bytes":
        return human_bytes(value)
    if fmt == "pct":
        return f"{float(value):.1f}%"
    if fmt == "pct2":
        return f"{float(value):.2f}%"
    if fmt == "num1":
        return f"{float(value):,.1f}"
    if fmt == "dt":
        return fmt_local_dt(value, tz) if tz else str(value)
    return str(value)


NUMERIC_FORMATS = {"int", "bytes", "pct", "pct2", "num1"}


def prepare_cell(row, col, tz):
    fmt = col.get("format", "text")
    key = col.get("key")
    value = row.get(key)
    cls = []
    if fmt in NUMERIC_FORMATS or col.get("align") == "right":
        cls.append("num")
    if fmt == "mono" or col.get("mono"):
        cls.append("mono")
    if col.get("wrap"):
        cls.append("wrap")
    if col.get("nowrap"):
        cls.append("nw")

    if fmt == "sev":
        sev = str(value or "low")
        color = SEV_COLORS.get(sev, "#94a3b8")
        return {"html": f'<span class="sev" style="background:{color}">'
                        f'{sev.upper()}</span>',
                "cls": " ".join(cls)}
    if fmt == "pill":
        pill_cls = (col.get("pill_map") or {}).get(str(value), "grey")
        return {"html": f'<span class="pill {pill_cls}">{value}</span>',
                "cls": " ".join(cls)}

    text = format_value(value, fmt, tz)
    if col.get("max"):
        text = ellipsize(text, int(col["max"]))
    return {"text": text, "cls": " ".join(cls)}


# ---------------------------------------------------------------------------
# section preparation
# ---------------------------------------------------------------------------
class SectionBuilder:
    def __init__(self, context, datasource, window):
        self.ctx = context
        self.ds = datasource
        self.window = window
        self.warnings = []

    def _eval(self, expr, default=None):
        try:
            return eval_expr(expr, self.ctx)
        except RuleError as e:
            self.warnings.append(str(e))
            return default

    def _text(self, template_str, default=""):
        try:
            return render_text(template_str, self.ctx)
        except Exception as e:
            self.warnings.append(f"text render failed: {e}")
            return default

    def _rows(self, spec):
        """Rows for table/bars/samples: `query: name` or `rows: <expr>`."""
        if spec.get("rows"):
            rows = self._eval(spec["rows"], [])
        else:
            rows = self.ctx["q"].get(spec.get("query"))
        return rows if isinstance(rows, list) else []

    def build_all(self, section_specs):
        out = []
        for spec in section_specs:
            sec = self.build(spec)
            if sec is not None:
                out.append(sec)
        return out

    def build(self, spec, half=False):
        # -- graceful degradation checks --------------------------------
        for logical in spec.get("skip_if_unmapped", []):
            if not self.ds.resolve(logical):
                return None
        if spec.get("show_if") is not None and \
                not self._eval(spec["show_if"]):
            return None

        builder = getattr(self, f"_build_{spec['type']}", None)
        if builder is None:
            self.warnings.append(f"unknown section type '{spec['type']}'")
            return None
        sec = builder(spec, half)
        if sec is None:
            return None
        sec["type"] = spec["type"]
        sec["title"] = self._text(spec.get("title", "")) or None
        sec["hint"] = self._text(spec.get("hint", "")) or None
        if spec.get("show_note_if") is not None and \
                not self._eval(spec["show_note_if"]):
            sec["note"] = None
        else:
            sec["note"] = self._text(spec.get("note", "")) or None
        sec["half"] = half
        return sec

    # -- widgets ----------------------------------------------------------
    def _build_heading(self, spec, half):
        return {}

    def _build_text(self, spec, half):
        return {"body": self._text(spec.get("body", ""))}

    def _build_insights(self, spec, half):
        items = self.ctx.get("insights") or []
        if not items:
            return None
        return {"items": items}

    def _build_actions(self, spec, half):
        items = self.ctx.get("actions") or []
        if not items:
            return None
        return {"items": items}

    def _build_kpi_row(self, spec, half):
        items = []
        for item in spec.get("items", []):
            value = self._eval(item.get("value", "None"))
            entry = {
                "label": self._text(item.get("label", "")),
                "value": format_value(value, item.get("format", "int"),
                                      self.window.tz),
                "style": "",
                "foot": "",
                "foot_cls": "",
            }
            if item.get("style"):
                entry["style"] = self._eval(item["style"], "") or ""
            if item.get("delta") is not None:
                d = self._eval(item["delta"])
                if d is None:
                    entry["foot"] = "no reliable baseline"
                else:
                    arrow = "▲" if d > 0 else ("▼" if d < 0 else "—")
                    entry["foot"] = (f"{arrow} {abs(d):.1f}% vs previous "
                                     f"{self.window.hours}h")
                    good_down = bool(item.get("down_is_good"))
                    up_cls = "down" if good_down else "up"
                    down_cls = "up" if good_down else "down"
                    entry["foot_cls"] = up_cls if d > 0 else \
                        (down_cls if d < 0 else "")
            elif item.get("foot"):
                entry["foot"] = self._text(item["foot"])
            items.append(entry)
        cols = max(len(items), 1)
        return {"items": items, "kpi_w": charts.kpi_width(cols)}

    def _build_timeseries(self, spec, half):
        rows = self._rows(spec)
        overlay = None
        if spec.get("overlay"):
            overlay = self.ctx["q"].get(spec["overlay"])
        svg = charts.timeseries(
            rows, overlay=overlay,
            width=charts.CHART_W_HALF if half else charts.CHART_W_FULL,
            line_color=charts.color(spec.get("color", "blue")),
            tz_label=self.window.tz_label,
            series_label=spec.get("series_label", "events / hour"),
            overlay_label=spec.get("overlay_label", "overlay"),
        )
        return {"svg": svg}

    def _build_donut(self, spec, half):
        segments = []
        for s in spec.get("slices", []):
            val = self._eval(s.get("expr", "0"), 0) or 0
            segments.append((self._text(s.get("label", "")), val,
                             charts.color(s.get("color"))))
        svg = charts.donut(
            segments,
            width=charts.CHART_W_HALF if half else charts.CHART_W_FULL,
            center_label=spec.get("center_label", "events"))
        return {"svg": svg}

    def _build_bars(self, spec, half):
        rows = self._rows(spec)
        label_key = spec.get("label_key", "key")
        value_key = spec.get("value_key", "count")
        pairs = [(r.get(label_key), r.get(value_key)) for r in rows]
        svg = charts.bar_chart(
            pairs,
            width=charts.CHART_W_HALF if half else charts.CHART_W_FULL,
            bar_color=charts.color(spec.get("color", "blue")),
            show_pct=bool(spec.get("show_pct")),
            font=10 if half else 11)
        return {"svg": svg}

    def _build_table(self, spec, half):
        rows = self._rows(spec)
        columns = spec.get("columns", [])
        if not rows and spec.get("hide_if_empty"):
            return None
        prepared = [[prepare_cell(r, col, self.window.tz)
                     for col in columns] for r in rows]
        return {
            "headers": [{"label": c.get("label", c.get("key", "")),
                         "width": c.get("width"),
                         "cls": "num" if (c.get("format") in NUMERIC_FORMATS
                                          or c.get("align") == "right")
                         else ""} for c in columns],
            "rows": prepared,
            "empty_text": self._text(
                spec.get("empty_text", "Nothing recorded in this window.")),
        }

    def _build_samples(self, spec, half):
        return self._build_table(spec, half)

    def _build_row(self, spec, half):
        left = self.build(spec["left"], half=True) if spec.get("left") \
            else None
        right = self.build(spec["right"], half=True) if spec.get("right") \
            else None
        if left is None and right is None:
            return None
        return {"left": left, "right": right}


# ---------------------------------------------------------------------------
# final assembly
# ---------------------------------------------------------------------------
def render_report(report, datasource, settings, window, context, sections):
    env = make_env()
    template = env.get_template(report.doc.get("template", "base.html"))
    now_local = datetime.datetime.now(window.tz)
    return template.render(
        report=report,
        ds={"name": datasource.name, "label": datasource.label,
            "index": datasource.index, "profile": datasource.profile},
        org=settings["org"],
        window={
            "label": window.label,
            "hours": window.hours,
            "tz_label": window.tz_label,
            "date": window.date,
        },
        generated_at=now_local.strftime("%d %b %Y, %H:%M ")
        + window.tz_label,
        badges=context.get("badges", []),
        warnings=context.get("data_warnings", []),
        sections=sections,
        layout=charts.LAYOUT,
        framework_version="1.0.0",
    )
