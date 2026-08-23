"""
Explorar variables adicionales para el modelo de la TRM.

Descarga y evalúa tres candidatas:
1. MICH: expectativas de inflación EE.UU. a 1 año (Michigan Survey)
2. NFCI: condiciones financieras (Chicago Fed) — proxy de apetito por riesgo
3. T10Y2Y: pendiente de la curva de treasuries — señal de ciclo

Evalúa cada una como factor adicional al modelo ampliado de pronóstico
para determinar si aportan poder explicativo marginal.

Uso:
    python src/explore_new_variables.py
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

import sys

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
sys.path.insert(0, str(ROOT / "src"))

from estimate_model import (
    build_dataset,
    difference_components,
    make_timed_difference_design,
    select_timed_difference_model,
    difference_validation,
    tidy_robust_ols,
    SAMPLE_START,
    SAMPLE_END,
    FORECAST_FACTOR_SPECS_3,
    EXPANDED_FACTOR_SPECS_4,
    SelectedDifferenceModel,
)

API_KEY = "dd22ac6406a29199a86edafc2f267524"


def download_fred_monthly(series_id: str, output_name: str) -> pd.Series:
    """Descarga una serie de FRED y la lleva a mensual."""
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&observation_start=2003-01-01"
        f"&file_type=json&api_key={API_KEY}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "modelo-trm/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    rows = []
    for obs in data["observations"]:
        if obs["value"] == ".":
            continue
        rows.append({"fecha": pd.Timestamp(obs["date"]), "valor": float(obs["value"])})

    df = pd.DataFrame(rows).set_index("fecha")
    # Si es diaria/semanal, agregar a mensual
    if len(df) > 300:
        series = df["valor"].resample("MS").mean()
    else:
        series = df["valor"]
        series.index = series.index.to_period("M").to_timestamp()
        series = series.groupby(level=0).mean()
    series.name = output_name
    return series


def evaluate_candidate(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
    new_series: pd.Series,
    variable_name: str,
    use_diff: bool = True,
    lag: int = 1,
) -> dict:
    """
    Evalúa una variable candidata añadiéndola al pronóstico top-3.

    Construye un factor adicional con el rezago especificado y compara
    BIC, R² ajustado y MAPE contra el top-3 sin la variable.
    """
    # Añadir la serie al model_data
    model_data_ext = model_data.copy()
    aligned = new_series.reindex(model_data_ext.index)
    model_data_ext[variable_name] = aligned

    # Añadir al components la diferencia de la nueva variable
    components_ext = components.copy()
    if use_diff:
        diff_col = f"D.{variable_name}"
        components_ext[diff_col] = model_data_ext[variable_name].diff()
        component_name = diff_col
    else:
        components_ext[variable_name] = model_data_ext[variable_name]
        component_name = variable_name

    # Specs del top-3 + nuevo factor
    top3_names = {"Monedas regionales", "Dólar amplio", "Riesgo soberano EMBIG Colombia"}
    specs_top3 = {
        name: spec for name, spec in FORECAST_FACTOR_SPECS_3.items()
        if name in top3_names
    }
    specs_extended = {
        **specs_top3,
        variable_name: {
            "grupo": "Candidata",
            "terminos": [(component_name, lag)],
        },
    }

    # Diseño matricial directo usando components_ext
    # Top-3 solo
    y_base, x_base = make_timed_difference_design(
        components_ext, p=0, factor_specs=specs_top3
    )
    # Top-3 + candidata
    y_ext, x_ext = make_timed_difference_design(
        components_ext, p=0, factor_specs=specs_extended
    )

    # Usar índice común
    common_idx = y_ext.index
    y_base = y_base.reindex(common_idx).dropna()
    x_base = x_base.reindex(y_base.index)
    y_ext = y_ext.reindex(common_idx).dropna()
    x_ext = x_ext.reindex(y_ext.index)

    # Estimar ambos
    result_base = sm.OLS(y_base, x_base).fit()
    result_ext = sm.OLS(y_ext, x_ext).fit()
    _, coefs_ext = tidy_robust_ols(result_ext, maxlags=6)

    # Validación expanding para ambos
    holdout_val = min(48, len(y_base) // 4)
    selected_base_obj = SelectedDifferenceModel(p=0, q=0, result=result_base, y=y_base, x=x_base)
    selected_ext_obj = SelectedDifferenceModel(p=0, q=0, result=result_ext, y=y_ext, x=x_ext)
    preds_base, metrics_base = difference_validation(model_data_ext, selected_base_obj, holdout=holdout_val)
    preds_ext, metrics_ext = difference_validation(model_data_ext, selected_ext_obj, holdout=holdout_val)

    # Métricas
    metric_base = metrics_base.loc[~metrics_base["modelo"].str.contains("Caminata")].iloc[0]
    metric_ext = metrics_ext.loc[~metrics_ext["modelo"].str.contains("Caminata")].iloc[0]

    # R² vs caminata
    def r2_walk(preds):
        e_m = preds["ln_trm_modelo_condicional"] - preds["ln_trm_observada"]
        e_w = preds["ln_trm_caminata_aleatoria"] - preds["ln_trm_observada"]
        return 1.0 - float((e_m**2).sum()) / float((e_w**2).sum())

    # Coeficiente de la candidata
    term_name = f"{component_name}.L{lag}"
    coef_row = coefs_ext.loc[coefs_ext["termino"] == term_name]
    coef_val = float(coef_row["coeficiente"].iloc[0]) if len(coef_row) > 0 else np.nan
    pval = float(coef_row["p_valor"].iloc[0]) if len(coef_row) > 0 else np.nan

    return {
        "variable": variable_name,
        "transformacion": f"{'D.' if use_diff else ''}{variable_name}.L{lag}",
        "coeficiente": coef_val,
        "p_valor_hac": pval,
        "bic_top3_solo": float(result_base.bic),
        "bic_top3_mas_candidata": float(result_ext.bic),
        "mejora_bic": float(result_base.bic) - float(result_ext.bic),
        "r2_adj_top3": float(result_base.rsquared_adj),
        "r2_adj_extendido": float(result_ext.rsquared_adj),
        "mape_top3": float(metric_base["mape_pct"]),
        "mape_extendido": float(metric_ext["mape_pct"]),
        "r2_vs_walk_top3": r2_walk(preds_base),
        "r2_vs_walk_extendido": r2_walk(preds_ext),
        "observaciones": int(result_ext.nobs),
        "aporta_por_bic": float(result_ext.bic) < float(result_base.bic),
    }


def main() -> None:
    print("=" * 70)
    print("EXPLORACIÓN DE VARIABLES CANDIDATAS")
    print("=" * 70)

    # Cargar modelo base
    print("\n[1/4] Cargando datos del modelo...")
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
    expected_index = pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")
    model_data = data.reindex(expected_index)[model_columns].copy()
    model_data.index.name = "fecha"
    components = difference_components(model_data)

    # Descargar candidatas
    print("\n[2/4] Descargando series candidatas de FRED...")
    candidates = {}

    print("  Descargando MICH (expectativas inflación Michigan)...")
    candidates["expectativas_inflacion_eeuu"] = download_fred_monthly("MICH", "expectativas_inflacion_eeuu")
    time.sleep(0.6)

    print("  Descargando NFCI (condiciones financieras Chicago Fed)...")
    candidates["nfci"] = download_fred_monthly("NFCI", "nfci")
    time.sleep(0.6)

    print("  Descargando T10Y2Y (pendiente curva treasuries)...")
    candidates["pendiente_curva_eeuu"] = download_fred_monthly("T10Y2Y", "pendiente_curva_eeuu")
    time.sleep(0.6)

    print("  Descargando STLFSI4 (estrés financiero St. Louis Fed)...")
    candidates["estres_financiero"] = download_fred_monthly("STLFSI4", "estres_financiero")

    # Evaluar cada candidata
    print("\n[3/4] Evaluando poder explicativo marginal...")
    results: list[dict] = []

    for name, series in candidates.items():
        print(f"\n  Evaluando: {name}")
        # En niveles con rezago 1
        try:
            result = evaluate_candidate(
                model_data, components, series,
                variable_name=name,
                use_diff=True,
                lag=1,
            )
            results.append(result)
            sig = "***" if result["p_valor_hac"] < 0.01 else "**" if result["p_valor_hac"] < 0.05 else "*" if result["p_valor_hac"] < 0.10 else ""
            mejora = "MEJORA" if result["aporta_por_bic"] else "no mejora"
            print(f"    coef={result['coeficiente']:.5f}, p={result['p_valor_hac']:.4f}{sig}")
            print(f"    BIC: {result['bic_top3_solo']:.1f} -> {result['bic_top3_mas_candidata']:.1f} ({mejora})")
            print(f"    MAPE: {result['mape_top3']:.2f}% -> {result['mape_extendido']:.2f}%")
        except Exception as e:
            print(f"    ERROR: {e}")

    # Guardar resultados
    print("\n[4/4] Guardando resultados...")
    output_dir = RESULTS / "robustez"
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(results)
    comparison.to_csv(
        output_dir / "evaluacion_variables_candidatas.csv",
        index=False, encoding="utf-8-sig",
    )

    # Guardar las series descargadas para uso futuro
    raw_dir = RAW
    for name, series in candidates.items():
        series.to_csv(raw_dir / f"{name}_fred.csv", header=True)

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    if results:
        df = pd.DataFrame(results)
        print(df[["variable", "coeficiente", "p_valor_hac", "mejora_bic", "mape_extendido", "aporta_por_bic"]].to_string(index=False))
        mejoran = df.loc[df["aporta_por_bic"]]
        if not mejoran.empty:
            print(f"\n  Variables que mejoran el BIC: {mejoran['variable'].tolist()}")
        else:
            print("\n  Ninguna variable candidata mejora el BIC del top-3.")
    print("=" * 70)


if __name__ == "__main__":
    main()
