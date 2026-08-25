"""Modelos de pronóstico diario: econométricos y ML."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def evaluate_forecast(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str,
) -> dict:
    """Métricas estándar para evaluar un pronóstico de retorno."""
    errors = y_pred - y_true
    rw_errors = -y_true  # caminata aleatoria = predecir 0

    mse_model = float((errors**2).mean())
    mse_rw = float((rw_errors**2).mean())
    r2_vs_rw = 1.0 - mse_model / mse_rw if mse_rw > 0 else np.nan

    # Dirección
    dir_hit = float(np.mean(np.sign(y_pred) == np.sign(y_true)))

    # Sharpe de estrategia simple
    strategy = -np.sign(y_pred) * y_true
    sharpe = float(strategy.mean() / strategy.std() * np.sqrt(250)) if strategy.std() > 0 else 0

    # Diebold-Mariano
    d = rw_errors**2 - errors**2
    dm_stat = float(d.mean() / (d.std() / np.sqrt(len(d)))) if d.std() > 0 else 0
    dm_p = float(2 * (1 - stats.t.cdf(abs(dm_stat), df=len(d) - 1)))

    # MAE en pesos (para interpretación)
    # Si TRM ~ 4200, un retorno de 0.001 = 4.2 pesos
    mae_retorno = float(np.abs(errors).mean())

    return {
        "modelo": model_name,
        "rmse": float(np.sqrt(mse_model)),
        "mae_retorno": mae_retorno,
        "r2_vs_caminata_pct": 100 * r2_vs_rw,
        "acierto_direccion_pct": 100 * dir_hit,
        "sharpe_anualizado": sharpe,
        "dm_stat": dm_stat,
        "dm_p_valor": dm_p,
    }


def fit_ols(X_train, y_train, X_test):
    """OLS con todos los features."""
    import statsmodels.api as sm
    X_tr = sm.add_constant(X_train)
    X_te = sm.add_constant(X_test)
    model = sm.OLS(y_train, X_tr).fit()
    return model.predict(X_te).values


def fit_ridge(X_train, y_train, X_test, alpha=1.0):
    """Ridge regression (L2)."""
    from sklearn.linear_model import Ridge
    model = Ridge(alpha=alpha)
    model.fit(X_train, y_train)
    return model.predict(X_test)


def fit_lasso(X_train, y_train, X_test, alpha=0.0001):
    """Lasso regression (L1) — selección automática de features."""
    from sklearn.linear_model import Lasso
    model = Lasso(alpha=alpha, max_iter=10000)
    model.fit(X_train, y_train)
    return model.predict(X_test)


def fit_elastic_net(X_train, y_train, X_test, alpha=0.0001, l1_ratio=0.5):
    """Elastic Net (L1 + L2)."""
    from sklearn.linear_model import ElasticNet
    model = ElasticNet(alpha=alpha, l1_ratio=l1_ratio, max_iter=10000)
    model.fit(X_train, y_train)
    return model.predict(X_test)


def fit_random_forest(X_train, y_train, X_test):
    """Random Forest con hiperparámetros conservadores y un hilo."""
    from sklearn.ensemble import RandomForestRegressor
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=5,
        min_samples_leaf=20,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X_train, y_train)
    return model.predict(X_test), model.feature_importances_


def fit_xgboost(X_train, y_train, X_test):
    """XGBoost regularizado con semilla y paralelismo controlados."""
    from xgboost import XGBRegressor
    model = XGBRegressor(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=1,
        verbosity=0,
    )
    model.fit(X_train, y_train)
    return model.predict(X_test), model.feature_importances_


def fit_lightgbm(X_train, y_train, X_test):
    """LightGBM determinista con paralelismo controlado."""
    from lightgbm import LGBMRegressor
    model = LGBMRegressor(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=1,
        deterministic=True,
        force_col_wise=True,
        verbose=-1,
    )
    model.fit(X_train, y_train)
    return model.predict(X_test), model.feature_importances_


def fit_expanding_ols(X_train, y_train, X_test):
    """OLS con ventana expanding (reestima cada día)."""
    import statsmodels.api as sm
    predictions = []
    X_all = pd.concat([X_train, X_test])
    y_all = pd.concat([y_train, pd.Series(np.nan, index=X_test.index)])
    n_train = len(X_train)

    for i in range(len(X_test)):
        idx = n_train + i
        X_tr = sm.add_constant(X_all.iloc[:idx], has_constant="add")
        y_tr = y_all.iloc[:idx].dropna()
        X_tr = X_tr.loc[y_tr.index]
        model = sm.OLS(y_tr, X_tr).fit()
        X_pred = sm.add_constant(X_all.iloc[[idx]], has_constant="add")
        predictions.append(float(model.predict(X_pred).iloc[0]))

    return np.array(predictions)


def fit_combination(predictions_dict: dict, y_test: np.ndarray) -> np.ndarray:
    """
    Combinación óptima: promedio ponderado por inversa del MSE
    usando los primeros 50 días como calibración.
    """
    calibration = 50
    if len(y_test) <= calibration:
        # Simple average si no hay suficiente calibración
        return np.mean(list(predictions_dict.values()), axis=0)

    # Calcular MSE de calibración para cada modelo
    weights = {}
    for name, preds in predictions_dict.items():
        mse = float(((preds[:calibration] - y_test[:calibration])**2).mean())
        weights[name] = 1.0 / max(mse, 1e-12)

    total_w = sum(weights.values())
    combined = np.zeros(len(y_test))
    for name, preds in predictions_dict.items():
        combined += (weights[name] / total_w) * preds

    return combined
