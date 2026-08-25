"""
Señales de largo plazo para la TRM (6-24 meses).

A corto plazo la TRM es imprevisible (eficiencia débil).
A largo plazo hay dos fuerzas que generan señales explotables:

1. REVERSIÓN A LA MEDIA: cuando la TRM real está "cara" vs su tendencia
   de largo plazo, tiende a depreciarse menos (o apreciarse) en los
   siguientes 6-24 meses.

2. TENDENCIAS MACRO: ciclos de la Fed, precio del petróleo y déficit
   fiscal mueven la TRM persistentemente durante trimestres.

Definición de "largo plazo": 6 a 24 meses.

Metodologías:
- Desviación de la TRM real vs su tendencia HP (Hodrick-Prescott)
- Z-score del diferencial de tasas reales vs promedio histórico
- Ratio TRM nominal vs PPP implícita
- Momentum del petróleo/TI (retorno acumulado 12 meses)
- Score compuesto: combinación lineal de las señales anteriores

Uso:
    python src/forecast_daily/long_term_signals.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from estimate_model import build_dataset, SAMPLE_START, SAMPLE_END

RESULTS = ROOT / "results" / "pronostico"


# ─────────────────────────────────────────────────────────────────────────────
# SEÑALES
# ─────────────────────────────────────────────────────────────────────────────


def compute_signals(data: pd.DataFrame) -> pd.DataFrame:
    """Construye señales de largo plazo disponibles en cada mes t."""
    signals = pd.DataFrame(index=data.index)

    # --- 1. Desviación de TRM real vs tendencia HP ---
    # TRM real ≈ TRM nominal ajustada por IPC relativo
    # Como no tenemos IPC mensual directo, usamos TRM nominal vs HP trend
    ln_trm = np.log(data["trm_cop_usd"].where(data["trm_cop_usd"] > 0))
    # HP filter con lambda = 14400 (mensual estándar)
    cycle, trend = sm.tsa.filters.hpfilter(ln_trm.dropna(), lamb=14400)
    signals["desviacion_hp_pct"] = 100 * (ln_trm - trend.reindex(ln_trm.index))

    # Z-score de la desviación (normalizada por su std histórica rolling 60m)
    signals["zscore_hp"] = (
        signals["desviacion_hp_pct"]
        / signals["desviacion_hp_pct"].rolling(60, min_periods=36).std()
    )

    # --- 2. Diferencial de tasas reales ---
    # Tasa real Colombia ≈ tasa política - inflación implícita (BEI)
    # Diferencial real vs EE.UU. ≈ (política_col - BEI_col) - (fed_funds - BEI_eeuu)
    if "tasa_politica_colombia_pct" in data.columns and "fed_funds_eeuu_pct" in data.columns:
        bei_col = data.get("bei_colombia_5y_pct", pd.Series(dtype=float))
        bei_eeuu = data.get("bei_eeuu_5y_pct", pd.Series(dtype=float))
        tasa_real_col = data["tasa_politica_colombia_pct"] - bei_col.reindex(data.index)
        tasa_real_eeuu = data["fed_funds_eeuu_pct"] - bei_eeuu.reindex(data.index)
        diferencial_real = tasa_real_col - tasa_real_eeuu
        # Z-score del diferencial real
        signals["diferencial_tasas_reales"] = diferencial_real
        signals["zscore_diferencial_real"] = (
            (diferencial_real - diferencial_real.rolling(60, min_periods=36).mean())
            / diferencial_real.rolling(60, min_periods=36).std()
        )

    # --- 3. Momentum de términos de intercambio (12 meses) ---
    if "terminos_intercambio" in data.columns:
        ti = data["terminos_intercambio"]
        signals["momentum_ti_12m"] = np.log(ti / ti.shift(12)) * 100
        # TI altos → COP tiende a apreciarse en los próximos meses
        signals["zscore_ti"] = (
            (signals["momentum_ti_12m"] - signals["momentum_ti_12m"].rolling(60, min_periods=36).mean())
            / signals["momentum_ti_12m"].rolling(60, min_periods=36).std()
        )

    # --- 4. EMBIG relativo a su media histórica ---
    if "embig_colombia_pb" in data.columns:
        embig = data["embig_colombia_pb"]
        signals["embig_zscore"] = (
            (embig - embig.rolling(60, min_periods=36).mean())
            / embig.rolling(60, min_periods=36).std()
        )

    # --- 5. Posición del dólar amplio vs su tendencia ---
    if "indice_dolar_amplio" in data.columns:
        ln_dolar = np.log(data["indice_dolar_amplio"].where(data["indice_dolar_amplio"] > 0))
        cycle_d, trend_d = sm.tsa.filters.hpfilter(ln_dolar.dropna(), lamb=14400)
        signals["dolar_desviacion_hp_pct"] = 100 * (ln_dolar - trend_d.reindex(ln_dolar.index))

    # --- 7. Factores globales mensuales (rezagados implícitamente en evaluación) ---
    global_specs = {
        "yield_real_10y_tips_pct": ("z_global_yield_real", +1),
        "yield_2y_us_pct": ("z_global_yield_2y", +1),
        "spread_10y_2y_us_pct": ("z_global_spread_10y2y", +1),
        "epu_global": ("z_global_epu", +1),
        "estres_financiero_stl": ("z_global_stress", +1),
        "ln_brent_global": ("z_global_brent", -1),
        "ln_commodities_global": ("z_global_commodities", -1),
        "ln_empleo_manufactura_us": ("z_global_employment", -1),
        "ln_produccion_industrial_us": ("z_global_industry", -1),
    }
    global_parts = []
    for source, (output, sign) in global_specs.items():
        if source not in data.columns:
            continue
        series = data[source].loc[SAMPLE_START:]
        rolling_mean = series.rolling(60, min_periods=36).mean()
        rolling_std = series.rolling(60, min_periods=36).std()
        signals[output] = (series - rolling_mean) / rolling_std
        global_parts.append(sign * signals[output])
        signals[f"mom12_{output[2:]}"] = series.diff(12)
    if global_parts:
        signals["score_global"] = pd.concat(global_parts, axis=1).mean(axis=1)

    # Señal negativa = TRM está "cara" → esperar apreciación
    z_cols = [c for c in signals.columns if "zscore" in c]
    if z_cols:
        # Invertir zscore_hp y embig (alto = TRM cara = señal de apreciación futura)
        sign_map = {
            "zscore_hp": -1,         # TRM sobre tendencia → apreciará
            "zscore_diferencial_real": -1,  # Tasa real alta Col → apreciará (atrae capital)
            "zscore_ti": -1,          # TI altos → apreciará (ingreso exportaciones)
            "embig_zscore": +1,       # EMBIG alto → depreciará (salida capital)
        }
        composite_parts = []
        for col in z_cols:
            sign = sign_map.get(col, -1)
            composite_parts.append(sign * signals[col])
        signals["score_compuesto"] = pd.concat(composite_parts, axis=1).mean(axis=1)

    return signals.loc[SAMPLE_START:]


# ─────────────────────────────────────────────────────────────────────────────
# EVALUACIÓN: ¿la señal predice retornos futuros?
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_signal(
    signal: pd.Series,
    trm: pd.Series,
    horizons: list[int] = [6, 12, 18, 24],
) -> pd.DataFrame:
    """
    Evalúa si una señal en t predice el retorno acumulado de t a t+h.
    Usa regresión OLS: r_{t:t+h} = α + β·señal_t + ε
    β > 0 significa: señal alta predice retorno alto (depreciación).
    """
    ln_trm = np.log(trm.where(trm > 0))
    rows = []

    for h in horizons:
        # Retorno forward h meses
        r_forward = (ln_trm.shift(-h) - ln_trm) * 100  # en %
        combined = pd.concat([signal.rename("signal"), r_forward.rename("r_forward")], axis=1).dropna()

        if len(combined) < 60:
            continue

        X = sm.add_constant(combined["signal"])
        y = combined["r_forward"]
        result = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": h})

        beta = float(result.params["signal"])
        t_stat = float(result.tvalues["signal"])
        p_val = float(result.pvalues["signal"])
        r2 = float(result.rsquared)

        # Acierto de dirección: ¿señal positiva predice retorno positivo?
        direction = float((np.sign(combined["signal"]) == np.sign(combined["r_forward"])).mean())

        # Sharpe de la estrategia: ir largo TRM (comprar USD) si señal > 0
        strategy_returns = np.sign(combined["signal"].values) * combined["r_forward"].values
        sharpe = float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(12 / h)) if strategy_returns.std() > 0 else 0

        rows.append({
            "horizonte_meses": h,
            "observaciones": len(combined),
            "beta": beta,
            "t_stat_hac": t_stat,
            "p_valor_hac": p_val,
            "r2_pct": 100 * r2,
            "acierto_direccion_pct": 100 * direction,
            "sharpe_estrategia": sharpe,
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print("SEÑALES DE LARGO PLAZO PARA LA TRM (6-24 MESES)")
    print("=" * 70)
    print("\nDefinición de largo plazo: 6 a 24 meses")
    print("Hipótesis: a estos horizontes, los fundamentales dominan al ruido.\n")

    print("[1/3] Cargando datos y construyendo señales...")
    data = build_dataset()
    signals = compute_signals(data)
    trm = data["trm_cop_usd"].loc[signals.index]

    print(f"  Señales disponibles: {list(signals.columns)}")
    print(f"  Período: {signals.index.min().date()} a {signals.index.max().date()}")
    print(f"  Observaciones: {len(signals)}")

    print("\n[2/3] Evaluando poder predictivo de cada señal...")
    all_results = []
    signal_columns = [c for c in signals.columns if signals[c].notna().sum() > 60]

    for col in signal_columns:
        signal = signals[col].dropna()
        if len(signal) < 60:
            continue
        result = evaluate_signal(signal, trm, horizons=[6, 12, 18, 24])
        if not result.empty:
            result["senal"] = col
            all_results.append(result)

    if not all_results:
        print("  Sin señales evaluables.")
        return

    evaluation = pd.concat(all_results, ignore_index=True)

    # Mostrar por horizonte
    for h in [6, 12, 18, 24]:
        sub = evaluation[evaluation["horizonte_meses"] == h].sort_values("r2_pct", ascending=False)
        if sub.empty:
            continue
        print(f"\n  Horizonte: {h} meses")
        print(f"  {'Señal':<30} {'β':>8} {'t-HAC':>8} {'p-val':>8} {'R²%':>6} {'Dir%':>6} {'Sharpe':>7}")
        for _, row in sub.iterrows():
            sig = "***" if row["p_valor_hac"] < 0.01 else "**" if row["p_valor_hac"] < 0.05 else "*" if row["p_valor_hac"] < 0.10 else ""
            print(f"  {row['senal']:<30} {row['beta']:>8.3f} {row['t_stat_hac']:>8.2f} {row['p_valor_hac']:>8.3f} {row['r2_pct']:>6.1f} {row['acierto_direccion_pct']:>6.1f} {row['sharpe_estrategia']:>7.2f} {sig}")

    print("\n[3/3] Guardando resultados...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    evaluation.to_csv(RESULTS / "senales_largo_plazo.csv", index=False, encoding="utf-8-sig")
    signals.to_csv(RESULTS / "senales_largo_plazo_series.csv", encoding="utf-8-sig")

    # Resumen: mejores señales a 12 meses
    best_12m = evaluation[evaluation["horizonte_meses"] == 12].sort_values("p_valor_hac")
    print("\n" + "=" * 70)
    print("RESUMEN: MEJORES SEÑALES A 12 MESES")
    print("=" * 70)
    if not best_12m.empty:
        top = best_12m.iloc[0]
        print(f"  Mejor señal: {top['senal']}")
        print(f"  β = {top['beta']:.3f} (t-HAC = {top['t_stat_hac']:.2f}, p = {top['p_valor_hac']:.4f})")
        print(f"  R² = {top['r2_pct']:.1f}%")
        print(f"  Dirección: {top['acierto_direccion_pct']:.1f}%")
        print(f"  Sharpe: {top['sharpe_estrategia']:.2f}")
        if top["p_valor_hac"] < 0.05:
            print("\n  ✓ HAY señal significativa a largo plazo.")
        else:
            print("\n  ✗ Sin señal significativa a 12 meses.")
    print("=" * 70)


if __name__ == "__main__":
    main()
