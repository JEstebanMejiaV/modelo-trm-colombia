"""
Mejoras al modelo de explicación — parte 2.

6. Rezagos distribuidos (Almon/PDL) del dólar amplio
7. Intervención cambiaria BanRep (si la serie está disponible)
8. Estimación robusta (MM-estimator y LAD) para reducir influencia de outliers

Uso:
    python src/improve_explanation_2.py
"""
from __future__ import annotations

import json
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

import sys

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
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
    EXPANDED_FACTOR_SPECS_4,
    ECM_LEVEL_VARIABLES,
    LEVEL_COMPONENTS,
    SelectedDifferenceModel,
)


def load_model_data():
    data = build_dataset()
    model_columns = [
        "ln_trm", *ECM_LEVEL_VARIABLES, "ln_vix", "dln_vix",
        "embig_colombia_pp", "ln_reservas_netas_sin_flar",
        "asinh_balanza_comercial", "asinh_flujos_capital",
        *LEVEL_COMPONENTS, "dummy_pandemia_2020",
    ]
    expected_index = pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")
    model_data = data.reindex(expected_index)[model_columns].copy()
    model_data.index.name = "fecha"
    return model_data


# ─────────────────────────────────────────────────────────────────────────────
# 6. REZAGOS DISTRIBUIDOS (PDL/ALMON) DEL DÓLAR AMPLIO
# ─────────────────────────────────────────────────────────────────────────────


def model_pdl_dolar(model_data, components, common_index, selected_base):
    """
    Polynomial Distributed Lag del dólar amplio: L0, L1, L2, L3.
    En vez de un solo coeficiente contemporáneo, captura que el efecto
    del dólar global se transmite gradualmente a lo largo de 0-3 meses.
    """
    y = selected_base.y
    x = selected_base.x.copy()

    # Añadir rezagos 1, 2, 3 del dólar amplio (L0 ya está)
    dolar_diff = model_data["ln_dolar_amplio"].diff()
    for lag in [1, 2, 3]:
        col_name = f"D.ln_dolar_amplio.L{lag}"
        if col_name not in x.columns:
            lagged = dolar_diff.shift(lag).reindex(x.index)
            x[col_name] = lagged

    # Eliminar NaN del inicio
    valid = x.notna().all(axis=1) & y.notna()
    y_clean = y[valid]
    x_clean = x[valid]

    result = sm.OLS(y_clean, x_clean).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)

    # Suma de coeficientes del dólar (efecto total acumulado)
    dolar_terms = [c for c in coefs["termino"] if "dolar_amplio" in c]
    total_effect = coefs.loc[coefs["termino"].isin(dolar_terms), "coeficiente"].sum()

    selected_obj = SelectedDifferenceModel(p=0, q=0, result=result, y=y_clean, x=x_clean)
    preds, metrics = difference_validation(model_data, selected_obj, holdout=48)
    metric_row = metrics.loc[~metrics["modelo"].str.contains("Caminata")].iloc[0]

    diag = diagnostics(result)
    arch_p = float(diag.loc[diag["prueba"] == "ARCH-LM (12)", "p_valor"].iloc[0])

    return {
        "modelo": "PDL dolar (L0-L3)",
        "parametros": int(result.df_model) + 1,
        "r_cuadrado_ajustado": float(result.rsquared_adj),
        "bic": float(result.bic),
        "mape_pct": float(metric_row["mape_pct"]),
        "efecto_total_dolar": total_effect,
        "arch_lm_p": arch_p,
        "nota": f"Efecto acumulado dolar (L0+L1+L2+L3): {total_effect:.4f}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. INTERVENCIÓN CAMBIARIA BANREP
# ─────────────────────────────────────────────────────────────────────────────


def download_intervencion_banrep() -> pd.Series | None:
    """
    Intenta descargar una serie de intervención cambiaria del BanRep.
    La serie 16722 parece ser mensual del sector cambiario (~268 obs).
    """
    url = "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16722"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        if not data or not data[0].get("data"):
            return None
        item = data[0]
        obs = item["data"]
        dates = pd.to_datetime([o[0] for o in obs], unit="ms", utc=True).tz_convert(None)
        values = pd.to_numeric([o[1] for o in obs], errors="coerce")
        series = pd.Series(values, index=dates, name="intervencion_cambiaria")
        series.index = series.index.to_period("M").to_timestamp()
        series = series.groupby(level=0).sum()  # suma mensual
        return series
    except Exception as e:
        print(f"  No se pudo descargar intervencion: {e}")
        return None


def model_intervencion(model_data, components, common_index, selected_base):
    """Añade la serie de intervención cambiaria (si disponible) al modelo."""
    intervencion = download_intervencion_banrep()
    if intervencion is None:
        return {"modelo": "Con intervencion cambiaria", "nota": "Serie no disponible"}

    y = selected_base.y
    x = selected_base.x.copy()

    # Añadir cambio de intervención rezagado 1 mes
    interv_aligned = intervencion.reindex(model_data.index)
    interv_diff = interv_aligned.diff().shift(1)  # rezago 1
    # Normalizar a miles de millones
    interv_diff = interv_diff / 1000.0
    x["D.intervencion_cambiaria.L1"] = interv_diff.reindex(x.index)

    valid = x.notna().all(axis=1) & y.notna()
    y_clean = y[valid]
    x_clean = x[valid]

    if y_clean.empty or len(y_clean) < 50:
        return {"modelo": "Con intervencion cambiaria", "nota": "Muestra insuficiente tras alinear"}

    result = sm.OLS(y_clean, x_clean).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)

    interv_coef = coefs.loc[coefs["termino"] == "D.intervencion_cambiaria.L1"]
    coef_val = float(interv_coef["coeficiente"].iloc[0]) if len(interv_coef) > 0 else np.nan
    p_val = float(interv_coef["p_valor"].iloc[0]) if len(interv_coef) > 0 else np.nan

    diag = diagnostics(result)
    arch_p = float(diag.loc[diag["prueba"] == "ARCH-LM (12)", "p_valor"].iloc[0])

    return {
        "modelo": "Con intervencion cambiaria",
        "parametros": int(result.df_model) + 1,
        "r_cuadrado_ajustado": float(result.rsquared_adj),
        "bic": float(result.bic),
        "coef_intervencion": coef_val,
        "p_valor_intervencion": p_val,
        "arch_lm_p": arch_p,
        "nota": f"coef={coef_val:.5f}, p={p_val:.4f}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. ESTIMACIÓN ROBUSTA (MM-ESTIMATOR y LAD)
# ─────────────────────────────────────────────────────────────────────────────


def model_robust_estimation(model_data, components, common_index, selected_base):
    """
    Compara OLS con estimadores robustos:
    - RLM (M-estimator con Huber T)
    - Quantile regression (mediana = LAD)
    """
    y = selected_base.y
    x = selected_base.x

    results_rows = []

    # OLS estándar (referencia)
    ols_result = selected_base.result
    results_rows.append({
        "estimador": "OLS (referencia)",
        "r_cuadrado": float(ols_result.rsquared),
        "n_outliers_detectados": 0,
        "residuo_max_abs": float(np.abs(ols_result.resid).max()),
        "residuo_std": float(ols_result.resid.std()),
    })

    # RLM (M-estimator con Huber)
    rlm_result = sm.RLM(y, x, M=sm.robust.norms.HuberT()).fit()
    rlm_weights = rlm_result.weights
    n_downweighted = int((rlm_weights < 0.9).sum())
    results_rows.append({
        "estimador": "RLM Huber-T",
        "r_cuadrado": float(1 - np.sum(rlm_result.resid**2) / np.sum((y - y.mean())**2)),
        "n_outliers_detectados": n_downweighted,
        "residuo_max_abs": float(np.abs(rlm_result.resid).max()),
        "residuo_std": float(rlm_result.resid.std()),
    })

    # Quantile regression (mediana)
    quant_result = sm.QuantReg(y, x).fit(q=0.5)
    results_rows.append({
        "estimador": "LAD (mediana)",
        "r_cuadrado": float(1 - np.sum(quant_result.resid**2) / np.sum((y - y.mean())**2)),
        "n_outliers_detectados": 0,
        "residuo_max_abs": float(np.abs(quant_result.resid).max()),
        "residuo_std": float(quant_result.resid.std()),
    })

    # Comparar coeficientes clave entre los 3 estimadores
    key_terms = ["D.ln_dolar_amplio.L0", "factor_monedas_regionales_4.L0", "D.embig_colombia_pp.L0"]
    coef_comparison = []
    for term in key_terms:
        if term in x.columns:
            idx = list(x.columns).index(term)
            coef_comparison.append({
                "termino": term,
                "OLS": float(ols_result.params.iloc[idx]),
                "RLM_Huber": float(rlm_result.params.iloc[idx]),
                "LAD_mediana": float(quant_result.params.iloc[idx]),
                "ratio_RLM_vs_OLS": float(rlm_result.params.iloc[idx] / ols_result.params.iloc[idx]) if ols_result.params.iloc[idx] != 0 else np.nan,
            })

    # Identificar los meses downweighted por Huber
    downweighted_dates = y.index[rlm_weights < 0.9]
    outlier_info = pd.DataFrame({
        "fecha": downweighted_dates,
        "peso_huber": rlm_weights[rlm_weights < 0.9],
        "residuo_ols": ols_result.resid.loc[downweighted_dates].values,
    })

    return (
        pd.DataFrame(results_rows),
        pd.DataFrame(coef_comparison),
        outlier_info,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("MEJORAS AL MODELO DE EXPLICACIÓN — PARTE 2")
    print("=" * 70)

    print("\n[1/5] Cargando datos...")
    model_data = load_model_data()
    components = difference_components(model_data)
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=EXPANDED_FACTOR_SPECS_4
    )[0].index

    selected_base, _ = select_timed_difference_model(
        model_data, EXPANDED_FACTOR_SPECS_4, common_index=common_index
    )

    output_dir = RESULTS / "robustez"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 6. PDL del dólar ─────────────────────────────────────────────────────
    print("\n[2/5] Rezagos distribuidos (PDL) del dólar amplio...")
    pdl = model_pdl_dolar(model_data, components, common_index, selected_base)
    print(f"  R² ajustado: {pdl.get('r_cuadrado_ajustado', 'N/A')}")
    print(f"  BIC: {pdl.get('bic', 'N/A')}")
    print(f"  {pdl.get('nota', '')}")

    # ── 7. Intervención cambiaria ────────────────────────────────────────────
    print("\n[3/5] Intervención cambiaria BanRep...")
    interv = model_intervencion(model_data, components, common_index, selected_base)
    print(f"  {interv.get('nota', 'No disponible')}")

    # ── 8. Estimación robusta ────────────────────────────────────────────────
    print("\n[4/5] Estimación robusta (OLS vs RLM Huber vs LAD)...")
    estimators, coef_comp, outliers = model_robust_estimation(
        model_data, components, common_index, selected_base
    )
    estimators.to_csv(output_dir / "comparacion_estimadores_robustos.csv", index=False, encoding="utf-8-sig")
    coef_comp.to_csv(output_dir / "coeficientes_robustos_vs_ols.csv", index=False, encoding="utf-8-sig")
    if not outliers.empty:
        outliers.to_csv(output_dir / "outliers_huber_identificados.csv", index=False, encoding="utf-8-sig")

    print("\n  Comparación de estimadores:")
    print(estimators.to_string(index=False))
    print(f"\n  Meses downweighted por Huber: {len(outliers)}")
    if not outliers.empty:
        print(f"  Fechas: {outliers['fecha'].dt.strftime('%Y-%m').tolist()}")

    print("\n  Comparación de coeficientes clave:")
    print(coef_comp.to_string(index=False))

    # ── Guardar resumen ──────────────────────────────────────────────────────
    print("\n[5/5] Guardando resumen...")
    summary = pd.DataFrame([
        pdl,
        interv,
        {"modelo": "OLS (referencia)", **{k: v for k, v in zip(estimators.columns, estimators.iloc[0])}},
    ])
    summary.to_csv(output_dir / "mejoras_explicacion_parte2.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("ARCHIVOS GENERADOS")
    print("=" * 70)
    print("  results/robustez/comparacion_estimadores_robustos.csv")
    print("  results/robustez/coeficientes_robustos_vs_ols.csv")
    print("  results/robustez/outliers_huber_identificados.csv")
    print("  results/robustez/mejoras_explicacion_parte2.csv")
    print("=" * 70)


if __name__ == "__main__":
    main()
