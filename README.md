# TLSOC Reporting Framework

Declarative, template-driven executive reporting over ELK log data.
Turns parsed security/infrastructure logs (nginx, Apache/Moodle, Postfix,
Squid, ...) into daily **HTML + PDF** reports with KPIs, charts, attack-
signature analysis, plain-English insights and prioritised action items.

**No report logic lives in Python.** A report is YAML (queries + narrative
rules + layout), a log source is YAML (index + field map), and the engine
multiplies them:

```
one report definition  ×  every datasource with a matching profile
        web_daily      ×  { nginx, moodle, <your next web source> }
```

## Features

- **Declarative everything** — queries, thresholds, insights, actions,
  badges and layout are YAML; adding a log source or report type is a
  config change, not a code change.
- **Logical field mapping** — reports say `client_ip` / `url_path`; each
  datasource maps those to its real index fields. One report renders for
  many differently-mapped indexes.
- **Graceful degradation** — a source missing a field loses only the
  dependent section, never the report.
- **Signature-based security analysis** — categorised, severity-rated
  threat patterns with per-estate benign allowlists; probe attribution,
  served-probe alerting, auth-surface and bot analysis.
- **Offline preview** — render any report from an NDJSON sample file with
  zero infrastructure; identical output to a live cluster run.
- **Robust PDF chain** — wkhtmltopdf → headless Chrome → WeasyPrint,
  first available wins; HTML always survives a PDF failure.
- **Honest numbers** — hour-aligned timezone-aware windows (gap-free
  hourly charts), trend arrows auto-suppressed on ingest gaps, client
  aborts (499) excluded from error rates, 404s triaged into
  probe / by-design / genuinely-broken.

## Requirements

- Python 3.10+
- An Elasticsearch 8.x cluster with parsed logs (ECS-style fields)
- One PDF engine on the host: `wkhtmltopdf`, Google Chrome/Chromium,
  or `weasyprint` (optional — HTML output works without any)

## Installation

### Option A — on a TLSOC host (zero configuration)

This framework is the reporting companion of the TLSOC docker stack. On a
host that runs the stack (default `/opt/TLSOCDockerDeploy`), the ES host,
password and CA certificate are **auto-detected from the deployment
itself** — there is nothing to configure:

```bash
cd /opt
sudo git clone https://github.com/<you>/tlsoc-reporting-framework.git
sudo chown -R $USER: tlsoc-reporting-framework
cd tlsoc-reporting-framework

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
sudo apt install -y wkhtmltopdf        # PDF engine (skip if already there)

.venv/bin/python -m framework validate
.venv/bin/python -m framework generate --report web_daily --datasource moodle
```

On startup you'll see a line like
`[settings] auto-detected TLSOC deployment in /opt/TLSOCDockerDeploy: host=..., password, ca_cert`
confirming where the connection came from. If the stack lives somewhere
else, set `tlsoc_deploy.dir` in `config/settings.yaml`.

### Option B — any other machine (manual configuration)

When there is no co-located stack, tell the framework where Elasticsearch
is. **Both** steps:

1. `config/settings.yaml` — the non-secret connection + identity values:

   | key | meaning | example |
   |---|---|---|
   | `elasticsearch.host` | cluster URL | `https://10.0.0.5:9200` |
   | `elasticsearch.user` | user with read access to the log indexes | `elastic` |
   | `elasticsearch.ca_cert` | CA file that signed the cluster cert (copy it to this machine) | `/etc/tlsoc/ca.crt` |
   | `org.*` | name/department printed on every report | |
   | `locale.*` | timezone the reports render in | `Asia/Kolkata` |

2. The password — never in a file that gets committed:

   ```bash
   cp .env.example .env
   nano .env                # TLSOC_ES_PASS=...
   set -a; source .env; set +a     # for manual shell runs
   ```
   (`scripts/daily_reports.sh` loads `.env` automatically; only manual
   shell sessions need the `source` line.)

Precedence, highest wins: env vars → `settings.yaml` → auto-detected
deployment → built-in defaults.

### Sanity checks (both options)

```bash
python3 -m framework list       # datasources, reports, runnable pairs
python3 -m framework validate   # compile-check everything, no ES needed
```

With a local sample file (see *Offline preview* below) you can also
prove the full render pipeline with zero infrastructure.

## Usage

```bash
# one report
python3 -m framework generate --report web_daily --datasource nginx

# everything that can run (the cron entry point)
python3 -m framework generate-all

# useful flags
--window-hours 168                  # weekly instead of daily
--window-end 2026-07-10T00:00       # re-run a historical day
--param top_n=20                    # override any report param
--formats html                      # skip PDF
```

Reports land in `output/html/` and `output/pdf/` as
`<report>_<datasource>_<date>.{html,pdf}`.

### Offline preview (no Elasticsearch)

Develop templates and queries against a sample file — the same query
engine runs over the file, so output is identical to a live run. A
sample is any NDJSON file (one parsed JSON log document per line, as the
parsing engine emits). Samples are **not shipped in the repo** — they
are real log data; keep them in a local, git-ignored `log_samples/`
directory:

```bash
python3 -m framework generate --report web_daily --datasource moodle \
        --backend local --sample log_samples/moodle_sample.json
```

## Automation (daily reports + logging)

`scripts/daily_reports.sh` is the production entry point. It loads `.env`,
runs `generate-all`, and writes a **per-day log** to
`logs/reports_YYYY-MM-DD.log` containing start/end timestamps, every
generated file path, and every warning or error — so a failed or degraded
run can be investigated days later. Logs older than 30 days are pruned
automatically (tune with `KEEP_DAYS`).

```bash
chmod +x scripts/daily_reports.sh     # once, after cloning
crontab -e
```

```cron
# Generate all daily reports at 06:10 every morning
10 6 * * * /opt/TLSOCDockerDeploy/reporting/scripts/daily_reports.sh
```

The script exits non-zero on failure, so cron's `MAILTO` (or any wrapper)
can alert on it. What to look for when something goes wrong:

| Symptom | Where to look |
|---|---|
| No report for a day | `logs/reports_<date>.log` — run start/FAILED lines |
| Report exists but a section is missing | `warning:` lines in the log (unmapped field, failed query) |
| Numbers look wrong / empty | header of the report itself — ingest-gap and degraded-query warnings are printed on the page |
| PDF missing, HTML present | `PDF generation failed` warning in the log; install/fix a PDF engine |
| `CERTIFICATE_VERIFY_FAILED ... key identifier mismatch` | You're pointing at a different cluster than the CA belongs to — check `elasticsearch.host` and `ca_cert` describe the SAME deployment |
| `Fielddata is disabled on [<field>]` | That index maps the field as `text`; aggregate its keyword subfield instead — set e.g. `url_path: "url.path.keyword"` in the datasource's field map |
| Queries return 0 but the index has data | Index pattern in the datasource doesn't match — compare with `GET _cat/indices` |

## Configuration guide

```
config/
├── settings.yaml           # THIS deployment: ES endpoint, org, timezone, dirs
├── datasources/*.yaml      # one per log source: index + logical-field map
├── reports/*.yaml          # one per report type: queries, narrative, layout
└── signatures/*.yaml       # shared attack-pattern packs
```

### Add a new log source (no code)

Create `config/datasources/<name>.yaml`:

```yaml
name: apache_www
label: "Corporate WWW (Apache)"
profile: web_access                 # reuses the existing web report
index: "fosstlsoc-logs-apache*"
fields:
  timestamp: "@timestamp"
  client_ip: "source.ip"
  status_code: "http.response.status_code"
  response_bytes: "http.response.body.bytes"
  url_path: "url.path"
  method: "http.request.method.keyword"
  user_agent: "user_agent.original.keyword"
  referrer: "http.request.referrer.keyword"
  geo_country: "source.geo.country_name"
  geo_city: "source.geo.city_name"
params:
  auth_path_patterns: ["/login*"]
  extra_benign_path_prefixes: ["/static/"]
```

Run `python3 -m framework validate` — the new pair appears and is
compile-checked. Existing reports cannot break: you only *added* a file.

Check `.keyword` suffixes once against the live mapping
(`GET /<index>/_mapping`): if a string field has a `fields.keyword` entry
map `<field>.keyword`, if it is already type `keyword` map it bare.

### Add a query / section to an existing report

Queries are independent blocks under `queries:`; sections under
`sections:` reference them by name. Add both, `validate`, preview offline,
done. Building blocks:

- **query kinds**: `count`, `cardinality`, `sum/avg/min/max`, `terms`,
  `date_histogram`, `range_buckets`, `signature_categories`, `samples`
- **filters**: `all` / `any` / `none` over leaf clauses (`equals, in,
  in_param, wildcard, wildcard_param, contains_param, suffix_param,
  prefix, prefix_param, range, exists, signatures`)
- **`window: previous`** re-runs a query over the preceding window
  (trend baselines)
- **transforms**: `classify_ip, cluster_paths, derive_pct, flag_match,
  min_count, sort, limit`
- **computed / insights / actions / badges**: Jinja expressions and
  sentence templates with `when` guards — the entire narrative is editable
  here
- **widgets**: `heading, kpi_row, insights, actions, timeseries, donut,
  bars, table, samples, text, row`; every section supports `show_if:` and
  `skip_if_unmapped: [fields]`

### Add a report type

Copy the closest file in `config/reports/`, rename, edit. It appears in
`list` on its own.

### Extend detections

Add categories/patterns to `config/signatures/web_threats.yaml` — every
web report picks them up automatically (tables, totals, badges,
insights). Estate-specific false positives go in that datasource's
`extra_benign_path_prefixes`, never in the shared pack.

## Project layout

```
├── framework/              # the engine (Python) - not edited for new reports
│   ├── cli.py              #   list / validate / generate / generate-all
│   ├── generate.py         #   orchestrator
│   ├── registry.py         #   loads the config/ tree
│   ├── queryspec.py        #   YAML query spec -> shared filter IR
│   ├── backends/es.py      #   IR -> Elasticsearch DSL
│   ├── backends/local.py   #   same IR over NDJSON samples (offline mode)
│   ├── window.py           #   hour-aligned tz-aware reporting windows
│   ├── transforms.py       #   row post-processing
│   ├── rules.py            #   computed metrics / insights / actions / badges
│   ├── charts.py           #   inline-SVG charts (print-safe, no JS)
│   ├── render.py           #   sections -> widgets -> HTML
│   └── pdf.py              #   wkhtmltopdf -> chrome -> weasyprint fallback
├── config/                 # everything you edit day-to-day
├── templates/framework/    # page chrome + one partial per widget
├── log_samples/            # local-only NDJSON samples (git-ignored)
├── scripts/                # automation (cron wrapper with logging)
├── output/{html,pdf}/      # generated reports (git-ignored)
└── logs/                   # automation logs (git-ignored)
```

## Security notes

- The Elasticsearch password comes **only** from the environment
  (`TLSOC_ES_PASS`, usually via the git-ignored `.env`). Nothing secret is
  committed.
- Generated reports (`output/`) and sample logs (`log_samples/`) are
  git-ignored: both contain real traffic data — internal IPs, hostnames,
  email addresses — and must never be committed.
