from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import forecast_longterm.wavelet_optimization.publishing as publishing_module
from forecast_longterm.wavelet_optimization.config import load_research_plan
from forecast_longterm.wavelet_optimization.evaluation import EvaluationBundle, OriginPrediction
from forecast_longterm.wavelet_optimization.metrics import (
    DM_INSUFFICIENT_OBSERVATIONS,
    EvaluationMetrics,
)
from forecast_longterm.wavelet_optimization.publishing import (
    COVERAGE_COLUMNS,
    EVALUATION_COLUMNS,
    OUTPUT_RELATIVE_PATHS,
    PREDICTION_COLUMNS,
    MissingProvenanceError,
    OutputPublisher,
    OutputVersionConflict,
    serialize_coverage,
    serialize_decision,
    serialize_evaluation,
    serialize_predictions,
)
from trm_model.paths import ProjectPaths

RUN_ID = "20260825T153158Z-c94713202491"


def _plan():
    return load_research_plan(
        data_cutoff="2026-04-01",
        origin_dates=("2019-01-01", "2020-01-01"),
    )


def _prediction(plan, *, origin: str, candidate: str, split: str, scoreable: bool):
    return OriginPrediction(
        origin_date=origin,
        horizon_months=6,
        candidate_id=candidate,
        prediction_wavelet=1.0 if scoreable else None,
        prediction_random_walk=0.0 if scoreable else None,
        observed_forward_return=0.5 if scoreable else None,
        label_end_date="2020-07-01",
        n_mature_labels=60 if scoreable else 11,
        scoreability_status="scoreable" if scoreable else "not_scoreable_insufficient_training",
        coverage_status="complete" if scoreable else "incomplete",
        causal_reconstruction=scoreable,
        snapshot_manifest="data/vintages/2020-01-01/manifest.json",
        source_vintage="vintage-1",
        prefix_last_date=origin,
        prefix_length=100,
        prefix_sha256="a" * 64,
        warning=None if scoreable else "insufficient_mature_training",
        data_cutoff=plan.data_cutoff,
        experiment_id=plan.experiment_id,
        product_id=plan.product_id,
        split=split,
    )


def _manifest(plan, *, complete: bool = True):
    context = {
        "plan_hash": plan.plan_hash,
        "snapshot_manifests": ["data/vintages/2020-01-01/manifest.json"],
        "source_vintages": ["vintage-1"],
        "data_cutoff": "2026-04-01",
        "target_definition": "100 * (ln(TRM[t+h]) - ln(TRM[t]))",
        "label_maturity_rule": "i_plus_h_strictly_before_origin",
        "minimum_mature_training": 60,
        "dwt": {
            "wavelet": "db4",
            "levels": 5,
            "boundary_mode": "symmetric",
            "signal_scale": 100.0,
        },
        "candidate_grid": [candidate.to_dict() for candidate in plan.candidates],
        "splits": list(plan.splits),
        "coverage_summary": {"complete": True},
        "promotion_gate": {},
        "output_paths": list(OUTPUT_RELATIVE_PATHS),
    }
    if not complete:
        context.pop("plan_hash")
    return {
        "run_id": RUN_ID,
        "experiment_id": plan.experiment_id,
        "input_files": [],
        "run_context": {"wavelet_optimization": context},
    }


def _coverage():
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


def test_serializers_use_exact_columns_and_keep_exclusions_separate() -> None:
    plan = _plan()
    rows = (
        _prediction(
            plan,
            origin="2020-01-01",
            candidate="db4_l5_sym_D2",
            split="full",
            scoreable=True,
        ),
        _prediction(
            plan,
            origin="2019-01-01",
            candidate="db4_l5_sym_D1",
            split="full",
            scoreable=False,
        ),
    )
    bundle = EvaluationBundle(predictions=rows, coverage=(_coverage(),), plan=plan)

    predictions = serialize_predictions(bundle, plan, run_id=RUN_ID)
    coverage = serialize_coverage(bundle)
    metrics = (
        EvaluationMetrics(
            candidate_id="db4_l5_sym_D2",
            horizon_months=6,
            split="full",
            n_requested_origins=2,
            n_scoreable_origins=1,
            n_excluded_origins=1,
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
        ),
    )
    evaluation = serialize_evaluation(metrics, plan, run_id=RUN_ID)

    assert tuple(predictions.columns) == PREDICTION_COLUMNS
    assert tuple(evaluation.columns) == EVALUATION_COLUMNS
    assert tuple(coverage.columns) == COVERAGE_COLUMNS
    assert list(predictions["origin_date"]) == ["2019-01-01", "2020-01-01"]
    excluded = predictions.iloc[0]
    assert pd.isna(excluded["prediction_wavelet"])
    assert pd.isna(excluded["prediction_random_walk"])
    assert "r2_oos" not in coverage.columns


def test_decision_contains_research_boundaries_and_gate_result() -> None:
    plan = _plan()
    metrics = (
        EvaluationMetrics(
            candidate_id="db4_l5_sym_D5",
            horizon_months=6,
            split="full",
            n_requested_origins=12,
            n_scoreable_origins=12,
            n_excluded_origins=0,
            n_oos=12,
            sse_model=1.0,
            sse_random_walk=2.0,
            r2_oos=0.5,
            mae_model=1.0,
            mae_random_walk=2.0,
            rmse_model=1.0,
            rmse_random_walk=2.0,
            direction_accuracy_model=1.0,
            direction_accuracy_random_walk=0.0,
            dm_stat=1.0,
            dm_p_value=0.01,
            dm_status="evaluated",
        ),
    )
    decision = serialize_decision(
        plan,
        run_id=RUN_ID,
        metrics=metrics,
        gate_decision={
            "eligible": False,
            "eligibility_scope": "methodological_review",
            "candidate_decisions": [],
        },
    )

    assert decision["status"] == "research"
    assert decision["exploratory"] is True
    assert decision["hypotheses"]["H1"]["result"] == "supported"
    assert decision["hypotheses"]["H2"]["result"] == "supported"
    assert decision["promotion_gate"]["eligible"] is False
    assert "no identifica un efecto causal" in decision["warning_no_causality"]
    assert "instrucciones de cobertura" in decision["warning_no_financial_use"]
    assert decision["monthly_forecast_connected"] is False


def test_publisher_writes_four_paths_atomically_and_rejects_same_pair(tmp_path: Path) -> None:
    plan = _plan()
    row = _prediction(
        plan,
        origin="2020-01-01",
        candidate="db4_l5_sym_D1",
        split="full",
        scoreable=True,
    )
    bundle = EvaluationBundle(predictions=(row,), coverage=(_coverage(),), plan=plan)
    publisher = OutputPublisher(paths=ProjectPaths.from_root(tmp_path))

    published = publisher.publish(plan, bundle, _manifest(plan))
    assert published == OUTPUT_RELATIVE_PATHS
    assert all((tmp_path / path).is_file() for path in published)
    decision = json.loads((tmp_path / OUTPUT_RELATIVE_PATHS[-1]).read_text(encoding="utf-8"))
    assert decision["product_id"] == "long_horizon_research"
    assert decision["status"] == "research"
    assert decision["output_status"] == "versioned"

    historical = tmp_path / "results" / "pronostico" / "wavelets_componentes.csv"
    historical.parent.mkdir(parents=True, exist_ok=True)
    historical.write_text("historical\n", encoding="utf-8")
    with pytest.raises(OutputVersionConflict):
        publisher.publish(plan, bundle, _manifest(plan))
    assert historical.read_text(encoding="utf-8") == "historical\n"
    assert not list((tmp_path / "results" / "pronostico" / "wavelet_optimization").glob("*.tmp"))


def test_publisher_rejects_incomplete_future_provenance_before_writing(tmp_path: Path) -> None:
    plan = _plan()
    row = _prediction(
        plan,
        origin="2020-01-01",
        candidate="db4_l5_sym_D1",
        split="full",
        scoreable=True,
    )
    bundle = EvaluationBundle(predictions=(row,), coverage=(_coverage(),), plan=plan)
    publisher = OutputPublisher(paths=ProjectPaths.from_root(tmp_path))

    with pytest.raises(MissingProvenanceError, match="plan_hash"):
        publisher.publish(plan, bundle, _manifest(plan, complete=False))
    assert not (tmp_path / OUTPUT_RELATIVE_PATHS[0]).exists()


def test_publisher_rolls_back_all_outputs_when_atomic_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    row = _prediction(
        plan,
        origin="2020-01-01",
        candidate="db4_l5_sym_D1",
        split="full",
        scoreable=True,
    )
    bundle = EvaluationBundle(predictions=(row,), coverage=(_coverage(),), plan=plan)
    publisher = OutputPublisher(paths=ProjectPaths.from_root(tmp_path))

    historical = tmp_path / "results" / "pronostico" / "wavelets_componentes.csv"
    historical.parent.mkdir(parents=True, exist_ok=True)
    historical.write_bytes(b"historical fixture\\n")
    historical_before = historical.read_bytes()

    original_replace = publishing_module.os.replace
    replace_calls = 0

    def fail_on_second_replace(source, target):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 2:
            raise OSError("simulated atomic commit failure")
        original_replace(source, target)

    monkeypatch.setattr(publishing_module.os, "replace", fail_on_second_replace)

    with pytest.raises(OSError, match="simulated atomic commit failure"):
        publisher.publish(plan, bundle, _manifest(plan))

    assert replace_calls == 2
    assert not any(path.exists() for path in publisher.output_paths)
    assert not list(publisher.output_paths[0].parent.glob("*.tmp"))
    assert historical.read_bytes() == historical_before


def _provenance_fixture(tmp_path: Path) -> tuple[ProjectPaths, Path, Path, Path]:
    """Crea un proyecto mínimo y archivos locales para el contrato de provenance."""

    import shutil

    paths = ProjectPaths.from_root(tmp_path)
    repository_root = Path(__file__).resolve().parents[1]
    for schema_name in ("run_manifest.json", "experiment_registry.json", "experiment_record.json"):
        destination = paths.schemas / schema_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository_root / "schemas" / schema_name, destination)
    registry = paths.experiments / "registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repository_root / "experiments" / "registry.json", registry)

    fixtures = tmp_path / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    config = fixtures / "wavelet.toml"
    config.write_text("fixture = true\n", encoding="utf-8")
    source = fixtures / "trm_snapshot.csv"
    source.write_text("date,banrep_trm_1\n2020-01-01,100.0\n", encoding="utf-8")
    snapshot_manifest = fixtures / "snapshot_manifest.json"
    snapshot_manifest.write_text(
        json.dumps({"origin_date": "2020-01-01", "mode": "snapshot"}),
        encoding="utf-8",
    )
    return paths, config, source, snapshot_manifest


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_publisher_and_provenance_write_manifest_hashes_and_preserve_history(
    tmp_path: Path,
) -> None:
    from forecast_longterm.wavelet_optimization.provenance import ProvenanceRecorder

    paths, config, source, snapshot_manifest = _provenance_fixture(tmp_path)
    plan = _plan()
    coverage = _coverage()
    coverage.update(
        {
            "snapshot_manifest": paths.relative(snapshot_manifest),
            "archived_path": paths.relative(source),
            "sha256": _file_sha256(source),
            "manifest_sha256": _file_sha256(snapshot_manifest),
        }
    )
    row = _prediction(
        plan,
        origin="2020-01-01",
        candidate="db4_l5_sym_D1",
        split="full",
        scoreable=True,
    )
    bundle = EvaluationBundle(predictions=(row,), coverage=(coverage,), plan=plan)

    historical_paths = (
        paths.results / "pronostico" / "wavelets_comparacion_bandas.csv",
        paths.results / "pronostico" / "wavelets_componentes.csv",
    )
    historical_before: dict[Path, bytes] = {}
    for historical_path in historical_paths:
        historical_path.parent.mkdir(parents=True, exist_ok=True)
        historical_path.write_bytes(b"historical fixture\n")
        historical_before[historical_path] = historical_path.read_bytes()

    recorder = ProvenanceRecorder(
        paths=paths,
        config_files=(config,),
        input_files=(source,),
        output_paths=OUTPUT_RELATIVE_PATHS,
    )
    manifest_before_outputs = recorder.build_manifest(
        plan,
        bundle,
        RUN_ID,
        complete=False,
    )
    publisher = OutputPublisher(paths=paths)
    assert publisher.publish(plan, bundle, manifest_before_outputs) == OUTPUT_RELATIVE_PATHS

    complete_manifest = recorder.build_manifest(
        plan,
        bundle,
        RUN_ID,
        complete=True,
    )
    manifest_path = recorder.write_manifest(complete_manifest, complete=True)
    expected_manifest_path = paths.run_directory(RUN_ID) / "manifest.json"
    assert manifest_path == expected_manifest_path
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["product_id"] == "long_horizon_research"
    assert manifest["status"] == "success"
    variant = manifest["run_context"]["wavelet_optimization"]
    assert variant["status"] == "research"
    assert variant["complete"] is True

    output_records = {record["path"]: record for record in manifest["output_files"]}
    output_descriptors = {record["path"]: record for record in variant["outputs"]}
    assert set(output_records) == set(OUTPUT_RELATIVE_PATHS)
    assert set(output_descriptors) == set(OUTPUT_RELATIVE_PATHS)
    assert set(publisher.output_metadata) == set(OUTPUT_RELATIVE_PATHS)
    for relative_path, record in output_records.items():
        output_path = paths.resolve(relative_path)
        assert output_path.is_file()
        assert record["sha256"] == _file_sha256(output_path)
        assert record["bytes"] == output_path.stat().st_size
        assert output_descriptors[relative_path]["kind"] == "research"
        assert output_descriptors[relative_path]["status"] == "versioned"
        assert publisher.output_metadata[relative_path] == {
            "kind": "research",
            "status": "versioned",
            "product_id": "long_horizon_research",
            "research_only": True,
        }

    input_records = {record["path"]: record for record in manifest["input_files"]}
    for input_path in (config, source, snapshot_manifest):
        relative_path = paths.relative(input_path)
        assert relative_path in input_records
        assert input_records[relative_path]["sha256"] == _file_sha256(input_path)
        assert input_records[relative_path]["bytes"] == input_path.stat().st_size
    vintage = variant["source_vintages"][0]
    assert vintage["archived_file_sha256"] == _file_sha256(source)

    for historical_path, content in historical_before.items():
        assert historical_path.read_bytes() == content


def test_conflict_and_missing_provenance_leave_no_partial_publication(
    tmp_path: Path,
) -> None:
    from forecast_longterm.wavelet_optimization.provenance import (
        MissingProvenanceError as ProvenanceMissingProvenanceError,
    )
    from forecast_longterm.wavelet_optimization.provenance import ProvenanceRecorder

    paths, config, source, _snapshot_manifest = _provenance_fixture(tmp_path)
    plan = _plan()
    row = _prediction(
        plan,
        origin="2020-01-01",
        candidate="db4_l5_sym_D1",
        split="full",
        scoreable=True,
    )
    bundle = EvaluationBundle(predictions=(row,), coverage=(_coverage(),), plan=plan)
    publisher = OutputPublisher(paths=paths)
    existing = paths.resolve(OUTPUT_RELATIVE_PATHS[0])
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"pre-existing version\n")

    with pytest.raises(OutputVersionConflict):
        publisher.publish(plan, bundle, _manifest(plan))

    assert existing.read_bytes() == b"pre-existing version\n"
    assert not any(
        paths.resolve(relative).exists() for relative in OUTPUT_RELATIVE_PATHS[1:]
    )
    assert not list(existing.parent.glob("*.tmp"))

    recorder = ProvenanceRecorder(
        paths=paths,
        config_files=(config,),
        input_files=(source,),
        output_paths=OUTPUT_RELATIVE_PATHS,
    )
    complete_manifest = recorder.build_manifest(
        plan,
        bundle,
        RUN_ID,
        complete=False,
    )
    incomplete_variant = dict(complete_manifest["run_context"]["wavelet_optimization"])
    incomplete_variant.pop("plan_hash")
    incomplete_context = dict(complete_manifest["run_context"])
    incomplete_context["wavelet_optimization"] = incomplete_variant
    incomplete_manifest = dict(complete_manifest)
    incomplete_manifest["run_context"] = incomplete_context

    manifest_path = paths.run_directory(RUN_ID) / "manifest.json"
    with pytest.raises(ProvenanceMissingProvenanceError, match="plan_hash"):
        recorder.write_manifest(incomplete_manifest, complete=True)
    assert not manifest_path.exists()
