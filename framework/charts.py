"""
Inline-SVG charts: no JavaScript, explicit pixel sizes, so they render
identically in a browser, in wkhtmltopdf and in headless Chrome.

Sizing contract (mirrors templates/framework/base.html):
    A4 (210mm) - 10mm side margins = 190mm = 718px @ 96dpi.
    page 718 / padding 14        -> content 690
    full card inner              -> CHART_W_FULL = 650
    half card inner              -> CHART_W_HALF = 298
"""
import html
import math

PAGE_W = 718
PAGE_PAD = 14
GRID_GAP = 14
CARD_PAD = 16
KPI_GAP = 10

CARD_W_FULL = PAGE_W - 2 * PAGE_PAD                     # 690
CARD_W_HALF = (CARD_W_FULL - GRID_GAP) // 2             # 338
CHART_W_FULL = CARD_W_FULL - 2 * CARD_PAD - 2 - 6       # 650
CHART_W_HALF = CARD_W_HALF - 2 * CARD_PAD - 2 - 6       # 298


def kpi_width(cols):
    return (CARD_W_FULL - (cols - 1) * KPI_GAP) // cols


LAYOUT = {
    "page_w": PAGE_W, "page_pad": PAGE_PAD, "grid_gap": GRID_GAP,
    "card_pad": CARD_PAD, "card_w_full": CARD_W_FULL,
    "card_w_half": CARD_W_HALF, "kpi_gap": KPI_GAP,
}

INK = "#1f2937"
MUTED = "#94a3b8"
GRIDC = "#eef2f7"
NAVY = "#1f4e79"
BLUE = "#2f5597"
GREEN = "#3f8e3f"
AMBER = "#f3a712"
RED = "#bc4749"

PALETTE = {
    "blue": BLUE, "navy": NAVY, "green": GREEN, "amber": AMBER, "red": RED,
    "teal": "#3f7cac", "purple": "#c8b6e2", "sky": "#5fa8d3",
    "grey": "#b8b8b8", "faint": "#e2e8f0", "salmon": "#e07a5f",
}


def color(name):
    return PALETTE.get(name, name or BLUE)


def _esc(t):
    return html.escape(str(t))


def human_int(n):
    try:
        return f"{int(n or 0):,}"
    except (TypeError, ValueError):
        return str(n)


def _pct(part, whole):
    return (part / whole * 100) if whole else 0.0


def ellipsize(text, max_chars):
    """Middle truncation - for URLs the tail carries the meaning."""
    text = str(text)
    if max_chars <= 1 or len(text) <= max_chars:
        return text
    if max_chars <= 4:
        return text[:max_chars]
    head = (max_chars - 1) * 2 // 3
    tail = max_chars - 1 - head
    return text[:head] + "…" + text[-tail:]


def no_data(width, msg="No data in this window."):
    return (f'<svg width="{width}" height="46" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Arial,Helvetica,sans-serif">'
            f'<text x="0" y="26" font-size="12" fill="{MUTED}">{_esc(msg)}'
            f'</text></svg>')


def bar_chart(pairs, width=CHART_W_FULL, bar_h=19, gap=7, bar_color=BLUE,
              show_pct=False, font=11):
    """Horizontal bars with self-sizing label column (labels never collide)."""
    pairs = [(str(k), int(v or 0)) for k, v in pairs if k is not None]
    if not pairs:
        return no_data(width)

    max_v = max(v for _, v in pairs) or 1
    total = sum(v for _, v in pairs) or 1
    char_w = font * 0.56
    value_w = int(len(human_int(max_v)) * char_w) + (52 if show_pct else 10)
    value_w = max(value_w, 46)

    longest = max(len(k) for k, _ in pairs)
    label_w = int(min(max(longest * char_w + 10, width * 0.18), width * 0.46))
    max_chars = max(int((label_w - 10) / char_w), 6)
    plot_w = width - label_w - value_w
    height = len(pairs) * (bar_h + gap) + gap

    rows = []
    y = gap
    for label, val in pairs:
        bw = max(int((val / max_v) * plot_w), 2)
        lbl = _esc(ellipsize(label, max_chars))
        vtxt = human_int(val)
        if show_pct:
            vtxt += f"  {_pct(val, total):.1f}%"
        rows.append(
            f'<text x="{label_w - 8}" y="{y + bar_h * 0.72:.0f}" '
            f'text-anchor="end" font-size="{font}" fill="{INK}">{lbl}</text>'
            f'<rect x="{label_w}" y="{y}" width="{plot_w}" height="{bar_h}" '
            f'rx="2" fill="{GRIDC}"></rect>'
            f'<rect x="{label_w}" y="{y}" width="{bw}" height="{bar_h}" '
            f'rx="2" fill="{bar_color}"></rect>'
            f'<text x="{label_w + plot_w + 6}" y="{y + bar_h * 0.72:.0f}" '
            f'font-size="{font}" fill="{INK}">{vtxt}</text>')
        y += bar_h + gap
    return (f'<svg width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Arial,Helvetica,sans-serif">{"".join(rows)}</svg>')


def donut(segments, width=CHART_W_HALF, size=132, thickness=26,
          center_label="events"):
    """Donut + legend as ONE svg (HTML legends drift in PDF renderers)."""
    segments = [(l, int(v or 0), c) for l, v, c in segments]
    total = sum(v for _, v, _ in segments)
    if total <= 0:
        return no_data(width)

    cx = cy = size / 2
    r = (size - thickness) / 2
    circ = 2 * math.pi * r
    offset = 0.0
    arcs = []
    for _, val, col in segments:
        if val <= 0:
            continue
        dash = (val / total) * circ
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" '
            f'stroke-width="{thickness}" '
            f'stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"></circle>')
        offset += dash
    arcs.append(
        f'<text x="{cx}" y="{cy - 1}" text-anchor="middle" font-size="17" '
        f'font-weight="bold" fill="{NAVY}">{human_int(total)}</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" font-size="9" '
        f'fill="{MUTED}">{_esc(center_label)}</text>')

    lx = size + 14
    row_h = 30
    ly = 10
    legend = []
    for lbl, val, col in segments:
        if val <= 0 and len(segments) > 6:
            continue
        legend.append(
            f'<rect x="{lx}" y="{ly + 1}" width="9" height="9" rx="2" '
            f'fill="{col}"></rect>'
            f'<text x="{lx + 15}" y="{ly + 9}" font-size="10.5" fill="{INK}">'
            f'{_esc(lbl)}</text>'
            f'<text x="{lx + 15}" y="{ly + 22}" font-size="10.5" '
            f'fill="{MUTED}">{human_int(val)} ({_pct(val, total):.1f}%)'
            f'</text>')
        ly += row_h
    height = max(size, ly + 4)
    return (f'<svg width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" '
            f'xmlns="http://www.w3.org/2000/svg" '
            f'font-family="Arial,Helvetica,sans-serif">'
            f'{"".join(arcs)}{"".join(legend)}</svg>')


def timeseries(buckets, overlay=None, width=CHART_W_FULL, height=196,
               line_color=BLUE, tz_label="", series_label="events / hour",
               overlay_label="overlay"):
    """
    Line chart over gap-free hourly buckets [{label, count}], with a mean
    line, a clamped peak callout and an optional bar overlay (e.g. probes).
    """
    if not buckets or not any(b["count"] for b in buckets):
        return no_data(width, "No activity recorded in this window.")

    values = [b["count"] for b in buckets]
    labels = [str(b.get("label", ""))[:5] for b in buckets]
    over = [b["count"] for b in (overlay or [])]
    if len(over) != len(values):
        over = []

    max_v = max(values) or 1
    mean_v = sum(values) / len(values)
    peak_i = max(range(len(values)), key=lambda i: values[i])

    pad_l, pad_r, pad_t, pad_b = 48, 12, 26, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(values)
    step = plot_w / max(n - 1, 1)

    def X(i):
        return pad_l + i * step

    def Y(v):
        return pad_t + plot_h - (v / max_v) * plot_h

    pts = [(X(i), Y(v)) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = (f"{X(0):.1f},{pad_t + plot_h:.1f} " + line +
            f" {X(n - 1):.1f},{pad_t + plot_h:.1f}")

    grid = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_t + plot_h - frac * plot_h
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + plot_w}" '
            f'y2="{gy:.1f}" stroke="{GRIDC}" stroke-width="1"></line>'
            f'<text x="{pad_l - 6}" y="{gy + 3:.1f}" font-size="9" '
            f'fill="{MUTED}" text-anchor="end">'
            f'{human_int(int(max_v * frac))}</text>')

    my = Y(mean_v)
    mean_line = (
        f'<line x1="{pad_l}" y1="{my:.1f}" x2="{pad_l + plot_w}" '
        f'y2="{my:.1f}" stroke="{MUTED}" stroke-width="1" '
        f'stroke-dasharray="4 3"></line>'
        f'<text x="{pad_l + plot_w}" y="{my - 4:.1f}" font-size="8.5" '
        f'fill="{MUTED}" text-anchor="end">mean {human_int(int(mean_v))}'
        f'</text>')

    xlabels = []
    tick_every = max(1, n // 8)
    for i in range(0, n, tick_every):
        xlabels.append(
            f'<text x="{X(i):.1f}" y="{height - 10}" font-size="9" '
            f'fill="{MUTED}" text-anchor="middle">{_esc(labels[i])}</text>')

    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.8" '
        f'fill="{line_color}"></circle>' for x, y in pts)

    overlay_layer = ""
    if over and max(over) > 0:
        omax = max(over) or 1
        bw = max(step * 0.5, 1.5)
        bars = []
        for i, v in enumerate(over):
            if v <= 0:
                continue
            bh = (v / omax) * (plot_h * 0.32)
            bars.append(
                f'<rect x="{X(i) - bw / 2:.1f}" '
                f'y="{pad_t + plot_h - bh:.1f}" width="{bw:.1f}" '
                f'height="{bh:.1f}" fill="{RED}" opacity="0.35"></rect>')
        overlay_layer = "".join(bars)

    px, py = pts[peak_i]
    px_c = min(max(px, pad_l + 60), pad_l + plot_w - 60)
    py_lbl = py - 8 if py > pad_t + 14 else py + 15
    peak = (
        f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{RED}"></circle>'
        f'<text x="{px_c:.1f}" y="{py_lbl:.1f}" font-size="9.5" '
        f'font-weight="bold" fill="{RED}" text-anchor="middle">'
        f'peak {human_int(values[peak_i])} @ {_esc(labels[peak_i])}</text>')

    legend_txt = f"{series_label} ({tz_label})" if tz_label else series_label
    if overlay_layer:
        legend_txt += f"  •  red bars = {overlay_label}"
    legend = (f'<text x="{pad_l}" y="12" font-size="9" fill="{MUTED}">'
              f'{_esc(legend_txt)}</text>')

    return (
        f'<svg width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="Arial,Helvetica,sans-serif">'
        f'{"".join(grid)}{overlay_layer}'
        f'<polygon points="{area}" fill="{line_color}" opacity="0.10">'
        f'</polygon>'
        f'<polyline points="{line}" fill="none" stroke="{line_color}" '
        f'stroke-width="1.8"></polyline>{dots}{mean_line}{peak}'
        f'{"".join(xlabels)}{legend}</svg>')
