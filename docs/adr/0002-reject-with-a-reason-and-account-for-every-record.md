# ADR 0002: Reject records with one named reason, and account for every record

- **Status:** Accepted

## Context

About 0.5% of the pinned TLC records cannot be counted as trips: refunds and disputes stored as
negative fares, zero-length trips, odometer readings above 4,000 miles, pickups outside the
file's month. There are three usual ways to handle them:

1. Filter them out with `WHERE` clauses, in staging or wherever someone notices.
2. Keep them in the fact table with an `is_valid` flag and let every query filter.
3. Keep them out of the fact table, but give each one a named reason in a model that is
   reconciled against the source.

Option 1 is what makes "some SQL" untrustworthy: nobody can say how many records a number
excludes. Option 2 hides nothing, but each dashboard must remember the filter; one forgotten
filter turns the average trip distance from 2.64 miles into 20.91 miles on the pinned data.

## Decision

- Staging never drops a row. `int_green_trips__validated` keeps every staged record and sets
  `rejection_reason` to the first rule it breaks, in a fixed order: `duplicate_record`,
  `missing_timestamp`, `dropoff_not_after_pickup`, `duration_over_limit`,
  `pickup_outside_file_month`, `negative_amount`, `distance_out_of_range`, `unknown_zone`.
  One reason per record, so the counts add up.
- `fact_trips` holds only records without a reason. `audit_trip_outcomes` reports records and
  money per source file and outcome, including `loaded`.
- A singular dbt test fails the build when, for any file, staged records differ from fact rows
  plus rejected records; another fails when fact money differs from valid-record money.
- Limits are dbt variables (`max_trip_duration_hours: 24`, `max_trip_distance_miles: 200`) so
  they are visible in one place and can be overridden per run.

## Consequences

- Dashboards on `fact_trips` need no filter, and the audit shows exactly what they exclude: on
  the pinned data 819 of 167,585 records (0.49%), in four reasons, and the audit's money total
  equals the staged total to the cent.
- Some rejected records may be legitimate: 158 zero-duration records carry $4,483.18 of fares
  (possibly flat fares entered without running the meter). They stay visible in the audit, but
  revenue from `fact_trips` alone is lower by that amount. A revenue view that needs them should
  read the audit, not relax the rule.
- The first-rule-wins order hides a record's second problem. That is deliberate (it keeps counts
  additive); the unit test pins the order, and a mutation test proves a reordering is caught.
- Records that pass all eight rules can still be odd (384 fact trips average above 100 mph
  because their duration is a few seconds). M2's accepted-range tests decide whether these
  become rules or warnings.
