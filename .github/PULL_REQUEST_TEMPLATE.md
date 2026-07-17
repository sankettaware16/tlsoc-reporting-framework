## Summary

<!-- What does this PR change, and why? Link the related issue: Fixes #NN -->

## Type of change

- [ ] Datasource / report / signature YAML (config/)
- [ ] Framework code (framework/)
- [ ] Templates / widgets / rendering
- [ ] Report Emailer
- [ ] Documentation

## Checklist

- [ ] `python3 -m framework validate` passes
- [ ] Verified with an offline render (`--backend local --sample ...`) using **sanitized** data
- [ ] For framework changes: both backends (`backends/es.py`, `backends/local.py`) behave identically
- [ ] No real traffic data or secrets anywhere (IPs, hostnames, email addresses, passwords)
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (for user-visible changes)
