"""Entry point y orquestador de la investigación wavelet point-in-time.

La variante vive deliberadamente fuera del runner de productos legacy. Este
módulo compone las primitivas de ``forecast_longterm.wavelet_optimization``
(configuración, snapshots, reconstrucción, etiquetas, evaluación, métricas,
gate, provenance y publicación) sin leer ``forecast_longterm.wavelets`` ni
conectar el producto ``monthly_forecast``.

El runner no infiere fechas, no construye un dataset ``latest_available`` y no
usa ningún output histórico como entrada. Una corrida normal sigue este orden:

1. cargar y congelar un ``ResearchPlan`` con ``Data_Cutoff`` y orígenes
   explícitos;
2. ejecutar la evaluación PIT con un resolver/store estrictos;
3. calcular métricas y ranking sobre la muestra común;
4. evaluar el ``PromotionGate`` únicamente como elegibilidad de revisión;
5. construir provenance antes de publicar, publicar exactamente cuatro rutas y
   finalmente escribir el manifest completo por ``Run_ID``.

El archivo comparte nombre con el namespace de submódulos
``forecast_longterm/wavelet_optimization/``. Cuando Python carga este entry
point como módulo, ``__path__`` se expone para conservar la compatibilidad de
los imports existentes como ``forecast_longterm.wavelet_optimization.config``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ``wavelet_optimization`` already existed as a namespace package containing
# the component modules. The entry point is now a sibling module with the same
# public name; exposing the directory as ``__path__`` keeps both contracts
# usable without adding a second package initializer or changing imports in the
# component modules.
_SUBMODULE_DIRECTORY = Path(__file__).with_name("wavelet_optimization")
if _SUBMODULE_DIRECTORY.is_dir():
    __path__ = [str(_SUBMODULE_DIRECTORY)]  # type: ignore[name-defined]

if __package__ in (None, ""):  # pragma: no cover - only direct-file execution
    _SRC_DIRECTORY = Path(__file__).resolve().parents[1]
    if str(_SRC_DIRECTORY) not in sys.path:
        sys.path.insert(0, str(_SRC_DIRECTORY))

# Ruff treats these imports as late because the namespace shim above must run
# first so ``forecast_longterm.wavelet_optimization`` can expose its submodules.
# ruff: noqa: E402
from forecast_longterm.wavelet_optimization.config import (
    DEFAULT_VARIANT_CONFIG,
    DEFAULT_VARIANT_SCHEMA,
    PreRegistrationGuard,
    ResearchPlan,
    load_research_plan,
)
from forecast_longterm.wavelet_optimization.evaluation import (
    EvaluationBundle,
    OOS_Evaluator,
)
from forecast_longterm.wavelet_optimization.ingestion import load_outcome_panel
from forecast_longterm.wavelet_optimization.labels import ForwardLabelBuilder
from forecast_longterm.wavelet_optimization.metrics import (
    EvaluationMetrics,
    MetricsCalculator,
    rank_metrics,
)
from forecast_longterm.wavelet_optimization.promotion import PromotionGate
from forecast_longterm.wavelet_optimization.provenance import ProvenanceRecorder
from forecast_longterm.wavelet_optimization.publishing import (
    OUTPUT_RELATIVE_PATHS,
    OutputPublisher,
)
from forecast_longterm.wavelet_optimization.reconstruction import OriginReconstructor
from forecast_longterm.wavelet_optimization.snapshots import (
    BANREP_TRM_SOURCE_ID,
    CoverageLedger,
    ForecastOrigin,
    PointInTimeSeriesStore,
    SnapshotResolver,
)
from trm_model.paths import ProjectPaths, project_paths
from trm_model.provenance.manifest import make_run_id, utc_now

_UNSET = object()


class WaveletOptimizationError(RuntimeError):
    """Error de composición de la variante wavelet."""


class RunIDConflict(WaveletOptimizationError):
    """El ``Run_ID`` solicitado ya tiene una carpeta de manifest."""


class RunnerContractError(WaveletOptimizationError):
    """Una dependencia inyectada no satisface el contrato del runner."""


@dataclass(frozen=True)
class WaveletOptimizationResult:
    """Resultado completo y auditable de una corrida de investigación."""

    run_id: str
    plan: ResearchPlan
    bundle: EvaluationBundle
    metrics: tuple[EvaluationMetrics, ...]
    ranking: tuple[EvaluationMetrics, ...]
    promotion_gate: Mapping[str, object]
    manifest: Mapping[str, object]
    manifest_path: Path
    published_outputs: tuple[str, ...]

    @property
    def gate_decision(self) -> Mapping[str, object]:
        """Alias legible para el resultado de elegibilidad metodológica."""

        return self.promotion_gate

    @property
    def output_paths(self) -> tuple[str, ...]:
        """Alias del conjunto exacto de cuatro outputs publicados."""

        return self.published_outputs


# Nombres alternativos para callers que prefieren un resultado genérico.
RunResult = WaveletOptimizationResult
ResearchRunResult = WaveletOptimizationResult


def _as_project_paths(value: ProjectPaths | Path | str | None) -> ProjectPaths:
    if isinstance(value, ProjectPaths):
        return value
    return project_paths(None if value is None else Path(value))


def _utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_run_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise RunnerContractError("Run_ID no puede estar vacío")
    if text in {".", ".."} or "/" in text or "\\" in text:
        raise RunnerContractError("Run_ID no puede contener separadores de ruta")
    return text


def _unique_run_id(
    paths: ProjectPaths,
    *,
    started_at: datetime,
    requested: str | None,
) -> str:
    """Devuelve un Run_ID no usado sin cambiar la identidad de la variante.

    ``make_run_id`` conserva el formato común del repositorio. Si dos llamadas
    ocurren en el mismo segundo, se incrementa únicamente el instante usado
    para generar la identidad hasta encontrar una carpeta libre; los valores
    científicos de la corrida no dependen de este ajuste.
    """

    if requested is not None:
        run_id = _safe_run_id(requested)
        if paths.run_directory(run_id).exists():
            raise RunIDConflict(
                f"Ya existe una carpeta para Run_ID={run_id!r}; no se sobrescribe."
            )
        return run_id

    base = _utc_datetime(started_at)
    for offset in range(10_000):
        candidate_time = base + timedelta(microseconds=offset)
        candidate = make_run_id(
            started_at=candidate_time,
            product_id="long_horizon_research",
        )
        if not paths.run_directory(candidate).exists():
            return candidate
    raise RunIDConflict("No se pudo generar un Run_ID único después de 10.000 intentos")


def _path_argument(
    value: str | Path | None,
    *,
    default: Path,
    paths: ProjectPaths,
) -> Path:
    if value is None:
        return paths.root / default
    path = Path(value)
    return path if path.is_absolute() else paths.root / path


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    for method_name in ("as_dict", "to_dict", "to_record"):
        method = getattr(value, method_name, None)
        if callable(method):
            converted = method()
            if isinstance(converted, Mapping):
                return converted
    raise RunnerContractError(f"{field_name} debe ser un mapping o un objeto serializable")


def _required_coverage_errors(bundle: EvaluationBundle) -> tuple[str, ...]:
    """Impide publicar una corrida con cobertura PIT requerida inválida."""

    rows = tuple(bundle.coverage)
    if not rows:
        return ("coverage_missing",)
    errors: list[str] = []
    for index, value in enumerate(rows):
        row = _mapping(value, field_name="coverage record")
        required = row.get("required_for_candidate", True)
        status = str(row.get("coverage_status", "complete"))
        if bool(required) and status != "complete":
            source_id = row.get("source_id", "unknown")
            origin_date = row.get("origin_date", "unknown")
            horizon = row.get("horizon_months", "unknown")
            reason = row.get("reason", "coverage_not_complete")
            errors.append(
                f"coverage[{index}]={source_id}/{origin_date}/h{horizon}:"
                f"{status}:{reason}"
            )
    return tuple(errors)


def _json_safe(value: Any) -> Any:
    """Convierte métricas y decisiones a un árbol estable para provenance."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (AttributeError, TypeError, ValueError):
            pass
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return str(value)
    return value


class _RecordingSnapshotResolver:
    """Adaptador que conserva cada snapshot resuelto para provenance.

    La evaluación sigue siendo la dueña de la resolución: este adaptador no
    crea snapshots ni sustituye una excepción por otra fuente. Solo registra
    los objetos que el resolver autorizado devuelve.
    """

    def __init__(self, delegate: Any, coverage_ledger: CoverageLedger) -> None:
        self.delegate = delegate
        self.coverage_ledger = coverage_ledger
        self._snapshots: dict[Any, Any] = {}

    def resolve(
        self,
        origin: ForecastOrigin,
        required_source_ids: tuple[str, ...] = (BANREP_TRM_SOURCE_ID,),
    ) -> Any:
        method = getattr(self.delegate, "resolve", None)
        if not callable(method):
            raise RunnerContractError("snapshot_resolver debe exponer resolve()")
        try:
            snapshot = method(origin, required_source_ids)
        except TypeError as first_error:
            # Compatibilidad con adaptadores antiguos de la interfaz; no es un
            # fallback de datos y no cambia la fuente requerida.
            try:
                snapshot = method(origin)
            except TypeError:
                raise first_error
        origin_date = getattr(origin, "origin_date", origin)
        self._snapshots[origin_date] = snapshot
        return snapshot

    @property
    def snapshots(self) -> tuple[Any, ...]:
        return tuple(
            self._snapshots[key]
            for key in sorted(self._snapshots, key=lambda value: str(value))
        )


class WaveletOptimizationRunner:
    """Compone una corrida PIT completa sin tocar productos históricos."""

    def __init__(
        self,
        *,
        paths: ProjectPaths | Path | str | None = None,
        config_path: str | Path | None = None,
        schema_path: str | Path | None = None,
        snapshot_resolver: Any | None = None,
        series_store: Any | None = None,
        origin_reconstructor: Any | None = None,
        label_builder: Any | None = None,
        evaluator: Any | None = None,
        metrics_calculator: Any | None = None,
        promotion_gate: Any | None = None,
        publisher: Any | None = None,
        provenance_recorder: Any | None = None,
        input_files: Iterable[str | Path] = (),
    ) -> None:
        self.paths = _as_project_paths(paths)
        self.config_path = config_path
        self.schema_path = schema_path
        self.snapshot_resolver = snapshot_resolver
        self.series_store = series_store
        self.origin_reconstructor = origin_reconstructor
        self.label_builder = label_builder
        self.evaluator = evaluator
        self.metrics_calculator = metrics_calculator
        self.promotion_gate = promotion_gate
        self.publisher = publisher
        self.provenance_recorder = provenance_recorder
        self.input_files = tuple(input_files)

    def _load_plan(
        self,
        *,
        plan: ResearchPlan | None,
        data_cutoff: Any,
        origin_dates: Iterable[Any] | Any,
    ) -> tuple[ResearchPlan, Path, Path]:
        config_path = _path_argument(
            self.config_path,
            default=DEFAULT_VARIANT_CONFIG,
            paths=self.paths,
        )
        schema_path = _path_argument(
            self.schema_path,
            default=DEFAULT_VARIANT_SCHEMA,
            paths=self.paths,
        )
        if plan is None:
            kwargs: dict[str, Any] = {
                "path": config_path,
                "schema_path": schema_path,
                "root": self.paths.root,
            }
            if data_cutoff is not _UNSET:
                kwargs["data_cutoff"] = data_cutoff
            if origin_dates is not _UNSET:
                kwargs["origin_dates"] = origin_dates
            loaded = load_research_plan(**kwargs)
        else:
            if not isinstance(plan, ResearchPlan):
                raise RunnerContractError("plan debe ser ResearchPlan")
            # Revalidar el mismo objeto conserva su canonicalización/hash; no
            # se crea una copia con un hash distinto para la ejecución.
            loaded = plan.freeze()
        if not loaded.is_frozen or not loaded.plan_hash:
            raise RunnerContractError("ResearchPlan debe quedar congelado con plan_hash")
        loaded.validate()
        return loaded, config_path, schema_path

    def _new_dependencies(
        self,
        plan: ResearchPlan,
    ) -> tuple[_RecordingSnapshotResolver, Any, Any, Any, CoverageLedger]:
        ledger = CoverageLedger(default_horizons=plan.horizons)
        resolver = self.snapshot_resolver
        if resolver is None:
            resolver = SnapshotResolver(
                paths=self.paths,
                coverage_ledger=ledger,
                horizons=plan.horizons,
            )
        recording_resolver = _RecordingSnapshotResolver(resolver, ledger)

        store = self.series_store
        if store is None:
            store = PointInTimeSeriesStore(
                paths=self.paths,
                coverage_ledger=ledger,
                horizons=plan.horizons,
            )
        reconstructor = self.origin_reconstructor or OriginReconstructor()
        label_builder = self.label_builder or ForwardLabelBuilder.from_plan(plan)
        return recording_resolver, store, reconstructor, label_builder, ledger

    @staticmethod
    def _bundle_with_contract(
        bundle: Any,
        *,
        plan: ResearchPlan,
        metrics: Iterable[EvaluationMetrics] = (),
        decisions: Iterable[Mapping[str, object]] = (),
    ) -> EvaluationBundle:
        if isinstance(bundle, EvaluationBundle):
            return replace(
                bundle,
                metrics=tuple(metrics),
                decisions=tuple(dict(item) for item in decisions),
                plan=plan,
            )
        predictions = getattr(bundle, "predictions", ())
        coverage = getattr(bundle, "coverage", ())
        if callable(predictions):
            predictions = predictions()
        if callable(coverage):
            coverage = coverage()
        return EvaluationBundle(
            predictions=tuple(predictions),
            coverage=tuple(coverage),
            metrics=tuple(metrics),
            decisions=tuple(dict(item) for item in decisions),
            plan=plan,
        )

    @staticmethod
    def _call_evaluator(
        evaluator: Any,
        plan: ResearchPlan,
        *,
        label_series: Any,
    ) -> Any:
        method = getattr(evaluator, "evaluate", None)
        if not callable(method):
            method = getattr(evaluator, "evaluate_walk_forward", None)
        if not callable(method):
            raise RunnerContractError("evaluator debe exponer evaluate()")
        if label_series is None:
            return method(plan)
        try:
            return method(plan, label_series=label_series)
        except TypeError as first_error:
            # Adaptador compatible con la firma antigua que llama al panel
            # ``trm_monthly`` en vez de ``label_series``.
            try:
                return method(plan, trm_monthly=label_series)
            except TypeError:
                raise first_error

    @staticmethod
    def _call_gate(
        gate: Any,
        plan: ResearchPlan,
        metrics: tuple[EvaluationMetrics, ...],
        bundle: EvaluationBundle,
        manifest: Mapping[str, object],
    ) -> Mapping[str, object]:
        method = getattr(gate, "evaluate", None)
        if not callable(method):
            method = getattr(gate, "assess", None)
        if callable(method):
            try:
                result = method(plan, metrics, bundle.coverage, manifest)
            except TypeError as first_error:
                try:
                    result = method(plan, bundle, bundle.coverage, manifest)
                except TypeError:
                    raise first_error
        elif callable(gate):
            result = gate(plan, metrics, bundle.coverage, manifest)
        else:
            raise RunnerContractError("promotion_gate debe exponer evaluate()")
        if not isinstance(result, Mapping):
            result = _mapping(result, field_name="promotion_gate")
        return dict(result)

    @staticmethod
    def _normalise_gate(
        result: Mapping[str, object],
        *,
        plan: ResearchPlan,
    ) -> dict[str, object]:
        value = dict(result)
        for key, expected in (
            ("product_id", plan.product_id),
            ("status", plan.status),
            ("promotion_authorized", False),
            ("monthly_forecast_connected", False),
        ):
            if key in value and value[key] != expected:
                raise RunnerContractError(
                    f"PromotionGate intentó alterar {key}: {value[key]!r} != {expected!r}"
                )
            value[key] = expected
        value.setdefault("schema_version", 1)
        value.setdefault("gate", "promotion_eligibility")
        value.setdefault("eligibility_scope", "methodological_review")
        value["research_only"] = True
        value["review_only"] = True
        value["requires_independent_methodological_review"] = True
        decisions = value.get("candidate_decisions", value.get("decisions", ()))
        if isinstance(decisions, Mapping):
            decisions = tuple(decisions.values())
        if decisions is None:
            decisions = ()
        if not isinstance(decisions, (list, tuple)):
            raise RunnerContractError("candidate_decisions del gate debe ser una colección")
        value["candidate_decisions"] = [dict(_mapping(item, field_name="candidate decision")) for item in decisions]
        value["decisions"] = list(value["candidate_decisions"])
        return value

    @staticmethod
    def _decorate_manifest(
        manifest: Mapping[str, object],
        *,
        ranking: tuple[EvaluationMetrics, ...],
        gate: Mapping[str, object] | None,
    ) -> dict[str, object]:
        """Añade ranking/gate al contexto sin cambiar contratos base."""

        document = dict(manifest)
        context = dict(document.get("run_context") or {})
        variant = dict(context.get("wavelet_optimization") or {})
        variant["ranking"] = [_json_safe(item.as_dict()) for item in ranking]
        if gate is not None:
            variant["promotion_gate_result"] = _json_safe(gate)
        variant["status"] = "research"
        variant["product_id"] = "long_horizon_research"
        context["wavelet_optimization"] = variant
        context["status"] = "research"
        context["variant_status"] = "research"
        context["product_status"] = "research"
        document["run_context"] = context
        document["product_id"] = "long_horizon_research"
        return document

    def _make_recorder(
        self,
        *,
        config_path: Path,
        schema_path: Path,
        snapshots: tuple[Any, ...],
        started_at: datetime,
        finished_at: datetime,
    ) -> Any:
        if self.provenance_recorder is not None:
            return self.provenance_recorder
        return ProvenanceRecorder(
            paths=self.paths,
            config_files=(config_path, schema_path),
            input_files=self.input_files,
            output_paths=OUTPUT_RELATIVE_PATHS,
            snapshots=snapshots,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _build_manifest(
        self,
        recorder: Any,
        *,
        plan: ResearchPlan,
        bundle: EvaluationBundle | None,
        run_id: str,
        config_path: Path,
        schema_path: Path,
        snapshots: tuple[Any, ...],
        started_at: datetime,
        finished_at: datetime,
        ranking: tuple[EvaluationMetrics, ...],
        gate: Mapping[str, object] | None,
        complete: bool,
        error: str | None = None,
    ) -> dict[str, object]:
        method = getattr(recorder, "build_manifest", None)
        if not callable(method):
            raise RunnerContractError("provenance_recorder debe exponer build_manifest()")
        manifest = method(
            plan,
            bundle,
            run_id=run_id,
            complete=complete,
            config_files=(config_path, schema_path),
            input_files=self.input_files,
            output_paths=OUTPUT_RELATIVE_PATHS,
            snapshots=snapshots,
            started_at=started_at,
            finished_at=finished_at,
            error=error,
        )
        if not isinstance(manifest, Mapping):
            raise RunnerContractError("build_manifest debe devolver un mapping")
        return self._decorate_manifest(manifest, ranking=ranking, gate=gate)

    def _write_failure_manifest(
        self,
        recorder: Any | None,
        *,
        plan: ResearchPlan,
        bundle: EvaluationBundle | None,
        run_id: str,
        config_path: Path,
        schema_path: Path,
        snapshots: tuple[Any, ...],
        started_at: datetime,
        error: BaseException,
        ranking: tuple[EvaluationMetrics, ...] = (),
        gate: Mapping[str, object] | None = None,
    ) -> Path | None:
        """Persiste un manifest fallido sin declarar éxito ni publicar parcial."""

        if recorder is None:
            try:
                recorder = self._make_recorder(
                    config_path=config_path,
                    schema_path=schema_path,
                    snapshots=snapshots,
                    started_at=started_at,
                    finished_at=_utc_datetime(None),
                )
            except Exception:
                return None
        try:
            manifest = self._build_manifest(
                recorder,
                plan=plan,
                bundle=bundle,
                run_id=run_id,
                config_path=config_path,
                schema_path=schema_path,
                snapshots=snapshots,
                started_at=started_at,
                finished_at=_utc_datetime(None),
                ranking=ranking,
                gate=gate,
                complete=False,
                error=f"{type(error).__name__}: {error}",
            )
            manifest["status"] = "failed"
            writer = getattr(recorder, "write_manifest", None)
            if not callable(writer):
                return None
            return writer(manifest, complete=False)
        except Exception:
            # Un fallo de provenance no debe ocultar la causa original ni
            # intentar reparar escribiendo en otra ruta.
            return None

    def run(
        self,
        *,
        plan: ResearchPlan | None = None,
        data_cutoff: Any = _UNSET,
        origin_dates: Iterable[Any] | Any = _UNSET,
        label_series: Any | None = None,
        trm_monthly: Any | None = None,
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> WaveletOptimizationResult:
        """Ejecuta una corrida completa y publica exactamente cuatro outputs.

        ``label_series``/``trm_monthly`` es un panel explícito de outcomes para
        construir las etiquetas observables. Si se omite, el evaluador solo
        puede usar el prefijo PIT de cada origen y conservará los targets aún no
        observables como ``not_evaluable``; nunca se carga un dataset global.
        """

        if label_series is not None and trm_monthly is not None and label_series is not trm_monthly:
            raise RunnerContractError("label_series y trm_monthly son aliases incompatibles")
        outcome_panel = label_series if label_series is not None else trm_monthly

        loaded_plan, config_path, schema_path = self._load_plan(
            plan=plan,
            data_cutoff=data_cutoff,
            origin_dates=origin_dates,
        )
        guard = PreRegistrationGuard(loaded_plan)
        # El guard conserva el mismo hash incluso si un caller muta un mapping
        # anidado después del freeze.
        guard.assert_unchanged(loaded_plan)

        started = _utc_datetime(started_at)
        effective_run_id = _unique_run_id(
            self.paths,
            started_at=started,
            requested=run_id,
        )

        recorder: Any | None = None
        bundle: EvaluationBundle | None = None
        metrics: tuple[EvaluationMetrics, ...] = ()
        ranking: tuple[EvaluationMetrics, ...] = ()
        gate_result: Mapping[str, object] | None = None
        snapshots: tuple[Any, ...] = ()

        try:
            recording_resolver, series_store, reconstructor, label_builder, ledger = self._new_dependencies(
                loaded_plan
            )
            if self.evaluator is None:
                evaluator = OOS_Evaluator(
                    snapshot_resolver=recording_resolver,
                    series_store=series_store,
                    origin_reconstructor=reconstructor,
                    label_builder=label_builder,
                    coverage_ledger=ledger,
                )
            else:
                evaluator = self.evaluator

            # La marca se hace justo antes de la primera predicción; todavía no
            # se ha llamado al evaluador ni se ha observado una métrica.
            guard.first_prediction(loaded_plan)
            raw_bundle = self._call_evaluator(
                evaluator,
                loaded_plan,
                label_series=outcome_panel,
            )
            snapshots = recording_resolver.snapshots
            guard.assert_unchanged(loaded_plan)
            bundle_without_metrics = self._bundle_with_contract(
                raw_bundle,
                plan=loaded_plan,
            )
            # La cobertura PIT requerida es un prerrequisito de la corrida:
            # una tabla con filas incompletas o inválidas no puede convertirse
            # en métricas ni llegar al publisher. Conservamos el bundle para
            # que el manifest de fallo documente exactamente la cobertura.
            bundle = bundle_without_metrics
            coverage_errors = _required_coverage_errors(bundle_without_metrics)
            if coverage_errors:
                raise WaveletOptimizationError(
                    "Cobertura PIT requerida incompleta o inválida; no se "
                    "calcularon métricas ni se publicaron outputs: "
                    + "; ".join(coverage_errors)
                )

            calculator = self.metrics_calculator or MetricsCalculator.from_plan(loaded_plan)
            calculate = getattr(calculator, "calculate", None)
            if not callable(calculate):
                calculate = getattr(calculator, "evaluate", None)
            if not callable(calculate):
                raise RunnerContractError("metrics_calculator debe exponer calculate()")
            metrics = tuple(
                calculate(
                    bundle_without_metrics,
                    plan=loaded_plan,
                    candidate_ids=tuple(item.candidate_id for item in loaded_plan.candidates),
                    horizons=loaded_plan.horizons,
                    splits=loaded_plan.splits,
                )
            )
            if any(not isinstance(item, EvaluationMetrics) for item in metrics):
                raise RunnerContractError("metrics_calculator debe devolver EvaluationMetrics")
            ranking = tuple(rank_metrics(metrics, split="full"))
            bundle = self._bundle_with_contract(
                bundle_without_metrics,
                plan=loaded_plan,
                metrics=metrics,
            )

            recorder = self._make_recorder(
                config_path=config_path,
                schema_path=schema_path,
                snapshots=snapshots,
                started_at=started,
                finished_at=_utc_datetime(None),
            )
            preliminary_manifest = self._build_manifest(
                recorder,
                plan=loaded_plan,
                bundle=bundle,
                run_id=effective_run_id,
                config_path=config_path,
                schema_path=schema_path,
                snapshots=snapshots,
                started_at=started,
                finished_at=_utc_datetime(None),
                ranking=ranking,
                gate=None,
                complete=False,
            )

            gate = self.promotion_gate or PromotionGate.from_plan(loaded_plan)
            gate_result = self._normalise_gate(
                self._call_gate(
                    gate,
                    loaded_plan,
                    metrics,
                    bundle,
                    preliminary_manifest,
                ),
                plan=loaded_plan,
            )
            guard.assert_unchanged(loaded_plan)
            decisions = gate_result.get("candidate_decisions", ())
            bundle = self._bundle_with_contract(
                bundle,
                plan=loaded_plan,
                metrics=metrics,
                decisions=decisions if isinstance(decisions, Sequence) else (),
            )

            manifest_before_outputs = self._build_manifest(
                recorder,
                plan=loaded_plan,
                bundle=bundle,
                run_id=effective_run_id,
                config_path=config_path,
                schema_path=schema_path,
                snapshots=snapshots,
                started_at=started,
                finished_at=_utc_datetime(None),
                ranking=ranking,
                gate=gate_result,
                complete=False,
            )

            publisher = self.publisher or OutputPublisher(paths=self.paths)
            publish = getattr(publisher, "publish", None)
            if not callable(publish):
                raise RunnerContractError("publisher debe exponer publish()")
            published = tuple(
                publish(
                    loaded_plan,
                    bundle,
                    manifest_before_outputs,
                    gate_decision=gate_result,
                    metrics=metrics,
                    run_id=effective_run_id,
                    experiment_id=loaded_plan.experiment_id,
                )
            )
            if published != OUTPUT_RELATIVE_PATHS:
                raise RunnerContractError(
                    "El publisher no publicó exactamente las cuatro rutas esperadas: "
                    f"{published!r}"
                )

            finished = _utc_datetime(None)
            complete_manifest = self._build_manifest(
                recorder,
                plan=loaded_plan,
                bundle=bundle,
                run_id=effective_run_id,
                config_path=config_path,
                schema_path=schema_path,
                snapshots=snapshots,
                started_at=started,
                finished_at=finished,
                ranking=ranking,
                gate=gate_result,
                complete=True,
            )
            writer = getattr(recorder, "write_manifest", None)
            if not callable(writer):
                raise RunnerContractError("provenance_recorder debe exponer write_manifest()")
            manifest_path = writer(complete_manifest, complete=True)
            if not isinstance(manifest_path, Path):
                manifest_path = Path(manifest_path)

            return WaveletOptimizationResult(
                run_id=effective_run_id,
                plan=loaded_plan,
                bundle=bundle,
                metrics=metrics,
                ranking=ranking,
                promotion_gate=gate_result,
                manifest=complete_manifest,
                manifest_path=manifest_path,
                published_outputs=published,
            )
        except Exception as error:
            # No se intenta un fallback de datos ni se publica una tabla
            # parcial. Si el pipeline ya publicó y falló al escribir el
            # manifest final, el manifest de fallo conserva esa advertencia.
            if recorder is not None:
                failure_snapshots = snapshots
            else:
                failure_snapshots = snapshots
            self._write_failure_manifest(
                recorder,
                plan=loaded_plan,
                bundle=bundle,
                run_id=effective_run_id,
                config_path=config_path,
                schema_path=schema_path,
                snapshots=failure_snapshots,
                started_at=started,
                error=error,
                ranking=ranking,
                gate=gate_result,
            )
            raise

    execute = run
    run_research = run


# ---------------------------------------------------------------------------
# Functional facade y CLI
# ---------------------------------------------------------------------------


def run_wavelet_optimization(
    *,
    paths: ProjectPaths | Path | str | None = None,
    config_path: str | Path | None = None,
    schema_path: str | Path | None = None,
    plan: ResearchPlan | None = None,
    data_cutoff: Any = _UNSET,
    origin_dates: Iterable[Any] | Any = _UNSET,
    label_series: Any | None = None,
    trm_monthly: Any | None = None,
    run_id: str | None = None,
    started_at: datetime | None = None,
    snapshot_resolver: Any | None = None,
    series_store: Any | None = None,
    origin_reconstructor: Any | None = None,
    label_builder: Any | None = None,
    evaluator: Any | None = None,
    metrics_calculator: Any | None = None,
    promotion_gate: Any | None = None,
    publisher: Any | None = None,
    provenance_recorder: Any | None = None,
    input_files: Iterable[str | Path] = (),
) -> WaveletOptimizationResult:
    """Ejecuta la variante con dependencias opcionalmente inyectables."""

    runner = WaveletOptimizationRunner(
        paths=paths,
        config_path=config_path,
        schema_path=schema_path,
        snapshot_resolver=snapshot_resolver,
        series_store=series_store,
        origin_reconstructor=origin_reconstructor,
        label_builder=label_builder,
        evaluator=evaluator,
        metrics_calculator=metrics_calculator,
        promotion_gate=promotion_gate,
        publisher=publisher,
        provenance_recorder=provenance_recorder,
        input_files=input_files,
    )
    return runner.run(
        plan=plan,
        data_cutoff=data_cutoff,
        origin_dates=origin_dates,
        label_series=label_series,
        trm_monthly=trm_monthly,
        run_id=run_id,
        started_at=started_at,
    )


run_research = run_wavelet_optimization
run = run_wavelet_optimization


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wavelet-optimization",
        description=(
            "Ejecuta la investigación wavelet causal PIT; exige un Data_Cutoff "
            "y no modifica los outputs históricos."
        ),
    )
    parser.add_argument("--root", type=Path, default=None, help="Raíz del repositorio")
    parser.add_argument("--config", dest="config_path", type=Path, default=None)
    parser.add_argument("--schema", dest="schema_path", type=Path, default=None)
    parser.add_argument(
        "--data-cutoff",
        required=False,
        help="Data_Cutoff ISO explícito; nunca se infiere de los datos",
    )
    parser.add_argument(
        "--origin-date",
        dest="origin_dates",
        action="append",
        required=False,
        help="Forecast_Origin ISO explícito; repetir para cada origen",
    )
    parser.add_argument(
        "--label-panel",
        "--outcome-panel",
        dest="label_panel",
        type=Path,
        default=None,
        help=(
            "Panel TRM externo y auditable para outcomes; debe estar dentro del proyecto, "
            "no puede ser data/raw y se limita al Data_Cutoff"
        ),
    )
    parser.add_argument("--run-id", default=None, help="Run_ID único opcional")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI compatible con ejecución ``python -m forecast_longterm.wavelet_optimization``."""

    args = _parser().parse_args(argv)
    label_series = None
    input_files: tuple[Path, ...] = ()
    if args.label_panel is not None:
        label_series = load_outcome_panel(
            args.label_panel,
            data_cutoff=args.data_cutoff,
            paths=args.root,
        )
        input_files = (args.label_panel,)
    result = run_wavelet_optimization(
        paths=args.root,
        config_path=args.config_path,
        schema_path=args.schema_path,
        data_cutoff=args.data_cutoff if args.data_cutoff is not None else _UNSET,
        origin_dates=args.origin_dates if args.origin_dates is not None else _UNSET,
        label_series=label_series,
        input_files=input_files,
        run_id=args.run_id,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "experiment_id": result.plan.experiment_id,
                "plan_hash": result.plan.plan_hash,
                "published_outputs": list(result.published_outputs),
                "manifest": result.manifest_path.as_posix(),
                "eligible_candidate_ids": list(
                    result.promotion_gate.get("eligible_candidate_ids", ())
                ),
                "monthly_forecast_connected": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI smoke
    raise SystemExit(main())


__all__ = [
    "RunIDConflict",
    "RunResult",
    "ResearchRunResult",
    "RunnerContractError",
    "WaveletOptimizationError",
    "WaveletOptimizationResult",
    "WaveletOptimizationRunner",
    "main",
    "run",
    "run_research",
    "run_wavelet_optimization",
]
