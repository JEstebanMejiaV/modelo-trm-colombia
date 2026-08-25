"""Calendarios de disponibilidad y rezagos de publicación."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Any

import pandas as pd

from ..paths import ProjectPaths, project_paths

REQUIRED_COLUMNS = {
    "factor",
    "rezago_meses_modelo",
    "frecuencia_y_publicacion",
    "regla_disponibilidad_al_inicio_del_mes_t",
}


def load_availability_calendar(
    path: Path | None = None, *, paths: ProjectPaths | None = None
) -> pd.DataFrame:
    project = paths or project_paths()
    calendar_path = (
        path
        or project.results / "pronostico" / "calendario_disponibilidad_pronostico.csv"
    ).resolve()
    if not calendar_path.is_file():
        raise FileNotFoundError(f"No existe el calendario de disponibilidad: {calendar_path}")
    frame = pd.read_csv(calendar_path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Faltan columnas en el calendario de disponibilidad: {sorted(missing)}")
    frame["rezago_meses_modelo"] = pd.to_numeric(
        frame["rezago_meses_modelo"], errors="raise"
    ).astype(int)
    if (frame["rezago_meses_modelo"] < 1).any():
        bad = frame.loc[frame["rezago_meses_modelo"] < 1, "factor"].tolist()
        raise ValueError(f"Hay factores contemporáneos en el calendario de pronóstico: {bad}")
    if frame["factor"].duplicated().any():
        raise ValueError("El calendario de disponibilidad contiene factores duplicados")
    return frame


def legacy_forecast_availability() -> pd.DataFrame:
    """Devuelve el calendario declarado por la especificación mensual legacy."""
    from model.config import FORECAST_AVAILABILITY

    return pd.DataFrame(
        FORECAST_AVAILABILITY,
        columns=[
            "factor",
            "rezago_meses_modelo",
            "frecuencia_y_publicacion",
            "regla_disponibilidad_al_inicio_del_mes_t",
        ],
    )


def factor_lag_map(factor_specs: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """Extrae el mayor rezago de cada factor legacy o tipado."""
    result: dict[str, int] = {}
    for factor_name, specification in factor_specs.items():
        terms = specification.get("terminos") or specification.get("terms")
        if terms is None:
            raise ValueError(f"La especificación no tiene términos: {factor_name}")
        lags = []
        for term in terms:
            if isinstance(term, Mapping):
                lags.append(int(term["lag_months"]))
            else:
                lags.append(int(term[1]))
        result[factor_name] = max(lags)
    return result
