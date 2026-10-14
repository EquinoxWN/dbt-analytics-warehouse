.PHONY: setup lint test data build report bench audit clean clean-data ci

PY ?= python
# dbt reads profiles.yml from the repository, never from ~/.dbt, and sends no usage statistics.
DBT = DBT_PROFILES_DIR=. DBT_SEND_ANONYMOUS_USAGE_STATS=false dbt

setup:
	$(PY) -m pip install --upgrade pip && $(PY) -m pip install -c constraints.txt -e ".[dev]"

# ruff, ruff format, mypy --strict, and dbt parse with every dbt warning treated as an error.
lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check . && $(PY) -m mypy
	$(DBT) --warn-error parse --no-partial-parse

# Python tests and end-to-end dbt builds on synthetic data with planted defects; the real-data
# tests run as well when `make data` has downloaded the pinned files.
test:
	$(PY) -m pytest -q -rs

# Download the pinned NYC TLC files into data/raw (size and SHA-256 verified).
data:
	daw fetch

# dbt build (seeds, models, data tests, unit tests) into data/warehouse.duckdb.
build:
	daw build

# Reconciliation, star schema sizes and two sample BI answers from the built warehouse.
report:
	daw report

# The M1 numbers in docs/results/m1.md: fetch, build and report on the real data.
bench: data build report

# Known vulnerabilities in the installed Python dependencies.
audit:
	$(PY) -m pip_audit --skip-editable --cache-dir .tmp/pip-audit

# Remove dbt output and the built warehouse; keeps the downloaded files.
clean:
	rm -rf target logs data/warehouse.duckdb data/warehouse.duckdb.wal

# Remove the downloaded files as well (`make data` restores them from the pinned manifest).
clean-data: clean
	rm -rf data

ci: setup lint test
