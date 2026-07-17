# Automation

Running the framework unattended: daily generation, logging, failure
investigation, and email delivery.

## Daily reports with cron

`scripts/daily_reports.sh` is the production entry point. It loads `.env`, runs
`generate-all`, and writes a **per-day log** to `logs/reports_YYYY-MM-DD.log`
containing start/end timestamps, every generated file path, and every warning or
error — so a failed or degraded run can be investigated days later. Logs older
than 30 days are pruned automatically (tune with `KEEP_DAYS`).

```bash
chmod +x scripts/daily_reports.sh     # once, after cloning
crontab -e
```

```cron
# Generate all daily reports at 06:10 every morning
10 6 * * * /opt/tlsoc-reporting/scripts/daily_reports.sh
```

(Adjust the path to wherever the repository is cloned.)

The script exits non-zero on failure, so cron's `MAILTO` (or any wrapper) can
alert on it.

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

## Email delivery

The bundled [Report Emailer](../TLSOC_Report_Emailer/README.md) is a standalone
tool that emails the day's PDF report to a recipient list once per day (cron),
with its own state tracking, logging, and retry behavior. Configure it via its
`.env` (SMTP credentials never committed) and schedule it after the report run —
for example generation at 06:10, delivery at 12:30.
