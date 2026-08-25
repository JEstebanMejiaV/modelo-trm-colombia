"""Construcción de componentes y diseños mensuales.

La selección/estimación de modelos vive en
:mod:`trm_model.monthly.estimation`; las pruebas e inferencia viven en
:mod:`trm_model.monthly.inference`.
"""
from __future__ import annotations

import pandas as pd
import statsmodels.api as sm

from trm_model.monthly.specifications import (
    ECM_LEVEL_VARIABLES,
    DIFFERENCED_COMPONENTS,
    LEVEL_COMPONENTS,
)


def difference_components(model_data: pd.DataFrame) -> pd.DataFrame:
    """Construye las series diferenciadas y componentes en niveles."""
    diff = pd.DataFrame(index=model_data.index)
    diff["D.ln_trm"] = model_data["ln_trm"].diff()
    for variable in DIFFERENCED_COMPONENTS:
        if variable in model_data:
            diff[f"D.{variable}"] = model_data[variable].diff()
    for variable in LEVEL_COMPONENTS:
        if variable in model_data:
            diff[variable] = model_data[variable]
    diff["dummy_pandemia_2020"] = model_data["dummy_pandemia_2020"]
    return diff


def make_difference_design(
    components: pd.DataFrame, p: int, q: int, index: pd.Index | None = None
) -> tuple[pd.Series, pd.DataFrame]:
    """Construye el diseño ADL de diferencias sin ajustar el modelo."""
    y = components["D.ln_trm"].rename("D.ln_trm")
    x = pd.DataFrame(index=components.index)
    for lag in range(1, p + 1):
        x[f"D.ln_trm.L{lag}"] = components["D.ln_trm"].shift(lag)
    drivers = [f"D.{variable}" for variable in ECM_LEVEL_VARIABLES] + ["D.ln_vix"]
    for driver in drivers:
        for lag in range(0, q + 1):
            x[f"{driver}.L{lag}"] = components[driver].shift(lag)
    x["dummy_pandemia_2020"] = components["dummy_pandemia_2020"]
    x = sm.add_constant(x, has_constant="add")
    combined = pd.concat([y, x], axis=1).dropna()
    if index is not None:
        combined = combined.reindex(index).dropna()
    return combined["D.ln_trm"], combined.drop(columns="D.ln_trm")


def design_term_name(component: str, lag: int) -> str:
    """Devuelve el nombre estable de un término y su rezago."""
    return f"{component}.L{lag}"


def make_timed_difference_design(
    components: pd.DataFrame,
    p: int,
    factor_specs: dict[str, dict[str, object]],
    index: pd.Index | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Construye un diseño con rezagos fijados por disponibilidad de publicación."""
    y = components["D.ln_trm"].rename("D.ln_trm")
    x = pd.DataFrame(index=components.index)
    for lag in range(1, p + 1):
        x[f"D.ln_trm.L{lag}"] = components["D.ln_trm"].shift(lag)

    for factor in factor_specs.values():
        for component, lag in factor["terminos"]:
            x[design_term_name(component, lag)] = components[component].shift(lag)
    x["dummy_pandemia_2020"] = components["dummy_pandemia_2020"]
    x = sm.add_constant(x, has_constant="add")
    combined = pd.concat([y, x], axis=1).dropna()
    if index is not None:
        combined = combined.reindex(index).dropna()
    return combined["D.ln_trm"], combined.drop(columns="D.ln_trm")


__all__ = [
    "difference_components",
    "design_term_name",
    "make_difference_design",
    "make_timed_difference_design",
]
