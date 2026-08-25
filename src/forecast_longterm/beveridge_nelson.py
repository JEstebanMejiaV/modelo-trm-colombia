"""
Descomposición de Beveridge-Nelson de la TRM.

Idea fundamental:
  ln(TRM_t) = τ_t + c_t

  τ_t = componente permanente (random walk con drift) — NO predecible
  c_t = componente transitorio (estacionario) — PREDECIBLE

El componente transitorio es la "brecha" entre la TRM y su valor de
largo plazo implícito. Si c_t > 0, la TRM está "cara" y tenderá a caer.

La descomposición BN se basa en un ARIMA(p,1,q) de la serie:
  τ_t = ln(TRM_t) + ψ(1) × (suma de psi_j × Δln(TRM_{t-j}))
  c_t = ln(TRM_t) - τ_t

donde ψ(1) es la suma de los coeficientes MA del ARIMA(p,1,q) evaluado
en la representación MA(∞).

Ventajas sobre HP y CF:
- Tiene interpretación económica clara (permanente = fundamentales, transitorio = desviación)
- No sufre endpoint bias (usa solo datos pasados)
- El componente transitorio es estacionario por construcción

Uso:
    python src/forecast_longterm/beveridge_nelson.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.arima.model import ARIMA
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

from estimate_model import build_dataset, SAMPLE_START, SAMPLE_END

RESULTS = ROOT / "results" / "pronostico"


def beveridge_nelson_decomposition(
    series: pd.Series,
    ar_order: int = 12,
    method: str = "ar",
) -> tuple[pd.Series, pd.Series]:
    """
    Descomposición BN usando un AR(p) sobre Δy_t.

    Método:
    1. Estimar AR(p) sobre Δy_t = c + φ_1 Δy_{t-1} + ... + φ_p Δy_{t-p} + ε_t
    2. Calcular ψ(1) = 1/(1 - φ_1 - φ_2 - ... - φ_p)
    3. Componente transitorio: c_t = -ψ(1) × pronóstico condicional de Δy futuro
       En la práctica: c_t = -Σ_{j=1}^{∞} E_t[Δy_{t+j}]
       Con AR(p): c_t = -Φ'(I-Φ)^{-1} × estado_t

    Implementación directa con recursión del pronóstico AR.
    """
    y = series.dropna()
    dy = y.diff().dropna()

    if method == "ar":
        # Estimar AR(p) sobre los cambios
        model = sm.tsa.AutoReg(dy, lags=ar_order, old_names=False).fit()
        params = model.params  # const, y.L1, y.L2, ..., y.Lp
        const = float(params.iloc[0])
        phi = params.iloc[1:].values  # φ_1, ..., φ_p

    elif method == "arima":
        # ARIMA(p,1,0) — equivalente
        model = ARIMA(y, order=(ar_order, 1, 0)).fit()
        const = float(model.params.get("const", 0))
        phi = np.array([float(model.params.get(f"ar.L{i}", 0)) for i in range(1, ar_order + 1)])

    else:
        raise ValueError(f"Método desconocido: {method}")

    # ψ(1) = 1 / (1 - Σφ_i) — suma de la función impulso-respuesta
    sum_phi = float(phi.sum())
    if abs(1 - sum_phi) < 0.01:
        # Casi una raíz unitaria en el AR de los cambios — BN no aplica bien
        psi_1 = 100.0  # cap arbitrario
    else:
        psi_1 = 1.0 / (1.0 - sum_phi)

    # Componente transitorio via pronóstico iterado
    # c_t = -Σ_{j=1}^{H} E_t[Δy_{t+j}] para H → ∞ (usamos H=120)
    H = 120  # horizonte de truncamiento
    transitory = pd.Series(np.nan, index=dy.index, dtype=float)

    for t_idx in range(ar_order, len(dy)):
        # Estado actual: últimos p cambios
        state = dy.iloc[t_idx - ar_order + 1:t_idx + 1].values[::-1]  # [Δy_t, Δy_{t-1}, ..., Δy_{t-p+1}]
        if len(state) < ar_order:
            continue

        # Iterar pronósticos
        forecast_sum = 0.0
        current_state = state.copy()
        for h in range(1, H + 1):
            # E[Δy_{t+h}] = const + φ' × estado
            forecast = const + float(phi @ current_state[:ar_order])
            forecast_sum += forecast
            # Actualizar estado: shift y añadir pronóstico
            current_state = np.concatenate([[forecast], current_state[:-1]])

        transitory.iloc[t_idx] = -forecast_sum

    # Alinear con la serie original
    transitory = transitory.reindex(y.index)
    # Componente permanente
    permanent = y - transitory

    return permanent, transitory


def evaluate_bn_signal(
    transitory: pd.Series,
    ln_trm: pd.Series,
    horizons: list[int] = [6, 12, 18],
    min_train: int = 60,
) -> pd.DataFrame:
    """Evalúa OOS si el componente transitorio predice retornos futuros."""
    results = []
    for h in horizons:
        r_forward = (ln_trm.shift(-h) - ln_trm) * 100
        dataset = pd.concat([
            transitory.rename("bn_transitory"),
            r_forward.rename("r_fwd"),
        ], axis=1, sort=True).dropna()

        if len(dataset) < min_train + 30:
            continue

        # Backtest expanding
        forecasts, actuals = [], []
        for i in range(min_train, len(dataset)):
            train = dataset.iloc[:i]
            X = sm.add_constant(train["bn_transitory"])
            y = train["r_fwd"]
            try:
                model = sm.OLS(y, X).fit()
                signal = float(dataset["bn_transitory"].iloc[i])
                fc = float(model.params.iloc[0] + model.params.iloc[1] * signal)
                forecasts.append(fc)
                actuals.append(float(dataset["r_fwd"].iloc[i]))
            except Exception:
                continue

        if len(forecasts) < 30:
            continue

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

        results.append({
            "horizonte_meses": h,
            "n_oos": len(forecasts),
            "r2_oos_pct": 100 * r2_oos,
            "correlacion": corr,
            "direccion_pct": 100 * direction,
            "dm_p_valor": dm_p,
        })

    return pd.DataFrame(results)


def main():
    print("=" * 70)
    print("DESCOMPOSICIÓN DE BEVERIDGE-NELSON DE LA TRM")
    print("=" * 70)

    print("\n[1/4] Cargando datos...")
    data = build_dataset()
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()
    print(f"  Observaciones: {len(ln_trm)} meses")

    print("\n[2/4] Estimando descomposición BN (AR(12) sobre cambios)...")
    permanent, transitory = beveridge_nelson_decomposition(ln_trm, ar_order=12)
    trans_clean = transitory.dropna()
    print(f"  Componente transitorio: {len(trans_clean)} obs")
    print(f"  Media: {trans_clean.mean():.4f}")
    print(f"  Std: {trans_clean.std():.4f}")
    print(f"  Min: {trans_clean.min():.4f}  Max: {trans_clean.max():.4f}")
    print(f"  Valor actual: {trans_clean.iloc[-1]:.4f}")

    # ¿Es estacionario? (debe serlo por construcción)
    from statsmodels.tsa.stattools import adfuller
    adf = adfuller(trans_clean, regression="c", autolag="BIC")
    print(f"  ADF test: stat={adf[0]:.3f}, p={adf[1]:.4f} ({'estacionario' if adf[1] < 0.05 else 'NO estacionario'})")

    print("\n[3/4] Evaluando poder predictivo OOS...")
    # Escalar a porcentaje para interpretabilidad
    trans_pct = transitory * 100
    evaluation = evaluate_bn_signal(trans_pct, ln_trm, horizons=[6, 12, 18])

    if not evaluation.empty:
        for _, row in evaluation.iterrows():
            sig = "**" if row["dm_p_valor"] < 0.05 else "*" if row["dm_p_valor"] < 0.10 else ""
            print(f"  h={int(row['horizonte_meses']):>2}m: R2 OOS={row['r2_oos_pct']:>7.2f}%  corr={row['correlacion']:.3f}  dir={row['direccion_pct']:.1f}%  DM p={row['dm_p_valor']:.3f}{sig}")

    # Comparar con CF filter
    print("\n  Comparación con CF filter (referencia):")
    cf_cycle, cf_trend = sm.tsa.filters.cffilter(ln_trm, low=6, high=96)
    cf_pct = cf_cycle * 100
    cf_eval = evaluate_bn_signal(cf_pct, ln_trm, horizons=[6, 12, 18])
    if not cf_eval.empty:
        for _, row in cf_eval.iterrows():
            sig = "**" if row["dm_p_valor"] < 0.05 else "*" if row["dm_p_valor"] < 0.10 else ""
            print(f"  CF h={int(row['horizonte_meses']):>2}m: R2 OOS={row['r2_oos_pct']:>7.2f}%  corr={row['correlacion']:.3f}  dir={row['direccion_pct']:.1f}%  DM p={row['dm_p_valor']:.3f}{sig}")

    print("\n[4/4] Guardando...")
    RESULTS.mkdir(parents=True, exist_ok=True)

    bn_series = pd.DataFrame({
        "fecha": ln_trm.index,
        "ln_trm": ln_trm.values,
        "permanente_bn": permanent.reindex(ln_trm.index).values,
        "transitorio_bn": transitory.reindex(ln_trm.index).values,
        "transitorio_bn_pct": (transitory.reindex(ln_trm.index) * 100).values,
    })
    bn_series.to_csv(RESULTS / "beveridge_nelson_descomposicion.csv", index=False, encoding="utf-8-sig")

    if not evaluation.empty:
        evaluation["senal"] = "BN transitorio"
        if not cf_eval.empty:
            cf_eval["senal"] = "CF filter"
            combined = pd.concat([evaluation, cf_eval], ignore_index=True)
        else:
            combined = evaluation
        combined.to_csv(RESULTS / "beveridge_nelson_vs_cf.csv", index=False, encoding="utf-8-sig")

    # Estado actual
    print("\n" + "=" * 70)
    print("ESTADO ACTUAL")
    print("=" * 70)
    bn_now = float(trans_clean.iloc[-1] * 100)
    print(f"  Componente transitorio BN: {bn_now:.2f}%")
    if bn_now > 2:
        print(f"  -> TRM SOBRE su componente permanente ({bn_now:.1f}%) -> tendencia a apreciar")
    elif bn_now < -2:
        print(f"  -> TRM BAJO su componente permanente ({bn_now:.1f}%) -> tendencia a depreciar")
    else:
        print(f"  -> TRM cerca de su componente permanente (sin señal clara)")
    print("=" * 70)


if __name__ == "__main__":
    main()
