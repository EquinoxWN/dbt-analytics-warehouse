"""Deterministic TLC-shaped green taxi files with planted defects and a ledger of expected outcomes."""

from __future__ import annotations

import csv
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb

# Column names and DuckDB types exactly as in the TLC green parquet files for 2024.
TLC_GREEN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("VendorID", "INTEGER"),
    ("lpep_pickup_datetime", "TIMESTAMP"),
    ("lpep_dropoff_datetime", "TIMESTAMP"),
    ("store_and_fwd_flag", "VARCHAR"),
    ("RatecodeID", "BIGINT"),
    ("PULocationID", "INTEGER"),
    ("DOLocationID", "INTEGER"),
    ("passenger_count", "BIGINT"),
    ("trip_distance", "DOUBLE"),
    ("fare_amount", "DOUBLE"),
    ("extra", "DOUBLE"),
    ("mta_tax", "DOUBLE"),
    ("tip_amount", "DOUBLE"),
    ("tolls_amount", "DOUBLE"),
    ("ehail_fee", "DOUBLE"),
    ("improvement_surcharge", "DOUBLE"),
    ("total_amount", "DOUBLE"),
    ("payment_type", "BIGINT"),
    ("trip_type", "BIGINT"),
    ("congestion_surcharge", "DOUBLE"),
)

# A small zone lookup in the published CSV layout: the placeholders 264/265 and two airports.
ZONES: tuple[tuple[int, str, str, str], ...] = (
    (1, "EWR", "Newark Airport", "EWR"),
    (7, "Queens", "Astoria", "Boro Zone"),
    (41, "Manhattan", "Central Harlem", "Boro Zone"),
    (42, "Manhattan", "Central Harlem North", "Boro Zone"),
    (74, "Manhattan", "East Harlem North", "Boro Zone"),
    (75, "Manhattan", "East Harlem South", "Boro Zone"),
    (82, "Queens", "Elmhurst", "Boro Zone"),
    (97, "Brooklyn", "Fort Greene", "Boro Zone"),
    (129, "Queens", "Jackson Heights", "Boro Zone"),
    (132, "Queens", "JFK Airport", "Airports"),
    (138, "Queens", "LaGuardia Airport", "Airports"),
    (166, "Manhattan", "Morningside Heights", "Boro Zone"),
    (236, "Manhattan", "Upper East Side North", "Yellow Zone"),
    (255, "Brooklyn", "Williamsburg (North Side)", "Boro Zone"),
    (264, "Unknown", "N/A", "N/A"),
    (265, "N/A", "Outside of NYC", "N/A"),
)
UNKNOWN_ZONE_ID = 999

# Each planted defect and the single rejection reason the warehouse must give it.
PLANTED: tuple[str, ...] = (
    "duplicate_record",
    "missing_timestamp",
    "dropoff_not_after_pickup",
    "duration_over_limit",
    "pickup_outside_file_month",
    "negative_amount",
    "distance_out_of_range",
    "unknown_zone",
)

Row = tuple[object, ...]


@dataclass
class Ledger:
    """Expected outcome counts per source file, and the money that should reach fact_trips."""

    outcomes: dict[str, Counter[str]] = field(default_factory=dict)
    loaded_total_amount: Decimal = Decimal("0.00")

    def add(self, source_file: str, outcome: str) -> None:
        """Count one record's expected outcome."""
        self.outcomes.setdefault(source_file, Counter())[outcome] += 1

    def load(self, source_file: str, row: Row) -> None:
        """Count a record that must reach fact_trips, with its total amount."""
        self.add(source_file, "loaded")
        self.loaded_total_amount += Decimal(str(_num(row[16])))

    def total(self, outcome: str) -> int:
        """Records with this outcome across all files."""
        return sum(c[outcome] for c in self.outcomes.values())


def _num(value: object) -> float:
    """A numeric cell as float; anything else is a programming error."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, got {value!r}")
    return float(value)


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """First instant of the month and of the next month."""
    first = datetime.strptime(month + "-01", "%Y-%m-%d")
    nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first, nxt


def _valid_trip(rng: random.Random, start: datetime, end: datetime, zone_ids: list[int]) -> Row:
    """One plausible trip that breaks no validation rule."""
    span = int((end - start).total_seconds()) - 3600
    pickup = start + timedelta(seconds=rng.randrange(span))
    minutes = rng.randint(2, 60)
    dropoff = pickup + timedelta(minutes=minutes, seconds=rng.randrange(60))
    distance = round(rng.uniform(0.3, 15.0), 2)
    fare = round(3.0 + 2.5 * distance + 0.5 * minutes, 2)
    tip = round(fare * rng.choice((0.0, 0.0, 0.15, 0.2)), 2)
    extra, mta, improvement = 1.0, 0.5, 1.0
    congestion = rng.choice((0.0, 0.0, 2.75))
    total = round(fare + tip + extra + mta + improvement + congestion, 2)
    coded = rng.random() >= 0.05  # about 5% of real records carry no codes at all
    return (
        rng.choice((1, 2, 2, 2)),
        pickup,
        dropoff,
        rng.choice(("N", "N", "N", "Y")) if coded else None,
        rng.choice((1, 1, 1, 1, 2, 5, 99)) if coded else None,
        rng.choice(zone_ids),
        rng.choice(zone_ids),
        rng.choice((0, 1, 1, 1, 2, 5)) if coded else None,
        distance,
        fare,
        extra,
        mta,
        tip,
        0.0,
        None,
        improvement,
        total,
        rng.choice((1, 1, 2, 3, 4)) if coded else None,
        rng.choice((1, 1, 1, 2)) if coded else None,
        congestion,
    )


def _plant(defect: str, base: Row, start: datetime) -> Row:
    """Turn a valid trip into one that breaks exactly the named rule first."""
    r = list(base)
    pickup = r[1]
    if not isinstance(pickup, datetime):
        raise TypeError("a planted defect needs a trip with a pickup time")
    if defect == "missing_timestamp":
        r[1] = None
    elif defect == "dropoff_not_after_pickup":
        r[2] = pickup
    elif defect == "duration_over_limit":
        r[2] = pickup + timedelta(hours=25)
    elif defect == "pickup_outside_file_month":
        r[1] = start - timedelta(minutes=20)
        r[2] = start + timedelta(minutes=5)
    elif defect == "negative_amount":
        r[9], r[16] = -abs(_num(r[9])), -abs(_num(r[16]))
    elif defect == "distance_out_of_range":
        r[8] = 250.0
    elif defect == "unknown_zone":
        r[6] = UNKNOWN_ZONE_ID
    else:
        raise ValueError(f"unknown defect {defect!r}")
    return tuple(r)


def generate(
    out_dir: Path, months: list[str], trips_per_month: int, seed: int, defects_per_kind: int = 3
) -> Ledger:
    """Write one parquet file per month plus the zone CSV; return the expected outcomes."""
    if not 1 <= trips_per_month <= 1_000_000:
        raise ValueError("trips_per_month must be in 1..1,000,000")
    if not 0 <= defects_per_kind <= trips_per_month:
        raise ValueError("defects_per_kind must be in 0..trips_per_month")
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    zone_ids = [z[0] for z in ZONES]
    ledger = Ledger()
    write_zone_lookup(out_dir / "taxi_zone_lookup.csv")
    for month in months:
        start, end = _month_bounds(month)
        name = f"green_tripdata_{month}.parquet"
        rows = [_valid_trip(rng, start, end, zone_ids) for _ in range(trips_per_month)]
        for row in rows:
            ledger.load(name, row)
        for defect in PLANTED:
            for _ in range(defects_per_kind):
                base = _valid_trip(rng, start, end, zone_ids)
                if defect == "duplicate_record":
                    # The first copy loads; the second is the duplicate.
                    rows.append(base)
                    ledger.load(name, base)
                    rows.append(base)
                else:
                    rows.append(_plant(defect, base, start))
                ledger.add(name, defect)
        rng.shuffle(rows)
        write_parquet(out_dir / name, rows)
    return ledger


def write_parquet(path: Path, rows: list[Row]) -> None:
    """Write rows with the exact TLC column names and types."""
    cols = ", ".join(f'"{n}" {t}' for n, t in TLC_GREEN_COLUMNS)
    con = duckdb.connect()
    try:
        con.execute(f"create table trips ({cols})")
        placeholders = ", ".join("?" for _ in TLC_GREEN_COLUMNS)
        con.executemany(f"insert into trips values ({placeholders})", rows)  # noqa: S608
        target = str(path).replace("\\", "/").replace("'", "''")
        con.execute(f"copy trips to '{target}' (format parquet)")
    finally:
        con.close()


def write_zone_lookup(path: Path) -> None:
    """Write the zone lookup CSV in the published column layout."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        writer.writerow(("LocationID", "Borough", "Zone", "service_zone"))
        writer.writerows(ZONES)


def month_list(first: date, count: int) -> list[str]:
    """Consecutive months as YYYY-MM starting at first."""
    out: list[str] = []
    year, month = first.year, first.month
    for _ in range(count):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out
