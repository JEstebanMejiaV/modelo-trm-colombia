from __future__ import annotations

import hashlib
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st

from forecast_longterm.wavelet_optimization.config import (  # noqa: E402
    ResearchPlan,
    load_research_plan,
)
from forecast_longterm.wavelet_optimization.evaluation import (  # noqa: E402
    EvaluationBundle,
    OOS_Evaluator,
)
from forecast_longterm.wavelet_optimization.metrics import (  # noqa: E402
    MetricsCalculator,
)
from forecast_longterm.wavelet_optimization.provenance import (  # noqa: E402
    ProvenanceRecorder,
)
from forecast_longterm.wavelet_optimization.publishing import (  # noqa: E402
    OUTPUT_RELATIVE_PATHS,
    OutputPublisher,
    OutputVersionConflict,
)
from forecast_longterm.wavelet_optimization.reconstruction import (  # noqa: E402
    ReconstructionMetadata,
    ReconstructionResult,
    hash_prefix,
)
from forecast_longterm.wavelet_optimization.snapshots import (  # noqa: E402
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSnapshot,
    SourceVintage,
)
from trm_model.paths import ProjectPaths  # noqa: E402

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_DATA_CUTOFF = pd.Timestamp("2008-12-01")
_ORIGIN_DATES = tuple(
    pd.Timestamp(value)
    for value in pd.date_range("2006-11-01", "2006-12-01", freq="MS")
)
_PANEL_DATES = pd.date_range("2000-01-01", _DATA_CUTOFF, freq="MS")
_VOLATILE_KEYS = frozenset(
    {
        "run_id",
        "Run_ID",
        "started_at",
        "finished_at",
        "started_at_utc",
        "finished_at_utc",
        "timestamp",
        "timestamp_utc",
    }
)


@dataclass(frozen=True)
class _PITFixture:
    plan: ResearchPlan
    panel: pd.Series
    snapshots: tuple[PointInTimeSnapshot, ...]
    prefixes: Mapping[pd.Timestamp, pd.Series]
    seed: int


class _InMemorySnapshotResolver:
    def __init__(self, snapshots: tuple[PointInTimeSnapshot, ...]) -> None:
        self._snapshots = {
            snapshot.origin.origin_date: snapshot for snapshot in snapshots
        }

    def resolve(
        self,
        origin: ForecastOrigin,
        required_source_ids: tuple[str, ...],
    ) -> PointInTimeSnapshot:
        snapshot = self._snapshots[origin.origin_date]
        for source_id in required_source_ids:
            snapshot.source(source_id)
        return snapshot


class _InMemorySeriesStore:
    def __init__(self, prefixes: Mapping[pd.Timestamp, pd.Series]) -> None:
        self._prefixes = prefixes

    def monthly_series(
        self,
        snapshot: PointInTimeSnapshot,
        source_id: str,
        *,
        through: pd.Timestamp,
    ) -> pd.Series:
        if source_id != BANREP_TRM_SOURCE_ID:
            raise KeyError(source_id)
        return self._prefixes[snapshot.origin.origin_date].copy(deep=True)


class _InMemoryCausalReconstructor:
    """Reconstructor determinista que materializa una fixture PIT en memoria.

    Property 10 verifica reproducibilidad de evaluación/publicación, no la DWT
    (cubierta por Property 2). Este adaptador conserva la interfaz y metadata
    causal del reconstructor para que la propiedad ejerza los contratos OOS,
    provenance y outputs sin crear archivos ni depender de un proveedor.
    """

    def reconstruct(
        self,
        origin: ForecastOrigin,
        snapshot: PointInTimeSnapshot,
        trm_monthly: pd.Series,
        plan: ResearchPlan,
    ) -> ReconstructionResult:
        prefix = trm_monthly.copy(deep=True)
        vintage = snapshot.source(plan.target_series)
        positions = np.arange(len(prefix), dtype=float)
        log_values = np.log(prefix.to_numpy(dtype=float))
        component_names = ("D1", "D2", "D3", "D4", "D5", "A5")
        components: dict[str, pd.Series] = {}
        for index, name in enumerate(component_names, start=1):
            values = (
                log_values * (1.0 + 0.001 * index)
                + 0.01 * index * positions
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


def _digest(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _fixture(seed: int) -> _PITFixture:
    generator = np.random.default_rng(seed)
    shocks = generator.normal(loc=0.0, scale=0.002, size=len(_PANEL_DATES))
    positions = np.arange(len(_PANEL_DATES), dtype=float)
    log_values = (
        np.log(1000.0)
        + np.cumsum(shocks)
        + 0.0002 * positions
        + 0.01 * np.sin(positions / 5.0)
    )
    panel = pd.Series(
        np.exp(log_values),
        index=_PANEL_DATES,
        name=BANREP_TRM_SOURCE_ID,
    )
    plan = load_research_plan(
        data_cutoff=_DATA_CUTOFF,
        origin_dates=_ORIGIN_DATES,
    )

    snapshots: list[PointInTimeSnapshot] = []
    prefixes: dict[pd.Timestamp, pd.Series] = {}
    for origin in _ORIGIN_DATES:
        origin_text = origin.strftime("%Y-%m-%d")
        manifest_path = f"data/vintages/pbt/{origin_text}/manifest.json"
        vintage = SourceVintage(
            source_id=BANREP_TRM_SOURCE_ID,
            vintage_id=f"pbt-{seed}-{origin:%Y%m}",
            snapshot_manifest=manifest_path,
            archived_path=f"data/vintages/pbt/{origin_text}/trm.csv",
            available_through=origin,
            sha256=_digest("source", seed, origin_text),
        )
        forecast_origin = ForecastOrigin(
            origin_date=origin,
            data_cutoff=_DATA_CUTOFF,
            snapshot_manifest=manifest_path,
        )
        snapshots.append(
            PointInTimeSnapshot(
                origin=forecast_origin,
                source_vintages=(vintage,),
                manifest_sha256=_digest("manifest", seed, origin_text),
            )
        )
        prefixes[origin] = panel.loc[:origin].copy(deep=True)

    return _PITFixture(
        plan=plan,
        panel=panel,
        snapshots=tuple(snapshots),
        prefixes=prefixes,
        seed=seed,
    )


def _fixture_with_input_change(fixture: _PITFixture) -> _PITFixture:
    """Devuelve la misma corrida con contenido PIT y hashes de input distintos."""

    changed_panel = fixture.panel.copy(deep=True)
    changed_panel.iloc[0] = float(changed_panel.iloc[0]) * 1.001
    changed_prefixes: dict[pd.Timestamp, pd.Series] = {}
    for origin, prefix in fixture.prefixes.items():
        changed_prefix = prefix.copy(deep=True)
        changed_prefix.iloc[0] = float(changed_prefix.iloc[0]) * 1.001
        changed_prefixes[origin] = changed_prefix

    changed_snapshots: list[PointInTimeSnapshot] = []
    for snapshot in fixture.snapshots:
        origin_text = snapshot.origin.origin_date.strftime("%Y-%m-%d")
        changed_vintages = tuple(
            replace(
                vintage,
                vintage_id=f"{vintage.vintage_id}-input-change",
                sha256=_digest("changed-source", fixture.seed, origin_text),
            )
            for vintage in snapshot.source_vintages
        )
        changed_snapshots.append(
            replace(
                snapshot,
                source_vintages=changed_vintages,
                manifest_sha256=_digest("changed-manifest", fixture.seed, origin_text),
            )
        )

    return _PITFixture(
        plan=fixture.plan,
        panel=changed_panel,
        snapshots=tuple(changed_snapshots),
        prefixes=changed_prefixes,
        seed=fixture.seed,
    )


def _fixture_with_plan_change(fixture: _PITFixture) -> _PITFixture:
    """Devuelve un plan válido con un cutoff distinto y, por tanto, otro hash."""

    changed_plan = load_research_plan(
        data_cutoff=pd.Timestamp("2007-06-01"),
        origin_dates=fixture.plan.origin_dates,
    )
    return _PITFixture(
        plan=changed_plan,
        panel=fixture.panel,
        snapshots=fixture.snapshots,
        prefixes=fixture.prefixes,
        seed=fixture.seed,
    )


def _hash_payload(manifest: Mapping[str, Any], documents: Any) -> dict[str, Any]:
    """Extrae hashes comparables sin incluir identidad ni tiempos de corrida."""

    variant = manifest["run_context"]["wavelet_optimization"]
    return {
        "plan_hash": variant["plan_hash"],
        "snapshot_manifest_hashes": tuple(
            (row["origin_date"], row.get("manifest_sha256"))
            for row in variant["snapshots"]
        ),
        "source_vintage_hashes": tuple(
            (
                row["origin_date"],
                row["source_id"],
                row.get("vintage_id"),
                row.get("sha256"),
                row.get("manifest_sha256"),
            )
            for row in variant["source_vintages"]
        ),
        "prefix_hashes": tuple(
            row.get("prefix_sha256") for row in documents.predictions
        ),
        "coverage_hashes": tuple(row.get("sha256") for row in documents.coverage),
    }


def _bundle_with_plan_change(
    bundle: EvaluationBundle,
    plan: ResearchPlan,
) -> EvaluationBundle:
    """Ajusta el cutoff serializable sin repetir una evaluación completa."""

    predictions = tuple(
        replace(row, data_cutoff=plan.data_cutoff) for row in bundle.predictions
    )
    return EvaluationBundle(
        predictions=predictions,
        coverage=bundle.coverage,
        metrics=bundle.metrics,
        decisions=bundle.decisions,
        plan=plan,
    )


def _manifest_with_input_change(
    manifest: Mapping[str, Any],
    fixture: _PITFixture,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Cambia la identidad de los snapshots sin repetir el hash del árbol."""

    changed = deepcopy(dict(manifest))
    changed["run_id"] = run_id
    context = changed["run_context"]
    variant = context["wavelet_optimization"]
    variant["run_id"] = run_id
    for snapshot_record in variant["snapshots"]:
        origin_text = snapshot_record["origin_date"]
        snapshot_record["manifest_sha256"] = _digest(
            "changed-manifest", fixture.seed, origin_text
        )
        for vintage_record in snapshot_record.get("source_vintages", ()):
            vintage_record["vintage_id"] = (
                f"{vintage_record.get('vintage_id')}-input-change"
            )
            vintage_record["sha256"] = _digest(
                "changed-source", fixture.seed, origin_text
            )
            vintage_record["manifest_sha256"] = snapshot_record["manifest_sha256"]
    for vintage_record in variant["source_vintages"]:
        origin_text = vintage_record["origin_date"]
        vintage_record["vintage_id"] = f"{vintage_record.get('vintage_id')}-input-change"
        vintage_record["sha256"] = _digest(
            "changed-source", fixture.seed, origin_text
        )
        vintage_record["manifest_sha256"] = _digest(
            "changed-manifest", fixture.seed, origin_text
        )
    variant["vintages"] = deepcopy(variant["source_vintages"])
    context["wavelet_optimization"] = variant
    return changed


def _manifest_with_plan_change(
    manifest: Mapping[str, Any],
    plan: ResearchPlan,
    *,
    run_id: str,
) -> dict[str, Any]:
    """Actualiza solo la identidad derivada del plan para una corrida nueva."""

    changed = deepcopy(dict(manifest))
    changed["run_id"] = run_id
    cutoff = pd.Timestamp(plan.data_cutoff).strftime("%Y-%m-%d")
    context = changed["run_context"]
    variant = context["wavelet_optimization"]
    variant["run_id"] = run_id
    variant["plan_hash"] = plan.plan_hash
    variant["data_cutoff"] = cutoff
    context["plan_hash"] = plan.plan_hash
    context["data_cutoff"] = cutoff
    context["wavelet_optimization"] = variant
    return changed


def _evaluate_fixture(fixture: _PITFixture) -> EvaluationBundle:
    evaluator = OOS_Evaluator(
        snapshot_resolver=_InMemorySnapshotResolver(fixture.snapshots),
        series_store=_InMemorySeriesStore(fixture.prefixes),
        origin_reconstructor=_InMemoryCausalReconstructor(),
    )
    bundle = evaluator.evaluate(fixture.plan, label_series=fixture.panel)
    metrics = MetricsCalculator.from_plan(fixture.plan).calculate(
        bundle,
        plan=fixture.plan,
    )
    return replace(bundle, metrics=metrics, plan=fixture.plan)


def _manifest_for_run(
    fixture: _PITFixture,
    bundle: EvaluationBundle,
    *,
    run_id: str,
    started_at: datetime,
) -> dict[str, Any]:
    recorder = ProvenanceRecorder(
        paths=ProjectPaths.from_root(_REPOSITORY_ROOT),
        output_paths=OUTPUT_RELATIVE_PATHS,
        snapshots=fixture.snapshots,
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
    )
    return recorder.build_manifest(
        fixture.plan,
        bundle,
        run_id=run_id,
        complete=False,
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
    )


def _manifest_with_execution_change(
    manifest: Mapping[str, Any],
    *,
    run_id: str,
    started_at: datetime,
) -> dict[str, Any]:
    """Cambia solo Run_ID/tiempos para comparar dos ejecuciones equivalentes."""

    changed = deepcopy(dict(manifest))
    finished_at = started_at + timedelta(minutes=1)
    start_text = started_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    finish_text = finished_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    changed["run_id"] = run_id
    changed["started_at_utc"] = start_text
    changed["finished_at_utc"] = finish_text
    variant = changed["run_context"]["wavelet_optimization"]
    variant["run_id"] = run_id
    variant["started_at_utc"] = start_text
    variant["finished_at_utc"] = finish_text
    return changed


def _without_volatile(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _without_volatile(item)
            for key, item in value.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(value, tuple):
        return tuple(_without_volatile(item) for item in value)
    if isinstance(value, list):
        return [_without_volatile(item) for item in value]
    return value


def _documents_payload(documents: Any) -> dict[str, Any]:
    return {
        "relative_paths": tuple(documents.relative_paths),
        "predictions": tuple(
            _without_volatile(row) for row in documents.predictions
        ),
        "evaluation": tuple(_without_volatile(row) for row in documents.evaluation),
        "coverage": tuple(_without_volatile(row) for row in documents.coverage),
        "decision": _without_volatile(documents.decision),
    }


def _assert_row_keys_and_order(left: Any, right: Any, field: str, key_fields: tuple[str, ...]) -> None:
    left_rows = getattr(left, field)
    right_rows = getattr(right, field)
    assert [tuple(row) for row in left_rows] == [tuple(row) for row in right_rows]
    assert [
        tuple(row.get(key) for key in key_fields) for row in left_rows
    ] == [tuple(row.get(key) for key in key_fields) for row in right_rows]


# Feature: long-horizon-wavelet-optimization, Property 10: Corridas comparables son reproducibles
# **Validates: Requirements 9.5**
@settings(max_examples=5, deadline=None, database=None)
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
def test_comparable_pit_runs_are_reproducible(
    seed: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    fixture = _fixture(seed)
    first_bundle = _evaluate_fixture(fixture)
    second_bundle = _evaluate_fixture(fixture)

    first_state = first_bundle.as_dict()
    second_state = second_bundle.as_dict()
    # La evaluación conserva records, coverage, métricas, decisiones, claves y
    # orden sin introducir identidad de corrida ni tiempos.
    assert first_state == second_state
    assert first_state["predictions"] == second_state["predictions"]
    assert first_state["coverage"] == second_state["coverage"]
    assert first_state["metrics"] == second_state["metrics"]
    assert first_state["decisions"] == second_state["decisions"]
    assert [row.key for row in first_bundle.predictions] == [
        row.key for row in second_bundle.predictions
    ]
    assert [tuple(row.as_dict()) for row in first_bundle.predictions] == [
        tuple(row.as_dict()) for row in second_bundle.predictions
    ]

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=seed % 1000
    )
    first_manifest = _manifest_for_run(
        fixture,
        first_bundle,
        run_id=f"pbt-{seed}-a",
        started_at=base_time,
    )
    second_manifest = _manifest_with_execution_change(
        first_manifest,
        run_id=f"pbt-{seed}-b",
        started_at=base_time + timedelta(seconds=1),
    )
    assert _without_volatile(first_manifest) == _without_volatile(second_manifest)

    publisher = OutputPublisher(require_complete_provenance=False)
    first_documents = publisher.build_documents(
        fixture.plan,
        first_bundle,
        first_manifest,
    )
    second_documents = publisher.build_documents(
        fixture.plan,
        second_bundle,
        second_manifest,
    )

    first_hashes = _hash_payload(first_manifest, first_documents)
    second_hashes = _hash_payload(second_manifest, second_documents)
    assert first_hashes == second_hashes
    assert first_hashes["plan_hash"] == fixture.plan.plan_hash
    assert first_documents.decision["plan_hash"] == fixture.plan.plan_hash
    assert _documents_payload(first_documents) == _documents_payload(second_documents)
    _assert_row_keys_and_order(
        first_documents,
        second_documents,
        "predictions",
        ("origin_date", "horizon_months", "candidate_id", "split"),
    )
    _assert_row_keys_and_order(
        first_documents,
        second_documents,
        "evaluation",
        ("candidate_id", "horizon_months", "split"),
    )
    _assert_row_keys_and_order(
        first_documents,
        second_documents,
        "coverage",
        ("origin_date", "horizon_months", "source_id"),
    )
    assert _without_volatile(first_documents.decision) == _without_volatile(
        second_documents.decision
    )

    # Un cambio de input debe quedar visible en los hashes y un cambio de plan
    # debe producir un plan_hash distinto antes de publicar. Se clonan los
    # manifests mutados para no repetir el costoso hash del árbol de código.
    changed_input_fixture = _fixture_with_input_change(fixture)
    changed_input_manifest = _manifest_with_input_change(
        first_manifest,
        changed_input_fixture,
        run_id=f"pbt-{seed}-input",
    )
    changed_input_documents = publisher.build_documents(
        changed_input_fixture.plan,
        first_bundle,
        changed_input_manifest,
    )
    changed_input_hashes = _hash_payload(
        changed_input_manifest,
        changed_input_documents,
    )
    assert changed_input_hashes["source_vintage_hashes"] != first_hashes[
        "source_vintage_hashes"
    ]
    assert changed_input_hashes["snapshot_manifest_hashes"] != first_hashes[
        "snapshot_manifest_hashes"
    ]

    changed_plan_fixture = _fixture_with_plan_change(fixture)
    changed_plan_bundle = _bundle_with_plan_change(
        first_bundle,
        changed_plan_fixture.plan,
    )
    changed_plan_manifest = _manifest_with_plan_change(
        first_manifest,
        changed_plan_fixture.plan,
        run_id=f"pbt-{seed}-plan",
    )
    changed_plan_documents = publisher.build_documents(
        changed_plan_fixture.plan,
        changed_plan_bundle,
        changed_plan_manifest,
    )
    changed_plan_hashes = _hash_payload(changed_plan_manifest, changed_plan_documents)
    assert changed_plan_fixture.plan.plan_hash != fixture.plan.plan_hash
    assert changed_plan_hashes["plan_hash"] != first_hashes["plan_hash"]
    assert changed_plan_documents.decision["plan_hash"] != first_documents.decision[
        "plan_hash"
    ]
    assert _documents_payload(changed_plan_documents) != _documents_payload(
        first_documents
    )

    # Una corrida distinta no puede reemplazar outputs ya versionados; los
    # históricos permanecen intactos aunque cambien inputs o plan.
    publish_root = tmp_path_factory.mktemp(f"property10-{seed}")
    publish_paths = ProjectPaths.from_root(publish_root)
    historical_paths = (
        publish_paths.results / "pronostico" / "wavelets_comparacion_bandas.csv",
        publish_paths.results / "pronostico" / "wavelets_componentes.csv",
    )
    for historical_path in historical_paths:
        historical_path.parent.mkdir(parents=True, exist_ok=True)
        historical_path.write_bytes(b"historical fixture\\n")
    historical_before = {
        path: path.read_bytes() for path in historical_paths
    }

    isolated_publisher = OutputPublisher(
        paths=publish_paths,
        require_complete_provenance=False,
    )
    isolated_publisher.publish(fixture.plan, first_bundle, first_manifest)
    published_before = {
        publish_paths.resolve(relative): publish_paths.resolve(relative).read_bytes()
        for relative in OUTPUT_RELATIVE_PATHS
    }
    for changed_fixture, changed_bundle, changed_manifest in (
        (changed_input_fixture, first_bundle, changed_input_manifest),
        (changed_plan_fixture, changed_plan_bundle, changed_plan_manifest),
    ):
        with pytest.raises(OutputVersionConflict):
            isolated_publisher.publish(
                changed_fixture.plan,
                changed_bundle,
                changed_manifest,
            )

    assert {
        publish_paths.resolve(relative): publish_paths.resolve(relative).read_bytes()
        for relative in OUTPUT_RELATIVE_PATHS
    } == published_before
    assert {path: path.read_bytes() for path in historical_paths} == historical_before
    assert not list(
        (publish_root / "results" / "pronostico" / "wavelet_optimization").glob(
            "*.tmp"
        )
    )
