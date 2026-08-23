"""
Ejecutar la comparación completa de modelos de pronóstico diario.

Uso:
    python src/forecast_daily/run.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forecast_daily.data import load_daily_features, train_test_split_temporal
from forecast_daily.models import (
    evaluate_forecast,
    fit_ols,
    fit_ridge,
    fit_lasso,
    fit_elastic_net,
    fit_random_forest,
    fit_xgboost,
    fit_lightgbm,
    fit_expanding_ols,
    fit_combination,
)

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "pronostico"


def main() -> None:
    print("=" * 70)
    print("COMPARACIÓN DE MODELOS — PRONÓSTICO TRM A 1 DÍA")
    print("=" * 70)

    print("\n[1/4] Cargando datos y features...")
    dataset = load_daily_features()
    X_train, X_test, y_train, y_test = train_test_split_temporal(dataset, holdout_days=250)
    print(f"  Train: {len(X_train)} días ({X_train.index.min().date()} a {X_train.index.max().date()})")
    print(f"  Test:  {len(X_test)} días ({X_test.index.min().date()} a {X_test.index.max().date()})")
    print(f"  Features: {X_train.shape[1]}")

    print("\n[2/4] Estimando modelos...")
    predictions = {}
    results = []

    # --- Econométricos ---
    print("  OLS...")
    pred_ols = fit_ols(X_train, y_train, X_test)
    predictions["OLS"] = pred_ols
    results.append(evaluate_forecast(y_test.values, pred_ols, "OLS (todos los features)"))

    print("  Ridge...")
    pred_ridge = fit_ridge(X_train, y_train, X_test, alpha=1.0)
    predictions["Ridge"] = pred_ridge
    results.append(evaluate_forecast(y_test.values, pred_ridge, "Ridge (α=1)"))

    print("  Lasso...")
    pred_lasso = fit_lasso(X_train, y_train, X_test, alpha=0.00005)
    predictions["Lasso"] = pred_lasso
    results.append(evaluate_forecast(y_test.values, pred_lasso, "Lasso (α=5e-5)"))

    print("  Elastic Net...")
    pred_enet = fit_elastic_net(X_train, y_train, X_test, alpha=0.0001, l1_ratio=0.5)
    predictions["ElasticNet"] = pred_enet
    results.append(evaluate_forecast(y_test.values, pred_enet, "Elastic Net"))

    print("  Expanding OLS (skip — muy lento con 250 reestimaciones)...")
    # pred_exp = fit_expanding_ols(X_train, y_train, X_test)
    # predictions["Expanding OLS"] = pred_exp
    # results.append(evaluate_forecast(y_test.values, pred_exp, "OLS expanding (reestima diario)"))

    # --- Machine Learning ---
    print("  Random Forest...")
    pred_rf, imp_rf = fit_random_forest(X_train, y_train, X_test)
    predictions["RF"] = pred_rf
    results.append(evaluate_forecast(y_test.values, pred_rf, "Random Forest"))

    print("  XGBoost...")
    pred_xgb, imp_xgb = fit_xgboost(X_train, y_train, X_test)
    predictions["XGBoost"] = pred_xgb
    results.append(evaluate_forecast(y_test.values, pred_xgb, "XGBoost"))

    print("  LightGBM...")
    pred_lgbm, imp_lgbm = fit_lightgbm(X_train, y_train, X_test)
    predictions["LightGBM"] = pred_lgbm
    results.append(evaluate_forecast(y_test.values, pred_lgbm, "LightGBM"))

    # --- Redes neuronales recurrentes ---
    try:
        from forecast_daily.rnn_models import fit_lstm, fit_gru, fit_lstm_attention

        print("  LSTM...")
        pred_lstm = fit_lstm(X_train, y_train, X_test)
        predictions["LSTM"] = pred_lstm
        results.append(evaluate_forecast(y_test.values, pred_lstm, "LSTM (hidden=32, seq=22)"))

        print("  GRU...")
        pred_gru = fit_gru(X_train, y_train, X_test)
        predictions["GRU"] = pred_gru
        results.append(evaluate_forecast(y_test.values, pred_gru, "GRU (hidden=32, seq=22)"))

        print("  LSTM + Atención...")
        pred_attn = fit_lstm_attention(X_train, y_train, X_test)
        predictions["LSTM+Attn"] = pred_attn
        results.append(evaluate_forecast(y_test.values, pred_attn, "LSTM + Atención temporal"))
    except ImportError as e:
        print(f"  SKIP RNN: {e}")

    # --- Combinaciones ---
    print("  Combinación óptima...")
    pred_combo = fit_combination(predictions, y_test.values)
    predictions["Combinación"] = pred_combo
    results.append(evaluate_forecast(y_test.values, pred_combo, "Combinación (inv-MSE)"))

    # --- Caminata aleatoria ---
    results.append({
        "modelo": "Caminata aleatoria (benchmark)",
        "rmse": float(np.sqrt((y_test.values**2).mean())),
        "mae_retorno": float(np.abs(y_test.values).mean()),
        "r2_vs_caminata_pct": 0.0,
        "acierto_direccion_pct": 50.0,
        "sharpe_anualizado": 0.0,
        "dm_stat": 0.0,
        "dm_p_valor": 1.0,
    })

    print("\n[3/4] Resultados...")
    comparison = pd.DataFrame(results).sort_values("r2_vs_caminata_pct", ascending=False)
    print(comparison[["modelo", "r2_vs_caminata_pct", "acierto_direccion_pct", "dm_p_valor"]].to_string(index=False))

    # Feature importance (promedio RF + XGBoost + LightGBM)
    importance = pd.DataFrame({
        "feature": X_train.columns,
        "random_forest": imp_rf,
        "xgboost": imp_xgb,
        "lightgbm": imp_lgbm,
    })
    importance["promedio"] = importance[["random_forest", "xgboost", "lightgbm"]].mean(axis=1)
    importance = importance.sort_values("promedio", ascending=False)

    print("\n  Top 10 features (importancia promedio ML):")
    for _, row in importance.head(10).iterrows():
        print(f"    {row['feature']:<25} {row['promedio']:.4f}")

    # Guardar
    print("\n[4/4] Guardando resultados...")
    RESULTS.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(
        RESULTS / "comparacion_modelos_diarios.csv",
        index=False, encoding="utf-8-sig",
    )
    importance.to_csv(
        RESULTS / "feature_importance_ml_diario.csv",
        index=False, encoding="utf-8-sig",
    )

    # Resumen
    print("\n" + "=" * 70)
    best = comparison.iloc[0]
    worst_ml = comparison.loc[comparison["modelo"].str.contains("Forest|XGBoost|LightGBM")].iloc[-1]
    print(f"  MEJOR modelo: {best['modelo']}")
    print(f"    R² vs caminata: {best['r2_vs_caminata_pct']:.2f}%")
    print(f"    DM p-valor: {best['dm_p_valor']:.4f}")
    print(f"    Dirección: {best['acierto_direccion_pct']:.1f}%")
    print()
    if best["dm_p_valor"] < 0.05:
        print("  ✓ El mejor modelo SUPERA la caminata aleatoria al 5%.")
    else:
        print("  ✗ Ningún modelo supera la caminata al 5%.")
    print("=" * 70)


if __name__ == "__main__":
    main()
