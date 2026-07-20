# Changelog

All notable changes to TLSOC Reporting are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this repository adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
