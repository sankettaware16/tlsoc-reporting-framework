# Contributing to TLSOC Reporting

Thank you for helping improve TLSOC Reporting. Ecosystem-wide guidelines live in
[tlsoc — CONTRIBUTING](https://github.com/sankettaware16/tlsoc/blob/main/CONTRIBUTING.md);
this file covers what is specific to this repository.

## Ground rules

- Be respectful — participation is governed by the
  [Code of Conduct](CODE_OF_CONDUCT.md).
- **Never commit real traffic data.** `log_samples/` and `output/` are
  git-ignored because they contain real IPs, hostnames, and email addresses —
  keep it that way. Anything you paste into issues, sample files, or tests must
  be sanitized (`203.0.113.10`, `user@example.com`, `example_org`).
- Secrets (the ES password, SMTP credentials) live only in git-ignored `.env`
  files — never in YAML, code, or issues.
- Security vulnerabilities go through [SECURITY.md](SECURITY.md), never public
  issues.
- Contributions are accepted under the [Apache-2.0 license](LICENSE).

## The golden rule of this codebase

**Report logic is YAML, not Python.** New datasources, report types, sections,
insights, and signatures belong in `config/` — if you find yourself editing
`framework/` to add a report feature, first check whether a new query kind,
transform, or widget is genuinely required, and open an issue to discuss it.

## Contributing a datasource, report, or signature pack

1. Follow [docs/configuration.md](docs/configuration.md) — datasources and
   reports are single YAML files; shared attack patterns go in
   `config/signatures/`.
2. Estate-specific false positives go in the datasource's
   `extra_benign_path_prefixes`, never in the shared signature pack.
3. Validate: `python3 -m framework validate` must pass.
4. Prove the render offline with a **sanitized** NDJSON sample:

   ```bash
   python3 -m framework generate --report <report> --datasource <name> \
           --backend local --sample log_samples/<name>_sample.json
   ```

5. Open a PR describing what the report/section shows and attach a screenshot
   of the rendered HTML if the layout changed (with sanitized data only).

## Contributing framework code

1. Open an issue first — framework changes affect every report.
2. Keep the two backends equivalent: any query-IR change must behave
   identically in `backends/es.py` and `backends/local.py` (the offline-preview
   guarantee depends on it).
3. Keep rendering print-safe: no JavaScript in report output; charts stay
   inline SVG.
4. Validate with `python3 -m framework validate` and an offline `generate`
   run before pushing.
5. Update `CHANGELOG.md` under `[Unreleased]` for user-visible changes.

## Development setup

```bash
git clone https://github.com/sankettaware16/tlsoc-reporting.git
cd tlsoc-reporting
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m framework list      # no Elasticsearch needed
.venv/bin/python -m framework validate
```

Everything except a live cluster run works with zero infrastructure via the
offline backend.
