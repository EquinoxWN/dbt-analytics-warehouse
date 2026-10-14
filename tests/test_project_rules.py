"""Layering rules read from dbt's manifest: staging -> intermediate -> marts, documented, contracted."""

from __future__ import annotations

from typing import Any

from conftest import Built

LAYERS: dict[str, tuple[str, ...]] = {
    "staging": ("stg_",),
    "intermediate": ("int_",),
    "marts": ("fact_", "dim_", "audit_"),
}


def models(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Project models keyed by name."""
    return {
        n["name"]: n
        for n in manifest["nodes"].values()
        if n["resource_type"] == "model" and n["package_name"] == "analytics_warehouse"
    }


def layer(node: dict[str, Any]) -> str:
    """The models/ sub-folder a model lives in."""
    return str(node["original_file_path"]).replace("\\", "/").split("/")[1]


def parents(node: dict[str, Any]) -> list[str]:
    """Upstream unique ids of a model."""
    return list(node["depends_on"]["nodes"])


def test_every_model_sits_in_a_known_layer_with_its_prefix(built: Built) -> None:
    found = models(built.manifest())
    assert len(found) == 8
    for name, node in found.items():
        assert layer(node) in LAYERS, name
        assert name.startswith(LAYERS[layer(node)]), name


def test_only_staging_reads_sources_and_staging_reads_nothing_else(built: Built) -> None:
    for name, node in models(built.manifest()).items():
        sources = [p for p in parents(node) if p.startswith("source.")]
        if layer(node) == "staging":
            assert sources, name
            assert all(p.startswith("source.") for p in parents(node)), name
        else:
            assert not sources, name


def test_intermediate_never_reads_marts(built: Built) -> None:
    found = models(built.manifest())
    by_id = {n["unique_id"]: n for n in found.values()}
    for name, node in found.items():
        if layer(node) == "intermediate":
            ups = [by_id[p] for p in parents(node) if p in by_id]
            assert all(layer(u) != "marts" for u in ups), name


def test_staging_is_views_and_star_schema_is_tables_with_contracts(built: Built) -> None:
    found = models(built.manifest())
    for name, node in found.items():
        materialized = node["config"]["materialized"]
        assert materialized == ("view" if layer(node) == "staging" else "table"), name
    for name in ("fact_trips", "dim_zone", "dim_date"):
        assert found[name]["config"]["contract"]["enforced"] is True, name


def test_every_model_and_mart_column_is_documented(built: Built) -> None:
    found = models(built.manifest())
    for name, node in found.items():
        assert node["description"].strip(), name
    for name in ("fact_trips", "dim_zone"):
        for column, spec in found[name]["columns"].items():
            assert spec["description"].strip(), f"{name}.{column}"


def test_star_schema_foreign_keys_are_tested(built: Built) -> None:
    tests = [
        n
        for n in built.manifest()["nodes"].values()
        if n["resource_type"] == "test"
        and n.get("test_metadata", {}).get("name") == "relationships"
    ]
    covered = {(t["attached_node"].split(".")[-1], t["column_name"]) for t in tests}
    assert {
        ("fact_trips", "pickup_date_key"),
        ("fact_trips", "pickup_zone_key"),
        ("fact_trips", "dropoff_zone_key"),
    } <= covered
