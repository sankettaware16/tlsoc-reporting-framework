#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Daily report generation wrapper - the cron entry point.
#
# What it does:
#   * loads secrets from <repo>/.env (TLSOC_ES_PASS etc.)
#   * runs `python3 -m framework generate-all`
#   * writes a per-day log to logs/reports_YYYY-MM-DD.log with start/end
#     timestamps and the full output (per-report paths, warnings, errors),
#     so any failed or degraded run can be investigated later
#   * prunes logs older than KEEP_DAYS
#   * exits non-zero when generation failed (so cron can mail on failure)
#
# Any arguments are passed through to `generate-all`, e.g.
#   daily_reports.sh --window-hours 168
#
# Cron example (daily at 12:00):
#   0 12 * * *  /opt/tlsoc-reporting-framework/scripts/daily_reports.sh
# ---------------------------------------------------------------------------
set -u

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$BASE_DIR/logs"
LOG_FILE="$LOG_DIR/reports_$(date +%F).log"
KEEP_DAYS="${KEEP_DAYS:-30}"

mkdir -p "$LOG_DIR"

# Load secrets (TLSOC_ES_PASS, optional host overrides) if a .env exists.
if [ -f "$BASE_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$BASE_DIR/.env"
    set +a
fi

# --- reporting window ------------------------------------------------------
# Default: the last COMPLETE calendar day (yesterday 00:00 -> today 00:00),
# whatever time of day the job happens to run. A daily report should cover a
# whole day: a rolling "last 24h from now" window straddles two dates, so the
# same report means something different at 12:00 than at 06:00 and no run
# ever covers a full day cleanly. The output is dated for the day it
# describes, not the day it ran.
#
# Override for a rolling window ending at run time:
#     REPORT_WINDOW_END=now ./daily_reports.sh
# Or pass any generate-all flag explicitly, which takes precedence:
#     ./daily_reports.sh --window-end 2026-07-10T00:00 --window-hours 168
WINDOW_ARGS=()
case " $* " in
    *" --window-end "*) ;;                       # caller decides
    *)
        case "${REPORT_WINDOW_END:-midnight}" in
            now|rolling) ;;                      # generate-all's own default
            midnight)
                WINDOW_ARGS=(--window-end "$(date +%F)T00:00") ;;
            *)
                WINDOW_ARGS=(--window-end "$REPORT_WINDOW_END") ;;
        esac
        ;;
esac

# Prefer the project's own virtualenv. cron runs with a minimal PATH, so
# relying on whatever `python3` resolves to is the usual reason a job that
# works by hand fails at 12:00 with ModuleNotFoundError.
if [ -x "$BASE_DIR/.venv/bin/python" ]; then
    PYTHON="$BASE_DIR/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

# Marker for "what did THIS run produce". It cannot be the log file: that
# is appended to throughout the run, so it always ends up newer than the
# reports and would list nothing.
STAMP="$(mktemp)"
trap 'rm -f "$STAMP"' EXIT

{
    echo "==== report run started  $(date '+%F %T %Z') ===="
    echo "interpreter: $PYTHON"
    echo "window args: ${WINDOW_ARGS[*]:-<generate-all default: rolling>} $*"
    cd "$BASE_DIR"
    "$PYTHON" -m framework generate-all "${WINDOW_ARGS[@]}" "$@"
    rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "generated this run:"
        find "$BASE_DIR/output" -newer "$STAMP" -type f \
             \( -name '*.pdf' -o -name '*.html' \) -printf '  %p\n' 2>/dev/null \
             | sort || true
        echo "==== report run finished OK  $(date '+%F %T %Z') ===="
    else
        echo "==== report run FAILED (exit $rc)  $(date '+%F %T %Z') ===="
        echo "     investigate the 'ERROR'/'warning' lines above."
    fi
} >> "$LOG_FILE" 2>&1

# Prune old logs so the directory never grows unbounded.
find "$LOG_DIR" -name "reports_*.log" -mtime +"$KEEP_DAYS" -delete

exit "${rc:-1}"
