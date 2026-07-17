# Configuration Guide

Everything you edit day-to-day lives under `config/`:

```
config/
├── settings.yaml           # THIS deployment: ES endpoint, org, timezone, dirs
├── datasources/*.yaml      # one per log source: index + logical-field map
├── reports/*.yaml          # one per report type: queries, narrative, layout
└── signatures/*.yaml       # shared attack-pattern packs
```

## Connection settings

Configuration precedence, highest wins: **env vars → `settings.yaml` →
auto-detected deployment → built-in defaults.**

### On a TLSOC stack host (auto-detection)

If the host runs
[tlsoc-docker-deploy](https://github.com/sankettaware16/tlsoc-docker-deploy),
the Elasticsearch host, password, and CA certificate are read from the
deployment itself. Auto-detection looks in `/opt/TLSOCDockerDeploy` by default;
if your stack lives elsewhere (for example a new clone at
`/opt/tlsoc-docker-deploy`), set:

```yaml
tlsoc_deploy:
  dir: "/opt/tlsoc-docker-deploy"
```

### Manual configuration (any other machine)

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

   (`scripts/daily_reports.sh` loads `.env` automatically; only manual shell
   sessions need the `source` line.)

## Add a new log source (no code)

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
(`GET /<index>/_mapping`): if a string field has a `fields.keyword` entry, map
`<field>.keyword`; if it is already type `keyword`, map it bare.

## Add a query / section to an existing report

Queries are independent blocks under `queries:`; sections under `sections:`
reference them by name. Add both, `validate`, preview offline, done. Building
blocks:

- **query kinds**: `count`, `cardinality`, `sum/avg/min/max`, `terms`,
  `date_histogram`, `range_buckets`, `signature_categories`, `samples`
- **filters**: `all` / `any` / `none` over leaf clauses (`equals, in, in_param,
  wildcard, wildcard_param, contains_param, suffix_param, prefix, prefix_param,
  range, exists, signatures`)
- **`window: previous`** re-runs a query over the preceding window (trend
  baselines)
- **transforms**: `classify_ip, cluster_paths, derive_pct, flag_match,
  min_count, sort, limit`
- **computed / insights / actions / badges**: Jinja expressions and sentence
  templates with `when` guards — the entire narrative is editable here
- **widgets**: `heading, kpi_row, insights, actions, timeseries, donut, bars,
  table, samples, text, row`; every section supports `show_if:` and
  `skip_if_unmapped: [fields]`

## Add a report type

Copy the closest file in `config/reports/`, rename, edit. It appears in
`python3 -m framework list` on its own.

## Extend detections

Add categories/patterns to `config/signatures/web_threats.yaml` — every web
report picks them up automatically (tables, totals, badges, insights).
Estate-specific false positives go in that datasource's
`extra_benign_path_prefixes`, never in the shared pack.

## Validate everything

```bash
python3 -m framework validate   # compile-check all pairs, no ES needed
```

Then prove the full render pipeline offline against a local NDJSON sample
(git-ignored `log_samples/`):

```bash
python3 -m framework generate --report web_daily --datasource <name> \
        --backend local --sample log_samples/<name>_sample.json
```
