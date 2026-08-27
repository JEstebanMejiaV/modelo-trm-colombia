"""Métricas OOS y selección determinista de la variante wavelet.

Las funciones de este módulo reciben la tabla lógica producida por
``wavelet_optimization.evaluation``.  No vuelven a ajustar candidatos ni
construyen un benchmark distinto: para cada grupo de candidato, horizonte y
split se utiliza una única máscara común de predicción modelo, benchmark y
retorno observado.

La prueba de Diebold--Mariano usa la diferencia de pérdidas cuadráticas
``loss_random_walk - loss_model`` y una varianza HAC de Bartlett con rezago
máximo ``horizon_months - 1``.  El orden de las observaciones es temporal y la
métrica queda sin evaluar si no hay al menos 12 observaciones o si la varianza
HAC no es positiva.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from typing import Any, TypeAlias

import numpy as np
import pandas as pd
from scipy import stats

from .config import (
    PHASE_FULL,
    PHASE_HOLDOUT,
    PHASE_SELECTION,
)

# ``evaluation.py`` intentionally does not import this module yet.  Importing
# only the string contract here keeps metrics usable with its OriginPrediction
# objects without introducing a circular import when the runner is wired later.
SCOREABLE_STATUS = "scoreable"

DM_EVALUATED = "evaluated"
DM_INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
DM_NON_POSITIVE_HAC_VARIANCE = "non_positive_hac_variance"

MetricInput: TypeAlias = Mapping[str, Any] | Any


class MetricsError(ValueError):
    """Error de entrada o de contrato de las métricas OOS."""


@dataclass(frozen=True)
class DMResult:
    """Resultado auditable del contraste DM con varianza HAC.

    ``mean_loss_difference`` es positivo cuando el modelo tiene menor pérdida
    cuadrática que la caminata aleatoria. ``hac_variance`` es la varianza de
    la media de esa diferencia, no la varianza de una observación individual.
    """

    dm_stat: float | None
    p_value: float | None
    status: str
    n_observations: int
    max_lag: int
    mean_loss_difference: float | None = None
    hac_variance: float | None = None

    def __post_init__(self) -> None:
        if self.n_observations < 0:
            raise MetricsError("DMResult.n_observations no puede ser negativo")
        if self.max_lag < 0:
            raise MetricsError("DMResult.max_lag no puede ser negativo")
        object.__setattr__(self, "status", str(self.status).strip())
        for name in (
            "dm_stat",
            "p_value",
            "mean_loss_difference",
            "hac_variance",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as error:
                raise MetricsError(f"{name} debe ser numérico o nulo") from error
            if not np.isfinite(value):
                raise MetricsError(f"{name} debe ser finito o nulo")
            if name == "p_value" and not 0.0 <= value <= 1.0:
                raise MetricsError("p_value debe estar en [0, 1]")
            object.__setattr__(self, name, value)

    @property
    def statistic(self) -> float | None:
        """Alias descriptivo del estadístico DM."""

        return self.dm_stat

    @property
    def dm_p_value(self) -> float | None:
        """Alias del p-valor bilateral usado por ``EvaluationMetrics``."""

        return self.p_value

    @property
    def p_value_two_sided(self) -> float | None:
        return self.p_value

    def as_dict(self) -> dict[str, object]:
        return {
            "dm_stat": self.dm_stat,
            "dm_p_value": self.p_value,
            "dm_status": self.status,
            "n_observations": self.n_observations,
            "dm_max_lag": self.max_lag,
            "dm_mean_loss_difference": self.mean_loss_difference,
            "dm_hac_variance": self.hac_variance,
        }

    to_dict = as_dict
    to_record = as_dict

    def __iter__(self):
        """Permite el desempaquetado ``stat, p_value, status``."""

        yield self.dm_stat
        yield self.p_value
        yield self.status


@dataclass(frozen=True)
class EvaluationMetrics:
    """Métricas de una candidata, horizonte y split.

    Los conteos distinguen los orígenes solicitados de los que realmente
    entran a la muestra OOS. Todos los floats están en escala decimal (por
    ejemplo, ``direction_accuracy_model=0.75``), no en porcentaje.
    """

    candidate_id: str
    horizon_months: int
    split: str
    n_requested_origins: int
    n_scoreable_origins: int
    n_excluded_origins: int
    n_oos: int
    sse_model: float | None
    sse_random_walk: float | None
    r2_oos: float | None
    mae_model: float | None
    mae_random_walk: float | None
    rmse_model: float | None
    rmse_random_walk: float | None
    direction_accuracy_model: float | None
    direction_accuracy_random_walk: float | None
    dm_stat: float | None
    dm_p_value: float | None
    dm_status: str
    phase: str | None = None

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        split = str(self.split).strip()
        if not candidate_id:
            raise MetricsError("candidate_id no puede estar vacío")
        if not split:
            raise MetricsError("split no puede estar vacío")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "split", split)

        try:
            horizon = int(self.horizon_months)
        except (TypeError, ValueError, OverflowError) as error:
            raise MetricsError("horizon_months debe ser entero") from error
        if isinstance(self.horizon_months, bool) or horizon < 1:
            raise MetricsError("horizon_months debe ser entero positivo")
        object.__setattr__(self, "horizon_months", horizon)

        counts = (
            "n_requested_origins",
            "n_scoreable_origins",
            "n_excluded_origins",
            "n_oos",
        )
        for name in counts:
            value = getattr(self, name)
            if isinstance(value, bool):
                raise MetricsError(f"{name} debe ser entero no negativo")
            try:
                integer = int(value)
            except (TypeError, ValueError, OverflowError) as error:
                raise MetricsError(f"{name} debe ser entero no negativo") from error
            if integer < 0 or integer != value:
                raise MetricsError(f"{name} debe ser entero no negativo")
            object.__setattr__(self, name, integer)

        if self.n_excluded_origins > self.n_requested_origins:
            raise MetricsError("n_excluded_origins no puede superar n_requested_origins")
        if self.n_scoreable_origins > self.n_requested_origins:
            raise MetricsError("n_scoreable_origins no puede superar n_requested_origins")
        if self.n_oos > self.n_scoreable_origins:
            raise MetricsError("n_oos no puede superar n_scoreable_origins")

        for name in (
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
        ):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError, OverflowError) as error:
                raise MetricsError(f"{name} debe ser numérico o nulo") from error
            if not np.isfinite(numeric):
                raise MetricsError(f"{name} debe ser finito o nulo")
            if name.startswith("direction_accuracy") and not 0.0 <= numeric <= 1.0:
                raise MetricsError(f"{name} debe estar en [0, 1]")
            if name == "dm_p_value" and not 0.0 <= numeric <= 1.0:
                raise MetricsError("dm_p_value debe estar en [0, 1]")
            object.__setattr__(self, name, numeric)
        object.__setattr__(self, "dm_status", str(self.dm_status).strip())
        if not self.dm_status:
            raise MetricsError("dm_status no puede estar vacío")
        phase = self.phase
        if phase is None or not str(phase).strip():
            phase = {
                "full": PHASE_FULL,
                "2008_2019": PHASE_SELECTION,
                "2020_2022": PHASE_SELECTION,
                "2023_2026": PHASE_HOLDOUT,
            }.get(self.split, PHASE_FULL)
        phase = str(phase).strip().lower()
        if phase not in {PHASE_FULL, PHASE_SELECTION, PHASE_HOLDOUT}:
            raise MetricsError(f"phase no soportada: {phase!r}")
        object.__setattr__(self, "phase", phase)

    @property
    def key(self) -> tuple[str, int, str]:
        return self.candidate_id, self.horizon_months, self.split

    @property
    def phase_key(self) -> tuple[str, int, str]:
        return self.candidate_id, self.horizon_months, str(self.phase)

    @property
    def n_observations(self) -> int:
        return self.n_oos

    @property
    def primary_metric(self) -> float | None:
        return self.r2_oos

    @property
    def is_evaluable(self) -> bool:
        return self.n_oos > 0 and self.r2_oos is not None

    def as_dict(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    to_dict = as_dict
    to_record = as_dict


@dataclass(frozen=True)
class CommonSample:
    """Muestra pareada usada simultáneamente por modelo y benchmark."""

    model: np.ndarray
    random_walk: np.ndarray
    observed: np.ndarray
    mask: np.ndarray

    def __post_init__(self) -> None:
        arrays = {
            "model": np.asarray(self.model, dtype=float).reshape(-1),
            "random_walk": np.asarray(self.random_walk, dtype=float).reshape(-1),
            "observed": np.asarray(self.observed, dtype=float).reshape(-1),
            "mask": np.asarray(self.mask, dtype=bool).reshape(-1),
        }
        lengths = {len(value) for value in arrays.values()}
        if len(lengths) != 1:
            raise MetricsError("CommonSample requiere vectores de igual longitud")
        for name, value in arrays.items():
            object.__setattr__(self, name, value)

    @property
    def n(self) -> int:
        return int(self.mask.sum())

    @property
    def model_common(self) -> np.ndarray:
        return self.model[self.mask]

    @property
    def random_walk_common(self) -> np.ndarray:
        return self.random_walk[self.mask]

    @property
    def observed_common(self) -> np.ndarray:
        return self.observed[self.mask]


def _finite_array(values: Sequence[Any] | np.ndarray | pd.Series) -> np.ndarray:
    """Convierte valores heterogéneos a float, sin imputar faltantes."""

    try:
        numeric = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce")
        result = numeric.to_numpy(dtype=float, na_value=np.nan)
    except (TypeError, ValueError, OverflowError) as error:
        raise MetricsError("Las predicciones y observaciones deben ser secuencias") from error
    return result.reshape(-1)


def common_observation_mask(
    prediction_model: Sequence[Any] | np.ndarray | pd.Series,
    prediction_random_walk: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> np.ndarray:
    """Devuelve la máscara única de observaciones finitas de los tres métodos."""

    model = _finite_array(prediction_model)
    random_walk = _finite_array(prediction_random_walk)
    actual = _finite_array(observed)
    if not (len(model) == len(random_walk) == len(actual)):
        raise MetricsError("modelo, benchmark y observado deben tener el mismo tamaño")
    return np.isfinite(model) & np.isfinite(random_walk) & np.isfinite(actual)


common_mask = common_observation_mask


def build_common_sample(
    prediction_model: Sequence[Any] | np.ndarray | pd.Series,
    prediction_random_walk: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> CommonSample:
    """Materializa las tres series y su máscara común sin alterar observaciones."""

    model = _finite_array(prediction_model)
    random_walk = _finite_array(prediction_random_walk)
    actual = _finite_array(observed)
    mask = common_observation_mask(model, random_walk, actual)
    return CommonSample(model=model, random_walk=random_walk, observed=actual, mask=mask)


common_sample = build_common_sample


def common_sse(
    prediction_model: Sequence[Any] | np.ndarray | pd.Series,
    prediction_random_walk: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> tuple[float | None, float | None]:
    """Calcula ambos SSE sobre exactamente la misma máscara común."""

    sample = build_common_sample(prediction_model, prediction_random_walk, observed)
    if sample.n == 0:
        return None, None
    model_error = sample.model_common - sample.observed_common
    random_walk_error = sample.random_walk_common - sample.observed_common
    return (
        float(np.dot(model_error, model_error)),
        float(np.dot(random_walk_error, random_walk_error)),
    )


sse_common = common_sse
sse_on_common_sample = common_sse
calculate_common_sse = common_sse


def calculate_r2_oos(
    sse_model: float | None,
    sse_random_walk: float | None,
) -> float | None:
    """Calcula ``1 - SSE_model/SSE_random_walk`` sin inventar un denominador."""

    if sse_model is None or sse_random_walk is None:
        return None
    try:
        model_sse = float(sse_model)
        benchmark_sse = float(sse_random_walk)
    except (TypeError, ValueError, OverflowError) as error:
        raise MetricsError("los SSE deben ser numéricos o nulos") from error
    if not np.isfinite(model_sse) or not np.isfinite(benchmark_sse):
        return None
    if benchmark_sse <= 0.0:
        return None
    result = 1.0 - model_sse / benchmark_sse
    return float(result) if np.isfinite(result) else None


def _paired_values(
    predictions: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    prediction_values = _finite_array(predictions)
    observed_values = _finite_array(observed)
    if len(prediction_values) != len(observed_values):
        raise MetricsError("predicción y observado deben tener el mismo tamaño")
    mask = np.isfinite(prediction_values) & np.isfinite(observed_values)
    return prediction_values[mask], observed_values[mask]


def calculate_mae(
    predictions: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> float | None:
    """Error absoluto medio sobre las parejas finitas disponibles."""

    prediction_values, observed_values = _paired_values(predictions, observed)
    if not len(observed_values):
        return None
    return float(np.mean(np.abs(prediction_values - observed_values)))


def calculate_rmse(
    predictions: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> float | None:
    """Raíz del error cuadrático medio sobre parejas finitas."""

    prediction_values, observed_values = _paired_values(predictions, observed)
    if not len(observed_values):
        return None
    return float(np.sqrt(np.mean(np.square(prediction_values - observed_values))))


def calculate_direction_accuracy(
    predictions: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
) -> float | None:
    """Proporción de signos iguales sobre parejas finitas."""

    prediction_values, observed_values = _paired_values(predictions, observed)
    if not len(observed_values):
        return None
    return float(np.mean(np.sign(prediction_values) == np.sign(observed_values)))


r2_oos = calculate_r2_oos
calculate_r2 = calculate_r2_oos
mae = calculate_mae
mean_absolute_error = calculate_mae
rmse = calculate_rmse
root_mean_squared_error = calculate_rmse
direction_accuracy = calculate_direction_accuracy
directional_accuracy = calculate_direction_accuracy


def _validate_horizon(horizon_months: Any) -> int:
    if isinstance(horizon_months, (bool, np.bool_)):
        raise MetricsError("horizon_months debe ser entero positivo")
    try:
        horizon = int(horizon_months)
    except (TypeError, ValueError, OverflowError) as error:
        raise MetricsError("horizon_months debe ser entero positivo") from error
    if horizon < 1:
        raise MetricsError("horizon_months debe ser entero positivo")
    return horizon


def _dm_max_lag(horizon_months: int, max_lag: int | None) -> int:
    if max_lag is None:
        return horizon_months - 1
    if isinstance(max_lag, (bool, np.bool_)):
        raise MetricsError("max_lag debe ser entero no negativo")
    try:
        lag = int(max_lag)
    except (TypeError, ValueError, OverflowError) as error:
        raise MetricsError("max_lag debe ser entero no negativo") from error
    if lag < 0:
        raise MetricsError("max_lag debe ser entero no negativo")
    return lag


def compute_dm_hac(
    prediction_model: Sequence[Any] | np.ndarray | pd.Series,
    prediction_random_walk: Sequence[Any] | np.ndarray | pd.Series,
    observed: Sequence[Any] | np.ndarray | pd.Series,
    horizon_months: int = 6,
    *,
    horizon: int | None = None,
    min_observations: int = 12,
    max_lag: int | None = None,
) -> DMResult:
    """Calcula DM bilateral con pérdidas cuadráticas y HAC de Bartlett.

    La diferencia es ``d = e_random_walk² - e_model²``; por ello un
    estadístico positivo favorece al modelo. El p-valor bilateral usa la
    distribución t con ``n-1`` grados de libertad, igual que el patrón DM
    histórico del repositorio.
    """

    if horizon is not None:
        horizon_months = horizon
    horizon_value = _validate_horizon(horizon_months)
    if isinstance(min_observations, (bool, np.bool_)):
        raise MetricsError("min_observations debe ser entero positivo")
    try:
        minimum = int(min_observations)
    except (TypeError, ValueError, OverflowError) as error:
        raise MetricsError("min_observations debe ser entero positivo") from error
    if minimum < 1:
        raise MetricsError("min_observations debe ser entero positivo")
    lag = _dm_max_lag(horizon_value, max_lag)

    sample = build_common_sample(prediction_model, prediction_random_walk, observed)
    model = sample.model_common
    random_walk = sample.random_walk_common
    actual = sample.observed_common
    n = len(actual)
    if n < minimum:
        return DMResult(
            dm_stat=None,
            p_value=None,
            status=DM_INSUFFICIENT_OBSERVATIONS,
            n_observations=n,
            max_lag=lag,
        )

    model_errors = model - actual
    random_walk_errors = random_walk - actual
    loss_difference = np.square(random_walk_errors) - np.square(model_errors)
    mean_difference = float(np.mean(loss_difference))
    centered = loss_difference - mean_difference

    # The minimum configured sample (12) is enough for h=12 and lag 11.  The
    # clipping also keeps this primitive well-defined for standalone callers
    # requesting a longer horizon than their sample can support.
    effective_lag = min(lag, n - 1)
    long_run_variance = float(np.mean(np.square(centered)))
    for current_lag in range(1, effective_lag + 1):
        weight = 1.0 - current_lag / (effective_lag + 1.0)
        covariance = float(
            np.mean(centered[current_lag:] * centered[:-current_lag])
        )
        long_run_variance += 2.0 * weight * covariance
    hac_variance = long_run_variance / float(n)

    if not np.isfinite(hac_variance) or hac_variance <= 0.0:
        return DMResult(
            dm_stat=None,
            p_value=None,
            status=DM_NON_POSITIVE_HAC_VARIANCE,
            n_observations=n,
            max_lag=lag,
            mean_loss_difference=mean_difference,
            hac_variance=hac_variance if np.isfinite(hac_variance) else None,
        )

    dm_stat = float(mean_difference / np.sqrt(hac_variance))
    p_value = float(2.0 * stats.t.sf(abs(dm_stat), df=n - 1))
    # ``sf`` is numerically stable in the tails, but clipping documents the
    # probability contract and protects against a one-ulp result outside [0,1].
    p_value = min(1.0, max(0.0, p_value))
    return DMResult(
        dm_stat=dm_stat,
        p_value=p_value,
        status=DM_EVALUATED,
        n_observations=n,
        max_lag=lag,
        mean_loss_difference=mean_difference,
        hac_variance=hac_variance,
    )


# Public aliases used by callers that use the test's long or short name.
dm_hac = compute_dm_hac
diebold_mariano_hac = compute_dm_hac
diebold_mariano_test = compute_dm_hac
compute_dm = compute_dm_hac


@dataclass(frozen=True)
class _MetricRow:
    candidate_id: str
    horizon_months: int
    split: str
    origin: Any
    prediction_model: float | None
    prediction_random_walk: float | None
    observed: float | None
    logically_scoreable: bool
    phase: str


def _row_value(row: MetricInput, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(row, Mapping):
            if name in row:
                return row[name]
        else:
            value = getattr(row, name, default)
            if value is not default:
                return value
    return default


def _finite_scalar(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if np.isfinite(result) else None


def _bool_value(value: Any) -> bool | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "si", "sí"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _coerce_metric_row(row: MetricInput, index: int) -> _MetricRow:
    candidate = _row_value(row, "candidate_id", "candidate", default=None)
    if candidate is None or not str(candidate).strip():
        raise MetricsError(f"La fila {index} no tiene candidate_id")
    horizon = _row_value(row, "horizon_months", "horizon", default=None)
    try:
        horizon_value = _validate_horizon(horizon)
    except MetricsError as error:
        raise MetricsError(f"La fila {index} tiene horizonte inválido") from error
    split = _row_value(row, "split", "evaluation_split", default="full")
    split_value = str(split).strip()
    if not split_value:
        raise MetricsError(f"La fila {index} tiene split vacío")

    model = _finite_scalar(
        _row_value(
            row,
            "prediction_wavelet",
            "prediction_model",
            "model_prediction",
            "forecast_model",
            default=None,
        )
    )
    random_walk = _finite_scalar(
        _row_value(
            row,
            "prediction_random_walk",
            "prediction_benchmark",
            "benchmark_prediction",
            "forecast_benchmark",
            default=None,
        )
    )
    observed = _finite_scalar(
        _row_value(
            row,
            "observed_forward_return",
            "observed",
            "target",
            "actual",
            default=None,
        )
    )

    status_value = _row_value(
        row,
        "scoreability_status",
        "status",
        "scoreability",
        default=None,
    )
    status_scoreable = (
        status_value is None
        or str(status_value).strip().lower() == SCOREABLE_STATUS
    )
    coverage_value = _row_value(row, "coverage_status", default=None)
    coverage_complete = coverage_value is None or str(coverage_value).strip().lower() == "complete"
    explicit_scoreable = _row_value(row, "is_scoreable", default=None)
    explicit_scoreable_bool = _bool_value(explicit_scoreable)
    if explicit_scoreable_bool is not None:
        status_scoreable = status_scoreable and explicit_scoreable_bool

    logically_scoreable = status_scoreable and coverage_complete
    phase = _row_value(row, "phase", "evaluation_phase", default=None)
    if phase is None or not str(phase).strip():
        phase = {
            "full": PHASE_FULL,
            "2008_2019": PHASE_SELECTION,
            "2020_2022": PHASE_SELECTION,
            "2023_2026": PHASE_HOLDOUT,
        }.get(split_value, PHASE_FULL)
    phase = str(phase).strip().lower()
    if phase not in {PHASE_FULL, PHASE_SELECTION, PHASE_HOLDOUT}:
        raise MetricsError(f"La fila {index} tiene phase inválida: {phase!r}")
    return _MetricRow(
        candidate_id=str(candidate).strip(),
        horizon_months=horizon_value,
        split=split_value,
        origin=_row_value(row, "origin_date", "origin", default=index),
        prediction_model=model,
        prediction_random_walk=random_walk,
        observed=observed,
        logically_scoreable=logically_scoreable,
        phase=phase,
    )


def _materialize_predictions(predictions: Any) -> tuple[MetricInput, ...]:
    """Acepta EvaluationBundle, DataFrame, mapping de bundle o iterable de filas."""

    if predictions is None:
        return ()
    if isinstance(predictions, pd.DataFrame):
        return tuple(predictions.to_dict(orient="records"))
    bundle_rows = getattr(predictions, "predictions", None)
    if bundle_rows is not None:
        return tuple(bundle_rows)
    if isinstance(predictions, Mapping) and "predictions" in predictions:
        value = predictions["predictions"]
        if isinstance(value, pd.DataFrame):
            return tuple(value.to_dict(orient="records"))
        return tuple(value)
    if isinstance(predictions, (str, bytes, bytearray)):
        raise MetricsError("predictions debe ser un bundle o iterable de filas")
    try:
        return tuple(predictions)
    except TypeError as error:
        raise MetricsError("predictions debe ser un bundle o iterable de filas") from error


def _ordered_origin_key(value: Any, fallback: int) -> tuple[int, int | str, int]:
    try:
        timestamp = pd.Timestamp(value)
        if pd.isna(timestamp):
            raise ValueError
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("UTC").tz_localize(None)
        return 0, int(timestamp.value), fallback
    except (TypeError, ValueError, OverflowError):
        return 1, str(value), fallback


def _ordered_rows(rows: Iterable[_MetricRow]) -> tuple[_MetricRow, ...]:
    materialized = tuple(rows)
    return tuple(
        row
        for _index, row in sorted(
            enumerate(materialized),
            key=lambda item: _ordered_origin_key(item[1].origin, item[0]),
        )
    )


def _metric_from_group(
    rows: Sequence[_MetricRow],
    *,
    candidate_id: str,
    horizon_months: int,
    split: str,
    phase: str,
    dm_min_observations: int,
    dm_max_lag_rule: str,
    requested_origins: int | None = None,
) -> EvaluationMetrics:
    if dm_max_lag_rule != "horizon_minus_one":
        raise MetricsError(
            "dm_max_lag_rule debe ser 'horizon_minus_one' para esta variante"
        )
    if requested_origins is None:
        n_requested = len(rows)
    else:
        if isinstance(requested_origins, bool) or int(requested_origins) != requested_origins:
            raise MetricsError("requested_origins debe ser entero no negativo")
        n_requested = int(requested_origins)
    if n_requested < 0:
        raise MetricsError("requested_origins debe ser no negativo")

    common_rows = tuple(
        row
        for row in _ordered_rows(rows)
        if row.logically_scoreable
        and row.prediction_model is not None
        and row.prediction_random_walk is not None
        and row.observed is not None
    )
    n_oos = len(common_rows)
    n_scoreable = n_oos
    n_excluded = max(0, n_requested - n_scoreable)

    if n_oos == 0:
        return EvaluationMetrics(
            candidate_id=candidate_id,
            horizon_months=horizon_months,
            split=split,
            n_requested_origins=n_requested,
            n_scoreable_origins=n_scoreable,
            n_excluded_origins=n_excluded,
            n_oos=0,
            sse_model=None,
            sse_random_walk=None,
            r2_oos=None,
            mae_model=None,
            mae_random_walk=None,
            rmse_model=None,
            rmse_random_walk=None,
            direction_accuracy_model=None,
            direction_accuracy_random_walk=None,
            dm_stat=None,
            dm_p_value=None,
            dm_status=DM_INSUFFICIENT_OBSERVATIONS,
            phase=phase,
        )

    model = np.asarray([row.prediction_model for row in common_rows], dtype=float)
    random_walk = np.asarray([row.prediction_random_walk for row in common_rows], dtype=float)
    observed = np.asarray([row.observed for row in common_rows], dtype=float)
    model_errors = model - observed
    random_walk_errors = random_walk - observed
    model_squared = np.square(model_errors)
    random_walk_squared = np.square(random_walk_errors)
    sse_model = float(np.sum(model_squared))
    sse_random_walk = float(np.sum(random_walk_squared))
    r2_oos = (
        None
        if sse_random_walk <= 0.0
        else float(1.0 - sse_model / sse_random_walk)
    )

    dm = compute_dm_hac(
        model,
        random_walk,
        observed,
        horizon_months,
        min_observations=dm_min_observations,
    )
    return EvaluationMetrics(
        candidate_id=candidate_id,
        horizon_months=horizon_months,
        split=split,
        n_requested_origins=n_requested,
        n_scoreable_origins=n_scoreable,
        n_excluded_origins=n_excluded,
        n_oos=n_oos,
        sse_model=sse_model,
        sse_random_walk=sse_random_walk,
        r2_oos=r2_oos,
        mae_model=float(np.mean(np.abs(model_errors))),
        mae_random_walk=float(np.mean(np.abs(random_walk_errors))),
        rmse_model=float(np.sqrt(np.mean(model_squared))),
        rmse_random_walk=float(np.sqrt(np.mean(random_walk_squared))),
        direction_accuracy_model=float(np.mean(np.sign(model) == np.sign(observed))),
        direction_accuracy_random_walk=float(
            np.mean(np.sign(random_walk) == np.sign(observed))
        ),
        dm_stat=dm.dm_stat,
        dm_p_value=dm.p_value,
        dm_status=dm.status,
        phase=phase,
    )


def _candidate_ids_from(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),)
    result: list[str] = []
    for item in value:
        candidate = getattr(item, "candidate_id", item)
        text = str(candidate).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _plan_values(plan: Any) -> tuple[tuple[str, ...], tuple[int, ...], tuple[str, ...], int, str]:
    candidates = _candidate_ids_from(getattr(plan, "candidates", None))
    horizons = tuple(int(value) for value in getattr(plan, "horizons", ()))
    splits = tuple(str(value) for value in getattr(plan, "splits", ()))
    minimum = int(getattr(plan, "dm_min_observations", 12))
    rule = str(getattr(plan, "dm_max_lag_rule", "horizon_minus_one"))
    return candidates, horizons, splits, minimum, rule


class MetricsCalculator:
    """Calculador puro de métricas para un ``EvaluationBundle`` o sus filas."""

    def __init__(
        self,
        *,
        dm_min_observations: int = 12,
        dm_max_lag_rule: str = "horizon_minus_one",
    ) -> None:
        if isinstance(dm_min_observations, (bool, np.bool_)):
            raise MetricsError("dm_min_observations debe ser entero positivo")
        try:
            minimum = int(dm_min_observations)
        except (TypeError, ValueError, OverflowError) as error:
            raise MetricsError("dm_min_observations debe ser entero positivo") from error
        if minimum < 1:
            raise MetricsError("dm_min_observations debe ser entero positivo")
        if str(dm_max_lag_rule) != "horizon_minus_one":
            raise MetricsError(
                "dm_max_lag_rule debe ser 'horizon_minus_one' para esta variante"
            )
        self.dm_min_observations = minimum
        self.dm_max_lag_rule = str(dm_max_lag_rule)

    @classmethod
    def from_plan(cls, plan: Any) -> "MetricsCalculator":
        return cls(
            dm_min_observations=int(getattr(plan, "dm_min_observations", 12)),
            dm_max_lag_rule=str(getattr(plan, "dm_max_lag_rule", "horizon_minus_one")),
        )

    def calculate(
        self,
        predictions: Any,
        *,
        plan: Any | None = None,
        candidate_ids: Iterable[Any] | None = None,
        horizons: Iterable[int] | None = None,
        splits: Iterable[str] | None = None,
    ) -> tuple[EvaluationMetrics, ...]:
        bundle_plan = getattr(predictions, "plan", None)
        selected_plan = plan if plan is not None else bundle_plan
        plan_candidates, plan_horizons, plan_splits, plan_minimum, plan_rule = _plan_values(
            selected_plan
        )
        minimum = self.dm_min_observations
        rule = self.dm_max_lag_rule
        if selected_plan is not None:
            minimum = plan_minimum
            rule = plan_rule
        if minimum < 1 or rule != "horizon_minus_one":
            raise MetricsError("El plan contiene una configuración DM no soportada")

        raw_rows = _materialize_predictions(predictions)
        rows = tuple(_coerce_metric_row(row, index) for index, row in enumerate(raw_rows))
        observed_candidates = tuple(dict.fromkeys(row.candidate_id for row in rows))
        observed_horizons = tuple(dict.fromkeys(row.horizon_months for row in rows))
        observed_splits = tuple(dict.fromkeys(row.split for row in rows))

        selected_candidates = _candidate_ids_from(candidate_ids)
        if not selected_candidates:
            selected_candidates = plan_candidates or observed_candidates
        else:
            selected_candidates = tuple(dict.fromkeys(selected_candidates))
        selected_candidates = tuple(dict.fromkeys((*selected_candidates, *observed_candidates)))

        if horizons is None:
            selected_horizons = plan_horizons or observed_horizons
        else:
            selected_horizons = tuple(dict.fromkeys(int(value) for value in horizons))
        selected_horizons = tuple(dict.fromkeys((*selected_horizons, *observed_horizons)))

        if splits is None:
            selected_splits = plan_splits or observed_splits
        else:
            selected_splits = tuple(dict.fromkeys(str(value) for value in splits))
        selected_splits = tuple(dict.fromkeys((*selected_splits, *observed_splits)))

        if not selected_candidates or not selected_horizons or not selected_splits:
            return ()

        groups: dict[tuple[str, int, str], list[_MetricRow]] = {}
        for row in rows:
            groups.setdefault((row.candidate_id, row.horizon_months, row.split), []).append(row)

        # The lexical key is intentional: a permuted input table cannot alter
        # the order of metrics or the later candidate ranking.
        result: list[EvaluationMetrics] = []
        for candidate_id in sorted(selected_candidates):
            for horizon_value in sorted(selected_horizons):
                for split_value in sorted(selected_splits):
                    group = groups.get((candidate_id, horizon_value, split_value), ())
                    phase = (
                        getattr(selected_plan, "phase_for_split", lambda value: {
                            "full": PHASE_FULL,
                            "2008_2019": PHASE_SELECTION,
                            "2020_2022": PHASE_SELECTION,
                            "2023_2026": PHASE_HOLDOUT,
                        }.get(str(value), PHASE_FULL))(split_value)
                    )
                    result.append(
                        _metric_from_group(
                            group,
                            candidate_id=candidate_id,
                            horizon_months=horizon_value,
                            split=split_value,
                            phase=phase,
                            dm_min_observations=minimum,
                            dm_max_lag_rule=rule,
                        )
                    )
        return tuple(result)

    evaluate = calculate
    calculate_metrics = calculate


def calculate_metrics(
    predictions: Any,
    *,
    plan: Any | None = None,
    candidate_ids: Iterable[Any] | None = None,
    horizons: Iterable[int] | None = None,
    splits: Iterable[str] | None = None,
    dm_min_observations: int | None = None,
    dm_max_lag_rule: str | None = None,
) -> tuple[EvaluationMetrics, ...]:
    """Función de conveniencia para calcular todos los grupos del bundle."""

    if dm_min_observations is None and dm_max_lag_rule is None and plan is not None:
        calculator = MetricsCalculator.from_plan(plan)
    else:
        calculator = MetricsCalculator(
            dm_min_observations=(12 if dm_min_observations is None else dm_min_observations),
            dm_max_lag_rule=(
                "horizon_minus_one" if dm_max_lag_rule is None else dm_max_lag_rule
            ),
        )
    return calculator.calculate(
        predictions,
        plan=plan,
        candidate_ids=candidate_ids,
        horizons=horizons,
        splits=splits,
    )


calculate_evaluation_metrics = calculate_metrics
metrics_from_predictions = calculate_metrics
metrics_from_bundle = calculate_metrics
compute_metrics = calculate_metrics


def _coerce_evaluation_metric(value: Any) -> EvaluationMetrics:
    if isinstance(value, EvaluationMetrics):
        return value
    if isinstance(value, Mapping):
        payload = dict(value)
        allowed = {field.name for field in fields(EvaluationMetrics)}
        payload = {key: payload[key] for key in allowed if key in payload}
        missing = allowed - set(payload) - {"phase"}
        if missing:
            raise MetricsError(f"Fila de métricas incompleta: faltan {sorted(missing)!r}")
        payload.setdefault("phase", None)
        for key, item in tuple(payload.items()):
            if item is None or item is pd.NA or (
                isinstance(item, (float, np.floating)) and np.isnan(item)
            ):
                payload[key] = None
        return EvaluationMetrics(**payload)
    raise MetricsError("ranking requiere EvaluationMetrics o mappings equivalentes")


def _rank_sort_key(metric: EvaluationMetrics) -> tuple[int, float, int, float, str]:
    r2 = metric.r2_oos
    mae = metric.mae_model
    r2_missing = 1 if r2 is None else 0
    mae_missing = 1 if mae is None else 0
    return (
        r2_missing,
        0.0 if r2 is None else -float(r2),
        mae_missing,
        float("inf") if mae is None else float(mae),
        metric.candidate_id,
    )


def aggregate_phase_metrics(
    metrics: Iterable[EvaluationMetrics | Mapping[str, Any]] | pd.DataFrame,
    *,
    phase: str,
) -> tuple[EvaluationMetrics, ...]:
    """Agrupa splits de una fase en una muestra común por candidato/horizonte.

    La selección se basa en la suma de errores de los splits preinscritos, no
    en un promedio de R² por ventana. El holdout nunca se mezcla con esta
    operación; el caller debe pedir explícitamente ``phase='holdout'``.
    """

    if isinstance(metrics, pd.DataFrame):
        values: Iterable[Any] = metrics.to_dict(orient="records")
    else:
        values = metrics
    phase_value = str(phase).strip().lower()
    if phase_value not in {PHASE_FULL, PHASE_SELECTION, PHASE_HOLDOUT}:
        raise MetricsError(f"phase no soportada: {phase!r}")
    rows = tuple(_coerce_evaluation_metric(value) for value in values)
    rows = tuple(item for item in rows if item.phase == phase_value)
    grouped: dict[tuple[str, int], list[EvaluationMetrics]] = {}
    for row in rows:
        grouped.setdefault((row.candidate_id, row.horizon_months), []).append(row)

    def _weighted(
        block: Sequence[EvaluationMetrics], field_name: str, *, denominator: int
    ) -> float | None:
        numerator = 0.0
        weight = 0
        for item in block:
            value = getattr(item, field_name)
            if value is None or item.n_oos <= 0:
                continue
            numerator += float(value) * item.n_oos
            weight += item.n_oos
        if denominator <= 0 or weight <= 0:
            return None
        return float(numerator / weight)

    result: list[EvaluationMetrics] = []
    for (candidate_id, horizon), block in sorted(grouped.items()):
        n_requested = sum(item.n_requested_origins for item in block)
        n_scoreable = sum(item.n_scoreable_origins for item in block)
        n_excluded = sum(item.n_excluded_origins for item in block)
        n_oos = sum(item.n_oos for item in block)
        sse_model_values = [item.sse_model for item in block if item.sse_model is not None]
        sse_benchmark_values = [
            item.sse_random_walk for item in block if item.sse_random_walk is not None
        ]
        sse_model = float(sum(sse_model_values)) if len(sse_model_values) == len(block) else None
        sse_benchmark = (
            float(sum(sse_benchmark_values))
            if len(sse_benchmark_values) == len(block)
            else None
        )
        r2 = calculate_r2_oos(sse_model, sse_benchmark)
        rmse_model = None
        rmse_benchmark = None
        if n_oos > 0:
            model_sse = [
                float(item.rmse_model) ** 2 * item.n_oos
                for item in block
                if item.rmse_model is not None
            ]
            benchmark_sse = [
                float(item.rmse_random_walk) ** 2 * item.n_oos
                for item in block
                if item.rmse_random_walk is not None
            ]
            if len(model_sse) == len(block):
                rmse_model = float(np.sqrt(sum(model_sse) / n_oos))
            if len(benchmark_sse) == len(block):
                rmse_benchmark = float(np.sqrt(sum(benchmark_sse) / n_oos))
        dm = block[0] if len(block) == 1 else None
        result.append(
            EvaluationMetrics(
                candidate_id=candidate_id,
                horizon_months=horizon,
                split=phase_value,
                phase=phase_value,
                n_requested_origins=n_requested,
                n_scoreable_origins=n_scoreable,
                n_excluded_origins=n_excluded,
                n_oos=n_oos,
                sse_model=sse_model,
                sse_random_walk=sse_benchmark,
                r2_oos=r2,
                mae_model=_weighted(block, "mae_model", denominator=n_oos),
                mae_random_walk=_weighted(block, "mae_random_walk", denominator=n_oos),
                rmse_model=rmse_model,
                rmse_random_walk=rmse_benchmark,
                direction_accuracy_model=_weighted(
                    block, "direction_accuracy_model", denominator=n_oos
                ),
                direction_accuracy_random_walk=_weighted(
                    block, "direction_accuracy_random_walk", denominator=n_oos
                ),
                dm_stat=None if dm is None else dm.dm_stat,
                dm_p_value=None if dm is None else dm.dm_p_value,
                dm_status=(
                    "aggregated"
                    if dm is None and n_oos > 0
                    else DM_INSUFFICIENT_OBSERVATIONS
                    if dm is None
                    else dm.dm_status
                ),
            )
        )
    return tuple(result)


aggregate_metrics_by_phase = aggregate_phase_metrics


def rank_metrics(
    metrics: Iterable[EvaluationMetrics | Mapping[str, Any]] | pd.DataFrame,
    *,
    horizon_months: int | None = None,
    horizon: int | None = None,
    split: str | None = "full",
    phase: str | None = None,
) -> tuple[EvaluationMetrics, ...]:
    """Ordena métricas por R², MAE y ``candidate_id``.

    Sin ``phase`` conserva el contrato histórico y filtra ``split='full'``.
    Con una fase explícita agrupa sus splits preinscritos antes de ordenar, de
    modo que ningún ranking de selección pueda consumir el holdout por error.
    """

    if isinstance(metrics, pd.DataFrame):
        values: Iterable[Any] = metrics.to_dict(orient="records")
    else:
        values = metrics
    materialized = tuple(_coerce_evaluation_metric(value) for value in values)
    if horizon is not None:
        if horizon_months is not None and int(horizon_months) != int(horizon):
            raise MetricsError("horizon y horizon_months no concilian")
        horizon_months = horizon
    if horizon_months is not None:
        horizon_value = _validate_horizon(horizon_months)
        materialized = tuple(
            item for item in materialized if item.horizon_months == horizon_value
        )
    if split is not None:
        split_value = str(split)
        if phase is None:
            materialized = tuple(item for item in materialized if item.split == split_value)

    if phase is not None:
        phase_value = str(phase).strip().lower()
        materialized = aggregate_phase_metrics(materialized, phase=phase_value)
        if split not in (None, "full", phase_value):
            materialized = tuple(item for item in materialized if item.split == str(split))

    result: list[EvaluationMetrics] = []
    horizon_values = sorted({item.horizon_months for item in materialized})
    for horizon_value in horizon_values:
        block = [item for item in materialized if item.horizon_months == horizon_value]
        result.extend(sorted(block, key=_rank_sort_key))
    return tuple(result)


rank_candidates = rank_metrics
rank_evaluation_metrics = rank_metrics
select_ranking = rank_metrics


def ranked_candidate_ids(
    metrics: Iterable[EvaluationMetrics | Mapping[str, Any]] | pd.DataFrame,
    *,
    horizon_months: int | None = None,
    horizon: int | None = None,
    split: str | None = "full",
    phase: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        metric.candidate_id
        for metric in rank_metrics(
            metrics,
            horizon_months=horizon_months,
            horizon=horizon,
            split=split,
            phase=phase,
        )
    )


rank_candidate_ids = ranked_candidate_ids


def metrics_frame(
    metrics: Iterable[EvaluationMetrics | Mapping[str, Any]],
) -> pd.DataFrame:
    """Serializa métricas en el orden de columnas del contrato de diseño."""

    rows = [_coerce_evaluation_metric(value).as_dict() for value in metrics]
    columns = [field.name for field in fields(EvaluationMetrics)]
    return pd.DataFrame(rows, columns=columns)


to_metrics_frame = metrics_frame


__all__ = [
    "CommonSample",
    "DM_EVALUATED",
    "DM_INSUFFICIENT_OBSERVATIONS",
    "DM_NON_POSITIVE_HAC_VARIANCE",
    "DMResult",
    "EvaluationMetrics",
    "MetricsCalculator",
    "MetricsError",
    "aggregate_metrics_by_phase",
    "aggregate_phase_metrics",
    "build_common_sample",
    "calculate_common_sse",
    "calculate_direction_accuracy",
    "calculate_evaluation_metrics",
    "calculate_mae",
    "calculate_metrics",
    "calculate_r2",
    "calculate_r2_oos",
    "calculate_rmse",
    "common_mask",
    "common_observation_mask",
    "common_sample",
    "common_sse",
    "compute_dm",
    "compute_dm_hac",
    "compute_metrics",
    "diebold_mariano_hac",
    "diebold_mariano_test",
    "direction_accuracy",
    "directional_accuracy",
    "dm_hac",
    "mae",
    "mean_absolute_error",
    "metrics_frame",
    "metrics_from_bundle",
    "metrics_from_predictions",
    "rank_candidate_ids",
    "rank_candidates",
    "rank_evaluation_metrics",
    "rank_metrics",
    "ranked_candidate_ids",
    "r2_oos",
    "root_mean_squared_error",
    "rmse",
    "select_ranking",
    "sse_common",
    "sse_on_common_sample",
    "to_metrics_frame",
]
