"""
Evaluación de variables globales para pronóstico de la TRM.

Usa la base mensual consolidada de FRED y evalúa, por separado y en un score,
rendimientos reales, expectativas de inflación, condiciones financieras,
commodities, actividad estadounidense, desempleo y logística. China se reporta
como señal exploratoria cuando existe, pero sus candidatos incompletos no entran
al modelo balanceado.

Uso:
    python src/forecast_longterm/global_variables.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from trm_model.data.curated import build_monthly_dataset
from trm_model.data.fred import download_fred_series as _download_fred_series
from trm_model.paths import project_paths
from model.config import SAMPLE_START

PATHS = project_paths()
ROOT = PATHS.root
RESULTS = PATHS.results / "pronostico"

SERIES_TO_DOWNLOAD = {
    "DFII10": "yield_real_10y_tips",
    "DFII5": "yield_real_5y",
    "DGS2": "yield_2y_us",
    "DGS10": "yield_10y_us",
    "T10Y2Y": "spread_10y_2y_us",
    "T5YIE": "breakeven_5y_us",
    "T10YIE": "breakeven_10y_us",
    "GEPUCURRENT": "epu_global",
    "STLFSI4": "estres_financiero_stl",
    "NFCI": "nfci_chicago",
    "ANFCI": "anfci_chicago",
    "MANEMP": "us_manufacturing_emp",
    "INDPRO": "us_industrial_production",
    "LRUN64TTUSM156S": "desempleo_us",
    "TSIFRGHT": "fletes_transporte_us",
    "CHNTOT": "precios_importacion_china",
}


def download_fred_series(series_id: str, name: str) -> pd.Series | None:
    """Compatibilidad local sobre el cliente centralizado de FRED."""
    return _download_fred_series(series_id, name, observation_start="2003-01-01")


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
        "z_yield_real_10y_tips": +1,
        "z_yield_real_5y": +1,
        "z_yield_2y_us": +1,
        "z_yield_10y_us": +1,
        "z_spread_10y_2y_us": +1,
        "z_breakeven_5y_us": +1,
        "z_breakeven_10y_us": +1,
        "z_epu_global": +1,
        "z_estres_financiero_stl": +1,
        "z_nfci_chicago": +1,
        "z_anfci_chicago": +1,
        "z_desempleo_us": +1,
        "z_fletes_transporte_us": +1,
        "z_precios_importacion_china": +1,
        "z_produccion_industrial_china": -1,
        "z_indicador_lider_china": -1,
        "z_commodities_index": -1,
        "z_brent_usd": -1,
        "z_us_manufacturing_emp": -1,
        "z_us_industrial_production": -1,
    }
    parts = []
    for col, sign in z_cols.items():
        if col in signals.columns:
            parts.append(sign * signals[col])
    if parts:
        signals["score_global"] = pd.concat(parts, axis=1).mean(axis=1)

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

    # Referencia de señales: solo CF
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
    print("VARIABLES GLOBALES: EVALUACIÓN PARA PRONÓSTICO TRM")
    print("=" * 70)

    print("\n[1/4] Cargando la base global mensual consolidada...")
    data = build_monthly_dataset()
    source_map = {
        "yield_real_10y_tips": "yield_real_10y_tips_pct",
        "yield_real_5y": "yield_real_5y_us_pct",
        "yield_2y_us": "yield_2y_us_pct",
        "yield_10y_us": "yield_10y_us_pct",
        "spread_10y_2y_us": "spread_10y_2y_us_pct",
        "breakeven_5y_us": "breakeven_5y_us_pct",
        "breakeven_10y_us": "breakeven_10y_us_pct",
        "commodities_index": "ln_commodities_global",
        "brent_usd": "ln_brent_global",
        "epu_global": "epu_global",
        "estres_financiero_stl": "estres_financiero_stl",
        "nfci_chicago": "nfci_chicago",
        "anfci_chicago": "anfci_chicago",
        "us_manufacturing_emp": "ln_empleo_manufactura_us",
        "us_industrial_production": "ln_produccion_industrial_us",
        "desempleo_us": "desempleo_us_pct",
        "fletes_transporte_us": "ln_fletes_transporte_us",
        # Estas señales chinas se evalúan solo en la ventana que cubren;
        # permanecen fuera de la muestra balanceada por faltantes publicados.
        "precios_importacion_china": "ln_precios_importacion_china",
        "produccion_industrial_china": "produccion_industrial_china",
        "indicador_lider_china": "indicador_lider_china",
    }
    new_series = {
        name: data[column].loc[SAMPLE_START:].rename(name)
        for name, column in source_map.items()
        if column in data.columns
    }
    ln_trm = np.log(data["trm_cop_usd"].loc[SAMPLE_START:].where(data["trm_cop_usd"] > 0)).dropna()
    print(f"  Series integradas: {list(new_series)}")

    print("\n[2/4] Construyendo señales globales...")
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
            print(f"  {col:<34} R2={m['r2_oos_pct']:>6.2f}%  corr={m['correlacion']:.3f}  dir={m['direccion_pct']:.1f}%  DM p={m['dm_p_valor']:.3f}{sig}")

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
            print(f"  CF + {col:<28} mejora R2={inc['mejora_r2_pp']:+.1f} pp")

    RESULTS.mkdir(parents=True, exist_ok=True)
    if results:
        pd.DataFrame(results).sort_values("r2_oos_pct", ascending=False).to_csv(
            RESULTS / "variables_globales_evaluacion.csv", index=False, encoding="utf-8-sig"
        )
    if incremental_results:
        pd.DataFrame(incremental_results).sort_values("mejora_r2_pp", ascending=False).to_csv(
            RESULTS / "variables_globales_incremental.csv", index=False, encoding="utf-8-sig"
        )
    signals.to_csv(RESULTS / "variables_globales_series.csv", encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    if results:
        best = max(results, key=lambda x: x["r2_oos_pct"])
        print(f"  Mejor señal individual: {best['senal']} (R2 OOS = {best['r2_oos_pct']:.2f}%)")
    if incremental_results:
        best_inc = max(incremental_results, key=lambda x: x["mejora_r2_pp"])
        print(f"  Mayor mejora sobre CF: {best_inc['senal_nueva']} ({best_inc['mejora_r2_pp']:+.1f} pp)")
    print("=" * 70)


if __name__ == "__main__":
    main()
