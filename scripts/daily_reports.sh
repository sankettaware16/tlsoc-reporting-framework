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
# Cron example (daily at 06:10):
#   10 6 * * *  /opt/TLSOCDockerDeploy/reporting/scripts/daily_reports.sh
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

{
    echo "==== report run started  $(date '+%F %T %Z') ===="
    cd "$BASE_DIR"
    python3 -m framework generate-all
    rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "==== report run finished OK  $(date '+%F %T %Z') ===="
    else
        echo "==== report run FAILED (exit $rc)  $(date '+%F %T %Z') ===="
    fi
} >> "$LOG_FILE" 2>&1

# Prune old logs so the directory never grows unbounded.
find "$LOG_DIR" -name "reports_*.log" -mtime +"$KEEP_DAYS" -delete

exit "${rc:-1}"
