"""Shared fixtures: one synthetic warehouse built once per test session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from dbt_analytics_warehouse import synthetic, warehouse


def pytest_configure(config: pytest.Config) -> None:
    """Create the git-ignored parent of --basetemp, missing on a fresh checkout."""
    basetemp = config.option.basetemp
    if basetemp:
        Path(basetemp).parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Built:
    """A dbt build over synthetic files, with the outcomes the generator planted."""

    paths: warehouse.Paths
    ledger: synthetic.Ledger
    stdout: str

    def manifest(self) -> dict[str, Any]:
        """The manifest.json dbt wrote for this build."""
        data: dict[str, Any] = json.loads(
            (self.paths.target_dir / "manifest.json").read_text(encoding="utf-8")
        )
        return data


def build_synthetic(root: Path, months: list[str], trips: int, seed: int, defects: int) -> Built:
    """Generate files under root and run `dbt build` on them; fail with dbt's output."""
    paths = warehouse.Paths.under(root)
    ledger = synthetic.generate(paths.raw_dir, months, trips, seed, defects)
    result = warehouse.run_dbt(["build"], paths)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    return Built(paths, ledger, result.stdout)


@pytest.fixture(scope="session")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    """Two months, 400 valid trips each, three of every planted defect."""
    root = tmp_path_factory.mktemp("synthetic")
    return build_synthetic(root, ["2024-02", "2024-03"], trips=400, seed=7, defects=3)
