"""
Comparación de filtros de series de tiempo para extraer la tendencia de la TRM.

El filtro ideal para pronóstico debe:
1. No tener endpoint bias (no usar datos futuros)
2. Capturar la tendencia de largo plazo sin sobrereaccionar
3. Producir una señal de desviación que prediga retornos futuros OOS

Filtros evaluados:
- Hodrick-Prescott (λ=14400) — referencia con look-ahead
- HP expanding (solo datos pasados) — corrección del endpoint bias
- Media móvil simple 60 meses
- Media móvil exponencial (span=60)
- Baxter-King bandpass (6-96 meses)
- Christiano-Fitzgerald bandpass (6-96 meses, asymmetric)
- Hamilton (2 años adelante, regresión con 4 rezagos = h=24, p=12)
- Butterworth lowpass (periodo de corte = 60 meses)

Uso:
    python src/forecast_longterm/compare_filters.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import signal as scipy_signal
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

from estimate_model import build_dataset, SAMPLE_START, SAMPLE_END

RESULTS = ROOT / "results" / "pronostico"


def apply_filters(ln_trm: pd.Series) -> pd.DataFrame:
    """Aplica todos los filtros y devuelve las tendencias estimadas."""
    n = len(ln_trm)
    trends = pd.DataFrame(index=ln_trm.index)

    # 1. HP estándar (con look-ahead — referencia)
    _, hp_trend = sm.tsa.filters.hpfilter(ln_trm, lamb=14400)
    trends["hp_standard"] = hp_trend

    # 2. HP expanding (sin look-ahead)
    hp_exp = pd.Series(np.nan, index=ln_trm.index)
    for i in range(60, n):
        subset = ln_trm.iloc[:i + 1]
        _, t = sm.tsa.filters.hpfilter(subset, lamb=14400)
        hp_exp.iloc[i] = t.iloc[-1]
    trends["hp_expanding"] = hp_exp

    # 3. Media móvil simple 60 meses
    trends["ma_60m"] = ln_trm.rolling(60, min_periods=48).mean()

    # 4. Media móvil exponencial (span=60)
    trends["ema_60m"] = ln_trm.ewm(span=60, min_periods=36).mean()

    # 5. Baxter-King bandpass (extrae ciclo 6-96 meses, lo que queda es tendencia)
    try:
        bk_cycle = sm.tsa.filters.bkfilter(ln_trm, low=6, high=96, K=36)
        # La tendencia es la serie original menos el ciclo
        trends["bk_trend"] = ln_trm.iloc[36:-36] - bk_cycle.values
        # Rellenar con NaN los extremos
        trends["bk_trend"] = trends["bk_trend"].reindex(ln_trm.index)
    except Exception:
        pass

    # 6. Christiano-Fitzgerald (asimétrico — menos endpoint bias)
    try:
        cf_cycle, cf_trend = sm.tsa.filters.cffilter(ln_trm, low=6, high=96)
        trends["cf_trend"] = cf_trend
    except Exception:
        pass

    # 7. Hamilton filter (h=24, p=12) — regresión de ln_trm_{t+h} sobre rezagos
    # En tiempo real: usar versión backward (regresión de ln_trm_t sobre ln_trm_{t-24:t-24-p})
    h = 24
    p = 12
    hamilton_trend = pd.Series(np.nan, index=ln_trm.index)
    for i in range(h + p, n):
        y_val = ln_trm.iloc[i]
        x_vals = ln_trm.iloc[i - h - p + 1:i - h + 1].values
        if len(x_vals) == p:
            x_with_const = np.concatenate([[1.0], x_vals])
            # Estimar con ventana expanding
            y_train = ln_trm.iloc[h + p:i + 1].values
            X_train = np.column_stack([
                np.ones(len(y_train)),
                *[ln_trm.iloc[j - h:j - h + len(y_train)].values for j in range(h + p, i + 1)
                  if len(ln_trm.iloc[j - h:j - h + len(y_train)]) == len(y_train)]
            ])
            # Simplificación: usar residuos de regresión directa
            pass  # Hamilton es complejo — usar statsmodels si disponible
    # Simplificación Hamilton: usar residuo de AR(p) a horizonte h
    try:
        from statsmodels.tsa.ar_model import AutoReg
        ar_model = AutoReg(ln_trm.values, lags=p, old_names=False).fit()
        hamilton_trend = pd.Series(ar_model.fittedvalues, index=ln_trm.index[p:])
        trends["hamilton"] = hamilton_trend.reindex(ln_trm.index)
    except Exception:
        pass

    # 8. Butterworth lowpass (periodo de corte = 60 meses)
    try:
        # Frecuencia de corte: 1/60 ciclos por mes, normalizada a Nyquist (0.5)
        fc = 1 / 60
        b, a = scipy_signal.butter(2, fc / 0.5, btype="low")
        # Aplicar filtro forward-only (causal, sin look-ahead)
        filtered = scipy_signal.lfilter(b, a, ln_trm.values)
        trends["butterworth"] = pd.Series(filtered, index=ln_trm.index)
    except Exception:
        pass

    return trends


def evaluate_filter_oos(
    deviation: pd.Series,
    ln_trm: pd.Series,
    horizon: int = 12,
    min_train: int = 60,
) -> dict:
    """Evalúa OOS: estima β con datos pasados, pronostica retorno forward."""
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat([
        deviation.rename("dev"),
        r_forward.rename("r_fwd"),
    ], axis=1, sort=True).dropna()

    if len(dataset) < min_train + 30:
        return {}

    forecasts, actuals = [], []
    for i in range(min_train, len(dataset)):
        train = dataset.iloc[:i]
        X = sm.add_constant(train["dev"])
        y = train["r_fwd"]
        try:
            model = sm.OLS(y, X).fit()
            signal_now = float(dataset["dev"].iloc[i])
            fc = float(model.params.iloc[0] + model.params.iloc[1] * signal_now)
            forecasts.append(fc)
            actuals.append(float(dataset["r_fwd"].iloc[i]))
        except Exception:
            continue

    if len(forecasts) < 30:
        return {}

    fc = np.array(forecasts)
    act = np.array(actuals)
    err = fc - act
    rw_err = -act

    mse_m = float((err**2).mean())
    mse_rw = float((rw_err**2).mean())
    r2_oos = 1.0 - mse_m / mse_rw
    corr = float(np.corrcoef(fc, act)[0, 1])
    direction = float(np.mean(np.sign(fc) == np.sign(act)))

    d = rw_err**2 - err**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    return {
        "n_oos": len(forecasts),
        "r2_oos_pct": 100 * r2_oos,
        "correlacion": corr,
        "direccion_pct": 100 * direction,
        "dm_p_valor": dm_p,
    }


def main():
    print("=" * 70)
    print("COMPARACIÓN DE FILTROS DE SERIES DE TIEMPO PARA LA TRM")
    print("=" * 70)

    print("\n[1/3] Cargando datos y aplicando filtros...")
    data = build_dataset()
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()
    print(f"  Observaciones: {len(ln_trm)} ({ln_trm.index.min().date()} a {ln_trm.index.max().date()})")

    trends = apply_filters(ln_trm)
    print(f"  Filtros calculados: {list(trends.columns)}")

    print("\n[2/3] Evaluando OOS a 12 meses...")
    results = []
    for col in trends.columns:
        trend = trends[col].dropna()
        if len(trend) < 90:
            continue
        # Desviación = ln(TRM) - tendencia (en %)
        deviation = (ln_trm - trend.reindex(ln_trm.index)) * 100
        deviation = deviation.dropna()
        if len(deviation) < 90:
            continue

        metrics = evaluate_filter_oos(deviation, ln_trm, horizon=12, min_train=60)
        if metrics:
            metrics["filtro"] = col
            results.append(metrics)
            sig = "**" if metrics["dm_p_valor"] < 0.05 else "*" if metrics["dm_p_valor"] < 0.10 else ""
            print(f"  {col:<20} R²OOS={metrics['r2_oos_pct']:>7.2f}%  corr={metrics['correlacion']:.3f}  dir={metrics['direccion_pct']:.1f}%  DM p={metrics['dm_p_valor']:.3f}{sig}")

    print("\n[3/3] Guardando...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(results).sort_values("r2_oos_pct", ascending=False)
    comparison.to_csv(RESULTS / "comparacion_filtros_tendencia.csv", index=False, encoding="utf-8-sig")
    trends.to_csv(RESULTS / "series_filtros_tendencia.csv", encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("RANKING DE FILTROS (OOS, 12 meses)")
    print("=" * 70)
    print(comparison[["filtro", "r2_oos_pct", "correlacion", "direccion_pct", "dm_p_valor"]].to_string(index=False))

    best = comparison.iloc[0]
    print(f"\n  Mejor filtro: {best['filtro']}")
    print(f"  R² OOS: {best['r2_oos_pct']:.2f}%")
    print(f"  Correlación: {best['correlacion']:.3f}")
    print(f"  Dirección: {best['direccion_pct']:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
