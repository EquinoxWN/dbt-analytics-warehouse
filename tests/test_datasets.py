"""Manifest validation and bounded, checksum-verified downloads (no network: a fake opener)."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import IO, Any

import pytest

from dbt_analytics_warehouse import datasets
from dbt_analytics_warehouse.datasets import DatasetError, PinnedFile

PAYLOAD = b"parquet bytes " * 1000
HOST = "https://d37ci6vzurychx.cloudfront.net/trip-data/"


def entry(**overrides: Any) -> dict[str, Any]:
    """A valid manifest entry with optional overrides."""
    base: dict[str, Any] = {
        "name": "green_tripdata_2024-01.parquet",
        "url": HOST + "green_tripdata_2024-01.parquet",
        "size": len(PAYLOAD),
        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
    }
    base.update(overrides)
    return base


def opener_for(payload: bytes, calls: list[str] | None = None) -> datasets.Opener:
    """Fake opener that serves the payload and records requested URLs."""

    def _open(url: str, timeout: float) -> IO[bytes]:
        if calls is not None:
            calls.append(url)
        return io.BytesIO(payload)

    return _open


def test_repository_manifest_is_valid_and_pins_four_files() -> None:
    files = datasets.load_manifest(Path(__file__).parents[1] / "datasets.json")
    assert [f.name for f in files] == [
        "green_tripdata_2024-01.parquet",
        "green_tripdata_2024-02.parquet",
        "green_tripdata_2024-03.parquet",
        "taxi_zone_lookup.csv",
    ]
    assert sum(f.size for f in files) < 5_000_000


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": "http://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2024-01.parquet"},
        {"url": "https://example.com/trip-data/green_tripdata_2024-01.parquet"},
        {"url": HOST + "green_tripdata_2024-01.parquet?x=1"},
        {"url": "https://user:pw@d37ci6vzurychx.cloudfront.net/green_tripdata_2024-01.parquet"},
        {"url": HOST + "other.parquet"},
        {"name": "../escape.parquet"},
        {"name": "green_tripdata.exe"},
        {"name": "C:\\green.parquet"},
        {"size": 0},
        {"size": datasets.MAX_FILE_BYTES + 1},
        {"size": True},
        {"size": "12"},
        {"sha256": "ABC"},
        {"sha256": "G" * 64},
        {"extra": "field"},
    ],
)
def test_unsafe_or_malformed_entries_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(DatasetError):
        datasets.parse_entry(entry(**overrides))


def test_duplicate_names_and_empty_manifests_are_rejected(tmp_path: Path) -> None:
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps({"files": [entry(), entry()]}), encoding="utf-8")
    with pytest.raises(DatasetError, match="unique"):
        datasets.load_manifest(dup)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"files": []}), encoding="utf-8")
    with pytest.raises(DatasetError, match="non-empty"):
        datasets.load_manifest(empty)


def test_download_keeps_a_verified_file(tmp_path: Path) -> None:
    pin = datasets.parse_entry(entry())
    path = datasets.download(pin, tmp_path, opener_for(PAYLOAD))
    assert path.read_bytes() == PAYLOAD
    assert datasets.is_verified(path, pin)
    assert list(tmp_path.iterdir()) == [path]


def test_verified_file_is_not_downloaded_again(tmp_path: Path) -> None:
    pin = datasets.parse_entry(entry())
    calls: list[str] = []
    datasets.download(pin, tmp_path, opener_for(PAYLOAD, calls))
    datasets.download(pin, tmp_path, opener_for(PAYLOAD, calls))
    assert calls == [pin.url]


@pytest.mark.parametrize(
    ("served", "message"),
    [
        (PAYLOAD[:-1] + b"X", "SHA-256"),
        (PAYLOAD[:-10], "got"),
        (PAYLOAD + b"more", "more than the pinned"),
    ],
)
def test_bad_download_leaves_no_file(tmp_path: Path, served: bytes, message: str) -> None:
    pin = datasets.parse_entry(entry())
    with pytest.raises(DatasetError, match=message):
        datasets.download(pin, tmp_path, opener_for(served))
    assert list(tmp_path.iterdir()) == []


def test_corrupted_local_file_is_replaced(tmp_path: Path) -> None:
    pin = datasets.parse_entry(entry())
    (tmp_path / pin.name).write_bytes(b"truncated")
    path = datasets.download(pin, tmp_path, opener_for(PAYLOAD))
    assert path.read_bytes() == PAYLOAD


def test_fetch_all_downloads_every_entry(tmp_path: Path) -> None:
    other = b"LocationID,Borough\n1,EWR\n"
    manifest = tmp_path / "m.json"
    files = [
        entry(),
        {
            "name": "taxi_zone_lookup.csv",
            "url": "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv",
            "size": len(other),
            "sha256": hashlib.sha256(other).hexdigest(),
        },
    ]
    manifest.write_text(json.dumps({"files": files}), encoding="utf-8")

    def _open(url: str, timeout: float) -> IO[bytes]:
        return io.BytesIO(other if url.endswith(".csv") else PAYLOAD)

    paths = datasets.fetch_all(manifest, tmp_path / "raw", _open)
    assert [p.name for p in paths] == ["green_tripdata_2024-01.parquet", "taxi_zone_lookup.csv"]


def test_pinned_file_is_immutable() -> None:
    pin = PinnedFile("a.csv", HOST + "a.csv", 1, "0" * 64)
    with pytest.raises(AttributeError):
        pin.size = 2  # type: ignore[misc]


def test_redirects_are_refused() -> None:
    handler = datasets._NoRedirect()
    with pytest.raises(DatasetError, match="redirects"):
        handler.redirect_request(None, None, 302, "Found", {}, "https://example.com/x")
