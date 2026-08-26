from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import forecast_longterm.wavelet_optimization as wavelet_variant
from forecast_longterm.wavelet_optimization.config import ResearchPlan, load_research_plan
from forecast_longterm.wavelet_optimization.evaluation import (
    NOT_EVALUABLE_LABEL_NOT_MATURE,
    NOT_SCOREABLE_SNAPSHOT_MISSING,
    SCOREABLE,
)
from forecast_longterm.wavelet_optimization.metrics import MetricsCalculator
from forecast_longterm.wavelet_optimization.promotion import PromotionGate
from forecast_longterm.wavelet_optimization.provenance import ProvenanceRecorder
from forecast_longterm.wavelet_optimization.publishing import (
    COVERAGE_COLUMNS,
    EVALUATION_COLUMNS,
    OUTPUT_RELATIVE_PATHS,
    PREDICTION_COLUMNS,
    OutputPublisher,
)
from forecast_longterm.wavelet_optimization.reconstruction import (
    ReconstructionMetadata,
    ReconstructionResult,
    hash_prefix,
)
from forecast_longterm.wavelet_optimization.snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSnapshot,
    SnapshotResolutionError,
    SourceVintage,
)
from trm_model.paths import ProjectPaths

_RUN_ID = "20270101T000000Z-e2e123456789"
_STARTED_AT = datetime(2027, 1, 1, tzinfo=timezone.utc)
_DATA_CUTOFF = pd.Timestamp("2007-12-01")
_SCOREABLE_ORIGIN = pd.Timestamp("2006-01-01")
_IMMATURE_ORIGIN = pd.Timestamp("2007-11-01")
_MISSING_SNAPSHOT_ORIGIN = pd.Timestamp("2007-12-01")


class _InMemorySnapshotResolver:
    def __init__(
        self,
        snapshots: Mapping[pd.Timestamp, PointInTimeSnapshot],
        *,
        missing_origin: pd.Timestamp,
    ) -> None:
        self._snapshots = dict(snapshots)
        self._missing_origin = missing_origin

    def resolve(
        self,
        origin: ForecastOrigin,
        required_source_ids: tuple[str, ...],
    ) -> PointInTimeSnapshot:
        if origin.origin_date == self._missing_origin:
            raise SnapshotResolutionError(
                "snapshot PIT ausente para la fixture E2E",
                origin=origin,
                source_id=BANREP_TRM_SOURCE_ID,
                coverage_status="missing",
                scoreability_status=NOT_SCOREABLE_SNAPSHOT_MISSING,
                reason="snapshot_manifest_missing",
            )
        snapshot = self._snapshots[origin.origin_date]
        for source_id in required_source_ids:
            snapshot.source(source_id)
        return snapshot


class _InMemorySeriesStore:
    def __init__(self, prefixes: Mapping[pd.Timestamp, pd.Series]) -> None:
        self._prefixes = dict(prefixes)

    def monthly_series(
        self,
        snapshot: PointInTimeSnapshot,
        source_id: str,
        *,
        through: pd.Timestamp,
    ) -> pd.Series:
        if source_id != BANREP_TRM_SOURCE_ID:
            raise KeyError(source_id)
        prefix = self._prefixes[snapshot.origin.origin_date].copy(deep=True)
        assert prefix.index[-1] <= through
        return prefix


class _InMemoryCausalReconstructor:
    """Construye señales deterministas desde el prefijo PIT, sin DWT externa."""

    def reconstruct(
        self,
        origin: ForecastOrigin,
        snapshot: PointInTimeSnapshot,
        trm_monthly: pd.Series,
        plan: ResearchPlan,
    ) -> ReconstructionResult:
        vintage = snapshot.source(plan.target_series)
        prefix = trm_monthly.copy(deep=True)
        positions = np.arange(len(prefix), dtype=float)
        log_values = np.log(prefix.to_numpy(dtype=float))
        components: dict[str, pd.Series] = {}
        for index, name in enumerate(("D1", "D2", "D3", "D4", "D5", "A5"), start=1):
            values = (
                log_values * (1.0 + 0.001 * index)
                + 0.002 * index * positions
                + 0.02 * np.sin(positions / (index + 1.0) + index)
            )
            components[name] = pd.Series(values, index=prefix.index, name=name)

        signals: dict[str, pd.Series] = {}
        for candidate in plan.candidates:
            signal = components[candidate.components[0]].copy(deep=True)
            for component_name in candidate.components[1:]:
                signal = signal + components[component_name]
            signals[candidate.candidate_id] = signal * float(candidate.signal_scale)

        metadata = ReconstructionMetadata(
            origin_date=origin.origin_date,
            available_through=vintage.available_through,
            prefix_length=len(prefix),
            prefix_first_date=prefix.index[0],
            prefix_last_date=prefix.index[-1],
            prefix_sha256=hash_prefix(prefix),
            wavelet_family="db4",
            levels=5,
            boundary_mode="symmetric",
            dwt_max_level=5,
            uses_future_observations=False,
            source_vintage=vintage.vintage_id,
        )
        return ReconstructionResult(
            components=components,
            metadata=metadata,
            status="causal",
            signals=signals,
        )


@dataclass(frozen=True)
class _E2EFixture:
    plan: ResearchPlan
    panel: pd.Series
    resolver: _InMemorySnapshotResolver
    store: _InMemorySeriesStore
    reconstructor: _InMemoryCausalReconstructor
    config_path: Path
    schema_path: Path
    input_files: tuple[Path, ...]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_contracts(root: Path) -> tuple[Path, Path]:
    repository_root = Path(__file__).resolve().parents[1]
    for relative in ("pyproject.toml", "requirements.lock", "requirements-optional.lock"):
        source = repository_root / relative
        if source.is_file():
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    schemas = root / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    for source in (repository_root / "schemas").glob("*.json"):
        shutil.copy2(source, schemas / source.name)

    registry = root / "experiments" / "registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repository_root / "experiments" / "registry.json", registry)

    config = root / "research" / "configs" / "long_horizon_wavelet_optimization.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repository_root / "research" / "configs" / config.name, config)
    return config, schemas / "long_horizon_wavelet_optimization.json"


def _make_fixture(
    tmp_path: Path,
    *,
    include_missing_snapshot: bool = False,
) -> _E2EFixture:
    config_path, schema_path = _copy_contracts(tmp_path)
    origins = tuple(pd.date_range("2000-01-01", "2005-06-01", freq="MS")) + (
        _SCOREABLE_ORIGIN,
        _IMMATURE_ORIGIN,
    )
    if include_missing_snapshot:
        origins += (_MISSING_SNAPSHOT_ORIGIN,)
    panel_index = pd.date_range("2000-01-01", "2008-12-01", freq="MS")
    positions = np.arange(len(panel_index), dtype=float)
    panel = pd.Series(
        1_000.0
        + 0.4 * positions
        + 8.0 * np.sin(positions / 4.0)
        + 0.5 * np.cos(positions / 11.0),
        index=panel_index,
        name=BANREP_TRM_SOURCE_ID,
    )
    plan = load_research_plan(
        data_cutoff=_DATA_CUTOFF,
        origin_dates=origins,
    )

    fixture_root = tmp_path / "data" / "vintages" / "e2e"
    fixture_root.mkdir(parents=True, exist_ok=True)
    source_path = fixture_root / "trm.csv"
    panel.rename(BANREP_TRM_SOURCE_ID).to_csv(source_path, header=True)
    source_relative = ProjectPaths.from_root(tmp_path).relative(source_path)
    source_hash = _sha256(source_path)

    snapshots: dict[pd.Timestamp, PointInTimeSnapshot] = {}
    prefixes: dict[pd.Timestamp, pd.Series] = {}
    manifest_paths: list[Path] = []
    for origin in origins:
        if origin == _MISSING_SNAPSHOT_ORIGIN:
            continue
        manifest_path = fixture_root / origin.strftime("%Y-%m") / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps({"origin_date": origin.strftime("%Y-%m-%d"), "mode": "snapshot"}),
            encoding="utf-8",
        )
        manifest_relative = ProjectPaths.from_root(tmp_path).relative(manifest_path)
        forecast_origin = ForecastOrigin(
            origin_date=origin,
            data_cutoff=_DATA_CUTOFF,
            snapshot_manifest=manifest_relative,
        )
        vintage = SourceVintage(
            source_id=BANREP_TRM_SOURCE_ID,
            vintage_id=f"e2e-{origin:%Y%m}",
            snapshot_manifest=manifest_relative,
            archived_path=source_relative,
            available_through=origin,
            sha256=source_hash,
        )
        snapshots[origin] = PointInTimeSnapshot(
            origin=forecast_origin,
            source_vintages=(vintage,),
            manifest_sha256=_sha256(manifest_path),
        )
        prefixes[origin] = panel.loc[:origin].copy(deep=True)
        manifest_paths.append(manifest_path)

    return _E2EFixture(
        plan=plan,
        panel=panel,
        resolver=_InMemorySnapshotResolver(
            snapshots,
            missing_origin=_MISSING_SNAPSHOT_ORIGIN,
        ),
        store=_InMemorySeriesStore(prefixes),
        reconstructor=_InMemoryCausalReconstructor(),
        config_path=config_path,
        schema_path=schema_path,
        input_files=(source_path, *manifest_paths),
    )


def _run_fixture(fixture: _E2EFixture, tmp_path: Path):
    paths = ProjectPaths.from_root(tmp_path)
    recorder = ProvenanceRecorder(
        paths=paths,
        output_paths=OUTPUT_RELATIVE_PATHS,
        started_at=_STARTED_AT,
    )
    return wavelet_variant.run_wavelet_optimization(
        paths=paths,
        config_path=fixture.config_path,
        schema_path=fixture.schema_path,
        plan=fixture.plan,
        snapshot_resolver=fixture.resolver,
        series_store=fixture.store,
        origin_reconstructor=fixture.reconstructor,
        label_series=fixture.panel,
        metrics_calculator=MetricsCalculator.from_plan(fixture.plan),
        promotion_gate=PromotionGate.from_plan(fixture.plan),
        publisher=OutputPublisher(paths=paths),
        provenance_recorder=recorder,
        input_files=fixture.input_files,
        run_id=_RUN_ID,
        started_at=_STARTED_AT,
    )


def test_wavelet_optimization_runner_end_to_end_pit_fixture(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    historical_paths = (
        tmp_path / "results" / "pronostico" / "wavelets_comparacion_bandas.csv",
        tmp_path / "results" / "pronostico" / "wavelets_componentes.csv",
    )
    for historical_path in historical_paths:
        historical_path.parent.mkdir(parents=True, exist_ok=True)
        historical_path.write_bytes(b"historical fixture\n")
    historical_before = {path: path.read_bytes() for path in historical_paths}

    result = _run_fixture(fixture, tmp_path)
    assert result.plan.is_frozen
    assert result.plan.plan_hash == fixture.plan.plan_hash
    assert result.published_outputs == OUTPUT_RELATIVE_PATHS
    assert all((tmp_path / relative).is_file() for relative in OUTPUT_RELATIVE_PATHS)

    scoreable = [
        row
        for row in result.bundle.origin_predictions
        if row.origin_date == _SCOREABLE_ORIGIN
        and row.candidate_id == "db4_l5_sym_D1"
    ]
    assert {row.horizon_months for row in scoreable} == {6, 12}
    assert all(row.scoreability_status == SCOREABLE for row in scoreable)
    assert all(row.n_mature_labels >= 60 for row in scoreable)
    assert all(row.prediction_random_walk == 0.0 for row in scoreable)
    assert all(row.observed_forward_return is not None for row in scoreable)

    immature = [
        row
        for row in result.bundle.origin_predictions
        if row.origin_date == _IMMATURE_ORIGIN
        and row.candidate_id == "db4_l5_sym_D1"
    ]
    assert {row.horizon_months for row in immature} == {6, 12}
    assert all(row.scoreability_status == NOT_EVALUABLE_LABEL_NOT_MATURE for row in immature)
    assert all(row.label_end_date is not None and row.label_end_date > _DATA_CUTOFF for row in immature)
    assert all(row.observed_forward_return is None for row in immature)
    assert all(row.prediction_wavelet is None and row.prediction_random_walk is None for row in immature)

    full_metrics = [metric for metric in result.metrics if metric.split == "full"]
    assert full_metrics
    for metric in full_metrics:
        common_rows = [
            row
            for row in result.bundle.predictions
            if row.split == "full"
            and row.candidate_id == metric.candidate_id
            and row.horizon_months == metric.horizon_months
            and row.is_scoreable
        ]
        assert metric.n_oos == len(common_rows)
        assert all(row.prediction_random_walk == 0.0 for row in common_rows)

    coverage_rows = list(result.bundle.coverage)
    assert coverage_rows
    assert all(row["coverage_status"] == "complete" for row in coverage_rows)
    assert all("r2_oos" not in row for row in coverage_rows)

    assert result.promotion_gate["eligible"] is False
    assert result.promotion_gate["review_only"] is True
    assert result.promotion_gate["promotion_authorized"] is False
    assert result.promotion_gate["monthly_forecast_connected"] is False
    first_decision = result.promotion_gate["candidate_decisions"][0]
    coverage_condition = next(
        condition
        for condition in first_decision["conditions"]
        if condition["condition"] == "complete_pit_coverage"
    )
    assert coverage_condition["passed"] is True

    predictions_path = tmp_path / OUTPUT_RELATIVE_PATHS[0]
    evaluation_path = tmp_path / OUTPUT_RELATIVE_PATHS[1]
    coverage_path = tmp_path / OUTPUT_RELATIVE_PATHS[2]
    decision_path = tmp_path / OUTPUT_RELATIVE_PATHS[3]
    predictions_frame = pd.read_csv(predictions_path)
    evaluation_frame = pd.read_csv(evaluation_path)
    coverage_frame = pd.read_csv(coverage_path)
    assert tuple(predictions_frame.columns) == PREDICTION_COLUMNS
    assert tuple(evaluation_frame.columns) == EVALUATION_COLUMNS
    assert tuple(coverage_frame.columns) == COVERAGE_COLUMNS
    assert float(
        predictions_frame.loc[
            (predictions_frame["origin_date"] == _SCOREABLE_ORIGIN.strftime("%Y-%m-%d"))
            & (predictions_frame["candidate_id"] == "db4_l5_sym_D1")
            & (predictions_frame["horizon_months"] == 6),
            "prediction_random_walk",
        ].iloc[0]
    ) == 0.0
    assert "r2_oos" not in coverage_frame.columns
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["status"] == "research"
    assert decision["promotion_gate"]["review_only"] is True
    assert decision["monthly_forecast_connected"] is False
    assert decision["promotion_gate"]["eligible"] is False

    manifest_path = tmp_path / "artifacts" / "runs" / _RUN_ID / "manifest.json"
    assert result.manifest_path == manifest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variant = manifest["run_context"]["wavelet_optimization"]
    assert manifest["experiment_id"] == fixture.plan.experiment_id
    assert manifest["status"] == "success"
    assert variant["complete"] is True
    assert variant["status"] == "research"
    assert variant["product_id"] == "long_horizon_research"
    assert variant["plan_hash"] == fixture.plan.plan_hash
    assert set(variant["output_paths"]) == set(OUTPUT_RELATIVE_PATHS)
    assert variant["coverage_summary"]["n_missing"] == 0
    assert "monthly_forecast" not in " ".join(variant["output_paths"])
    assert set(record["path"] for record in manifest["output_files"]) == set(OUTPUT_RELATIVE_PATHS)

    assert {path: path.read_bytes() for path in historical_paths} == historical_before


def test_wavelet_optimization_runner_rejects_incomplete_required_coverage(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path, include_missing_snapshot=True)
    historical_paths = (
        tmp_path / "results" / "pronostico" / "wavelets_comparacion_bandas.csv",
        tmp_path / "results" / "pronostico" / "wavelets_componentes.csv",
    )
    for historical_path in historical_paths:
        historical_path.parent.mkdir(parents=True, exist_ok=True)
        historical_path.write_bytes(b"historical fixture\n")
    historical_before = {path: path.read_bytes() for path in historical_paths}

    with pytest.raises(
        wavelet_variant.WaveletOptimizationError,
        match="Cobertura PIT requerida incompleta o inválida",
    ):
        _run_fixture(fixture, tmp_path)

    output_paths = tuple(tmp_path / relative for relative in OUTPUT_RELATIVE_PATHS)
    assert all(not path.exists() for path in output_paths)

    manifest_path = tmp_path / "artifacts" / "runs" / _RUN_ID / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    variant = manifest["run_context"]["wavelet_optimization"]
    assert manifest["status"] == "failed"
    assert variant["complete"] is False
    assert "snapshot_manifest_missing" in manifest["error"]
    assert any(row["coverage_status"] == "missing" for row in variant["coverage"])
    assert {path: path.read_bytes() for path in historical_paths} == historical_before


def test_wavelet_optimization_runner_rejects_run_id_without_overwrite(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    _run_fixture(fixture, tmp_path)
    output_paths = tuple(tmp_path / relative for relative in OUTPUT_RELATIVE_PATHS)
    manifest_path = tmp_path / "artifacts" / "runs" / _RUN_ID / "manifest.json"
    before = {path: path.read_bytes() for path in (*output_paths, manifest_path)}

    with pytest.raises(wavelet_variant.RunIDConflict, match="no se sobrescribe"):
        _run_fixture(fixture, tmp_path)

    assert {path: path.read_bytes() for path in (*output_paths, manifest_path)} == before
    assert not list(
        (tmp_path / "results" / "pronostico" / "wavelet_optimization").glob("*.tmp")
    )
