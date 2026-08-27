from __future__ import annotations

import json
import tomllib

import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization.config import (
    BASE_CANDIDATE_GRID,
    DEFAULT_HYPOTHESES,
    EXPERIMENT_ID,
    H1,
    H1_TEXT,
    H2,
    H2_TEXT,
    LEGACY_EXPERIMENT_ID,
    PRODUCT_ID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    RESEARCH_STATUS,
    ConfigurationError,
    PreRegistrationGuard,
    ResearchPlan,
    load_research_plan,
    validate_variant_document,
)
from trm_model.experiments.registry import load_experiment_registry
from trm_model.paths import project_paths
from trm_model.specifications.products import load_products


def _load_explicit_plan():
    return load_research_plan(
        data_cutoff=pd.Timestamp("2026-04-01"),
        origin_dates=("2020-01-01", "2023-01-01"),
    )


def test_variant_toml_is_schema_valid_and_isolated_from_products() -> None:
    paths = project_paths()
    config_path = paths.root / "research" / "configs" / "long_horizon_wavelet_optimization.toml"
    document = tomllib.loads(config_path.read_text(encoding="utf-8"))

    validate_variant_document(document)
    assert document["experiment_id"] == EXPERIMENT_ID
    assert document["horizons_months"] == list(REQUIRED_HORIZONS)
    assert document["evaluation_splits"] == list(REQUIRED_SPLITS)
    assert {item["id"] for item in document["hypotheses"]} == {H1, H2}
    assert [item["id"] for item in document["candidates"]] == [
        "db4_l5_sym_D1",
        "db4_l5_sym_D2",
        "db4_l5_sym_D3",
        "db4_l5_sym_D4",
        "db4_l5_sym_D5",
        "db4_l5_sym_A5",
        "db4_l5_sym_D3_D4",
        "db4_l5_sym_D3_D4_D5",
    ]
    assert "data_cutoff" not in document
    assert config_path.parent != paths.configs / "products"


def test_loader_requires_explicit_cutoff_and_origins() -> None:
    with pytest.raises(ConfigurationError, match="data_cutoff/Data_Cutoff"):
        load_research_plan(origin_dates=("2020-01-01",))

    with pytest.raises(ConfigurationError, match="origin_dates"):
        load_research_plan(data_cutoff="2026-04-01")


@pytest.mark.parametrize(
    "marker",
    [
        "REQUIRED_EXPLICIT_DATE",
        "latest_available",
        "last_observation",
        "auto",
        "TBD",
        "",
        None,
        pd.NaT,
    ],
    ids=[
        "design-marker",
        "latest-available",
        "last-observation",
        "auto",
        "tbd",
        "empty",
        "none",
        "nat",
    ],
)
def test_loader_rejects_cutoff_markers_and_non_dates(marker) -> None:
    with pytest.raises(ConfigurationError, match="data_cutoff/Data_Cutoff"):
        load_research_plan(
            data_cutoff=marker,
            origin_dates=("2020-01-01",),
        )


def test_variant_document_rejects_materialized_cutoff_marker() -> None:
    paths = project_paths()
    config_path = paths.root / "research" / "configs" / "long_horizon_wavelet_optimization.toml"
    document = tomllib.loads(config_path.read_text(encoding="utf-8"))
    document["data_cutoff"] = "REQUIRED_EXPLICIT_DATE"

    with pytest.raises(ConfigurationError, match="data_cutoff/Data_Cutoff"):
        validate_variant_document(document)


def test_loader_builds_frozen_research_plan_from_explicit_dates() -> None:
    plan = _load_explicit_plan()

    assert plan.experiment_id == EXPERIMENT_ID
    assert plan.product_id == PRODUCT_ID
    assert plan.status == RESEARCH_STATUS
    assert plan.data_cutoff == pd.Timestamp("2026-04-01")
    assert plan.origin_dates == (
        pd.Timestamp("2020-01-01"),
        pd.Timestamp("2023-01-01"),
    )
    assert plan.horizons == REQUIRED_HORIZONS
    assert plan.splits == REQUIRED_SPLITS
    assert plan.is_frozen
    assert len(plan.plan_hash) == 64
    assert len(plan.candidates) == 8


def test_hypotheses_are_preregistered_before_first_prediction() -> None:
    plan = _load_explicit_plan()
    guard = PreRegistrationGuard(plan)

    assert not guard.first_prediction_started
    assert plan.hypotheses == DEFAULT_HYPOTHESES
    assert plan.hypotheses == (
        {"id": H1, "statement": H1_TEXT},
        {"id": H2, "statement": H2_TEXT},
    )

    guard.first_prediction()
    assert guard.first_prediction_started


def test_experiment_id_is_new_distinct_and_registered() -> None:
    paths = project_paths()
    registry = load_experiment_registry(paths=paths)
    records = registry["experiments"]
    ids = {record["experiment_id"] for record in records}
    record = next(record for record in records if record["experiment_id"] == EXPERIMENT_ID)

    assert EXPERIMENT_ID != LEGACY_EXPERIMENT_ID
    assert EXPERIMENT_ID in ids
    assert LEGACY_EXPERIMENT_ID in ids
    assert record["parent_experiment_id"] == LEGACY_EXPERIMENT_ID
    assert record["product_id"] == PRODUCT_ID
    assert record["parameters"]["variant_status"] == RESEARCH_STATUS


def test_plan_uses_the_exact_eight_candidate_grid() -> None:
    plan = _load_explicit_plan()
    expected = (
        ("db4_l5_sym_D1", ("D1",)),
        ("db4_l5_sym_D2", ("D2",)),
        ("db4_l5_sym_D3", ("D3",)),
        ("db4_l5_sym_D4", ("D4",)),
        ("db4_l5_sym_D5", ("D5",)),
        ("db4_l5_sym_A5", ("A5",)),
        ("db4_l5_sym_D3_D4", ("D3", "D4")),
        ("db4_l5_sym_D3_D4_D5", ("D3", "D4", "D5")),
    )

    actual = tuple(
        (candidate.candidate_id, candidate.components)
        for candidate in plan.candidates
    )
    assert actual == expected
    assert tuple(plan.candidates) == BASE_CANDIDATE_GRID
    assert all(candidate.wavelet_family == "db4" for candidate in plan.candidates)
    assert all(candidate.levels == 5 for candidate in plan.candidates)
    assert all(candidate.boundary_mode == "symmetric" for candidate in plan.candidates)


@pytest.mark.parametrize("evaluation_outcome", ["positive", "negative", "not_evaluable"])
def test_evaluation_outcomes_preserve_research_product_and_status(evaluation_outcome) -> None:
    """Una conclusión OOS no convierte la variante exploratoria en producto."""

    plan = _load_explicit_plan()
    registry_record = next(
        record
        for record in load_experiment_registry(paths=project_paths())["experiments"]
        if record["experiment_id"] == plan.experiment_id
    )

    serialized_result = plan.to_dict()
    serialized_result["evaluation"] = {"outcome": evaluation_outcome}

    assert serialized_result["product_id"] == PRODUCT_ID
    assert serialized_result["status"] == RESEARCH_STATUS
    assert registry_record["product_id"] == PRODUCT_ID
    assert registry_record["parameters"]["variant_status"] == RESEARCH_STATUS


def test_result_outcome_cannot_replace_variant_research_status() -> None:
    paths = project_paths()
    config_path = paths.root / "research" / "configs" / "long_horizon_wavelet_optimization.toml"
    document = tomllib.loads(config_path.read_text(encoding="utf-8"))

    for outcome in ("positive", "negative", "not_evaluable"):
        mutated = json.loads(json.dumps(document))
        mutated["status"] = outcome
        with pytest.raises(ConfigurationError, match="status debe ser 'research'"):
            ResearchPlan.from_mapping(
                mutated,
                data_cutoff="2026-04-01",
                origin_dates=("2020-01-01",),
            )


def test_shared_product_loader_does_not_discover_variant_toml() -> None:
    products = load_products()
    assert set(products) == {
        "daily_direction",
        "daily_volatility",
        "long_horizon_research",
        "monthly_explanation",
        "monthly_forecast",
        "robustness",
    }
    assert products["long_horizon_research"].vintage_policy == "latest_available"
