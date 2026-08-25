"""
Variables de la literatura académica para pronóstico de la TRM.

Descarga 6 series de FRED con respaldo en papers:
1. DFII10: US 10Y real yield (TIPS) — dollar smile
2. GOLDAMGBD228NLBM: Gold price — refugio/risk-off extremo
3. GEPUCURRENT: Global Economic Policy Uncertainty — incertidumbre
4. PALLFNFINDEXM: All Commodities Index — más amplio que TI Colombia
5. MANEMP: US Manufacturing Employment — ciclo real US
6. DGS2: US 2Y Treasury yield — expectativas de Fed forward

Evalúa cada una como señal de largo plazo (6-12 meses) y la combina
con el CF filter para ver si hay mejora incremental.

Uso:
    python src/forecast_longterm/academic_variables.py
"""
from __future__ import annotations

import json
import time
import urllib.request
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
API_KEY = "dd22ac6406a29199a86edafc2f267524"

SERIES_TO_DOWNLOAD = {
    "DFII10": "yield_real_10y_tips",
    "GOLDAMGBD228NLBM": "gold_usd",
    "GEPUCURRENT": "epu_global",
    "PALLFNFINDEXM": "commodities_index",
    "MANEMP": "us_manufacturing_emp",
    "DGS2": "yield_2y_us",
}


def download_fred_series(series_id: str, name: str) -> pd.Series:
    """Descarga una serie de FRED y la convierte a mensual."""
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

    if not rows:
        return pd.Series(dtype=float, name=name)

    df = pd.DataFrame(rows).set_index("fecha")
    series = df["valor"]
    # Si diaria, agregar a mensual
    if len(series) > 300:
        series = series.resample("MS").mean()
    else:
        series.index = series.index.to_period("M").to_timestamp()
        series = series.groupby(level=0).mean()
    series.name = name
    return series


def build_academic_signals(data: pd.DataFrame, new_series: dict[str, pd.Series]) -> pd.DataFrame:
    """Construye señales de largo plazo a partir de las nuevas variables."""
    signals = pd.DataFrame(index=data.loc[SAMPLE_START:].index)

    for name, series in new_series.items():
        aligned = series.reindex(signals.index)
        if aligned.notna().sum() < 60:
            continue

        # Nivel normalizado (z-score rolling 60m)
        mean = aligned.rolling(60, min_periods=36).mean()
        std = aligned.rolling(60, min_periods=36).std()
        signals[f"z_{name}"] = (aligned - mean) / std

        # Cambio 12 meses (momentum)
        if name not in ("epu_global",):  # EPU ya es un índice de cambio
            signals[f"mom12_{name}"] = aligned.pct_change(12) * 100

    # Señal compuesta: promedio de z-scores (signos ajustados)
    # Yield real alto + gold alto + EPU alto + commodities bajo = depreciación
    z_cols = {
        "z_yield_real_10y_tips": +1,   # yield real alto → COP deprecia
        "z_gold_usd": +1,             # gold alto → risk-off → COP deprecia
        "z_epu_global": +1,           # incertidumbre → COP deprecia
        "z_commodities_index": -1,    # commodities alto → COP aprecia
        "z_yield_2y_us": +1,          # yield 2Y alto → Fed hawkish → COP deprecia
    }
    parts = []
    for col, sign in z_cols.items():
        if col in signals.columns:
            parts.append(sign * signals[col])
    if parts:
        signals["score_academico"] = pd.concat(parts, axis=1).mean(axis=1)

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


def evaluate_incremental(
    base_signal: pd.Series,
    new_signal: pd.Series,
    ln_trm: pd.Series,
    horizon: int = 12,
    min_train: int = 60,
) -> dict:
    """Evalúa si new_signal mejora sobre base_signal (CF filter)."""
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat([
        base_signal.rename("cf"),
        new_signal.rename("new"),
        r_forward.rename("r"),
    ], axis=1, sort=True).dropna()

    if len(dataset) < min_train + 30:
        return {}

    # Modelo base: solo CF
    fc_base, fc_combined, act_list = [], [], []
    for i in range(min_train, len(dataset)):
        train = dataset.iloc[:i]
        try:
            m_base = sm.OLS(train["r"], sm.add_constant(train["cf"])).fit()
            m_comb = sm.OLS(train["r"], sm.add_constant(train[["cf", "new"]])).fit()
            fc_base.append(float(m_base.predict(sm.add_constant(dataset[["cf"]].iloc[[i]]))[0]))
            fc_combined.append(float(m_comb.predict(sm.add_constant(dataset[["cf", "new"]].iloc[[i]]))[0]))
            act_list.append(float(dataset["r"].iloc[i]))
        except Exception:
            continue

    if len(fc_base) < 30:
        return {}

    fc_b, fc_c, act = np.array(fc_base), np.array(fc_combined), np.array(act_list)
    mse_base = float(((fc_b - act)**2).mean())
    mse_combined = float(((fc_c - act)**2).mean())
    mse_rw = float((act**2).mean())

    return {
        "r2_oos_cf_solo_pct": 100 * (1 - mse_base / mse_rw),
        "r2_oos_cf_mas_nueva_pct": 100 * (1 - mse_combined / mse_rw),
        "mejora_r2_pp": 100 * (1 - mse_combined / mse_rw) - 100 * (1 - mse_base / mse_rw),
    }


def main():
    print("=" * 70)
    print("VARIABLES ACADÉMICAS: EVALUACIÓN PARA PRONÓSTICO TRM")
    print("=" * 70)

    print("\n[1/4] Descargando 6 series de FRED...")
    new_series = {}
    for fred_id, name in SERIES_TO_DOWNLOAD.items():
        try:
            s = download_fred_series(fred_id, name)
            new_series[name] = s
            print(f"  {fred_id:<20} -> {name:<25} ({len(s)} obs, {s.index.min().date()} a {s.index.max().date()})")
        except Exception as e:
            print(f"  {fred_id:<20} -> ERROR: {e}")
        time.sleep(0.6)

    print("\n[2/4] Construyendo señales...")
    data = build_dataset()
    ln_trm = np.log(data["trm_cop_usd"].loc[SAMPLE_START:].where(data["trm_cop_usd"] > 0)).dropna()
    signals = build_academic_signals(data, new_series)
    print(f"  Señales construidas: {list(signals.columns)}")

    print("\n[3/4] Evaluando OOS a 12 meses...")
    results = []
    for col in signals.columns:
        s = signals[col].dropna()
        if len(s) < 90:
            continue
        m = evaluate_oos(s, ln_trm, horizon=12)
        if m:
            m["senal"] = col
            results.append(m)
            sig = "**" if m["dm_p_valor"] < 0.05 else "*" if m["dm_p_valor"] < 0.10 else ""
            print(f"  {col:<30} R2={m['r2_oos_pct']:>6.2f}%  corr={m['correlacion']:.3f}  dir={m['direccion_pct']:.1f}%  DM p={m['dm_p_valor']:.3f}{sig}")

    # Evaluar mejora incremental sobre CF filter
    print("\n[4/4] Mejora incremental sobre CF filter...")
    cf_cycle, _ = sm.tsa.filters.cffilter(ln_trm, low=6, high=96)
    cf_signal = cf_cycle * 100

    incremental_results = []
    for col in signals.columns:
        s = signals[col].dropna()
        if len(s) < 90:
            continue
        inc = evaluate_incremental(cf_signal, s, ln_trm, horizon=12)
        if inc:
            inc["senal_nueva"] = col
            incremental_results.append(inc)
            mejora = inc["mejora_r2_pp"]
            marca = "+" if mejora > 0 else ""
            print(f"  CF + {col:<25} R2_cf={inc['r2_oos_cf_solo_pct']:.1f}% -> R2_combo={inc['r2_oos_cf_mas_nueva_pct']:.1f}% ({marca}{mejora:.1f} pp)")

    # Guardar
    RESULTS.mkdir(parents=True, exist_ok=True)
    if results:
        pd.DataFrame(results).sort_values("r2_oos_pct", ascending=False).to_csv(
            RESULTS / "variables_academicas_evaluacion.csv", index=False, encoding="utf-8-sig"
        )
    if incremental_results:
        pd.DataFrame(incremental_results).sort_values("mejora_r2_pp", ascending=False).to_csv(
            RESULTS / "variables_academicas_incremental.csv", index=False, encoding="utf-8-sig"
        )
    signals.to_csv(RESULTS / "variables_academicas_series.csv", encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    if results:
        best = max(results, key=lambda x: x["r2_oos_pct"])
        print(f"  Mejor variable individual: {best['senal']} (R2 OOS = {best['r2_oos_pct']:.2f}%)")
    if incremental_results:
        best_inc = max(incremental_results, key=lambda x: x["mejora_r2_pp"])
        print(f"  Mayor mejora sobre CF: +{best_inc['senal_nueva']} ({best_inc['mejora_r2_pp']:+.1f} pp)")
        if best_inc["mejora_r2_pp"] > 2:
            print("  -> HAY valor incremental de las variables académicas")
        else:
            print("  -> El CF filter ya captura la mayor parte de la señal")
    print("=" * 70)


if __name__ == "__main__":
    main()
