# TLSOC Reporting Roadmap

Component roadmap for the reporting framework. The platform-wide roadmap lives
in [tlsoc — Roadmap](https://github.com/sankettaware16/tlsoc/blob/main/docs/roadmap.md).

## Current

Shipped and maintained:

- Declarative report engine: YAML reports × YAML datasources with logical field
  mapping and graceful degradation.
- Web-access report profile with signature-based threat analysis, probe
  attribution, auth-surface and bot analysis.
- Live Elasticsearch backend and identical offline NDJSON backend.
- Seven reports: web, mail, proxy, DNS, Wi-Fi (RADIUS), SSO/LDAP and the
  mail-gateway SPF service.
- HTML rendering with inline-SVG charts and the three-engine PDF chain.
- Daily cron automation with per-day logs, and standalone email delivery.

## Next Release

- Ecosystem alignment: standardized documentation, community health files, and
  release tagging (this refactoring).
- Per-institution (realm) and per-sender-domain tables once the log engine
  emits `user.domain` / `email.sender_domain` for RADIUS and the SPF gateway.

## Future

- New report profiles: vulnerability-scan summaries and threat-intelligence
  matches.
- Weekly and monthly rollup reports alongside the daily window.
- Growing shared signature packs, with community contributions.
- Optional delivery targets beyond email (webhook, shared drive).

## Long Term Vision

- Report browsing integrated into the planned `tlsoc-dashboard`.
- Anomaly-driven report sections powered by the planned `tlsoc-ml` component.

## Proposing changes

Open a [feature request](https://github.com/sankettaware16/tlsoc-reporting-framework/issues) using the template. Roadmap changes land
here via pull request.
