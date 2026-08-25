"""
Extensiones al análisis de largo plazo de la TRM.

1. Tendencias alternativas (promedio móvil 60 meses, tendencia lineal rolling)
2. Regime-switching Markov para β (velocidad de reversión varía por régimen)
3. Señales de momentum macro (ciclo Fed, petróleo/TI, EMBIG trend)

Uso:
    python src/forecast_longterm/extended_signals.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

from estimate_model import build_dataset, SAMPLE_START, SAMPLE_END

RESULTS = ROOT / "results" / "pronostico"


# ─────────────────────────────────────────────────────────────────────────────
# 1. TENDENCIAS ALTERNATIVAS (sin endpoint bias)
# ─────────────────────────────────────────────────────────────────────────────


def alternative_trends(data: pd.DataFrame) -> pd.DataFrame:
    """
    Construye desviaciones de la TRM usando tendencias que NO sufren
    endpoint bias (a diferencia del HP filter):
    - Promedio móvil de 60 meses (5 años)
    - Promedio móvil de 36 meses (3 años)
    - Tendencia lineal rolling de 60 meses
    """
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0))

    signals = pd.DataFrame(index=ln_trm.index)

    # MA 60 meses (5 años) — la más robusta, sin look-ahead
    ma60 = ln_trm.rolling(60, min_periods=48).mean()
    signals["desv_ma60_pct"] = 100 * (ln_trm - ma60)

    # MA 36 meses (3 años) — más reactiva
    ma36 = ln_trm.rolling(36, min_periods=24).mean()
    signals["desv_ma36_pct"] = 100 * (ln_trm - ma36)

    # Tendencia lineal rolling 60 meses (extrapolada)
    def rolling_linear_trend(series, window=60):
        trend = pd.Series(np.nan, index=series.index, dtype=float)
        clean = series.dropna()
        for i in range(window, len(clean)):
            y = clean.iloc[i - window:i].values
            x = np.arange(window)
            slope, intercept = np.polyfit(x, y, 1)
            # Extrapolar 1 paso: el valor actual de la tendencia
            trend.loc[clean.index[i - 1]] = intercept + slope * (window - 1)
        return trend

    trend_linear = rolling_linear_trend(ln_trm, window=60)
    signals["desv_trend_lineal_pct"] = 100 * (ln_trm - trend_linear)

    # Z-scores normalizados
    for col in ["desv_ma60_pct", "desv_ma36_pct", "desv_trend_lineal_pct"]:
        std = signals[col].rolling(60, min_periods=36).std()
        signals[f"z_{col}"] = signals[col] / std

    return signals.dropna(how="all")


# ─────────────────────────────────────────────────────────────────────────────
# 2. REGIME-SWITCHING MARKOV PARA β
# ─────────────────────────────────────────────────────────────────────────────


def markov_switching_beta(data: pd.DataFrame, horizon: int = 12) -> pd.DataFrame:
    """
    Estima un modelo de switching de Markov con 2 estados:
    - Estado 1: β bajo (reversión lenta o sin reversión)
    - Estado 2: β alto (reversión rápida)

    r_{t:t+h} = α_s + β_s × desviación_t + ε_t,  s ∈ {1, 2}
    """
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()

    # Usar MA 60 como tendencia (sin endpoint bias)
    ma60 = ln_trm.rolling(60, min_periods=48).mean()
    deviation = (ln_trm - ma60).dropna()

    # Retorno forward
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat(
        [deviation.rename("dev"), r_forward.rename("r_fwd")],
        axis=1,
        sort=False,
    ).dropna()

    if len(dataset) < 80:
        return pd.DataFrame()

    # Markov Switching Regression
    try:
        ms_model = sm.tsa.MarkovRegression(
            dataset["r_fwd"],
            k_regimes=2,
            exog=sm.add_constant(dataset["dev"]),
            switching_variance=True,
        )
        ms_result = ms_model.fit(disp=False, maxiter=200)
    except Exception as e:
        print(f"  Markov switching falló: {e}")
        return pd.DataFrame()

    # Extraer parámetros por régimen
    regimes = pd.DataFrame({
        "fecha": dataset.index,
        "desviacion": dataset["dev"].values,
        "r_forward": dataset["r_fwd"].values,
        "prob_regimen_1": ms_result.smoothed_marginal_probabilities[0],
        "prob_regimen_2": ms_result.smoothed_marginal_probabilities[1],
        "regimen_mas_probable": np.argmax(
            ms_result.smoothed_marginal_probabilities.to_numpy(), axis=1
        ),
    })

    # Parámetros por régimen
    params_info = pd.DataFrame([
        {
            "regimen": 0,
            "alpha": float(ms_result.params[f"const[{0}]"]) if f"const[{0}]" in ms_result.params.index else float(ms_result.params.iloc[0]),
            "beta": float(ms_result.params.iloc[1]) if len(ms_result.params) > 1 else np.nan,
            "sigma": float(ms_result.params.iloc[-2]) if len(ms_result.params) > 3 else np.nan,
        },
        {
            "regimen": 1,
            "alpha": float(ms_result.params.iloc[2]) if len(ms_result.params) > 2 else np.nan,
            "beta": float(ms_result.params.iloc[3]) if len(ms_result.params) > 3 else np.nan,
            "sigma": float(ms_result.params.iloc[-1]) if len(ms_result.params) > 4 else np.nan,
        },
    ])

    return regimes, params_info, ms_result


# ─────────────────────────────────────────────────────────────────────────────
# 3. SEÑALES DE MOMENTUM MACRO
# ─────────────────────────────────────────────────────────────────────────────


def macro_momentum_signals(data: pd.DataFrame) -> pd.DataFrame:
    """
    Señales basadas en tendencias macro sostenidas:
    - Ciclo de la Fed: dirección de los fed funds (subiendo vs bajando)
    - Momentum del petróleo/TI: cambio 12 meses de términos de intercambio
    - Tendencia del EMBIG: pendiente 6 meses del riesgo soberano
    - Diferencial de tasas en tendencia: cambio acumulado 6m
    """
    signals = pd.DataFrame(index=data.loc[SAMPLE_START:].index)

    # Ciclo Fed: cambio acumulado de fed_funds en 12 meses
    if "fed_funds_eeuu_pct" in data.columns:
        ff = data["fed_funds_eeuu_pct"].loc[SAMPLE_START:]
        signals["delta_fed_12m"] = ff - ff.shift(12)
        # Positivo = Fed subiendo = negativo para COP (capital sale de EM)

    # Momentum TI 12 meses
    if "terminos_intercambio" in data.columns:
        ti = data["terminos_intercambio"].loc[SAMPLE_START:]
        signals["momentum_ti_12m_pct"] = 100 * np.log(ti / ti.shift(12))
        # Positivo = TI mejorando = positivo para COP (aprecia)

    # Tendencia EMBIG: pendiente 6 meses (regresión lineal rolling)
    if "embig_colombia_pb" in data.columns:
        embig = data["embig_colombia_pb"].loc[SAMPLE_START:]
        signals["delta_embig_6m"] = embig - embig.shift(6)
        # Positivo = riesgo subiendo = negativo para COP

    # Diferencial de tasas acumulado 6m
    if "tasa_politica_colombia_pct" in data.columns and "fed_funds_eeuu_pct" in data.columns:
        diff = (data["tasa_politica_colombia_pct"] - data["fed_funds_eeuu_pct"]).loc[SAMPLE_START:]
        signals["delta_diferencial_6m"] = diff - diff.shift(6)
        # Positivo = Colombia sube más que Fed = atractivo para COP

    # Señales globales nuevas: tasas, commodities, riesgo y actividad.
    global_momentum = {
        "delta_yield_real_12m": "yield_real_10y_tips_pct",
        "delta_yield_2y_12m": "yield_2y_us_pct",
        "momentum_commodities_12m": "ln_commodities_global",
        "momentum_brent_12m": "ln_brent_global",
        "delta_epu_6m": "epu_global",
        "delta_actividad_us_12m": "ln_produccion_industrial_us",
    }
    for output, source in global_momentum.items():
        if source not in data.columns:
            continue
        series = data[source].loc[SAMPLE_START:]
        horizon = 6 if "epu" in output else 12
        signals[output] = series - series.shift(horizon)

    # Score macro compuesto (signos ajustados para predecir depreciación)
    score_cols = []
    if "delta_fed_12m" in signals.columns:
        # Fed subiendo → depreciación COP
        score_cols.append(signals["delta_fed_12m"] / signals["delta_fed_12m"].rolling(60, min_periods=24).std())
    if "momentum_ti_12m_pct" in signals.columns:
        # TI subiendo → apreciación COP (invertir)
        score_cols.append(-signals["momentum_ti_12m_pct"] / signals["momentum_ti_12m_pct"].rolling(60, min_periods=24).std())
    if "delta_embig_6m" in signals.columns:
        # EMBIG subiendo → depreciación COP
        score_cols.append(signals["delta_embig_6m"] / signals["delta_embig_6m"].rolling(60, min_periods=24).std())
    for col, sign in {
        "delta_yield_real_12m": +1,
        "delta_yield_2y_12m": +1,
        "momentum_commodities_12m": -1,
        "momentum_brent_12m": -1,
        "delta_epu_6m": +1,
        "delta_actividad_us_12m": -1,
    }.items():
        if col in signals.columns:
            scale = signals[col].rolling(60, min_periods=24).std()
            score_cols.append(sign * signals[col] / scale)
        signals["score_macro_momentum"] = pd.concat(score_cols, axis=1).mean(axis=1)

    return signals.dropna(how="all")


# ─────────────────────────────────────────────────────────────────────────────
# EVALUACIÓN
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_signal_oos(
    signal: pd.Series,
    ln_trm: pd.Series,
    horizon: int = 12,
    min_train: int = 60,
) -> dict:
    """
    Evaluación OOS expanding: estima β con datos hasta t, pronostica t+h.
    Usa la señal directamente (sin HP, sin look-ahead).
    """
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat(
        [signal.rename("signal"), r_forward.rename("r_fwd")],
        axis=1,
        sort=False,
    ).dropna()

    if len(dataset) < min_train + 30:
        return {"senal": signal.name, "horizonte": horizon, "error": "muestra insuficiente"}

    forecasts = []
    actuals = []
    for i in range(min_train, len(dataset)):
        train = dataset.iloc[:i]
        X = sm.add_constant(train["signal"])
        y = train["r_fwd"]
        try:
            model = sm.OLS(y, X).fit()
            signal_now = float(dataset["signal"].iloc[i])
            fc = float(model.params["const"] + model.params["signal"] * signal_now)
            actual = float(dataset["r_fwd"].iloc[i])
            forecasts.append(fc)
            actuals.append(actual)
        except Exception:
            continue

    if len(forecasts) < 30:
        return {"senal": signal.name, "horizonte": horizon, "error": "predicciones insuficientes"}

    forecasts = np.array(forecasts)
    actuals = np.array(actuals)
    errors = forecasts - actuals
    rw_errors = -actuals

    mse_m = float((errors**2).mean())
    mse_rw = float((rw_errors**2).mean())
    r2_oos = 1.0 - mse_m / mse_rw

    corr = float(np.corrcoef(forecasts, actuals)[0, 1])
    direction = float(np.mean(np.sign(forecasts) == np.sign(actuals)))

    d = rw_errors**2 - errors**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    return {
        "senal": signal.name,
        "horizonte": horizon,
        "n_oos": len(forecasts),
        "r2_oos_pct": 100 * r2_oos,
        "correlacion": corr,
        "direccion_pct": 100 * direction,
        "dm_p_valor": dm_p,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print("EXTENSIONES LARGO PLAZO: TENDENCIAS ALTERNATIVAS, MARKOV Y MOMENTUM")
    print("=" * 70)

    print("\n[1/4] Cargando datos...")
    data = build_dataset()
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()

    print("\n[2/4] Tendencias alternativas (MA 60m, MA 36m, lineal rolling)...")
    alt_signals = alternative_trends(data)
    print(f"  Señales: {list(alt_signals.columns)}")

    # Evaluar OOS cada señal a 12 meses
    results_alt = []
    for col in alt_signals.columns:
        s = alt_signals[col].dropna()
        if len(s) < 90:
            continue
        r = evaluate_signal_oos(s, ln_trm, horizon=12, min_train=60)
        results_alt.append(r)
        if "r2_oos_pct" in r:
            sig = "**" if r["dm_p_valor"] < 0.05 else "*" if r["dm_p_valor"] < 0.10 else ""
            print(f"  {col:<30} R²OOS={r['r2_oos_pct']:>6.1f}%  corr={r['correlacion']:.3f}  dir={r['direccion_pct']:.1f}%  DM p={r['dm_p_valor']:.3f}{sig}")

    print("\n[3/4] Señales de momentum macro...")
    macro_signals = macro_momentum_signals(data)
    print(f"  Señales: {list(macro_signals.columns)}")

    results_macro = []
    for col in macro_signals.columns:
        s = macro_signals[col].dropna()
        if len(s) < 90:
            continue
        for h in [6, 12]:
            r = evaluate_signal_oos(s, ln_trm, horizon=h, min_train=60)
            results_macro.append(r)
            if "r2_oos_pct" in r:
                sig = "**" if r["dm_p_valor"] < 0.05 else "*" if r["dm_p_valor"] < 0.10 else ""
                print(f"  {col:<30} h={h:>2}m  R²OOS={r['r2_oos_pct']:>6.1f}%  corr={r['correlacion']:.3f}  DM p={r['dm_p_valor']:.3f}{sig}")

    print("\n[4/4] Markov switching (2 regímenes de reversión)...")
    try:
        regimes, params, ms_result = markov_switching_beta(data, horizon=12)
        print(f"  Parámetros por régimen:")
        print(params.to_string(index=False))
        print(f"\n  Proporción en cada régimen:")
        print(f"    Régimen 0: {regimes['regimen_mas_probable'].eq(0).mean()*100:.1f}% del tiempo")
        print(f"    Régimen 1: {regimes['regimen_mas_probable'].eq(1).mean()*100:.1f}% del tiempo")
        regimes.to_csv(RESULTS / "markov_regimes_largo_plazo.csv", index=False, encoding="utf-8-sig")
        params.to_csv(RESULTS / "markov_parametros_largo_plazo.csv", index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"  Error Markov: {e}")

    # Guardar resultados
    print("\n  Guardando...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    all_results = [r for r in results_alt + results_macro if "r2_oos_pct" in r]
    if all_results:
        comparison = pd.DataFrame(all_results).sort_values("r2_oos_pct", ascending=False)
        comparison.to_csv(RESULTS / "senales_extendidas_largo_plazo.csv", index=False, encoding="utf-8-sig")
        alt_signals.to_csv(RESULTS / "series_tendencias_alternativas.csv", encoding="utf-8-sig")
        macro_signals.to_csv(RESULTS / "series_momentum_macro.csv", encoding="utf-8-sig")

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN: MEJORES SEÑALES OUT-OF-SAMPLE A 12 MESES")
    print("=" * 70)
    if all_results:
        top = pd.DataFrame(all_results).sort_values("r2_oos_pct", ascending=False)
        top_12 = top[top["horizonte"] == 12].head(5)
        if not top_12.empty:
            print(top_12[["senal", "r2_oos_pct", "correlacion", "direccion_pct", "dm_p_valor"]].to_string(index=False))
            best = top_12.iloc[0]
            if best["dm_p_valor"] < 0.05:
                print(f"\n  ✓ {best['senal']} supera la caminata al 5% (R² OOS = {best['r2_oos_pct']:.1f}%)")
            elif best["correlacion"] > 0.3:
                print(f"\n  ~ {best['senal']} tiene señal direccional (corr = {best['correlacion']:.3f}) pero no es estadísticamente significativa")
            else:
                print(f"\n  ✗ Ninguna señal supera la caminata al 5%")
    print("=" * 70)


if __name__ == "__main__":
    main()
