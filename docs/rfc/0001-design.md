# RFC 0001: dbt-analytics-warehouse design

- **Status:** Accepted (M1 implemented)
- **Author:** EquinoxWN
- **Created:** 2026

## Problem

Most analytics SQL lives as one-off queries: each analyst cleans the raw data a little
differently, nobody can say how many records a dashboard silently dropped, and a renamed column
breaks a report without anyone noticing. The NYC Taxi and Limousine Commission (TLC) trip files
show the problem well. They are public and widely used, but they contain records that no
dashboard should count as trips: refunds recorded as negative fares, zero-length trips,
odometer faults of more than 200,000 miles and pickups years before the file's month.

This project builds the part that makes a warehouse trustworthy: pinned inputs, layered and
tested dbt models, a star schema with enforced contracts, and an audit trail that accounts for
every raw record.

**Users.** Analytics engineers and data analysts who build or review a warehouse; BI developers
who need a stable star schema; reviewers who want to see how a dbt project should be laid out.

## Critical-to-quality measures (Define)

| CTQ | Measure | Target |
|---|---|---|
| Completeness | raw records not accounted for (loaded + rejected with a reason - raw), per file | 0 |
| Key integrity | fact rows whose date or zone key has no dimension row; duplicate `trip_id` | 0 and 0 |
| Money reconciliation | audit total - staged total; fact total - valid-record total | $0.00 exactly |
| Defect detection | planted defect classes caught in end-to-end tests; planted SQL bugs caught by unit tests | 8 of 8; every mutation |
| Reproducibility | inputs pinned by size and SHA-256; dependency versions pinned | 100% of files and packages |
| Build time | `dbt build` (all models and tests) on three months of green taxi data on the laptop | under 60 s |
| Visibility of bad data | share of raw records rejected, reported by reason | reported; expected under 1% |

## Goals

- Raw trip data lands in staging models that only rename, cast and clean.
- Intermediate models join and enrich; marts expose a star schema (`fact_trips`, `dim_zone`,
  `dim_date`) for BI tools.
- Every raw record ends in `fact_trips` or in the audit with a single, named rejection reason.
- Everything runs on a laptop with no server: DuckDB as the warehouse, about 4 MB of input.

## Non-goals

- Running as a hosted production service, or serving dashboards (M3 adds one sample).
- Snapshots (SCD Type 2), incremental facts, full test coverage of every column and SQLFluff
  (M2); slim CI, a docs site and exposures (M3).
- Correcting the TLC data. Records that break a rule are rejected and counted, not repaired.

## Design

```
datasets.json (URL, size, SHA-256)
  -> daw fetch -> data/raw/*.parquet, taxi_zone_lookup.csv
  -> sources (read in place by DuckDB: read_parquet / read_csv)
  -> staging      stg_tlc__green_trips, stg_tlc__taxi_zones        (views)
  -> intermediate int_green_trips__validated -> int_green_trips__enriched   (tables)
  -> marts        fact_trips, dim_zone, dim_date, audit_trip_outcomes        (tables)
```

- **Inputs.** `datasets.json` pins three monthly green taxi files (January to March 2024,
  167,585 records) and the zone lookup by URL, byte size and SHA-256. `daw fetch` accepts only
  HTTPS on the TLC CDN host, caps each download at 64 MB, writes to a `.part` file and renames
  it only when size and checksum match. The files are read in place (ADR 0003).
- **Staging.** One view per source. It renames to snake_case, casts to exact types (money as
  `DECIMAL(12,2)`), maps the store-and-forward flag to a boolean, turns the dictionary's code 99
  and the lookup's `N/A` placeholders into NULL, and derives the source file and month from the
  file name. It never filters, joins or aggregates: one row out per row in.
- **Intermediate.** `int_green_trips__validated` gives every record one outcome: kept, or the
  first of eight rules it breaks (duplicate, missing timestamp, dropoff not after pickup,
  duration over 24 h, pickup outside the file's month, negative amount, distance outside 0 to
  200 miles, unknown zone). `int_green_trips__enriched` joins valid trips to zones and the four
  TLC code lists (dbt seeds) and derives duration, speed and an airport flag (ADR 0002).
- **Marts.** `fact_trips` has one row per valid trip with `pickup_date_key`, `pickup_zone_key`
  and `dropoff_zone_key`; `dim_zone` has the 265 zones; `dim_date` covers whole calendar years.
  Their column names and types are enforced dbt contracts. `audit_trip_outcomes` counts records
  and money per source file and outcome.
- **Checks.** dbt data tests (unique, not null, relationships, accepted values) and three
  singular tests (every record accounted for, fact money equals valid money, no gap in
  `dim_date`); five dbt unit tests on hand-made rows; pytest runs end-to-end builds on synthetic
  files with planted defects, enforces the layering from dbt's manifest, and plants bugs in a
  copy of the project to prove the unit tests catch them.

## Alternatives considered

| Option | Why not (yet) |
|---|---|
| Postgres as the local warehouse | Needs a server or Docker on a laptop that already runs other builds; DuckDB reads parquet directly and the project stays a single file. dbt keeps the SQL portable, so a Postgres target can be added later. |
| Load raw files into a `raw` schema first (`COPY` or a Python loader) | One more copy of the data and one more step to keep in sync; reading pinned files in place keeps lineage to the exact file, and checksums give the immutability a raw copy would (ADR 0003). |
| Drop bad rows in staging with `WHERE` filters | Simple, but the dropped records become invisible and staging stops being a faithful copy; counts could no longer be reconciled to the source (ADR 0002). |
| Keep every record in `fact_trips` with an `is_valid` flag | No data hidden, but every dashboard must remember the filter, and one forgotten filter puts a 201,421-mile trip in an average (ADR 0002). |
| dbt-expectations and dbt_utils for tests and keys | Useful in M2 for range tests; for M1 two small macros (surrogate key, money cast) avoid a package download and keep the build offline. |

## Measurement plan

- Completeness, key integrity and money: dbt singular tests in every build and pytest
  assertions against the planted ledger (synthetic) and the raw parquet counts (real data).
- Defect detection: end-to-end tests compare `audit_trip_outcomes` to the generator's ledger for
  three seeds; mutation tests break a rule and expect the matching unit test to fail.
- Build time: wall time of `daw build` on the laptop (includes starting dbt).
- Later milestones: CI duration before and after slim CI, lineage-graph screenshots and one
  sample dashboard (M3).

## Milestones

- **M1:** Raw trip data lands in staging models that only rename, cast and clean. Intermediate
  models join and enrich; marts expose a star schema (fact_trips, dim_zone, dim_date) for BI tools.
- **M2:** Snapshots track slowly changing dimensions (SCD Type 2), and large facts build
  incrementally. Every model has tests (unique, not null, relationships, accepted ranges), and
  SQLFluff enforces SQL style.
- **M3:** Slim CI builds only modified models and their children against production state,
  keeping PR checks fast. dbt docs generates a lineage site you run locally, and exposures link
  marts to the dashboards that use them.

## Risks and open questions

- TLC republishes files from time to time. The SHA-256 pin then fails the download on purpose;
  the pin must be reviewed and updated, and the results re-measured.
- The rejection limits (24 h, 200 miles) are judgement calls. On the pinned data no record lies
  between 200 and 4,076 miles, so the distance limit is not close to real trips; the residual
  defects that remain in the fact (speeds above 100 mph) are listed in the M1 results for M2.
- Zero-duration records with a fare (158, $4,483.18) may be legitimate flat fares. They are
  rejected from the fact but kept with their amounts in the audit, so revenue can still be
  reconciled.
