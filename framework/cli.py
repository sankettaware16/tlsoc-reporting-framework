"""
Command-line interface.

    python3 -m framework list
    python3 -m framework validate
    python3 -m framework generate --report web_daily --datasource nginx
    python3 -m framework generate --report web_daily --datasource moodle \
            --backend local --sample ../log_samples/moodleapplication_sample.json
    python3 -m framework generate-all

Run from the reporting/ directory (or use ./reportgen.py from anywhere).
"""
import argparse
import datetime
import sys

from .generate import GenerateError, generate
from .queryspec import (QueryContext, SpecError, UnmappedFieldError,
                        compile_query)
from .registry import ConfigError, Registry
from .settings import load_settings
from .window import resolve_window


def _parse_params(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--param must be key=value, got: {pair}")
        k, v = pair.split("=", 1)
        for cast in (int, float):
            try:
                v = cast(v)
                break
            except ValueError:
                continue
        out[k] = v
    return out


def cmd_list(args):
    registry = Registry()
    print("Datasources:")
    for ds in registry.datasources.values():
        extra = f" (+{', '.join(ds.extra_profiles)})" \
            if ds.extra_profiles else ""
        print(f"  {ds.name:<12} profile={ds.profile}{extra:<18} "
              f"index={ds.index}")
    print("\nReports:")
    for rep in registry.reports.values():
        print(f"  {rep.name:<18} profile={rep.profile:<12} {rep.title}")
    print("\nRunnable combinations:")
    for rep, ds in registry.pairs():
        print(f"  {rep.name} × {ds.name}")
    return 0


def cmd_validate(args):
    """Compile every report against every compatible datasource: catches
    bad specs, unknown params/signature packs and unmapped fields without
    touching Elasticsearch."""
    try:
        registry = Registry()
    except ConfigError as e:
        print(f"CONFIG ERROR: {e}")
        return 1
    settings = load_settings()
    window = resolve_window(24, settings["locale"]["timezone"],
                            settings["locale"]["tz_label"])
    failures = 0
    for rep, ds in registry.pairs():
        params = registry.merged_params(rep, ds)
        qctx = QueryContext(ds, registry.signatures, params, window)
        unmapped, errors = [], []
        for name, spec in rep.queries.items():
            try:
                compile_query(name, spec, qctx)
            except UnmappedFieldError as e:
                unmapped.append(f"{name} ({e.logical})")
            except SpecError as e:
                errors.append(f"{name}: {e}")
        status = "OK"
        if errors:
            status = "ERROR"
            failures += 1
        print(f"[{status:>5}] {rep.name} × {ds.name}")
        for e in errors:
            print(f"         spec error: {e}")
        if unmapped:
            print(f"         degraded (unmapped, sections will be omitted): "
                  f"{', '.join(unmapped)}")
    return 1 if failures else 0


def _run_one(rep_name, ds_name, args, settings, registry):
    window_end = None
    if args.window_end:
        window_end = datetime.datetime.fromisoformat(args.window_end)
    result = generate(
        rep_name, ds_name,
        settings=settings, registry=registry,
        backend=args.backend, sample_paths=args.sample,
        window_hours=args.window_hours, window_end=window_end,
        formats=args.formats.split(",") if args.formats else None,
        cli_params=_parse_params(args.param),
        out_html_dir=args.out_html, out_pdf_dir=args.out_pdf,
    )
    print(f"HTML: {result.html_path}")
    if result.pdf_path:
        print(f"PDF:  {result.pdf_path}  (engine: {result.pdf_engine})")
    for w in result.warnings:
        print(f"  warning: {w}")
    return result


def cmd_generate(args):
    settings = load_settings()
    registry = Registry()
    try:
        _run_one(args.report, args.datasource, args, settings, registry)
    except GenerateError as e:
        print(f"ERROR: {e}")
        return 1
    return 0


def cmd_generate_all(args):
    """Every runnable (report × datasource) pair - the cron entry point."""
    settings = load_settings()
    registry = Registry()
    failures = 0
    for rep, ds in registry.pairs():
        print(f"--- {rep.name} × {ds.name} ---")
        try:
            _run_one(rep.name, ds.name, args, settings, registry)
        except GenerateError as e:
            print(f"ERROR: {e}")
            failures += 1
    return 1 if failures else 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="reportgen",
        description="TLSOC declarative reporting framework")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show datasources, reports, combinations")
    sub.add_parser("validate",
                   help="compile all reports against all datasources")

    def add_common(sp):
        sp.add_argument("--backend", choices=["es", "local"], default="es")
        sp.add_argument("--sample", action="append",
                        help="NDJSON sample file (local backend); repeatable")
        sp.add_argument("--window-hours", type=int, default=None)
        sp.add_argument("--window-end", default=None,
                        help="ISO timestamp; default: last complete hour "
                             "(ES) / newest sample doc (local)")
        sp.add_argument("--formats", default=None, help="html,pdf")
        sp.add_argument("--param", action="append",
                        help="override a report param: key=value; repeatable")
        sp.add_argument("--out-html", default=None)
        sp.add_argument("--out-pdf", default=None)

    g = sub.add_parser("generate", help="generate one report")
    g.add_argument("--report", required=True)
    g.add_argument("--datasource", required=True)
    add_common(g)

    ga = sub.add_parser("generate-all",
                        help="generate every runnable combination")
    add_common(ga)

    args = p.parse_args(argv)
    return {"list": cmd_list, "validate": cmd_validate,
            "generate": cmd_generate,
            "generate-all": cmd_generate_all}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
