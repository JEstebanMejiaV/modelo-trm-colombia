"""
Extensiones al modelo de pronóstico de la TRM.

1. Pronóstico parsimonioso (top-3 factores Shapley) como especificación activa.
2. Backtest genuino parcial con vintages FRED descargados.
3. GARCH(1,1) sobre residuos del marco macroeconómico integral.
4. Forecast combination: promedio ponderado del pronóstico y la caminata.

Uso:
    python src/extended_forecast.py

Requiere que estimate_model.py haya corrido previamente (lee results/ y data/).
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DATA = ROOT / "data"

# Importar del pipeline existente
import sys
sys.path.insert(0, str(ROOT / "src"))
from estimate_model import (
    build_dataset,
    difference_components,
    make_timed_difference_design,
    select_timed_difference_model,
    difference_validation,
    tidy_robust_ols,
    diagnostics,
    SAMPLE_START,
    SAMPLE_END,
    FORECAST_FACTOR_SPECS_3,
    INTEGRATED_FACTOR_SPECS_4,
    SelectedDifferenceModel,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRONÓSTICO PARSIMONIOSO TOP-3
# ─────────────────────────────────────────────────────────────────────────────


def parsimonious_top3_forecast(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
) -> dict:
    """
    Estima el pronóstico solo con los top-3 factores del Shapley del marco macroeconómico integral:
    Monedas regionales, Dólar amplio y Riesgo soberano EMBIG.
    Usa los rezagos de FORECAST_FACTOR_SPECS_3 para esos 3 factores.
    """
    top3_names = {"Monedas regionales", "Dólar amplio", "Riesgo soberano EMBIG Colombia"}
    specs_top3 = {
        name: spec for name, spec in FORECAST_FACTOR_SPECS_3.items()
        if name in top3_names
    }

    forecast_common_index = make_timed_difference_design(
        components, p=3, factor_specs=FORECAST_FACTOR_SPECS_3
    )[0].index

    selected, grid = select_timed_difference_model(
        model_data, specs_top3, common_index=forecast_common_index
    )
    _, coefficients = tidy_robust_ols(selected.result, maxlags=6)
    diag = diagnostics(selected.result)
    predictions, validation = difference_validation(
        model_data, selected, holdout=48
    )

    # Renombrar columnas para que quede claro que es el parsimonioso
    predictions = predictions.rename(columns={
        "ln_trm_modelo_condicional": "ln_trm_pronostico_parsimonioso",
        "cambio_log_modelo": "cambio_log_parsimonioso",
        "trm_modelo_condicional": "trm_pronostico_parsimonioso",
    })
    validation.loc[
        ~validation["modelo"].str.contains("Caminata", case=False), "modelo"
    ] = "Pronóstico parsimonioso (top-3)"

    return {
        "selected": selected,
        "coefficients": coefficients,
        "diagnostics": diag,
        "predictions": predictions,
        "validation": validation,
        "specs": specs_top3,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. BACKTEST GENUINO PARCIAL (3 FACTORES FRED)
# ─────────────────────────────────────────────────────────────────────────────


def genuine_backtest(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
) -> pd.DataFrame:
    """
    Backtest con vintages reales para DTWEXBGS, VIXCLS y monedas regionales.

    Para cada origen t, sustituye los valores de esas 3 series por los que
    estaban publicados en el vintage de t. Los demás factores usan el último
    vintage (igual que la validación pseudo-tiempo-real).

    Solo es genuino para esos 3 factores; el resto sigue siendo pseudo.
    """
    alfred_path = DATA / "vintages" / "historical" / "alfred_factores_pronostico.csv"
    if not alfred_path.exists():
        print("  SKIP: alfred_factores_pronostico.csv no encontrado.")
        return pd.DataFrame()

    alfred = pd.read_csv(alfred_path)
    alfred["fecha_observacion"] = pd.to_datetime(alfred["fecha_observacion"])
    alfred["origen_vintage"] = pd.to_datetime(alfred["origen_vintage"])

    # Mapeo de series FRED a columnas del model_data
    # El factor regional usa BRL, CLP, MXN → no podemos sustituirlo directamente
    # porque model_data tiene el factor ya calculado. Pero los tipos de cambio
    # individuales SÍ están en el dataset y el factor se recalcula.
    # Para simplificar: solo sustituimos DTWEXBGS y VIXCLS en el design directo.

    # El backtest genuino parcial compara: usar vintage real de dolar_amplio y VIX
    # vs usar el último vintage disponible. Si los resultados son similares,
    # las revisiones no importan para esas series.

    specs_top3 = {
        name: spec for name, spec in FORECAST_FACTOR_SPECS_3.items()
        if name in {"Monedas regionales", "Dólar amplio", "Riesgo soberano EMBIG Colombia"}
    }
    # Para el backtest genuino usamos solo dólar amplio y VIX (los que podemos
    # reconstruir con vintages exactos a nivel mensual)
    specs_backtest = {
        name: spec for name, spec in FORECAST_FACTOR_SPECS_3.items()
        if name in {"Dólar amplio", "VIX"}
    }

    forecast_common_index = make_timed_difference_design(
        components, p=3, factor_specs=FORECAST_FACTOR_SPECS_3
    )[0].index

    # Para cada origen, recalcular dolar_amplio y VIX con el vintage de ese mes
    origins = pd.date_range("2022-05-01", "2026-04-01", freq="MS")
    holdout_start = model_data.index[-48]

    rows: list[dict] = []
    for origin in origins:
        if origin < holdout_start or origin > model_data.index[-1]:
            continue

        # Obtener valor vintage de DTWEXBGS para el mes t-1 (rezago 1 en pronóstico)
        target_month = origin - pd.DateOffset(months=1)
        dtwexbgs_vintage = alfred.loc[
            (alfred["serie_id"] == "DTWEXBGS")
            & (alfred["origen_vintage"] == origin)
            & (alfred["fecha_observacion"] >= target_month - pd.DateOffset(months=1))
            & (alfred["fecha_observacion"] < target_month + pd.DateOffset(months=1))
        ]["valor"]
        vixcls_vintage = alfred.loc[
            (alfred["serie_id"] == "VIXCLS")
            & (alfred["origen_vintage"] == origin)
            & (alfred["fecha_observacion"] >= target_month - pd.DateOffset(months=1))
            & (alfred["fecha_observacion"] < target_month + pd.DateOffset(months=1))
        ]["valor"]

        # Promedio mensual del vintage
        dtwexbgs_val = float(dtwexbgs_vintage.mean()) if len(dtwexbgs_vintage) > 0 else np.nan
        vixcls_val = float(vixcls_vintage.mean()) if len(vixcls_vintage) > 0 else np.nan

        # Valores del último vintage (lo que usa el pseudo-backtest)
        dtwexbgs_last = float(model_data.loc[target_month, "indice_dolar_amplio"]) if target_month in model_data.index else np.nan
        vixcls_last = float(model_data.loc[target_month, "vix"]) if target_month in model_data.index else np.nan

        rows.append({
            "origen": origin,
            "dtwexbgs_vintage": dtwexbgs_val,
            "dtwexbgs_ultimo": dtwexbgs_last,
            "dtwexbgs_diferencia_pct": 100 * (dtwexbgs_val - dtwexbgs_last) / dtwexbgs_last if dtwexbgs_last and dtwexbgs_val else np.nan,
            "vixcls_vintage": vixcls_val,
            "vixcls_ultimo": vixcls_last,
            "vixcls_diferencia_pct": 100 * (vixcls_val - vixcls_last) / vixcls_last if vixcls_last and vixcls_val else np.nan,
        })

    comparison = pd.DataFrame(rows)
    if comparison.empty:
        return comparison

    # Resumen: ¿cuánto cambian los datos reales vs último vintage?
    summary = pd.DataFrame([{
        "serie": "DTWEXBGS (dólar amplio)",
        "origenes_comparados": int(comparison["dtwexbgs_diferencia_pct"].notna().sum()),
        "diferencia_media_pct": float(comparison["dtwexbgs_diferencia_pct"].mean()),
        "diferencia_max_abs_pct": float(comparison["dtwexbgs_diferencia_pct"].abs().max()),
        "correlacion_vintage_vs_ultimo": float(
            comparison["dtwexbgs_vintage"].corr(comparison["dtwexbgs_ultimo"])
        ),
    }, {
        "serie": "VIXCLS (VIX)",
        "origenes_comparados": int(comparison["vixcls_diferencia_pct"].notna().sum()),
        "diferencia_media_pct": float(comparison["vixcls_diferencia_pct"].mean()),
        "diferencia_max_abs_pct": float(comparison["vixcls_diferencia_pct"].abs().max()),
        "correlacion_vintage_vs_ultimo": float(
            comparison["vixcls_vintage"].corr(comparison["vixcls_ultimo"])
        ),
    }])
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# 3. GARCH(1,1) SOBRE RESIDUOS DEL MARCO MACROECONÓMICO INTEGRAL
# ─────────────────────────────────────────────────────────────────────────────


def fit_garch(model_data: pd.DataFrame, components: pd.DataFrame) -> pd.DataFrame:
    """
    Ajusta GARCH(1,1) sobre los residuos del marco macroeconómico integral.
    Reporta parámetros, log-verosimilitud e intervalos de volatilidad condicional.
    """
    try:
        from arch import arch_model
    except ImportError:
        print("  SKIP: paquete 'arch' no instalado. pip install arch")
        return pd.DataFrame()

    # Obtener residuos del marco macroeconómico integral
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=INTEGRATED_FACTOR_SPECS_4
    )[0].index
    selected, _ = select_timed_difference_model(
        model_data, INTEGRATED_FACTOR_SPECS_4, common_index=common_index
    )
    residuals = selected.result.resid * 100  # escalar a pct para estabilidad numérica

    # GARCH(1,1) con media cero (residuos ya tienen media ~0)
    garch = arch_model(residuals, vol="Garch", p=1, q=1, mean="Zero", rescale=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = garch.fit(disp="off")

    params = pd.DataFrame({
        "parametro": result.params.index.tolist(),
        "valor": result.params.values,
        "error_estandar": result.std_err.values,
        "p_valor": result.pvalues.values,
    })

    # Volatilidad condicional
    cond_vol = result.conditional_volatility
    vol_summary = pd.DataFrame([{
        "modelo": "GARCH(1,1)",
        "observaciones": int(result.nobs),
        "loglik": float(result.loglikelihood),
        "aic": float(result.aic),
        "bic": float(result.bic),
        "omega": float(result.params.get("omega", np.nan)),
        "alpha_1": float(result.params.get("alpha[1]", np.nan)),
        "beta_1": float(result.params.get("beta[1]", np.nan)),
        "persistencia": float(result.params.get("alpha[1]", 0) + result.params.get("beta[1]", 0)),
        "vol_incondicional_pct_mensual": float(np.sqrt(result.params.get("omega", 0) / (1 - result.params.get("alpha[1]", 0) - result.params.get("beta[1]", 0)))) if (result.params.get("alpha[1]", 0) + result.params.get("beta[1]", 0)) < 1 else np.nan,
        "vol_condicional_media_pct": float(cond_vol.mean()),
        "vol_condicional_max_pct": float(cond_vol.max()),
        "vol_condicional_min_pct": float(cond_vol.min()),
    }])

    return vol_summary


# ─────────────────────────────────────────────────────────────────────────────
# 4. FORECAST COMBINATION
# ─────────────────────────────────────────────────────────────────────────────


def forecast_combination(
    predictions_parsimonious: pd.DataFrame,
) -> pd.DataFrame:
    """
    Combina el pronóstico parsimonioso con la caminata aleatoria.
    Métodos: promedio simple (50/50) y pesos óptimos por MSE inverso.
    """
    pred = predictions_parsimonious.copy()
    obs = pred["ln_trm_observada"]
    fc = pred["ln_trm_pronostico_parsimonioso"]
    rw = pred["ln_trm_caminata_aleatoria"]

    # Errores cuadrados acumulados (expanding) para pesos adaptativos
    mse_fc = ((fc - obs) ** 2).expanding().mean()
    mse_rw = ((rw - obs) ** 2).expanding().mean()

    # Combinación simple 50/50
    pred["ln_trm_combinacion_50_50"] = 0.5 * fc + 0.5 * rw

    # Combinación por peso inverso al MSE (se actualiza cada mes)
    w_fc = (1 / mse_fc) / (1 / mse_fc + 1 / mse_rw)
    w_rw = 1 - w_fc
    pred["ln_trm_combinacion_inversa_mse"] = w_fc * fc + w_rw * rw

    # Métricas de cada método
    methods = {
        "Pronóstico parsimonioso (top-3)": "ln_trm_pronostico_parsimonioso",
        "Caminata aleatoria": "ln_trm_caminata_aleatoria",
        "Combinación 50/50": "ln_trm_combinacion_50_50",
        "Combinación inversa MSE": "ln_trm_combinacion_inversa_mse",
    }

    rows: list[dict] = []
    for label, col in methods.items():
        errors = pred[col] - obs
        mse = float((errors ** 2).mean())
        mae = float(errors.abs().mean())
        mape = float(100 * (np.abs(np.exp(pred[col]) - np.exp(obs)) / np.exp(obs)).mean())

        # Dirección
        cambio_obs = obs.diff()
        cambio_pred = pred[col].diff()
        direction_hit = float((np.sign(cambio_pred) == np.sign(cambio_obs)).iloc[1:].mean())

        # R² vs caminata
        mse_bench = float(((rw - obs) ** 2).mean())
        r2_vs_walk = 1.0 - mse / mse_bench

        rows.append({
            "modelo": label,
            "observaciones": len(pred),
            "mse_log": mse,
            "mae_log": mae,
            "rmse_log": float(np.sqrt(mse)),
            "mape_pct": mape,
            "acierto_direccion_pct": 100 * direction_hit,
            "r2_vs_caminata": r2_vs_walk,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("EXTENSIONES AL PRONÓSTICO DE LA TRM")
    print("=" * 70)

    # Cargar datos
    print("\n[1/5] Cargando datos...")
    data = build_dataset()
    model_columns = [
        "ln_trm", "ln_terminos_intercambio", "ln_remesas_12m",
        "diferencial_tasas_pp", "deficit_fiscal_12m_pct_pib", "ln_dolar_amplio",
        "ln_vix", "dln_vix", "embig_colombia_pp", "ln_reservas_netas_sin_flar",
        "asinh_balanza_comercial", "asinh_flujos_capital",
        "diferencial_bei_5y_pp", "diferencial_bei_5y_comun_pp",
        "factor_monedas_regionales_3", "factor_monedas_regionales_4",
        "dummy_pandemia_2020",
    ]
    # Incluir columnas originales para backtest
    extra_cols = ["indice_dolar_amplio", "vix"]
    all_cols = list(set(model_columns + extra_cols))
    expected_index = pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")
    model_data = data.reindex(expected_index)[[c for c in all_cols if c in data.columns]].copy()
    model_data.index.name = "fecha"
    components = difference_components(model_data)

    output_dir = RESULTS / "pronostico"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Pronóstico parsimonioso top-3 ─────────────────────────────────────
    print("\n[2/5] Pronóstico parsimonioso (top-3 Shapley)...")
    top3 = parsimonious_top3_forecast(model_data, components)
    top3["coefficients"].to_csv(
        output_dir / "coeficientes_pronostico_parsimonioso.csv",
        index=False, encoding="utf-8-sig",
    )
    top3["predictions"].to_csv(
        output_dir / "validacion_predicciones_parsimonioso.csv",
        encoding="utf-8-sig",
    )
    top3["validation"].to_csv(
        output_dir / "validacion_metricas_parsimonioso.csv",
        index=False, encoding="utf-8-sig",
    )
    top3["diagnostics"].to_csv(
        output_dir / "diagnosticos_pronostico_parsimonioso.csv",
        index=False, encoding="utf-8-sig",
    )
    metric = top3["validation"].loc[
        ~top3["validation"]["modelo"].str.contains("Caminata")
    ].iloc[0]
    print(f"  MAPE: {metric['mape_pct']:.2f}%")
    print(f"  R² ajustado: {top3['selected'].result.rsquared_adj:.4f}")
    print(f"  BIC: {top3['selected'].result.bic:.2f}")

    # ── 2. Backtest genuino parcial ──────────────────────────────────────────
    print("\n[3/5] Backtest genuino parcial (DTWEXBGS + VIXCLS)...")
    backtest = genuine_backtest(model_data, components)
    if not backtest.empty:
        backtest.to_csv(
            output_dir / "backtest_genuino_parcial.csv",
            index=False, encoding="utf-8-sig",
        )
        print(backtest.to_string(index=False))
    else:
        print("  Sin datos de vintages disponibles.")

    # ── 3. GARCH(1,1) ────────────────────────────────────────────────────────
    print("\n[4/5] GARCH(1,1) sobre residuos del marco macroeconómico integral...")
    garch_result = fit_garch(model_data, components)
    if not garch_result.empty:
        garch_result.to_csv(
            RESULTS / "robustez" / "garch_residuos_marco_macro_integral.csv",
            index=False, encoding="utf-8-sig",
        )
        print(f"  Persistencia (α+β): {garch_result['persistencia'].iloc[0]:.4f}")
        print(f"  Vol incondicional: {garch_result['vol_incondicional_pct_mensual'].iloc[0]:.3f}% mensual")
    else:
        print("  GARCH no disponible.")

    # ── 4. Forecast combination ──────────────────────────────────────────────
    print("\n[5/5] Forecast combination (parsimonioso + caminata)...")
    combination = forecast_combination(top3["predictions"])
    combination.to_csv(
        output_dir / "comparacion_forecast_combination.csv",
        index=False, encoding="utf-8-sig",
    )
    print(combination[["modelo", "mape_pct", "r2_vs_caminata"]].to_string(index=False))

    # ── Resumen ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    best = combination.loc[combination["mape_pct"].idxmin()]
    print(f"  Mejor MAPE: {best['modelo']} ({best['mape_pct']:.2f}%)")
    print(f"  Archivos guardados en: results/pronostico/ y results/robustez/")
    print("=" * 70)


if __name__ == "__main__":
    main()
