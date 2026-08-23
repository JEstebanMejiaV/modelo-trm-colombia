"""
Diagnósticos avanzados del modelo de TRM.

5. Rolling window (120 meses): detectar inestabilidad de coeficientes.
6. Pronóstico multihorizonte (h=1,2,3,6): iterated vs direct.
7. No linealidades (threshold regression): ¿cambia el modelo en crisis?

Uso:
    python src/advanced_diagnostics.py

Requiere que estimate_model.py haya corrido previamente.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

import sys

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "src"))

from estimate_model import (
    build_dataset,
    difference_components,
    make_timed_difference_design,
    select_timed_difference_model,
    tidy_robust_ols,
    SAMPLE_START,
    SAMPLE_END,
    EXPANDED_FACTOR_SPECS_4,
    FORECAST_FACTOR_SPECS_3,
    SelectedDifferenceModel,
)


# ─────────────────────────────────────────────────────────────────────────────
# 5. ROLLING WINDOW — 120 MESES
# ─────────────────────────────────────────────────────────────────────────────


def rolling_window_estimation(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
    window: int = 120,
) -> pd.DataFrame:
    """
    Estima el modelo ampliado con ventana fija de 120 meses (10 años).
    Para cada posición final t, estima con [t-119, t] y guarda coeficientes.
    Detecta inestabilidad midiendo dispersión temporal de cada coeficiente.
    """
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=EXPANDED_FACTOR_SPECS_4
    )[0].index

    # Diseño completo para obtener y, x
    selected_full, _ = select_timed_difference_model(
        model_data, EXPANDED_FACTOR_SPECS_4, common_index=common_index
    )
    y_full = selected_full.y
    x_full = selected_full.x
    n = len(y_full)

    if n < window + 12:
        raise ValueError(f"Muestra ({n}) insuficiente para rolling window de {window}.")

    rows: list[dict] = []
    for end in range(window, n):
        start = end - window
        y_win = y_full.iloc[start:end]
        x_win = x_full.iloc[start:end]
        result = sm.OLS(y_win, x_win).fit()

        row = {
            "fecha_fin_ventana": y_full.index[end - 1],
            "observaciones": window,
            "r_cuadrado_ajustado": float(result.rsquared_adj),
        }
        for name, coef in zip(x_win.columns, result.params):
            row[f"coef_{name}"] = float(coef)
        rows.append(row)

    rolling = pd.DataFrame(rows)

    # Resumen de estabilidad por coeficiente
    coef_cols = [c for c in rolling.columns if c.startswith("coef_")]
    stability_rows: list[dict] = []
    for col in coef_cols:
        term = col.replace("coef_", "")
        values = rolling[col].dropna()
        # Test de cambio: comparar primera y segunda mitad
        mid = len(values) // 2
        first_half = values.iloc[:mid]
        second_half = values.iloc[mid:]
        tstat, pval = stats.ttest_ind(first_half, second_half, equal_var=False)

        # Cuántas veces cambia de signo
        signs = np.sign(values)
        sign_changes = int((signs.diff().abs() > 0).sum())

        stability_rows.append({
            "termino": term,
            "media": float(values.mean()),
            "std": float(values.std()),
            "coef_variacion": float(values.std() / abs(values.mean())) if values.mean() != 0 else np.nan,
            "min": float(values.min()),
            "max": float(values.max()),
            "cambios_signo": sign_changes,
            "t_stat_mitades": float(tstat),
            "p_valor_mitades": float(pval),
            "inestable_5pct": pval < 0.05,
        })

    stability = pd.DataFrame(stability_rows)
    return rolling, stability


# ─────────────────────────────────────────────────────────────────────────────
# 6. PRONÓSTICO MULTIHORIZONTE (h=1, 2, 3, 6)
# ─────────────────────────────────────────────────────────────────────────────


def multi_horizon_forecast(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
    horizons: list[int] = [1, 2, 3, 6],
    holdout: int = 48,
) -> pd.DataFrame:
    """
    Pronóstico direct para múltiples horizontes.

    Para h > 1, la variable dependiente es ln(TRM_{t+h}) - ln(TRM_t),
    y los regresores son los mismos del pronóstico parsimonioso (top-3)
    disponibles en t (con rezago h en vez de 1).

    Compara con la caminata aleatoria en cada horizonte.
    """
    # Top-3 factores
    top3_names = {"Monedas regionales", "Dólar amplio", "Riesgo soberano EMBIG Colombia"}

    results_rows: list[dict] = []

    for h in horizons:
        # Construir variable dependiente: cambio a h meses
        ln_trm = model_data["ln_trm"]
        y_h = (ln_trm.shift(-h) - ln_trm).dropna()
        y_h.name = f"cambio_log_{h}m"

        # Construir regresores: misma lógica pero sin shift adicional
        # (los factores ya están rezagados 1 mes en FORECAST_FACTOR_SPECS_3)
        specs_top3 = {
            name: spec for name, spec in FORECAST_FACTOR_SPECS_3.items()
            if name in top3_names
        }

        # Para horizonte h, necesitamos que la info esté disponible en t
        # Los specs ya tienen rezago ≥ 1, así que para h > 1 la info sigue
        # disponible en t (es del mes t-1 o anterior).
        y_design, x_design = make_timed_difference_design(
            components, p=0, factor_specs=specs_top3
        )

        # Alinear y_h con x_design
        common_idx = y_h.index.intersection(x_design.index)
        # Necesitamos que la observación y_h[t] = ln(TRM_{t+h}) - ln(TRM_t)
        # corresponda a regresores en t
        # Pero y_h ya está indexada por t (la fecha de "hoy"), shift(-h) se
        # calculó arriba, así que y_h[t] es el cambio de t a t+h.
        # Eliminamos los últimos h meses que no tienen target futuro.
        valid_dates = sorted(set(common_idx) & set(y_h.index))
        if not valid_dates:
            continue

        y_aligned = y_h.reindex(valid_dates).dropna()
        x_aligned = x_design.reindex(y_aligned.index).dropna()
        common = y_aligned.index.intersection(x_aligned.index)
        y_aligned = y_aligned.loc[common]
        x_aligned = x_aligned.loc[common]

        if len(y_aligned) < holdout + 20:
            continue

        # Validación expanding
        split = len(y_aligned) - holdout
        errors_model: list[float] = []
        errors_walk: list[float] = []
        direction_hits: list[bool] = []

        for i in range(split, len(y_aligned)):
            train_result = sm.OLS(
                y_aligned.iloc[:i], x_aligned.iloc[:i]
            ).fit()
            forecast = float(train_result.predict(x_aligned.iloc[[i]]).iloc[0])
            actual = float(y_aligned.iloc[i])
            # Caminata aleatoria para h meses: cambio = 0
            errors_model.append(forecast - actual)
            errors_walk.append(0.0 - actual)  # predicción de la caminata = sin cambio
            direction_hits.append(np.sign(forecast) == np.sign(actual))

        errors_model_arr = np.array(errors_model)
        errors_walk_arr = np.array(errors_walk)
        mse_model = float((errors_model_arr ** 2).mean())
        mse_walk = float((errors_walk_arr ** 2).mean())

        # MAPE en niveles de TRM
        # Para h meses: TRM_pred = TRM_t * exp(forecast), TRM_obs = TRM_t * exp(actual)
        # MAPE = mean(|exp(forecast) - exp(actual)| / exp(actual))
        mape = float(100 * np.mean(np.abs(
            np.exp(np.array([e + a for e, a in zip(errors_model, [float(y_aligned.iloc[i]) for i in range(split, len(y_aligned))])])) -
            np.exp(np.array([float(y_aligned.iloc[i]) for i in range(split, len(y_aligned))]))
        ) / np.exp(np.array([float(y_aligned.iloc[i]) for i in range(split, len(y_aligned))]))))

        # Simplificar MAPE
        actuals = np.array([float(y_aligned.iloc[i]) for i in range(split, len(y_aligned))])
        forecasts = np.array([float(train_result.predict(x_aligned.iloc[[i]]).iloc[0]) for i in range(split, len(y_aligned))])
        mape_simple = float(100 * np.mean(np.abs(forecasts - actuals) / np.maximum(np.abs(actuals), 1e-8)))

        results_rows.append({
            "horizonte_meses": h,
            "observaciones_validacion": holdout,
            "rmse_modelo_log": float(np.sqrt(mse_model)),
            "rmse_caminata_log": float(np.sqrt(mse_walk)),
            "r2_vs_caminata": 1.0 - mse_model / mse_walk if mse_walk > 0 else np.nan,
            "acierto_direccion_pct": 100 * float(np.mean(direction_hits)),
            "dm_stat": float(np.mean(errors_walk_arr**2 - errors_model_arr**2) / (np.std(errors_walk_arr**2 - errors_model_arr**2) / np.sqrt(len(errors_model_arr)))) if np.std(errors_walk_arr**2 - errors_model_arr**2) > 0 else np.nan,
        })

    return pd.DataFrame(results_rows)


# ─────────────────────────────────────────────────────────────────────────────
# 7. NO LINEALIDADES — THRESHOLD REGRESSION
# ─────────────────────────────────────────────────────────────────────────────


def threshold_regression(
    model_data: pd.DataFrame,
    components: pd.DataFrame,
) -> pd.DataFrame:
    """
    Threshold regression: ¿cambia la relación cuando el VIX está alto?

    Divide la muestra en dos regímenes:
    - Normal: VIX ≤ mediana
    - Estrés: VIX > mediana

    También prueba con dólar amplio y EMBIG como variables de umbral.
    Compara R² y coeficientes entre regímenes.
    """
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=EXPANDED_FACTOR_SPECS_4
    )[0].index
    selected, _ = select_timed_difference_model(
        model_data, EXPANDED_FACTOR_SPECS_4, common_index=common_index
    )
    y = selected.y
    x = selected.x

    # Variables de umbral
    threshold_vars = {
        "VIX (nivel)": model_data["ln_vix"].reindex(y.index),
        "Dólar amplio (cambio)": model_data["ln_dolar_amplio"].diff().reindex(y.index),
        "EMBIG Colombia (nivel)": model_data["embig_colombia_pp"].reindex(y.index),
    }

    results_rows: list[dict] = []

    for threshold_name, threshold_series in threshold_vars.items():
        # Mediana como umbral
        threshold_value = float(threshold_series.median())
        mask_low = threshold_series <= threshold_value
        mask_high = threshold_series > threshold_value

        # Estimar en cada régimen
        y_low, x_low = y.loc[mask_low], x.loc[mask_low]
        y_high, x_high = y.loc[mask_high], x.loc[mask_high]

        if len(y_low) < 30 or len(y_high) < 30:
            continue

        result_low = sm.OLS(y_low, x_low).fit()
        result_high = sm.OLS(y_high, x_high).fit()
        result_full = selected.result

        # Test de Chow: ¿es significativa la diferencia entre regímenes?
        rss_full = float(np.sum(result_full.resid ** 2))
        rss_low = float(np.sum(result_low.resid ** 2))
        rss_high = float(np.sum(result_high.resid ** 2))
        rss_restricted = rss_full
        rss_unrestricted = rss_low + rss_high
        k = x.shape[1]  # número de parámetros
        n = len(y)
        f_chow = ((rss_restricted - rss_unrestricted) / k) / (rss_unrestricted / (n - 2 * k))
        p_chow = float(1 - stats.f.cdf(f_chow, k, n - 2 * k))

        results_rows.append({
            "variable_umbral": threshold_name,
            "umbral_mediana": threshold_value,
            "n_regimen_bajo": len(y_low),
            "n_regimen_alto": len(y_high),
            "r2_ajust_completo": float(result_full.rsquared_adj),
            "r2_ajust_regimen_bajo": float(result_low.rsquared_adj),
            "r2_ajust_regimen_alto": float(result_high.rsquared_adj),
            "f_chow": float(f_chow),
            "p_chow": p_chow,
            "quiebre_significativo_5pct": p_chow < 0.05,
        })

        # Comparar coeficientes clave entre regímenes
        key_terms = [
            "D.ln_dolar_amplio.L0",
            "D.ln_vix.L0",
            "D.embig_colombia_pp.L0",
            "factor_monedas_regionales_4.L0",
        ]
        for term in key_terms:
            if term in x.columns:
                idx = list(x.columns).index(term)
                coef_low = float(result_low.params.iloc[idx])
                coef_high = float(result_high.params.iloc[idx])
                results_rows[-1][f"coef_{term}_bajo"] = coef_low
                results_rows[-1][f"coef_{term}_alto"] = coef_high
                results_rows[-1][f"ratio_{term}"] = coef_high / coef_low if coef_low != 0 else np.nan

    return pd.DataFrame(results_rows)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("DIAGNÓSTICOS AVANZADOS DEL MODELO TRM")
    print("=" * 70)

    print("\n[1/4] Cargando datos...")
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

    robustez_dir = RESULTS / "robustez"
    robustez_dir.mkdir(parents=True, exist_ok=True)
    pronostico_dir = RESULTS / "pronostico"
    pronostico_dir.mkdir(parents=True, exist_ok=True)

    # ── 5. Rolling window ────────────────────────────────────────────────────
    print("\n[2/4] Rolling window (120 meses)...")
    rolling_coefs, rolling_stability = rolling_window_estimation(
        model_data, components, window=120
    )
    rolling_coefs.to_csv(
        robustez_dir / "rolling_window_coeficientes.csv",
        index=False, encoding="utf-8-sig",
    )
    rolling_stability.to_csv(
        robustez_dir / "rolling_window_estabilidad.csv",
        index=False, encoding="utf-8-sig",
    )
    n_inestables = int(rolling_stability["inestable_5pct"].sum())
    print(f"  Ventanas estimadas: {len(rolling_coefs)}")
    print(f"  Coeficientes inestables (p<5%): {n_inestables}/{len(rolling_stability)}")
    if n_inestables > 0:
        inestables = rolling_stability.loc[rolling_stability["inestable_5pct"], "termino"].tolist()
        print(f"  Términos inestables: {inestables}")

    # ── 6. Pronóstico multihorizonte ─────────────────────────────────────────
    print("\n[3/4] Pronóstico multihorizonte (h=1,2,3,6)...")
    multi_h = multi_horizon_forecast(model_data, components, horizons=[1, 2, 3, 6])
    multi_h.to_csv(
        pronostico_dir / "pronostico_multihorizonte.csv",
        index=False, encoding="utf-8-sig",
    )
    print(multi_h[["horizonte_meses", "rmse_modelo_log", "r2_vs_caminata", "acierto_direccion_pct"]].to_string(index=False))

    # ── 7. Threshold regression ──────────────────────────────────────────────
    print("\n[4/4] Threshold regression (no linealidades)...")
    thresholds = threshold_regression(model_data, components)
    thresholds.to_csv(
        robustez_dir / "threshold_regression.csv",
        index=False, encoding="utf-8-sig",
    )
    for _, row in thresholds.iterrows():
        sig = "***" if row["p_chow"] < 0.01 else "**" if row["p_chow"] < 0.05 else "*" if row["p_chow"] < 0.10 else ""
        print(f"  {row['variable_umbral']}: F={row['f_chow']:.2f}, p={row['p_chow']:.4f} {sig}")

    # ── Resumen ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ARCHIVOS GENERADOS")
    print("=" * 70)
    print("  results/robustez/rolling_window_coeficientes.csv")
    print("  results/robustez/rolling_window_estabilidad.csv")
    print("  results/pronostico/pronostico_multihorizonte.csv")
    print("  results/robustez/threshold_regression.csv")
    print("=" * 70)


if __name__ == "__main__":
    main()
