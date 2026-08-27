"""Construcción PIT de etiquetas forward y filtros de scoreabilidad.

Las etiquetas de esta variante se construyen sobre las posiciones de un panel
mensual que ya fue materializado por la capa PIT. El módulo no carga archivos,
no mensualiza fuentes y no completa fechas o valores faltantes: solo calcula el
retorno entre dos posiciones que existen en la serie recibida y conserva el
estado de disponibilidad de cada etiqueta.

La frontera temporal es deliberadamente estricta. Una etiqueta que comienza en
``i`` y termina en ``i + h`` solo puede entrenar una predicción en el origen
``t`` cuando ``i + h < t``. La igualdad ``i + h == t`` queda fuera del conjunto
de entrenamiento. Una etiqueta cuyo final supera ``Data_Cutoff`` puede quedar
registrada para diagnóstico, pero nunca es utilizable para métricas OOS.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from forecast_longterm.oos import label_end_is_strictly_before

from .config import (
    MINIMUM_MATURE_TRAINING,
    REQUIRED_HORIZONS,
    TARGET_SERIES,
    ResearchPlan,
)
from .snapshots import NOT_EVALUABLE_LABEL_NOT_MATURE, ForecastOrigin

# ---------------------------------------------------------------------------
# Estados públicos
# ---------------------------------------------------------------------------

SCOREABLE = "scoreable"
NOT_SCOREABLE_INSUFFICIENT_TRAINING = "not_scoreable_insufficient_training"
NOT_SCOREABLE_LABEL_INVALID = "not_scoreable_label_invalid"
NOT_SCOREABLE_LABEL_MISSING = "not_scoreable_label_missing"
NOT_SCOREABLE_LABEL_ENDS_AT_ORIGIN = "not_scoreable_label_ends_at_origin"
NOT_EVALUABLE_ORIGIN_NOT_IN_PANEL = "not_evaluable_origin_not_in_panel"

# Los nombres de estas constantes forman parte del contrato de CSV/JSON. Se
# conserva el valor definido por snapshots.py para que ambos módulos concilien.
NOT_EVALUABLE_LABEL_NOT_MATURE = NOT_EVALUABLE_LABEL_NOT_MATURE

LabelScoreabilityStatus = Literal[
    "scoreable",
    "not_scoreable_insufficient_training",
    "not_scoreable_label_invalid",
    "not_scoreable_label_missing",
    "not_scoreable_label_ends_at_origin",
    "not_evaluable_label_not_mature",
    "not_evaluable_origin_not_in_panel",
]


class LabelError(ValueError):
    """Error de entrada o de contrato al construir etiquetas forward."""


class LabelValidationError(LabelError):
    """Una etiqueta o un panel no satisface los invariantes temporales."""


class UnsupportedHorizonError(LabelValidationError):
    """El horizonte no pertenece a la variante inicial (6 o 12 meses)."""


# Alias de nombres útiles para adaptadores que consumen los contratos del
# diseño con otra nomenclatura.
ForwardLabelError = LabelError
ForwardLabelValidationError = LabelValidationError


# ---------------------------------------------------------------------------
# Utilidades de fechas y entradas
# ---------------------------------------------------------------------------


def _timestamp(value: Any, field_name: str) -> pd.Timestamp:
    """Convierte una fecha explícita en un timestamp naive normalizado."""

    if value is None or value is pd.NaT:
        raise LabelValidationError(f"{field_name} no puede ser nulo")
    if isinstance(value, (bool, np.bool_, int, float, complex, np.number)):
        raise LabelValidationError(
            f"{field_name} debe ser una fecha explícita, no un número"
        )
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise LabelValidationError(f"{field_name} no puede estar vacío")
        if text.lower() in {
            "latest_available",
            "last_observation",
            "auto",
            "tbd",
            "required_explicit_date",
        }:
            raise LabelValidationError(
                f"{field_name} no puede inferirse desde el marcador {value!r}"
            )
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise LabelValidationError(
            f"{field_name} no es una fecha válida: {value!r}"
        ) from error
    if pd.isna(result):
        raise LabelValidationError(f"{field_name} no es una fecha válida: {value!r}")
    if result.tzinfo is not None:
        result = result.tz_convert("UTC").tz_localize(None)
    return result.normalize()


def _period(value: Any, field_name: str) -> pd.Period:
    """Obtiene el mes calendario de una fecha/periodo sin crear meses."""

    if isinstance(value, pd.Period):
        try:
            return value.asfreq("M")
        except (TypeError, ValueError) as error:
            raise LabelValidationError(
                f"{field_name} no es un periodo mensual válido: {value!r}"
            ) from error
    timestamp = _timestamp(value, field_name)
    try:
        return timestamp.to_period("M")
    except (TypeError, ValueError) as error:
        raise LabelValidationError(
            f"{field_name} no se puede convertir a periodo mensual"
        ) from error


def _period_text(value: Any, field_name: str) -> str:
    return str(_period(value, field_name))


def _origin_period(value: Any) -> pd.Period:
    if isinstance(value, ForecastOrigin):
        return _period(value.origin_date, "forecast_origin")
    if hasattr(value, "origin_date") and not isinstance(value, (str, pd.Timestamp)):
        return _period(getattr(value, "origin_date"), "forecast_origin.origin_date")
    return _period(value, "forecast_origin")


def _validate_horizon(value: Any) -> int:
    if isinstance(value, bool):
        raise UnsupportedHorizonError(f"horizon_months no es válido: {value!r}")
    try:
        horizon = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise UnsupportedHorizonError(
            f"horizon_months debe ser uno de {REQUIRED_HORIZONS!r}: {value!r}"
        ) from error
    if horizon not in REQUIRED_HORIZONS:
        raise UnsupportedHorizonError(
            f"horizon_months debe ser exactamente 6 o 12; llegó {value!r}"
        )
    return horizon


def _validate_horizons(values: Iterable[int]) -> tuple[int, ...]:
    try:
        horizons = tuple(_validate_horizon(value) for value in values)
    except TypeError as error:
        raise UnsupportedHorizonError("horizons debe ser iterable") from error
    if not horizons:
        raise UnsupportedHorizonError("horizons no puede estar vacío")
    if len(set(horizons)) != len(horizons):
        raise UnsupportedHorizonError("horizons no puede contener duplicados")
    return horizons


def _coalesce_horizon(horizon: Any | None, horizon_months: Any | None) -> Any | None:
    """Acepta ``horizon`` y ``horizon_months`` como aliases sin ambigüedad."""

    if horizon is None:
        return horizon_months
    if horizon_months is None:
        return horizon
    first = _validate_horizon(horizon)
    second = _validate_horizon(horizon_months)
    if first != second:
        raise UnsupportedHorizonError(
            f"horizon y horizon_months no concilian: {first} != {second}"
        )
    return first


def _monthly_periods(index: pd.Index) -> pd.PeriodIndex:
    """Normaliza un índice mensual sin reindexar ni rellenar huecos."""

    if isinstance(index, pd.PeriodIndex):
        try:
            periods = index.asfreq("M")
        except (TypeError, ValueError) as error:
            raise LabelValidationError("El índice no es mensual") from error
    else:
        values: list[pd.Period] = []
        for position, raw_value in enumerate(index):
            try:
                values.append(_period(raw_value, f"trm_monthly.index[{position}]"))
            except LabelValidationError as error:
                raise LabelValidationError(
                    "trm_monthly debe tener un índice mensual de fechas"
                ) from error
        periods = pd.PeriodIndex(values, freq="M")

    if periods.hasnans:
        raise LabelValidationError("trm_monthly.index contiene fechas faltantes")
    if not periods.is_monotonic_increasing:
        raise LabelValidationError(
            "trm_monthly.index debe estar ordenado cronológicamente"
        )
    if not periods.is_unique:
        raise LabelValidationError(
            "trm_monthly.index no puede tener dos filas del mismo mes"
        )

    # Un hueco no se convierte en una fecha o una observación inventada. El
    # store PIT normalmente entrega NaN para un mes faltante; ese NaN conserva
    # la posición y será descartado como etiqueta inválida más abajo.
    for previous, current in zip(periods[:-1], periods[1:]):
        if current != previous + 1:
            raise LabelValidationError(
                "trm_monthly.index tiene meses ausentes; no se infieren ni se "
                "extrapolan fechas"
            )
    return periods


def _coerce_monthly_series(trm_monthly: pd.Series) -> tuple[pd.PeriodIndex, np.ndarray]:
    if not isinstance(trm_monthly, pd.Series):
        raise TypeError("trm_monthly debe ser pandas.Series")
    periods = _monthly_periods(trm_monthly.index)
    raw = trm_monthly.to_numpy(copy=True)
    numeric = pd.to_numeric(pd.Series(raw, dtype="object"), errors="coerce")
    values = numeric.to_numpy(dtype=float, na_value=np.nan)
    return periods, values


def _safe_forward_return(start: Any, end: Any) -> tuple[float | None, str | None]:
    """Calcula el objetivo sin imputar; devuelve valor y causa si es inválido."""

    try:
        start_value = float(start)
        end_value = float(end)
    except (TypeError, ValueError, OverflowError):
        return None, "trm_no_numeric"
    if not np.isfinite(start_value) or not np.isfinite(end_value):
        return None, "trm_missing_or_non_finite"
    if start_value <= 0 or end_value <= 0:
        return None, "trm_non_positive"
    result = 100.0 * (float(np.log(end_value)) - float(np.log(start_value)))
    if not np.isfinite(result):
        return None, "forward_return_non_finite"
    return result, None


def _labels_from_input(
    labels: Iterable["MatureLabel"] | Mapping[int, Iterable["MatureLabel"]],
    *,
    horizon_months: int | None = None,
) -> tuple["MatureLabel", ...]:
    """Coerce una colección o el mapping producido por ``build_all``."""

    if isinstance(labels, Mapping):
        if horizon_months is None:
            keys = tuple(labels)
            if len(keys) != 1:
                raise LabelValidationError(
                    "Debe indicar horizon_months cuando se entregan varios horizontes"
                )
            horizon_months = int(keys[0])
        try:
            labels = labels[horizon_months]
        except KeyError as error:
            raise LabelValidationError(
                f"No hay etiquetas para horizon_months={horizon_months}"
            ) from error
    try:
        result = tuple(labels)
    except TypeError as error:
        raise TypeError("labels debe ser iterable de MatureLabel") from error
    if any(not isinstance(label, MatureLabel) for label in result):
        raise TypeError("labels solo puede contener MatureLabel")
    if horizon_months is not None:
        horizon = _validate_horizon(horizon_months)
        if any(label.horizon_months != horizon for label in result):
            raise LabelValidationError(
                "La colección contiene etiquetas de un horizonte distinto"
            )
    return tuple(sorted(result, key=lambda item: item.origin_period))


# ---------------------------------------------------------------------------
# Modelo de etiqueta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatureLabel:
    """Una etiqueta ``Forward_Return(h)`` asociada a una posición ``i``.

    ``origin_period`` es el mes de inicio de la etiqueta (la posición ``i``),
    no el origen futuro en el que se usará para entrenar. La etiqueta conoce si
    su final estaba disponible antes de ``Data_Cutoff``; la madurez respecto a
    un origen de pronóstico se consulta con :meth:`mature_for`, que aplica la
    desigualdad estricta ``label_end_period < forecast_origin``.
    """

    origin_period: str
    horizon_months: int
    label_end_period: str
    value: float | None
    observed_by_cutoff: bool
    scoreability_status: str = SCOREABLE
    reason: str | None = None

    def __post_init__(self) -> None:
        start = _period_text(self.origin_period, "MatureLabel.origin_period")
        horizon = _validate_horizon(self.horizon_months)
        end = _period_text(self.label_end_period, "MatureLabel.label_end_period")
        expected_end = str(pd.Period(start, freq="M") + horizon)
        if end != expected_end:
            raise LabelValidationError(
                "label_end_period no concilia con origin_period+horizon_months: "
                f"{end!r} != {expected_end!r}"
            )
        if not isinstance(self.observed_by_cutoff, (bool, np.bool_)):
            raise LabelValidationError("observed_by_cutoff debe ser bool")

        value: float | None
        if self.value is None or self.value is pd.NA:
            value = None
        else:
            try:
                value = float(self.value)
            except (TypeError, ValueError, OverflowError) as error:
                raise LabelValidationError("MatureLabel.value debe ser numérico o nulo") from error
            if not np.isfinite(value):
                value = None

        status = str(self.scoreability_status).strip()
        if not status:
            status = SCOREABLE
        if status == SCOREABLE and value is None:
            status = NOT_SCOREABLE_LABEL_INVALID
        elif status == SCOREABLE and not bool(self.observed_by_cutoff):
            status = NOT_EVALUABLE_LABEL_NOT_MATURE

        object.__setattr__(self, "origin_period", start)
        object.__setattr__(self, "horizon_months", horizon)
        object.__setattr__(self, "label_end_period", end)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "observed_by_cutoff", bool(self.observed_by_cutoff))
        object.__setattr__(self, "scoreability_status", status)
        if self.reason is not None:
            object.__setattr__(self, "reason", str(self.reason).strip() or None)

    @property
    def label_start_period(self) -> str:
        """Alias explícito para el mes ``i`` de la etiqueta."""

        return self.origin_period

    @property
    def start_period(self) -> str:
        return self.origin_period

    @property
    def origin_date(self) -> pd.Timestamp:
        return pd.Period(self.origin_period, freq="M").to_timestamp(how="start")

    @property
    def label_end_date(self) -> pd.Timestamp:
        return pd.Period(self.label_end_period, freq="M").to_timestamp(how="start")

    @property
    def is_valid(self) -> bool:
        return self.value is not None and np.isfinite(float(self.value))

    @property
    def is_observed(self) -> bool:
        return self.is_valid and self.observed_by_cutoff

    @property
    def usable_value(self) -> float | None:
        """Valor que puede entrar a métricas o entrenamiento PIT."""

        return float(self.value) if self.is_observed and self.value is not None else None

    @property
    def maturity_status(self) -> str:
        if not self.is_valid:
            return "invalid"
        if not self.observed_by_cutoff:
            return "not_observed_by_cutoff"
        return "observed"

    @property
    def observed(self) -> bool:
        return self.is_observed

    @property
    def is_observed_by_cutoff(self) -> bool:
        return self.observed_by_cutoff

    @property
    def forward_return(self) -> float | None:
        return self.value

    @property
    def return_value(self) -> float | None:
        return self.value

    @property
    def label_value(self) -> float | None:
        return self.value

    @property
    def horizon(self) -> int:
        return self.horizon_months

    def ends_at(self, forecast_origin: Any) -> bool:
        """Indica la frontera prohibida ``i+h == t`` por mes calendario."""

        return pd.Period(self.label_end_period, freq="M") == _origin_period(forecast_origin)

    def ends_before(self, forecast_origin: Any) -> bool:
        return label_end_is_strictly_before(self.label_end_date, _origin_period(forecast_origin))

    def mature_for(self, forecast_origin: Any) -> bool:
        """Indica si la etiqueta es válida, observable y estrictamente madura."""

        return self.is_observed and self.ends_before(forecast_origin)

    # Alias usados por adaptadores/evaluadores.
    is_mature_for = mature_for
    eligible_for_training = mature_for

    def as_dict(self) -> dict[str, object]:
        return {
            "origin_period": self.origin_period,
            "label_start_period": self.label_start_period,
            "horizon_months": self.horizon_months,
            "label_end_period": self.label_end_period,
            "label_end_date": self.label_end_date.strftime("%Y-%m-%d"),
            "value": self.value,
            "usable_value": self.usable_value,
            "observed_by_cutoff": self.observed_by_cutoff,
            "maturity_status": self.maturity_status,
            "scoreability_status": self.scoreability_status,
            "reason": self.reason,
        }

    to_record = as_dict


# The design document names the structural contract ``ForwardLabel`` while the
# implementation task names the concrete record ``MatureLabel``. Both refer to
# the same immutable record to avoid duplicate, divergent representations.
ForwardLabel = MatureLabel


# ---------------------------------------------------------------------------
# Resultado de los filtros de scoreabilidad
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreabilityResult(Sequence[MatureLabel]):
    """Resultado auditable de filtrar entrenamiento y etiqueta OOS.

    La clase implementa la interfaz de ``Sequence`` para que un caller que solo
    necesita las etiquetas maduras pueda iterarla o pedir ``len(result)``. El
    estado y los conteos permanecen disponibles para el evaluador y los
    serializadores.
    """

    origin_period: str
    horizon_months: int
    mature_labels: tuple[MatureLabel, ...]
    n_mature_labels: int
    minimum_mature_training: int
    status: str
    training_status: str
    target_label: MatureLabel | None = None
    target_status: str = NOT_EVALUABLE_LABEL_NOT_MATURE
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_period", _period_text(self.origin_period, "origin_period"))
        object.__setattr__(self, "horizon_months", _validate_horizon(self.horizon_months))
        labels = _labels_from_input(self.mature_labels, horizon_months=self.horizon_months)
        object.__setattr__(self, "mature_labels", labels)
        if self.n_mature_labels != len(labels):
            raise LabelValidationError(
                "n_mature_labels no concilia con la colección filtrada"
            )
        if (
            not isinstance(self.minimum_mature_training, int)
            or isinstance(self.minimum_mature_training, bool)
            or self.minimum_mature_training <= 0
        ):
            raise LabelValidationError("minimum_mature_training debe ser entero positivo")
        if self.target_label is not None:
            if not isinstance(self.target_label, MatureLabel):
                raise TypeError("target_label debe ser MatureLabel o None")
            if self.target_label.horizon_months != self.horizon_months:
                raise LabelValidationError("target_label usa otro horizonte")
            if self.target_label.origin_period != self.origin_period:
                raise LabelValidationError(
                    "target_label debe comenzar en el forecast origin evaluado"
                )
        object.__setattr__(self, "status", str(self.status).strip())
        object.__setattr__(self, "training_status", str(self.training_status).strip())
        object.__setattr__(self, "target_status", str(self.target_status).strip())
        if self.reason is not None:
            object.__setattr__(self, "reason", str(self.reason).strip() or None)

    @property
    def labels(self) -> tuple[MatureLabel, ...]:
        return self.mature_labels

    @property
    def training_labels(self) -> tuple[MatureLabel, ...]:
        return self.mature_labels

    @property
    def training_scoreable(self) -> bool:
        return self.training_status == SCOREABLE

    @property
    def prediction_allowed(self) -> bool:
        """Indica si hay suficientes etiquetas para ajustar el modelo."""

        return self.training_scoreable

    @property
    def scoreable(self) -> bool:
        """Indica si el origen puede producir una observación OOS evaluable."""

        return self.status == SCOREABLE

    @property
    def is_scoreable(self) -> bool:
        return self.scoreable

    @property
    def state(self) -> str:
        return self.status

    @property
    def n_labels(self) -> int:
        return self.n_mature_labels

    @property
    def is_training_scoreable(self) -> bool:
        return self.training_scoreable

    @property
    def evaluable(self) -> bool:
        return self.scoreable

    @property
    def n_excluded_labels(self) -> int:
        return max(0, self.minimum_mature_training - self.n_mature_labels)

    @property
    def observed_forward_return(self) -> float | None:
        if self.scoreable and self.target_label is not None:
            return self.target_label.usable_value
        return None

    @property
    def label_end_period(self) -> str | None:
        return self.target_label.label_end_period if self.target_label else None

    @property
    def label_end_date(self) -> pd.Timestamp | None:
        return self.target_label.label_end_date if self.target_label else None

    def __iter__(self) -> Iterator[MatureLabel]:
        return iter(self.mature_labels)

    def __len__(self) -> int:
        return len(self.mature_labels)

    def __getitem__(self, index: int | slice) -> MatureLabel | tuple[MatureLabel, ...]:
        return self.mature_labels[index]

    def as_dict(self) -> dict[str, object]:
        return {
            "origin_period": self.origin_period,
            "horizon_months": self.horizon_months,
            "n_mature_labels": self.n_mature_labels,
            "minimum_mature_training": self.minimum_mature_training,
            "status": self.status,
            "training_status": self.training_status,
            "target_status": self.target_status,
            "target_label": self.target_label.as_dict() if self.target_label else None,
            "label_end_period": self.label_end_period,
            "label_end_date": (
                self.label_end_date.strftime("%Y-%m-%d")
                if self.label_end_date is not None
                else None
            ),
            "reason": self.reason,
        }

    to_record = as_dict


class ScoreabilityFilter:
    """Aplica el embargo estricto y el umbral de 60 etiquetas maduras."""

    def __init__(self, minimum_mature_training: int = MINIMUM_MATURE_TRAINING) -> None:
        if (
            not isinstance(minimum_mature_training, int)
            or isinstance(minimum_mature_training, bool)
            or minimum_mature_training <= 0
        ):
            raise LabelValidationError(
                "minimum_mature_training debe ser entero positivo"
            )
        self.minimum_mature_training = minimum_mature_training

    @staticmethod
    def _horizon(
        labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
        horizon_months: int | None,
    ) -> int:
        if horizon_months is not None:
            return _validate_horizon(horizon_months)
        if isinstance(labels, Mapping):
            keys = tuple(labels)
            if len(keys) == 1:
                return _validate_horizon(keys[0])
            raise LabelValidationError(
                "Debe indicar horizon_months para filtrar varios horizontes"
            )
        materialized = tuple(labels)
        horizons = {label.horizon_months for label in materialized}
        if len(horizons) != 1:
            raise LabelValidationError(
                "Debe indicar horizon_months cuando labels contiene varios horizontes"
            )
        return _validate_horizon(next(iter(horizons)))

    def mature(
        self,
        labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
        forecast_origin: Any,
        *,
        horizon_months: int | None = None,
    ) -> tuple[MatureLabel, ...]:
        # Materializar aquí evita consumir un generador durante la inferencia
        # del horizonte y volver a filtrarlo vacío en ``_labels_from_input``.
        if not isinstance(labels, Mapping) and horizon_months is None:
            labels = tuple(labels)
        horizon = self._horizon(labels, horizon_months)
        materialized = _labels_from_input(labels, horizon_months=horizon)
        origin = _origin_period(forecast_origin)
        # No <= aquí: una etiqueta que termina en el mes del origen está
        # explícitamente embargada y no puede entrar al ajuste.
        return tuple(
            label
            for label in materialized
            if label.horizon_months == horizon and label.mature_for(origin)
        )

    # Nombres equivalentes para el evaluador y para tests de contrato.
    filter_mature = mature
    mature_training = mature
    training_labels = mature

    def assess(
        self,
        labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
        forecast_origin: Any,
        *,
        horizon_months: int | None = None,
        target_label: MatureLabel | None = None,
    ) -> ScoreabilityResult:
        if not isinstance(labels, Mapping) and horizon_months is None:
            labels = tuple(labels)
        horizon = self._horizon(labels, horizon_months)
        materialized = _labels_from_input(labels, horizon_months=horizon)
        origin = _origin_period(forecast_origin)
        mature = self.mature(materialized, origin, horizon_months=horizon)
        training_status = (
            SCOREABLE
            if len(mature) >= self.minimum_mature_training
            else NOT_SCOREABLE_INSUFFICIENT_TRAINING
        )

        if target_label is None:
            target_label = next(
                (
                    label
                    for label in materialized
                    if label.origin_period == str(origin)
                ),
                None,
            )

        if target_label is None:
            target_status = NOT_EVALUABLE_LABEL_NOT_MATURE
            target_reason = "forward_label_end_not_available_in_panel_or_cutoff"
        elif not target_label.is_valid:
            target_status = NOT_SCOREABLE_LABEL_INVALID
            target_reason = target_label.reason or "forward_label_value_invalid"
        elif not target_label.observed_by_cutoff:
            target_status = NOT_EVALUABLE_LABEL_NOT_MATURE
            target_reason = "forward_label_end_after_data_cutoff"
        else:
            target_status = SCOREABLE
            target_reason = None

        # El umbral de entrenamiento es bloqueante para ajustar. Cuando se
        # cumple, la etiqueta forward todavía no observada sigue siendo una
        # exclusión de evaluación, nunca un error predictivo imputado.
        status = training_status if training_status != SCOREABLE else target_status
        reason = (
            "insufficient_mature_training"
            if training_status != SCOREABLE
            else target_reason
        )
        return ScoreabilityResult(
            origin_period=str(origin),
            horizon_months=horizon,
            mature_labels=mature,
            n_mature_labels=len(mature),
            minimum_mature_training=self.minimum_mature_training,
            status=status,
            training_status=training_status,
            target_label=target_label,
            target_status=target_status,
            reason=reason,
        )

    assess_origin = assess
    scoreability = assess
    scoreability_for_origin = assess

    def filter(
        self,
        labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
        forecast_origin: Any,
        *,
        horizon_months: int | None = None,
    ) -> ScoreabilityResult:
        return self.assess(
            labels,
            forecast_origin,
            horizon_months=horizon_months,
        )

    filter_scoreable = filter
    filter_scoreable_labels = filter


# Funciones de módulo para callers que no necesitan instanciar un filtro.
def filter_mature_labels(
    labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
    forecast_origin: Any,
    *,
    horizon_months: int | None = None,
) -> tuple[MatureLabel, ...]:
    """Devuelve solo etiquetas válidas con ``label_end < forecast_origin``."""

    return ScoreabilityFilter(minimum_mature_training=1).mature(
        labels,
        forecast_origin,
        horizon_months=horizon_months,
    )


def filter_scoreable_labels(
    labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
    forecast_origin: Any,
    *,
    horizon_months: int | None = None,
    minimum_mature_training: int = MINIMUM_MATURE_TRAINING,
) -> ScoreabilityResult:
    """Filtra entrenamiento y conserva el estado explícito de scoreabilidad."""

    return ScoreabilityFilter(minimum_mature_training).assess(
        labels,
        forecast_origin,
        horizon_months=horizon_months,
    )


def assess_scoreability(
    labels: Iterable[MatureLabel] | Mapping[int, Iterable[MatureLabel]],
    forecast_origin: Any,
    *,
    horizon_months: int | None = None,
    minimum_mature_training: int = MINIMUM_MATURE_TRAINING,
) -> ScoreabilityResult:
    return filter_scoreable_labels(
        labels,
        forecast_origin,
        horizon_months=horizon_months,
        minimum_mature_training=minimum_mature_training,
    )


# ---------------------------------------------------------------------------
# Constructor de etiquetas
# ---------------------------------------------------------------------------


class ForwardLabelBuilder:
    """Construye objetivos forward mensuales para los horizontes preinscritos."""

    def __init__(
        self,
        data_cutoff: Any | None = None,
        *,
        horizons: Iterable[int] = REQUIRED_HORIZONS,
        minimum_mature_training: int = MINIMUM_MATURE_TRAINING,
        target_series: str = TARGET_SERIES,
        plan: ResearchPlan | None = None,
    ) -> None:
        if plan is not None:
            if not isinstance(plan, ResearchPlan):
                raise TypeError("plan debe ser ResearchPlan")
            if data_cutoff is not None and _timestamp(data_cutoff, "data_cutoff") != _timestamp(
                plan.data_cutoff, "plan.data_cutoff"
            ):
                raise LabelValidationError(
                    "data_cutoff explícito no concilia con ResearchPlan.data_cutoff"
                )
            data_cutoff = plan.data_cutoff
            horizons = plan.horizons
            minimum_mature_training = plan.minimum_mature_training
            target_series = plan.target_series

        if data_cutoff is None:
            raise LabelValidationError(
                "data_cutoff/Data_Cutoff es obligatorio; no se infiere de la serie"
            )
        self.data_cutoff = _timestamp(data_cutoff, "data_cutoff")
        self.cutoff_period = self.data_cutoff.to_period("M")
        self.horizons = _validate_horizons(horizons)
        if (
            not isinstance(minimum_mature_training, int)
            or isinstance(minimum_mature_training, bool)
            or minimum_mature_training <= 0
        ):
            raise LabelValidationError(
                "minimum_mature_training debe ser entero positivo"
            )
        self.minimum_mature_training = minimum_mature_training
        self.target_series = str(target_series).strip()
        if self.target_series != TARGET_SERIES:
            raise LabelValidationError(
                f"target_series debe ser {TARGET_SERIES!r}; llegó {target_series!r}"
            )
        self.scoreability_filter = ScoreabilityFilter(minimum_mature_training)

    @classmethod
    def from_plan(cls, plan: ResearchPlan) -> "ForwardLabelBuilder":
        return cls(plan=plan)

    def _validate_requested_horizon(self, horizon: Any) -> int:
        normalized = _validate_horizon(horizon)
        if normalized not in self.horizons:
            raise UnsupportedHorizonError(
                f"horizon_months={normalized} no está habilitado en este builder: "
                f"{self.horizons!r}"
            )
        return normalized

    def build(
        self,
        trm_monthly: pd.Series,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> tuple[MatureLabel, ...] | dict[int, tuple[MatureLabel, ...]]:
        """Construye etiquetas para un horizonte o para todos los habilitados.

        Solo se recorren pares de posiciones existentes ``(i, i+h)``. En
        particular, una cola sin observación no se rellena con fechas o valores
        extrapolados. Las filas que sí existen después del cutoff se conservan
        con ``observed_by_cutoff=False`` y no pasan los filtros de entrenamiento
        o métricas.
        """

        requested_horizon = _coalesce_horizon(horizon, horizon_months)
        if requested_horizon is None:
            return self.build_all(trm_monthly)
        return self.build_horizon(trm_monthly, requested_horizon)

    def build_horizon(
        self,
        trm_monthly: pd.Series,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> tuple[MatureLabel, ...]:
        requested_horizon = _coalesce_horizon(horizon, horizon_months)
        if requested_horizon is None:
            raise UnsupportedHorizonError("horizon_months es obligatorio")
        normalized_horizon = self._validate_requested_horizon(requested_horizon)
        periods, values = _coerce_monthly_series(trm_monthly)
        labels: list[MatureLabel] = []
        # No se crean filas para i+h fuera del panel disponible.
        for index in range(max(0, len(periods) - normalized_horizon)):
            start_period = str(periods[index])
            end_period = str(periods[index + normalized_horizon])
            value, invalid_reason = _safe_forward_return(
                values[index], values[index + normalized_horizon]
            )
            observed_by_cutoff = periods[index + normalized_horizon] <= self.cutoff_period
            if invalid_reason is not None:
                status = NOT_SCOREABLE_LABEL_INVALID
                reason = invalid_reason
            elif not observed_by_cutoff:
                status = NOT_EVALUABLE_LABEL_NOT_MATURE
                reason = "forward_label_end_after_data_cutoff"
            else:
                status = SCOREABLE
                reason = None
            labels.append(
                MatureLabel(
                    origin_period=start_period,
                    horizon_months=normalized_horizon,
                    label_end_period=end_period,
                    value=value,
                    observed_by_cutoff=bool(observed_by_cutoff),
                    scoreability_status=status,
                    reason=reason,
                )
            )
        return tuple(labels)

    def build_labels(
        self,
        trm_monthly: pd.Series,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> tuple[MatureLabel, ...] | dict[int, tuple[MatureLabel, ...]]:
        """Alias explícito de ``build`` para consumidores del contrato."""

        return self.build(
            trm_monthly,
            horizon,
            horizon_months=horizon_months,
        )

    build_for_horizon = build_horizon

    def build_all(self, trm_monthly: pd.Series) -> dict[int, tuple[MatureLabel, ...]]:
        return {
            horizon: self.build_horizon(trm_monthly, horizon)
            for horizon in self.horizons
        }

    build_forward_labels = build_all

    def build_frame(
        self,
        trm_monthly: pd.Series,
        horizon: int | None = None,
    ) -> pd.DataFrame:
        built = self.build(trm_monthly, horizon)
        if isinstance(built, Mapping):
            labels = tuple(label for group in built.values() for label in group)
        else:
            labels = built
        columns = [
            "origin_period",
            "label_start_period",
            "horizon_months",
            "label_end_period",
            "label_end_date",
            "value",
            "usable_value",
            "observed_by_cutoff",
            "maturity_status",
            "scoreability_status",
            "reason",
        ]
        return pd.DataFrame([label.as_dict() for label in labels], columns=columns)

    to_frame = build_frame

    def label_for_origin(
        self,
        trm_monthly: pd.Series,
        forecast_origin: Any,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> MatureLabel | None:
        """Obtiene la etiqueta que empieza en un origen si su final está en el panel."""

        requested_horizon = _coalesce_horizon(horizon, horizon_months)
        if requested_horizon is None:
            raise UnsupportedHorizonError("horizon_months es obligatorio")
        normalized_horizon = self._validate_requested_horizon(requested_horizon)
        origin = str(_origin_period(forecast_origin))
        labels = self.build_horizon(trm_monthly, normalized_horizon)
        return next((label for label in labels if label.origin_period == origin), None)

    target_label = label_for_origin
    forward_label_for_origin = label_for_origin

    def mature_labels(
        self,
        labels_or_series: pd.Series
        | Iterable[MatureLabel]
        | Mapping[int, Iterable[MatureLabel]],
        forecast_origin: Any,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> tuple[MatureLabel, ...]:
        requested_horizon = _coalesce_horizon(horizon, horizon_months)
        if isinstance(labels_or_series, pd.Series):
            if requested_horizon is None:
                raise UnsupportedHorizonError(
                    "Debe indicar horizon_months al construir etiquetas desde una serie"
                )
            labels: tuple[MatureLabel, ...] = self.build_horizon(
                labels_or_series,
                requested_horizon,
            )
            normalized_horizon = self._validate_requested_horizon(requested_horizon)
        else:
            normalized_horizon = (
                self._validate_requested_horizon(requested_horizon)
                if requested_horizon is not None
                else None
            )
            labels = _labels_from_input(
                labels_or_series,
                horizon_months=normalized_horizon,
            )
        return self.scoreability_filter.mature(
            labels,
            forecast_origin,
            horizon_months=normalized_horizon,
        )

    training_labels = mature_labels
    filter_mature_labels = mature_labels

    def assess_origin(
        self,
        labels_or_series: pd.Series
        | Iterable[MatureLabel]
        | Mapping[int, Iterable[MatureLabel]],
        forecast_origin: Any,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> ScoreabilityResult:
        requested_horizon = _coalesce_horizon(horizon, horizon_months)
        if isinstance(labels_or_series, pd.Series):
            if requested_horizon is None:
                raise UnsupportedHorizonError(
                    "Debe indicar horizon_months al construir etiquetas desde una serie"
                )
            normalized_horizon = self._validate_requested_horizon(requested_horizon)
            labels = self.build_horizon(labels_or_series, normalized_horizon)
        else:
            normalized_horizon = (
                self._validate_requested_horizon(requested_horizon)
                if requested_horizon is not None
                else None
            )
            labels = _labels_from_input(
                labels_or_series,
                horizon_months=normalized_horizon,
            )
            if normalized_horizon is None:
                if not labels:
                    raise UnsupportedHorizonError(
                        "No se puede inferir el horizonte desde una colección vacía"
                    )
                normalized_horizon = labels[0].horizon_months
        return self.scoreability_filter.assess(
            labels,
            forecast_origin,
            horizon_months=normalized_horizon,
        )

    scoreability = assess_origin
    scoreability_for_origin = assess_origin
    evaluate_origin = assess_origin

    def filter_scoreable_labels(
        self,
        labels_or_series: pd.Series
        | Iterable[MatureLabel]
        | Mapping[int, Iterable[MatureLabel]],
        forecast_origin: Any,
        horizon: int | None = None,
        *,
        horizon_months: int | None = None,
    ) -> ScoreabilityResult:
        return self.assess_origin(
            labels_or_series,
            forecast_origin,
            horizon,
            horizon_months=horizon_months,
        )

    filter_scoreable = filter_scoreable_labels


# Public aliases for clients that use the protocol names from the design.
ForwardLabelBuilderProtocol = ForwardLabelBuilder
MatureLabelRecord = MatureLabel


__all__ = [
    "ForwardLabel",
    "ForwardLabelBuilder",
    "ForwardLabelBuilderProtocol",
    "ForwardLabelError",
    "ForwardLabelValidationError",
    "LabelError",
    "LabelScoreabilityStatus",
    "LabelValidationError",
    "MatureLabel",
    "MatureLabelRecord",
    "NOT_EVALUABLE_LABEL_NOT_MATURE",
    "NOT_EVALUABLE_ORIGIN_NOT_IN_PANEL",
    "NOT_SCOREABLE_INSUFFICIENT_TRAINING",
    "NOT_SCOREABLE_LABEL_ENDS_AT_ORIGIN",
    "NOT_SCOREABLE_LABEL_INVALID",
    "NOT_SCOREABLE_LABEL_MISSING",
    "SCOREABLE",
    "ScoreabilityFilter",
    "ScoreabilityResult",
    "UnsupportedHorizonError",
    "assess_scoreability",
    "filter_mature_labels",
    "filter_scoreable_labels",
]
