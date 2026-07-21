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
    cd "$BASE_DIR"
    "$PYTHON" -m framework generate-all "$@"
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
