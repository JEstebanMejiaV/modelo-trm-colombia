"""Evaluación walk-forward causal de la variante wavelet de largo horizonte.

Este módulo coordina las capas PIT, reconstrucción causal y etiquetas. La
coordinación es deliberadamente independiente de ``forecast_longterm.wavelets``:
una señal de entrenamiento se reconstruye en el origen histórico de la etiqueta
y una señal OOS se reconstruye en el origen que la consume. Así, ninguna
predicción comparte coeficientes, señales ni coeficientes OLS con otro origen.

La tabla lógica producida por :class:`OOS_Evaluator` tiene una fila por
``(origin_date, horizon_months, candidate_id)``. Las vistas ``full`` y de
submuestra son únicamente proyecciones de esa tabla; no vuelven a ajustar ni a
calcular el benchmark.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

import numpy as np
import pandas as pd

from .config import (
    BENCHMARK_RETURN_PREDICTION,
    MINIMUM_MATURE_TRAINING,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    CandidateSpecification,
    ResearchPlan,
)
from .labels import (
    NOT_EVALUABLE_LABEL_NOT_MATURE,
    NOT_SCOREABLE_INSUFFICIENT_TRAINING,
    SCOREABLE,
    ForwardLabelBuilder,
    MatureLabel,
    ScoreabilityResult,
)
from .reconstruction import (
    CausalReconstructionError,
    OriginReconstructor,
    ReconstructionResult,
)
from .snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSeriesStore,
    PointInTimeSnapshot,
    SnapshotResolutionError,
    SnapshotResolver,
    SnapshotSeriesError,
)

# ---------------------------------------------------------------------------
# Estados de evaluación
# ---------------------------------------------------------------------------

NOT_SCOREABLE_SNAPSHOT_MISSING = "not_scoreable_snapshot_missing"
NOT_SCOREABLE_SNAPSHOT_INVALID = "not_scoreable_snapshot_invalid"
NOT_SCOREABLE_SOURCE_MISSING = "not_scoreable_source_missing"
NOT_SCOREABLE_COVERAGE_INCOMPLETE = "not_scoreable_coverage_incomplete"
NOT_SCOREABLE_RECONSTRUCTION = "not_scoreable_reconstruction"
INVALID_CAUSAL_RECONSTRUCTION = "invalid_causal_reconstruction"
EXCLUDED_NUMERIC_FAILURE = "excluded_numeric_failure"

# El nombre largo facilita la lectura en serializadores y mantiene el contrato
# de estados estable para consumers que importan el evaluador directamente.
NOT_SCOREABLE_TRAINING_ORIGIN_MISSING = "not_scoreable_training_origin_missing"

_SPLIT_WINDOWS: dict[str, tuple[pd.Period | None, pd.Period | None]] = {
    "full": (None, None),
    "2008_2019": (pd.Period("2008-01", freq="M"), pd.Period("2019-12", freq="M")),
    "2020_2022": (pd.Period("2020-01", freq="M"), pd.Period("2022-12", freq="M")),
    "2023_2026": (pd.Period("2023-01", freq="M"), pd.Period("2026-12", freq="M")),
}


class EvaluationError(ValueError):
    """Error de entrada o de contrato del evaluador."""


class NumericEvaluationError(EvaluationError):
    """El ajuste OLS no es finito o no tiene rango suficiente."""


class CausalEvaluationError(EvaluationError):
    """La metadata de una reconstrucción contradice el prefijo causal."""


# ---------------------------------------------------------------------------
# Utilidades pequeñas y contratos auxiliares
# ---------------------------------------------------------------------------


def _timestamp(value: Any, field_name: str = "date") -> pd.Timestamp:
    if value is None or value is pd.NaT:
        raise EvaluationError(f"{field_name} no puede ser nulo")
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise EvaluationError(f"{field_name} no es una fecha válida: {value!r}") from error
    if pd.isna(result):
        raise EvaluationError(f"{field_name} no es una fecha válida: {value!r}")
    if result.tzinfo is not None:
        result = result.tz_convert("UTC").tz_localize(None)
    return result.normalize()


def _period(value: Any, field_name: str = "date") -> pd.Period:
    return _timestamp(value, field_name).to_period("M")


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    return _timestamp(value).strftime("%Y-%m-%d")


def _finite_or_none(value: Any, field_name: str) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise EvaluationError(f"{field_name} debe ser numérico o nulo") from error
    return result if np.isfinite(result) else None


def _source_vintage(snapshot: Any, source_id: str) -> Any | None:
    """Obtiene el vintage sin asumir que un fake store expone todos los aliases."""

    for method_name in ("source", "source_vintage", "get_source_vintage"):
        method = getattr(snapshot, method_name, None)
        if method is None:
            continue
        try:
            return method(source_id)
        except (KeyError, ValueError, TypeError):
            return None
    vintages = getattr(snapshot, "source_vintages", ())
    if isinstance(vintages, Mapping):
        vintages = tuple(vintages.values())
    matches = [item for item in vintages if getattr(item, "source_id", None) == source_id]
    return matches[0] if len(matches) == 1 else None


def _snapshot_manifest(snapshot: Any, vintage: Any | None, origin: ForecastOrigin) -> str | None:
    value = getattr(snapshot, "snapshot_manifest", None)
    if value:
        return str(value)
    value = getattr(origin, "snapshot_manifest", None)
    if value:
        return str(value)
    value = getattr(vintage, "snapshot_manifest", None)
    return str(value) if value else None


def _error_status(error: Any, default: str) -> str:
    value = getattr(error, "scoreability_status", None)
    return str(value).strip() if value else default


def _error_coverage(error: Any, default: str = "incomplete") -> str:
    value = getattr(error, "coverage_status", None)
    value = str(value).strip().lower() if value else default
    return value if value in {"complete", "incomplete", "missing", "invalid"} else default


def _error_reason(error: Any) -> str:
    value = getattr(error, "reason", None)
    return str(value).strip() if value else str(error)


def _period_index(series: pd.Series) -> pd.PeriodIndex:
    try:
        return pd.DatetimeIndex(pd.to_datetime(series.index)).to_period("M")
    except (TypeError, ValueError, OverflowError) as error:
        raise EvaluationError("La serie PIT debe tener un índice mensual interpretable") from error


def _series_missing_counts(series: pd.Series, through: pd.Timestamp) -> tuple[int, int]:
    """Calcula faltantes mensuales sin imputarlos.

    El primer conteo cubre meses ausentes entre la primera y la última
    observación solicitada; el segundo cubre valores nulos presentes en el
    índice. La función solo se usa para el ledger de cobertura.
    """

    if series.empty:
        return 0, 0
    periods = _period_index(series)
    unique_periods = pd.PeriodIndex(sorted(set(periods)), freq="M")
    first = unique_periods.min()
    last = min(unique_periods.max(), through.to_period("M"))
    expected = pd.period_range(first, last, freq="M")
    missing_periods = len(expected.difference(unique_periods))
    values = pd.to_numeric(series, errors="coerce")
    missing_values = int(values.isna().sum())
    return int(missing_periods), missing_values


def _reconstruction_status(result: Any) -> str:
    value = getattr(result, "status", "")
    return str(value).strip().lower()


def _validate_reconstruction_metadata(
    result: Any,
    *,
    origin: ForecastOrigin,
    snapshot: Any,
    source_id: str,
) -> tuple[bool, str | None]:
    """Valida metadata de causalidad y devuelve ``(válida, warning)``."""

    if not isinstance(result, ReconstructionResult):
        # Fakes y adaptadores pueden implementar el protocolo sin usar la clase
        # concreta. Se mantiene la misma validación observable del contrato.
        metadata = getattr(result, "metadata", None)
        if metadata is None:
            return False, "reconstruction_metadata_missing"
    else:
        metadata = result.metadata

    try:
        validate = getattr(metadata, "validate_causal", None)
        if validate is not None:
            validate()
    except (CausalReconstructionError, ValueError, TypeError) as error:
        return False, str(error)

    status = _reconstruction_status(result)
    if status != "causal":
        return False, f"reconstruction_status={status or 'missing'}"

    uses_future = getattr(metadata, "uses_future_observations", None)
    if uses_future is not False:
        return False, "metadata_uses_future_observations"

    metadata_origin = getattr(metadata, "origin_date", None)
    if metadata_origin is not None and _timestamp(metadata_origin) != origin.origin_date:
        return False, "reconstruction_origin_mismatch"

    available_through = getattr(metadata, "available_through", None)
    if available_through is not None and _timestamp(available_through) > origin.effective_cutoff:
        return False, "available_through_after_origin_or_cutoff"
    prefix_last = getattr(metadata, "prefix_last_date", None)
    if prefix_last is None:
        prefix_last = getattr(metadata, "prefix_last", None)
    if prefix_last is not None and _timestamp(prefix_last) > origin.effective_cutoff:
        return False, "prefix_last_date_after_origin_or_cutoff"

    vintage = _source_vintage(snapshot, source_id)
    metadata_vintage = getattr(metadata, "source_vintage", None)
    if vintage is not None and metadata_vintage is not None:
        expected = str(getattr(vintage, "vintage_id", "")).strip()
        if expected and str(metadata_vintage).strip() != expected:
            return False, "reconstruction_source_vintage_mismatch"
    return True, None


# ---------------------------------------------------------------------------
# Predicción por origen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OriginPrediction:
    """Resultado auditable de un candidato en un origen y horizonte.

    Las filas no scoreables se conservan con las predicciones nulas. ``split``
    identifica una vista de la tabla lógica; el ajuste y el benchmark nunca se
    vuelven a ejecutar al proyectar una fila a un sub-split.
    """

    origin_date: pd.Timestamp
    horizon_months: int
    candidate_id: str
    prediction_wavelet: float | None = None
    prediction_random_walk: float | None = None
    observed_forward_return: float | None = None
    label_end_date: pd.Timestamp | None = None
    n_mature_labels: int = 0
    scoreability_status: str = NOT_SCOREABLE_COVERAGE_INCOMPLETE
    coverage_status: str = "incomplete"
    causal_reconstruction: bool = False
    snapshot_manifest: str | None = None
    source_vintage: str | None = None
    split: str = "full"
    prefix_last_date: pd.Timestamp | None = None
    prefix_length: int | None = None
    prefix_sha256: str | None = None
    warning: str | None = None
    minimum_mature_training: int = MINIMUM_MATURE_TRAINING
    data_cutoff: pd.Timestamp | None = None
    experiment_id: str | None = None
    product_id: str | None = None
    research_label: str = "exploratory_research"

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_date", _timestamp(self.origin_date, "origin_date"))
        try:
            horizon = int(self.horizon_months)
        except (TypeError, ValueError, OverflowError) as error:
            raise EvaluationError("horizon_months debe ser entero") from error
        if horizon not in REQUIRED_HORIZONS:
            raise EvaluationError(f"horizon_months debe ser uno de {REQUIRED_HORIZONS!r}")
        object.__setattr__(self, "horizon_months", horizon)
        candidate_id = str(self.candidate_id).strip()
        if not candidate_id:
            raise EvaluationError("candidate_id no puede estar vacío")
        object.__setattr__(self, "candidate_id", candidate_id)

        for field_name in (
            "prediction_wavelet",
            "prediction_random_walk",
            "observed_forward_return",
        ):
            value = _finite_or_none(getattr(self, field_name), field_name)
            if field_name == "prediction_random_walk" and value is not None:
                if value != float(BENCHMARK_RETURN_PREDICTION):
                    raise EvaluationError("Random_Walk_Benchmark debe ser retorno cero")
            object.__setattr__(self, field_name, value)

        if self.label_end_date is not None:
            object.__setattr__(self, "label_end_date", _timestamp(self.label_end_date, "label_end_date"))
        if self.data_cutoff is not None:
            object.__setattr__(self, "data_cutoff", _timestamp(self.data_cutoff, "data_cutoff"))
        if (
            not isinstance(self.n_mature_labels, int)
            or isinstance(self.n_mature_labels, bool)
            or self.n_mature_labels < 0
        ):
            raise EvaluationError("n_mature_labels debe ser entero no negativo")
        if (
            not isinstance(self.minimum_mature_training, int)
            or isinstance(self.minimum_mature_training, bool)
            or self.minimum_mature_training <= 0
        ):
            raise EvaluationError("minimum_mature_training debe ser entero positivo")
        object.__setattr__(self, "scoreability_status", str(self.scoreability_status).strip())
        object.__setattr__(self, "coverage_status", str(self.coverage_status).strip().lower())
        object.__setattr__(self, "split", str(self.split).strip())
        if not self.split:
            raise EvaluationError("split no puede estar vacío")
        if not isinstance(self.causal_reconstruction, (bool, np.bool_)):
            raise EvaluationError("causal_reconstruction debe ser bool")
        object.__setattr__(self, "causal_reconstruction", bool(self.causal_reconstruction))
        if self.prefix_last_date is not None:
            object.__setattr__(self, "prefix_last_date", _timestamp(self.prefix_last_date, "prefix_last_date"))
        if self.prefix_length is not None:
            if (
                not isinstance(self.prefix_length, int)
                or isinstance(self.prefix_length, bool)
                or self.prefix_length <= 0
            ):
                raise EvaluationError("prefix_length debe ser entero positivo o None")
        if self.prefix_sha256 is not None:
            prefix_hash = str(self.prefix_sha256).strip().lower()
            if len(prefix_hash) != 64 or any(c not in "0123456789abcdef" for c in prefix_hash):
                raise EvaluationError("prefix_sha256 debe ser SHA-256 hexadecimal o None")
            object.__setattr__(self, "prefix_sha256", prefix_hash)
        if self.warning is not None:
            object.__setattr__(self, "warning", str(self.warning).strip() or None)
        for field_name in ("snapshot_manifest", "source_vintage", "experiment_id", "product_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, str(value).strip() or None)
        object.__setattr__(self, "research_label", str(self.research_label).strip() or "exploratory_research")

    @property
    def prediction_benchmark(self) -> float | None:
        return self.prediction_random_walk

    @property
    def observed(self) -> float | None:
        return self.observed_forward_return

    @property
    def n_training_labels(self) -> int:
        return self.n_mature_labels

    @property
    def status(self) -> str:
        return self.scoreability_status

    @property
    def is_scoreable(self) -> bool:
        return (
            self.scoreability_status == SCOREABLE
            and self.prediction_wavelet is not None
            and self.prediction_random_walk is not None
            and self.observed_forward_return is not None
        )

    @property
    def logical_key(self) -> tuple[pd.Timestamp, int, str]:
        return self.origin_date, self.horizon_months, self.candidate_id

    @property
    def key(self) -> tuple[pd.Timestamp, int, str, str]:
        return (*self.logical_key, self.split)

    @property
    def causal_metadata(self) -> dict[str, object]:
        return {
            "causal_reconstruction": self.causal_reconstruction,
            "prefix_last_date": _date_text(self.prefix_last_date),
            "prefix_length": self.prefix_length,
            "prefix_sha256": self.prefix_sha256,
            "snapshot_manifest": self.snapshot_manifest,
            "source_vintage": self.source_vintage,
        }

    def with_split(self, split: str) -> "OriginPrediction":
        return replace(self, split=split)

    def as_dict(self) -> dict[str, object]:
        """Serializa una fila sin introducir columnas dependientes de métricas."""

        return {
            "origin_date": _date_text(self.origin_date),
            "horizon_months": self.horizon_months,
            "candidate_id": self.candidate_id,
            "split": self.split,
            "prediction_wavelet": self.prediction_wavelet,
            "prediction_random_walk": self.prediction_random_walk,
            "observed_forward_return": self.observed_forward_return,
            "label_end_date": _date_text(self.label_end_date),
            "n_mature_labels": self.n_mature_labels,
            "minimum_mature_training": self.minimum_mature_training,
            "scoreability_status": self.scoreability_status,
            "coverage_status": self.coverage_status,
            "causal_reconstruction": self.causal_reconstruction,
            "snapshot_manifest": self.snapshot_manifest,
            "source_vintage": self.source_vintage,
            "prefix_last_date": _date_text(self.prefix_last_date),
            "prefix_length": self.prefix_length,
            "prefix_sha256": self.prefix_sha256,
            "warning": self.warning,
            "data_cutoff": _date_text(self.data_cutoff),
            "experiment_id": self.experiment_id,
            "product_id": self.product_id,
            "research_label": self.research_label,
        }

    to_record = as_dict


# ---------------------------------------------------------------------------
# Ajuste OLS y benchmark
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OLSFit:
    """Coeficientes del modelo ``y = intercept + slope * signal``."""

    intercept: float
    slope: float
    n_observations: int
    rank: int = 2
    rcond: None = None

    def __post_init__(self) -> None:
        for name in ("intercept", "slope"):
            value = float(getattr(self, name))
            if not np.isfinite(value):
                raise NumericEvaluationError(f"OLSFit.{name} no es finito")
            object.__setattr__(self, name, value)
        if self.n_observations < 2 or self.rank < 2:
            raise NumericEvaluationError("OLS requiere una matriz de diseño de rango 2")

    @property
    def coefficients(self) -> tuple[float, float]:
        return self.intercept, self.slope

    @property
    def beta(self) -> np.ndarray:
        return np.asarray(self.coefficients, dtype=float)

    def predict(self, signal: Any) -> float | np.ndarray:
        values = np.asarray(signal, dtype=float)
        if not np.isfinite(values).all():
            raise NumericEvaluationError("La señal a predecir contiene valores no finitos")
        result = self.intercept + self.slope * values
        if not np.isfinite(result).all():
            raise NumericEvaluationError("La predicción OLS no es finita")
        return float(result) if values.ndim == 0 else result


OLSResult = OLSFit
DeterministicOLS = OLSFit


def fit_ols(signal: Sequence[float] | np.ndarray, target: Sequence[float] | np.ndarray) -> OLSFit:
    """Ajusta OLS con intercepto mediante ``numpy.linalg.lstsq``.

    No se centra, escala ni regulariza la señal. El orden de las filas que
    recibe la función es el orden temporal de las etiquetas maduras, por lo
    que el resultado es reproducible y auditable.
    """

    x = np.asarray(signal, dtype=float).reshape(-1)
    y = np.asarray(target, dtype=float).reshape(-1)
    if x.size != y.size:
        raise NumericEvaluationError("signal y target deben tener el mismo número de filas")
    if x.size < 2:
        raise NumericEvaluationError("OLS requiere al menos dos observaciones")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise NumericEvaluationError("signal y target deben ser finitos")
    design = np.column_stack((np.ones(x.size, dtype=float), x))
    try:
        coefficients, _residuals, rank, _singular_values = np.linalg.lstsq(
            design,
            y,
            rcond=None,
        )
    except (np.linalg.LinAlgError, ValueError, TypeError) as error:
        raise NumericEvaluationError(f"fallo numérico de OLS: {error}") from error
    coefficients = np.asarray(coefficients, dtype=float).reshape(-1)
    if coefficients.size != 2 or int(rank) < 2 or not np.isfinite(coefficients).all():
        raise NumericEvaluationError("la matriz OLS no es resoluble con rango completo")
    return OLSFit(
        intercept=float(coefficients[0]),
        slope=float(coefficients[1]),
        n_observations=int(x.size),
        rank=int(rank),
    )


def fit_ols_intercept_signal(
    signal: Sequence[float] | np.ndarray,
    target: Sequence[float] | np.ndarray,
) -> OLSFit:
    return fit_ols(signal, target)


fit_deterministic_ols = fit_ols


def random_walk_benchmark(*_args: Any, **_kwargs: Any) -> float:
    """Devuelve el benchmark preinscrito: retorno forward cero."""

    return float(BENCHMARK_RETURN_PREDICTION)


random_walk_prediction = random_walk_benchmark
benchmark_return_zero = random_walk_benchmark


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------


def assign_evaluation_splits(
    origin_date: Any,
    *,
    data_cutoff: Any | None = None,
    splits: Iterable[str] = REQUIRED_SPLITS,
) -> tuple[str, ...]:
    """Asigna un origen a ``full`` y, como máximo, una submuestra.

    Las fronteras son inclusivas a nivel de mes. ``2023_2026`` además queda
    truncado por ``data_cutoff``; no se crean orígenes posteriores al corte.
    """

    date = _timestamp(origin_date, "origin_date")
    period = date.to_period("M")
    requested = tuple(str(item) for item in splits)
    unknown = sorted(set(requested) - set(REQUIRED_SPLITS))
    if unknown:
        raise EvaluationError(f"splits no soportados: {unknown!r}")
    cutoff_period = None if data_cutoff is None else _period(data_cutoff, "data_cutoff")
    if cutoff_period is not None and period > cutoff_period:
        return ()

    assigned: list[str] = []
    for split in requested:
        start, end = _SPLIT_WINDOWS[split]
        if split == "full":
            assigned.append(split)
            continue
        if start is not None and period < start:
            continue
        if end is not None and period > end:
            continue
        if split == "2023_2026" and cutoff_period is not None and period > cutoff_period:
            continue
        assigned.append(split)
    return tuple(assigned)


# Common aliases used by adapters and tests.
assign_splits = assign_evaluation_splits
splits_for_origin = assign_evaluation_splits
split_for_origin = assign_evaluation_splits
split_membership = assign_evaluation_splits


def assign_split(
    origin_date: Any,
    split: str | None = None,
    *,
    data_cutoff: Any | None = None,
    splits: Iterable[str] = REQUIRED_SPLITS,
) -> tuple[str, ...] | bool:
    assigned = assign_evaluation_splits(origin_date, data_cutoff=data_cutoff, splits=splits)
    if split is None:
        return assigned
    return str(split) in assigned


# ---------------------------------------------------------------------------
# Bundle de evaluación
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationBundle:
    """Predicciones y cobertura de una corrida walk-forward.

    ``predictions`` contiene las vistas de split. ``logical_predictions``
    devuelve solo ``full`` y permite verificar que las otras vistas son una
    proyección exacta, sin reestimación.
    """

    predictions: tuple[OriginPrediction, ...]
    coverage: tuple[dict[str, object], ...] = ()
    metrics: tuple[Any, ...] = ()
    decisions: tuple[Mapping[str, object], ...] = ()
    plan: ResearchPlan | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "predictions", tuple(self.predictions))
        object.__setattr__(self, "coverage", tuple(dict(row) for row in self.coverage))
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "decisions", tuple(dict(row) for row in self.decisions))

    @property
    def origin_predictions(self) -> tuple[OriginPrediction, ...]:
        return tuple(row for row in self.predictions if row.split == "full")

    @property
    def logical_predictions(self) -> tuple[OriginPrediction, ...]:
        return self.origin_predictions

    @property
    def split_predictions(self) -> tuple[OriginPrediction, ...]:
        return self.predictions

    @property
    def all_predictions(self) -> tuple[OriginPrediction, ...]:
        return self.predictions

    @property
    def predictions_by_split(self) -> dict[str, tuple[OriginPrediction, ...]]:
        split_names = tuple(self.plan.splits) if self.plan is not None else REQUIRED_SPLITS
        result: dict[str, list[OriginPrediction]] = {str(split): [] for split in split_names}
        for row in self.predictions:
            result.setdefault(row.split, []).append(row)
        return {key: tuple(value) for key, value in result.items()}

    @property
    def counts(self) -> dict[tuple[str, int, str], dict[str, int]]:
        """Conteos auditables por candidato, horizonte y vista temporal."""

        grouped: dict[tuple[str, int, str], list[OriginPrediction]] = {}
        for row in self.predictions:
            grouped.setdefault((row.candidate_id, row.horizon_months, row.split), []).append(row)
        result: dict[tuple[str, int, str], dict[str, int]] = {}
        for key, rows in grouped.items():
            requested = len({row.origin_date for row in rows})
            scoreable = sum(1 for row in rows if row.is_scoreable)
            result[key] = {
                "n_requested_origins": requested,
                "n_scoreable_origins": scoreable,
                "n_excluded_origins": requested - scoreable,
                "n_oos": scoreable,
            }
        return result

    @property
    def counts_by_candidate_horizon_split(self) -> dict[tuple[str, int, str], dict[str, int]]:
        return self.counts

    def prediction_frame(self) -> pd.DataFrame:
        columns = list(OriginPrediction(  # type: ignore[arg-type]
            origin_date=pd.Timestamp("2000-01-01"),
            horizon_months=6,
            candidate_id="_schema",
        ).as_dict().keys())
        rows = [row.as_dict() for row in self.predictions]
        return pd.DataFrame(rows, columns=columns)

    to_frame = prediction_frame
    predictions_frame = prediction_frame

    def coverage_frame(self) -> pd.DataFrame:
        if not self.coverage:
            return pd.DataFrame()
        columns = sorted({key for row in self.coverage for key in row})
        return pd.DataFrame(self.coverage, columns=columns)

    def split_rows(self, split: str) -> tuple[OriginPrediction, ...]:
        return self.predictions_by_split.get(str(split), ())

    def as_dict(self) -> dict[str, object]:
        return {
            "predictions": [row.as_dict() for row in self.predictions],
            "coverage": [dict(row) for row in self.coverage],
            "counts": [
                {
                    "candidate_id": candidate_id,
                    "horizon_months": horizon,
                    "split": split,
                    **values,
                }
                for (candidate_id, horizon, split), values in sorted(self.counts.items())
            ],
            "metrics": [dict(item) if isinstance(item, Mapping) else item for item in self.metrics],
            "decisions": [dict(item) for item in self.decisions],
        }


@dataclass
class _OriginContext:
    origin: ForecastOrigin
    snapshot: PointInTimeSnapshot | Any | None = None
    series: pd.Series | None = None
    reconstruction: ReconstructionResult | Any | None = None
    status: str = SCOREABLE
    coverage_status: str = "complete"
    reason: str | None = None
    source_vintage: Any | None = None
    snapshot_manifest: str | None = None
    prefix_last_date: pd.Timestamp | None = None
    prefix_length: int | None = None
    prefix_sha256: str | None = None
    n_observations_available: int = 0
    n_missing: int = 0

    @property
    def valid(self) -> bool:
        return self.status == SCOREABLE and self.reconstruction is not None


# ---------------------------------------------------------------------------
# Evaluador walk-forward
# ---------------------------------------------------------------------------


class _ResolverProtocol(Protocol):
    def resolve(self, origin: ForecastOrigin, required_source_ids: tuple[str, ...]) -> Any:
        ...


class _StoreProtocol(Protocol):
    def monthly_series(
        self,
        snapshot: Any,
        source_id: str,
        *,
        through: pd.Timestamp,
    ) -> pd.Series:
        ...


class OOS_Evaluator:
    """Coordina una evaluación causal expanding por origen.

    ``label_series``/``trm_monthly`` es opcional. Cuando se proporciona, se
    usa exclusivamente para construir outcomes y etiquetas; jamás se entrega
    a ``OriginReconstructor``. Las features siempre salen de
    ``PointInTimeSeriesStore``. Si se omite, la serie PIT del origen se usa
    como panel de etiquetas y, por construcción, no puede aportar un target
    forward todavía no observado.
    """

    def __init__(
        self,
        snapshot_resolver: _ResolverProtocol | None = None,
        series_store: _StoreProtocol | None = None,
        origin_reconstructor: OriginReconstructor | None = None,
        label_builder: ForwardLabelBuilder | None = None,
        *,
        snapshot_store: _ResolverProtocol | None = None,
        reconstructor: OriginReconstructor | None = None,
        target_series: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
        label_series: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
        required_source_ids: Iterable[str] = (BANREP_TRM_SOURCE_ID,),
        coverage_ledger: Any | None = None,
    ) -> None:
        if snapshot_resolver is not None and snapshot_store is not None and snapshot_resolver is not snapshot_store:
            raise TypeError("snapshot_resolver y snapshot_store son aliases incompatibles")
        if origin_reconstructor is not None and reconstructor is not None and origin_reconstructor is not reconstructor:
            raise TypeError("origin_reconstructor y reconstructor son aliases incompatibles")
        self.snapshot_resolver = snapshot_resolver or snapshot_store
        self.series_store = series_store
        self.origin_reconstructor = origin_reconstructor or reconstructor
        self.label_builder = label_builder
        if target_series is not None and label_series is not None and target_series is not label_series:
            raise TypeError("target_series y label_series son aliases incompatibles")
        self.label_series = label_series if label_series is not None else target_series
        self.required_source_ids = tuple(dict.fromkeys(str(item).strip() for item in required_source_ids))
        if not self.required_source_ids:
            self.required_source_ids = (BANREP_TRM_SOURCE_ID,)
        self.coverage_ledger = coverage_ledger

        self._contexts: dict[pd.Timestamp, _OriginContext] = {}
        self._coverage: dict[tuple[str, pd.Timestamp, int], dict[str, object]] = {}
        self._configured_origins: dict[pd.Period, ForecastOrigin] = {}
        self._plan: ResearchPlan | None = None

    # -- dependency construction ------------------------------------------

    def _resolver(self) -> _ResolverProtocol:
        if self.snapshot_resolver is None:
            self.snapshot_resolver = SnapshotResolver(coverage_ledger=self.coverage_ledger)
        return self.snapshot_resolver

    def _store(self) -> _StoreProtocol:
        if self.series_store is None:
            self.series_store = PointInTimeSeriesStore(coverage_ledger=self.coverage_ledger)
        return self.series_store

    def _reconstructor(self) -> OriginReconstructor:
        if self.origin_reconstructor is None:
            self.origin_reconstructor = OriginReconstructor()
        return self.origin_reconstructor

    def _labels(self, plan: ResearchPlan) -> ForwardLabelBuilder:
        if self.label_builder is None:
            self.label_builder = ForwardLabelBuilder.from_plan(plan)
        return self.label_builder

    # -- origin and dependency adapters -----------------------------------

    @staticmethod
    def _origin_from_value(value: Any, plan: ResearchPlan) -> ForecastOrigin:
        if isinstance(value, ForecastOrigin):
            if value.data_cutoff != plan.data_cutoff:
                return ForecastOrigin(
                    origin_date=value.origin_date,
                    origin_period=value.origin_period,
                    data_cutoff=plan.data_cutoff,
                    snapshot_manifest=value.snapshot_manifest,
                )
            return value
        return ForecastOrigin(origin_date=_timestamp(value, "origin_date"), data_cutoff=plan.data_cutoff)

    def _configured_origin(self, value: Any) -> ForecastOrigin | None:
        period = _period(value, "training_origin")
        return self._configured_origins.get(period)

    def _resolve_snapshot(self, origin: ForecastOrigin) -> Any:
        resolver = self._resolver()
        try:
            return resolver.resolve(origin, self.required_source_ids)
        except TypeError as first_error:
            # Adapters antiguos del protocolo solo aceptaban ``origin``. El
            # fallback no cambia la fuente requerida ni permite un fallback de
            # datos; únicamente adapta la firma.
            try:
                return resolver.resolve(origin)  # type: ignore[call-arg]
            except TypeError:
                raise first_error

    def _read_series(self, snapshot: Any, origin: ForecastOrigin, plan: ResearchPlan) -> pd.Series:
        store = self._store()
        try:
            series = store.monthly_series(
                snapshot,
                plan.target_series,
                through=origin.effective_cutoff,
            )
        except TypeError as first_error:
            try:
                series = store.monthly_series(
                    snapshot,
                    plan.target_series,
                    origin.effective_cutoff,
                )  # type: ignore[call-arg]
            except TypeError:
                raise first_error
        if not isinstance(series, pd.Series):
            raise SnapshotSeriesError(
                "PointInTimeSeriesStore debe devolver pandas.Series",
                origin=origin,
                source_id=plan.target_series,
                coverage_status="invalid",
                scoreability_status=NOT_SCOREABLE_SNAPSHOT_INVALID,
                reason="pit_series_not_series",
            )
        if series.empty:
            raise SnapshotSeriesError(
                "El snapshot PIT no contiene observaciones mensuales",
                origin=origin,
                source_id=plan.target_series,
                coverage_status="missing",
                scoreability_status=NOT_SCOREABLE_SOURCE_MISSING,
                reason="pit_series_empty",
            )
        series = series.copy(deep=True)
        dates = pd.to_datetime(series.index, errors="coerce")
        if dates.isna().any():
            raise SnapshotSeriesError(
                "La serie PIT contiene fechas inválidas",
                origin=origin,
                source_id=plan.target_series,
                coverage_status="invalid",
                scoreability_status=NOT_SCOREABLE_SNAPSHOT_INVALID,
                reason="pit_series_invalid_index",
            )
        if getattr(dates, "tz", None) is not None:
            dates = dates.tz_convert("UTC").tz_localize(None)
        dates = dates.normalize()
        if bool((dates > origin.effective_cutoff).any()):
            raise SnapshotSeriesError(
                "La serie PIT contiene observaciones posteriores al origen/corte",
                origin=origin,
                source_id=plan.target_series,
                coverage_status="incomplete",
                scoreability_status=NOT_SCOREABLE_COVERAGE_INCOMPLETE,
                reason="observation_after_origin_or_cutoff",
            )
        series.index = dates
        return series.sort_index()

    def _call_reconstructor(
        self,
        origin: ForecastOrigin,
        snapshot: Any,
        series: pd.Series,
        plan: ResearchPlan,
    ) -> Any:
        reconstructor = self._reconstructor()
        method = getattr(reconstructor, "reconstruct", None)
        if method is None:
            method = getattr(reconstructor, "reconstruct_origin", None)
        if method is None:
            raise CausalReconstructionError("El OriginReconstructor no expone reconstruct")
        return method(origin, snapshot, series, plan)

    @staticmethod
    def _snapshot_valid(snapshot: Any) -> bool:
        valid = getattr(snapshot, "valid", None)
        return bool(valid) if valid is not None else True

    def _context_for(self, origin: ForecastOrigin, plan: ResearchPlan) -> _OriginContext:
        cached = self._contexts.get(origin.origin_date)
        if cached is not None:
            return cached
        context = _OriginContext(origin=origin)
        self._contexts[origin.origin_date] = context

        try:
            snapshot = self._resolve_snapshot(origin)
            context.snapshot = snapshot
        except SnapshotResolutionError as error:
            context.status = _error_status(error, NOT_SCOREABLE_SNAPSHOT_INVALID)
            context.coverage_status = _error_coverage(error)
            context.reason = _error_reason(error)
            context.snapshot_manifest = getattr(error, "snapshot_manifest", None)
            self._record_context_coverage(context, plan)
            return context
        except (SnapshotSeriesError, KeyError, ValueError, TypeError) as error:
            context.status = _error_status(error, NOT_SCOREABLE_SNAPSHOT_INVALID)
            context.coverage_status = _error_coverage(error)
            context.reason = _error_reason(error)
            self._record_context_coverage(context, plan)
            return context

        if not self._snapshot_valid(snapshot):
            context.status = _error_status(snapshot, NOT_SCOREABLE_SNAPSHOT_INVALID)
            context.coverage_status = _error_coverage(snapshot)
            context.reason = getattr(snapshot, "reason", None) or "snapshot_not_valid"
            context.snapshot_manifest = getattr(snapshot, "snapshot_manifest", None)
            self._record_context_coverage(context, plan)
            return context

        vintage = _source_vintage(snapshot, plan.target_series)
        context.source_vintage = vintage
        context.snapshot_manifest = _snapshot_manifest(snapshot, vintage, origin)
        if vintage is None:
            context.status = NOT_SCOREABLE_SOURCE_MISSING
            context.coverage_status = "missing"
            context.reason = "source_vintage_missing"
            self._record_context_coverage(context, plan)
            return context

        snapshot_origin = getattr(snapshot, "origin", None)
        snapshot_origin_date = getattr(snapshot_origin, "origin_date", None)
        if snapshot_origin_date is not None and _timestamp(snapshot_origin_date) != origin.origin_date:
            context.status = NOT_SCOREABLE_SNAPSHOT_INVALID
            context.coverage_status = "invalid"
            context.reason = "snapshot_origin_mismatch"
            self._record_context_coverage(context, plan)
            return context
        vintage_available = getattr(vintage, "available_through", None)
        if vintage_available is not None and _timestamp(vintage_available) > origin.effective_cutoff:
            context.status = NOT_SCOREABLE_COVERAGE_INCOMPLETE
            context.coverage_status = "incomplete"
            context.reason = "available_through_after_origin_or_cutoff"
            self._record_context_coverage(context, plan)
            return context

        try:
            series = self._read_series(snapshot, origin, plan)
            context.series = series
            context.n_observations_available = int(pd.to_numeric(series, errors="coerce").notna().sum())
            missing_periods, missing_values = _series_missing_counts(series, origin.effective_cutoff)
            context.n_missing = missing_periods + missing_values
            if context.n_missing:
                context.status = NOT_SCOREABLE_COVERAGE_INCOMPLETE
                context.coverage_status = "incomplete"
                context.reason = "missing_months_without_imputation"
                self._record_context_coverage(context, plan)
                return context
        except SnapshotSeriesError as error:
            context.status = _error_status(error, NOT_SCOREABLE_COVERAGE_INCOMPLETE)
            context.coverage_status = _error_coverage(error)
            context.reason = _error_reason(error)
            self._record_context_coverage(context, plan)
            return context
        except (KeyError, ValueError, TypeError) as error:
            context.status = NOT_SCOREABLE_SNAPSHOT_INVALID
            context.coverage_status = "invalid"
            context.reason = str(error)
            self._record_context_coverage(context, plan)
            return context

        try:
            reconstruction = self._call_reconstructor(origin, snapshot, series, plan)
            context.reconstruction = reconstruction
            valid, warning = _validate_reconstruction_metadata(
                reconstruction,
                origin=origin,
                snapshot=snapshot,
                source_id=plan.target_series,
            )
            if not valid:
                context.status = (
                    INVALID_CAUSAL_RECONSTRUCTION
                    if warning and (
                        "future" in warning
                        or "prefix" in warning
                        or "causal" in warning
                        or "origin" in warning
                    )
                    else NOT_SCOREABLE_RECONSTRUCTION
                )
                context.coverage_status = "complete"
                context.reason = warning
                self._record_context_coverage(context, plan)
                return context
        except CausalReconstructionError as error:
            context.status = NOT_SCOREABLE_RECONSTRUCTION
            context.coverage_status = "complete"
            context.reason = str(error)
            self._record_context_coverage(context, plan)
            return context
        except (KeyError, ValueError, TypeError, np.linalg.LinAlgError) as error:
            context.status = NOT_SCOREABLE_RECONSTRUCTION
            context.coverage_status = "complete"
            context.reason = str(error)
            self._record_context_coverage(context, plan)
            return context

        metadata = getattr(context.reconstruction, "metadata", None)
        context.prefix_last_date = getattr(metadata, "prefix_last_date", None)
        if context.prefix_last_date is None:
            context.prefix_last_date = getattr(metadata, "prefix_last", None)
        if context.prefix_last_date is not None:
            context.prefix_last_date = _timestamp(context.prefix_last_date)
        context.prefix_length = getattr(metadata, "prefix_length", None)
        context.prefix_sha256 = getattr(metadata, "prefix_sha256", None)
        context.status = SCOREABLE
        context.coverage_status = "complete"
        self._record_context_coverage(context, plan)
        return context

    # -- coverage ----------------------------------------------------------

    def _record_context_coverage(self, context: _OriginContext, plan: ResearchPlan) -> None:
        vintage = context.source_vintage
        source_id = plan.target_series
        for horizon in plan.horizons:
            key = (source_id, context.origin.origin_date, int(horizon))
            if key in self._coverage:
                continue
            row: dict[str, object] = {
                "source_id": source_id,
                "origin_date": _date_text(context.origin.origin_date),
                "horizon_months": int(horizon),
                "snapshot_manifest": context.snapshot_manifest,
                "source_vintage": getattr(vintage, "vintage_id", None),
                "available_through": _date_text(getattr(vintage, "available_through", None)),
                "sha256": getattr(vintage, "sha256", None),
                "n_observations_available": context.n_observations_available,
                "n_missing": context.n_missing,
                "coverage_status": context.coverage_status,
                "scoreability_status": context.status,
                "required_for_candidate": True,
                "excluded_origins": [],
                "reason": context.reason,
            }
            self._coverage[key] = row

    def _merge_external_coverage(self) -> None:
        ledgers: list[Any] = []
        for dependency in (self.snapshot_resolver, self.series_store, self.coverage_ledger):
            ledger = getattr(dependency, "coverage_ledger", None) if dependency is not None else None
            if ledger is not None:
                ledgers.append(ledger)
        for ledger in ledgers:
            records = getattr(ledger, "records", ())
            if callable(records):
                records = records()
            for record in records:
                if hasattr(record, "as_dict"):
                    row = record.as_dict()
                elif isinstance(record, Mapping):
                    row = dict(record)
                else:
                    continue
                try:
                    key = (
                        str(row["source_id"]),
                        _timestamp(row["origin_date"]),
                        int(row["horizon_months"]),
                    )
                except (KeyError, TypeError, ValueError, EvaluationError):
                    continue
                current = self._coverage.get(key)
                if current is None or current.get("coverage_status") != "complete":
                    self._coverage[key] = row

    # -- labels and signals -----------------------------------------------

    def _label_series_for(
        self,
        origin: ForecastOrigin,
        fallback: pd.Series | None,
        override: Any | None,
    ) -> pd.Series | None:
        provider = override if override is not None else self.label_series
        if provider is None:
            return fallback
        if isinstance(provider, pd.Series):
            return provider
        if callable(provider):
            value = provider(origin)
            return value if isinstance(value, pd.Series) else None
        if isinstance(provider, Mapping):
            candidates: list[Any] = [
                origin,
                origin.origin_date,
                origin.origin_period,
                str(origin.origin_date),
                str(origin.origin_date.to_period("M")),
            ]
            for candidate in candidates:
                try:
                    value = provider[candidate]
                except (KeyError, TypeError):
                    continue
                return value if isinstance(value, pd.Series) else None
            return None
        raise TypeError("label_series debe ser pandas.Series, mapping o callable")

    def _label_results(
        self,
        origin: ForecastOrigin,
        plan: ResearchPlan,
        series: pd.Series | None,
    ) -> dict[int, ScoreabilityResult]:
        builder = self._labels(plan)
        if series is None:
            # No se inventa un target cuando no existe un panel de outcomes.
            return {
                horizon: ScoreabilityResult(
                    origin_period=origin.origin_period,
                    horizon_months=horizon,
                    mature_labels=(),
                    n_mature_labels=0,
                    minimum_mature_training=plan.minimum_mature_training,
                    status=NOT_SCOREABLE_INSUFFICIENT_TRAINING,
                    training_status=NOT_SCOREABLE_INSUFFICIENT_TRAINING,
                    target_label=None,
                    target_status=NOT_EVALUABLE_LABEL_NOT_MATURE,
                    reason="label_series_missing",
                )
                for horizon in plan.horizons
            }
        results: dict[int, ScoreabilityResult] = {}
        built = builder.build_all(series)
        for horizon in plan.horizons:
            labels = built[horizon]
            results[horizon] = builder.assess_origin(labels, origin, horizon)
        return results

    @staticmethod
    def _signal_value(reconstruction: Any, candidate: CandidateSpecification) -> float:
        method = getattr(reconstruction, "signal_value", None)
        if method is not None:
            value = method(candidate)
            finite = _finite_or_none(value, "candidate_signal")
            if finite is None:
                raise CausalEvaluationError("candidate_signal no es finita")
            return finite

        signals = getattr(reconstruction, "signals", None)
        if signals is None:
            signals = getattr(reconstruction, "candidate_signals", None)
        if signals is not None and candidate.candidate_id in signals:
            series = signals[candidate.candidate_id]
            values = np.asarray(series, dtype=float).reshape(-1)
            if values.size == 0 or not np.isfinite(values).all():
                raise CausalEvaluationError("candidate_signal no es finita")
            return float(values[-1])

        components = getattr(reconstruction, "components", None)
        if components is None:
            raise CausalEvaluationError(f"No hay señal para {candidate.candidate_id!r}")
        values: pd.Series | None = None
        for component in candidate.components:
            current = components.get(component)
            if current is None:
                raise CausalEvaluationError(
                    f"No hay componente {component!r} para {candidate.candidate_id!r}"
                )
            values = current.copy(deep=True) if values is None else values + current
        if values is None or values.empty:
            raise CausalEvaluationError("La combinación de componentes está vacía")
        values = values * float(candidate.signal_scale)
        result = _finite_or_none(values.iloc[-1], "candidate_signal")
        if result is None:
            raise CausalEvaluationError("candidate_signal no es finita")
        return result

    def _training_context_for_label(
        self,
        label: MatureLabel,
        plan: ResearchPlan,
    ) -> _OriginContext:
        configured = self._configured_origin(label.origin_date)
        if configured is None:
            # La etiqueta identifica un origen real, pero la configuración no
            # autorizó resolver su snapshot. No se fabrica un origen adicional.
            return _OriginContext(
                origin=ForecastOrigin(origin_date=label.origin_date, data_cutoff=plan.data_cutoff),
                status=NOT_SCOREABLE_TRAINING_ORIGIN_MISSING,
                coverage_status="missing",
                reason="training_origin_not_configured",
            )
        return self._context_for(configured, plan)

    def _fit_candidate(
        self,
        candidate: CandidateSpecification,
        labels: tuple[MatureLabel, ...],
        current_context: _OriginContext,
        plan: ResearchPlan,
    ) -> tuple[OLSFit, float] | tuple[None, str, str]:
        train_signals: list[float] = []
        train_targets: list[float] = []
        for label in labels:
            training_context = self._training_context_for_label(label, plan)
            if not training_context.valid:
                return (
                    None,
                    training_context.status,
                    training_context.reason or "training_context_not_scoreable",
                )
            try:
                train_signals.append(self._signal_value(training_context.reconstruction, candidate))
            except (CausalEvaluationError, KeyError, ValueError, TypeError) as error:
                return None, NOT_SCOREABLE_RECONSTRUCTION, str(error)
            target = label.usable_value
            if target is None or not np.isfinite(float(target)):
                return None, NOT_EVALUABLE_LABEL_NOT_MATURE, "training_label_not_observed"
            train_targets.append(float(target))

        try:
            fit = fit_ols(train_signals, train_targets)
            current_signal = self._signal_value(current_context.reconstruction, candidate)
            prediction = fit.predict(current_signal)
        except NumericEvaluationError as error:
            return None, EXCLUDED_NUMERIC_FAILURE, str(error)
        except (CausalEvaluationError, KeyError, ValueError, TypeError) as error:
            return None, NOT_SCOREABLE_RECONSTRUCTION, str(error)
        if not np.isfinite(float(prediction)):
            return None, EXCLUDED_NUMERIC_FAILURE, "prediction_not_finite"
        return fit, float(prediction)

    # -- public evaluation -------------------------------------------------

    def evaluate(
        self,
        plan: ResearchPlan,
        *,
        trm_monthly: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
        label_series: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
    ) -> EvaluationBundle:
        """Ejecuta la tabla lógica y sus vistas de split de forma determinista."""

        if not isinstance(plan, ResearchPlan):
            raise TypeError("evaluate requiere un ResearchPlan")
        plan.validate()
        if not plan.is_frozen:
            raise EvaluationError("ResearchPlan debe estar congelado antes de evaluar")
        self._plan = plan
        self._contexts = {}
        self._coverage = {}
        self._configured_origins = {}
        for value in plan.origin_dates:
            origin = self._origin_from_value(value, plan)
            self._configured_origins.setdefault(origin.origin_date.to_period("M"), origin)

        override_labels = label_series if label_series is not None else trm_monthly
        logical_rows: list[OriginPrediction] = []
        split_rows: list[OriginPrediction] = []

        candidates = tuple(plan.candidates)
        for configured_value in plan.origin_dates:
            origin = self._origin_from_value(configured_value, plan)
            label_panel = self._label_series_for(origin, None, override_labels)
            current_context = self._context_for(origin, plan)
            fallback_panel = current_context.series
            if label_panel is None:
                label_panel = self._label_series_for(origin, fallback_panel, override_labels)
            label_results = self._label_results(origin, plan, label_panel)

            assigned_splits = assign_evaluation_splits(
                origin.origin_date,
                data_cutoff=plan.data_cutoff,
                splits=plan.splits,
            )
            if not assigned_splits:
                continue

            for horizon in plan.horizons:
                scoreability = label_results[horizon]
                target_value = (
                    scoreability.target_label.usable_value
                    if scoreability.target_status == SCOREABLE and scoreability.target_label is not None
                    else None
                )
                target_end = scoreability.label_end_date
                for candidate in candidates:
                    status = current_context.status if not current_context.valid else scoreability.status
                    warning = current_context.reason if not current_context.valid else scoreability.reason
                    prediction: float | None = None
                    benchmark: float | None = None
                    causal = current_context.valid

                    if current_context.valid and scoreability.training_status != SCOREABLE:
                        status = scoreability.training_status
                        warning = scoreability.reason or "insufficient_mature_training"
                    elif current_context.valid and scoreability.target_status != SCOREABLE:
                        # La predicción no se completa si el target aún no es
                        # observable por Data_Cutoff o no existe en el panel.
                        status = scoreability.target_status or NOT_EVALUABLE_LABEL_NOT_MATURE
                        warning = scoreability.reason or "forward_label_not_mature"
                    elif current_context.valid:
                        result = self._fit_candidate(
                            candidate,
                            scoreability.mature_labels,
                            current_context,
                            plan,
                        )
                        if result[0] is None:
                            _fit, fit_status, fit_warning = result
                            status = fit_status
                            warning = fit_warning
                            # Un contexto histórico inválido hace que la
                            # evidencia causal de la fila no sea completa.
                            if fit_status != EXCLUDED_NUMERIC_FAILURE:
                                causal = False
                        else:
                            _fit, prediction = result
                            benchmark = random_walk_benchmark()
                            status = SCOREABLE
                            warning = None

                    base = OriginPrediction(
                        origin_date=origin.origin_date,
                        horizon_months=horizon,
                        candidate_id=candidate.candidate_id,
                        prediction_wavelet=prediction,
                        prediction_random_walk=benchmark,
                        observed_forward_return=target_value,
                        label_end_date=target_end,
                        n_mature_labels=scoreability.n_mature_labels,
                        scoreability_status=status,
                        coverage_status=current_context.coverage_status,
                        causal_reconstruction=causal,
                        snapshot_manifest=current_context.snapshot_manifest,
                        source_vintage=getattr(current_context.source_vintage, "vintage_id", None),
                        split="full",
                        prefix_last_date=current_context.prefix_last_date,
                        prefix_length=current_context.prefix_length,
                        prefix_sha256=current_context.prefix_sha256,
                        warning=warning,
                        minimum_mature_training=plan.minimum_mature_training,
                        data_cutoff=plan.data_cutoff,
                        experiment_id=plan.experiment_id,
                        product_id=plan.product_id,
                    )
                    logical_rows.append(base)
                    for split in assigned_splits:
                        split_rows.append(base.with_split(split))

        self._merge_external_coverage()
        ordered_rows = tuple(
            sorted(
                split_rows,
                key=lambda row: (
                    row.origin_date,
                    row.horizon_months,
                    row.candidate_id,
                    tuple(REQUIRED_SPLITS).index(row.split)
                    if row.split in REQUIRED_SPLITS
                    else len(REQUIRED_SPLITS),
                ),
            )
        )
        coverage_rows = tuple(
            self._coverage[key]
            for key in sorted(self._coverage, key=lambda value: (value[1], value[2], value[0]))
        )
        return EvaluationBundle(
            predictions=ordered_rows,
            coverage=coverage_rows,
            plan=plan,
        )

    evaluate_walk_forward = evaluate
    walk_forward = evaluate

    def evaluate_origin(
        self,
        plan: ResearchPlan,
        origin: Any,
        *,
        trm_monthly: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
        label_series: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
    ) -> tuple[OriginPrediction, ...]:
        """Evalúa un origen y devuelve sus filas de la vista ``full``.

        Es un adaptador útil para inspección; la ejecución oficial debe usar
        :meth:`evaluate`, que garantiza la proyección común de splits.
        """

        if not isinstance(plan, ResearchPlan):
            raise TypeError("evaluate_origin requiere un ResearchPlan")
        selected = _timestamp(origin, "origin_date")
        if selected not in tuple(_timestamp(item.origin_date if isinstance(item, ForecastOrigin) else item) for item in plan.origin_dates):
            raise EvaluationError("origin no pertenece a ResearchPlan.origin_dates")
        single = replace(plan, origin_dates=(selected,), plan_hash="")
        single.freeze()
        bundle = self.evaluate(single, trm_monthly=trm_monthly, label_series=label_series)
        return bundle.origin_predictions


# Alternate spelling used in some Python call sites.
OOSEvaluator = OOS_Evaluator
WalkForwardEvaluator = OOS_Evaluator


def evaluate_walk_forward(
    plan: ResearchPlan,
    *,
    snapshot_resolver: _ResolverProtocol | None = None,
    series_store: _StoreProtocol | None = None,
    origin_reconstructor: OriginReconstructor | None = None,
    reconstructor: OriginReconstructor | None = None,
    label_builder: ForwardLabelBuilder | None = None,
    trm_monthly: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
    label_series: pd.Series | Mapping[Any, pd.Series] | Callable[[ForecastOrigin], pd.Series] | None = None,
    coverage_ledger: Any | None = None,
) -> EvaluationBundle:
    """Función de conveniencia para ejecutar una corrida sin instanciar la clase."""

    evaluator = OOS_Evaluator(
        snapshot_resolver=snapshot_resolver,
        series_store=series_store,
        origin_reconstructor=origin_reconstructor,
        reconstructor=reconstructor,
        label_builder=label_builder,
        coverage_ledger=coverage_ledger,
        label_series=label_series if label_series is not None else trm_monthly,
    )
    return evaluator.evaluate(plan, trm_monthly=trm_monthly, label_series=label_series)


walk_forward = evaluate_walk_forward


__all__ = [
    "BENCHMARK_RETURN_PREDICTION",
    "CausalEvaluationError",
    "DeterministicOLS",
    "EvaluationBundle",
    "EvaluationError",
    "EXCLUDED_NUMERIC_FAILURE",
    "INVALID_CAUSAL_RECONSTRUCTION",
    "NOT_EVALUABLE_LABEL_NOT_MATURE",
    "NOT_SCOREABLE_COVERAGE_INCOMPLETE",
    "NOT_SCOREABLE_INSUFFICIENT_TRAINING",
    "NOT_SCOREABLE_RECONSTRUCTION",
    "NOT_SCOREABLE_SNAPSHOT_INVALID",
    "NOT_SCOREABLE_SNAPSHOT_MISSING",
    "NOT_SCOREABLE_SOURCE_MISSING",
    "NOT_SCOREABLE_TRAINING_ORIGIN_MISSING",
    "NumericEvaluationError",
    "OLSFit",
    "OLSResult",
    "OOS_Evaluator",
    "OOSEvaluator",
    "OriginPrediction",
    "REQUIRED_SPLITS",
    "SCOREABLE",
    "WalkForwardEvaluator",
    "assign_evaluation_splits",
    "assign_split",
    "assign_splits",
    "benchmark_return_zero",
    "evaluate_walk_forward",
    "fit_deterministic_ols",
    "fit_ols",
    "fit_ols_intercept_signal",
    "random_walk_benchmark",
    "random_walk_prediction",
    "split_membership",
    "split_for_origin",
    "splits_for_origin",
    "walk_forward",
]
