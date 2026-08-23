from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, kpss

from .config import (
    ECM_LEVEL_VARIABLES,
    DIFFERENCED_COMPONENTS,
    LEVEL_COMPONENTS,
    SelectedDifferenceModel,
)


def integration_tests(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column in columns:
        for transform, series in [
            ("nivel", data[column].dropna()),
            ("primera_diferencia", data[column].diff().dropna()),
        ]:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                adf = adfuller(series, regression="c", autolag="BIC")
                try:
                    kpss_result = kpss(series, regression="c", nlags="auto")
                    kpss_stat, kpss_p = float(kpss_result[0]), float(kpss_result[1])
                except Exception:
                    kpss_stat, kpss_p = math.nan, math.nan
            rows.append(
                {
                    "variable": column,
                    "transformacion": transform,
                    "n": int(series.shape[0]),
                    "adf_estadistico": float(adf[0]),
                    "adf_p": float(adf[1]),
                    "adf_rezagos": int(adf[2]),
                    "kpss_estadistico": kpss_stat,
                    "kpss_p": kpss_p,
                }
            )
    return pd.DataFrame(rows)


def difference_components(model_data: pd.DataFrame) -> pd.DataFrame:
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


def select_difference_model(model_data: pd.DataFrame) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
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


def design_term_name(component: str, lag: int) -> str:
    return f"{component}.L{lag}"


def make_timed_difference_design(
    components: pd.DataFrame,
    p: int,
    factor_specs: dict[str, dict[str, object]],
    index: pd.Index | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
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


def select_timed_difference_model(
    model_data: pd.DataFrame,
    factor_specs: dict[str, dict[str, object]],
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
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
