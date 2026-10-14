"""Run the dbt project against a chosen raw folder and DuckDB file, and read results back."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

PROJECT_DIR = Path(__file__).resolve().parents[2]
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./:\\ -]+$")


@dataclass(frozen=True)
class Paths:
    """Where dbt reads raw files and writes the warehouse, its artifacts and logs."""

    raw_dir: Path
    db_path: Path
    target_dir: Path
    log_dir: Path

    @classmethod
    def default(cls) -> Paths:
        """The repository defaults: data/raw, data/warehouse.duckdb, target/, logs/."""
        return cls(
            PROJECT_DIR / "data" / "raw",
            PROJECT_DIR / "data" / "warehouse.duckdb",
            PROJECT_DIR / "target",
            PROJECT_DIR / "logs",
        )

    @classmethod
    def under(cls, root: Path, raw_dir: Path | None = None) -> Paths:
        """An isolated set of paths below one folder (tests and synthetic runs)."""
        return cls(
            raw_dir or root / "raw", root / "warehouse.duckdb", root / "target", root / "logs"
        )


def sql_path(path: Path) -> str:
    """Absolute forward-slash path, refused if it could break out of a SQL string literal."""
    text = str(path.resolve()).replace("\\", "/")
    if not _SAFE_PATH.fullmatch(text):
        raise ValueError(f"path has characters not allowed in a SQL literal: {text!r}")
    return text


def dbt_env(paths: Paths, project_dir: Path = PROJECT_DIR) -> dict[str, str]:
    """Environment that pins every dbt and DuckDB location inside the given paths."""
    env = dict(os.environ)
    env.update(
        DAW_RAW_DIR=sql_path(paths.raw_dir),
        DAW_DUCKDB_PATH=sql_path(paths.db_path),
        DBT_TARGET_PATH=str(paths.target_dir),
        DBT_LOG_PATH=str(paths.log_dir),
        DBT_PROFILES_DIR=str(project_dir),
        DBT_PROJECT_DIR=str(project_dir),
        DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        DBT_VERSION_CHECK="false",
    )
    return env


def run_dbt(
    args: list[str], paths: Paths, project_dir: Path = PROJECT_DIR, timeout_s: int = 900
) -> subprocess.CompletedProcess[str]:
    """Run one dbt command in a child process (memory is released when it exits)."""
    if not (project_dir / "dbt_project.yml").is_file():
        raise FileNotFoundError(f"dbt project not found at {project_dir}; install with pip -e")
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-c", "from dbt.cli.main import cli; cli()", *args]
    return subprocess.run(  # noqa: S603 - fixed interpreter and module, list arguments
        cmd,
        cwd=project_dir,
        env=dbt_env(paths, project_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
    )


def connect(db_path: Path) -> duckdb.DuckDBPyConnection:
    """Read-only connection to a built warehouse that never downloads extensions."""
    if not db_path.is_file():
        raise FileNotFoundError(f"no warehouse at {db_path}; run `daw build` first")
    return duckdb.connect(
        str(db_path),
        read_only=True,
        config={"autoinstall_known_extensions": False, "autoload_known_extensions": False},
    )


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[Any, ...]]:
    """All result rows of a query."""
    result: list[tuple[Any, ...]] = con.execute(sql).fetchall()
    return result


def outcome_counts(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, int]]:
    """Records per source file and outcome, from the audit mart."""
    out: dict[str, dict[str, int]] = {}
    for source_file, outcome, n in rows(
        con, "select source_file, outcome, trip_count from marts.audit_trip_outcomes"
    ):
        out.setdefault(str(source_file), {})[str(outcome)] = int(n)
    return out


def summary(db_path: Path) -> dict[str, Any]:
    """Headline numbers of a built warehouse: reconciliation, star schema sizes, sample BI answers."""
    con = connect(db_path)
    try:
        (staged,) = rows(con, "select count(*) from staging.stg_tlc__green_trips")[0]
        (facts, fact_total) = rows(
            con, "select count(*), coalesce(sum(total_amount), 0) from marts.fact_trips"
        )[0]
        outcomes = rows(
            con,
            "select outcome, sum(trip_count)::bigint from marts.audit_trip_outcomes "
            "group by all order by 2 desc, 1",
        )
        boroughs = rows(
            con,
            """
            select z.borough, count(*) as trips, round(avg(f.total_amount), 2) as avg_total,
                   round(100.0 * sum(f.tip_amount) / nullif(sum(f.fare_amount), 0), 1) as tip_pct
            from marts.fact_trips f
            join marts.dim_zone z on f.pickup_zone_key = z.zone_key
            group by all order by trips desc limit 5
            """,
        )
        weekday = rows(
            con,
            """
            select d.is_weekend, count(*) as trips,
                   round(median(f.trip_duration_minutes), 1) as median_minutes
            from marts.fact_trips f
            join marts.dim_date d on f.pickup_date_key = d.date_key
            group by all order by 1
            """,
        )
        (zones,) = rows(con, "select count(*) from marts.dim_zone")[0]
        (days, first_day, last_day) = rows(
            con, "select count(*), min(date_day), max(date_day) from marts.dim_date"
        )[0]
    finally:
        con.close()
    return {
        "staged_records": int(staged),
        "fact_trips": int(facts),
        "fact_total_amount": str(Decimal(fact_total)),
        "outcomes": {str(o): int(n) for o, n in outcomes},
        "dim_zone_rows": int(zones),
        "dim_date_rows": int(days),
        "dim_date_range": [str(first_day), str(last_day)],
        "top_pickup_boroughs": [
            {"borough": b, "trips": int(t), "avg_total": float(a), "tip_pct_of_fare": float(p)}
            for b, t, a, p in boroughs
        ],
        "weekday_vs_weekend": [
            {"is_weekend": bool(w), "trips": int(t), "median_minutes": float(m)}
            for w, t, m in weekday
        ],
    }
