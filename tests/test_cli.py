"""The `daw` command line: synth output, clear errors and exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dbt_analytics_warehouse import cli


def test_synth_prints_expected_outcomes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["synth", "--out", str(tmp_path), "--trips", "10", "--defects", "1"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)["expected_outcomes"]
    assert set(out) == {"green_tripdata_2024-01.parquet", "green_tripdata_2024-02.parquet"}
    assert out["green_tripdata_2024-01.parquet"]["loaded"] == 11
    assert (tmp_path / "taxi_zone_lookup.csv").is_file()


def test_bad_manifest_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"files": [{"name": "x.csv"}]}), encoding="utf-8")
    assert cli.main(["fetch", "--manifest", str(manifest), "--dest", str(tmp_path)]) == 2
    assert "daw: error:" in capsys.readouterr().err


def test_report_without_a_warehouse_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["report", "--db", str(tmp_path / "missing.duckdb")]) == 2
    assert "run `daw build` first" in capsys.readouterr().err


def test_unsafe_raw_dir_is_refused_before_dbt_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "it's"
    assert cli.main(["build", "--raw-dir", str(bad), "--db", str(tmp_path / "w.duckdb")]) == 2
    assert "not allowed in a SQL literal" in capsys.readouterr().err
