"""
Modelo de pronóstico de la TRM a corto plazo (diario/semanal).

Estrategia: usar datos diarios de las 3 variables que se publican en tiempo real
(dólar amplio, VIX, EMBIG) como predictores del cambio de la TRM del día siguiente.

La ventaja sobre el modelo mensual:
- Frecuencia diaria → más observaciones (5000+)
- Los factores globales se conocen ANTES del cierre de la TRM
- El VIX y el dólar amplio se mueven antes que la TRM colombiana (diferencia horaria)

Modelos implementados:
1. AR(1): Δln(TRM)_t = c + φ·Δln(TRM)_{t-1} + ε
2. AR(1) + dólar: + β·Δln(dólar)_{t-1}
3. HAR (Heterogeneous AR): rezagos 1d, 5d, 22d
4. HAR + factores globales: dólar + VIX + EMBIG rezagados 1 día
5. HAR + factores + volatilidad realizada

Evaluación: pseudo-out-of-sample con ventana expanding de los últimos 250 días (~1 año).

Uso:
    python src/forecast_short_term.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results" / "pronostico"


# ─────────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS DIARIOS
# ─────────────────────────────────────────────────────────────────────────────


def load_monthly_global_features(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Construye señales mensuales globales rezagadas para el modelo diario.

    Las variables mensuales no se imputan contemporáneamente: cada día del mes
    usa únicamente el último promedio mensual disponible (t-1). Así se evita
    convertir una observación mensual revisada en información intradía.
    """
    path = ROOT / "data" / "base_global_mensual.csv"
    raw = pd.read_csv(path, parse_dates=["fecha"]).set_index("fecha").sort_index()
    raw.index = raw.index.to_period("M").to_timestamp()
    raw = raw.groupby(level=0).mean()

    features = pd.DataFrame(index=raw.index)
    rate_columns = [
        "yield_real_10y_tips_pct",
        "yield_2y_us_pct",
        "yield_10y_us_pct",
        "spread_10y_2y_us_pct",
    ]
    features["global_rates_mom"] = raw[rate_columns].diff().mean(axis=1)
    features["global_commodities_mom"] = (
        np.log(raw["brent_usd_barril"].where(raw["brent_usd_barril"] > 0)).diff()
        + np.log(raw["commodities_index_imf"].where(raw["commodities_index_imf"] > 0)).diff()
    ) / 2.0
    features["global_risk_mom"] = (
        np.log(raw["epu_global"].where(raw["epu_global"] > 0)).diff()
        + raw["estres_financiero_stl"].diff()
    ) / 2.0
    features["global_activity_mom"] = (
        np.log(raw["empleo_manufactura_us_miles"].where(raw["empleo_manufactura_us_miles"] > 0)).diff()
        + np.log(raw["produccion_industrial_us"].where(raw["produccion_industrial_us"] > 0)).diff()
    ) / 2.0

    # El valor mensual t solo puede alimentar días de t+1 en el pronóstico.
    lagged = features.shift(1)
    return lagged.reindex(index, method="ffill")


def load_daily_data() -> pd.DataFrame:
    """Carga y alinea las series diarias disponibles."""
    # TRM diaria
    trm_raw = json.loads((RAW / "trm_diaria_banrep.json").read_text("utf-8"))
    trm_df = pd.DataFrame(trm_raw[0]["data"], columns=["ts", "trm"])
    trm_df["fecha"] = pd.to_datetime(trm_df["ts"], unit="ms", utc=True).dt.tz_convert(None).dt.normalize()
    trm_df["trm"] = pd.to_numeric(trm_df["trm"], errors="coerce")
    trm = trm_df.dropna().set_index("fecha")["trm"].sort_index()
    trm = trm.groupby(level=0).mean()

    # Dólar amplio diario (DTWEXBGS)
    dolar_raw = pd.read_csv(RAW / "dolar_amplio_diario_fred.csv")
    dolar_raw.columns = ["fecha", "dolar"]
    dolar_raw["fecha"] = pd.to_datetime(dolar_raw["fecha"], errors="coerce")
    dolar_raw["dolar"] = pd.to_numeric(dolar_raw["dolar"], errors="coerce")
    dolar = dolar_raw.dropna().set_index("fecha")["dolar"].sort_index()

    # VIX diario (VIXCLS)
    vix_raw = pd.read_csv(RAW / "vix_diario_fred.csv")
    vix_raw.columns = ["fecha", "vix"]
    vix_raw["fecha"] = pd.to_datetime(vix_raw["fecha"], errors="coerce")
    vix_raw["vix"] = pd.to_numeric(vix_raw["vix"], errors="coerce")
    vix = vix_raw.dropna().set_index("fecha")["vix"].sort_index()

    # EMBIG Colombia diario
    embig_raw = json.loads((RAW / "embig_colombia_diario_bcrp.json").read_text("utf-8"))
    MONTH_NUMBERS = {"Ene":1,"Feb":2,"Mar":3,"Abr":4,"May":5,"Jun":6,"Jul":7,"Ago":8,"Sep":9,"Set":9,"Oct":10,"Nov":11,"Dic":12}
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
    embig = pd.Series(
        [v for _, v in embig_rows],
        index=pd.DatetimeIndex([d for d, _ in embig_rows]),
        name="embig_pb",
    ).sort_index().groupby(level=0).mean()

    # Combinar con forward fill para alinear calendarios
    daily = pd.DataFrame({
        "trm": trm,
        "dolar": dolar,
        "vix": vix,
        "embig_pb": embig,
    }).sort_index()
    daily = daily.join(load_monthly_global_features(daily.index), how="left")

    # Forward fill para cubrir feriados locales (máx 5 días)
    daily = daily.ffill(limit=5)

    # Calcular retornos logarítmicos
    daily["r_trm"] = np.log(daily["trm"]).diff()
    daily["r_dolar"] = np.log(daily["dolar"]).diff()
    daily["r_vix"] = np.log(daily["vix"]).diff()
    daily["d_embig"] = daily["embig_pb"].diff() / 100  # cambio en pp

    # Volatilidad realizada (rolling 5 días)
    daily["rv_5d"] = daily["r_trm"].rolling(5).std()
    daily["rv_22d"] = daily["r_trm"].rolling(22).std()

    # Promedios HAR
    daily["r_trm_5d"] = daily["r_trm"].rolling(5).mean()
    daily["r_trm_22d"] = daily["r_trm"].rolling(22).mean()

    return daily.loc["2006-01-01":].dropna()


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS DE PRONÓSTICO
# ─────────────────────────────────────────────────────────────────────────────


def build_designs(daily: pd.DataFrame) -> dict[str, tuple[pd.Series, pd.DataFrame]]:
    """Construye los diseños de regresión para cada modelo candidato."""
    y = daily["r_trm"].copy()
    designs = {}

    # 1. AR(1): solo retorno rezagado
    x_ar1 = pd.DataFrame({
        "const": 1.0,
        "r_trm_L1": daily["r_trm"].shift(1),
    }, index=daily.index)
    designs["AR(1)"] = (y, x_ar1)

    # 2. AR(1) + dólar
    x_ar_dolar = pd.DataFrame({
        "const": 1.0,
        "r_trm_L1": daily["r_trm"].shift(1),
        "r_dolar_L1": daily["r_dolar"].shift(1),
    }, index=daily.index)
    designs["AR(1) + dólar"] = (y, x_ar_dolar)

    # 3. HAR (Heterogeneous Autoregressive)
    x_har = pd.DataFrame({
        "const": 1.0,
        "r_trm_L1": daily["r_trm"].shift(1),
        "r_trm_5d_L1": daily["r_trm_5d"].shift(1),
        "r_trm_22d_L1": daily["r_trm_22d"].shift(1),
    }, index=daily.index)
    designs["HAR"] = (y, x_har)

    # 4. HAR + factores globales
    x_har_global = pd.DataFrame({
        "const": 1.0,
        "r_trm_L1": daily["r_trm"].shift(1),
        "r_trm_5d_L1": daily["r_trm_5d"].shift(1),
        "r_trm_22d_L1": daily["r_trm_22d"].shift(1),
        "r_dolar_L1": daily["r_dolar"].shift(1),
        "r_vix_L1": daily["r_vix"].shift(1),
        "d_embig_L1": daily["d_embig"].shift(1),
        "global_rates_mom_L1": daily["global_rates_mom"].shift(1),
        "global_commodities_mom_L1": daily["global_commodities_mom"].shift(1),
        "global_risk_mom_L1": daily["global_risk_mom"].shift(1),
        "global_activity_mom_L1": daily["global_activity_mom"].shift(1),
    }, index=daily.index)
    designs["HAR + globales mensuales"] = (y, x_har_global)

    # 5. HAR + globales + volatilidad realizada
    x_full = pd.DataFrame({
        "const": 1.0,
        "r_trm_L1": daily["r_trm"].shift(1),
        "r_trm_5d_L1": daily["r_trm_5d"].shift(1),
        "r_trm_22d_L1": daily["r_trm_22d"].shift(1),
        "r_dolar_L1": daily["r_dolar"].shift(1),
        "r_vix_L1": daily["r_vix"].shift(1),
        "d_embig_L1": daily["d_embig"].shift(1),
        "global_rates_mom_L1": daily["global_rates_mom"].shift(1),
        "global_commodities_mom_L1": daily["global_commodities_mom"].shift(1),
        "global_risk_mom_L1": daily["global_risk_mom"].shift(1),
        "global_activity_mom_L1": daily["global_activity_mom"].shift(1),
        "rv_5d_L1": daily["rv_5d"].shift(1),
    }, index=daily.index)
    designs["HAR + globales mensuales + vol"] = (y, x_full)

    return designs


def expanding_backtest(
    y: pd.Series,
    x: pd.DataFrame,
    holdout: int = 250,
) -> dict:
    """Backtest expanding window: estima hasta t-1, pronostica t."""
    common = pd.concat([y, x], axis=1).dropna()
    y_clean = common.iloc[:, 0]
    x_clean = common.iloc[:, 1:]
    n = len(y_clean)

    if n < holdout + 100:
        return {"error": "muestra insuficiente"}

    split = n - holdout
    forecasts = []
    actuals = []

    for i in range(split, n):
        model = sm.OLS(y_clean.iloc[:i], x_clean.iloc[:i]).fit()
        fc = float(model.predict(x_clean.iloc[[i]]).iloc[0])
        forecasts.append(fc)
        actuals.append(float(y_clean.iloc[i]))

    forecasts = np.array(forecasts)
    actuals = np.array(actuals)
    errors = forecasts - actuals

    # Caminata aleatoria: pronóstico = 0 (sin cambio)
    rw_errors = -actuals  # pronosticar 0

    mse_model = float((errors**2).mean())
    mse_rw = float((rw_errors**2).mean())
    r2_vs_rw = 1.0 - mse_model / mse_rw

    # Dirección
    direction_hit = float(np.mean(np.sign(forecasts) == np.sign(actuals)))

    # Rentabilidad de una estrategia simple: comprar COP si pronóstico < 0
    # (si predice apreciación, comprar COP = vender USD)
    strategy_returns = -np.sign(forecasts) * actuals  # posición × retorno
    sharpe = float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(250))

    # DM test
    d = rw_errors**2 - errors**2  # positivo si modelo es mejor
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d))))
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    return {
        "observaciones_backtest": holdout,
        "rmse_modelo": float(np.sqrt(mse_model)),
        "rmse_caminata": float(np.sqrt(mse_rw)),
        "r2_vs_caminata_pct": 100 * r2_vs_rw,
        "acierto_direccion_pct": 100 * direction_hit,
        "sharpe_estrategia_diaria": sharpe,
        "dm_stat": dm_stat,
        "dm_p_valor": dm_p,
    }


# ─────────────────────────────────────────────────────────────────────────────
# HORIZONTE SEMANAL (5 DÍAS)
# ─────────────────────────────────────────────────────────────────────────────


def weekly_backtest(daily: pd.DataFrame, holdout_weeks: int = 52) -> dict:
    """Pronóstico a 5 días hábiles usando el modelo HAR + globales."""
    # Variable dependiente: retorno semanal
    weekly_return = daily["r_trm"].rolling(5).sum().shift(-4)  # r_{t:t+4}

    x = pd.DataFrame({
        "const": 1.0,
        "r_trm_L1": daily["r_trm"].shift(1),
        "r_trm_5d_L1": daily["r_trm_5d"].shift(1),
        "r_trm_22d_L1": daily["r_trm_22d"].shift(1),
        "r_dolar_L1": daily["r_dolar"].shift(1),
        "r_vix_L1": daily["r_vix"].shift(1),
        "d_embig_L1": daily["d_embig"].shift(1),
        "global_rates_mom_L1": daily["global_rates_mom"].shift(1),
        "global_commodities_mom_L1": daily["global_commodities_mom"].shift(1),
        "global_risk_mom_L1": daily["global_risk_mom"].shift(1),
        "global_activity_mom_L1": daily["global_activity_mom"].shift(1),
        "rv_5d_L1": daily["rv_5d"].shift(1),
    }, index=daily.index)

    common = pd.concat([weekly_return.rename("y"), x], axis=1).dropna()
    y_clean = common["y"]
    x_clean = common.drop(columns="y")

    holdout = holdout_weeks * 5
    n = len(y_clean)
    split = n - holdout

    forecasts = []
    actuals = []
    for i in range(split, n, 5):  # cada 5 días
        if i >= n:
            break
        model = sm.OLS(y_clean.iloc[:i], x_clean.iloc[:i]).fit()
        fc = float(model.predict(x_clean.iloc[[i]]).iloc[0])
        forecasts.append(fc)
        actuals.append(float(y_clean.iloc[i]))

    forecasts = np.array(forecasts)
    actuals = np.array(actuals)
    errors = forecasts - actuals
    rw_errors = -actuals

    mse_model = float((errors**2).mean())
    mse_rw = float((rw_errors**2).mean())

    return {
        "horizonte": "5 días (semanal)",
        "semanas_backtest": len(forecasts),
        "rmse_modelo": float(np.sqrt(mse_model)),
        "rmse_caminata": float(np.sqrt(mse_rw)),
        "r2_vs_caminata_pct": 100 * (1 - mse_model / mse_rw),
        "acierto_direccion_pct": 100 * float(np.mean(np.sign(forecasts) == np.sign(actuals))),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print("=" * 70)
    print("MODELO DE PRONÓSTICO TRM — CORTO PLAZO (DIARIO/SEMANAL)")
    print("=" * 70)

    print("\n[1/4] Cargando datos diarios...")
    daily = load_daily_data()
    print(f"  Observaciones: {len(daily)}")
    print(f"  Período: {daily.index.min().date()} a {daily.index.max().date()}")

    print("\n[2/4] Backtest diario (últimos 250 días hábiles)...")
    designs = build_designs(daily)
    results = []
    for name, (y, x) in designs.items():
        result = expanding_backtest(y, x, holdout=250)
        result["modelo"] = name
        result["parametros"] = x.shape[1]
        results.append(result)
        r2 = result.get("r2_vs_caminata_pct", 0)
        dir_pct = result.get("acierto_direccion_pct", 0)
        sharpe = result.get("sharpe_estrategia_diaria", 0)
        dm_p = result.get("dm_p_valor", 1)
        sig = "***" if dm_p < 0.01 else "**" if dm_p < 0.05 else "*" if dm_p < 0.10 else ""
        print(f"  {name:<25} R²={r2:>6.2f}%  Dir={dir_pct:.1f}%  Sharpe={sharpe:.2f}  DM p={dm_p:.3f}{sig}")

    # Caminata aleatoria como referencia
    results.append({
        "modelo": "Caminata aleatoria",
        "parametros": 0,
        "observaciones_backtest": 250,
        "rmse_modelo": results[0]["rmse_caminata"],
        "rmse_caminata": results[0]["rmse_caminata"],
        "r2_vs_caminata_pct": 0.0,
        "acierto_direccion_pct": 50.0,
        "sharpe_estrategia_diaria": 0.0,
        "dm_stat": 0.0,
        "dm_p_valor": 1.0,
    })

    print("\n[3/4] Backtest semanal (últimas 52 semanas)...")
    weekly = weekly_backtest(daily, holdout_weeks=52)
    print(f"  HAR + globales + vol (5 días): R²={weekly['r2_vs_caminata_pct']:.2f}%  Dir={weekly['acierto_direccion_pct']:.1f}%")

    print("\n[4/4] Guardando resultados...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    comparison = pd.DataFrame(results)
    comparison.to_csv(
        RESULTS / "pronostico_corto_plazo_diario.csv",
        index=False, encoding="utf-8-sig",
    )
    pd.DataFrame([weekly]).to_csv(
        RESULTS / "pronostico_corto_plazo_semanal.csv",
        index=False, encoding="utf-8-sig",
    )

    # Coeficientes del mejor modelo
    best_name = comparison.loc[comparison["modelo"] != "Caminata aleatoria"].sort_values("r2_vs_caminata_pct", ascending=False).iloc[0]["modelo"]
    y_best, x_best = designs[best_name]
    common = pd.concat([y_best, x_best], axis=1).dropna()
    full_model = sm.OLS(common.iloc[:, 0], common.iloc[:, 1:]).fit()
    robust = full_model.get_robustcov_results(cov_type="HAC", maxlags=10, use_correction=True)
    coef_df = pd.DataFrame({
        "termino": common.columns[1:],
        "coeficiente": robust.params,
        "error_estandar_hac": robust.bse,
        "t_stat": robust.tvalues,
        "p_valor": robust.pvalues,
    })
    coef_df.to_csv(
        RESULTS / "coeficientes_pronostico_corto_plazo.csv",
        index=False, encoding="utf-8-sig",
    )

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    best = comparison.loc[comparison["r2_vs_caminata_pct"].idxmax()]
    print(f"  Mejor modelo diario: {best['modelo']}")
    print(f"  R² vs caminata: {best['r2_vs_caminata_pct']:.2f}%")
    print(f"  Acierto de dirección: {best['acierto_direccion_pct']:.1f}%")
    print(f"  Sharpe anualizado: {best['sharpe_estrategia_diaria']:.2f}")
    print(f"  Diebold-Mariano: p = {best['dm_p_valor']:.4f}")
    if best["dm_p_valor"] < 0.05:
        print("  → SUPERA la caminata aleatoria al 5%")
    else:
        print("  → NO supera la caminata al 5%")
    print(f"\n  Mejor modelo semanal: HAR + globales + vol")
    print(f"  R² vs caminata semanal: {weekly['r2_vs_caminata_pct']:.2f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
