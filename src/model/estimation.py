from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import (
    acorr_breusch_godfrey,
    acorr_ljungbox,
    breaks_cusumolsresid,
    het_arch,
    linear_reset,
)
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.tsa.ardl import ARDL, UECM

from .config import (
    SelectedModel,
    SelectedDifferenceModel,
    REFERENCE_FACTOR_SPECS,
    INTEGRATED_FACTOR_SPECS_3,
    INTEGRATED_FACTOR_SPECS_4,
    FORECAST_FACTOR_SPECS_3,
    FORECAST_FACTOR_SPECS_4,
    ECM_LEVEL_VARIABLES,
)
from .transforms import (
    difference_components,
    make_timed_difference_design,
    select_timed_difference_model,
    integration_tests,
)
from .validation import difference_validation, difference_fit_and_contributions
from .shapley import exact_shapley_r2, block_bootstrap_shapley, subsample_stability


def select_ardl(y: pd.Series, exog: pd.DataFrame, fixed: pd.DataFrame) -> tuple[SelectedModel, pd.DataFrame]:
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


def tidy_robust_ols(result, maxlags: int = 6) -> tuple[object, pd.DataFrame]:
    robust = result.get_robustcov_results(
        cov_type="HAC", maxlags=maxlags, use_correction=True, use_t=True
    )
    names = result.model.exog_names
    confidence = robust.conf_int(alpha=0.05)
    table = pd.DataFrame(
        {
            "termino": names,
            "coeficiente": robust.params,
            "error_estandar_hac": robust.bse,
            "estadistico_t": robust.tvalues,
            "p_valor": robust.pvalues,
            "ic_95_inferior": confidence[:, 0],
            "ic_95_superior": confidence[:, 1],
        }
    )
    return robust, table


def tidy_result(result) -> pd.DataFrame:
    confidence = result.conf_int(alpha=0.05)
    return pd.DataFrame(
        {
            "termino": result.params.index,
            "coeficiente": result.params.values,
            "error_estandar_hac": result.bse.values,
            "estadistico_t": result.tvalues.values,
            "p_valor": result.pvalues.values,
            "ic_95_inferior": confidence.iloc[:, 0].values,
            "ic_95_superior": confidence.iloc[:, 1].values,
        }
    )


def tidy_long_run(result) -> pd.DataFrame:
    confidence = result.ci_conf_int(alpha=0.05)
    return pd.DataFrame(
        {
            "termino": result.ci_params.index,
            "coeficiente_largo_plazo": result.ci_params.values,
            "error_estandar": result.ci_bse.values,
            "estadistico_t": result.ci_tvalues.values,
            "p_valor": result.ci_pvalues.values,
            "ic_95_inferior": confidence.iloc[:, 0].values,
            "ic_95_superior": confidence.iloc[:, 1].values,
        }
    )


def diagnostics(result) -> pd.DataFrame:
    residuals = pd.Series(result.resid).dropna()
    lb = acorr_ljungbox(residuals, lags=[6, 12], return_df=True)
    arch = het_arch(residuals, nlags=12)
    jb = jarque_bera(residuals)
    if hasattr(result.model, "_y") and hasattr(result.model, "_x"):
        ols_proxy = sm.OLS(result.model._y, result.model._x).fit()
    else:
        ols_proxy = result
    bg = acorr_breusch_godfrey(ols_proxy, nlags=12)
    reset = linear_reset(ols_proxy, power=2, use_f=True)
    cusum = breaks_cusumolsresid(residuals, ddof=int(result.df_model) + 1)
    return pd.DataFrame(
        [
            {"prueba": "Ljung-Box (6)", "estadistico": lb.loc[6, "lb_stat"], "p_valor": lb.loc[6, "lb_pvalue"]},
            {"prueba": "Ljung-Box (12)", "estadistico": lb.loc[12, "lb_stat"], "p_valor": lb.loc[12, "lb_pvalue"]},
            {"prueba": "Breusch-Godfrey (12)", "estadistico": bg[0], "p_valor": bg[1]},
            {"prueba": "ARCH-LM (12)", "estadistico": arch[0], "p_valor": arch[1]},
            {"prueba": "Jarque-Bera", "estadistico": jb[0], "p_valor": jb[1]},
            {"prueba": "Ramsey RESET", "estadistico": float(reset.fvalue), "p_valor": float(reset.pvalue)},
            {"prueba": "CUSUM estabilidad", "estadistico": cusum[0], "p_valor": cusum[1]},
            {"prueba": "Durbin-Watson", "estadistico": durbin_watson(residuals), "p_valor": np.nan},
        ]
    )


def bounds_to_frames(bounds_result) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = pd.DataFrame(
        [
            {
                "estadistico_f": float(bounds_result.stat),
                "p_valor_i0": float(bounds_result.p_values.loc["lower"]),
                "p_valor_i1": float(bounds_result.p_values.loc["upper"]),
            }
        ]
    )
    critical = bounds_result.crit_vals.reset_index().rename(columns={"index": "percentil"})
    return summary, critical


def estimate_explanation(
    model_data: pd.DataFrame,
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    """Estima el marco macroeconómico integral de explicación histórica (4 monedas)."""
    selected, grid = select_timed_difference_model(
        model_data, INTEGRATED_FACTOR_SPECS_4, common_index=common_index
    )
    return selected, grid


def estimate_forecast(
    model_data: pd.DataFrame,
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    """Estima el modelo de pronóstico con rezagos de publicación (selecciona 3 o 4 monedas por BIC)."""
    selected_3, grid_3 = select_timed_difference_model(
        model_data, FORECAST_FACTOR_SPECS_3, common_index=common_index
    )
    selected_4, grid_4 = select_timed_difference_model(
        model_data, FORECAST_FACTOR_SPECS_4, common_index=common_index
    )
    if selected_3.result.bic <= selected_4.result.bic:
        return selected_3, grid_3
    return selected_4, grid_4
