from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from trm_model.data.registry import load_source_registry
from trm_model.output_contract import (
    MONTHLY_GENERATED_OUTPUT_COUNT,
    flatten_output_ownership,
    monthly_generated_output_ownership,
)
from trm_model.paths import project_paths
from trm_model.provenance.manifest import build_run_manifest, contract_files
from trm_model.specifications.products import (
    load_product_manifest,
    load_products,
    validate_product_output_ownership,
)
from trm_model.validation.contracts import (
    ContractError,
    validate_product_manifest,
    validate_run_manifest,
)


def test_source_registry_and_product_manifests_are_valid() -> None:
    paths = project_paths()
    registry = load_source_registry(paths=paths)
    assert len(registry.active_sources) == 26
    assert registry.missing_monthly_model_inputs() == []

    products = load_products(paths=paths)
    assert set(products) == {
        "daily_direction",
        "daily_volatility",
        "long_horizon_research",
        "monthly_explanation",
        "monthly_forecast",
        "robustness",
    }
    for product_id in products:
        manifest = load_product_manifest(product_id, paths=paths)
        validate_product_output_ownership(product_id, manifest, paths=paths)
        validate_product_manifest(manifest, paths=paths)


def test_run_manifest_can_be_built_and_validated_without_writing() -> None:
    paths = project_paths()
    manifest = build_run_manifest(
        product_id="monthly_forecast",
        config_files=[paths.configs / "common.toml"],
        input_files=[paths.source_registry()],
        output_files=[paths.schemas / "run_manifest.json"],
        paths=paths,
        status="success",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 23, 0, 1, tzinfo=timezone.utc),
    )
    validate_run_manifest(manifest, paths=paths)
    assert manifest["run_id"].startswith("20260823T000000Z-")
    assert manifest["input_files"][0]["sha256"]


def test_contract_rejects_unknown_product_output_kind() -> None:
    paths = project_paths()
    manifest = json.loads(
        (paths.product_manifest("monthly_forecast")).read_text(encoding="utf-8")
    )
    manifest["outputs"][0]["kind"] = "not-a-kind"
    with pytest.raises(ContractError):
        validate_product_manifest(manifest, paths=paths)


def test_output_catalog_covers_legacy_results_without_unclassified_files() -> None:
    paths = project_paths()
    catalog = json.loads(
        (paths.results / "output_catalog.json").read_text(encoding="utf-8")
    )
    listed = {
        output_path
        for group in catalog["groups"]
        for output_path in group["paths"]
    }
    actual = {
        paths.relative(path)
        for folder in (paths.results / "explicacion", paths.results / "pronostico", paths.results / "robustez")
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".csv", ".json"}
    }
    actual.add(paths.relative(paths.results / "metadata.json"))
    assert actual <= listed
    assert len(listed) == len({path for path in listed})


def test_compatibility_wrappers_and_legacy_packages_are_importable() -> None:
    import forecast_daily.run  # noqa: F401
    import forecast_longterm.global_variables  # noqa: F401
    import volatility_model  # noqa: F401
    from pipelines.daily_direction import run as run_daily_direction
    from pipelines.daily_volatility import run as run_daily_volatility
    from pipelines.long_horizon import run as run_long_horizon
    from pipelines.monthly import run_monthly
    assert callable(run_daily_direction)
    assert callable(run_daily_volatility)
    assert callable(run_long_horizon)
    assert callable(run_monthly)


def test_run_manifest_rejects_stale_contract_tree_hash() -> None:
    paths = project_paths()
    manifest = build_run_manifest(
        product_id="monthly_forecast",
        config_files=[paths.configs / "common.toml"],
        input_files=[paths.source_registry()],
        output_files=[paths.schemas / "run_manifest.json"],
        paths=paths,
        status="success",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 23, 0, 1, tzinfo=timezone.utc),
    )
    manifest["contract_tree_sha256"] = "0" * 64
    with pytest.raises(ContractError, match="contract_tree_sha256"):
        validate_run_manifest(manifest, paths=paths)


def test_monthly_output_contract_is_exact_and_disjoint() -> None:
    ownership = monthly_generated_output_ownership(project_paths())
    output_paths = flatten_output_ownership(ownership)
    assert len(output_paths) == MONTHLY_GENERATED_OUTPUT_COUNT
    assert len(output_paths) == len(set(output_paths))
    contract_paths = {project_paths().relative(path) for path in contract_files(project_paths().root)}
    assert {"requirements.lock", "requirements-optional.lock"}.issubset(contract_paths)


def test_experiment_registry_is_valid_and_ids_are_unique() -> None:
    from trm_model.experiments.registry import validate_experiment_registry

    registry = validate_experiment_registry(paths=project_paths())
    ids = [record["experiment_id"] for record in registry["experiments"]]
    assert len(ids) >= 1
    assert len(ids) == len(set(ids))


def test_run_manifest_experiment_references_are_validated() -> None:
    from trm_model.experiments.registry import MONTHLY_EXPERIMENT_IDS

    paths = project_paths()
    manifest = build_run_manifest(
        product_id="monthly_bundle",
        config_files=[paths.configs / "common.toml"],
        input_files=[paths.source_registry()],
        output_files=[paths.schemas / "run_manifest.json"],
        paths=paths,
        status="success",
        started_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 23, 0, 1, tzinfo=timezone.utc),
        experiment_ids=MONTHLY_EXPERIMENT_IDS,
    )
    validate_run_manifest(manifest, paths=paths)
    assert manifest["experiment_ids"] == list(MONTHLY_EXPERIMENT_IDS)

    manifest["experiment_id"] = "monthly_forecast.not_registered.v1"
    with pytest.raises(ValueError, match="no registrados"):
        validate_run_manifest(manifest, paths=paths)


def test_experiment_listing_and_filters() -> None:
    from trm_model.experiments.registry import experiment_details, list_experiments

    monthly = list_experiments(product_id="monthly_forecast", paths=project_paths())
    assert monthly
    assert all(record["product_id"] == "monthly_forecast" for record in monthly)
    active = list_experiments(status="active", paths=project_paths())
    assert active
    assert all(record["status"] == "active" for record in active)
    details = experiment_details(monthly[0]["experiment_id"], paths=project_paths())
    assert details["experiment_id"] == monthly[0]["experiment_id"]
    assert "observed_runs" in details


def test_experiment_registration_rejects_duplicate_id(tmp_path) -> None:
    from trm_model.experiments.registry import (
        ExperimentError,
        load_experiment_registry,
        register_experiment_file,
    )

    record = load_experiment_registry(paths=project_paths())["experiments"][0]
    candidate = tmp_path / "duplicate.json"
    candidate.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ExperimentError, match="ya existe"):
        register_experiment_file(candidate, paths=project_paths())
