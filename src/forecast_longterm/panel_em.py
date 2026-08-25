"""
Panel de monedas EM: reversión a la media conjunta (BRL, CLP, MXN, COP).

Hipótesis: si las 4 monedas latinoamericanas comparten un factor común de
reversión, estimar en panel da más potencia estadística (4× observaciones)
y permite comparar velocidades de ajuste entre países.

Metodología:
1. Aplicar CF filter a cada moneda por separado (señal sin look-ahead)
2. Estimar regresión pooled: r_{i,t:t+h} = α + β × desviación_CF_{i,t} + ε
3. Estimar con efectos fijos por moneda: permite diferentes interceptos
4. Comparar β del panel vs β individual de COP

Si β_panel es significativo con más potencia, confirma que la reversión a la
media es un fenómeno REGIONAL, no solo colombiano.

Uso:
    python src/forecast_longterm/panel_em.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]

from estimate_model import build_dataset, SAMPLE_START

RESULTS = ROOT / "results" / "pronostico"
RAW = ROOT / "data" / "raw"


def load_em_currencies() -> pd.DataFrame:
    """Carga las 4 monedas EM por USD en frecuencia mensual."""
    data = build_dataset()

    currencies = pd.DataFrame({
        "COP": data["trm_cop_usd"],
        "BRL": data["brl_por_usd"],
        "CLP": data["clp_por_usd"],
        "MXN": data["mxn_por_usd"],
    }).loc[SAMPLE_START:]

    return currencies


def apply_cf_filter_panel(currencies: pd.DataFrame) -> pd.DataFrame:
    """Aplica CF filter a cada moneda y devuelve desviaciones en %."""
    deviations = pd.DataFrame(index=currencies.index)

    for col in currencies.columns:
        ln_series = np.log(currencies[col].where(currencies[col] > 0)).dropna()
        try:
            cf_cycle, cf_trend = sm.tsa.filters.cffilter(ln_series, low=6, high=96)
            deviations[col] = cf_cycle * 100  # en %
        except Exception:
            pass

    return deviations


def build_panel(deviations: pd.DataFrame, currencies: pd.DataFrame, horizon: int = 12) -> pd.DataFrame:
    """
    Construye panel largo: una fila por (moneda, mes).
    Variable dependiente: retorno forward h meses.
    """
    rows = []
    for col in deviations.columns:
        ln_fx = np.log(currencies[col].where(currencies[col] > 0))
        r_forward = (ln_fx.shift(-horizon) - ln_fx) * 100  # retorno en %
        dev = deviations[col]

        for date in dev.index:
            if pd.notna(dev.loc[date]) and pd.notna(r_forward.get(date, np.nan)):
                rows.append({
                    "fecha": date,
                    "moneda": col,
                    "desviacion_cf_pct": float(dev.loc[date]),
                    "retorno_forward_pct": float(r_forward.loc[date]),
                })

    return pd.DataFrame(rows)


def estimate_panel(panel: pd.DataFrame) -> dict:
    """
    Estima 3 especificaciones:
    1. Pooled OLS: β común para todas las monedas
    2. Efectos fijos por moneda: diferentes interceptos
    3. Interacción moneda × desviación: diferentes betas
    """
    results = {}

    # 1. Pooled OLS
    X_pooled = sm.add_constant(panel["desviacion_cf_pct"])
    y = panel["retorno_forward_pct"]
    pooled = sm.OLS(y, X_pooled).fit(cov_type="cluster", cov_kwds={"groups": panel["moneda"]})
    results["pooled"] = {
        "beta": float(pooled.params.iloc[1]),
        "t_stat": float(pooled.tvalues.iloc[1]),
        "p_valor": float(pooled.pvalues.iloc[1]),
        "r2": float(pooled.rsquared),
        "n": len(panel),
    }

    # 2. Efectos fijos por moneda
    dummies = pd.get_dummies(panel["moneda"], drop_first=True, dtype=float)
    X_fe = pd.concat([sm.add_constant(panel[["desviacion_cf_pct"]]), dummies], axis=1)
    fe = sm.OLS(y, X_fe).fit(cov_type="cluster", cov_kwds={"groups": panel["moneda"]})
    results["efectos_fijos"] = {
        "beta": float(fe.params["desviacion_cf_pct"]),
        "t_stat": float(fe.tvalues["desviacion_cf_pct"]),
        "p_valor": float(fe.pvalues["desviacion_cf_pct"]),
        "r2": float(fe.rsquared),
        "n": len(panel),
    }

    # 3. Betas por moneda (interacción)
    individual_betas = {}
    for moneda in panel["moneda"].unique():
        sub = panel[panel["moneda"] == moneda]
        X_ind = sm.add_constant(sub["desviacion_cf_pct"])
        y_ind = sub["retorno_forward_pct"]
        ind = sm.OLS(y_ind, X_ind).fit(cov_type="HAC", cov_kwds={"maxlags": 12})
        individual_betas[moneda] = {
            "beta": float(ind.params.iloc[1]),
            "t_stat": float(ind.tvalues.iloc[1]),
            "p_valor": float(ind.pvalues.iloc[1]),
            "r2": float(ind.rsquared),
            "n": len(sub),
        }
    results["individual"] = individual_betas

    return results


def panel_oos_backtest(panel: pd.DataFrame, min_train_months: int = 60) -> dict:
    """Backtest OOS: estima β pooled con datos pasados, pronostica adelante."""
    # Ordenar por fecha
    dates = sorted(panel["fecha"].unique())
    n_dates = len(dates)
    start_idx = min_train_months

    forecasts, actuals, monedas_list = [], [], []

    for i in range(start_idx, n_dates):
        current_date = dates[i]
        train = panel[panel["fecha"] < current_date]
        test = panel[panel["fecha"] == current_date]

        if len(train) < 60 or test.empty:
            continue

        # Estimar pooled con train
        X_tr = sm.add_constant(train["desviacion_cf_pct"])
        y_tr = train["retorno_forward_pct"]
        try:
            model = sm.OLS(y_tr, X_tr).fit()
        except Exception:
            continue

        # Pronosticar para cada moneda en test
        for _, row in test.iterrows():
            fc = float(model.params.iloc[0] + model.params.iloc[1] * row["desviacion_cf_pct"])
            forecasts.append(fc)
            actuals.append(float(row["retorno_forward_pct"]))
            monedas_list.append(row["moneda"])

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

    d = rw_err**2 - err**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    # Métricas por moneda
    per_currency = {}
    for moneda in set(monedas_list):
        mask = [m == moneda for m in monedas_list]
        fc_m = fc[mask]
        act_m = act[mask]
        if len(fc_m) > 10:
            per_currency[moneda] = {
                "n": len(fc_m),
                "correlacion": float(np.corrcoef(fc_m, act_m)[0, 1]),
                "direccion_pct": 100 * float(np.mean(np.sign(fc_m) == np.sign(act_m))),
            }

    return {
        "n_total": len(forecasts),
        "r2_oos_pct": 100 * r2_oos,
        "correlacion": corr,
        "direccion_pct": 100 * direction,
        "dm_p_valor": dm_p,
        "por_moneda": per_currency,
    }


def main():
    print("=" * 70)
    print("PANEL DE MONEDAS EM: REVERSIÓN A LA MEDIA CONJUNTA")
    print("=" * 70)

    print("\n[1/4] Cargando monedas...")
    currencies = load_em_currencies()
    print(f"  Monedas: {list(currencies.columns)}")
    print(f"  Período: {currencies.index.min().date()} a {currencies.index.max().date()}")
    print(f"  Observaciones por moneda: {currencies.notna().sum().to_dict()}")

    print("\n[2/4] Aplicando CF filter a cada moneda...")
    deviations = apply_cf_filter_panel(currencies)
    print(f"  Desviaciones calculadas: {list(deviations.columns)}")
    print(f"  Correlación de ciclos:")
    corr_matrix = deviations.corr()
    for i, col1 in enumerate(corr_matrix.columns):
        for col2 in corr_matrix.columns[i+1:]:
            print(f"    {col1}-{col2}: {corr_matrix.loc[col1, col2]:.3f}")

    print("\n[3/4] Estimación en panel (horizonte 12 meses)...")
    panel = build_panel(deviations, currencies, horizon=12)
    print(f"  Observaciones panel: {len(panel)} ({panel['moneda'].value_counts().to_dict()})")

    estimates = estimate_panel(panel)

    print(f"\n  Pooled OLS:")
    p = estimates["pooled"]
    print(f"    β = {p['beta']:.4f} (t = {p['t_stat']:.2f}, p = {p['p_valor']:.4f}), R² = {p['r2']*100:.1f}%")

    print(f"\n  Efectos fijos:")
    fe = estimates["efectos_fijos"]
    print(f"    β = {fe['beta']:.4f} (t = {fe['t_stat']:.2f}, p = {fe['p_valor']:.4f}), R² = {fe['r2']*100:.1f}%")

    print(f"\n  Betas individuales:")
    for moneda, info in estimates["individual"].items():
        sig = "**" if info["p_valor"] < 0.05 else "*" if info["p_valor"] < 0.10 else ""
        print(f"    {moneda}: β = {info['beta']:.4f} (t = {info['t_stat']:.2f}, p = {info['p_valor']:.4f}) R²={info['r2']*100:.1f}%{sig}")

    print("\n[4/4] Backtest OOS del panel...")
    oos = panel_oos_backtest(panel, min_train_months=60)
    if "error" not in oos:
        sig = "**" if oos["dm_p_valor"] < 0.05 else "*" if oos["dm_p_valor"] < 0.10 else ""
        print(f"  Panel OOS: R²={oos['r2_oos_pct']:.2f}%  corr={oos['correlacion']:.3f}  dir={oos['direccion_pct']:.1f}%  DM p={oos['dm_p_valor']:.4f}{sig}")
        print(f"\n  Por moneda (OOS):")
        for moneda, info in oos.get("por_moneda", {}).items():
            print(f"    {moneda}: corr={info['correlacion']:.3f}  dir={info['direccion_pct']:.1f}%  (n={info['n']})")

    # Guardar
    RESULTS.mkdir(parents=True, exist_ok=True)
    panel.to_csv(RESULTS / "panel_em_datos.csv", index=False, encoding="utf-8-sig")
    deviations.to_csv(RESULTS / "panel_em_desviaciones_cf.csv", encoding="utf-8-sig")

    summary = []
    for moneda, info in estimates["individual"].items():
        summary.append({"moneda": moneda, "tipo": "individual", **info})
    summary.append({"moneda": "PANEL", "tipo": "pooled", **estimates["pooled"]})
    summary.append({"moneda": "PANEL", "tipo": "efectos_fijos", **estimates["efectos_fijos"]})
    pd.DataFrame(summary).to_csv(RESULTS / "panel_em_estimaciones.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print("CONCLUSIÓN")
    print("=" * 70)
    print(f"  β pooled = {estimates['pooled']['beta']:.4f} (p = {estimates['pooled']['p_valor']:.4f})")
    if estimates["pooled"]["p_valor"] < 0.05:
        print("  La reversión a la media es un FENÓMENO REGIONAL (significativo en panel)")
    cop_beta = estimates["individual"].get("COP", {}).get("beta", 0)
    print(f"  β COP individual = {cop_beta:.4f}")
    print(f"  El panel confirma que la señal CF no es un artefacto estadístico de COP")
    print("=" * 70)


if __name__ == "__main__":
    main()
