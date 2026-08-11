# Changelog

All notable changes to TLSOC Reporting are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this repository adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Per-server traffic breakdown** for proxy reports. When a proxy
  datasource maps a `proxy_instance` field — for Squid, the worker/instance
  process name (`squid-2`, `squid-4`, `squid-7`, …) — the report adds a
  "Traffic by proxy server" table (requests, clients, destinations, denials,
  denied %, bandwidth per node) and an executive-summary line naming the
  busiest node and its share of the total. Multi-node gateways can now see
  which server carried the load and whether any single node accounts for an
  unusual share of denials. Estates whose datasource does not map an instance
  field are unaffected — the section stays hidden.
- **Site-area segmentation** for web reports. A datasource can declare
  `site_areas` (name + URL-path prefix) to split one estate served behind a
  single host into its sections; the report then breaks scanning and exposure
  down per area — a "Scanning & exposure by site area" table (probes, sources,
  probes served 2xx, most-probed path), a "Traffic by site area" table, and an
  executive-summary line naming the most-scanned and any exposed area. Built on
  a general `path_groups` query kind (group any field by configured prefixes),
  so it is reusable beyond site sections. Estates that declare no areas are
  unaffected — the sections stay hidden.
- Source geography now reports **external** traffic only, with internal
  volume counted and stated separately — private addressing has no public
  geolocation and previously dominated the chart as "Unresolved".
- Client errors are broken down **by status code**, so a 4xx total can be
  attributed to malformed requests, rejected access, missing resources,
  wrong methods or rate limiting.
- `infrastructure_cidrs` datasource parameter — load balancers, proxies and
  monitors are excluded from volume-anomaly flagging (they remain in the
  traffic, bandwidth and error tables).
- `ip_in_param` filter clause matching an address against CIDRs from a
  parameter, evaluated identically by the live and offline backends.
- `show_note_if` on widgets, for notes that only apply when the value they
  describe is present.
- `framework check-fields` — verifies a datasource's field map against the
  live Elasticsearch mapping and names the exact `.keyword` suffix to use.
  Turns field-mapping mistakes into an explicit pre-flight check instead of
  an empty table in a generated report.

### Changed

- Scheduled runs now **label the report with the issue date (the day it
  runs)** while still covering the previous full day: the noon run on the
  21st writes `daily_web_nginx_2026-07-21.pdf`, and the report shows that
  date with its Window line stating the covered period in full. This keeps
  the daily output aligned with a same-day delivery step that looks for
  today's date. Set `REPORT_DATE=covered` to label by the day the data
  describes; the framework's own default (outside the wrapper) is unchanged
  and still labels by the covered day. New `--report-date YYYY-MM-DD` flag.
- Scheduled runs now cover the **last complete calendar day** by default
  instead of a rolling 24 hours ending at run time, so a daily report always
  describes a whole day regardless of when the job fires. Override with
  `REPORT_WINDOW_END=now` or an explicit `--window-end`.
- Output files are named `<slug>_<datasource>_<date>` with cadence first —
  `daily_web_nginx_2026-07-21.pdf`, `daily_mail_postfix_…`,
  `daily_proxy_squid_…`. The slug is declared per report and is
  independent of the report's internal name, so the on-disk convention
  that automated delivery matches on stays stable across renames.

### Fixed

- Reports are now named after the day their data actually covers. A window
  ending exactly at midnight (`--window-end 2026-07-17T23:59`) was filed
  under the following date; ordinary scheduled runs are unaffected.
- Evidence-sample tables rendered `-` for any field mapped with a
  `.keyword` suffix: `_source` filtering used the aggregatable field name,
  which does not exist in the stored document.

### Changed

- Joined the unified TLSOC ecosystem: standardized README, branding, and
  cross-repository links. The component is presented as **TLSOC Reporting**;
  the repository name (`tlsoc-reporting-framework`) is unchanged.
- Documentation reorganized into `docs/`: configuration guide, automation
  guide, and framework architecture.

### Added

- Apache-2.0 `LICENSE`.
- Community health files: contributing guide, security policy, code of conduct,
  issue templates, and a pull request template.
- Component roadmap (`docs/roadmap.md`).
