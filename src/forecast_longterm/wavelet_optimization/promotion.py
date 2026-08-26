"""Puerta conservadora de elegibilidad para la investigación wavelet.

El gate de este módulo no promociona un producto ni modifica el plan de
investigación. Evalúa cada candidato de forma independiente y devuelve una
estructura JSON-friendly que conserva, para cada regla, el estado, la evidencia
y la razón de cualquier rechazo.

Las métricas se reciben normalmente como ``EvaluationMetrics`` producidas por
``MetricsCalculator``. También se aceptan ``EvaluationBundle``/predicciones y
mappings equivalentes para que el runner futuro pueda conectar el gate sin
recalcular una muestra distinta.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, Callable, TypeAlias

import numpy as np
import pandas as pd

from .config import (
    LABEL_MATURITY_RULE,
    MINIMUM_MATURE_TRAINING,
    PRODUCT_ID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    RESEARCH_STATUS,
    ResearchPlan,
)
from .metrics import (
    DM_EVALUATED,
    DM_INSUFFICIENT_OBSERVATIONS,
    EvaluationMetrics,
    MetricsCalculator,
    MetricsError,
)

# ---------------------------------------------------------------------------
# Contrato de umbrales fijados por la preinscripción
# ---------------------------------------------------------------------------

FULL_R2_THRESHOLD = 0.0
DM_P_VALUE_MAX = 0.05
MINIMUM_POSITIVE_SPLITS = 3
SPLIT_MIN_OBSERVATIONS = 12
MINIMUM_R2 = -0.10

# Alias descriptivos para consumidores que usan el nombre de la regla en vez
# del nombre corto. Todos representan exactamente los valores preinscritos.
R2_OOS_FLOOR = MINIMUM_R2
DM_P_VALUE_THRESHOLD = DM_P_VALUE_MAX
MIN_POSITIVE_SPLITS = MINIMUM_POSITIVE_SPLITS
MIN_SPLIT_OBSERVATIONS = SPLIT_MIN_OBSERVATIONS

CONDITION_PASSED = "passed"
CONDITION_FAILED = "failed"
CONDITION_NOT_EVALUABLE = "not_evaluable"
CONDITION_MISSING_EVIDENCE = "missing_evidence"

MetricLike: TypeAlias = EvaluationMetrics | Mapping[str, Any] | Any


class PromotionError(ValueError):
    """Error de entrada o de contrato al evaluar el gate."""


@dataclass(frozen=True)
class PromotionThresholds:
    """Umbrales serializables de una decisión del gate."""

    full_r2_threshold: float = FULL_R2_THRESHOLD
    dm_p_value_max: float = DM_P_VALUE_MAX
    minimum_positive_splits: int = MINIMUM_POSITIVE_SPLITS
    split_min_observations: int = SPLIT_MIN_OBSERVATIONS
    minimum_r2: float = MINIMUM_R2

    def __post_init__(self) -> None:
        try:
            full_r2 = float(self.full_r2_threshold)
            p_value = float(self.dm_p_value_max)
            floor = float(self.minimum_r2)
        except (TypeError, ValueError, OverflowError) as error:
            raise PromotionError("Los umbrales del gate deben ser numéricos") from error
        if not np.isfinite(full_r2) or not np.isfinite(p_value) or not np.isfinite(floor):
            raise PromotionError("Los umbrales del gate deben ser finitos")
        if not 0.0 <= p_value <= 1.0:
            raise PromotionError("dm_p_value_max debe estar en [0, 1]")
        try:
            positive_splits = int(self.minimum_positive_splits)
            minimum_observations = int(self.split_min_observations)
        except (TypeError, ValueError, OverflowError) as error:
            raise PromotionError("Los conteos del gate deben ser enteros") from error
        if (
            isinstance(self.minimum_positive_splits, bool)
            or positive_splits != self.minimum_positive_splits
            or positive_splits < 1
        ):
            raise PromotionError("minimum_positive_splits debe ser entero positivo")
        if (
            isinstance(self.split_min_observations, bool)
            or minimum_observations != self.split_min_observations
            or minimum_observations < 1
        ):
            raise PromotionError("split_min_observations debe ser entero positivo")
        object.__setattr__(self, "full_r2_threshold", full_r2)
        object.__setattr__(self, "dm_p_value_max", p_value)
        object.__setattr__(self, "minimum_r2", floor)
        object.__setattr__(self, "minimum_positive_splits", positive_splits)
        object.__setattr__(self, "split_min_observations", minimum_observations)

    def as_dict(self) -> dict[str, object]:
        return {
            "full_r2_threshold": self.full_r2_threshold,
            "dm_p_value_max": self.dm_p_value_max,
            "minimum_positive_splits": self.minimum_positive_splits,
            "split_min_observations": self.split_min_observations,
            "minimum_r2": self.minimum_r2,
        }

    to_dict = as_dict


@dataclass(frozen=True)
class PromotionCondition:
    """Una condición auditable del gate.

    ``passed`` es la decisión lógica; ``status`` conserva si la condición se
    pudo evaluar. En particular, ``not_evaluable`` nunca se interpreta como
    aprobación: siempre deja ``passed=False``.
    """

    condition: str
    passed: bool
    status: str
    evidence: Mapping[str, object] = field(default_factory=dict)
    reason: str | None = None
    requirement: str | None = None

    def __post_init__(self) -> None:
        name = str(self.condition).strip()
        if not name:
            raise PromotionError("PromotionCondition.condition no puede estar vacío")
        status = str(self.status).strip().lower()
        if status not in {
            CONDITION_PASSED,
            CONDITION_FAILED,
            CONDITION_NOT_EVALUABLE,
            CONDITION_MISSING_EVIDENCE,
        }:
            raise PromotionError(f"Estado de condición no soportado: {status!r}")
        if bool(self.passed) != (status == CONDITION_PASSED):
            raise PromotionError(
                "PromotionCondition.passed debe conciliar con el estado de la condición"
            )
        object.__setattr__(self, "condition", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "passed", status == CONDITION_PASSED)
        object.__setattr__(self, "evidence", dict(self.evidence))
        if self.reason is not None:
            object.__setattr__(self, "reason", str(self.reason))
        if self.requirement is not None:
            object.__setattr__(self, "requirement", str(self.requirement))

    @property
    def rule(self) -> str:
        """Alias usado por serializadores que llaman ``rule`` a la condición."""

        return self.condition

    @property
    def is_failed(self) -> bool:
        return not self.passed

    def as_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "condition": self.condition,
            "rule": self.condition,
            "passed": self.passed,
            "status": self.status,
            "evidence": _json_value(self.evidence),
        }
        if self.reason is not None:
            value["reason"] = self.reason
        if self.requirement is not None:
            value["requirement"] = self.requirement
        return value

    to_dict = as_dict
    to_record = as_dict


@dataclass(frozen=True)
class PromotionDecision:
    """Decisión de elegibilidad metodológica para un candidato."""

    candidate_id: str
    eligible: bool
    conditions: tuple[PromotionCondition, ...]
    product_id: str
    research_status: str

    def __post_init__(self) -> None:
        candidate = str(self.candidate_id).strip()
        if not candidate:
            raise PromotionError("PromotionDecision.candidate_id no puede estar vacío")
        conditions = tuple(self.conditions)
        if any(not isinstance(condition, PromotionCondition) for condition in conditions):
            raise PromotionError("conditions debe contener PromotionCondition")
        expected = all(condition.passed for condition in conditions)
        if bool(self.eligible) != expected:
            raise PromotionError("eligible debe ser la conjunción de todas las condiciones")
        object.__setattr__(self, "candidate_id", candidate)
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "eligible", expected)
        object.__setattr__(self, "product_id", str(self.product_id))
        object.__setattr__(self, "research_status", str(self.research_status))

    @property
    def eligibility(self) -> str:
        return "eligible" if self.eligible else "not_eligible"

    @property
    def failed_conditions(self) -> tuple[str, ...]:
        return tuple(condition.condition for condition in self.conditions if not condition.passed)

    @property
    def failed_condition_details(self) -> tuple[PromotionCondition, ...]:
        return tuple(condition for condition in self.conditions if not condition.passed)

    def as_dict(self) -> dict[str, object]:
        conditions = [condition.as_dict() for condition in self.conditions]
        failed = [condition for condition in conditions if not condition["passed"]]
        return {
            "candidate_id": self.candidate_id,
            "eligible": self.eligible,
            "eligibility": self.eligibility,
            "promotion_eligibility": self.eligibility,
            "conditions": conditions,
            "failed_conditions": list(self.failed_conditions),
            "failed_condition_details": failed,
            "failures": failed,
            "condition_results": conditions,
            "product_id": self.product_id,
            "status": self.research_status,
            "research_status": self.research_status,
            "review_only": True,
        }

    to_dict = as_dict
    to_record = as_dict


# ---------------------------------------------------------------------------
# Normalización tolerante de entradas
# ---------------------------------------------------------------------------


def _json_value(value: Any) -> object:
    """Convierte escalares numpy/pandas y mappings a valores JSON-friendly."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (np.generic,)):
        return _json_value(value.item())
    if isinstance(value, (pd.Timestamp, pd.Period)):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if hasattr(value, "isoformat"):
        try:
            return str(value.isoformat())
        except (AttributeError, TypeError, ValueError):
            pass
    return str(value)


def _normal_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _coerce_bool(value: Any) -> bool | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
        try:
            numeric = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if np.isfinite(numeric) and numeric in {0.0, 1.0}:
            return bool(numeric)
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "si", "sí", "complete", "completed", "valid", "causal", "mature", "evaluated", "scoreable", "observed"}:
        return True
    if text in {"false", "0", "no", "n", "incomplete", "invalid", "missing", "not_evaluable", "not_mature", "non_causal"}:
        return False
    return None


def _is_nonempty(value: Any) -> bool:
    if value is None or value is pd.NA:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    try:
        return bool(value == value)  # NaN -> False; ordinary scalars -> True.
    except (TypeError, ValueError):
        return True


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    method = getattr(value, "as_dict", None)
    if callable(method):
        result = method()
        return result if isinstance(result, Mapping) else None
    return None


def _nested_mappings(value: Any, *, _seen: set[int] | None = None) -> tuple[Mapping[str, Any], ...]:
    """Aplana mappings anidadas sin asumir un schema único de provenance."""

    mapping = _as_mapping(value)
    if mapping is None:
        return ()
    seen = set() if _seen is None else _seen
    identity = id(mapping)
    if identity in seen:
        return ()
    seen.add(identity)
    result: list[Mapping[str, Any]] = [mapping]
    for child in mapping.values():
        child_mapping = _as_mapping(child)
        if child_mapping is not None:
            result.extend(_nested_mappings(child_mapping, _seen=seen))
        elif isinstance(child, (list, tuple)):
            for item in child:
                item_mapping = _as_mapping(item)
                if item_mapping is not None:
                    result.extend(_nested_mappings(item_mapping, _seen=seen))
    return tuple(result)


def _source_mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Devuelve mappings de una fuente o de una secuencia de registros."""

    mappings = _nested_mappings(value)
    if mappings:
        return mappings
    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[Mapping[str, Any]] = []
        for item in value:
            result.extend(_nested_mappings(item))
        return tuple(result)
    return ()


def _materialize_records(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Materializa cobertura, ledger o DataFrame sin perder flags globales."""

    if value is None:
        return ()
    if isinstance(value, pd.DataFrame):
        return tuple(value.to_dict(orient="records"))
    coverage = getattr(value, "coverage", None)
    if coverage is not None and coverage is not value:
        return _materialize_records(coverage)
    records = getattr(value, "records", None)
    if records is not None and not callable(records):
        return _materialize_records(records)
    mapping = _as_mapping(value)
    if mapping is not None:
        result: list[Mapping[str, Any]] = [mapping]
        for key in ("coverage", "records", "rows", "entries"):
            child = mapping.get(key)
            if child is not None and child is not value:
                result.extend(_materialize_records(child))
        return tuple(result)
    if isinstance(value, (str, bytes, bytearray)):
        raise PromotionError("coverage no puede ser texto")
    try:
        values = tuple(value)
    except TypeError as error:
        raise PromotionError("coverage debe ser un ledger, DataFrame o iterable") from error
    result = []
    for item in values:
        item_mapping = _as_mapping(item)
        if item_mapping is not None:
            result.append(item_mapping)
    return tuple(result)


def _mapping_get(mapping: Mapping[str, Any], *names: str) -> Any:
    normalized = {_normal_key(key): value for key, value in mapping.items()}
    for name in names:
        key = _normal_key(name)
        if key in normalized:
            return normalized[key]
    return None


def _metric_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {_normal_key(key): item for key, item in value.items()}

    def get(*names: str, default: Any = None) -> Any:
        for name in names:
            key = _normal_key(name)
            if key in normalized:
                return normalized[key]
        return default

    candidate = get("candidate_id", "candidate")
    horizon = get("horizon_months", "horizon")
    split = get("split", "evaluation_split", default="full")
    if candidate is None or horizon is None:
        raise PromotionError("Cada fila de métricas requiere candidate_id y horizon_months")

    n_oos = get("n_oos", "n_observations", "n_effective_observations", default=0)
    n_requested = get("n_requested_origins", "n_requested", default=n_oos)
    n_scoreable = get("n_scoreable_origins", "n_scoreable", default=n_oos)
    n_excluded = get("n_excluded_origins", "n_excluded", default=None)
    if n_excluded is None:
        try:
            n_excluded = max(0, int(n_requested) - int(n_scoreable))
        except (TypeError, ValueError, OverflowError):
            n_excluded = 0

    dm_p_value = get("dm_p_value", "p_value", "dm_p")
    dm_status = get(
        "dm_status",
        "status_dm",
        default=DM_EVALUATED if dm_p_value is not None else DM_INSUFFICIENT_OBSERVATIONS,
    )
    fields_by_name = {
        "candidate_id": candidate,
        "horizon_months": horizon,
        "split": split,
        "n_requested_origins": n_requested,
        "n_scoreable_origins": n_scoreable,
        "n_excluded_origins": n_excluded,
        "n_oos": n_oos,
        "sse_model": get("sse_model"),
        "sse_random_walk": get("sse_random_walk", "sse_benchmark"),
        "r2_oos": get("r2_oos", "r2"),
        "mae_model": get("mae_model", "mae"),
        "mae_random_walk": get("mae_random_walk", "mae_benchmark"),
        "rmse_model": get("rmse_model", "rmse"),
        "rmse_random_walk": get("rmse_random_walk", "rmse_benchmark"),
        "direction_accuracy_model": get("direction_accuracy_model"),
        "direction_accuracy_random_walk": get("direction_accuracy_random_walk"),
        "dm_stat": get("dm_stat"),
        "dm_p_value": dm_p_value,
        "dm_status": dm_status,
    }
    count_fields = {
        "n_requested_origins",
        "n_scoreable_origins",
        "n_excluded_origins",
        "n_oos",
    }
    nullable_numeric_fields = {
        "sse_model",
        "sse_random_walk",
        "r2_oos",
        "mae_model",
        "mae_random_walk",
        "rmse_model",
        "rmse_random_walk",
        "direction_accuracy_model",
        "direction_accuracy_random_walk",
        "dm_stat",
        "dm_p_value",
    }
    for name in (*count_fields, *nullable_numeric_fields):
        item = fields_by_name[name]
        missing = item is pd.NA or (
            isinstance(item, (float, np.floating)) and bool(np.isnan(item))
        )
        if missing:
            fields_by_name[name] = 0 if name in count_fields else None
    return fields_by_name


def _coerce_metric(value: MetricLike) -> EvaluationMetrics:
    if isinstance(value, EvaluationMetrics):
        return value
    mapping = _as_mapping(value)
    if mapping is None:
        # Objects with the same public attributes as EvaluationMetrics are
        # accepted for adapters, but prediction rows are handled earlier.
        mapping = {
            field.name: getattr(value, field.name)
            for field in fields(EvaluationMetrics)
            if hasattr(value, field.name)
        }
    payload = _metric_mapping(mapping)
    try:
        return EvaluationMetrics(**payload)
    except (TypeError, ValueError, MetricsError) as error:
        raise PromotionError(f"Fila de métricas inválida: {error}") from error


def _looks_like_prediction(value: Any) -> bool:
    names = (
        "prediction_wavelet",
        "prediction_model",
        "prediction_random_walk",
        "observed_forward_return",
    )
    if isinstance(value, Mapping):
        normalized = {_normal_key(key) for key in value}
        return any(_normal_key(name) in normalized for name in names)
    return any(hasattr(value, name) for name in names)


def _materialize_metrics(
    metrics: Any,
    *,
    plan: Any,
) -> tuple[EvaluationMetrics, ...]:
    """Acepta métricas, bundle o predicciones y siempre devuelve filas tipadas."""

    if metrics is None:
        return ()

    bundle = metrics if hasattr(metrics, "predictions") else None
    if bundle is not None:
        raw_metrics = getattr(bundle, "metrics", ())
        if raw_metrics:
            return tuple(_coerce_metric(item) for item in raw_metrics)
        metrics = getattr(bundle, "predictions", ())

    if isinstance(metrics, pd.DataFrame):
        values: tuple[Any, ...] = tuple(metrics.to_dict(orient="records"))
    elif isinstance(metrics, Mapping):
        nested = metrics.get("metrics")
        if nested is not None:
            values = tuple(nested.to_dict(orient="records")) if isinstance(nested, pd.DataFrame) else tuple(nested)
        elif "candidate_id" in metrics or "candidate" in metrics:
            values = (metrics,)
        else:
            values = tuple(metrics.values())
    elif isinstance(metrics, (str, bytes, bytearray)):
        raise PromotionError("metrics no puede ser texto")
    else:
        try:
            values = tuple(metrics)
        except TypeError:
            values = (metrics,)

    if values and _looks_like_prediction(values[0]):
        try:
            calculated = MetricsCalculator.from_plan(plan).calculate(
                values,
                plan=plan,
            )
        except (MetricsError, ValueError, TypeError) as error:
            raise PromotionError(f"No se pudieron calcular las métricas del bundle: {error}") from error
        return tuple(calculated)
    return tuple(_coerce_metric(item) for item in values)


def _candidate_ids(plan: Any, metrics: Sequence[EvaluationMetrics]) -> tuple[str, ...]:
    result: set[str] = set()
    raw_candidates = getattr(plan, "candidates", ()) if plan is not None else ()
    if isinstance(raw_candidates, Mapping):
        raw_candidates = raw_candidates.values()
    for candidate in raw_candidates or ():
        identifier = getattr(candidate, "candidate_id", candidate)
        if isinstance(candidate, Mapping):
            identifier = candidate.get("candidate_id", candidate.get("id", identifier))
        text = str(identifier).strip()
        if text:
            result.add(text)
    result.update(metric.candidate_id for metric in metrics)
    return tuple(sorted(result))


def _metric_lookup(metrics: Sequence[EvaluationMetrics]) -> dict[tuple[str, int, str], EvaluationMetrics]:
    lookup: dict[tuple[str, int, str], EvaluationMetrics] = {}
    for metric in metrics:
        # MetricsCalculator emits one row per group. If an adapter sends a
        # duplicate, keep the first row deterministically and expose the
        # duplicate in the top-level summary rather than silently replacing it.
        lookup.setdefault(metric.key, metric)
    return lookup


def _metric_evidence(metric: EvaluationMetrics | None) -> dict[str, object]:
    if metric is None:
        return {"metric_status": "missing", "metric": None}
    return {
        "metric_status": "evaluable" if metric.n_oos > 0 else CONDITION_NOT_EVALUABLE,
        "candidate_id": metric.candidate_id,
        "horizon_months": metric.horizon_months,
        "split": metric.split,
        "n_requested_origins": metric.n_requested_origins,
        "n_scoreable_origins": metric.n_scoreable_origins,
        "n_excluded_origins": metric.n_excluded_origins,
        "n_oos": metric.n_oos,
        "r2_oos": metric.r2_oos,
        "mae_model": metric.mae_model,
        "mae_random_walk": metric.mae_random_walk,
        "rmse_model": metric.rmse_model,
        "rmse_random_walk": metric.rmse_random_walk,
        "dm_p_value": metric.dm_p_value,
        "dm_status": metric.dm_status,
    }


def _condition(
    name: str,
    passed: bool,
    *,
    status: str | None = None,
    evidence: Mapping[str, object] | None = None,
    reason: str | None = None,
    requirement: str | None = None,
) -> PromotionCondition:
    resolved_status = CONDITION_PASSED if passed else (status or CONDITION_FAILED)
    return PromotionCondition(
        condition=name,
        passed=passed,
        status=resolved_status,
        evidence={} if evidence is None else evidence,
        reason=reason,
        requirement=requirement,
    )


def _finite(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if np.isfinite(numeric) else None


def _full_numeric_condition(
    metric: EvaluationMetrics | None,
    *,
    candidate_id: str,
    horizon: int,
    field_name: str,
    benchmark_field: str | None,
    name: str,
    requirement: str,
    comparator: Callable[[float, float], bool] | Callable[[float], bool],
    threshold: float | None = None,
) -> PromotionCondition:
    evidence = _metric_evidence(metric)
    evidence.update(
        {
            "candidate_id": candidate_id,
            "horizon_months": horizon,
            "split": "full",
            "required_field": field_name,
            "benchmark_field": benchmark_field,
            "threshold": threshold,
        }
    )
    if metric is None:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason="metric_missing",
            requirement=requirement,
        )
    if metric.n_oos <= 0:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason="no_scoreable_observations",
            requirement=requirement,
        )
    value = _finite(getattr(metric, field_name, None))
    evidence[field_name] = value
    if value is None:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason=f"{field_name}_not_evaluable",
            requirement=requirement,
        )
    if benchmark_field is None:
        passed = comparator(value)  # type: ignore[call-arg]
        evidence["comparison"] = f"{field_name} > {threshold}"
    else:
        benchmark = _finite(getattr(metric, benchmark_field, None))
        evidence[benchmark_field] = benchmark
        if benchmark is None:
            return _condition(
                name,
                False,
                status=CONDITION_NOT_EVALUABLE,
                evidence=evidence,
                reason=f"{benchmark_field}_not_evaluable",
                requirement=requirement,
            )
        passed = comparator(value, benchmark)  # type: ignore[call-arg]
        evidence["comparison"] = f"{field_name} < {benchmark_field}"
    if passed:
        return _condition(name, True, evidence=evidence, requirement=requirement)
    return _condition(
        name,
        False,
        status=CONDITION_FAILED,
        evidence=evidence,
        reason="threshold_not_met",
        requirement=requirement,
    )


def _dm_condition(
    metric: EvaluationMetrics | None,
    *,
    candidate_id: str,
    horizon: int,
    threshold: float,
) -> PromotionCondition:
    name = f"full_dm_p_value_at_most_0_05_h{horizon}"
    evidence = _metric_evidence(metric)
    evidence.update(
        {
            "candidate_id": candidate_id,
            "horizon_months": horizon,
            "split": "full",
            "required_dm_status": DM_EVALUATED,
            "dm_p_value_max": threshold,
        }
    )
    if metric is None or metric.n_oos <= 0:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason="metric_missing" if metric is None else "no_scoreable_observations",
            requirement="10.1",
        )
    p_value = _finite(metric.dm_p_value)
    dm_status = str(metric.dm_status).strip().lower()
    evidence.update({"dm_p_value": p_value, "dm_status": metric.dm_status})
    if p_value is None or dm_status != DM_EVALUATED:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason=(
                "dm_p_value_not_evaluable"
                if p_value is None
                else f"dm_status_{dm_status or 'missing'}"
            ),
            requirement="10.1",
        )
    if p_value <= threshold:
        return _condition(name, True, evidence=evidence, requirement="10.1")
    return _condition(
        name,
        False,
        status=CONDITION_FAILED,
        evidence=evidence,
        reason="dm_p_value_above_threshold",
        requirement="10.1",
    )


def _split_condition(
    lookup: Mapping[tuple[str, int, str], EvaluationMetrics],
    *,
    candidate_id: str,
    horizon: int,
    minimum_positive_splits: int,
    minimum_observations: int,
) -> PromotionCondition:
    name = f"at_least_{minimum_positive_splits}_of_4_positive_splits_h{horizon}"
    split_details: list[dict[str, object]] = []
    positive: list[str] = []
    considered: list[str] = []
    missing: list[str] = []
    for split in REQUIRED_SPLITS:
        metric = lookup.get((candidate_id, horizon, split))
        detail = _metric_evidence(metric)
        detail["split"] = split
        detail["minimum_observations"] = minimum_observations
        qualifies = False
        if metric is None:
            missing.append(split)
            detail.update({"status": CONDITION_NOT_EVALUABLE, "qualifies": False, "reason": "metric_missing"})
        elif metric.n_oos < minimum_observations:
            considered.append(split)
            detail.update({"status": "insufficient_observations", "qualifies": False, "reason": "n_oos_below_minimum"})
        elif metric.r2_oos is None or _finite(metric.r2_oos) is None:
            considered.append(split)
            detail.update({"status": CONDITION_NOT_EVALUABLE, "qualifies": False, "reason": "r2_oos_not_evaluable"})
        else:
            considered.append(split)
            qualifies = float(metric.r2_oos) > FULL_R2_THRESHOLD
            detail.update(
                {
                    "status": "positive" if qualifies else "not_positive",
                    "qualifies": qualifies,
                    "reason": None if qualifies else "r2_oos_not_positive",
                }
            )
        if qualifies:
            positive.append(split)
        split_details.append(detail)

    evidence = {
        "candidate_id": candidate_id,
        "horizon_months": horizon,
        "splits": split_details,
        "positive_splits": positive,
        "n_positive_splits": len(positive),
        "minimum_positive_splits": minimum_positive_splits,
        "minimum_observations": minimum_observations,
        "missing_splits": missing,
    }
    if len(positive) >= minimum_positive_splits:
        return _condition(
            name,
            True,
            evidence=evidence,
            requirement="10.2",
        )
    status = CONDITION_NOT_EVALUABLE if not considered else CONDITION_FAILED
    reason = "metrics_not_evaluable" if status == CONDITION_NOT_EVALUABLE else "positive_split_count_below_minimum"
    return _condition(
        name,
        False,
        status=status,
        evidence=evidence,
        reason=reason,
        requirement="10.2",
    )


def _floor_condition(
    lookup: Mapping[tuple[str, int, str], EvaluationMetrics],
    *,
    candidate_id: str,
    horizon: int,
    minimum_r2: float,
) -> PromotionCondition:
    name = f"no_scoreable_split_below_r2_floor_h{horizon}"
    scoreable: list[dict[str, object]] = []
    violations: list[dict[str, object]] = []
    missing: list[str] = []
    for split in REQUIRED_SPLITS:
        metric = lookup.get((candidate_id, horizon, split))
        if metric is None:
            missing.append(split)
            continue
        r2 = _finite(metric.r2_oos)
        if metric.n_oos <= 0 or r2 is None:
            continue
        detail = {
            "split": split,
            "n_oos": metric.n_oos,
            "r2_oos": r2,
            "minimum_r2": minimum_r2,
            "scoreable": True,
        }
        scoreable.append(detail)
        if r2 < minimum_r2:
            violations.append(detail)

    evidence = {
        "candidate_id": candidate_id,
        "horizon_months": horizon,
        "minimum_r2": minimum_r2,
        "scoreable_splits": scoreable,
        "violating_splits": violations,
        "missing_splits": missing,
    }
    if violations:
        return _condition(
            name,
            False,
            status=CONDITION_FAILED,
            evidence=evidence,
            reason="scoreable_split_below_r2_floor",
            requirement="10.2",
        )
    if not scoreable:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason="no_scoreable_split",
            requirement="10.2",
        )
    return _condition(name, True, evidence=evidence, requirement="10.2")


# ---------------------------------------------------------------------------
# Evidencia causal, madurez, PIT y provenance
# ---------------------------------------------------------------------------


def _record_applies(record: Mapping[str, Any], candidate_id: str) -> bool:
    raw = _mapping_get(record, "candidate_id", "candidate")
    if raw is not None and str(raw).strip() != candidate_id:
        return False
    required = _coerce_bool(_mapping_get(record, "required_for_candidate", "required"))
    return required is not False


def _flag_values(
    sources: Iterable[Any],
    aliases: Iterable[str],
    *,
    candidate_id: str | None = None,
) -> tuple[tuple[bool, Mapping[str, Any]], ...]:
    alias_set = {_normal_key(alias) for alias in aliases}
    found: list[tuple[bool, Mapping[str, Any]]] = []
    for source in sources:
        for mapping in _source_mappings(source):
            if candidate_id is not None and not _record_applies(mapping, candidate_id):
                continue
            for key, raw_value in mapping.items():
                normalized = _normal_key(key)
                if normalized not in alias_set:
                    continue
                value = _coerce_bool(raw_value)
                if value is not None:
                    found.append((value, mapping))
                elif isinstance(raw_value, Mapping):
                    nested = _mapping_get(raw_value, "complete", "valid", "value", "status")
                    nested_value = _coerce_bool(nested)
                    if nested_value is not None:
                        found.append((nested_value, mapping))
    return tuple(found)


def _flag_condition(
    name: str,
    *,
    candidate_id: str,
    aliases: Iterable[str],
    sources: Iterable[Any],
    requirement: str,
    inverse_aliases: Iterable[str] = (),
    inferred: tuple[bool | None, Mapping[str, object]] | None = None,
) -> PromotionCondition:
    values = list(_flag_values(sources, aliases, candidate_id=candidate_id))
    inverse_values = list(_flag_values(sources, inverse_aliases, candidate_id=candidate_id))
    evidence: dict[str, object] = {
        "candidate_id": candidate_id,
        "aliases_checked": list(aliases),
        "observations": [
            {"value": value, "source": _json_value(dict(mapping))}
            for value, mapping in values
        ],
    }
    if inverse_values:
        evidence["inverse_observations"] = [
            {"uses_future_observations": value, "source": _json_value(dict(mapping))}
            for value, mapping in inverse_values
        ]
        if any(value for value, _mapping in inverse_values):
            return _condition(
                name,
                False,
                status=CONDITION_FAILED,
                evidence=evidence,
                reason="future_observations_detected",
                requirement=requirement,
            )
        values.extend((not value, mapping) for value, mapping in inverse_values)

    if any(not value for value, _mapping in values):
        return _condition(
            name,
            False,
            status=CONDITION_FAILED,
            evidence=evidence,
            reason="evidence_flag_false",
            requirement=requirement,
        )
    if values:
        evidence["resolved"] = True
        return _condition(name, True, evidence=evidence, requirement=requirement)
    if inferred is not None and inferred[0] is not None:
        evidence.update(dict(inferred[1]))
        if inferred[0]:
            return _condition(name, True, evidence=evidence, requirement=requirement)
        return _condition(
            name,
            False,
            status=CONDITION_FAILED,
            evidence=evidence,
            reason="inferred_evidence_false",
            requirement=requirement,
        )
    return _condition(
        name,
        False,
        status=CONDITION_NOT_EVALUABLE,
        evidence=evidence,
        reason="evidence_missing",
        requirement=requirement,
    )


def _coverage_condition(
    coverage: Sequence[Mapping[str, Any]],
    provenance: Any,
    *,
    candidate_id: str,
) -> PromotionCondition:
    name = "complete_pit_coverage"
    relevant = [row for row in coverage if _record_applies(row, candidate_id)]
    explicit_values = list(
        _flag_values(
            (coverage, provenance),
            ("complete_pit_coverage", "pit_coverage_complete", "coverage_complete"),
            candidate_id=candidate_id,
        )
    )
    evidence: dict[str, object] = {
        "candidate_id": candidate_id,
        "n_coverage_records": len(relevant),
        "coverage_records": [_json_value(dict(row)) for row in relevant],
        "explicit_flags": [value for value, _mapping in explicit_values],
    }
    if any(not value for value, _mapping in explicit_values):
        return _condition(
            name,
            False,
            status=CONDITION_FAILED,
            evidence=evidence,
            reason="pit_coverage_flag_false",
            requirement="10.3",
        )

    bad_rows: list[dict[str, object]] = []
    for row in relevant:
        status = _mapping_get(row, "coverage_status", "pit_coverage_status")
        complete = _mapping_get(row, "complete", "coverage_complete")
        missing = _mapping_get(row, "n_missing", "missing")
        complete_bool = _coerce_bool(complete)
        missing_count = _finite(missing)
        if status is None and complete_bool is None:
            bad_rows.append({"reason": "coverage_status_missing", "row": _json_value(dict(row))})
            continue
        normalized_status = _normal_key(status) if status is not None else "complete" if complete_bool else "incomplete"
        if normalized_status != "complete" or complete_bool is False or (missing_count is not None and missing_count > 0):
            bad_rows.append(
                {
                    "reason": "coverage_not_complete",
                    "coverage_status": status,
                    "complete": complete_bool,
                    "n_missing": missing_count,
                    "row": _json_value(dict(row)),
                }
            )
    evidence["invalid_records"] = bad_rows
    if bad_rows:
        return _condition(
            name,
            False,
            status=CONDITION_FAILED,
            evidence=evidence,
            reason="pit_coverage_incomplete",
            requirement="10.3",
        )
    if relevant or any(value for value, _mapping in explicit_values):
        return _condition(name, True, evidence=evidence, requirement="10.3")
    return _condition(
        name,
        False,
        status=CONDITION_NOT_EVALUABLE,
        evidence=evidence,
        reason="coverage_records_missing",
        requirement="10.3",
    )


def _provenance_value(provenance: Any, *aliases: str) -> Any:
    for mapping in _nested_mappings(provenance):
        value = _mapping_get(mapping, *aliases)
        if value is not None:
            return value
    return None


def _provenance_condition(provenance: Any, *, candidate_id: str) -> PromotionCondition:
    name = "complete_provenance"
    mappings = _nested_mappings(provenance)
    evidence: dict[str, object] = {
        "candidate_id": candidate_id,
        "provenance_present": bool(mappings),
    }
    if not mappings:
        return _condition(
            name,
            False,
            status=CONDITION_NOT_EVALUABLE,
            evidence=evidence,
            reason="provenance_missing",
            requirement="10.3",
        )

    explicit = _flag_values(
        (provenance,),
        ("provenance_complete", "complete_provenance", "is_complete", "complete"),
    )
    evidence["explicit_flags"] = [value for value, _mapping in explicit]
    missing_fields: list[Any] = []
    for mapping in mappings:
        value = _mapping_get(mapping, "missing_fields", "missing_provenance_fields", "required_fields_missing")
        if isinstance(value, (list, tuple, set, frozenset)):
            missing_fields.extend(value)
        elif value is not None and _is_nonempty(value):
            missing_fields.append(value)
    evidence["missing_fields"] = [_json_value(item) for item in missing_fields]
    if missing_fields or any(not value for value, _mapping in explicit):
        return _condition(
            name,
            False,
            status=CONDITION_FAILED,
            evidence=evidence,
            reason="provenance_fields_missing",
            requirement="10.3",
        )
    if explicit and all(value for value, _mapping in explicit):
        return _condition(name, True, evidence=evidence, requirement="10.3")

    # Un manifest futuro puede declarar solo ``missing_fields=[]`` como
    # resultado de una validación de schema; esa declaración es una evidencia
    # explícita aunque no repita todos los campos del manifest.
    if any(
        _mapping_get(mapping, "missing_fields", "missing_provenance_fields") == []
        for mapping in mappings
    ):
        evidence["resolved_from_empty_missing_fields"] = True
        return _condition(name, True, evidence=evidence, requirement="10.3")

    # Si no hay flag explícito, se exige el conjunto mínimo que el diseño
    # manda conservar en run_context/provenance. Las alternativas permiten
    # consumir tanto el nombre del plan como el del manifest base.
    required_groups: tuple[tuple[str, ...], ...] = (
        ("run_id",),
        ("experiment_id", "experiment_ids"),
        ("product_id",),
        ("status",),
        ("plan_hash",),
        ("data_cutoff", "data_cutoff_date"),
        ("target_definition",),
        ("horizons", "horizons_months"),
        ("splits", "evaluation_splits"),
        ("benchmark", "benchmark_id"),
        ("label_maturity_rule", "label_maturity"),
        ("minimum_mature_training",),
        ("dwt", "dwt_parameters"),
        ("candidates", "candidate_grid"),
        ("snapshot_manifests", "snapshots"),
        ("source_vintages", "vintages"),
        ("coverage_summary", "coverage"),
        ("input_files", "inputs"),
        ("git_commit", "code_revision", "revision"),
        ("environment",),
        ("seed",),
        ("output_paths", "outputs", "output_files"),
        ("warnings",),
    )
    missing_groups: list[list[str]] = []
    for group in required_groups:
        found = False
        for mapping in mappings:
            for alias in group:
                value = _mapping_get(mapping, alias)
                if _is_nonempty(value):
                    found = True
                    break
            if found:
                break
        if not found:
            missing_groups.append(list(group))
    evidence["missing_required_groups"] = missing_groups
    if not missing_groups:
        return _condition(name, True, evidence=evidence, requirement="10.3")
    return _condition(
        name,
        False,
        status=CONDITION_NOT_EVALUABLE,
        evidence=evidence,
        reason="provenance_required_fields_not_available",
        requirement="10.3",
    )


def _maturity_inference(provenance: Any) -> tuple[bool | None, Mapping[str, object]]:
    rule = _provenance_value(provenance, "label_maturity_rule", "label_maturity")
    minimum = _provenance_value(provenance, "minimum_mature_training")
    if rule is None:
        return None, {}
    rule_text = _normal_key(rule)
    try:
        minimum_value = int(minimum)
    except (TypeError, ValueError, OverflowError):
        minimum_value = None
    matches_rule = rule_text in {
        _normal_key(LABEL_MATURITY_RULE),
        "i_plus_h_strictly_before_origin",
        "i_h_t",
        "i_plus_h_lt_t",
    }
    matches_minimum = minimum_value is None or minimum_value >= MINIMUM_MATURE_TRAINING
    return (
        bool(matches_rule and matches_minimum),
        {
            "inferred_from_provenance_rule": rule,
            "minimum_mature_training": minimum_value,
            "required_minimum_mature_training": MINIMUM_MATURE_TRAINING,
        },
    )


# ---------------------------------------------------------------------------
# Gate público
# ---------------------------------------------------------------------------


class PromotionGate:
    """Evalúa la elegibilidad metodológica sin promover productos.

    La instancia es configurable para pruebas de contrato, pero sus valores
    por defecto son exactamente los de ``[promotion_gate]`` del TOML
    preinscrito. Una condición ausente o no evaluable siempre es falsa.
    """

    def __init__(
        self,
        *,
        full_r2_threshold: float = FULL_R2_THRESHOLD,
        dm_p_value_max: float = DM_P_VALUE_MAX,
        minimum_positive_splits: int = MINIMUM_POSITIVE_SPLITS,
        split_min_observations: int = SPLIT_MIN_OBSERVATIONS,
        minimum_r2: float = MINIMUM_R2,
    ) -> None:
        self.thresholds = PromotionThresholds(
            full_r2_threshold=full_r2_threshold,
            dm_p_value_max=dm_p_value_max,
            minimum_positive_splits=minimum_positive_splits,
            split_min_observations=split_min_observations,
            minimum_r2=minimum_r2,
        )

    @classmethod
    def from_plan(cls, _plan: Any) -> "PromotionGate":
        """Construye el gate con los umbrales fijos de la variante."""

        return cls()

    def _candidate_conditions(
        self,
        candidate_id: str,
        lookup: Mapping[tuple[str, int, str], EvaluationMetrics],
        coverage: Sequence[Mapping[str, Any]],
        provenance: Any,
    ) -> tuple[PromotionCondition, ...]:
        conditions: list[PromotionCondition] = []
        for horizon in REQUIRED_HORIZONS:
            full = lookup.get((candidate_id, horizon, "full"))
            conditions.append(
                _full_numeric_condition(
                    full,
                    candidate_id=candidate_id,
                    horizon=horizon,
                    field_name="r2_oos",
                    benchmark_field=None,
                    name=f"full_r2_oos_positive_h{horizon}",
                    requirement="10.1",
                    comparator=lambda value, threshold=self.thresholds.full_r2_threshold: value > threshold,
                    threshold=self.thresholds.full_r2_threshold,
                )
            )
            conditions.append(
                _full_numeric_condition(
                    full,
                    candidate_id=candidate_id,
                    horizon=horizon,
                    field_name="mae_model",
                    benchmark_field="mae_random_walk",
                    name=f"full_mae_below_benchmark_h{horizon}",
                    requirement="10.1",
                    comparator=lambda value, benchmark: value < benchmark,
                )
            )
            conditions.append(
                _full_numeric_condition(
                    full,
                    candidate_id=candidate_id,
                    horizon=horizon,
                    field_name="rmse_model",
                    benchmark_field="rmse_random_walk",
                    name=f"full_rmse_below_benchmark_h{horizon}",
                    requirement="10.1",
                    comparator=lambda value, benchmark: value < benchmark,
                )
            )
            conditions.append(
                _dm_condition(
                    full,
                    candidate_id=candidate_id,
                    horizon=horizon,
                    threshold=self.thresholds.dm_p_value_max,
                )
            )
            conditions.append(
                _split_condition(
                    lookup,
                    candidate_id=candidate_id,
                    horizon=horizon,
                    minimum_positive_splits=self.thresholds.minimum_positive_splits,
                    minimum_observations=self.thresholds.split_min_observations,
                )
            )
            conditions.append(
                _floor_condition(
                    lookup,
                    candidate_id=candidate_id,
                    horizon=horizon,
                    minimum_r2=self.thresholds.minimum_r2,
                )
            )

        evidence_sources = (coverage, provenance)
        conditions.append(
            _flag_condition(
                "causal_reconstruction",
                candidate_id=candidate_id,
                aliases=("causal_reconstruction", "causal_reconstruction_complete", "causal"),
                inverse_aliases=("uses_future_observations",),
                sources=evidence_sources,
                requirement="10.3",
            )
        )
        conditions.append(
            _flag_condition(
                "label_maturity",
                candidate_id=candidate_id,
                aliases=("label_maturity", "label_maturity_complete", "label_maturity_status", "maturity_complete", "all_labels_mature", "mature_labels", "mature"),
                sources=evidence_sources,
                requirement="10.3",
                inferred=_maturity_inference(provenance),
            )
        )
        conditions.append(
            _coverage_condition(coverage, provenance, candidate_id=candidate_id)
        )
        conditions.append(
            _provenance_condition(provenance, candidate_id=candidate_id)
        )
        return tuple(conditions)

    def evaluate(
        self,
        plan: ResearchPlan | Any,
        metrics: Any = None,
        coverage: Any = None,
        provenance: Mapping[str, Any] | Any = None,
    ) -> dict[str, object]:
        """Evalúa todos los candidatos y devuelve una decisión explicable.

        ``metrics`` puede ser una secuencia de ``EvaluationMetrics``, una tabla
        equivalente, un ``EvaluationBundle`` o sus predicciones. En el último
        caso se usa ``MetricsCalculator.from_plan(plan)`` para conservar las
        mismas reglas de muestra y DM del evaluador.
        """

        if plan is None:
            raise PromotionError("PromotionGate.evaluate requiere un plan")
        try:
            metric_rows = _materialize_metrics(metrics, plan=plan)
        except PromotionError:
            raise
        except Exception as error:
            raise PromotionError(f"No se pudieron materializar las métricas: {error}") from error

        bundle = metrics if hasattr(metrics, "predictions") else None
        if coverage is None and bundle is not None:
            coverage = getattr(bundle, "coverage", ())
        coverage_rows = _materialize_records(coverage)
        lookup = _metric_lookup(metric_rows)
        candidates = _candidate_ids(plan, metric_rows)
        product_id = str(getattr(plan, "product_id", PRODUCT_ID))
        research_status = str(getattr(plan, "status", RESEARCH_STATUS))

        decisions: list[dict[str, object]] = []
        decision_objects: list[PromotionDecision] = []
        for candidate_id in candidates:
            conditions = self._candidate_conditions(
                candidate_id,
                lookup,
                coverage_rows,
                provenance,
            )
            decision_object = PromotionDecision(
                candidate_id=candidate_id,
                eligible=all(condition.passed for condition in conditions),
                conditions=conditions,
                product_id=product_id,
                research_status=research_status,
            )
            decision_objects.append(decision_object)
            decisions.append(decision_object.as_dict())

        eligible_ids = [
            decision.candidate_id for decision in decision_objects if decision.eligible
        ]
        context_warnings: list[str] = []
        if product_id != PRODUCT_ID:
            context_warnings.append(
                "El plan no conserva product_id='long_horizon_research'; la decisión no lo modifica."
            )
        if research_status != RESEARCH_STATUS:
            context_warnings.append(
                "El plan no conserva status='research'; la decisión no lo modifica."
            )
        if not candidates:
            context_warnings.append("No hay candidatos preinscritos ni métricas para evaluar.")

        result: dict[str, object] = {
            "schema_version": 1,
            "gate": "promotion_eligibility",
            "eligibility_scope": "methodological_review",
            # ``eligible`` indica si existe al menos una candidata elegible para
            # revisión. La decisión individual y la lista completa están debajo;
            # no existe una promoción global de producto.
            "eligible": bool(eligible_ids),
            "eligible_candidate_ids": eligible_ids,
            "all_candidates_eligible": bool(decision_objects) and all(
                decision.eligible for decision in decision_objects
            ),
            "candidate_decisions": decisions,
            "decisions": decisions,
            "by_candidate": {
                decision["candidate_id"]: decision for decision in decisions
            },
            "thresholds": self.thresholds.as_dict(),
            "n_metric_rows": len(metric_rows),
            "n_candidates": len(candidates),
            "product_id": product_id,
            "status": research_status,
            "research_only": True,
            "review_only": True,
            "requires_independent_methodological_review": True,
            "monthly_forecast_connected": False,
            "promotion_authorized": False,
            "warnings": context_warnings,
        }
        return result

    assess = evaluate
    check = evaluate
    evaluate_gate = evaluate

    def evaluate_bundle(
        self,
        plan: ResearchPlan | Any,
        bundle: Any,
        provenance: Mapping[str, Any] | Any = None,
    ) -> dict[str, object]:
        """Atajo explícito para ``EvaluationBundle``."""

        return self.evaluate(plan, bundle, getattr(bundle, "coverage", ()), provenance)


# API funcional para callers que no necesitan conservar una instancia.
def evaluate_promotion_gate(
    plan: ResearchPlan | Any,
    metrics: Any = None,
    coverage: Any = None,
    provenance: Mapping[str, Any] | Any = None,
) -> dict[str, object]:
    return PromotionGate().evaluate(plan, metrics, coverage, provenance)


promotion_gate = evaluate_promotion_gate
check_promotion = evaluate_promotion_gate


__all__ = [
    "CONDITION_FAILED",
    "CONDITION_MISSING_EVIDENCE",
    "CONDITION_NOT_EVALUABLE",
    "CONDITION_PASSED",
    "DM_P_VALUE_MAX",
    "DM_P_VALUE_THRESHOLD",
    "FULL_R2_THRESHOLD",
    "MINIMUM_POSITIVE_SPLITS",
    "MINIMUM_R2",
    "MIN_POSITIVE_SPLITS",
    "MIN_SPLIT_OBSERVATIONS",
    "PromotionCondition",
    "PromotionDecision",
    "PromotionError",
    "PromotionGate",
    "PromotionThresholds",
    "R2_OOS_FLOOR",
    "SPLIT_MIN_OBSERVATIONS",
    "check_promotion",
    "evaluate_promotion_gate",
    "promotion_gate",
]
