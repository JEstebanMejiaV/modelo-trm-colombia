"""
Factor de carry: diferencial de tasas ajustado por volatilidad.

El carry trade consiste en pedir prestado en moneda de tasa baja (USD)
e invertir en moneda de tasa alta (COP). El retorno esperado es:

  Carry = (tasa_col - tasa_us) - E[depreciación_COP]

Si el mercado es eficiente, el carry = 0 (UIP). Pero en la práctica:
- El carry tiende a ser positivo en promedio (forward premium puzzle)
- Cuando el carry es MUY alto, atrae capital → COP se aprecia → carry se cumple
- Cuando el carry se comprime, el flujo se revierte → COP se deprecia

La señal ajustada por volatilidad es el Sharpe ratio del carry:
  carry_sharpe = diferencial_tasas / vol_trm

Cuando carry_sharpe es extremo (alto o bajo), predice corrección.

Uso:
    python src/forecast_longterm/carry_factor.py
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

from estimate_model import build_dataset, SAMPLE_START

RESULTS = ROOT / "results" / "pronostico"


def build_carry_signals(data: pd.DataFrame) -> pd.DataFrame:
    """
    Construye señales de carry:
    1. Diferencial de tasas nominal (tasa_col - fed_funds)
    2. Diferencial de tasas real (nominal - diferencial BEI)
    3. Carry Sharpe = diferencial / vol_TRM_12m
    4. Z-score del carry (normalizado por historia)
    5. Carry momentum = cambio 6m del diferencial
    """
    df = data.loc[SAMPLE_START:].copy()
    signals = pd.DataFrame(index=df.index)

    # Diferencial nominal
    if "tasa_politica_colombia_pct" in df.columns and "fed_funds_eeuu_pct" in df.columns:
        signals["diferencial_nominal"] = df["tasa_politica_colombia_pct"] - df["fed_funds_eeuu_pct"]

    # Diferencial real (ajustado por compensación inflacionaria)
    if "diferencial_bei_5y_pp" in df.columns and "diferencial_nominal" in signals.columns:
        signals["diferencial_real"] = signals["diferencial_nominal"] - df.get("diferencial_bei_5y_pp", 0)

    # Volatilidad realizada de la TRM (rolling 12 meses, anualizada)
    if "trm_cop_usd" in df.columns:
        r_trm = np.log(df["trm_cop_usd"].where(df["trm_cop_usd"] > 0)).diff()
        signals["vol_trm_12m_anual"] = r_trm.rolling(12).std() * np.sqrt(12) * 100

    # Carry Sharpe = diferencial / vol
    if "diferencial_nominal" in signals.columns and "vol_trm_12m_anual" in signals.columns:
        signals["carry_sharpe"] = (
            signals["diferencial_nominal"] / signals["vol_trm_12m_anual"].clip(lower=1)
        )

    # Z-score del carry (rolling 60 meses)
    if "carry_sharpe" in signals.columns:
        mean_roll = signals["carry_sharpe"].rolling(60, min_periods=36).mean()
        std_roll = signals["carry_sharpe"].rolling(60, min_periods=36).std()
        signals["carry_zscore"] = (signals["carry_sharpe"] - mean_roll) / std_roll

    # Z-score del diferencial nominal
    if "diferencial_nominal" in signals.columns:
        mean_d = signals["diferencial_nominal"].rolling(60, min_periods=36).mean()
        std_d = signals["diferencial_nominal"].rolling(60, min_periods=36).std()
        signals["diferencial_zscore"] = (signals["diferencial_nominal"] - mean_d) / std_d

    # Carry momentum: cambio del diferencial en 6 meses
    if "diferencial_nominal" in signals.columns:
        signals["carry_momentum_6m"] = signals["diferencial_nominal"] - signals["diferencial_nominal"].shift(6)

    # Carry relativo a EMBIG (carry neto de riesgo)
    if "diferencial_nominal" in signals.columns and "embig_colombia_pp" in df.columns:
        signals["carry_neto_embig"] = signals["diferencial_nominal"] - df["embig_colombia_pp"]

    return signals.dropna(how="all")


def evaluate_oos(signal: pd.Series, ln_trm: pd.Series, horizon: int, min_train: int = 60) -> dict:
    """Backtest OOS expanding."""
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat([signal.rename("s"), r_forward.rename("r")], axis=1, sort=True).dropna()

    if len(dataset) < min_train + 30:
        return {}

    fc_list, act_list = [], []
    for i in range(min_train, len(dataset)):
        train = dataset.iloc[:i]
        try:
            model = sm.OLS(train["r"], sm.add_constant(train["s"])).fit()
            fc_list.append(float(model.params.iloc[0] + model.params.iloc[1] * dataset["s"].iloc[i]))
            act_list.append(float(dataset["r"].iloc[i]))
        except Exception:
            continue

    if len(fc_list) < 30:
        return {}

    fc, act = np.array(fc_list), np.array(act_list)
    err = fc - act
    rw_err = -act
    mse_m, mse_rw = float((err**2).mean()), float((rw_err**2).mean())
    r2_oos = 1.0 - mse_m / mse_rw
    corr = float(np.corrcoef(fc, act)[0, 1])
    direction = float(np.mean(np.sign(fc) == np.sign(act)))
    d = rw_err**2 - err**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    return {
        "n_oos": len(fc_list),
        "r2_oos_pct": 100 * r2_oos,
        "correlacion": corr,
        "direccion_pct": 100 * direction,
        "dm_p_valor": dm_p,
    }


def main():
    print("=" * 70)
    print("FACTOR DE CARRY: DIFERENCIAL AJUSTADO POR VOLATILIDAD")
    print("=" * 70)

    print("\n[1/3] Construyendo señales de carry...")
    data = build_dataset()
    signals = build_carry_signals(data)
    ln_trm = np.log(data["trm_cop_usd"].loc[SAMPLE_START:].where(data["trm_cop_usd"] > 0)).dropna()

    print(f"  Señales: {list(signals.columns)}")
    print(f"\n  Estado actual:")
    last = signals.iloc[-1]
    for col in signals.columns:
        if pd.notna(last[col]):
            print(f"    {col:<25}: {last[col]:.3f}")

    print("\n[2/3] Evaluando OOS (h = 6, 12 meses)...")
    results = []
    for col in signals.columns:
        s = signals[col].dropna()
        if len(s) < 90:
            continue
        for h in [6, 12]:
            m = evaluate_oos(s, ln_trm, horizon=h)
            if m:
                m["senal"] = col
                m["horizonte"] = h
                results.append(m)

    if results:
        df_results = pd.DataFrame(results)
        # Mostrar solo h=12
        r12 = df_results[df_results["horizonte"] == 12].sort_values("r2_oos_pct", ascending=False)
        print(f"\n  Horizonte 12 meses:")
        for _, row in r12.iterrows():
            sig = "**" if row["dm_p_valor"] < 0.05 else "*" if row["dm_p_valor"] < 0.10 else ""
            print(f"    {row['senal']:<25} R2={row['r2_oos_pct']:>6.2f}%  corr={row['correlacion']:.3f}  dir={row['direccion_pct']:.1f}%  DM p={row['dm_p_valor']:.3f}{sig}")

        r6 = df_results[df_results["horizonte"] == 6].sort_values("r2_oos_pct", ascending=False)
        print(f"\n  Horizonte 6 meses:")
        for _, row in r6.head(5).iterrows():
            sig = "**" if row["dm_p_valor"] < 0.05 else "*" if row["dm_p_valor"] < 0.10 else ""
            print(f"    {row['senal']:<25} R2={row['r2_oos_pct']:>6.2f}%  corr={row['correlacion']:.3f}  dir={row['direccion_pct']:.1f}%  DM p={row['dm_p_valor']:.3f}{sig}")

    print("\n[3/3] Guardando...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    if results:
        pd.DataFrame(results).to_csv(RESULTS / "carry_factor_evaluacion.csv", index=False, encoding="utf-8-sig")
    signals.to_csv(RESULTS / "carry_factor_series.csv", encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("CONCLUSIÓN")
    print("=" * 70)
    if results:
        best = df_results[df_results["horizonte"] == 12].sort_values("r2_oos_pct", ascending=False).iloc[0]
        print(f"  Mejor señal de carry a 12m: {best['senal']}")
        print(f"  R² OOS: {best['r2_oos_pct']:.2f}%  |  DM p: {best['dm_p_valor']:.3f}")
        if best["dm_p_valor"] < 0.05:
            print("  ✓ El carry factor TIENE poder predictivo a 12 meses")
        elif best["r2_oos_pct"] > 0:
            print("  ~ Señal positiva pero no significativa al 5%")
        else:
            print("  ✗ El carry factor no supera la caminata")
    print("=" * 70)


if __name__ == "__main__":
    main()
