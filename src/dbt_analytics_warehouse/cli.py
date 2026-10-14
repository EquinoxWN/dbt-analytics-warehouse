"""`daw`: fetch pinned data, generate synthetic data, build the warehouse, print its summary."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

from dbt_analytics_warehouse import datasets, synthetic, warehouse


def _fetch(args: argparse.Namespace) -> int:
    """Download every pinned file and verify size and SHA-256."""
    dest = Path(args.dest)
    for pin in datasets.load_manifest(Path(args.manifest)):
        present = datasets.is_verified(dest / pin.name, pin)
        path = datasets.download(pin, dest)
        action = "already present" if present else "downloaded"
        print(f"{action}: {path.name} ({pin.size:,} bytes, size and sha256 match the pin)")
    return 0


def _synth(args: argparse.Namespace) -> int:
    """Write synthetic TLC-shaped files and print the expected outcomes."""
    months = synthetic.month_list(date.fromisoformat(args.first_month + "-01"), args.months)
    ledger = synthetic.generate(Path(args.out), months, args.trips, args.seed, args.defects)
    expected = {f: dict(sorted(c.items())) for f, c in sorted(ledger.outcomes.items())}
    print(json.dumps({"expected_outcomes": expected}, indent=2))
    return 0


def _build(args: argparse.Namespace) -> int:
    """Run `dbt build` (seeds, models, data tests and unit tests) and report the time."""
    paths = warehouse.Paths.default()
    if args.raw_dir:
        paths = warehouse.Paths(Path(args.raw_dir), paths.db_path, paths.target_dir, paths.log_dir)
    if args.db:
        paths = warehouse.Paths(paths.raw_dir, Path(args.db), paths.target_dir, paths.log_dir)
    started = time.perf_counter()
    result = warehouse.run_dbt(["build"], paths)
    elapsed = time.perf_counter() - started
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    print(f"dbt build exit code {result.returncode} in {elapsed:.1f} s")
    return result.returncode


def _report(args: argparse.Namespace) -> int:
    """Print the warehouse summary as JSON."""
    db = Path(args.db) if args.db else warehouse.Paths.default().db_path
    print(json.dumps(warehouse.summary(db), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for all subcommands."""
    parser = argparse.ArgumentParser(prog="daw", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download the pinned NYC TLC files")
    fetch.add_argument("--manifest", default=str(warehouse.PROJECT_DIR / "datasets.json"))
    fetch.add_argument("--dest", default=str(warehouse.Paths.default().raw_dir))
    fetch.set_defaults(func=_fetch)

    synth = sub.add_parser("synth", help="write synthetic files with planted defects")
    synth.add_argument("--out", required=True)
    synth.add_argument("--first-month", default="2024-01")
    synth.add_argument("--months", type=int, default=2, choices=range(1, 13), metavar="1..12")
    synth.add_argument("--trips", type=int, default=500, help="valid trips per month")
    synth.add_argument("--defects", type=int, default=3, help="planted records per defect kind")
    synth.add_argument("--seed", type=int, default=7)
    synth.set_defaults(func=_synth)

    build = sub.add_parser("build", help="dbt build into the DuckDB warehouse")
    build.add_argument("--raw-dir")
    build.add_argument("--db")
    build.set_defaults(func=_build)

    report = sub.add_parser("report", help="summarise a built warehouse")
    report.add_argument("--db")
    report.set_defaults(func=_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the `daw` command."""
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (datasets.DatasetError, ValueError, FileNotFoundError, OSError) as exc:
        print(f"daw: error: {exc}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
