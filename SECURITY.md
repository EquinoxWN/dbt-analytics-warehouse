# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub:
**Security > Report a vulnerability** on this repository
(`https://github.com/EquinoxWN/dbt-analytics-warehouse/security/advisories/new`). Do not open a public issue.

Include what you found, how to reproduce it, and the impact you expect. You will get an answer
within 7 days. Fixes are released as soon as they are ready, and you are credited unless you ask
not to be.

## Supported versions

This project is pre-1.0. Only the latest commit on `main` receives fixes.

## Scope

- **In scope:** Downloads that could fetch from an unexpected host or keep an unverified file,
  path handling that could escape the data folder or break out of a SQL string, records silently
  lost or double counted between the raw files and `fact_trips`, and secrets in the repository.
- **Out of scope:** Vulnerabilities in dbt, DuckDB or the NYC TLC files themselves (report those
  upstream).

## How this repository protects itself

- Every GitHub Action is pinned to a full commit SHA, and workflows run with read-only
  permissions and without persisted credentials.
- Dependabot update pull requests are paused (`open-pull-requests-limit: 0`) so the repository keeps a single `main` branch; dependencies are updated by hand and checked by the CI audit.
- CI runs lint, tests and a known-vulnerability check (pip-audit) on every push and pull request.
- Every dependency version is pinned in `constraints.txt`; downloads are limited to an allowed
  HTTPS host, capped in size and kept only when the size and SHA-256 match `datasets.json`.
- The warehouse is a local DuckDB file: no server, no credentials, nothing listening on a port.
