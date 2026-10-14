# Contributing

Thanks for helping. This is a dbt project (SQL) with a small Python package around it; issues and
pull requests are welcome.

## Set up and check your change

Needs Python 3.11+. Caches, the virtual environment, downloaded data and dbt output stay in
git-ignored folders inside the repository (`.venv/`, `.tmp/`, `data/`, `target/`, `logs/`).

```bash
make setup   # install exact versions from constraints.txt
make lint    # ruff, ruff format, mypy --strict, dbt parse --warn-error
make data    # download the pinned NYC TLC files (size and SHA-256 checked)
make test    # Python tests, dbt builds on synthetic data, real-data reconciliation
make bench   # fetch, build and report on the real data
make audit   # known-vulnerability check (as in CI)
```

A pull request is ready when `make lint` and `make test` pass and CI is green.

## Guidelines

- Staging models only rename, cast and clean; joins and business rules belong in intermediate
  models; marts expose the star schema. `tests/test_project_rules.py` enforces the layering.
- A new rejection rule needs a dbt unit test case, a planted defect in
  `src/dbt_analytics_warehouse/synthetic.py`, and a line in ADR 0002.
- Changing a mart column changes its contract in `models/marts/_marts__models.yml`; say which
  dashboards or queries are affected in the pull request.
- Keep function comments to one short phrase; let names and tests explain the rest.
- Update `docs/results/` when numbers change, and add an ADR in `docs/adr/` for design changes.
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).

By contributing you agree that your work is released under the [MIT License](LICENSE).
