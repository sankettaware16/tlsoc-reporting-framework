# Changelog

All notable changes to TLSOC Reporting are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this repository adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Reports are now named after the day their data actually covers. A window
  ending exactly at midnight (`--window-end 2026-07-17T23:59`) was filed
  under the following date; ordinary scheduled runs are unaffected.

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
