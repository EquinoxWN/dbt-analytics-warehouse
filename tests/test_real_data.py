"""The pinned NYC TLC files (run `daw fetch` first; CI downloads them): checksums, schema, reconciliation."""

from __future__ import annotations

import duckdb
import pytest
from conftest import Built

from dbt_analytics_warehouse import datasets, synthetic, warehouse

pytestmark = pytest.mark.realdata

RAW = warehouse.Paths.default().raw_dir
PINS = datasets.load_manifest(warehouse.PROJECT_DIR / "datasets.json")
HAVE_DATA = all((RAW / p.name).is_file() for p in PINS)
needs_data = pytest.mark.skipif(
    not HAVE_DATA, reason="pinned TLC files not in data/raw (daw fetch)"
)


@pytest.fixture(scope="module")
def real(tmp_path_factory: pytest.TempPathFactory) -> Built:
    """dbt build over the downloaded files into a throwaway warehouse."""
    paths = warehouse.Paths.under(tmp_path_factory.mktemp("real"), raw_dir=RAW)
    result = warehouse.run_dbt(["build"], paths)
    assert result.returncode == 0, result.stdout[-4000:]
    return Built(paths, synthetic.Ledger(), result.stdout)


@needs_data
def test_downloaded_files_match_their_pins() -> None:
    assert all(datasets.is_verified(RAW / p.name, p) for p in PINS)


@needs_data
def test_synthetic_files_mirror_the_real_schema() -> None:
    con = duckdb.connect()
    try:
        for p in PINS:
            if p.name.endswith(".parquet"):
                rel = con.read_parquet(str(RAW / p.name))
                got = list(zip(rel.columns, [str(t) for t in rel.types], strict=True))
                assert got == list(synthetic.TLC_GREEN_COLUMNS), p.name
    finally:
        con.close()


@needs_data
def test_every_raw_record_is_loaded_or_rejected_with_a_reason(real: Built) -> None:
    con = duckdb.connect()
    try:
        raw_counts = {
            p.name: con.read_parquet(str(RAW / p.name)).count("*").fetchone()[0]  # type: ignore[index]
            for p in PINS
            if p.name.endswith(".parquet")
        }
    finally:
        con.close()
    wh = warehouse.connect(real.paths.db_path)
    try:
        outcomes = warehouse.outcome_counts(wh)
        (facts,) = warehouse.rows(wh, "select count(*) from marts.fact_trips")[0]
    finally:
        wh.close()
    assert {f: sum(c.values()) for f, c in outcomes.items()} == raw_counts
    assert facts == sum(c.get("loaded", 0) for c in outcomes.values())
    rejected = sum(n for c in outcomes.values() for o, n in c.items() if o != "loaded")
    assert 0 < rejected < 0.01 * sum(raw_counts.values())


@needs_data
def test_real_dimensions(real: Built) -> None:
    s = warehouse.summary(real.paths.db_path)
    assert s["dim_zone_rows"] == 265
    assert s["dim_date_range"] == ["2024-01-01", "2024-12-31"]
