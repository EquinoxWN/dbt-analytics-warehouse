"""The synthetic generator: deterministic, TLC-shaped, with a ledger that matches its files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest

from dbt_analytics_warehouse import synthetic


def describe(path: Path) -> list[tuple[str, str]]:
    """Column names and DuckDB types of a parquet file."""
    con = duckdb.connect()
    try:
        rel = con.read_parquet(str(path))
        return list(zip(rel.columns, [str(t) for t in rel.types], strict=True))
    finally:
        con.close()


def test_same_seed_gives_identical_files(tmp_path: Path) -> None:
    synthetic.generate(tmp_path / "a", ["2024-01"], 50, seed=3)
    synthetic.generate(tmp_path / "b", ["2024-01"], 50, seed=3)
    for name in ("green_tripdata_2024-01.parquet", "taxi_zone_lookup.csv"):
        con = duckdb.connect()
        try:
            a = con.sql(f"select * from '{tmp_path / 'a' / name}'").fetchall()
            b = con.sql(f"select * from '{tmp_path / 'b' / name}'").fetchall()
        finally:
            con.close()
        assert a == b


def test_files_have_the_tlc_column_names_and_types(tmp_path: Path) -> None:
    synthetic.generate(tmp_path, ["2024-01"], 20, seed=1)
    assert describe(tmp_path / "green_tripdata_2024-01.parquet") == list(
        synthetic.TLC_GREEN_COLUMNS
    )


def test_ledger_counts_match_rows_written(tmp_path: Path) -> None:
    ledger = synthetic.generate(tmp_path, ["2024-01", "2024-02"], 30, seed=5, defects_per_kind=2)
    con = duckdb.connect()
    try:
        for name, counts in ledger.outcomes.items():
            (n,) = con.sql(f"select count(*) from '{tmp_path / name}'").fetchone() or (0,)
            # A planted duplicate is two records: one loaded, one rejected.
            assert n == sum(counts.values())
            assert counts["loaded"] == 30 + 2
            assert all(counts[d] == 2 for d in synthetic.PLANTED)
    finally:
        con.close()


def test_month_list_rolls_over_the_year() -> None:
    assert synthetic.month_list(date(2024, 11, 1), 3) == ["2024-11", "2024-12", "2025-01"]


@pytest.mark.parametrize(("trips", "defects"), [(0, 0), (5, 6), (2_000_000, 1)])
def test_out_of_range_sizes_are_rejected(tmp_path: Path, trips: int, defects: int) -> None:
    with pytest.raises(ValueError, match="must be in"):
        synthetic.generate(tmp_path, ["2024-01"], trips, seed=1, defects_per_kind=defects)
