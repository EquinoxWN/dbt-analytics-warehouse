"""End to end: synthetic TLC files through dbt build, checked against the planted ledger."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from conftest import Built, build_synthetic

from dbt_analytics_warehouse import synthetic, warehouse


def test_dbt_build_runs_every_model_and_test(built: Built) -> None:
    assert "Completed successfully" in built.stdout
    assert "ERROR=0" in built.stdout
    assert "WARN=0" in built.stdout


def test_every_record_gets_exactly_the_planted_outcome(built: Built) -> None:
    con = warehouse.connect(built.paths.db_path)
    try:
        actual = warehouse.outcome_counts(con)
    finally:
        con.close()
    expected = {f: dict(c) for f, c in built.ledger.outcomes.items()}
    assert actual == expected


def test_fact_holds_every_valid_trip_and_its_money(built: Built) -> None:
    s = warehouse.summary(built.paths.db_path)
    assert s["fact_trips"] == built.ledger.total("loaded") == 2 * (400 + 3)
    assert Decimal(s["fact_total_amount"]) == built.ledger.loaded_total_amount
    planted = sum(built.ledger.total(d) for d in synthetic.PLANTED)
    assert s["staged_records"] == s["fact_trips"] + planted


def test_star_schema_keys_resolve(built: Built) -> None:
    con = warehouse.connect(built.paths.db_path)
    try:
        orphans = warehouse.rows(
            con,
            """
            select count(*) from marts.fact_trips f
            left join marts.dim_date d on f.pickup_date_key = d.date_key
            left join marts.dim_zone pz on f.pickup_zone_key = pz.zone_key
            left join marts.dim_zone dz on f.dropoff_zone_key = dz.zone_key
            where d.date_key is null or pz.zone_key is null or dz.zone_key is null
            """,
        )
        dup_keys = warehouse.rows(
            con, "select count(*) - count(distinct trip_id) from marts.fact_trips"
        )
    finally:
        con.close()
    assert orphans == [(0,)]
    assert dup_keys == [(0,)]


def test_dimensions_have_expected_shape(built: Built) -> None:
    con = warehouse.connect(built.paths.db_path)
    try:
        zones = warehouse.rows(
            con, "select zone_key, borough, zone_name, is_airport from marts.dim_zone order by 1"
        )
        leap = warehouse.rows(
            con,
            "select date_key, day_name, iso_week_number, is_weekend, day_of_year "
            "from marts.dim_date where date_day = date '2024-02-29'",
        )
        (days, first, last) = warehouse.rows(
            con, "select count(*), min(date_day), max(date_day) from marts.dim_date"
        )[0]
    finally:
        con.close()
    assert len(zones) == len(synthetic.ZONES)
    assert (264, "Unknown", "Unknown", False) in zones
    assert (265, "Unknown", "Outside of NYC", False) in zones
    assert (132, "Queens", "JFK Airport", True) in zones
    assert leap == [(20240229, "Thursday", 9, False, 60)]
    assert (days, first, last) == (366, date(2024, 1, 1), date(2024, 12, 31))


def test_codes_without_a_label_become_unknown_not_null(built: Built) -> None:
    con = warehouse.connect(built.paths.db_path)
    try:
        nulls = warehouse.rows(
            con,
            "select count(*) from marts.fact_trips where vendor_name is null "
            "or rate_code_name is null or payment_type_name is null or trip_type_name is null",
        )
        unknown = warehouse.rows(
            con, "select count(*) from marts.fact_trips where payment_type_name = 'Unknown'"
        )
    finally:
        con.close()
    assert nulls == [(0,)]
    assert unknown[0][0] > 0


@pytest.mark.parametrize(("seed", "months", "trips"), [(101, 1, 150), (202, 3, 90)])
def test_randomized_inputs_always_reconcile(
    tmp_path_factory: pytest.TempPathFactory, seed: int, months: int, trips: int
) -> None:
    month_names = synthetic.month_list(date(2024, 11, 1), months)
    b = build_synthetic(tmp_path_factory.mktemp(f"seed{seed}"), month_names, trips, seed, 2)
    con = warehouse.connect(b.paths.db_path)
    try:
        actual = warehouse.outcome_counts(con)
    finally:
        con.close()
    assert actual == {f: dict(c) for f, c in b.ledger.outcomes.items()}
    s = warehouse.summary(b.paths.db_path)
    assert Decimal(s["fact_total_amount"]) == b.ledger.loaded_total_amount
    # Trips from November 2024 to January 2025 span two calendar years.
    if months == 3:
        assert s["dim_date_rows"] == 366 + 365
