# ADR 0003: DuckDB reads pinned public files in place

- **Status:** Accepted

## Context

The warehouse must run on a laptop with about 4 GB of free memory, alongside other builds, with
no server and no Docker. dbt needs a database adapter, and the raw TLC files have to reach the
first model somehow. Two questions follow: which database, and whether raw files are copied into
a `raw` schema before dbt runs.

## Decision

- **DuckDB through dbt-duckdb**, as a single file at `data/warehouse.duckdb`, with the profile
  in the repository (`profiles.yml`, read through `DBT_PROFILES_DIR`), a 1 GB memory limit, two
  threads, and automatic extension download disabled.
- **Sources read the files in place**: the source definitions set `external_location` to
  `read_parquet('<raw dir>/green_tripdata_*.parquet', filename = true, union_by_name = true)`
  and `read_csv(..., all_varchar = true)`. There is no raw copy.
- **Immutability comes from the pin, not from a copy**: `datasets.json` holds each file's URL,
  size and SHA-256, `daw fetch` keeps a file only when both match, and a real-data test checks
  the files again before reconciling counts.

## Consequences

- No load step and no second copy of the data; `source_file` in every fact row names the exact
  file, and the build runs in about 12 s on the laptop including dbt start-up.
- The raw directory is an environment variable (`DAW_RAW_DIR`), so tests point the same project
  at synthetic files in a temporary folder. Because the path is placed inside a SQL string, the
  Python runner refuses paths with quotes or other characters outside a small allowed set.
- dbt cannot introspect the columns of an external source, so unit tests of staging models use
  SQL fixtures that list every raw column with its type. This is more verbose but also documents
  the raw schema; a separate test checks that the synthetic files have exactly the real schema.
- If TLC republishes a file, the checksum fails the download instead of silently changing past
  results. Updating a pin is a reviewed change that also re-measures `docs/results`.
- Moving to Postgres or a cloud warehouse later means loading the files into a raw schema
  there; the staging, intermediate and mart SQL is plain enough to port, but a few DuckDB
  functions (`read_parquet`, `regexp_extract`, `strftime`, `group by all`) would need adapter
  macros.
