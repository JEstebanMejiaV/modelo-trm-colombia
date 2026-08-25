"""
Orquestador de las especificaciones de la TRM Colombia.

Importa toda la logica de estimacion del paquete src/model/ y ejecuta:
1. Carga de datos y construccion de la base mensual
2. Estimación de las especificaciones históricas de controles externos y marco macroeconómico integral
3. Estimacion del pronostico con rezagos de publicacion
4. Comparacion regional, Shapley, bootstrap y estabilidad
5. Contraste ARDL-ECM exploratorio
6. Robustez BEI
7. Test Diebold-Mariano y modelos parsimoniosos
8. Escritura de CSVs, metadata y actualizacion del README
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.tsa.ardl import UECM

from trm_model.monthly.specifications import (
    ROOT,
    RAW,
    RESULTS,
    DATA,
    SAMPLE_START,
    SAMPLE_END,
    REFERENCE_MODEL_ID,
    REFERENCE_MODEL_LABEL,
    INTEGRATED_MODEL_ID,
    INTEGRATED_MODEL_LABEL,
    SHAPLEY_BOOTSTRAP_REPLICATIONS,
    SHAPLEY_BOOTSTRAP_BLOCK_MONTHS,
    SHAPLEY_BOOTSTRAP_PERMUTATIONS,
    SHAPLEY_BOOTSTRAP_SEED,
    ECM_LEVEL_VARIABLES,
    REFERENCE_FACTOR_SPECS,
    INTEGRATED_FACTOR_SPECS,
    INTEGRATED_FACTOR_SPECS_3,
    INTEGRATED_FACTOR_SPECS_4,
    FORECAST_FACTOR_SPECS_3,
    FORECAST_FACTOR_SPECS_4,
    FORECAST_AVAILABILITY,
    DIFFERENCED_COMPONENTS,
    LEVEL_COMPONENTS,
    GLOBAL_RAW_COMPONENTS,
    INTERNAL_RAW_COMPONENTS,
    SelectedModel,
    SelectedDifferenceModel,
    sha256_file,
)
from trm_model.data.monthly_loaders import build_dataset
from trm_model.features.monthly_transforms import (
    difference_components,
    make_timed_difference_design,
)
from trm_model.monthly.estimation import (
    select_ardl,
    select_timed_difference_model,
)
from trm_model.monthly.inference import (
    bounds_to_frames,
    diagnostics,
    integration_tests,
    tidy_long_run,
    tidy_result,
    tidy_robust_ols,
)
from model.validation import (
    difference_validation,
    difference_fit_and_contributions,
)
from model.shapley import (
    exact_shapley_r2,
    block_bootstrap_shapley,
    subsample_stability,
)
from model.bei import (
    bei_stationarity_tests,
    bei_trend_break_models,
    bei_model_specification_comparison,
)
from model.readme_sync import update_readme_fragments


def estimate_explanation(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
    common_index: pd.Index,
) -> dict:
    """
    Estima las especificaciones de explicación histórica de controles externos y del marco macroeconómico integral.

    Incluye:
    - Especificación de controles externos (REFERENCE_FACTOR_SPECS): selección de rezagos, coeficientes,
      diagnósticos, ajuste, contribuciones y validación condicional.
    - Marco macroeconómico integral con 3 monedas (INTEGRATED_FACTOR_SPECS_3): coeficientes y validación.
    - Marco macroeconómico integral con 4 monedas (INTEGRATED_FACTOR_SPECS_4): especificación activa
      con Shapley, bootstrap e intervalos de estabilidad.
    - Contraste ARDL–ECM exploratorio.

    Retorna un diccionario con todos los objetos necesarios para la escritura
    de resultados y la comparación con el pronóstico.
    """
    # ── Especificación de controles externos ──────────────────────────────────
    selected_diff, lag_grid_diff = select_timed_difference_model(
        model_data, REFERENCE_FACTOR_SPECS, common_index=common_index
    )
    _, coefficients_diff = tidy_robust_ols(selected_diff.result, maxlags=6)
    diagnostics_diff = diagnostics(selected_diff.result)
    predictions, validation = difference_validation(
        model_data, selected_diff, holdout=min(48, len(selected_diff.y) // 4)
    )
    fitted_diff, contributions_diff = difference_fit_and_contributions(
        model_data, selected_diff
    )

    # ── Marco macroeconómico integral — 3 monedas (comparación) ──────────────
    selected_integrated_3, _ = select_timed_difference_model(
        model_data, INTEGRATED_FACTOR_SPECS_3, common_index=common_index
    )
    _, coefficients_integrated_3 = tidy_robust_ols(selected_integrated_3.result, maxlags=6)
    predictions_integrated_3, validation_integrated_3 = difference_validation(
        model_data, selected_integrated_3, holdout=min(48, len(selected_integrated_3.y) // 4)
    )

    # ── Marco macroeconómico integral — 4 monedas (activo) ───────────────────
    selected_integrated, lag_grid_integrated = select_timed_difference_model(
        model_data, INTEGRATED_FACTOR_SPECS_4, common_index=common_index
    )
    _, coefficients_integrated = tidy_robust_ols(selected_integrated.result, maxlags=6)
    diagnostics_integrated = diagnostics(selected_integrated.result)
    predictions_integrated, validation_integrated = difference_validation(
        model_data, selected_integrated, holdout=min(48, len(selected_integrated.y) // 4)
    )
    fitted_integrated, contributions_integrated = difference_fit_and_contributions(
        model_data, selected_integrated
    )
    shapley_integrated = exact_shapley_r2(
        selected_integrated, INTEGRATED_FACTOR_SPECS_4, coefficients_integrated
    )
    shapley_bootstrap = block_bootstrap_shapley(
        selected_integrated, INTEGRATED_FACTOR_SPECS_4, shapley_integrated
    )
    stability_detail, stability_summary = subsample_stability(
        selected_integrated,
        INTEGRATED_FACTOR_SPECS_4,
        shapley_integrated,
        coefficients_integrated,
    )

    # ── Contraste ARDL–ECM exploratorio ──────────────────────────────────────
    y = model_data["ln_trm"]
    exog = model_data[ECM_LEVEL_VARIABLES]
    fixed = model_data[["dln_vix", "dummy_pandemia_2020"]]
    selected_ecm, lag_grid_ecm = select_ardl(y, exog, fixed)
    uecm_model = UECM.from_ardl(selected_ecm.result.model)
    uecm_result = uecm_model.fit(
        cov_type="HAC", cov_kwds={"maxlags": 6, "use_correction": True}, use_t=True
    )
    bounds = uecm_result.bounds_test(case=3, cov_type="nonrobust")
    bounds_summary, bounds_critical = bounds_to_frames(bounds)
    short_run_ecm = tidy_result(uecm_result)
    long_run_ecm = tidy_long_run(uecm_result)
    diagnostics_ecm = diagnostics(selected_ecm.result)

    # ── Pruebas de integración ───────────────────────────────────────────────
    tests = integration_tests(
        model_data,
        [
            "ln_trm",
            *ECM_LEVEL_VARIABLES,
            "ln_vix",
            "embig_colombia_pp",
            "ln_reservas_netas_sin_flar",
            "asinh_balanza_comercial",
            "asinh_flujos_capital",
            "diferencial_bei_5y_pp",
            "diferencial_bei_5y_comun_pp",
        ],
    )

    return {
        "selected_diff": selected_diff,
        "lag_grid_diff": lag_grid_diff,
        "coefficients_diff": coefficients_diff,
        "diagnostics_diff": diagnostics_diff,
        "predictions": predictions,
        "validation": validation,
        "fitted_diff": fitted_diff,
        "contributions_diff": contributions_diff,
        "selected_integrated_3": selected_integrated_3,
        "coefficients_integrated_3": coefficients_integrated_3,
        "predictions_integrated_3": predictions_integrated_3,
        "validation_integrated_3": validation_integrated_3,
        "selected_integrated": selected_integrated,
        "lag_grid_integrated": lag_grid_integrated,
        "coefficients_integrated": coefficients_integrated,
        "diagnostics_integrated": diagnostics_integrated,
        "predictions_integrated": predictions_integrated,
        "validation_integrated": validation_integrated,
        "fitted_integrated": fitted_integrated,
        "contributions_integrated": contributions_integrated,
        "shapley_integrated": shapley_integrated,
        "shapley_bootstrap": shapley_bootstrap,
        "stability_detail": stability_detail,
        "stability_summary": stability_summary,
        "selected_ecm": selected_ecm,
        "lag_grid_ecm": lag_grid_ecm,
        "bounds": bounds,
        "bounds_summary": bounds_summary,
        "bounds_critical": bounds_critical,
        "short_run_ecm": short_run_ecm,
        "long_run_ecm": long_run_ecm,
        "diagnostics_ecm": diagnostics_ecm,
        "uecm_result": uecm_result,
        "tests": tests,
    }


def estimate_forecast(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
) -> dict:
    """
    Estima el modelo de pronóstico con rezagos de publicación.

    Compara composiciones regionales de 3 y 4 monedas y selecciona por BIC.
    Retorna los resultados del pronóstico seleccionado y las variantes para
    la comparación regional.
    """
    forecast_common_index = make_timed_difference_design(
        components, p=3, factor_specs=FORECAST_FACTOR_SPECS_4
    )[0].index

    # ── Pronóstico — 3 monedas ───────────────────────────────────────────────
    selected_forecast_3, lag_grid_forecast_3 = select_timed_difference_model(
        model_data, FORECAST_FACTOR_SPECS_3, common_index=forecast_common_index
    )
    _, coefficients_forecast_3 = tidy_robust_ols(selected_forecast_3.result, maxlags=6)
    diagnostics_forecast_3 = diagnostics(selected_forecast_3.result)
    predictions_forecast_3, validation_forecast_3 = difference_validation(
        model_data, selected_forecast_3, holdout=min(48, len(selected_forecast_3.y) // 4)
    )

    # ── Pronóstico — 4 monedas ───────────────────────────────────────────────
    selected_forecast_4, lag_grid_forecast_4 = select_timed_difference_model(
        model_data, FORECAST_FACTOR_SPECS_4, common_index=forecast_common_index
    )
    _, coefficients_forecast_4 = tidy_robust_ols(selected_forecast_4.result, maxlags=6)
    diagnostics_forecast_4 = diagnostics(selected_forecast_4.result)
    predictions_forecast_4, validation_forecast_4 = difference_validation(
        model_data, selected_forecast_4, holdout=min(48, len(selected_forecast_4.y) // 4)
    )

    # ── Selección por BIC ────────────────────────────────────────────────────
    if selected_forecast_3.result.bic <= selected_forecast_4.result.bic:
        forecast_currencies = "BRL, CLP y MXN"
        selected_forecast = selected_forecast_3
        lag_grid_forecast = lag_grid_forecast_3
        coefficients_forecast = coefficients_forecast_3
        diagnostics_forecast = diagnostics_forecast_3
        predictions_forecast = predictions_forecast_3.copy()
        validation_forecast = validation_forecast_3.copy()
    else:
        forecast_currencies = "BRL, CLP, MXN y PEN"
        selected_forecast = selected_forecast_4
        lag_grid_forecast = lag_grid_forecast_4
        coefficients_forecast = coefficients_forecast_4
        diagnostics_forecast = diagnostics_forecast_4
        predictions_forecast = predictions_forecast_4.copy()
        validation_forecast = validation_forecast_4.copy()

    return {
        "forecast_currencies": forecast_currencies,
        "selected_forecast": selected_forecast,
        "lag_grid_forecast": lag_grid_forecast,
        "coefficients_forecast": coefficients_forecast,
        "diagnostics_forecast": diagnostics_forecast,
        "predictions_forecast": predictions_forecast,
        "validation_forecast": validation_forecast,
        "selected_forecast_3": selected_forecast_3,
        "coefficients_forecast_3": coefficients_forecast_3,
        "predictions_forecast_3": predictions_forecast_3,
        "validation_forecast_3": validation_forecast_3,
        "selected_forecast_4": selected_forecast_4,
        "coefficients_forecast_4": coefficients_forecast_4,
        "predictions_forecast_4": predictions_forecast_4,
        "validation_forecast_4": validation_forecast_4,
    }




def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "explicacion").mkdir(exist_ok=True)
    (RESULTS / "pronostico").mkdir(exist_ok=True)
    (RESULTS / "robustez").mkdir(exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    data = build_dataset()
    model_columns = [
        "ln_trm",
        *ECM_LEVEL_VARIABLES,
        "ln_vix",
        "dln_vix",
        "embig_colombia_pp",
        "ln_reservas_netas_sin_flar",
        "asinh_balanza_comercial",
        "asinh_flujos_capital",
        *LEVEL_COMPONENTS,
        "ise_total_dane",
        "ipc_colombia_indice",
        *INTERNAL_RAW_COMPONENTS,
        *GLOBAL_RAW_COMPONENTS,
        "dummy_pandemia_2020",
    ]
    expected_index = pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")
    model_data = data.reindex(expected_index)[model_columns].copy()
    if model_data.isna().any().any():
        missing = {
            column: model_data.index[model_data[column].isna()].strftime("%Y-%m").tolist()
            for column in model_data.columns
            if model_data[column].isna().any()
        }
        raise ValueError(f"La muestra balanceada contiene meses faltantes: {missing}")
    model_data.index.name = "fecha"
    bei_stationarity = bei_stationarity_tests(model_data)
    bei_trend_breaks = bei_trend_break_models(model_data, bei_stationarity)
    bei_break_date = pd.Timestamp(
        bei_stationarity.loc[
            bei_stationarity["agregacion"].eq("Medias mensuales separadas")
            & bei_stationarity["transformacion"].eq("nivel")
            & bei_stationarity["prueba"].eq("Zivot-Andrews")
            & bei_stationarity["deterministico"].eq(
                "constante_tendencia_con_quiebre"
            ),
            "fecha_quiebre",
        ].iloc[0]
    )

    components = difference_components(model_data)
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=INTEGRATED_FACTOR_SPECS
    )[0].index

    # ── Explicación histórica (controles externos + marco macroeconómico integral + ECM) ──
    print("Estimando modelos de explicación histórica...")
    explanation = estimate_explanation(model_data, components, common_index)
    selected_diff = explanation["selected_diff"]
    lag_grid_diff = explanation["lag_grid_diff"]
    coefficients_diff = explanation["coefficients_diff"]
    diagnostics_diff = explanation["diagnostics_diff"]
    predictions = explanation["predictions"]
    validation = explanation["validation"]
    fitted_diff = explanation["fitted_diff"]
    contributions_diff = explanation["contributions_diff"]
    selected_integrated_3 = explanation["selected_integrated_3"]
    coefficients_integrated_3 = explanation["coefficients_integrated_3"]
    predictions_integrated_3 = explanation["predictions_integrated_3"]
    validation_integrated_3 = explanation["validation_integrated_3"]
    selected_integrated = explanation["selected_integrated"]
    lag_grid_integrated = explanation["lag_grid_integrated"]
    coefficients_integrated = explanation["coefficients_integrated"]
    diagnostics_integrated = explanation["diagnostics_integrated"]
    predictions_integrated = explanation["predictions_integrated"]
    validation_integrated = explanation["validation_integrated"]
    fitted_integrated = explanation["fitted_integrated"]
    contributions_integrated = explanation["contributions_integrated"]
    shapley_integrated = explanation["shapley_integrated"]
    shapley_bootstrap = explanation["shapley_bootstrap"]
    stability_detail = explanation["stability_detail"]
    stability_summary = explanation["stability_summary"]
    selected_ecm = explanation["selected_ecm"]
    lag_grid_ecm = explanation["lag_grid_ecm"]
    bounds = explanation["bounds"]
    bounds_summary = explanation["bounds_summary"]
    bounds_critical = explanation["bounds_critical"]
    short_run_ecm = explanation["short_run_ecm"]
    long_run_ecm = explanation["long_run_ecm"]
    diagnostics_ecm = explanation["diagnostics_ecm"]
    uecm_result = explanation["uecm_result"]
    tests = explanation["tests"]

    bei_model_comparison = bei_model_specification_comparison(
        model_data, selected_integrated, bei_break_date
    )

    # ── Pronóstico con rezagos de publicación ────────────────────────────────
    print("Estimando modelo de pronóstico...")
    forecast = estimate_forecast(model_data, components)
    forecast_currencies = forecast["forecast_currencies"]
    selected_forecast = forecast["selected_forecast"]
    lag_grid_forecast = forecast["lag_grid_forecast"]
    coefficients_forecast = forecast["coefficients_forecast"]
    diagnostics_forecast = forecast["diagnostics_forecast"]
    predictions_forecast = forecast["predictions_forecast"]
    validation_forecast = forecast["validation_forecast"]
    selected_forecast_3 = forecast["selected_forecast_3"]
    coefficients_forecast_3 = forecast["coefficients_forecast_3"]
    predictions_forecast_3 = forecast["predictions_forecast_3"]
    validation_forecast_3 = forecast["validation_forecast_3"]
    selected_forecast_4 = forecast["selected_forecast_4"]
    coefficients_forecast_4 = forecast["coefficients_forecast_4"]
    predictions_forecast_4 = forecast["predictions_forecast_4"]
    validation_forecast_4 = forecast["validation_forecast_4"]

    def out_of_sample_r2(
        predictions_frame: pd.DataFrame,
        forecast_column: str = "ln_trm_modelo_condicional",
    ) -> float:
        model_error = (
            predictions_frame[forecast_column]
            - predictions_frame["ln_trm_observada"]
        )
        benchmark_error = (
            predictions_frame["ln_trm_caminata_aleatoria"]
            - predictions_frame["ln_trm_observada"]
        )
        return 1.0 - float(np.square(model_error).sum()) / float(
            np.square(benchmark_error).sum()
        )

    base_validation_row = validation.iloc[0]
    integrated_validation_row = validation_integrated.iloc[0]
    comparison = pd.DataFrame(
        [
            {
                "modelo": REFERENCE_MODEL_LABEL,
                "observaciones": int(selected_diff.result.nobs),
                "r_cuadrado": float(selected_diff.result.rsquared),
                "r_cuadrado_ajustado": float(selected_diff.result.rsquared_adj),
                "aic": float(selected_diff.result.aic),
                "bic": float(selected_diff.result.bic),
                "mape_pct": float(base_validation_row["mape_pct"]),
                "acierto_direccion_pct": float(
                    base_validation_row["acierto_direccion_pct"]
                ),
                "r2_validacion_condicional_vs_caminata": out_of_sample_r2(predictions),
            },
            {
                "modelo": INTEGRATED_MODEL_LABEL,
                "observaciones": int(selected_integrated.result.nobs),
                "r_cuadrado": float(selected_integrated.result.rsquared),
                "r_cuadrado_ajustado": float(selected_integrated.result.rsquared_adj),
                "aic": float(selected_integrated.result.aic),
                "bic": float(selected_integrated.result.bic),
                "mape_pct": float(integrated_validation_row["mape_pct"]),
                "acierto_direccion_pct": float(
                    integrated_validation_row["acierto_direccion_pct"]
                ),
                "r2_validacion_condicional_vs_caminata": out_of_sample_r2(
                    predictions_integrated
                ),
            },
        ]
    )

    regional_correlation = float(
        model_data["factor_monedas_regionales_3"].corr(
            model_data["factor_monedas_regionales_4"]
        )
    )

    def coefficient_value(table: pd.DataFrame, term: str, column: str) -> float:
        return float(table.loc[table["termino"].eq(term), column].iloc[0])

    regional_comparison_rows: list[dict[str, object]] = []
    regional_variants = [
        (
            "Explicación histórica",
            "BRL, CLP y MXN",
            selected_integrated_3,
            coefficients_integrated_3,
            predictions_integrated_3,
            validation_integrated_3,
            "factor_monedas_regionales_3.L0",
        ),
        (
            "Explicación histórica",
            "BRL, CLP, MXN y PEN",
            selected_integrated,
            coefficients_integrated,
            predictions_integrated,
            validation_integrated,
            "factor_monedas_regionales_4.L0",
        ),
        (
            "Pronóstico con rezagos de publicación",
            "BRL, CLP y MXN",
            selected_forecast_3,
            coefficients_forecast_3,
            predictions_forecast_3,
            validation_forecast_3,
            "factor_monedas_regionales_3.L1",
        ),
        (
            "Pronóstico con rezagos de publicación",
            "BRL, CLP, MXN y PEN",
            selected_forecast_4,
            coefficients_forecast_4,
            predictions_forecast_4,
            validation_forecast_4,
            "factor_monedas_regionales_4.L1",
        ),
    ]
    for use, currencies, selected_variant, coefficient_table, predictions_variant, validation_variant, term in regional_variants:
        metric = validation_variant.loc[
            ~validation_variant["modelo"].str.contains("Caminata", case=False)
        ].iloc[0]
        regional_comparison_rows.append(
            {
                "uso": use,
                "monedas": currencies,
                "observaciones": int(selected_variant.result.nobs),
                "p_cambio_trm": int(selected_variant.p),
                "r_cuadrado": float(selected_variant.result.rsquared),
                "r_cuadrado_ajustado": float(selected_variant.result.rsquared_adj),
                "aic": float(selected_variant.result.aic),
                "bic": float(selected_variant.result.bic),
                "mape_pct": float(metric["mape_pct"]),
                "acierto_direccion_pct": float(metric["acierto_direccion_pct"]),
                "r2_validacion_vs_caminata": out_of_sample_r2(predictions_variant),
                "coeficiente_factor_regional": coefficient_value(
                    coefficient_table, term, "coeficiente"
                ),
                "p_valor_hac_factor_regional": coefficient_value(
                    coefficient_table, term, "p_valor"
                ),
                "correlacion_factores_3_4": regional_correlation,
            }
        )
    regional_comparison = pd.DataFrame(regional_comparison_rows)

    availability = pd.DataFrame(
        FORECAST_AVAILABILITY,
        columns=[
            "factor",
            "rezago_meses_modelo",
            "frecuencia_y_publicacion",
            "regla_disponibilidad_al_inicio_del_mes_t",
        ],
    )

    validation_forecast.loc[
        ~validation_forecast["modelo"].str.contains("Caminata", case=False), "modelo"
    ] = "Pronóstico con rezagos de publicación"
    predictions_forecast = predictions_forecast.rename(
        columns={
            "ln_trm_modelo_condicional": "ln_trm_pronostico_publicacion",
            "cambio_log_modelo": "cambio_log_pronostico",
            "trm_modelo_condicional": "trm_pronostico_publicacion",
        }
    )

    data.to_csv(DATA / "modelo_trm_datos_mensuales.csv", encoding="utf-8-sig", float_format="%.10g")
    model_data.to_csv(DATA / "modelo_trm_muestra_estimacion.csv", encoding="utf-8-sig", float_format="%.10g")
    bei_aggregation_columns = [
        "tes_5y_pesos_colombia_pct",
        "tes_5y_uvr_colombia_pct",
        "bei_eeuu_5y_pct",
        "bei_colombia_5y_pct",
        "diferencial_bei_5y_pp",
        "tes_5y_pesos_comun_pct",
        "tes_5y_uvr_comun_pct",
        "bei_eeuu_5y_comun_pct",
        "diferencial_bei_5y_comun_pp",
        "diferencia_comun_menos_separada_pp",
        "dias_tes_pesos",
        "dias_tes_uvr",
        "dias_bei_eeuu",
        "dias_comunes",
    ]
    data.loc[SAMPLE_START:SAMPLE_END, bei_aggregation_columns].to_csv(
        RESULTS / "robustez/comparacion_agregacion_bei_5y.csv",
        encoding="utf-8-sig",
        float_format="%.10g",
    )
    bei_stationarity.to_csv(
        RESULTS / "robustez/pruebas_estacionariedad_bei_5y.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.10g",
    )
    bei_trend_breaks.to_csv(
        RESULTS / "robustez/tendencias_quiebres_bei_5y.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.10g",
    )
    bei_model_comparison.to_csv(
        RESULTS / "robustez/comparacion_especificaciones_bei_5y.csv",
        index=False,
        encoding="utf-8-sig",
        float_format="%.10g",
    )
    lag_grid_diff.to_csv(
        RESULTS / "explicacion/seleccion_rezagos_adl_diferencias.csv", index=False, encoding="utf-8-sig"
    )
    coefficients_diff.to_csv(
        RESULTS / "explicacion/coeficientes_controles_externos.csv", index=False, encoding="utf-8-sig"
    )
    diagnostics_diff.to_csv(
        RESULTS / "explicacion/diagnosticos_controles_externos.csv", index=False, encoding="utf-8-sig"
    )
    fitted_diff.to_csv(
        RESULTS / "explicacion/ajuste_historico_controles_externos.csv", encoding="utf-8-sig"
    )
    contributions_diff.to_csv(
        RESULTS / "explicacion/contribuciones_controles_externos.csv", encoding="utf-8-sig"
    )
    lag_grid_integrated.to_csv(
        RESULTS / "explicacion/seleccion_rezagos_marco_macro_integral.csv",
        index=False,
        encoding="utf-8-sig",
    )
    coefficients_integrated.to_csv(
        RESULTS / "explicacion/coeficientes_marco_macro_integral.csv", index=False, encoding="utf-8-sig"
    )
    diagnostics_integrated.to_csv(
        RESULTS / "explicacion/diagnosticos_marco_macro_integral.csv", index=False, encoding="utf-8-sig"
    )
    fitted_integrated.to_csv(
        RESULTS / "explicacion/ajuste_historico_marco_macro_integral.csv", encoding="utf-8-sig"
    )
    contributions_integrated.to_csv(
        RESULTS / "explicacion/contribuciones_marco_macro_integral.csv", encoding="utf-8-sig"
    )
    shapley_integrated.to_csv(
        RESULTS / "explicacion/pesos_explicativos_marco_macro_integral.csv",
        index=False,
        encoding="utf-8-sig",
    )
    shapley_bootstrap.to_csv(
        RESULTS / "explicacion/intervalos_bootstrap_pesos_shapley.csv",
        index=False,
        encoding="utf-8-sig",
    )
    stability_detail.to_csv(
        RESULTS / "explicacion/estabilidad_submuestras_marco_macro_integral.csv",
        index=False,
        encoding="utf-8-sig",
    )
    stability_summary.to_csv(
        RESULTS / "explicacion/estabilidad_submuestras_resumen.csv",
        index=False,
        encoding="utf-8-sig",
    )
    comparison.to_csv(
        RESULTS / "explicacion/comparacion_especificaciones.csv", index=False, encoding="utf-8-sig"
    )
    regional_comparison.to_csv(
        RESULTS / "explicacion/comparacion_factor_regional.csv", index=False, encoding="utf-8-sig"
    )
    availability.to_csv(
        RESULTS / "pronostico/calendario_disponibilidad_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )
    lag_grid_forecast.to_csv(
        RESULTS / "pronostico/seleccion_rezagos_modelo_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )
    coefficients_forecast.to_csv(
        RESULTS / "pronostico/coeficientes_modelo_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )
    diagnostics_forecast.to_csv(
        RESULTS / "pronostico/diagnosticos_modelo_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )
    predictions_forecast.to_csv(
        RESULTS / "pronostico/validacion_predicciones_pronostico.csv", encoding="utf-8-sig"
    )
    validation_forecast.to_csv(
        RESULTS / "pronostico/validacion_metricas_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # ── Diebold-Mariano: pronóstico vs caminata aleatoria ────────────────────
    dm_result = diebold_mariano_test(predictions_forecast)
    dm_result.to_csv(
        RESULTS / "pronostico/diebold_mariano_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # ── Modelos parsimoniosos de pronóstico ──────────────────────────────────
    components = difference_components(model_data)
    parsimonious = parsimonious_forecasts(
        model_data, components, shapley_integrated, holdout=48
    )
    parsimonious.to_csv(
        RESULTS / "pronostico/comparacion_parsimoniosos_pronostico.csv",
        index=False,
        encoding="utf-8-sig",
    )

    lag_grid_ecm.to_csv(
        RESULTS / "robustez/seleccion_rezagos_ecm.csv", index=False, encoding="utf-8-sig"
    )
    tests.to_csv(RESULTS / "explicacion/pruebas_integracion.csv", index=False, encoding="utf-8-sig")
    short_run_ecm.to_csv(
        RESULTS / "robustez/coeficientes_corto_plazo_ecm.csv", index=False, encoding="utf-8-sig"
    )
    long_run_ecm.to_csv(
        RESULTS / "robustez/coeficientes_largo_plazo_ecm.csv", index=False, encoding="utf-8-sig"
    )
    bounds_summary.to_csv(RESULTS / "robustez/bounds_resumen.csv", index=False, encoding="utf-8-sig")
    bounds_critical.to_csv(RESULTS / "robustez/bounds_criticos.csv", index=False, encoding="utf-8-sig")
    diagnostics_ecm.to_csv(
        RESULTS / "robustez/diagnosticos_ecm.csv", index=False, encoding="utf-8-sig"
    )
    predictions.to_csv(RESULTS / "explicacion/validacion_predicciones_controles_externos.csv", encoding="utf-8-sig")
    validation.to_csv(RESULTS / "explicacion/validacion_metricas_controles_externos.csv", index=False, encoding="utf-8-sig")
    predictions_integrated.to_csv(
        RESULTS / "explicacion/validacion_predicciones_marco_macro_integral.csv", encoding="utf-8-sig"
    )
    validation_integrated.to_csv(
        RESULTS / "explicacion/validacion_metricas_marco_macro_integral.csv",
        index=False,
        encoding="utf-8-sig",
    )

    bei_level_test = tests.loc[
        (tests["variable"] == "diferencial_bei_5y_pp")
        & (tests["transformacion"] == "nivel")
    ].iloc[0]
    bounds_p_i0 = float(bounds.p_values.loc["lower"])
    bounds_p_i1 = float(bounds.p_values.loc["upper"])
    if bounds_p_i1 < 0.05:
        cointegration_5pct = "evidencia de cointegracion"
    elif bounds_p_i0 > 0.05:
        cointegration_5pct = "sin evidencia de cointegracion"
    else:
        cointegration_5pct = "no concluyente"

    vintage_coverage = pd.read_csv(RESULTS / "pronostico/cobertura_vintages_pronostico.csv")
    complete_vintage_factors = int(
        vintage_coverage["apto_backtest_genuino"].astype("string").str.lower().eq("true").sum()
    )
    bootstrap_widest = shapley_bootstrap.assign(
        ancho=lambda frame: frame["ic_95_superior_pct"] - frame["ic_95_inferior_pct"]
    ).sort_values("ancho", ascending=False).iloc[0]
    recent_stability = stability_summary.loc[
        stability_summary["submuestra"].eq("2020 en adelante")
    ].iloc[0]
    bei_best_bic = bei_model_comparison.sort_values("bic").iloc[0]
    bei_best_validation = bei_model_comparison.sort_values(
        "rmse_log_condicional"
    ).iloc[0]
    bei_aggregation_sample = data.loc[
        SAMPLE_START:SAMPLE_END,
        [
            "diferencial_bei_5y_pp",
            "diferencial_bei_5y_comun_pp",
            "diferencia_comun_menos_separada_pp",
            "dias_comunes",
        ],
    ].dropna()
    bei_adf_trend = bei_stationarity.loc[
        bei_stationarity["agregacion"].eq("Medias mensuales separadas")
        & bei_stationarity["transformacion"].eq("nivel")
        & bei_stationarity["prueba"].eq("ADF")
        & bei_stationarity["deterministico"].eq("constante_tendencia")
    ].iloc[0]
    bei_za_trend = bei_stationarity.loc[
        bei_stationarity["agregacion"].eq("Medias mensuales separadas")
        & bei_stationarity["transformacion"].eq("nivel")
        & bei_stationarity["prueba"].eq("Zivot-Andrews")
        & bei_stationarity["deterministico"].eq(
            "constante_tendencia_con_quiebre"
        )
    ].iloc[0]

    metadata = {
        "muestra_inicio": model_data.index.min().strftime("%Y-%m-%d"),
        "muestra_fin": model_data.index.max().strftime("%Y-%m-%d"),
        "observaciones": int(model_data.shape[0]),
        REFERENCE_MODEL_ID: f"{REFERENCE_MODEL_LABEL}: diferencias mensuales con temporización económica y errores HAC",
        "adl_p_cambio_trm": selected_diff.p,
        "temporizacion": "Términos de intercambio, dólar amplio y VIX contemporáneos; remesas, diferencial de tasas y déficit rezagados un mes",
        "adl_observaciones": int(selected_diff.result.nobs),
        "adl_aic": float(selected_diff.result.aic),
        "adl_bic": float(selected_diff.result.bic),
        "adl_r_cuadrado": float(selected_diff.result.rsquared),
        "adl_r_cuadrado_ajustado": float(selected_diff.result.rsquared_adj),
        INTEGRATED_MODEL_ID: f"{INTEGRATED_MODEL_LABEL}: contabilidad histórica mensual en primeras diferencias con 14 factores, cuatro monedas regionales y errores HAC",
        "marco_macro_integral_p_cambio_trm": selected_integrated.p,
        "marco_macro_integral_observaciones": int(selected_integrated.result.nobs),
        "marco_macro_integral_aic": float(selected_integrated.result.aic),
        "marco_macro_integral_bic": float(selected_integrated.result.bic),
        "marco_macro_integral_r_cuadrado": float(selected_integrated.result.rsquared),
        "marco_macro_integral_r_cuadrado_ajustado": float(
            selected_integrated.result.rsquared_adj
        ),
        "marco_macro_integral_temporizacion": "Términos de intercambio, dólar amplio, VIX, EMBIG Colombia, monedas regionales y condiciones financieras, commodities y actividad internacional contemporáneos; cambios de remesas, tasas, déficit, reservas, balanza, flujos de capital y diferencial BEI rezagados un mes",
        "pesos_metodo": "Shapley/LMG exacto del incremento del R2 sobre intercepto, dinamica de TRM y dummy de pandemia",
        "pesos_suma_pct": float(shapley_integrated["peso_entre_factores_pct"].sum()),
        "shapley_r2_base": float(shapley_integrated["r2_base"].iloc[0]),
        "shapley_r2_completo": float(shapley_integrated["r2_completo"].iloc[0]),
        "shapley_r2_incremental": float(
            shapley_integrated["r2_incremental"].iloc[0]
        ),
        "shapley_bootstrap_metodo": "Bootstrap circular de bloques mensuales; pesos de cada réplica aproximados con permutaciones antitéticas",
        "shapley_bootstrap_replicas": SHAPLEY_BOOTSTRAP_REPLICATIONS,
        "shapley_bootstrap_bloque_meses": SHAPLEY_BOOTSTRAP_BLOCK_MONTHS,
        "shapley_bootstrap_permutaciones": SHAPLEY_BOOTSTRAP_PERMUTATIONS,
        "shapley_bootstrap_semilla": SHAPLEY_BOOTSTRAP_SEED,
        "shapley_bootstrap_factor_intervalo_mas_ancho": str(bootstrap_widest["factor"]),
        "shapley_bootstrap_intervalo_mas_ancho_pp": float(bootstrap_widest["ancho"]),
        "estabilidad_submuestras_cortes": int(len(stability_summary)),
        "estabilidad_2020_spearman_rangos": float(
            recent_stability["correlacion_spearman_rangos_vs_completa"]
        ),
        "estabilidad_2020_factores_mismo_signo_de_14": int(
            recent_stability["factores_mismo_signo_de_14"]
        ),
        "factor_regional": "Especificación histórica activa: promedio de cambios log estandarizados de BRL, CLP, MXN y PEN por USD; comparación contra BRL, CLP y MXN; parámetros calibrados 2006-2019",
        "factor_regional_correlacion_3_4": regional_correlation,
        "pronostico_modelo": f"Modelo mensual de un paso con todos los factores rezagados conforme a un calendario conservador de disponibilidad al inicio del mes objetivo; composición regional seleccionada por BIC: {forecast_currencies}",
        "pronostico_factor_regional_monedas": forecast_currencies,
        "pronostico_advertencia_vintages": "El backtest respeta rezagos de publicación, pero usa la última versión disponible de las series. Es pseudo-tiempo-real hasta contar con vintages históricos archivados; no debe rotularse como backtest genuino en tiempo real.",
        "vintages_archivo_inicio": "2026-08-23",
        "vintages_origenes_alfred_recuperados": 0,
        "vintages_factores_completos_de_14": complete_vintage_factors,
        "backtest_genuino_disponible": complete_vintage_factors == len(FORECAST_FACTOR_SPECS_3),
        "pronostico_p_cambio_trm": selected_forecast.p,
        "pronostico_observaciones": int(selected_forecast.result.nobs),
        "pronostico_r_cuadrado": float(selected_forecast.result.rsquared),
        "pronostico_r_cuadrado_ajustado": float(selected_forecast.result.rsquared_adj),
        "pronostico_aic": float(selected_forecast.result.aic),
        "pronostico_bic": float(selected_forecast.result.bic),
        "pronostico_mape_pct": float(validation_forecast.iloc[0]["mape_pct"]),
        "pronostico_acierto_direccion_pct": float(
            validation_forecast.iloc[0]["acierto_direccion_pct"]
        ),
        "pronostico_r2_vs_caminata": out_of_sample_r2(
            predictions_forecast, "ln_trm_pronostico_publicacion"
        ),
        "terminos_intercambio": "BanRep serie 15360; índice encadenado mensual, base geométrica 2000=100",
        "riesgo_soberano": "EMBIG Colombia del BCRP; promedio mensual de puntos base y conversión a puntos porcentuales",
        "bei_colombia_5y": "Diferencia entre promedios mensuales separados de TES COP 5 años BanRep 15273 y TES UVR 5 años BanRep 15276",
        "bei_eeuu_5y": "Federal Reserve Board Gürkaynak-Sack-Wright BKEVEN05; compensación inflacionaria cero cupón a 5 años, capitalización continua, promedio mensual",
        "bei_advertencia": "El BEI es compensación inflacionaria y no una expectativa pura: incorpora primas de riesgo de inflación y diferencias de liquidez",
        "proxies_snapshot_fecha_descarga": "2026-08-23",
        "proxies_snapshot_sha256": {
            filename: sha256_file(RAW / filename)
            for filename in [
                "embig_colombia_diario_bcrp.json",
                "tes_5y_pesos_banrep.json",
                "tes_5y_uvr_banrep.json",
                "bei_5y_eeuu_diario_fed.csv",
                "pen_usd_mensual_bcrp.json",
            ]
        },
        "internal_snapshot_sha256": {
            filename: sha256_file(RAW / filename)
            for filename in [
                "ise_dane_9actividades_jun2026.xlsx",
                "ise_dane_12actividades_jun2026.xlsx",
                "ipi_dane_jun2026.xlsx",
                "ipp_dane_jul2026.xlsx",
                "geih_dane_jun2026.xlsx",
                "geih_dane_desestacionalizado_jun2026.xlsx",
                "ipc_colombia_banrep.json",
            ]
        },
        "diferencial_bei_5y_transformacion": "Modelo vigente: primera diferencia rezagada un mes y promedios mensuales separados; nivel, fechas comunes, tendencia y quiebre se reportan como robustez",
        "diferencial_bei_5y_advertencia_estacionariedad": "Las conclusiones cambian al permitir tendencia o quiebre; ninguna prueba aislada determina la transformación económica correcta",
        "diferencial_bei_5y_adf_p_nivel": float(bei_level_test["adf_p"]),
        "diferencial_bei_5y_kpss_p_nivel": float(bei_level_test["kpss_p"]),
        "diferencial_bei_5y_adf_p_nivel_con_tendencia": float(
            bei_adf_trend["p_valor"]
        ),
        "diferencial_bei_5y_za_p_nivel_con_tendencia_quiebre": float(
            bei_za_trend["p_valor"]
        ),
        "diferencial_bei_5y_quiebre_za": str(bei_za_trend["fecha_quiebre"]),
        "diferencial_bei_5y_correlacion_agregaciones": float(
            bei_aggregation_sample["diferencial_bei_5y_pp"].corr(
                bei_aggregation_sample["diferencial_bei_5y_comun_pp"]
            )
        ),
        "diferencial_bei_5y_diferencia_media_comun_menos_separada_pp": float(
            bei_aggregation_sample["diferencia_comun_menos_separada_pp"].mean()
        ),
        "diferencial_bei_5y_max_diferencia_abs_agregacion_pp": float(
            bei_aggregation_sample[
                "diferencia_comun_menos_separada_pp"
            ].abs().max()
        ),
        "diferencial_bei_5y_min_dias_comunes_mes": int(
            bei_aggregation_sample["dias_comunes"].min()
        ),
        "diferencial_bei_5y_mejor_bic_especificacion": str(
            bei_best_bic["especificacion"]
        ),
        "diferencial_bei_5y_mejor_validacion_especificacion": str(
            bei_best_validation["especificacion"]
        ),
        "flujos_capital": "Movimientos netos de capital de la balanza cambiaria, BanRep serie 16706",
        "validacion_controles_externos_mape_pct": float(base_validation_row["mape_pct"]),
        "validacion_marco_macro_integral_mape_pct": float(integrated_validation_row["mape_pct"]),
        "validacion_controles_externos_acierto_direccion_pct": float(
            base_validation_row["acierto_direccion_pct"]
        ),
        "validacion_marco_macro_integral_acierto_direccion_pct": float(
            integrated_validation_row["acierto_direccion_pct"]
        ),
        "ecm_p": selected_ecm.p,
        "ecm_q_comun": selected_ecm.q,
        "bounds_f": float(bounds.stat),
        "bounds_p_i0": bounds_p_i0,
        "bounds_p_i1": bounds_p_i1,
        "cointegracion_5pct": cointegration_5pct,
        "velocidad_ajuste": float(uecm_result.params.get("ln_trm.L1", np.nan)),
    }
    (RESULTS / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\nActualizando README.md con los valores del modelo...")
    update_readme_fragments(
        coefficients_diff=coefficients_diff,
        coefficients_integrated=coefficients_integrated,
        comparison=comparison,
        shapley_integrated=shapley_integrated,
        shapley_bootstrap=shapley_bootstrap,
        validation=validation,
        validation_integrated=validation_integrated,
        validation_forecast=validation_forecast,
        predictions_forecast=predictions_forecast,
    )

    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print("\nCoeficientes de controles externos en diferencias")
    print(coefficients_diff.to_string(index=False))
    print("\nDiagnósticos de controles externos")
    print(diagnostics_diff.to_string(index=False))
    print("\nValidación")
    print(validation.to_string(index=False))
    print("\nComparación de especificaciones")
    print(comparison.to_string(index=False))
    print("\nPesos explicativos Shapley del marco macroeconómico integral")
    print(
        shapley_integrated[
            ["factor", "grupo", "shapley_r2", "peso_entre_factores_pct"]
        ].to_string(index=False)
    )
    print("\nComparación del factor regional de tres y cuatro monedas")
    print(regional_comparison.to_string(index=False))
    print("\nValidación del pronóstico con rezagos de publicación")
    print(validation_forecast.to_string(index=False))
    print("\nECM exploratorio: coeficientes de largo plazo")
    print(long_run_ecm.to_string(index=False))


# ---------------------------------------------------------------------------
# Etiquetas legibles para los términos del modelo en las tablas del README.
# Cualquier término no listado aquí se muestra con su nombre técnico tal cual.
# ---------------------------------------------------------------------------
_TERM_LABELS: dict[str, str] = {
    "const": "Constante",
    "D.ln_terminos_intercambio.L0": "Δln términos de intercambio, mes actual",
    "D.ln_remesas_12m.L1": "Δln remesas 12 meses, rezago 1",
    "D.diferencial_tasas_pp.L1": "Δ diferencial de tasas, rezago 1",
    "D.deficit_fiscal_12m_pct_pib.L1": "Δ déficit fiscal 12 meses/PIB, rezago 1",
    "D.ln_dolar_amplio.L0": "Δln dólar amplio, mes actual",
    "D.ln_vix.L0": "Δln VIX, mes actual",
    "D.embig_colombia_pp.L0": "Δ EMBIG Colombia (pp), mes actual",
    "D.ln_reservas_netas_sin_flar.L1": "Δln reservas netas sin FLAR, rezago 1",
    "D.asinh_balanza_comercial.L1": "Δ asinh(balanza comercial), rezago 1",
    "D.asinh_flujos_capital.L1": "Δ asinh(flujos de capital), rezago 1",
    "D.diferencial_bei_5y_pp.L1": "Δ diferencial BEI 5 años (pp), rezago 1",
    "factor_monedas_regionales_4.L0": "Factor regional BRL+CLP+MXN+PEN, mes actual",
    "factor_monedas_regionales_3.L1": "Factor regional BRL+CLP+MXN, rezago 1",
    "dummy_pandemia_2020": "Pandemia marzo–mayo 2020",
}

# Lectura del coeficiente de la constante del controles externos y financieros (sin lectura
# económica distinta; se mantiene el texto de referencia).
_REFERENCE_READINGS: dict[str, str] = {
    "const": "No hay evidencia de una deriva mensual adicional.",
    "D.ln_terminos_intercambio.L0": (
        "Una mejora de 10% se asocia con una TRM cerca de {:.1f}% menor."
    ),
    "D.ln_remesas_12m.L1": (
        "Un aumento de 10% se asocia con una TRM cerca de {:.1f}% mayor; "
        "el signo contrario al canal simple de oferta de divisas aconseja cautela por endogeneidad."
    ),
    "D.diferencial_tasas_pp.L1": (
        "Un aumento de 1 punto porcentual en el cambio del diferencial "
        "se asocia con una TRM cerca de {:.2f}% menor."
    ),
    "D.deficit_fiscal_12m_pct_pib.L1": (
        "Un aumento de 1 punto porcentual se asocia con una TRM cerca de {:.2f}% mayor, "
        "pero la estimación no es precisa al 5%."
    ),
    "D.ln_dolar_amplio.L0": (
        "Un aumento de 1% del dólar global se asocia con una TRM cerca de {:.2f}% mayor."
    ),
    "D.ln_vix.L0": (
        "Un aumento de 10% del VIX se asocia con una TRM cerca de {:.2f}% mayor."
    ),
    "dummy_pandemia_2020": (
        "Se asocia con una TRM alrededor de {:.1f}% mayor, condicionado a los demás factores."
    ),
}


def diebold_mariano_test(
    predictions: pd.DataFrame,
    model_column: str = "ln_trm_pronostico_publicacion",
    benchmark_column: str = "ln_trm_caminata_aleatoria",
    observed_column: str = "ln_trm_observada",
    max_lag: int = 6,
) -> pd.DataFrame:
    """
    Test de Diebold-Mariano (1995) con errores HAC (Newey-West).

    H0: la capacidad predictiva del modelo y del benchmark son iguales.
    H1 (dos colas): son distintas.
    H1 (una cola): el modelo es mejor (loss menor).

    Usa loss cuadrática: L(e) = e².
    """
    e_model = predictions[model_column] - predictions[observed_column]
    e_bench = predictions[benchmark_column] - predictions[observed_column]
    d = e_bench ** 2 - e_model ** 2  # positivo si modelo es mejor

    n = len(d)
    d_bar = float(d.mean())

    # Varianza HAC Newey-West
    gamma_0 = float(((d - d_bar) ** 2).mean())
    gamma_sum = 0.0
    for lag in range(1, max_lag + 1):
        weight = 1.0 - lag / (max_lag + 1)  # Bartlett kernel
        gamma_k = float(((d.iloc[lag:].values - d_bar) * (d.iloc[:-lag].values - d_bar)).mean())
        gamma_sum += 2 * weight * gamma_k
    variance = (gamma_0 + gamma_sum) / n

    if variance <= 0:
        dm_stat = float("nan")
        p_two_sided = float("nan")
        p_one_sided = float("nan")
    else:
        dm_stat = d_bar / (variance ** 0.5)
        p_two_sided = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=n - 1)))
        # Una cola: H1 = modelo mejor (d_bar > 0 → dm_stat > 0)
        p_one_sided = float(1 - stats.t.cdf(dm_stat, df=n - 1))

    result = pd.DataFrame([
        {
            "test": "Diebold-Mariano",
            "loss": "cuadrática (MSE)",
            "kernel_hac": f"Bartlett ({max_lag} rezagos)",
            "observaciones": n,
            "loss_media_modelo": float((e_model ** 2).mean()),
            "loss_media_benchmark": float((e_bench ** 2).mean()),
            "diferencia_loss_media": d_bar,
            "estadistico_dm": dm_stat,
            "p_valor_dos_colas": p_two_sided,
            "p_valor_una_cola_modelo_mejor": p_one_sided,
            "modelo": model_column,
            "benchmark": benchmark_column,
        }
    ])
    return result


def parsimonious_forecasts(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
    shapley_integrated: pd.DataFrame,
    holdout: int = 48,
) -> pd.DataFrame:
    """
    Estima modelos de pronóstico parsimoniosos con los top-N factores por Shapley.

    Compara: top-3, top-5, top-7 y el marco macroeconómico integral completo (14 factores).
    Todos usan rezagos de publicación (FORECAST_FACTOR_SPECS).
    """
    from copy import deepcopy

    # Ranking de factores por peso Shapley
    ranked_factors = shapley_integrated.sort_values(
        "peso_entre_factores_pct", ascending=False
    )["factor"].tolist()

    forecast_common_index = make_timed_difference_design(
        components, p=3, factor_specs=FORECAST_FACTOR_SPECS_3
    )[0].index

    results_rows: list[dict[str, object]] = []
    for n_factors in [3, 5, 7, 14]:
        selected_names = set(ranked_factors[:n_factors])
        # Filtrar FORECAST_FACTOR_SPECS_3 a solo los factores seleccionados
        specs_subset = {
            name: spec for name, spec in FORECAST_FACTOR_SPECS_3.items()
            if name in selected_names
        }
        if not specs_subset:
            continue

        selected_model, _ = select_timed_difference_model(
            model_data, specs_subset, common_index=forecast_common_index
        )
        preds, metrics = difference_validation(
            model_data, selected_model, holdout=holdout
        )

        metric_row = metrics.loc[
            ~metrics["modelo"].str.contains("Caminata", case=False)
        ].iloc[0]

        # R² vs caminata
        e_model = preds["ln_trm_modelo_condicional"] - preds["ln_trm_observada"]
        e_bench = preds["ln_trm_caminata_aleatoria"] - preds["ln_trm_observada"]
        r2_vs_walk = 1.0 - float((e_model ** 2).sum()) / float((e_bench ** 2).sum())

        results_rows.append({
            "factores_top_n": n_factors,
            "factores": ", ".join(sorted(selected_names)),
            "parametros": int(selected_model.result.df_model) + 1,
            "r_cuadrado_ajustado": float(selected_model.result.rsquared_adj),
            "bic": float(selected_model.result.bic),
            "mape_pct": float(metric_row["mape_pct"]),
            "acierto_direccion_pct": float(metric_row["acierto_direccion_pct"]),
            "r2_vs_caminata": r2_vs_walk,
        })

    return pd.DataFrame(results_rows)


def _pval_str(p: float) -> str:
    """Formatea un p-valor como '<0,0001' o con 4 decimales, usando coma decimal."""
    if p < 0.0001:
        return "<0,0001"
    return f"{p:.4f}".replace(".", ",")


def _coef_str(c: float) -> str:
    """Formatea un coeficiente con 5 decimales y coma decimal, con signo −."""
    s = f"{abs(c):.5f}".replace(".", ",")
    return f"−{s}" if c < 0 else s


def _pct_str(v: float, decimals: int = 2) -> str:
    """Formatea un porcentaje con coma decimal."""
    return f"{v:.{decimals}f}".replace(".", ",") + "%"


def _replace_auto_block(text: str, tag: str, new_content: str) -> str:
    """Reemplaza el contenido entre marcadores <!-- AUTO:tag --> en el README."""
    open_marker = f"<!-- AUTO:{tag} -->\n"
    close_marker = f"<!-- /AUTO:{tag} -->"
    start = text.find(open_marker)
    if start < 0:
        raise ValueError(
            f"Marcador AUTO:{tag} no encontrado en el README. "
            f"Añade <!-- AUTO:{tag} --> ... <!-- /AUTO:{tag} --> manualmente."
        )
    end = text.find(close_marker, start + len(open_marker))
    if end < 0:
        raise ValueError(f"Cierre <!-- /AUTO:{tag} --> no encontrado en el README.")
    return text[:start + len(open_marker)] + new_content + "\n" + text[end:]


def update_readme_fragments(
    coefficients_diff: pd.DataFrame,
    coefficients_integrated: pd.DataFrame,
    comparison: pd.DataFrame,
    shapley_integrated: pd.DataFrame,
    shapley_bootstrap: pd.DataFrame,
    validation: pd.DataFrame,
    validation_integrated: pd.DataFrame,
    validation_forecast: pd.DataFrame,
    predictions_forecast: pd.DataFrame,
) -> None:
    """Sobreescribe los bloques AUTO del README raíz con los valores actuales."""
    readme_path = ROOT / "README.md"
    text = readme_path.read_text(encoding="utf-8")

    # ── 1. Coeficientes controles externos y financieros ─────────────────────────────────────
    base_row = validation.loc[validation["modelo"].ne("Caminata aleatoria")].iloc[0]
    mape_base = float(base_row["mape_pct"])
    acierto_base = float(base_row["acierto_direccion_pct"])
    r2_vs_walk_base = float(
        comparison.loc[comparison["modelo"].eq(REFERENCE_MODEL_LABEL), "r2_validacion_condicional_vs_caminata"].iloc[0]
    )

    rows_reference = [
        "| Término | Coeficiente | p-valor HAC | Lectura aproximada |",
        "|---|---:|---:|---|",
    ]
    for _, row in coefficients_diff.iterrows():
        term = str(row["termino"])
        coef = float(row["coeficiente"])
        pval = float(row["p_valor"])
        label = _TERM_LABELS.get(term, f"`{term}`")
        reading_tpl = _REFERENCE_READINGS.get(term, "")
        if reading_tpl and "{" in reading_tpl:
            # Magnitud del efecto: para log-log usamos abs(coef)*10; para otros abs(coef)*100
            if "10%" in reading_tpl:
                mag = abs(coef) * 10 * 100
            elif "1 punto porcentual" in reading_tpl and "diferencial" in reading_tpl:
                mag = abs(coef) * 100
            elif "1 punto porcentual" in reading_tpl:
                mag = abs(coef) * 100
            elif "1%" in reading_tpl:
                mag = abs(coef) * 100
            else:
                mag = abs(coef) * 100
            reading = reading_tpl.format(mag)
        else:
            reading = reading_tpl
        rows_reference.append(
            f"| {label} | {_coef_str(coef)} | {_pval_str(pval)} | {reading} |"
        )
    text = _replace_auto_block(text, "coeficientes_controles_externos", "\n".join(rows_reference))

    # ── 2. Métricas controles externos y financieros ─────────────────────────────────────────
    lines_metricas_base = [
        f"- MAPE condicional: **{_pct_str(mape_base)}**.",
        f"- Acierto de dirección: **{_pct_str(acierto_base)}**.",
        f"- R² condicional frente a caminata aleatoria: **{_pct_str(r2_vs_walk_base)}**.",
    ]
    text = _replace_auto_block(text, "metricas_controles_externos", "\n".join(lines_metricas_base))

    # ── 3. Coeficientes marco macroeconómico integral ──────────────────────────────────────
    rows_integrated = [
        "| Término | Coeficiente | p-valor |",
        "|---|---:|---:|",
    ]
    for _, row in coefficients_integrated.iterrows():
        term = str(row["termino"])
        coef = float(row["coeficiente"])
        pval = float(row["p_valor"])
        label = _TERM_LABELS.get(term, f"`{term}`")
        rows_integrated.append(f"| {label} | {_coef_str(coef)} | {_pval_str(pval)} |")
    text = _replace_auto_block(text, "coeficientes_marco_macro_integral", "\n".join(rows_integrated))

    # ── 4. Comparación de métricas entre especificaciones ─────────────────────
    base = comparison.loc[comparison["modelo"].eq(REFERENCE_MODEL_LABEL)].iloc[0]
    amp = comparison.loc[comparison["modelo"].eq(INTEGRATED_MODEL_LABEL)].iloc[0]
    r2_vs_walk_amp = float(amp["r2_validacion_condicional_vs_caminata"])
    rows_comp = [
        "| Métrica | Controles externos y financieros | Marco macroeconómico integral |",
        "|---|---:|---:|",
        f"| Observaciones efectivas | {int(base['observaciones'])} | {int(amp['observaciones'])} |",
        f"| R² | {_pct_str(base['r_cuadrado'] * 100)} | {_pct_str(amp['r_cuadrado'] * 100)} |",
        f"| R² ajustado | {_pct_str(base['r_cuadrado_ajustado'] * 100)} | {_pct_str(amp['r_cuadrado_ajustado'] * 100)} |",
        f"| MAPE, validación condicional de 48 meses | {_pct_str(base['mape_pct'])} | {_pct_str(amp['mape_pct'])} |",
        f"| Acierto de dirección | {_pct_str(base['acierto_direccion_pct'])} | {_pct_str(amp['acierto_direccion_pct'])} |",
        f"| R² condicional frente a caminata aleatoria | {_pct_str(base['r2_validacion_condicional_vs_caminata'] * 100)} | {_pct_str(r2_vs_walk_amp * 100)} |",
    ]
    text = _replace_auto_block(text, "comparacion_especificaciones", "\n".join(rows_comp))

    # ── 5. Pesos Shapley ─────────────────────────────────────────────────────
    shapley_sorted = shapley_integrated.sort_values(
        "peso_entre_factores_pct", ascending=False
    )
    rows_shapley = [
        f"| Factor | Peso entre los {len(shapley_integrated)} factores | Aporte al R² |",
        "|---|---:|---:|",
    ]
    for _, row in shapley_sorted.iterrows():
        peso = float(row["peso_entre_factores_pct"])
        aporte = float(row["aporte_r2_puntos_porcentuales"])
        rows_shapley.append(
            f"| {row['factor']} | {_pct_str(peso)} | "
            f"{aporte:.2f} p.p. |".replace(".", ",")
        )
    text = _replace_auto_block(text, "pesos_shapley", "\n".join(rows_shapley))

    # ── 6. Intervalos bootstrap de los 3 factores con mayor peso ────────────────
    top3 = shapley_bootstrap.nlargest(3, "peso_puntual_pct").reset_index(drop=True)
    partes = []
    for _, row in top3.iterrows():
        lo = f"{row['ic_95_inferior_pct']:.2f}".replace(".", ",")
        hi = f"{row['ic_95_superior_pct']:.2f}".replace(".", ",")
        partes.append(f"{row['factor']}, **{lo}%–{hi}%**")
    top3_str = "; ".join(partes)
    nreplicas = int(top3.iloc[0]["replicas_validas"])
    bloque = int(top3.iloc[0]["bloque_meses"])
    lines_bootstrap = [
        f"La incertidumbre se evalúa con {nreplicas} réplicas de un *bootstrap* circular de "
        f"bloques de {bloque} meses. Los intervalos percentiles del 95% de los tres factores "
        f"principales son: {top3_str}. Son intervalos de la asignación Shapley bajo remuestreo "
        "temporal, no intervalos de un efecto causal.",
    ]
    text = _replace_auto_block(text, "bootstrap_intervalos", "\n".join(lines_bootstrap))

    # ── 7. Métricas del pronóstico ────────────────────────────────────────────
    pronostico_row = validation_forecast.loc[
        validation_forecast["modelo"].ne("Caminata aleatoria")
    ].iloc[0]
    caminata_row = validation_forecast.loc[
        validation_forecast["modelo"].eq("Caminata aleatoria")
    ].iloc[0]
    mape_fc = float(pronostico_row["mape_pct"])
    acierto_fc = float(pronostico_row["acierto_direccion_pct"])
    mape_walk = float(caminata_row["mape_pct"])

    # Calcula R² vs caminata aleatoria directamente desde las predicciones
    fc_col = "ln_trm_pronostico_publicacion"
    if fc_col not in predictions_forecast.columns:
        fc_col = "ln_trm_modelo_condicional"
    model_err = predictions_forecast[fc_col] - predictions_forecast["ln_trm_observada"]
    bench_err = predictions_forecast["ln_trm_caminata_aleatoria"] - predictions_forecast["ln_trm_observada"]
    mse_model = float((model_err ** 2).mean())
    mse_bench = float((bench_err ** 2).mean())
    r2_fc = 1.0 - mse_model / mse_bench if mse_bench != 0 else float("nan")
    r2_fc_str = _pct_str(r2_fc * 100) if r2_fc >= 0 else f"−{_pct_str(abs(r2_fc) * 100)}"

    lines_fc = [
        f"La validación expansiva de 48 meses obtiene MAPE de **{_pct_str(mape_fc)}**, "
        f"acierto de dirección de **{_pct_str(acierto_fc, 2)}** y R² frente a la caminata "
        f"aleatoria de **{r2_fc_str}**. La caminata obtiene MAPE de **{_pct_str(mape_walk)}**. "
        "Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico "
        "y, con esta información, el benchmark simple sigue siendo superior.",
    ]
    text = _replace_auto_block(text, "metricas_pronostico", "\n".join(lines_fc))

    readme_path.write_text(text, encoding="utf-8")
    print("README.md actualizado con los valores del modelo.")


if __name__ == "__main__":
    main()
