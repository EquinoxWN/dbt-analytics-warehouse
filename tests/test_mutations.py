"""The dbt unit tests catch planted bugs: copy the project, break one rule, expect a failure."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dbt_analytics_warehouse import synthetic, warehouse

COPIED = ("models", "macros", "seeds", "data_tests", "dbt_project.yml", "profiles.yml")
VALIDATED = "models/intermediate/int_green_trips__validated.sql"
STAGING = "models/staging/tlc/stg_tlc__green_trips.sql"


def copy_project(dest: Path) -> Path:
    """A throwaway copy of the dbt project."""
    for item in COPIED:
        src = warehouse.PROJECT_DIR / item
        if src.is_dir():
            shutil.copytree(src, dest / item)
        else:
            shutil.copy2(src, dest / item)
    return dest


@pytest.mark.parametrize(
    ("path", "old", "new", "failing_test"),
    [
        # Off-by-one on the distance limit: a 200-mile trip would be rejected.
        (VALIDATED, "trip_distance_miles > {{", "trip_distance_miles >= {{", "validated_applies"),
        # Rules checked in the wrong order: a bad trip gets the wrong reason.
        (
            VALIDATED,
            "when copy_number > 1",
            "when not has_known_pickup_zone then 'unknown_zone' when copy_number > 1",
            "validated_applies",
        ),
        # Staging forgets that rate code 99 means unknown.
        (STAGING, "nullif(RatecodeID, 99)", "RatecodeID", "stg_green_trips_cleans"),
    ],
)
def test_unit_tests_fail_on_a_planted_bug(
    tmp_path: Path, path: str, old: str, new: str, failing_test: str
) -> None:
    project = copy_project(tmp_path / "project")
    target = project / path
    text = target.read_text(encoding="utf-8")
    assert text.count(old) == 1
    target.write_text(text.replace(old, new), encoding="utf-8")
    paths = warehouse.Paths.under(tmp_path / "run")
    synthetic.generate(paths.raw_dir, ["2024-01"], 20, seed=1, defects_per_kind=1)
    result = warehouse.run_dbt(["build"], paths, project_dir=project)
    assert result.returncode != 0
    failed = [line for line in result.stdout.splitlines() if " FAIL " in line]
    assert any(failing_test in line for line in failed), result.stdout[-3000:]
