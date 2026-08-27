"""Utilidades para evaluaciones walk-forward temporalmente reproducibles.

Los objetivos forward se construyen con ``shift(-horizon_months)``. Por eso,
en el origen ``t`` solo pueden usarse para entrenar las observaciones cuyo
retorno ya terminó antes de ``t``. La separación se expresa en posiciones del
panel mensual, igual que la construcción actual de esos objetivos.
"""

from __future__ import annotations

from typing import Any


def matured_training_frame(
    dataset: Any,
    origin_position: int,
    horizon_months: int,
    *,
    min_train: int = 0,
    estimation_window: int | None = None,
) -> Any:
    """Devuelve solo etiquetas forward maduras antes del origen del forecast.

    ``dataset.iloc[i]`` representa el origen del pronóstico y su etiqueta
    termina ``horizon_months`` observaciones después. El corte estricto
    ``[:i-h]`` excluye también la etiqueta que terminaría exactamente en el
    origen, evitando usar información del mismo período de decisión.

    Si no hay suficientes observaciones maduras, devuelve un frame vacío con
    la misma estructura. ``estimation_window`` conserva únicamente las últimas
    observaciones maduras para evaluaciones con ventana móvil.
    """
    if horizon_months < 1:
        raise ValueError("horizon_months debe ser positivo")
    if origin_position < 0 or origin_position > len(dataset):
        raise IndexError("origin_position fuera del dataset")

    train_end = origin_position - horizon_months
    if train_end < 0:
        return dataset.iloc[0:0]

    train_start = 0
    if estimation_window is not None:
        if estimation_window < 1:
            raise ValueError("estimation_window debe ser positivo")
        train_start = max(0, train_end - estimation_window)

    train = dataset.iloc[train_start:train_end]
    if len(train) < min_train:
        return dataset.iloc[0:0]
    return train
