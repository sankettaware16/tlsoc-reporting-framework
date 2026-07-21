"""
Orchestrator: (report definition, datasource) -> HTML + PDF.

Pipeline:
    1. merge params           report defaults <- datasource <- CLI
    2. resolve window         whole-hour aligned in the report timezone
    3. compile + run queries  unmapped logical fields degrade, not crash
    4. apply transforms
    5. computed / insights / actions / badges   (rule engine)
    6. build sections         skip_if_unmapped + show_if honoured here
    7. render HTML, then PDF via the engine chain
"""
import datetime
import os

from .backends import ESBackend, LocalBackend
from .pdf import PDFError, html_to_pdf
from .queryspec import (QueryContext, SpecError, UnmappedFieldError,
                        compile_query, SCALAR_KINDS)
from .registry import Registry
from .render import SectionBuilder, render_report
from .rules import run_actions, run_badges, run_computed, run_insights
from .settings import load_settings
from .transforms import apply_transforms
from .window import resolve_window


class GenerateError(Exception):
    pass


def _empty_result(kind):
    if kind in SCALAR_KINDS:
        return None
    if kind == "range_buckets":
        return {}
    return []


class RunResult:
    def __init__(self):
        self.html_path = None
        self.pdf_path = None
        self.pdf_engine = None
        self.warnings = []
        self.skipped_queries = []


def generate(report_name, datasource_name, *,
             settings=None, registry=None,
             backend="es", sample_paths=None,
             window_hours=None, window_end=None,
             formats=None, cli_params=None,
             out_html_dir=None, out_pdf_dir=None):
    settings = settings or load_settings()
    registry = registry or Registry()
    result = RunResult()

    report = registry.reports.get(report_name)
    if report is None:
        raise GenerateError(f"unknown report '{report_name}'. "
                            f"Available: {sorted(registry.reports)}")
    ds = registry.datasources.get(datasource_name)
    if ds is None:
        raise GenerateError(f"unknown datasource '{datasource_name}'. "
                            f"Available: {sorted(registry.datasources)}")
    if not ds.supports(report.profile):
        raise GenerateError(
            f"datasource '{ds.name}' (profile '{ds.profile}') does not "
            f"support report '{report.name}' (profile '{report.profile}'). "
            f"Add '{report.profile}' to its extra_profiles if intended.")

    params = registry.merged_params(report, ds, cli_params)
    hours = int(window_hours or params.get("window_hours", 24))
    tz_name = settings["locale"]["timezone"]
    tz_label = settings["locale"]["tz_label"]

    # -- backend ------------------------------------------------------------
    if backend == "local":
        if not sample_paths:
            raise GenerateError("local backend needs --sample <ndjson file>")
        be = LocalBackend(sample_paths, ds, None)
        if window_end is None:
            # Preview mode: anchor the window to the newest sample document
            # (ceiled to the next whole hour) so the report covers the data.
            max_ts = be.max_timestamp()
            if max_ts is None:
                raise GenerateError("sample file has no parseable timestamps")
            window_end = (max_ts + datetime.timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0)
        window = resolve_window(hours, tz_name, tz_label, end=window_end)
        be.window = window
    else:
        window = resolve_window(hours, tz_name, tz_label, end=window_end)
        be = ESBackend(settings, ds, window)

    # -- queries --------------------------------------------------------------
    qctx = QueryContext(ds, registry.signatures, params, window)
    q = {}
    attempted = failed = 0
    first_failure = None
    for name, spec in report.queries.items():
        try:
            cq = compile_query(name, spec, qctx)
        except UnmappedFieldError as e:
            q[name] = _empty_result(spec.get("kind"))
            result.skipped_queries.append(name)
            if not spec.get("optional"):
                result.warnings.append(
                    f"Query '{name}' skipped: {e.logical} is not mapped by "
                    f"datasource '{ds.name}'. The dependent section is "
                    f"omitted from this report.")
            continue
        except SpecError as e:
            raise GenerateError(f"report '{report.name}', query '{name}': "
                                f"{e}") from e
        attempted += 1
        try:
            rows = be.execute(cq)
            q[name] = apply_transforms(rows, cq.spec.get("transforms"),
                                       params)
        except Exception as e:  # noqa: BLE001 - a query must not kill the run
            q[name] = _empty_result(cq.kind)
            failed += 1
            first_failure = first_failure or str(e)
            result.warnings.append(f"Query '{name}' failed: {e}")

    # An individual query failing degrades one section. EVERY query failing
    # means the backend is unreachable or refusing us - the cluster is down,
    # credentials expired, the CA no longer matches. Emitting a report then
    # produces a document of zeros that reads as "no traffic, no attacks",
    # which is far more dangerous unattended than no report at all.
    if attempted and failed == attempted:
        raise GenerateError(
            f"all {attempted} queries failed - no report written. "
            f"First error: {first_failure}")

    # -- rule engine ---------------------------------------------------------
    context = {
        "q": q,
        "c": {},
        "params": params,
        "window": {
            "hours": window.hours, "label": window.label,
            "tz_label": window.tz_label, "date": str(window.date),
            "start": window.fmt_local(window.start),
            "end": window.fmt_local(window.end),
        },
        "ds": {"name": ds.name, "label": ds.label, "index": ds.index},
    }
    errors = run_computed(report.computed, context)
    insights, err_i = run_insights(report.insights, context)
    context["insights"] = insights
    actions, err_a = run_actions(report.actions, context)
    context["actions"] = actions
    badges, err_b = run_badges(report.badges, context)
    context["badges"] = badges
    for e in errors + err_i + err_a + err_b:
        result.warnings.append(e)

    # data-quality warnings computed by the report itself (e.g. an
    # implausibly small previous window) surface in the header block.
    context["data_warnings"] = [w for w in
                                (context["c"].get("data_warnings") or [])
                                if w]
    dw = context["c"].get("data_warning")
    if dw:
        context["data_warnings"].append(dw)
    context["data_warnings"].extend(
        w for w in result.warnings if w.startswith("Query '"))

    # -- sections + render -----------------------------------------------------
    builder = SectionBuilder(context, ds, window)
    sections = builder.build_all(report.sections)
    result.warnings.extend(builder.warnings)

    html_out = render_report(report, ds, settings, window, context, sections)

    html_dir = out_html_dir or settings["output"]["html_dir"]
    pdf_dir = out_pdf_dir or settings["output"]["pdf_dir"]
    os.makedirs(html_dir, exist_ok=True)
    # <slug>_<datasource>_<YYYY-MM-DD>. The slug defaults to the report
    # name; reports set it explicitly so the on-disk naming stays stable
    # even if a report is renamed. Downstream delivery matches on this
    # pattern, so it is part of the contract, not a display detail.
    stem = f"{report.slug}_{ds.name}_{window.date}"
    formats = formats or settings["output"].get("formats", ["html", "pdf"])

    result.html_path = os.path.join(html_dir, f"{stem}.html")
    with open(result.html_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    if "pdf" in formats:
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{stem}.pdf")
        footer = f"{report.title} — {settings['org']['name']}"
        try:
            result.pdf_engine = html_to_pdf(result.html_path, pdf_path,
                                            settings.get("pdf", {}), footer)
            result.pdf_path = pdf_path
        except PDFError as e:
            result.warnings.append(f"PDF generation failed (HTML still "
                                   f"written): {e}")
    return result
