"""Value formatting helpers shared by templates, rules and widgets."""
import datetime


def human_int(n):
    try:
        return f"{int(n or 0):,}"
    except (TypeError, ValueError):
        return str(n)


def human_bytes(n):
    try:
        n = float(n or 0)
    except (TypeError, ValueError):
        return str(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024.0:
            return f"{n:,.1f} {unit}"
        n /= 1024.0
    return f"{n:,.1f} PB"


def pct(part, whole):
    try:
        return (part / whole * 100) if whole else 0.0
    except TypeError:
        return 0.0


def delta_pct(now_v, prev_v):
    if not prev_v:
        return None
    try:
        return (now_v - prev_v) / prev_v * 100
    except TypeError:
        return None


def ellipsize(text, max_chars=60):
    """Middle truncation - for URLs and UAs both ends carry meaning."""
    text = str(text)
    if max_chars <= 1 or len(text) <= max_chars:
        return text
    if max_chars <= 4:
        return text[:max_chars]
    head = (max_chars - 1) * 2 // 3
    tail = max_chars - 1 - head
    return text[:head] + "…" + text[-tail:]


def fmt_local_dt(value, tz, fmt="%d %b %Y, %H:%M"):
    if value in (None, "", "-"):
        return "-"
    if isinstance(value, datetime.datetime):
        dt = value
    else:
        try:
            dt = datetime.datetime.fromisoformat(
                str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(tz).strftime(fmt)


FILTERS = {
    "human_int": human_int,
    "human_bytes": human_bytes,
    "pct_of": pct,
    "ellipsize": ellipsize,
}
