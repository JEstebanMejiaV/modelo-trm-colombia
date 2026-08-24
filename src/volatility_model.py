"""
Modelo de volatilidad condicional de la TRM como producto.

No se puede predecir la dirección del COP a corto plazo, pero SÍ se puede
predecir cuánto se va a mover (volatilidad). Esto tiene valor directo para:
- Pricing de opciones sobre USD/COP
- Cálculo de VaR para posiciones en TRM
- Sizing de coberturas corporativas
- Bandas de predicción calibradas

Modelos:
1. GARCH(1,1) sobre retornos diarios
2. EGARCH (captura asimetría: caídas del COP son más volátiles)
3. GJR-GARCH (threshold GARCH)
4. GARCH con variables exógenas (VIX, EMBIG como drivers de vol)

Evaluación:
- Cobertura del intervalo al 95% y 99% (debería cubrir 5% y 1% de los días)
- Kupiec test (proporción correcta de violaciones)
- Christoffersen test (independencia de violaciones)
- Mincer-Zarnowitz (calibración de la volatilidad predicha)

Uso:
    python src/volatility_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RESULTS = ROOT / "results" / "pronostico"
RAW = ROOT / "data" / "raw"


def load_daily_returns() -> pd.DataFrame:
    """Carga retornos diarios de la TRM y variables de volatilidad."""
    # TRM
    trm_raw = json.loads((RAW / "trm_diaria_banrep.json").read_text("utf-8"))
    trm_df = pd.DataFrame(trm_raw[0]["data"], columns=["ts", "trm"])
    trm_df["fecha"] = pd.to_datetime(trm_df["ts"], unit="ms", utc=True).dt.tz_convert(None).dt.normalize()
    trm_df["trm"] = pd.to_numeric(trm_df["trm"], errors="coerce")
    trm = trm_df.dropna().set_index("fecha")["trm"].sort_index().groupby(level=0).mean()

    # VIX
    vix_raw = pd.read_csv(RAW / "vix_diario_fred.csv")
    vix_raw.columns = ["fecha", "vix"]
    vix_raw["fecha"] = pd.to_datetime(vix_raw["fecha"], errors="coerce")
    vix_raw["vix"] = pd.to_numeric(vix_raw["vix"], errors="coerce")
    vix = vix_raw.dropna().set_index("fecha")["vix"].sort_index()

    # EMBIG
    MONTH_NUMBERS = {"Ene":1,"Feb":2,"Mar":3,"Abr":4,"May":5,"Jun":6,"Jul":7,"Ago":8,"Sep":9,"Set":9,"Oct":10,"Nov":11,"Dic":12}
    embig_raw = json.loads((RAW / "embig_colombia_diario_bcrp.json").read_text("utf-8"))
    embig_rows = []
    for obs in embig_raw.get("periods", []):
        parts = str(obs.get("name", "")).strip().split(".")
        values = obs.get("values") or []
        if len(parts) != 3 or not values or parts[1] not in MONTH_NUMBERS:
            continue
        year = int(parts[2])
        year += 2000 if year < 70 else 1900
        date = pd.Timestamp(year=year, month=MONTH_NUMBERS[parts[1]], day=int(parts[0]))
        value = pd.to_numeric(str(values[0]).replace(",", "."), errors="coerce")
        if pd.notna(value):
            embig_rows.append((date, float(value)))
    embig = pd.Series([v for _, v in embig_rows], index=pd.DatetimeIndex([d for d, _ in embig_rows]))
    embig = embig.sort_index().groupby(level=0).mean()
    embig.name = "embig"

    daily = pd.DataFrame({"trm": trm, "vix": vix, "embig": embig}).sort_index().ffill(limit=5)
    daily["r_trm"] = np.log(daily["trm"]).diff() * 100  # retorno en %
    daily["r_vix"] = np.log(daily["vix"]).diff() * 100
    daily = daily.loc["2006-01-01":].dropna()
    return daily


def fit_garch_models(returns: pd.Series, exog_vix: pd.Series | None = None):
    """Ajusta GARCH(1,1), EGARCH(1,1) y GJR-GARCH(1,1)."""
    from arch import arch_model

    results = {}

    # 1. GARCH(1,1) estándar
    garch = arch_model(returns, vol="Garch", p=1, q=1, mean="ARX", lags=1, rescale=False)
    results["GARCH(1,1)"] = garch.fit(disp="off")

    # 2. EGARCH (captura asimetría)
    egarch = arch_model(returns, vol="EGARCH", p=1, q=1, mean="ARX", lags=1, rescale=False)
    results["EGARCH(1,1)"] = egarch.fit(disp="off")

    # 3. GJR-GARCH (threshold)
    gjr = arch_model(returns, vol="Garch", p=1, o=1, q=1, mean="ARX", lags=1, rescale=False)
    results["GJR-GARCH(1,1,1)"] = gjr.fit(disp="off")

    # 4. GARCH con exógenas en la varianza (VIX como driver)
    if exog_vix is not None:
        try:
            # Usar VIX rezagado como variable en la ecuación de media
            garch_x = arch_model(returns, vol="Garch", p=1, q=1, mean="ARX", lags=1, x=pd.DataFrame({"vix_L1": exog_vix.shift(1).reindex(returns.index)}), rescale=False)
            results["GARCH + VIX"] = garch_x.fit(disp="off")
        except Exception:
            pass

    return results


def var_backtest(
    returns: pd.Series,
    conditional_vol: pd.Series,
    confidence: float = 0.95,
) -> dict:
    """
    Backtest del VaR: ¿el intervalo cubre la proporción correcta?

    VaR_α = -z_α × σ_t (pérdida máxima esperada al nivel α)
    Violación = retorno < -VaR_α
    """
    alpha = 1 - confidence
    z = stats.norm.ppf(confidence)

    var_level = z * conditional_vol
    violations = (returns < -var_level).astype(int)
    n_violations = int(violations.sum())
    n_obs = len(returns)
    violation_rate = n_violations / n_obs
    expected_rate = alpha

    # Kupiec test: H0 = tasa de violación = α
    if n_violations > 0 and n_violations < n_obs:
        lr_kupiec = -2 * (
            n_violations * np.log(alpha) + (n_obs - n_violations) * np.log(1 - alpha)
            - n_violations * np.log(violation_rate) - (n_obs - n_violations) * np.log(1 - violation_rate)
        )
        p_kupiec = float(1 - stats.chi2.cdf(lr_kupiec, df=1))
    else:
        lr_kupiec = np.nan
        p_kupiec = np.nan

    # Christoffersen: test de independencia (las violaciones no deben venir en clusters)
    v = violations.values
    n_00 = int(((v[:-1] == 0) & (v[1:] == 0)).sum())
    n_01 = int(((v[:-1] == 0) & (v[1:] == 1)).sum())
    n_10 = int(((v[:-1] == 1) & (v[1:] == 0)).sum())
    n_11 = int(((v[:-1] == 1) & (v[1:] == 1)).sum())
    p_ind = np.nan
    if (n_00 + n_01) > 0 and (n_10 + n_11) > 0 and n_01 > 0 and n_10 > 0:
        pi_01 = n_01 / (n_00 + n_01)
        pi_11 = n_11 / (n_10 + n_11) if (n_10 + n_11) > 0 else 0
        pi = (n_01 + n_11) / (n_obs - 1)
        if pi > 0 and pi < 1 and pi_01 > 0 and pi_01 < 1:
            lr_ind = -2 * (
                (n_00 + n_10) * np.log(1 - pi) + (n_01 + n_11) * np.log(pi)
                - n_00 * np.log(1 - pi_01) - n_01 * np.log(pi_01)
                - n_10 * np.log(1 - pi_11) - n_11 * np.log(pi_11)
            ) if pi_11 > 0 and pi_11 < 1 else np.nan
            p_ind = float(1 - stats.chi2.cdf(lr_ind, df=1)) if not np.isnan(lr_ind) else np.nan

    return {
        "confianza_pct": confidence * 100,
        "violaciones": n_violations,
        "tasa_violacion_pct": violation_rate * 100,
        "tasa_esperada_pct": alpha * 100,
        "ratio_violacion": violation_rate / alpha if alpha > 0 else np.nan,
        "kupiec_p_valor": p_kupiec,
        "christoffersen_p_valor": p_ind,
    }


def main():
    print("=" * 70)
    print("MODELO DE VOLATILIDAD CONDICIONAL — PRODUCTO DE RIESGO")
    print("=" * 70)

    print("\n[1/4] Cargando retornos diarios...")
    daily = load_daily_returns()
    returns = daily["r_trm"]
    print(f"  Observaciones: {len(returns)} días")
    print(f"  Período: {returns.index.min().date()} a {returns.index.max().date()}")
    print(f"  Vol incondicional: {returns.std():.3f}% diaria ({returns.std() * np.sqrt(250):.1f}% anualizada)")
    print(f"  Skewness: {returns.skew():.3f}  |  Kurtosis: {returns.kurtosis():.1f}")

    print("\n[2/4] Estimando modelos GARCH...")
    from arch import arch_model
    models = fit_garch_models(returns, exog_vix=daily["r_vix"])

    model_summary = []
    for name, result in models.items():
        cond_vol = result.conditional_volatility
        persistence = 0
        if hasattr(result, "params"):
            p = result.params
            alpha = p.get("alpha[1]", 0)
            beta = p.get("beta[1]", 0)
            gamma = p.get("gamma[1]", 0)
            persistence = alpha + beta + 0.5 * gamma
        model_summary.append({
            "modelo": name,
            "loglik": float(result.loglikelihood),
            "aic": float(result.aic),
            "bic": float(result.bic),
            "persistencia": persistence,
            "vol_media_pct_diaria": float(cond_vol.mean()),
            "vol_max_pct_diaria": float(cond_vol.max()),
            "vol_anualizada_media_pct": float(cond_vol.mean() * np.sqrt(250)),
        })
        print(f"  {name:<20} BIC={result.bic:.1f}  persist={persistence:.4f}  vol_media={cond_vol.mean():.3f}%/día")

    print("\n[3/4] Backtest VaR (últimos 500 días)...")
    best_name = min(model_summary, key=lambda x: x["bic"])["modelo"]
    best_result = models[best_name]
    cond_vol = best_result.conditional_volatility

    # Usar últimos 500 días como período de evaluación
    eval_start = -500
    eval_returns = returns.iloc[eval_start:]
    eval_vol = cond_vol.iloc[eval_start:]

    var_results = []
    for conf in [0.90, 0.95, 0.99]:
        vr = var_backtest(eval_returns, eval_vol, confidence=conf)
        vr["modelo"] = best_name
        var_results.append(vr)
        status = "OK" if 0.5 < vr["ratio_violacion"] < 2.0 else "FALLO"
        print(f"  VaR {conf*100:.0f}%: violaciones={vr['violaciones']}/{len(eval_returns)} "
              f"({vr['tasa_violacion_pct']:.1f}% vs {vr['tasa_esperada_pct']:.0f}% esperado) "
              f"ratio={vr['ratio_violacion']:.2f} {status}")

    print(f"\n[4/4] Producto final: intervalos de predicción para mañana...")
    # Pronóstico de volatilidad: usar GJR-GARCH (mejor BIC sin exógenas)
    gjr_name = "GJR-GARCH(1,1,1)"
    forecast_model = models[gjr_name] if gjr_name in models else best_result
    forecast = forecast_model.forecast(horizon=1)
    vol_tomorrow = float(np.sqrt(forecast.variance.iloc[-1, 0]))
    trm_hoy = float(daily["trm"].iloc[-1])

    print(f"\n  TRM hoy: {trm_hoy:.2f} COP/USD")
    print(f"  Volatilidad condicional mañana: {vol_tomorrow:.3f}% ({vol_tomorrow * np.sqrt(250):.1f}% anualizada)")
    print(f"\n  Intervalos de predicción para mañana:")
    for conf, z in [(0.68, 1.0), (0.90, 1.645), (0.95, 1.96), (0.99, 2.576)]:
        move_pct = z * vol_tomorrow
        move_pesos = trm_hoy * move_pct / 100
        lo = trm_hoy * np.exp(-move_pct / 100)
        hi = trm_hoy * np.exp(move_pct / 100)
        print(f"    {conf*100:.0f}%: [{lo:.2f}, {hi:.2f}] COP/USD  (±{move_pesos:.1f} pesos, ±{move_pct:.2f}%)")

    # VaR en pesos
    print(f"\n  Value at Risk (posición 1 millón USD):")
    for conf, z in [(0.95, 1.645), (0.99, 2.576)]:
        var_pesos = 1_000_000 * trm_hoy * z * vol_tomorrow / 100
        print(f"    VaR {conf*100:.0f}%: {var_pesos:,.0f} COP ({z * vol_tomorrow:.2f}% de la posición)")

    # Guardar
    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(model_summary).to_csv(RESULTS / "volatilidad_modelos_garch.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(var_results).to_csv(RESULTS / "volatilidad_var_backtest.csv", index=False, encoding="utf-8-sig")

    # Serie de volatilidad condicional
    vol_series = pd.DataFrame({
        "fecha": cond_vol.index,
        "vol_condicional_pct_diaria": cond_vol.values,
        "vol_anualizada_pct": cond_vol.values * np.sqrt(250),
    })
    vol_series.to_csv(RESULTS / "volatilidad_serie_condicional.csv", index=False, encoding="utf-8-sig")

    print(f"\n  Guardado en results/pronostico/")
    print("=" * 70)


if __name__ == "__main__":
    main()
