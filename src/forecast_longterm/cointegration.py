"""
Cointegración TRM — dólar amplio.

Hipótesis: si ln(TRM) y ln(dólar amplio) están cointegradas, existe una
relación de largo plazo estable. Cuando la TRM se desvía de esta relación
(residuo de cointegración positivo), tiende a corregir.

El residuo de cointegración es una señal de "desalineamiento" que podría
predecir retornos futuros — similar al CF filter pero con fundamento
económico explícito (la TRM sigue al dólar global).

Metodología:
1. Test de cointegración de Engle-Granger (2 variables)
2. Test de Johansen (permite más variables)
3. Estimar relación de largo plazo: ln(TRM) = α + β×ln(dólar) + ε
4. El residuo ε_t es la señal de desalineamiento
5. Evaluar OOS como predictor de retornos futuros

Uso:
    python src/forecast_longterm/cointegration.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from scipy import stats

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from estimate_model import build_dataset, SAMPLE_START

RESULTS = ROOT / "results" / "pronostico"


def engle_granger_test(y: pd.Series, x: pd.Series) -> dict:
    """Test de cointegración de Engle-Granger."""
    # Paso 1: regresión de largo plazo
    X = sm.add_constant(x)
    ols = sm.OLS(y, X).fit()
    residuals = ols.resid

    # Paso 2: ADF sobre residuos
    adf = adfuller(residuals, regression="c", autolag="BIC")

    # También usar la función coint() de statsmodels
    coint_stat, coint_p, coint_crit = coint(y, x, trend="c", autolag="BIC")

    return {
        "beta_largo_plazo": float(ols.params.iloc[1]),
        "alpha": float(ols.params.iloc[0]),
        "r2_relacion": float(ols.rsquared),
        "adf_residuos_stat": float(adf[0]),
        "adf_residuos_p": float(adf[1]),
        "coint_stat": float(coint_stat),
        "coint_p": float(coint_p),
        "coint_cv_5pct": float(coint_crit[1]),
        "cointegradas": coint_p < 0.05,
        "residuals": residuals,
    }


def johansen_test(data: pd.DataFrame, det_order: int = 0, k_ar: int = 2) -> dict:
    """Test de Johansen para múltiples variables."""
    clean = data.dropna()
    result = coint_johansen(clean, det_order=det_order, k_ar_diff=k_ar)

    # Trace statistic
    trace_stats = result.lr1
    trace_cvs = result.cvt[:, 1]  # 5% critical values

    # Max eigenvalue
    max_stats = result.lr2
    max_cvs = result.cvm[:, 1]

    n_coint = 0
    for i in range(len(trace_stats)):
        if trace_stats[i] > trace_cvs[i]:
            n_coint = i + 1

    return {
        "n_variables": data.shape[1],
        "trace_stats": trace_stats.tolist(),
        "trace_cv_5pct": trace_cvs.tolist(),
        "max_eigen_stats": max_stats.tolist(),
        "max_eigen_cv_5pct": max_cvs.tolist(),
        "n_relaciones_cointegracion": n_coint,
        "vector_cointegrante": result.evec[:, 0].tolist() if n_coint > 0 else None,
    }


def expanding_cointegration_signal(
    ln_trm: pd.Series,
    ln_dolar: pd.Series,
    min_window: int = 60,
) -> pd.Series:
    """
    Genera señal de desalineamiento SIN look-ahead:
    en cada t, estima la relación de LP con datos [0:t] y calcula el residuo en t.
    """
    signal = pd.Series(np.nan, index=ln_trm.index, dtype=float)
    common = pd.concat([ln_trm, ln_dolar], axis=1).dropna()

    for i in range(min_window, len(common)):
        y_train = common.iloc[:i + 1, 0]
        x_train = common.iloc[:i + 1, 1]
        X = sm.add_constant(x_train)
        try:
            ols = sm.OLS(y_train, X).fit()
            # Residuo en t = desalineamiento actual
            signal.iloc[i] = float(ols.resid.iloc[-1])
        except Exception:
            continue

    return signal * 100  # en %


def evaluate_signal_oos(
    signal: pd.Series,
    ln_trm: pd.Series,
    horizon: int = 12,
    min_train: int = 60,
) -> dict:
    """Backtest OOS expanding."""
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat([signal.rename("signal"), r_forward.rename("r_fwd")], axis=1, sort=True).dropna()

    if len(dataset) < min_train + 30:
        return {}

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
    print("COINTEGRACIÓN TRM — DÓLAR AMPLIO")
    print("=" * 70)

    print("\n[1/5] Cargando datos...")
    data = build_dataset()
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    dolar = data["indice_dolar_amplio"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()
    ln_dolar = np.log(dolar.where(dolar > 0)).dropna()

    common = pd.concat([ln_trm.rename("ln_trm"), ln_dolar.rename("ln_dolar")], axis=1).dropna()
    print(f"  Observaciones comunes: {len(common)}")

    print("\n[2/5] Test de Engle-Granger...")
    eg = engle_granger_test(common["ln_trm"], common["ln_dolar"])
    print(f"  Relación LP: ln(TRM) = {eg['alpha']:.3f} + {eg['beta_largo_plazo']:.3f} × ln(dólar)")
    print(f"  R² de la relación: {eg['r2_relacion']*100:.1f}%")
    print(f"  ADF sobre residuos: stat={eg['adf_residuos_stat']:.3f}, p={eg['adf_residuos_p']:.4f}")
    print(f"  Test coint(): stat={eg['coint_stat']:.3f}, p={eg['coint_p']:.4f}")
    print(f"  ¿Cointegradas al 5%? {'SÍ' if eg['cointegradas'] else 'NO'}")

    print("\n[3/5] Test de Johansen (ln_trm, ln_dolar)...")
    joh = johansen_test(common, det_order=0, k_ar=2)
    print(f"  Trace stats: {[f'{s:.2f}' for s in joh['trace_stats']]}")
    print(f"  CV 5%:       {[f'{c:.2f}' for c in joh['trace_cv_5pct']]}")
    print(f"  Relaciones de cointegración: {joh['n_relaciones_cointegracion']}")
    if joh["vector_cointegrante"]:
        vec = joh["vector_cointegrante"]
        print(f"  Vector: [{vec[0]:.4f}, {vec[1]:.4f}] (normalizado)")

    print("\n[4/5] Generando señal expanding (sin look-ahead)...")
    signal = expanding_cointegration_signal(common["ln_trm"], common["ln_dolar"], min_window=60)
    signal_clean = signal.dropna()
    print(f"  Señal disponible: {len(signal_clean)} meses")
    print(f"  Media: {signal_clean.mean():.3f}%  |  Std: {signal_clean.std():.3f}%")
    print(f"  Valor actual: {signal_clean.iloc[-1]:.2f}%")

    # ADF del residuo expanding
    adf_exp = adfuller(signal_clean, regression="c", autolag="BIC")
    print(f"  ADF residuo expanding: stat={adf_exp[0]:.3f}, p={adf_exp[1]:.4f}")

    print("\n[5/5] Evaluando OOS como predictor...")
    results = []
    for h in [6, 12, 18]:
        m = evaluate_signal_oos(signal, ln_trm, horizon=h, min_train=60)
        if m:
            m["horizonte"] = h
            m["senal"] = "coint_trm_dolar"
            results.append(m)
            sig = "**" if m["dm_p_valor"] < 0.05 else "*" if m["dm_p_valor"] < 0.10 else ""
            print(f"  h={h:>2}m: R2 OOS={m['r2_oos_pct']:>7.2f}%  corr={m['correlacion']:.3f}  dir={m['direccion_pct']:.1f}%  DM p={m['dm_p_valor']:.3f}{sig}")

    # Guardar
    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(RESULTS / "cointegracion_trm_dolar.csv", index=False, encoding="utf-8-sig")

    signal_df = pd.DataFrame({
        "fecha": signal.index, "desalineamiento_pct": signal.values
    })
    signal_df.to_csv(RESULTS / "cointegracion_serie_desalineamiento.csv", index=False, encoding="utf-8-sig")

    summary = pd.DataFrame([{
        "test": "Engle-Granger",
        "beta": eg["beta_largo_plazo"],
        "alpha": eg["alpha"],
        "r2": eg["r2_relacion"],
        "coint_p": eg["coint_p"],
        "cointegradas": eg["cointegradas"],
    }, {
        "test": "Johansen (trace)",
        "n_relaciones": joh["n_relaciones_cointegracion"],
    }])
    summary.to_csv(RESULTS / "cointegracion_tests.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("CONCLUSIÓN")
    print("=" * 70)
    if eg["cointegradas"]:
        print(f"  TRM y dólar amplio ESTÁN cointegradas (p = {eg['coint_p']:.4f})")
        print(f"  Elasticidad de LP: 1% de dólar global → {eg['beta_largo_plazo']:.2f}% de TRM")
        print(f"  Desalineamiento actual: {signal_clean.iloc[-1]:.2f}%")
        if signal_clean.iloc[-1] > 3:
            print(f"  → TRM SOBRE su relación con el dólar → esperada apreciación")
        elif signal_clean.iloc[-1] < -3:
            print(f"  → TRM BAJO su relación con el dólar → esperada depreciación")
        else:
            print(f"  → TRM alineada con el dólar global (sin señal)")
    else:
        print(f"  TRM y dólar amplio NO están cointegradas al 5% (p = {eg['coint_p']:.4f})")
        print(f"  La relación de LP no es estable → señal menos confiable")
    print("=" * 70)


if __name__ == "__main__":
    main()
