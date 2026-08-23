"""
Backtest out-of-sample de señales de largo plazo.

La evaluación in-sample (R²=50%) puede sobreestimar el poder predictivo.
Este módulo implementa un backtest rolling genuino:
- Estima el filtro HP SOLO con datos hasta t (no usa el futuro)
- Genera la señal en t usando solo información pasada
- Evalúa el retorno forward de t a t+h
- Reporta métricas puramente out-of-sample

Uso:
    python src/forecast_longterm/backtest.py
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


def hp_filter_expanding(series: pd.Series, lamb: float = 14400, min_obs: int = 60) -> pd.Series:
    """
    Filtro HP expanding: en cada mes t, calcula la tendencia usando SOLO datos hasta t.
    Esto elimina el look-ahead bias del HP estándar (que usa toda la muestra).
    """
    trend_values = pd.Series(np.nan, index=series.index, dtype=float)
    clean = series.dropna()

    for i in range(min_obs, len(clean)):
        subset = clean.iloc[:i + 1]
        _, trend = sm.tsa.filters.hpfilter(subset, lamb=lamb)
        # Solo conservar el último valor de la tendencia (que corresponde a t)
        trend_values.loc[clean.index[i]] = float(trend.iloc[-1])

    return trend_values


def rolling_backtest(
    data: pd.DataFrame,
    horizon_months: int = 12,
    min_history: int = 60,
    estimation_window: int | None = None,
) -> pd.DataFrame:
    """
    Backtest genuino de la señal de reversión a la media.

    Para cada mes t:
    1. Calcula la tendencia HP con datos [t-window, t] (o expanding si window=None)
    2. Genera la señal: desviación = ln(TRM_t) - trend_t
    3. Estima β con datos [t-window, t-1] (o expanding)
    4. Pronóstico: r_hat = α_hat + β_hat × señal_t
    5. Compara con r_realizado = ln(TRM_{t+h}) - ln(TRM_t)
    """
    ln_trm = np.log(data["trm_cop_usd"].where(data["trm_cop_usd"] > 0)).dropna()
    ln_trm = ln_trm.loc[SAMPLE_START:]

    # Calcular tendencia HP expanding (sin look-ahead)
    print("  Calculando tendencia HP expanding (sin look-ahead)...")
    trend = hp_filter_expanding(ln_trm, lamb=14400, min_obs=min_history)

    # Señal: desviación de la TRM vs tendencia
    deviation = ln_trm - trend

    # Retorno forward h meses
    r_forward = (ln_trm.shift(-horizon_months) - ln_trm) * 100  # en %

    # Construir dataset
    dataset = pd.DataFrame({
        "deviation": deviation,
        "r_forward": r_forward,
    }).dropna()

    # Backtest: desde el mes min_history + estimation_window hasta el final
    start_idx = min_history + (estimation_window or 60)
    if start_idx >= len(dataset):
        return pd.DataFrame()

    rows = []
    for i in range(start_idx, len(dataset)):
        # Datos para estimar β: todos los meses anteriores con retorno forward disponible
        if estimation_window:
            train_start = max(0, i - estimation_window)
        else:
            train_start = 0

        train = dataset.iloc[train_start:i]
        train_valid = train.dropna()

        if len(train_valid) < 30:
            continue

        # Estimar: r_forward = α + β × deviation
        X_train = sm.add_constant(train_valid["deviation"])
        y_train = train_valid["r_forward"]
        try:
            model = sm.OLS(y_train, X_train).fit()
        except Exception:
            continue

        # Señal de HOY
        signal_today = float(dataset["deviation"].iloc[i])

        # Pronóstico
        forecast = float(model.predict(np.array([[1.0, signal_today]]))[0])

        # Retorno realizado (si está disponible)
        actual = dataset["r_forward"].iloc[i]
        if np.isnan(actual):
            continue

        rows.append({
            "fecha": dataset.index[i],
            "senal_desviacion_pct": signal_today * 100,
            "pronostico_retorno_pct": forecast,
            "retorno_realizado_pct": float(actual),
            "beta_estimado": float(model.params.iloc[1]) if len(model.params) > 1 else np.nan,
            "r2_insample": float(model.rsquared),
            "n_train": len(train_valid),
        })

    return pd.DataFrame(rows)


def evaluate_backtest(bt: pd.DataFrame) -> dict:
    """Métricas del backtest out-of-sample."""
    if bt.empty:
        return {}

    errors = bt["pronostico_retorno_pct"] - bt["retorno_realizado_pct"]
    rw_errors = -bt["retorno_realizado_pct"]  # caminata = sin cambio

    mse_model = float((errors**2).mean())
    mse_rw = float((rw_errors**2).mean())
    r2_oos = 1.0 - mse_model / mse_rw

    # Dirección
    direction = float(np.mean(
        np.sign(bt["pronostico_retorno_pct"]) == np.sign(bt["retorno_realizado_pct"])
    ))

    # Correlación pronóstico-realizado
    corr = float(bt["pronostico_retorno_pct"].corr(bt["retorno_realizado_pct"]))

    # DM test
    d = rw_errors.values**2 - errors.values**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    # Sharpe de la estrategia: comprar USD si pronóstico > 0
    strategy = np.sign(bt["pronostico_retorno_pct"].values) * bt["retorno_realizado_pct"].values
    sharpe = float(strategy.mean() / strategy.std() * np.sqrt(12)) if strategy.std() > 0 else 0

    return {
        "observaciones_oos": len(bt),
        "r2_oos_pct": 100 * r2_oos,
        "correlacion_pronostico_real": corr,
        "acierto_direccion_pct": 100 * direction,
        "rmse_modelo_pct": float(np.sqrt(mse_model)),
        "rmse_caminata_pct": float(np.sqrt(mse_rw)),
        "dm_stat": dm_stat,
        "dm_p_valor": dm_p,
        "sharpe_anualizado": sharpe,
        "beta_medio": float(bt["beta_estimado"].mean()),
        "beta_std": float(bt["beta_estimado"].std()),
    }


def main():
    print("=" * 70)
    print("BACKTEST OUT-OF-SAMPLE — SEÑAL DE REVERSIÓN A LA MEDIA")
    print("=" * 70)
    print("\nEste backtest usa HP expanding (sin look-ahead) y estima β")
    print("solo con datos pasados. Es genuinamente out-of-sample.\n")

    print("[1/3] Cargando datos...")
    data = build_dataset()
    print(f"  Período: {data.index.min().date()} a {data.index.max().date()}")

    print("\n[2/3] Backtest por horizonte...")
    all_results = []
    for h in [6, 12, 18, 24]:
        print(f"\n  Horizonte: {h} meses")
        bt = rolling_backtest(data, horizon_months=h)
        if bt.empty:
            print("    Sin datos suficientes.")
            continue

        metrics = evaluate_backtest(bt)
        metrics["horizonte_meses"] = h
        all_results.append(metrics)

        sig = "***" if metrics["dm_p_valor"] < 0.01 else "**" if metrics["dm_p_valor"] < 0.05 else "*" if metrics["dm_p_valor"] < 0.10 else ""
        print(f"    R² OOS: {metrics['r2_oos_pct']:.1f}%  |  Dirección: {metrics['acierto_direccion_pct']:.1f}%  |  DM p={metrics['dm_p_valor']:.3f}{sig}")
        print(f"    Correlación pronóstico-real: {metrics['correlacion_pronostico_real']:.3f}")
        print(f"    β medio: {metrics['beta_medio']:.3f} ± {metrics['beta_std']:.3f}")

        # Guardar serie del backtest
        bt.to_csv(RESULTS / f"backtest_largo_plazo_{h}m.csv", index=False, encoding="utf-8-sig")

    print("\n[3/3] Guardando resumen...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(all_results)
    summary.to_csv(RESULTS / "backtest_largo_plazo_resumen.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("RESUMEN OUT-OF-SAMPLE (HP expanding, β estimado solo con pasado)")
    print("=" * 70)
    if not summary.empty:
        print(summary[["horizonte_meses", "r2_oos_pct", "acierto_direccion_pct", "dm_p_valor", "sharpe_anualizado"]].to_string(index=False))
        best = summary.loc[summary["r2_oos_pct"].idxmax()]
        print(f"\n  Mejor horizonte: {int(best['horizonte_meses'])} meses")
        print(f"  R² OOS: {best['r2_oos_pct']:.1f}%")
        if best["dm_p_valor"] < 0.05:
            print("  ✓ La señal funciona OUT-OF-SAMPLE al 5%.")
        else:
            print("  La señal no es significativa out-of-sample al 5%.")
    print("=" * 70)


if __name__ == "__main__":
    main()
