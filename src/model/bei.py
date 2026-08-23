from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, kpss, zivot_andrews

from .config import (
    SAMPLE_START,
    SAMPLE_END,
    EXPANDED_FACTOR_SPECS_4,
    SelectedDifferenceModel,
)
from .transforms import make_timed_difference_design, select_timed_difference_model, design_term_name
from .estimation import tidy_robust_ols, diagnostics
from .validation import difference_validation


def bei_stationarity_tests(data: pd.DataFrame) -> pd.DataFrame:
    """Contrasta nivel/diferencia con constante, tendencia y un quiebre endógeno."""
    definitions = {
        "Medias mensuales separadas": "diferencial_bei_5y_pp",
        "Fechas diarias comunes": "diferencial_bei_5y_comun_pp",
    }
    rows: list[dict[str, object]] = []
    for aggregation, column in definitions.items():
        original = data[column].loc[SAMPLE_START:SAMPLE_END].dropna()
        for transformation, series in [
            ("nivel", original),
            ("primera_diferencia", original.diff().dropna()),
        ]:
            for deterministic, regression in [
                ("constante", "c"),
                ("constante_tendencia", "ct"),
            ]:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    adf = adfuller(series, regression=regression, autolag="BIC")
                    kpss_result = kpss(series, regression=regression, nlags="auto")
                rows.extend(
                    [
                        {
                            "agregacion": aggregation,
                            "variable": column,
                            "transformacion": transformation,
                            "prueba": "ADF",
                            "deterministico": deterministic,
                            "hipotesis_nula": "raiz_unitaria",
                            "n": len(series),
                            "estadistico": float(adf[0]),
                            "p_valor": float(adf[1]),
                            "rezagos": int(adf[2]),
                            "fecha_quiebre": "",
                            "critico_5_pct": float(adf[4]["5%"]),
                        },
                        {
                            "agregacion": aggregation,
                            "variable": column,
                            "transformacion": transformation,
                            "prueba": "KPSS",
                            "deterministico": deterministic,
                            "hipotesis_nula": "estacionariedad",
                            "n": len(series),
                            "estadistico": float(kpss_result[0]),
                            "p_valor": float(kpss_result[1]),
                            "rezagos": int(kpss_result[2]),
                            "fecha_quiebre": "",
                            "critico_5_pct": float(kpss_result[3]["5%"]),
                        },
                    ]
                )
            for deterministic, regression in [
                ("constante_con_quiebre", "c"),
                ("constante_tendencia_con_quiebre", "ct"),
            ]:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    za = zivot_andrews(series, regression=regression, autolag="BIC")
                break_date = series.index[int(za[4])]
                rows.append(
                    {
                        "agregacion": aggregation,
                        "variable": column,
                        "transformacion": transformation,
                        "prueba": "Zivot-Andrews",
                        "deterministico": deterministic,
                        "hipotesis_nula": "raiz_unitaria_con_quiebre",
                        "n": len(series),
                        "estadistico": float(za[0]),
                        "p_valor": float(za[1]),
                        "rezagos": int(za[3]),
                        "fecha_quiebre": break_date.strftime("%Y-%m-%d"),
                        "critico_5_pct": float(za[2]["5%"]),
                    }
                )
    return pd.DataFrame(rows)


def bei_trend_break_models(
    data: pd.DataFrame, stationarity: pd.DataFrame
) -> pd.DataFrame:
    """Compara tendencia lineal y tendencia segmentada en el propio diferencial BEI."""
    definitions = {
        "Medias mensuales separadas": "diferencial_bei_5y_pp",
        "Fechas diarias comunes": "diferencial_bei_5y_comun_pp",
    }
    rows: list[dict[str, object]] = []
    for aggregation, column in definitions.items():
        series = data[column].loc[SAMPLE_START:SAMPLE_END].dropna()
        break_record = stationarity.loc[
            stationarity["agregacion"].eq(aggregation)
            & stationarity["transformacion"].eq("nivel")
            & stationarity["prueba"].eq("Zivot-Andrews")
            & stationarity["deterministico"].eq("constante_tendencia_con_quiebre")
        ].iloc[0]
        break_date = pd.Timestamp(break_record["fecha_quiebre"])
        trend_years = pd.Series(
            np.arange(len(series), dtype=float) / 12.0,
            index=series.index,
            name="tendencia_anual",
        )
        post = (series.index >= break_date).astype(float)
        break_year = float(trend_years.loc[break_date])
        post_slope = np.maximum(0.0, trend_years.to_numpy() - break_year)
        designs = {
            "Sin tendencia": pd.DataFrame(index=series.index),
            "Tendencia lineal": pd.DataFrame(
                {"tendencia_anual": trend_years}, index=series.index
            ),
            "Tendencia segmentada con quiebre ZA": pd.DataFrame(
                {
                    "tendencia_anual": trend_years,
                    "cambio_nivel_post_quiebre": post,
                    "cambio_pendiente_post_quiebre": post_slope,
                },
                index=series.index,
            ),
        }
        for model_name, design in designs.items():
            x = sm.add_constant(design, has_constant="add")
            result = sm.OLS(series, x).fit()
            _, coefficients = tidy_robust_ols(result, maxlags=6)
            lookup = coefficients.set_index("termino")

            def value(term: str, field: str) -> float:
                if term not in lookup.index:
                    return math.nan
                return float(lookup.loc[term, field])

            rows.append(
                {
                    "agregacion": aggregation,
                    "variable": column,
                    "modelo_deterministico": model_name,
                    "fecha_quiebre_za": break_date.strftime("%Y-%m-%d"),
                    "observaciones": int(result.nobs),
                    "r_cuadrado_ajustado": float(result.rsquared_adj),
                    "aic": float(result.aic),
                    "bic": float(result.bic),
                    "tendencia_pp_por_ano": value("tendencia_anual", "coeficiente"),
                    "p_valor_hac_tendencia": value("tendencia_anual", "p_valor"),
                    "cambio_nivel_quiebre_pp": value(
                        "cambio_nivel_post_quiebre", "coeficiente"
                    ),
                    "p_valor_hac_cambio_nivel": value(
                        "cambio_nivel_post_quiebre", "p_valor"
                    ),
                    "cambio_pendiente_pp_por_ano": value(
                        "cambio_pendiente_post_quiebre", "coeficiente"
                    ),
                    "p_valor_hac_cambio_pendiente": value(
                        "cambio_pendiente_post_quiebre", "p_valor"
                    ),
                }
            )
    return pd.DataFrame(rows)


def bei_factor_specs(component: str) -> dict[str, dict[str, object]]:
    """Copia la especificación ampliada y sustituye únicamente el término BEI."""
    specs = {
        name: {**spec, "terminos": list(spec["terminos"])}
        for name, spec in EXPANDED_FACTOR_SPECS_4.items()
    }
    specs["Diferencial de compensación inflacionaria 5 años"]["terminos"] = [
        (component, 1)
    ]
    return specs


def bei_model_specification_comparison(
    model_data: pd.DataFrame,
    selected_expanded: SelectedDifferenceModel,
    break_date: pd.Timestamp,
) -> pd.DataFrame:
    """Compara transformaciones y calendarios BEI sobre una muestra idéntica."""
    from .transforms import difference_components

    components = difference_components(model_data)
    common_index = selected_expanded.y.index
    variants = [
        (
            "Nivel — medias separadas (referencia)",
            "Medias mensuales separadas",
            "nivel",
            "diferencial_bei_5y_pp",
            "ninguno",
        ),
        (
            "Primera diferencia — medias separadas (vigente)",
            "Medias mensuales separadas",
            "primera_diferencia",
            "D.diferencial_bei_5y_pp",
            "ninguno",
        ),
        (
            "Nivel — fechas diarias comunes",
            "Fechas diarias comunes",
            "nivel",
            "diferencial_bei_5y_comun_pp",
            "ninguno",
        ),
        (
            "Primera diferencia — fechas diarias comunes",
            "Fechas diarias comunes",
            "primera_diferencia",
            "D.diferencial_bei_5y_comun_pp",
            "ninguno",
        ),
        (
            "Nivel separado + tendencia lineal",
            "Medias mensuales separadas",
            "nivel",
            "diferencial_bei_5y_pp",
            "tendencia",
        ),
        (
            "Nivel separado + quiebre de coeficiente ZA",
            "Medias mensuales separadas",
            "nivel",
            "diferencial_bei_5y_pp",
            "quiebre_coeficiente",
        ),
    ]
    rows: list[dict[str, object]] = []
    full_trend = pd.Series(
        np.arange(len(model_data), dtype=float) / 12.0,
        index=model_data.index,
        name="tendencia_anual",
    )
    for name, aggregation, transformation, component, extension in variants:
        specs = bei_factor_specs(component)
        y, x = make_timed_difference_design(
            components,
            p=selected_expanded.p,
            factor_specs=specs,
            index=common_index,
        )
        bei_term = design_term_name(component, 1)
        if extension == "tendencia":
            x["tendencia_anual"] = full_trend.reindex(x.index)
        elif extension == "quiebre_coeficiente":
            x["post_quiebre_za"] = (x.index >= break_date).astype(float)
            x[f"{bei_term}_x_post_quiebre"] = x[bei_term] * x["post_quiebre_za"]

        result = sm.OLS(y, x).fit()
        robust, coefficients = tidy_robust_ols(result, maxlags=6)
        lookup = coefficients.set_index("termino")
        predictions, metrics = difference_validation(
            model_data,
            SelectedDifferenceModel(
                p=selected_expanded.p,
                q=0,
                result=result,
                y=y,
                x=x,
            ),
            holdout=48,
        )
        metric = metrics.loc[~metrics["modelo"].str.contains("Caminata")].iloc[0]
        model_error = (
            predictions["ln_trm_modelo_condicional"]
            - predictions["ln_trm_observada"]
        )
        benchmark_error = (
            predictions["ln_trm_caminata_aleatoria"]
            - predictions["ln_trm_observada"]
        )
        r2_validation = 1.0 - float(np.square(model_error).sum()) / float(
            np.square(benchmark_error).sum()
        )

        pre_coefficient = float(lookup.loc[bei_term, "coeficiente"])
        pre_p_value = float(lookup.loc[bei_term, "p_valor"])
        change_term = f"{bei_term}_x_post_quiebre"
        change_coefficient = math.nan
        change_p_value = math.nan
        post_coefficient = math.nan
        post_p_value = math.nan
        if change_term in lookup.index:
            change_coefficient = float(lookup.loc[change_term, "coeficiente"])
            change_p_value = float(lookup.loc[change_term, "p_valor"])
            restriction = np.zeros(len(result.params), dtype=float)
            restriction[list(x.columns).index(bei_term)] = 1.0
            restriction[list(x.columns).index(change_term)] = 1.0
            post_test = robust.t_test(restriction)
            post_coefficient = float(np.asarray(post_test.effect).reshape(-1)[0])
            post_p_value = float(np.asarray(post_test.pvalue).reshape(-1)[0])

        rows.append(
            {
                "especificacion": name,
                "agregacion_bei": aggregation,
                "transformacion_bei": transformation,
                "extension_deterministica": extension,
                "fecha_quiebre_za": (
                    break_date.strftime("%Y-%m-%d")
                    if extension == "quiebre_coeficiente"
                    else ""
                ),
                "observaciones": int(result.nobs),
                "p_cambio_trm": int(selected_expanded.p),
                "r_cuadrado_ajustado": float(result.rsquared_adj),
                "aic": float(result.aic),
                "bic": float(result.bic),
                "coeficiente_bei_pre_quiebre": pre_coefficient,
                "p_valor_hac_bei_pre_quiebre": pre_p_value,
                "cambio_coeficiente_post_quiebre": change_coefficient,
                "p_valor_hac_cambio_coeficiente": change_p_value,
                "coeficiente_bei_post_quiebre": post_coefficient,
                "p_valor_hac_bei_post_quiebre": post_p_value,
                "mape_condicional_pct": float(metric["mape_pct"]),
                "rmse_log_condicional": float(metric["rmse_log"]),
                "acierto_direccion_condicional_pct": float(
                    metric["acierto_direccion_pct"]
                ),
                "r2_validacion_condicional_vs_caminata": r2_validation,
                "quiebre_elegido_con_muestra_completa": extension
                == "quiebre_coeficiente",
            }
        )
    comparison = pd.DataFrame(rows)
    current = comparison.loc[
        comparison["especificacion"].eq(
            "Primera diferencia — medias separadas (vigente)"
        )
    ].iloc[0]
    if not np.isclose(current["bic"], selected_expanded.result.bic, atol=1e-8):
        raise AssertionError("La especificación BEI vigente no concilia con el modelo ampliado.")
    return comparison
