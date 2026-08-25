"""
Optimización de hiperparámetros de LightGBM para pronóstico diario TRM.

Usa TimeSeriesSplit (5 folds temporales) con búsqueda aleatoria (100 trials).

Uso:
    python src/forecast_daily/optimize_lightgbm.py
"""
from __future__ import annotations

from pathlib import Path
import json

import numpy as np
import pandas as pd

from forecast_daily.data import load_daily_features, train_test_split_temporal
from forecast_daily.models import evaluate_forecast

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results" / "pronostico"


def time_series_cv(X, y, params, n_splits=5):
    """Cross-validation temporal."""
    from lightgbm import LGBMRegressor

    n = len(X)
    fold_size = n // (n_splits + 1)
    scores = []

    for i in range(n_splits):
        train_end = fold_size * (i + 2)
        val_start = train_end
        val_end = min(train_end + fold_size, n)
        if val_end <= val_start:
            continue

        model = LGBMRegressor(**params, random_state=42, verbose=-1)
        model.fit(X.iloc[:train_end], y.iloc[:train_end])
        pred = model.predict(X.iloc[val_start:val_end])
        mse = float(((pred - y.iloc[val_start:val_end].values) ** 2).mean())
        scores.append(mse)

    return np.mean(scores) if scores else float("inf")


def main():
    print("=" * 70)
    print("OPTIMIZACIÓN DE LIGHTGBM — PRONÓSTICO DIARIO TRM")
    print("=" * 70)

    print("\n[1/3] Cargando datos...")
    dataset = load_daily_features()
    X_train, X_test, y_train, y_test = train_test_split_temporal(dataset, holdout_days=250)
    print(f"  Train: {len(X_train)} días, Test: {len(X_test)} días")

    print("\n[2/3] Búsqueda aleatoria (100 trials, 5-fold temporal)...")

    param_grid = {
        "n_estimators": [50, 100, 200, 300, 500],
        "max_depth": [2, 3, 4, 5, 6, -1],
        "learning_rate": [0.005, 0.01, 0.03, 0.05, 0.1],
        "num_leaves": [7, 15, 31, 63],
        "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.5, 0.6, 0.7, 0.8, 1.0],
        "reg_alpha": [0, 0.01, 0.1, 1.0, 5.0],
        "reg_lambda": [0, 0.1, 1.0, 5.0, 10.0],
        "min_child_samples": [10, 20, 50, 100],
    }

    np.random.seed(123)
    n_trials = 100
    all_results = []

    for trial in range(n_trials):
        params = {k: np.random.choice(v) for k, v in param_grid.items()}
        params["n_estimators"] = int(params["n_estimators"])
        params["max_depth"] = int(params["max_depth"])
        params["num_leaves"] = int(params["num_leaves"])
        params["min_child_samples"] = int(params["min_child_samples"])

        mse_cv = time_series_cv(X_train, y_train, params, n_splits=5)
        all_results.append({**params, "mse_cv": mse_cv})

        if (trial + 1) % 20 == 0:
            best_so_far = min(all_results, key=lambda x: x["mse_cv"])
            print(f"  Trial {trial+1}/{n_trials}: mejor MSE_cv = {best_so_far['mse_cv']:.10f}")

    results_df = pd.DataFrame(all_results).sort_values("mse_cv")
    best_params = results_df.iloc[0].drop("mse_cv").to_dict()
    best_params["n_estimators"] = int(best_params["n_estimators"])
    best_params["max_depth"] = int(best_params["max_depth"])
    best_params["num_leaves"] = int(best_params["num_leaves"])
    best_params["min_child_samples"] = int(best_params["min_child_samples"])

    print(f"\n  Mejor configuración:")
    for k, v in best_params.items():
        print(f"    {k}: {v}")

    print("\n[3/3] Evaluando en test...")
    from lightgbm import LGBMRegressor

    model_opt = LGBMRegressor(**best_params, random_state=42, verbose=-1)
    model_opt.fit(X_train, y_train)
    pred_opt = model_opt.predict(X_test)
    result_opt = evaluate_forecast(y_test.values, pred_opt, "LightGBM optimizado")

    model_def = LGBMRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, verbose=-1,
    )
    model_def.fit(X_train, y_train)
    pred_def = model_def.predict(X_test)
    result_def = evaluate_forecast(y_test.values, pred_def, "LightGBM default")

    print(f"\n  {'Métrica':<25} {'Default':>12} {'Optimizado':>12}")
    print(f"  {'-'*50}")
    print(f"  {'R² vs caminata (%)':<25} {result_def['r2_vs_caminata_pct']:>12.3f} {result_opt['r2_vs_caminata_pct']:>12.3f}")
    print(f"  {'Dirección (%)':<25} {result_def['acierto_direccion_pct']:>12.1f} {result_opt['acierto_direccion_pct']:>12.1f}")
    print(f"  {'RMSE':<25} {result_def['rmse']:>12.6f} {result_opt['rmse']:>12.6f}")
    print(f"  {'DM p-valor':<25} {result_def['dm_p_valor']:>12.4f} {result_opt['dm_p_valor']:>12.4f}")
    print(f"  {'Sharpe':<25} {result_def['sharpe_anualizado']:>12.2f} {result_opt['sharpe_anualizado']:>12.2f}")

    importance = pd.DataFrame({
        "feature": X_train.columns,
        "importance": model_opt.feature_importances_,
    }).sort_values("importance", ascending=False)

    print(f"\n  Top 5 features (LightGBM optimizado):")
    for _, row in importance.head(5).iterrows():
        print(f"    {row['feature']:<25} {row['importance']}")

    # Guardar
    RESULTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([result_def, result_opt]).to_csv(
        RESULTS / "lightgbm_optimizado_vs_default.csv", index=False, encoding="utf-8-sig"
    )
    results_df.head(20).to_csv(
        RESULTS / "lightgbm_grid_search_top20.csv", index=False, encoding="utf-8-sig"
    )
    importance.to_csv(
        RESULTS / "lightgbm_optimizado_feature_importance.csv", index=False, encoding="utf-8-sig"
    )
    (RESULTS / "lightgbm_mejores_parametros.json").write_text(
        json.dumps(best_params, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n  Guardado en results/pronostico/")
    print("=" * 70)


if __name__ == "__main__":
    main()
