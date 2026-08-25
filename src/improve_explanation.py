"""
Mejoras al modelo de explicación histórica de la TRM.

1. Interacciones multiplicativas (dólar×VIX, EMBIG×regionales)
2. Efectos asimétricos NARDL (separar Δ+ y Δ- del dólar amplio)
3. Factores principales PCA (reducir multicolinealidad)
4. Dummies de outliers (2008-10, 2015-02, 2020-03)

Compara cada extensión contra el marco macroeconómico integral actual usando:
- R² ajustado, BIC, MAPE condicional
- Proporción de coeficientes significativos
- Diagnósticos residuales

Uso:
    python src/improve_explanation.py
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
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
    INTEGRATED_FACTOR_SPECS_4,
    SelectedDifferenceModel,
)


def load_model_data():
    """Carga y prepara model_data como lo hace estimate_model.py."""
    from estimate_model import ECM_LEVEL_VARIABLES, LEVEL_COMPONENTS

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


def baseline_model(model_data, components, common_index):
    """Especificación integral actual como referencia."""
    selected, _ = select_timed_difference_model(
        model_data, INTEGRATED_FACTOR_SPECS_4, common_index=common_index
    )
    _, coefs = tidy_robust_ols(selected.result, maxlags=6)
    preds, metrics = difference_validation(model_data, selected, holdout=48)
    diag = diagnostics(selected.result)
    return selected, coefs, preds, metrics, diag


def evaluate_model(name, result, model_data, y, x, coefs=None):
    """Evalúa un modelo alternativo con las mismas métricas."""
    selected_obj = SelectedDifferenceModel(p=0, q=0, result=result, y=y, x=x)
    preds, metrics = difference_validation(model_data, selected_obj, holdout=48)
    if coefs is None:
        _, coefs = tidy_robust_ols(result, maxlags=6)
    diag = diagnostics(result)

    metric_row = metrics.loc[~metrics["modelo"].str.contains("Caminata")].iloc[0]
    n_sig = int((coefs["p_valor"] < 0.05).sum())
    n_total = len(coefs)

    # R² vs caminata
    e_m = preds["ln_trm_modelo_condicional"] - preds["ln_trm_observada"]
    e_w = preds["ln_trm_caminata_aleatoria"] - preds["ln_trm_observada"]
    r2_walk = 1.0 - float((e_m**2).sum()) / float((e_w**2).sum())

    arch_p = float(diag.loc[diag["prueba"] == "ARCH-LM (12)", "p_valor"].iloc[0])
    jb_p = float(diag.loc[diag["prueba"] == "Jarque-Bera", "p_valor"].iloc[0])

    return {
        "modelo": name,
        "parametros": int(result.df_model) + 1,
        "r_cuadrado_ajustado": float(result.rsquared_adj),
        "bic": float(result.bic),
        "mape_pct": float(metric_row["mape_pct"]),
        "acierto_direccion_pct": float(metric_row["acierto_direccion_pct"]),
        "r2_vs_caminata": r2_walk,
        "coefs_significativos_5pct": f"{n_sig}/{n_total}",
        "arch_lm_p": arch_p,
        "jarque_bera_p": jb_p,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. INTERACCIONES MULTIPLICATIVAS
# ─────────────────────────────────────────────────────────────────────────────


def model_interactions(model_data, components, common_index, selected_base):
    """Añade dólar×VIX y EMBIG×regionales al marco macroeconómico integral."""
    y = selected_base.y
    x = selected_base.x.copy()

    # Interacciones (producto de los regresores ya en el diseño)
    if "D.ln_dolar_amplio.L0" in x.columns and "D.ln_vix.L0" in x.columns:
        x["dolar_x_vix"] = x["D.ln_dolar_amplio.L0"] * x["D.ln_vix.L0"]
    if "D.embig_colombia_pp.L0" in x.columns and "factor_monedas_regionales_4.L0" in x.columns:
        x["embig_x_regionales"] = x["D.embig_colombia_pp.L0"] * x["factor_monedas_regionales_4.L0"]

    result = sm.OLS(y, x).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)
    return evaluate_model("Marco macroeconómico integral + interacciones", result, model_data, y, x, coefs)


# ─────────────────────────────────────────────────────────────────────────────
# 2. EFECTOS ASIMÉTRICOS (NARDL)
# ─────────────────────────────────────────────────────────────────────────────


def model_asymmetric(model_data, components, common_index, selected_base):
    """Separa Δ.dólar_amplio en componentes positivo y negativo."""
    y = selected_base.y
    x = selected_base.x.copy()

    dolar_col = "D.ln_dolar_amplio.L0"
    if dolar_col in x.columns:
        dolar = x[dolar_col]
        x["D.ln_dolar_amplio_pos.L0"] = dolar.clip(lower=0)
        x["D.ln_dolar_amplio_neg.L0"] = dolar.clip(upper=0)
        x = x.drop(columns=[dolar_col])

    result = sm.OLS(y, x).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)
    return evaluate_model("Marco macroeconómico integral + asimetria dolar", result, model_data, y, x, coefs)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FACTORES PRINCIPALES (PCA)
# ─────────────────────────────────────────────────────────────────────────────


def model_pca(model_data, components, common_index, selected_base):
    """Reemplaza los 12 factores individuales por componentes principales."""
    y = selected_base.y
    x_orig = selected_base.x.copy()

    # Columnas de factores (excluir const y dummy)
    factor_cols = [c for c in x_orig.columns if c not in ("const", "dummy_pandemia_2020")]
    X_factors = x_orig[factor_cols].values

    # Estandarizar y PCA
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_factors)
    pca = PCA(n_components=0.95)  # retener 95% de varianza
    X_pca = pca.fit_transform(X_scaled)
    n_components = X_pca.shape[1]

    # Nuevo diseño con PCA
    x_pca = pd.DataFrame(
        X_pca,
        index=x_orig.index,
        columns=[f"PC{i+1}" for i in range(n_components)],
    )
    x_pca["const"] = 1.0
    x_pca["dummy_pandemia_2020"] = x_orig["dummy_pandemia_2020"].values

    result = sm.OLS(y, x_pca).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)

    info = evaluate_model(
        f"PCA ({n_components} componentes, 95% varianza)",
        result, model_data, y, x_pca, coefs
    )
    info["varianza_explicada_pca"] = float(pca.explained_variance_ratio_.sum())
    info["n_componentes"] = n_components
    return info


# ─────────────────────────────────────────────────────────────────────────────
# 4. DUMMIES DE OUTLIERS
# ─────────────────────────────────────────────────────────────────────────────


def model_outlier_dummies(model_data, components, common_index, selected_base):
    """Añade dummies para los 3 meses con residuos más extremos."""
    y = selected_base.y
    x = selected_base.x.copy()
    resid = selected_base.result.resid

    # Identificar los 3 meses con residuos absolutos más grandes
    top_outliers = resid.abs().nlargest(5).index
    for date in top_outliers[:3]:
        col_name = f"dummy_{date.strftime('%Y_%m')}"
        x[col_name] = (x.index == date).astype(float)

    result = sm.OLS(y, x).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)
    outlier_dates = [d.strftime("%Y-%m") for d in top_outliers[:3]]
    info = evaluate_model("Marco macroeconómico integral + 3 dummies outlier", result, model_data, y, x, coefs)
    info["outliers_identificados"] = ", ".join(outlier_dates)
    return info


# ─────────────────────────────────────────────────────────────────────────────
# 5. COMBINACIÓN: interacciones + asimetría + outliers
# ─────────────────────────────────────────────────────────────────────────────


def model_combined(model_data, components, common_index, selected_base):
    """Mejor modelo combinado: interacciones + asimetría + outliers."""
    y = selected_base.y
    x = selected_base.x.copy()

    # Interacciones
    if "D.ln_dolar_amplio.L0" in x.columns and "D.ln_vix.L0" in x.columns:
        x["dolar_x_vix"] = x["D.ln_dolar_amplio.L0"] * x["D.ln_vix.L0"]
    if "D.embig_colombia_pp.L0" in x.columns and "factor_monedas_regionales_4.L0" in x.columns:
        x["embig_x_regionales"] = x["D.embig_colombia_pp.L0"] * x["factor_monedas_regionales_4.L0"]

    # Asimetría del dólar
    dolar_col = "D.ln_dolar_amplio.L0"
    if dolar_col in x.columns:
        dolar = x[dolar_col]
        x["D.ln_dolar_amplio_pos.L0"] = dolar.clip(lower=0)
        x["D.ln_dolar_amplio_neg.L0"] = dolar.clip(upper=0)
        x = x.drop(columns=[dolar_col])

    # Outliers
    resid_base = selected_base.result.resid
    top_outliers = resid_base.abs().nlargest(3).index
    for date in top_outliers:
        x[f"dummy_{date.strftime('%Y_%m')}"] = (x.index == date).astype(float)

    result = sm.OLS(y, x).fit()
    _, coefs = tidy_robust_ols(result, maxlags=6)
    return evaluate_model("Combinado (inter+asim+outliers)", result, model_data, y, x, coefs)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("MEJORAS AL MODELO DE EXPLICACIÓN HISTÓRICA")
    print("=" * 70)

    print("\n[1/6] Cargando datos...")
    model_data = load_model_data()
    components = difference_components(model_data)
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=INTEGRATED_FACTOR_SPECS_4
    )[0].index

    print("[2/6] Estimando la especificación integral de referencia...")
    selected_base, coefs_base, preds_base, metrics_base, diag_base = baseline_model(
        model_data, components, common_index
    )
    base_info = evaluate_model(
        "Marco macroeconómico integral actual (referencia)",
        selected_base.result, model_data, selected_base.y, selected_base.x
    )

    results = [base_info]

    print("[3/6] Modelo con interacciones multiplicativas...")
    results.append(model_interactions(model_data, components, common_index, selected_base))

    print("[4/6] Modelo con efectos asimétricos (NARDL dólar)...")
    results.append(model_asymmetric(model_data, components, common_index, selected_base))

    print("[5/6] Modelo con PCA...")
    try:
        results.append(model_pca(model_data, components, common_index, selected_base))
    except Exception as e:
        print(f"  ERROR PCA: {e}")

    print("[6/6] Modelo con dummies de outliers...")
    results.append(model_outlier_dummies(model_data, components, common_index, selected_base))

    # Modelo combinado
    print("  + Modelo combinado (interacciones + asimetría + outliers)...")
    results.append(model_combined(model_data, components, common_index, selected_base))

    # Guardar resultados
    comparison = pd.DataFrame(results)
    output = RESULTS / "robustez" / "comparacion_mejoras_explicacion.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output, index=False, encoding="utf-8-sig")

    # Mostrar resultados
    print("\n" + "=" * 70)
    print("COMPARACIÓN DE ESPECIFICACIONES")
    print("=" * 70)
    display_cols = ["modelo", "parametros", "r_cuadrado_ajustado", "bic", "mape_pct", "coefs_significativos_5pct", "arch_lm_p"]
    print(comparison[display_cols].to_string(index=False))

    # Resumen
    best_bic = comparison.loc[comparison["bic"].idxmin()]
    best_r2 = comparison.loc[comparison["r_cuadrado_ajustado"].idxmax()]
    best_mape = comparison.loc[comparison["mape_pct"].idxmin()]
    print(f"\n  Mejor BIC: {best_bic['modelo']} ({best_bic['bic']:.2f})")
    print(f"  Mejor R² ajustado: {best_r2['modelo']} ({best_r2['r_cuadrado_ajustado']*100:.2f}%)")
    print(f"  Mejor MAPE: {best_mape['modelo']} ({best_mape['mape_pct']:.2f}%)")

    print(f"\n  Guardado: {output.relative_to(ROOT)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
