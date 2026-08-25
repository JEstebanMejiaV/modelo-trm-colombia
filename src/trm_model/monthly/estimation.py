"""Estimación y selección de modelos mensuales.

Este módulo contiene únicamente operaciones que ajustan modelos o seleccionan
especificaciones por criterios de información. Las tablas de errores estándar,
intervalos, pruebas y diagnósticos viven en :mod:`trm_model.monthly.inference`.
"""
from __future__ import annotations

import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.ardl import ARDL

from trm_model.features.monthly_transforms import (
    difference_components,
    make_difference_design,
    make_timed_difference_design,
)
from trm_model.monthly.specifications import (
    ECM_LEVEL_VARIABLES,
    FORECAST_FACTOR_SPECS_3,
    FORECAST_FACTOR_SPECS_4,
    INTEGRATED_FACTOR_SPECS_3,
    INTEGRATED_FACTOR_SPECS_4,
    SelectedDifferenceModel,
    SelectedModel,
)


def select_difference_model(
    model_data: pd.DataFrame,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    """Ajusta candidatos ADL en diferencias y selecciona el menor BIC."""
    components = difference_components(model_data)
    common_index = make_difference_design(components, p=3, q=2)[0].index
    candidates: list[dict[str, float | int]] = []
    selected: SelectedDifferenceModel | None = None
    for p in range(0, 4):
        for q in range(0, 3):
            y, x = make_difference_design(components, p=p, q=q, index=common_index)
            result = sm.OLS(y, x).fit()
            candidates.append(
                {
                    "p_cambio_trm": p,
                    "q_cambios_explicativas": q,
                    "aic": float(result.aic),
                    "bic": float(result.bic),
                    "r_cuadrado_ajustado": float(result.rsquared_adj),
                }
            )
            if selected is None or result.bic < selected.result.bic:
                selected = SelectedDifferenceModel(p=p, q=q, result=result, y=y, x=x)
    assert selected is not None
    grid = pd.DataFrame(candidates).sort_values("bic").reset_index(drop=True)
    return selected, grid


def select_timed_difference_model(
    model_data: pd.DataFrame,
    factor_specs: dict[str, dict[str, object]],
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    """Ajusta candidatos con temporización de publicación y selecciona por BIC."""
    components = difference_components(model_data)
    if common_index is None:
        common_index = make_timed_difference_design(
            components, p=3, factor_specs=factor_specs
        )[0].index
    candidates: list[dict[str, float | int]] = []
    selected: SelectedDifferenceModel | None = None
    for p in range(0, 4):
        y, x = make_timed_difference_design(
            components, p=p, factor_specs=factor_specs, index=common_index
        )
        result = sm.OLS(y, x).fit()
        candidates.append(
            {
                "p_cambio_trm": p,
                "aic": float(result.aic),
                "bic": float(result.bic),
                "r_cuadrado_ajustado": float(result.rsquared_adj),
            }
        )
        if selected is None or result.bic < selected.result.bic:
            selected = SelectedDifferenceModel(p=p, q=0, result=result, y=y, x=x)
    assert selected is not None
    return selected, pd.DataFrame(candidates).sort_values("bic").reset_index(drop=True)


def select_ardl(
    y: pd.Series,
    exog: pd.DataFrame,
    fixed: pd.DataFrame,
) -> tuple[SelectedModel, pd.DataFrame]:
    """Ajusta candidatos ARDL y selecciona la combinación con menor BIC."""
    candidates: list[dict[str, float | int]] = []
    selected: SelectedModel | None = None
    for p in range(1, 5):
        for q in range(1, 3):
            result = ARDL(
                y,
                lags=p,
                exog=exog,
                order=q,
                trend="c",
                fixed=fixed,
                causal=False,
                missing="raise",
            ).fit()
            candidates.append(
                {
                    "p_trm": p,
                    "q_explicativas": q,
                    "aic": float(result.aic),
                    "bic": float(result.bic),
                    "hqic": float(result.hqic),
                    "loglik": float(result.llf),
                }
            )
            if selected is None or result.bic < selected.result.bic:
                selected = SelectedModel(p=p, q=q, result=result)
    assert selected is not None
    return selected, pd.DataFrame(candidates).sort_values("bic").reset_index(drop=True)


def estimate_explanation(
    model_data: pd.DataFrame,
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    """Estima la especificación integral histórica de cuatro monedas."""
    return select_timed_difference_model(
        model_data, INTEGRATED_FACTOR_SPECS_4, common_index=common_index
    )


def estimate_forecast(
    model_data: pd.DataFrame,
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    """Estima las variantes de pronóstico y selecciona 3 o 4 monedas por BIC."""
    selected_3, grid_3 = select_timed_difference_model(
        model_data, FORECAST_FACTOR_SPECS_3, common_index=common_index
    )
    selected_4, grid_4 = select_timed_difference_model(
        model_data, FORECAST_FACTOR_SPECS_4, common_index=common_index
    )
    if selected_3.result.bic <= selected_4.result.bic:
        return selected_3, grid_3
    return selected_4, grid_4


__all__ = [
    "estimate_explanation",
    "estimate_forecast",
    "select_ardl",
    "select_difference_model",
    "select_timed_difference_model",
]
