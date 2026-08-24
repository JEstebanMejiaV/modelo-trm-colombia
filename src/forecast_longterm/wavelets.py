"""
Análisis wavelet de la TRM: en qué frecuencia está la señal predecible.

Descompone ln(TRM) en bandas de frecuencia usando Discrete Wavelet Transform (DWT)
con Daubechies-4. Cada nivel captura un rango de períodos:

  Nivel 1 (D1): 2-4 meses (ruido de alta frecuencia)
  Nivel 2 (D2): 4-8 meses (ciclo corto)
  Nivel 3 (D3): 8-16 meses (ciclo medio — donde está la señal CF)
  Nivel 4 (D4): 16-32 meses (ciclo largo)
  Nivel 5 (D5): 32-64 meses (tendencia cíclica)
  Aproximación (A5): >64 meses (tendencia secular)

Evalúa qué nivel contiene poder predictivo para retornos futuros.
Compara con CF filter (que captura 6-96 meses todo junto).

Uso:
    python src/forecast_longterm/wavelets.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pywt
import statsmodels.api as sm
from scipy import stats

import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from estimate_model import build_dataset, SAMPLE_START

RESULTS = ROOT / "results" / "pronostico"


def wavelet_decomposition(
    series: pd.Series,
    wavelet: str = "db4",
    levels: int = 5,
) -> dict[str, pd.Series]:
    """
    Descomposición wavelet discreta (DWT) de una serie mensual.

    Retorna los detalles D1-D5 y la aproximación A5.
    Cada componente se puede reconstruir a la longitud original.
    """
    y = series.dropna().values.copy()  # .copy() para que pywt pueda escribir
    n = len(y)

    # Descomposición en niveles
    coeffs = pywt.wavedec(y, wavelet, level=levels)
    # coeffs = [cA5, cD5, cD4, cD3, cD2, cD1]

    # Reconstruir cada componente por separado
    components = {}
    for i in range(1, len(coeffs)):
        level = levels - i + 1
        # Poner ceros en todos los coeficientes excepto el nivel actual
        detail_coeffs = [np.zeros_like(c) for c in coeffs]
        detail_coeffs[i] = coeffs[i]
        reconstructed = pywt.waverec(detail_coeffs, wavelet)[:n]
        period_lo = 2 ** level
        period_hi = 2 ** (level + 1)
        components[f"D{level} ({period_lo}-{period_hi}m)"] = pd.Series(
            reconstructed, index=series.dropna().index
        )

    # Aproximación (tendencia)
    approx_coeffs = [coeffs[0]] + [np.zeros_like(c) for c in coeffs[1:]]
    approx = pywt.waverec(approx_coeffs, wavelet)[:n]
    components[f"A{levels} (>{2**levels}m)"] = pd.Series(
        approx, index=series.dropna().index
    )

    return components


def evaluate_wavelet_signal(
    component: pd.Series,
    ln_trm: pd.Series,
    horizon: int = 12,
    min_train: int = 60,
) -> dict:
    """Evalúa OOS si un componente wavelet predice retornos futuros."""
    # La señal: valor actual del componente (desviación del ciclo)
    r_forward = (ln_trm.shift(-horizon) - ln_trm) * 100
    dataset = pd.concat([
        component.rename("wavelet"),
        r_forward.rename("r_fwd"),
    ], axis=1, sort=True).dropna()

    if len(dataset) < min_train + 30:
        return {}

    forecasts, actuals = [], []
    for i in range(min_train, len(dataset)):
        train = dataset.iloc[:i]
        X = sm.add_constant(train["wavelet"])
        y = train["r_fwd"]
        try:
            model = sm.OLS(y, X).fit()
            signal = float(dataset["wavelet"].iloc[i])
            fc = float(model.params.iloc[0] + model.params.iloc[1] * signal)
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
    print("ANÁLISIS WAVELET DE LA TRM: SEÑAL POR FRECUENCIA")
    print("=" * 70)

    print("\n[1/4] Cargando datos...")
    data = build_dataset()
    trm = data["trm_cop_usd"].loc[SAMPLE_START:]
    ln_trm = np.log(trm.where(trm > 0)).dropna()
    print(f"  Observaciones: {len(ln_trm)} meses")

    print("\n[2/4] Descomposición wavelet (Daubechies-4, 5 niveles)...")
    components = wavelet_decomposition(ln_trm, wavelet="db4", levels=5)

    print(f"\n  Bandas de frecuencia:")
    print(f"  {'Componente':<20} {'Período':<15} {'Varianza':<12} {'% de variación'}")
    total_var = ln_trm.var()
    for name, comp in components.items():
        var = comp.var()
        pct = var / total_var * 100
        print(f"  {name:<20} {'meses':<15} {var:.6f}     {pct:.1f}%")

    print("\n[3/4] Evaluando poder predictivo OOS por banda (h=12 meses)...")
    results = []
    for name, comp in components.items():
        # Usar componente como señal de desviación
        signal = comp * 100  # escalar a %
        metrics = evaluate_wavelet_signal(signal, ln_trm, horizon=12, min_train=60)
        if metrics:
            metrics["componente"] = name
            results.append(metrics)
            sig = "**" if metrics["dm_p_valor"] < 0.05 else "*" if metrics["dm_p_valor"] < 0.10 else ""
            print(f"  {name:<20} R2OOS={metrics['r2_oos_pct']:>7.2f}%  corr={metrics['correlacion']:.3f}  dir={metrics['direccion_pct']:.1f}%  DM p={metrics['dm_p_valor']:.3f}{sig}")

    # También evaluar combinaciones
    print("\n  Combinaciones de bandas:")
    # D3 + D4 (ciclo medio + largo = 8-32 meses ≈ lo que captura CF)
    if "D3 (8-16m)" in components and "D4 (16-32m)" in components:
        combo_34 = components["D3 (8-16m)"] + components["D4 (16-32m)"]
        m = evaluate_wavelet_signal(combo_34 * 100, ln_trm, horizon=12, min_train=60)
        if m:
            m["componente"] = "D3+D4 (8-32m)"
            results.append(m)
            sig = "**" if m["dm_p_valor"] < 0.05 else "*" if m["dm_p_valor"] < 0.10 else ""
            print(f"  {'D3+D4 (8-32m)':<20} R2OOS={m['r2_oos_pct']:>7.2f}%  corr={m['correlacion']:.3f}  dir={m['direccion_pct']:.1f}%  DM p={m['dm_p_valor']:.3f}{sig}")

    # D3 + D4 + D5 (8-64 meses ≈ CF band)
    if "D5 (32-64m)" in components:
        combo_345 = components["D3 (8-16m)"] + components["D4 (16-32m)"] + components["D5 (32-64m)"]
        m = evaluate_wavelet_signal(combo_345 * 100, ln_trm, horizon=12, min_train=60)
        if m:
            m["componente"] = "D3+D4+D5 (8-64m)"
            results.append(m)
            sig = "**" if m["dm_p_valor"] < 0.05 else "*" if m["dm_p_valor"] < 0.10 else ""
            print(f"  {'D3+D4+D5 (8-64m)':<20} R2OOS={m['r2_oos_pct']:>7.2f}%  corr={m['correlacion']:.3f}  dir={m['direccion_pct']:.1f}%  DM p={m['dm_p_valor']:.3f}{sig}")

    # CF como referencia
    cf_cycle, _ = sm.tsa.filters.cffilter(ln_trm, low=6, high=96)
    m_cf = evaluate_wavelet_signal(cf_cycle * 100, ln_trm, horizon=12, min_train=60)
    if m_cf:
        m_cf["componente"] = "CF filter (6-96m)"
        results.append(m_cf)
        print(f"  {'CF filter (6-96m)':<20} R2OOS={m_cf['r2_oos_pct']:>7.2f}%  corr={m_cf['correlacion']:.3f}  dir={m_cf['direccion_pct']:.1f}%  DM p={m_cf['dm_p_valor']:.3f}**")

    print("\n[4/4] Guardando...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(results).sort_values("r2_oos_pct", ascending=False)
    comparison.to_csv(RESULTS / "wavelets_comparacion_bandas.csv", index=False, encoding="utf-8-sig")

    # Guardar componentes
    comp_df = pd.DataFrame({name: comp for name, comp in components.items()})
    comp_df.index = ln_trm.dropna().index
    comp_df.to_csv(RESULTS / "wavelets_componentes.csv", encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("RANKING: EN QUÉ FRECUENCIA ESTÁ LA SEÑAL")
    print("=" * 70)
    print(comparison[["componente", "r2_oos_pct", "correlacion", "direccion_pct", "dm_p_valor"]].to_string(index=False))
    best = comparison.iloc[0]
    print(f"\n  Mejor banda: {best['componente']}")
    print(f"  La señal está concentrada en períodos de {best['componente'].split('(')[1].split(')')[0] if '(' in best['componente'] else '?'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
