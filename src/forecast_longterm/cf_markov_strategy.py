"""
Estrategia combinada: Christiano-Fitzgerald + Markov switching.

Idea:
- CF filter da la SEÑAL: cuánto está desviada la TRM de su tendencia.
- Markov da el TIMING: en qué régimen estamos (tranquilo vs turbulento).
- La estrategia solo actúa cuando CF dice "desviada" Y Markov dice "va a corregir".

Esto debería mejorar sobre usar CF solo (que tiene corr=0.51 pero DM p=0.69)
porque condiciona la apuesta al régimen correcto.

Uso:
    python src/forecast_longterm/cf_markov_strategy.py
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


def build_cf_markov_signals(data: pd.DataFrame) -> pd.DataFrame:
    """
    Construye el sistema combinado CF + Markov.

    1. Aplica CF filter a ln(TRM) para obtener tendencia y ciclo.
    2. La desviación (ciclo) es la señal de reversión.
    3. Estima Markov switching sobre la desviación para identificar regímenes.
    4. La señal final solo se activa en el régimen de "corrección inminente".
    """
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()

    # ── 1. Christiano-Fitzgerald filter ──────────────────────────────────────
    cf_cycle, cf_trend = sm.tsa.filters.cffilter(ln_trm, low=6, high=96)
    # Desviación en % (ciclo / señal de reversión)
    deviation_cf = cf_cycle * 100  # en puntos porcentuales de ln

    # ── 2. Markov switching sobre la desviación ──────────────────────────────
    # Modelo: desviación_t sigue un proceso con 2 regímenes de media y varianza
    # Régimen 0: desviación pequeña, baja vol (TRM cerca de equilibrio)
    # Régimen 1: desviación grande, alta vol (TRM lejos de equilibrio → corrección)
    dev_clean = deviation_cf.dropna()

    ms_model = sm.tsa.MarkovRegression(
        dev_clean.values,
        k_regimes=2,
        switching_variance=True,
    )
    ms_result = ms_model.fit(disp=False, maxiter=500)

    probs = ms_result.smoothed_marginal_probabilities  # (n_obs, 2)
    regimes = np.argmax(probs, axis=1)

    # Identificar cuál régimen es el de "desviación grande"
    mean_dev_0 = float(dev_clean.values[regimes == 0].mean()) if (regimes == 0).any() else 0
    mean_dev_1 = float(dev_clean.values[regimes == 1].mean()) if (regimes == 1).any() else 0
    vol_0 = float(dev_clean.values[regimes == 0].std()) if (regimes == 0).any() else 0
    vol_1 = float(dev_clean.values[regimes == 1].std()) if (regimes == 1).any() else 0

    # El régimen con mayor volatilidad es el "turbulento"
    if vol_1 > vol_0:
        regime_turbulent = 1
    else:
        regime_turbulent = 0

    # ── 3. Construir señales ─────────────────────────────────────────────────
    signals = pd.DataFrame(index=dev_clean.index)
    signals["desviacion_cf_pct"] = dev_clean.values
    signals["prob_turbulento"] = probs[:, regime_turbulent]
    signals["regimen"] = regimes
    signals["es_turbulento"] = (regimes == regime_turbulent).astype(float)

    # Señal combinada: desviación × probabilidad de estar en régimen turbulento
    # Cuando la TRM está desviada Y el mercado está en modo corrección
    signals["senal_cf_markov"] = signals["desviacion_cf_pct"] * signals["prob_turbulento"]

    # Señal pura CF (sin Markov, para comparar)
    signals["senal_cf_pura"] = signals["desviacion_cf_pct"]

    # Señal condicional: solo actuar si prob_turbulento > 0.5
    signals["senal_condicional"] = signals["desviacion_cf_pct"].where(
        signals["prob_turbulento"] > 0.5, other=0.0
    )

    return signals, {
        "regime_turbulent": regime_turbulent,
        "mean_dev_0": mean_dev_0,
        "mean_dev_1": mean_dev_1,
        "vol_0": vol_0,
        "vol_1": vol_1,
        "pct_turbulento": float((regimes == regime_turbulent).mean()) * 100,
    }


def backtest_signal(
    signal: pd.Series,
    ln_trm: pd.Series,
    horizon: int = 12,
    min_train: int = 60,
) -> dict:
    """Backtest OOS expanding."""
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat([
        signal.rename("signal"),
        r_forward.rename("r_fwd"),
    ], axis=1, sort=True).dropna()

    if len(dataset) < min_train + 30:
        return {"error": "insuficiente"}

    forecasts, actuals = [], []
    for i in range(min_train, len(dataset)):
        train = dataset.iloc[:i]
        X = sm.add_constant(train["signal"])
        y = train["r_fwd"]
        try:
            model = sm.OLS(y, X).fit()
            fc = float(model.params.iloc[0] + model.params.iloc[1] * dataset["signal"].iloc[i])
            forecasts.append(fc)
            actuals.append(float(dataset["r_fwd"].iloc[i]))
        except Exception:
            continue

    if len(forecasts) < 30:
        return {"error": "insuficiente"}

    fc = np.array(forecasts)
    act = np.array(actuals)
    err = fc - act
    rw_err = -act

    mse_m = float((err**2).mean())
    mse_rw = float((rw_err**2).mean())
    r2_oos = 1.0 - mse_m / mse_rw
    corr = float(np.corrcoef(fc, act)[0, 1])
    direction = float(np.mean(np.sign(fc) == np.sign(act)))

    # Strategy: comprar COP (vender USD) si señal es negativa (TRM sobre equilibrio)
    strategy = -np.sign(fc) * act
    sharpe = float(strategy.mean() / strategy.std() * np.sqrt(12 / horizon)) if strategy.std() > 0 else 0

    d = rw_err**2 - err**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    return {
        "n_oos": len(forecasts),
        "r2_oos_pct": 100 * r2_oos,
        "correlacion": corr,
        "direccion_pct": 100 * direction,
        "sharpe": sharpe,
        "dm_p_valor": dm_p,
    }


def main():
    print("=" * 70)
    print("ESTRATEGIA COMBINADA: CHRISTIANO-FITZGERALD + MARKOV SWITCHING")
    print("=" * 70)

    print("\n[1/3] Construyendo señales...")
    data = build_dataset()
    ln_trm = np.log(data["trm_cop_usd"].loc[SAMPLE_START:].where(data["trm_cop_usd"] > 0)).dropna()

    signals, regime_info = build_cf_markov_signals(data)
    print(f"  Observaciones: {len(signals)}")
    print(f"  Régimen turbulento: {regime_info['pct_turbulento']:.1f}% del tiempo")
    print(f"  Vol régimen 0: {regime_info['vol_0']:.2f}%  |  Vol régimen 1: {regime_info['vol_1']:.2f}%")
    print(f"  Media dev régimen 0: {regime_info['mean_dev_0']:.2f}%  |  Régimen 1: {regime_info['mean_dev_1']:.2f}%")

    print("\n[2/3] Backtest OOS a múltiples horizontes...")
    signal_names = ["senal_cf_pura", "senal_cf_markov", "senal_condicional"]
    all_results = []

    for horizon in [6, 12, 18]:
        print(f"\n  Horizonte: {horizon} meses")
        for name in signal_names:
            s = signals[name]
            result = backtest_signal(s, ln_trm, horizon=horizon, min_train=60)
            if "error" not in result:
                result["senal"] = name
                result["horizonte"] = horizon
                all_results.append(result)
                sig = "**" if result["dm_p_valor"] < 0.05 else "*" if result["dm_p_valor"] < 0.10 else ""
                print(f"    {name:<25} R²={result['r2_oos_pct']:>7.2f}%  corr={result['correlacion']:.3f}  dir={result['direccion_pct']:.1f}%  Sharpe={result['sharpe']:.2f}  DM p={result['dm_p_valor']:.3f}{sig}")

    print("\n[3/3] Guardando...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(all_results)
    comparison.to_csv(RESULTS / "cf_markov_estrategia.csv", index=False, encoding="utf-8-sig")
    signals.to_csv(RESULTS / "cf_markov_senales.csv", encoding="utf-8-sig")

    # Estado actual
    print("\n" + "=" * 70)
    print("SEÑAL ACTUAL (último mes disponible)")
    print("=" * 70)
    last = signals.iloc[-1]
    print(f"  Fecha: {signals.index[-1].strftime('%Y-%m')}")
    print(f"  Desviación CF: {last['desviacion_cf_pct']:.2f}%")
    print(f"  Prob. régimen turbulento: {last['prob_turbulento']:.1%}")
    print(f"  Señal combinada: {last['senal_cf_markov']:.2f}")
    if last["prob_turbulento"] > 0.5 and abs(last["desviacion_cf_pct"]) > 5:
        if last["desviacion_cf_pct"] > 0:
            print("  → TRM POR ENCIMA de equilibrio + régimen turbulento = PROBABLE APRECIACIÓN")
        else:
            print("  → TRM POR DEBAJO de equilibrio + régimen turbulento = PROBABLE DEPRECIACIÓN")
    else:
        print("  → Sin señal fuerte (régimen tranquilo o desviación pequeña)")

    print("\n" + "=" * 70)
    print("RESUMEN: ¿LA COMBINACIÓN MEJORA?")
    print("=" * 70)
    if all_results:
        comp_12 = comparison[comparison["horizonte"] == 12]
        if not comp_12.empty:
            for _, row in comp_12.iterrows():
                print(f"  {row['senal']:<25} R²OOS={row['r2_oos_pct']:>6.2f}%  dir={row['direccion_pct']:.1f}%  Sharpe={row['sharpe']:.2f}")
    print("=" * 70)


if __name__ == "__main__":
    main()
