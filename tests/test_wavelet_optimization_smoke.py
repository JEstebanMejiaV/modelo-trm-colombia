"""Smoke contracts for the opt-in long-horizon wavelet research variant."""

from __future__ import annotations

import importlib
import json
import tomllib
from typing import Any

import pytest

from forecast_longterm.wavelet_optimization.config import (
    EXPERIMENT_ID,
    LEGACY_EXPERIMENT_ID,
    load_research_plan,
    validate_variant_document,
)
from forecast_longterm.wavelet_optimization.evaluation import EvaluationBundle, OriginPrediction
from forecast_longterm.wavelet_optimization.metrics import (
    DM_INSUFFICIENT_OBSERVATIONS,
    EvaluationMetrics,
)
from forecast_longterm.wavelet_optimization.publishing import (
    OUTPUT_RELATIVE_PATHS,
    serialize_coverage_records,
    serialize_decision,
    serialize_evaluation_records,
    serialize_prediction_records,
)
from pipelines import long_horizon
from trm_model import cli
from trm_model.experiments.registry import validate_experiment_registry
from trm_model.paths import project_paths
from trm_model.specifications.products import (
    load_product_manifest,
    load_products,
)
from trm_model.validation.contracts import validate_document, validate_product_manifest

RUN_ID = "20260825T153158Z-c94713202491"
HISTORICAL_WAVELET_PATHS = {
    "results/pronostico/wavelets_comparacion_bandas.csv",
    "results/pronostico/wavelets_componentes.csv",
}


def _plan():
    return load_research_plan(
        data_cutoff="2026-04-01",
        origin_dates=("2020-01-01", "2021-01-01"),
    )


def _prediction(plan) -> OriginPrediction:
    return OriginPrediction(
        origin_date="2020-01-01",
        horizon_months=6,
        candidate_id="db4_l5_sym_D1",
        prediction_wavelet=1.0,
        prediction_random_walk=0.0,
        observed_forward_return=0.5,
        label_end_date="2020-07-01",
        n_mature_labels=60,
        scoreability_status="scoreable",
        coverage_status="complete",
        causal_reconstruction=True,
        snapshot_manifest="data/vintages/2020-01-01/manifest.json",
        source_vintage="vintage-1",
        split="full",
        prefix_last_date="2020-01-01",
        prefix_length=100,
        prefix_sha256="a" * 64,
        data_cutoff=plan.data_cutoff,
        experiment_id=plan.experiment_id,
        product_id=plan.product_id,
    )


def _coverage() -> dict[str, Any]:
    return {
        "origin_date": "2020-01-01",
        "horizon_months": 6,
        "source_id": "banrep_trm_1",
        "snapshot_manifest": "data/vintages/2020-01-01/manifest.json",
        "source_vintage": "vintage-1",
        "available_through": "2020-01-01",
        "sha256": "b" * 64,
        "n_observations_available": 100,
        "n_missing": 0,
        "coverage_status": "complete",
        "required_for_candidate": True,
        "excluded_origins": [],
        "reason": None,
    }


def _metrics() -> EvaluationMetrics:
    return EvaluationMetrics(
        candidate_id="db4_l5_sym_D1",
        horizon_months=6,
        split="full",
        n_requested_origins=1,
        n_scoreable_origins=1,
        n_excluded_origins=0,
        n_oos=1,
        sse_model=1.0,
        sse_random_walk=2.0,
        r2_oos=0.5,
        mae_model=1.0,
        mae_random_walk=2.0,
        rmse_model=1.0,
        rmse_random_walk=2.0,
        direction_accuracy_model=1.0,
        direction_accuracy_random_walk=0.0,
        dm_stat=None,
        dm_p_value=None,
        dm_status=DM_INSUFFICIENT_OBSERVATIONS,
    )


def _bundle(plan) -> EvaluationBundle:
    return EvaluationBundle(
        predictions=(_prediction(plan),),
        coverage=(_coverage(),),
        metrics=(_metrics(),),
        plan=plan,
    )


def _serialized_documents(plan) -> dict[str, list[dict[str, Any]]]:
    bundle = _bundle(plan)
    return {
        "wavelet_optimization_predicciones_por_origen.json": serialize_prediction_records(
            bundle,
            plan,
            run_id=RUN_ID,
        ),
        "wavelet_optimization_evaluacion_por_candidato.json": serialize_evaluation_records(
            bundle,
            plan,
            run_id=RUN_ID,
        ),
        "wavelet_optimization_cobertura_point_in_time.json": serialize_coverage_records(bundle),
        "wavelet_optimization_hipotesis_decision.json": [
            serialize_decision(
                plan,
                run_id=RUN_ID,
                metrics=bundle.metrics,
                gate_decision={
                    "eligible": False,
                    "eligibility_scope": "methodological_review",
                    "candidate_decisions": [],
                },
            )
        ],
    }


def _json_round_trip(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


@pytest.mark.parametrize(
    "schema_name",
    [
        "wavelet_optimization_predicciones_por_origen.json",
        "wavelet_optimization_evaluacion_por_candidato.json",
        "wavelet_optimization_cobertura_point_in_time.json",
        "wavelet_optimization_hipotesis_decision.json",
    ],
)
def test_serialized_wavelet_records_validate_against_all_four_schemas(schema_name: str) -> None:
    paths = project_paths()
    documents = _serialized_documents(_plan())[schema_name]

    assert documents
    for document in documents:
        validate_document(
            _json_round_trip(document),
            paths.schema(schema_name),
        )


def test_variant_import_config_and_shared_product_loader_are_compatible() -> None:
    paths = project_paths()
    module = importlib.import_module("forecast_longterm.wavelet_optimization")
    assert callable(module.run_wavelet_optimization)

    config_path = paths.root / "research" / "configs" / "long_horizon_wavelet_optimization.toml"
    config_document = tomllib.loads(config_path.read_text(encoding="utf-8"))
    validate_variant_document(config_document)
    validate_document(config_document, paths.schema("long_horizon_wavelet_optimization.json"))

    products = load_products(paths=paths)
    assert "long_horizon_wavelet_optimization" not in products
    assert products["long_horizon_research"].vintage_policy == "latest_available"


def test_registry_and_manifest_catalog_ownership_are_unique_and_keep_historical_wavelets() -> None:
    paths = project_paths()

    registry = validate_experiment_registry(paths=paths)
    experiment_ids = [record["experiment_id"] for record in registry["experiments"]]
    assert len(experiment_ids) == len(set(experiment_ids))
    assert EXPERIMENT_ID in experiment_ids
    assert LEGACY_EXPERIMENT_ID in experiment_ids
    assert EXPERIMENT_ID != LEGACY_EXPERIMENT_ID

    variant_manifest_path = (
        paths.root / "research" / "manifests" / "long_horizon_wavelet_optimization.json"
    )
    variant_manifest = json.loads(variant_manifest_path.read_text(encoding="utf-8"))
    validate_product_manifest(variant_manifest, paths=paths)
    variant_outputs = [output["path"] for output in variant_manifest["outputs"]]
    assert len(variant_outputs) == len(set(variant_outputs))
    assert set(variant_outputs) == set(OUTPUT_RELATIVE_PATHS)
    assert all(
        output["kind"] == "research" and output["status"] == "versioned"
        for output in variant_manifest["outputs"]
    )
    assert HISTORICAL_WAVELET_PATHS.isdisjoint(variant_outputs)

    legacy_manifest = load_product_manifest("long_horizon_research", paths=paths)
    validate_product_manifest(legacy_manifest, paths=paths)
    legacy_outputs = [output["path"] for output in legacy_manifest["outputs"]]
    assert len(legacy_outputs) == len(set(legacy_outputs))
    assert HISTORICAL_WAVELET_PATHS <= set(legacy_outputs)
    assert set(variant_outputs) <= set(legacy_outputs)

    catalog = json.loads((paths.results / "output_catalog.json").read_text(encoding="utf-8"))
    groups = catalog["groups"]
    group_ids = [group["product_id"] for group in groups]
    assert len(group_ids) == len(set(group_ids))

    owner_by_path: dict[str, str] = {}
    for group in groups:
        group_paths = list(group["paths"])
        assert len(group_paths) == len(set(group_paths))
        for output_path in group_paths:
            assert output_path not in owner_by_path
            owner_by_path[output_path] = group["product_id"]

    assert owner_by_path["results/pronostico/wavelets_comparacion_bandas.csv"] == (
        "long_horizon_research"
    )
    assert owner_by_path["results/pronostico/wavelets_componentes.csv"] == (
        "long_horizon_research"
    )
    assert all(owner_by_path[path] == "long_horizon_research" for path in variant_outputs)


def test_cli_wavelet_opt_in_forwards_explicit_cutoff_and_origins_without_legacy_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(long_horizon, "run", fake_run)

    assert cli.main(
        [
            "run-research",
            "--module",
            "wavelet_optimization",
            "--data-cutoff",
            "2026-04-01",
            "--origin-date",
            "2020-01-01",
            "--forecast-origin",
            "2021-01-01",
        ]
    ) == 0
    assert cli.main(["run-research", "--module", "wavelets"]) == 0

    assert calls == [
        (
            ("wavelet_optimization",),
            {
                "data_cutoff": "2026-04-01",
                "origin_dates": ["2020-01-01", "2021-01-01"],
                "config_path": None,
                "schema_path": None,
            },
        ),
        (("wavelets",), {}),
    ]


def test_cli_rejects_wavelet_variant_without_cutoff_or_origins() -> None:
    with pytest.raises(ValueError, match="Data_Cutoff explícito"):
        cli.main(
            [
                "run-research",
                "--module",
                "wavelet_optimization",
                "--origin-date",
                "2020-01-01",
            ]
        )

    with pytest.raises(ValueError, match="Forecast_Origin explícito"):
        cli.main(
            [
                "run-research",
                "--module",
                "wavelet_optimization",
                "--data-cutoff",
                "2026-04-01",
            ]
        )


def test_wavelet_variant_is_opt_in_and_legacy_dispatch_remains_separate() -> None:
    assert long_horizon.WAVELET_OPTIMIZATION_MODULE in long_horizon.ALLOWED_MODULES
    assert long_horizon.WAVELET_OPTIMIZATION_MODULE not in long_horizon.LEGACY_MODULES
    assert "wavelets" in long_horizon.LEGACY_MODULES
