# Automation

Running the framework unattended: scheduling, the reporting window, logging,
and failure investigation.

## Quick setup

```bash
cd /opt/tlsoc-reporting-framework
chmod +x scripts/daily_reports.sh      # once, after cloning

./scripts/daily_reports.sh             # always test by hand first
echo $?                                # 0 = success
cat logs/reports_$(date +%F).log
```

Then schedule it:

```bash
crontab -e
```

```cron
# Generate all daily reports at 12:00 noon
0 12 * * * /opt/tlsoc-reporting-framework/scripts/daily_reports.sh
```

That is the whole setup. The script finds its own virtualenv, so no `PATH`
juggling is needed in the crontab; adjust the path if the repository is
cloned elsewhere.

## What it does

`scripts/daily_reports.sh` is the production entry point. It:

1. loads `.env` if present (for any environment overrides),
2. uses `.venv/bin/python` when it exists — cron's minimal `PATH` is the
   usual reason a job that works by hand fails on schedule,
3. runs `generate-all` for **the last complete calendar day**,
4. writes everything to `logs/reports_YYYY-MM-DD.log` — start/end timestamps,
   the window used, every file produced, and every warning or error,
5. prunes logs older than 30 days (`KEEP_DAYS`),
6. exits non-zero if the run failed, so a wrapper or monitor can alert.

Datasources with no matching index on this cluster are skipped and logged as
such, so the same schedule works unchanged on every server.

## The reporting window

**Default: the last complete calendar day** — yesterday 00:00 → today 00:00
in the report timezone — regardless of what time the job runs.

This is deliberate. A rolling "last 24 hours from now" window straddles two
dates, so the same report covers something different at 06:00 than at 12:00,
and no run ever covers a full day cleanly. With the calendar-day window, a
run at any hour on the 21st produces one report covering all of the 20th.

**Output is dated for the day it describes, not the day it ran**, so the
noon run on 21 July writes `daily_web_nginx_2026-07-20.pdf`.

### Changing the schedule

Edit the cron line — the window follows the day, not the hour, so any time
works and the report still covers a whole day:

```cron
0 12 * * *   ...    # noon (default suggestion)
30 6 * * *   ...    # 06:30
0 2 * * *    ...    # 02:00, quieter for the cluster
0 12 * * 1   ...    # Mondays only
```

Pick a time comfortably after midnight so the previous day is fully ingested.

### Changing the window itself

| Want | How |
|---|---|
| Last complete calendar day | default — nothing to do |
| Rolling 24h ending at run time | `REPORT_WINDOW_END=now` before the command |
| A specific end instant | `./scripts/daily_reports.sh --window-end 2026-07-10T00:00` |
| A different span (e.g. weekly) | `./scripts/daily_reports.sh --window-hours 168` |

In cron, environment overrides go inline:

```cron
0 12 * * * REPORT_WINDOW_END=now /opt/tlsoc-reporting-framework/scripts/daily_reports.sh
```

Any flag you pass is forwarded to `generate-all`, and an explicit
`--window-end` always wins over the default.

## Reading the log

Every run appends to `logs/reports_YYYY-MM-DD.log` (named for the run date):

```
==== report run started  2026-07-21 12:00:01 IST ====
interpreter: /opt/tlsoc-reporting-framework/.venv/bin/python
window args: --window-end 2026-07-21T00:00
--- mail_daily × postfix ---
PDF:  .../output/pdf/daily_mail_postfix_2026-07-20.pdf  (engine: wkhtmltopdf)
--- web_daily × moodle: skipped, no matching index on this cluster
generated this run:
  ...
==== report run finished OK  2026-07-21 12:00:21 IST ====
```

| Line | Meaning |
|---|---|
| `finished OK` + file list | Healthy; those files are in `output/` |
| `ERROR: all N queries failed` | Backend unreachable, credentials or CA wrong. **No report is written** — a report of zeros would read as "no traffic, no attacks" |
| `warning: Query 'x' failed` | One section degraded; the rest of the report is sound |
| `skipped, no matching index` | Normal — that log source is not on this cluster |
| no log file for a date | The job never ran: check `crontab -l` and the system cron log |

Across days: `grep -c ERROR logs/reports_*.log`

## Investigating a bad or missing report

| Symptom | Where to look |
|---|---|
| No report for a day | `logs/reports_<date>.log` — run start/FAILED lines |
| Report exists but a section is missing | `warning:` lines in the log (unmapped field, failed query) |
| Numbers look wrong / empty | header of the report itself — ingest-gap and degraded-query warnings are printed on the page |
| PDF missing, HTML present | `PDF generation failed` warning in the log; install/fix a PDF engine |
| `CERTIFICATE_VERIFY_FAILED ... key identifier mismatch` | You're pointing at a different cluster than the CA belongs to — check `elasticsearch.host` and `ca_cert` describe the SAME deployment |
| `Fielddata is disabled on [<field>]` | That index maps the field as `text`; aggregate its keyword subfield instead — set e.g. `url_path: "url.path.keyword"` in the datasource's field map |
| Queries return 0 but the index has data | Index pattern in the datasource doesn't match — compare with `GET _cat/indices` |

## Historical re-runs

Re-generate any past window without touching the schedule:

```bash
python3 -m framework generate-all --window-end 2026-07-10T00:00
python3 -m framework generate --report web_daily --datasource nginx --window-hours 168
```

## Downstream delivery

Delivery is out of scope for this framework: its job ends when the files are
in `output/`. Any separate tool that picks them up should rely on the
documented naming contract — `<slug>_<datasource>_<YYYY-MM-DD>` — and note
that **the date in the filename is the day the data covers**, which is the
day before the run under the default calendar-day window. A delivery job
looking for "today's date" will not match; match the data date, or select by
modification time.

Schedule delivery after generation with enough margin for a slow run — the
report step typically takes seconds to a minute per report.
