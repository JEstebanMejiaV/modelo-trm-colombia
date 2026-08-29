"""Primitivas neutrales para evaluación OOS temporalmente reproducible.

Este módulo concentra las fronteras temporales que comparten los evaluadores
legacy y PIT. No carga datos ni decide qué fuente es válida: recibe un panel ya
materializado y devuelve únicamente ventanas/índices causales. La regla de
madurez es estricta: una etiqueta que termina en ``t`` no puede entrenar un
pronóstico cuyo origen también es ``t``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

# Mantener este módulo temporalmente neutral evita un ciclo de importación con
# el entry point de la variante wavelet. La secuencia contractual es estable y
# se comparte con la configuración de investigación.
REQUIRED_SPLITS = ("full", "2008_2019", "2020_2022", "2023_2026")

_SPLIT_WINDOWS: dict[str, tuple[pd.Period | None, pd.Period | None]] = {
    "full": (None, None),
    "2008_2019": (pd.Period("2008-01", freq="M"), pd.Period("2019-12", freq="M")),
    "2020_2022": (pd.Period("2020-01", freq="M"), pd.Period("2022-12", freq="M")),
    "2023_2026": (pd.Period("2023-01", freq="M"), pd.Period("2026-12", freq="M")),
}


@dataclass(frozen=True)
class OOSWindow:
    """Límites causales de entrenamiento para un origen e horizonte."""

    origin_position: int
    horizon_months: int
    train_start: int
    train_end: int
    min_train: int = 0
    estimation_window: int | None = None

    def __post_init__(self) -> None:
        if self.origin_position < 0:
            raise ValueError("origin_position debe ser no negativo")
        if self.horizon_months < 1:
            raise ValueError("horizon_months debe ser positivo")
        if self.train_start < 0 or self.train_end < 0:
            raise ValueError("los límites de entrenamiento deben ser no negativos")
        if self.train_start > self.train_end:
            raise ValueError("train_start no puede superar train_end")
        if self.min_train < 0:
            raise ValueError("min_train no puede ser negativo")
        if self.estimation_window is not None and self.estimation_window < 1:
            raise ValueError("estimation_window debe ser positivo")

    @property
    def n_rows(self) -> int:
        return max(0, self.train_end - self.train_start)

    @property
    def is_scoreable(self) -> bool:
        return self.n_rows >= self.min_train

    @property
    def slice(self) -> slice:
        return slice(self.train_start, self.train_end)


def _validated_position(dataset: Any, origin_position: int) -> int:
    if isinstance(origin_position, bool):
        raise ValueError("origin_position debe ser entero")
    try:
        position = int(origin_position)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("origin_position debe ser entero") from error
    if position != origin_position:
        raise ValueError("origin_position debe ser entero")
    if position < 0 or position > len(dataset):
        raise IndexError("origin_position fuera del dataset")
    return position


def oos_window(
    dataset: Any,
    origin_position: int,
    horizon_months: int,
    *,
    min_train: int = 0,
    estimation_window: int | None = None,
) -> OOSWindow:
    """Calcula una ventana expanding/rolling sin observar etiquetas futuras.

    ``train_end = origin_position - horizon_months`` implementa el embargo
    estricto para objetivos construidos con ``shift(-horizon_months)``. La
    ventana devuelta no incluye nunca la observación cuyo label termina en el
    origen.
    """

    position = _validated_position(dataset, origin_position)
    if isinstance(horizon_months, bool):
        raise ValueError("horizon_months debe ser entero positivo")
    try:
        horizon = int(horizon_months)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("horizon_months debe ser entero positivo") from error
    if horizon < 1:
        raise ValueError("horizon_months debe ser positivo")
    if isinstance(min_train, bool) or int(min_train) != min_train or min_train < 0:
        raise ValueError("min_train debe ser entero no negativo")
    if estimation_window is not None and (
        isinstance(estimation_window, bool)
        or int(estimation_window) != estimation_window
        or estimation_window < 1
    ):
        raise ValueError("estimation_window debe ser positivo")

    train_end = max(0, position - horizon)
    train_start = 0
    if estimation_window is not None:
        train_start = max(0, train_end - int(estimation_window))
    return OOSWindow(
        origin_position=position,
        horizon_months=horizon,
        train_start=train_start,
        train_end=train_end,
        min_train=int(min_train),
        estimation_window=None if estimation_window is None else int(estimation_window),
    )


def matured_training_bounds(
    dataset: Any,
    origin_position: int,
    horizon_months: int,
    *,
    min_train: int = 0,
    estimation_window: int | None = None,
) -> tuple[int, int]:
    """Devuelve ``(start, end)`` de las etiquetas maduras antes del origen."""

    window = oos_window(
        dataset,
        origin_position,
        horizon_months,
        min_train=min_train,
        estimation_window=estimation_window,
    )
    if not window.is_scoreable:
        return 0, 0
    return window.train_start, window.train_end


def matured_training_frame(
    dataset: Any,
    origin_position: int,
    horizon_months: int,
    *,
    min_train: int = 0,
    estimation_window: int | None = None,
) -> Any:
    """Devuelve solo etiquetas forward maduras antes del origen del forecast.

    Si no hay suficientes observaciones maduras, devuelve un frame vacío con
    la misma estructura. ``estimation_window`` conserva únicamente las últimas
    observaciones maduras para evaluaciones con ventana móvil.
    """

    window = oos_window(
        dataset,
        origin_position,
        horizon_months,
        min_train=min_train,
        estimation_window=estimation_window,
    )
    if not window.is_scoreable:
        return dataset.iloc[0:0]
    return dataset.iloc[window.slice]


# Alias explícitos para callers que trabajan con índices en vez de frames.
matured_training_slice = matured_training_bounds
causal_training_window = oos_window


def label_end_is_strictly_before(label_end: Any, forecast_origin: Any) -> bool:
    """Indica si el final de una etiqueta precede estrictamente al origen."""

    try:
        label_period = _period(label_end)
        origin_period = _period(forecast_origin)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("label_end y forecast_origin deben ser fechas válidas") from error
    return label_period < origin_period


# ---------------------------------------------------------------------------
# Partición temporal reutilizable
# ---------------------------------------------------------------------------


def _period(value: Any) -> pd.Period:
    if isinstance(value, pd.Period):
        try:
            return value.asfreq("M")
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"fecha inválida: {value!r}") from error
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"fecha inválida: {value!r}") from error
    if pd.isna(timestamp):
        raise ValueError(f"fecha inválida: {value!r}")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize().to_period("M")


def assign_evaluation_splits(
    origin_date: Any,
    *,
    data_cutoff: Any | None = None,
    splits: tuple[str, ...] | list[str] = REQUIRED_SPLITS,
) -> tuple[str, ...]:
    """Asigna un origen a ``full`` y, como máximo, una submuestra."""

    period = _period(origin_date)
    requested = tuple(str(item) for item in splits)
    unknown = sorted(set(requested) - set(REQUIRED_SPLITS))
    if unknown:
        raise ValueError(f"splits no soportados: {unknown!r}")
    cutoff_period = None if data_cutoff is None else _period(data_cutoff)
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


assign_splits = assign_evaluation_splits
splits_for_origin = assign_evaluation_splits
split_for_origin = assign_evaluation_splits
split_membership = assign_evaluation_splits


def assign_split(
    origin_date: Any,
    split: str | None = None,
    *,
    data_cutoff: Any | None = None,
    splits: tuple[str, ...] | list[str] = REQUIRED_SPLITS,
) -> tuple[str, ...] | bool:
    assigned = assign_evaluation_splits(origin_date, data_cutoff=data_cutoff, splits=splits)
    if split is None:
        return assigned
    return str(split) in assigned


__all__ = [
    "OOSWindow",
    "assign_evaluation_splits",
    "assign_split",
    "assign_splits",
    "causal_training_window",
    "label_end_is_strictly_before",
    "matured_training_bounds",
    "matured_training_frame",
    "matured_training_slice",
    "oos_window",
    "split_for_origin",
    "split_membership",
    "splits_for_origin",
]
