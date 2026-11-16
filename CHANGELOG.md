# Changelog

All notable changes to TLSOC Reporting are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this repository adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Three new reports, so every ingested log source is covered** (seven in
  total):
  - `radius_daily` × `radius` (FreeRADIUS): authentication volume and
    failure causes, retry-loop devices vs accounts failing from many
    devices, EAP/certificate onboarding problems, roaming identities, and
    federation upstream and accounting health. Follow-up log lines for an
    already-rejected request are excluded so a failure counts once.
  - `sso_daily` × `sso` (LDAP proxy + web SSO): bind volume and failure
    rate reconciled against request records, per-node load, accounts with
    repeated failures, credential-guessing sources, repeating OAuth/token
    clients and accounts signing in from several countries.
  - `fmlr_daily` × `fmlr` (policyd-spf mail gateway): SPF verdict split,
    exactly which verdicts are rejected vs accepted, spoofing of the
    institute's own addresses, DNS temp-error coverage gaps and PermError
    rejects. Counts verdicts from one log line type so a transaction is
    not tripled.
- `join` and `overlap` transforms: copy columns from another query's rows
  with the same key (today next to the previous window), and flag rows
  whose two value lists share an entry.
- `suffix_param` accepts `versioned: true`, matching an asset suffix that is
  followed by a cache-busting tail (`app.js@ver=1.2.3`).
- squid datasource: client campus location (`source.geo.name`,
  `source.site.zone`) and a "Usage by campus location" table.
- postfix datasource: source ASN (`asn_org`) and the institute's own-domain
  patterns (`own_domain_patterns`).

- **Multi-domain (vhost) breakdown for web reports.** Estates whose
  datasource maps a `domain` logical field (nginx: `url.domain` from the
  vhost-first log format, ~115 domains) gain a per-domain traffic table
  (requests, visitors, Err %, 5xx, bandwidth, distinct-domain count),
  a "Scanning by domain" table on the security side, a "Traffic by edge
  server" table (`edge_server`: vh3/vh4), an executive-summary line
  naming the busiest vhost, and a "Domains served" KPI. Single-site
  estates render exactly as before.
- **NAXSI WAF section for web reports.** The edge's `denied` documents
  (`event.action: waf_block`) get their own block: blocks-per-hour
  timeseries, attack-category ($SQL/$XSS/$RFI/$TRAVERSAL) and match-zone
  charts, a top-rules table (id-range legend plus a whitelist-tuning
  note), most-blocked sources, most-targeted vhosts, a WAF/edge KPI
  strip, and a P2 action when one source exceeds `waf_ip_action_min`
  blocks. The summary states blocked volume as additional to access
  traffic — a denied request never reaches the access log.
- **Edge-health section for web reports.** nginx `error` documents
  render as an edge error breakdown (rate/connection limiting, upstream
  failures, SSL-handshake noise, unclassified), an upstream-failures-
  per-hour timeseries, upstream failures by domain (clients hit,
  failure kinds, exact backend), and most rate-limited clients — with
  P2/P3 actions on the `upstream_fail_warn` / `rl_ip_review_min`
  thresholds. Backend outages that never appear in any application log
  are now visible per domain.
- nginx datasource: mapped `domain`, `edge_server`, `event_action`,
  `waf_rule_id`, `waf_rule_category`, `waf_zone`, `waf_mode`,
  `rate_limit_zone`, `upstream`, `asn_org`; unmapped `service` (since
  the vhost-first format, `service.name` only distinguishes the syslog
  program - `vhnginx_access` / `vhnginx_error` - not a site).

- **DNS log source + daily DNS report** (`dns_daily` × `dns`). New `dns`
  datasource for the campus PowerDNS dnsdist resolvers
  (`fosstlsoc-logs-dns*`, parsed by foss-soc-engine `rules/dns.yaml`,
  ~60–85M docs/day) and a new `dns` report profile. The daily report
  covers query/answer volume and trend, per-hour activity with a
  failed-answer overlay, query types, answer outcomes (NXDOMAIN /
  REFUSED / SERVFAIL rates driving "Resolution health" and "Lookup
  hygiene" badges), top clients with campus-location enrichment
  (`source.geo.name` / `source.site.*`), most-queried names, campus
  zone and building breakdowns, top NXDOMAIN and SERVFAIL names,
  refused clients, a per-resolver-node table and dnsdist daemon
  notices (downstream `down` transitions raise a P3). Two
  security-signal tables raise P2 actions: NXDOMAIN-storm clients
  (the DGA-malware signature, separated from stale-config noise by a
  distinct-names column) and heavy TXT/NULL/ANY clients (the
  DNS-tunneling profile). EXTERNAL addresses among the top talkers
  flag open-resolver exposure with a P2.

- **Gateway-health section** for proxy reports. Upstream connection
  failures (squid `NONE/503`, `event.action_detail: connection_failed`) are
  now tracked separately from policy denials: a "Failed connections" KPI, a
  per-hour failure timeseries, a failure-type breakdown, a top-failing-
  destinations table, per-server Failed / Failed % columns, and a
  "Gateway health" badge (HEALTHY / WATCH / DEGRADED on configurable
  `fail_rate_warn` / `fail_rate_crit` thresholds). Sustained failure rates
  point at uplink/DNS trouble on the gateway — previously they were
  invisible next to denials.
- **Request-outcomes donut and HTTP-method chart** for proxy reports:
  succeeded vs policy-denied vs upstream-failed vs other errors at a
  glance, alongside a method (CONNECT/GET/POST/…) breakdown.
- **Destination ASN & country charts** for proxy reports. When the
  datasource maps the destination-side GeoIP/ASN enrichment
  (`dest_org`, `dest_country`), the report charts the networks and
  countries the estate talks to, and the executive summary names the
  most-contacted destination network. Estates without enrichment omit
  the charts.
- **Most-denied destinations table**: the destination side of policy
  denials, with ports and top clients per row — a single dest:port
  collecting hundreds of denials from one client is the signature of an
  automated retry loop (mis-configured agent, or beaconing malware the
  ACL is holding), and now surfaces as one row plus a P3 action instead
  of hiding inside per-client totals.
- **Cloud-metadata probe detection**: plain-HTTP requests for
  `169.254.169.254` seen at the egress proxy get their own table, an
  executive-summary line and a P2 action — the link-local metadata
  address should never be reachable through a forward proxy (SSRF-style
  recon or a misconfigured cloud agent).
- **Outbound SMB flagging**: port 445 through the proxy now raises a
  dedicated P2 action naming the clients (classic worm/scanner
  behaviour). The unusual-ports watchlist also gains 6568 (AnyDesk),
  5938 (TeamViewer), 853 (DNS-over-TLS resolver bypass) and 1433/3306
  (direct database access).
- Squid datasource: mapped `action_detail`, `dest_org`, `dest_country`,
  `url` and `dest_domain` logical fields to drive the sections above.
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

- **Mail report counted log lines as messages.** The mail index holds one
  correlated record per delivery plus several single-line SMTP events
  (connect, disconnect, TLS, reject) per connection; every figure counted
  all of them, inflating volume roughly tenfold and shrinking every
  percentage. Message figures now count deliveries only; refusals at the
  SMTP stage have their own section (reply codes, senders, sources) and
  failed SMTP logins their own table. The outcome chart no longer counts
  a delivery twice.
- **Web exposure check is now per site.** A probe response is compared with
  the site's own home page and with its responses to other probe paths, so
  catch-all (soft-404) sites are recognised whatever the path, and every
  path is evaluated instead of the busiest twenty. Only a response unlike
  the site's default page raises P1. The security badge no longer turns
  red for scanning alone.
- **Web outage caused by a traffic surge is reported as one.** Per-domain
  requests and visitors are compared with the previous window; when the
  site producing most 5xx also multiplied its traffic, the action names
  the surge and recommends site-wide rate capping instead of "check the
  backend".
- Terms queries larger than 20 buckets with sub-aggregations use
  breadth-first collection: Elasticsearch 8.19 returned wrong cardinality
  values for some buckets otherwise.
- dns: every heavy TXT/NULL/ANY client is listed (only the tunneling shape
  raises an action); DGA and SSH-scan checks look past the ten busiest
  clients; counts are no longer attributed to example names.
- proxy: the retry-loop action states how many clients were involved.
- web: daily actions for rejected logins and critical-signature sources
  fire on a per-address threshold and no longer duplicate each other.
- **Reports no longer raise actions on normal behaviour.** Findings checked
  against the raw logs and corrected:
  - proxy: outbound SSH (port 22) produced a P2 every day. It is now treated
    as routine and raises an action only on scan-like use (one client
    reaching many distinct hosts) or for other non-web ports the proxy
    actually let through. Only CONNECT tunnels count, which removes phantom
    VNC/TeamViewer ports caused by IPv6 addresses split into host and port.
    The failed-connections text no longer blames the gateway when failures
    are a few unreachable peers.
  - dns: the DGA action fired for hosts retrying a single missing name, and
    the tunneling action for resolver diagnostics (`hostname.bind`), a
    security-vendor domain and a mail filter. DGA now needs many distinct,
    non-service-discovery names; tunneling needs volume spread over many
    names and excludes diagnostics and listed vendor domains. Repetitive
    hosts are reported as stale configuration (P4). Example names are shown.
  - web: critical probe paths answering 200 on many unrelated vhosts are
    catch-all/soft-404 pages, not exposures: they no longer raise P1 and
    produce a "return 404" action instead. Versioned static assets
    (`.js@ver=…`) no longer count as probes. A single vhost causing nearly
    all 5xx is reported as a single-site outage with the estate rate
    without it, in one action instead of two.
  - mail: the institute's own subdomains and upper-cased recipient domains
    no longer count as "external"; SMTP-stage rejects are labelled instead
    of looking like delivered traffic; the "many source IPs" action now
    counts unrelated networks, so Gmail "send mail as" and mobile carriers
    do not trigger it.
- dns report text no longer contains mojibake (`â€”`) in place of dashes.
- Wildcard and prefix filters with an empty pattern list match nothing
  explicitly (`match_none`) instead of relying on an empty `bool`.
- Web-report traffic metrics no longer count nginx error and WAF
  documents. Since the multi-vhost + NAXSI rollout the nginx index mixes
  three document shapes, and every unfiltered metric (total requests,
  visitors, top paths/IPs, referrers, methods, bandwidth, geography,
  auth surface, signature-probe detection, trend baselines) silently
  included ~11% error/denied lines - the status-mix donut showed them as
  "No status logged". Traffic queries are now scoped to access lines
  (`status_code` exists), a no-op for pure access-log estates (moodle).

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
