"""Inferencia estadística y diagnósticos post-estimación mensuales.

Las funciones de este módulo reciben resultados ya ajustados. No seleccionan
rezagos ni cambian la especificación: producen covarianzas HAC, intervalos,
tablas de coeficientes, pruebas de integración y diagnósticos.
"""
from __future__ import annotations

import math
import warnings

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
from statsmodels.tsa.stattools import adfuller, kpss


def tidy_robust_ols(result, maxlags: int = 6) -> tuple[object, pd.DataFrame]:
    """Construye inferencia HAC e intervalos para un resultado OLS ajustado."""
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
    """Extrae coeficientes, errores, pruebas e intervalos de un resultado."""
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
    """Extrae la inferencia de largo plazo de un resultado UECM."""
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
    """Ejecuta pruebas de residuos, especificación y estabilidad."""
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
    """Convierte el resultado del bounds test en tablas serializables."""
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


def integration_tests(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Ejecuta ADF/KPSS sobre niveles y primeras diferencias."""
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


__all__ = [
    "bounds_to_frames",
    "diagnostics",
    "integration_tests",
    "tidy_long_run",
    "tidy_result",
    "tidy_robust_ols",
]
