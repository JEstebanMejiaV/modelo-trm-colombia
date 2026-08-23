from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.ardl import ARDL

from .config import SelectedDifferenceModel, SAMPLE_START
from .transforms import make_timed_difference_design, difference_components


def expanding_validation(
    y: pd.Series,
    exog: pd.DataFrame,
    fixed: pd.DataFrame,
    p: int,
    q: int,
    holdout: int = 48,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions: list[dict[str, object]] = []
    split = len(y) - holdout
    for i in range(split, len(y)):
        train_y = y.iloc[:i]
        train_x = exog.iloc[:i]
        train_fixed = fixed.iloc[:i]
        model = ARDL(
            train_y,
            lags=p,
            exog=train_x,
            order=q,
            trend="c",
            fixed=train_fixed,
            causal=False,
            missing="raise",
        ).fit()
        forecast_log = float(model.forecast(1, exog=exog.iloc[[i]], fixed=fixed.iloc[[i]]).iloc[0])
        predictions.append(
            {
                "fecha": y.index[i],
                "ln_trm_observada": float(y.iloc[i]),
                "ln_trm_modelo_condicional": forecast_log,
                "ln_trm_caminata_aleatoria": float(y.iloc[i - 1]),
            }
        )
    pred = pd.DataFrame(predictions).set_index("fecha")
    pred["trm_observada"] = np.exp(pred["ln_trm_observada"])
    pred["trm_modelo_condicional"] = np.exp(pred["ln_trm_modelo_condicional"])
    pred["trm_caminata_aleatoria"] = np.exp(pred["ln_trm_caminata_aleatoria"])
    pred["cambio_observado"] = pred["ln_trm_observada"].diff()
    pred["cambio_modelo"] = pred["ln_trm_modelo_condicional"] - pred["ln_trm_caminata_aleatoria"]
    pred["cambio_caminata"] = 0.0

    metrics: list[dict[str, object]] = []
    for label, forecast_col in [
        ("ARDL condicional", "ln_trm_modelo_condicional"),
        ("Caminata aleatoria", "ln_trm_caminata_aleatoria"),
    ]:
        errors = pred[forecast_col] - pred["ln_trm_observada"]
        if label == "ARDL condicional":
            direction = np.sign(pred["cambio_modelo"])
        else:
            direction = np.sign(pred["cambio_caminata"])
        observed_direction = np.sign(pred["ln_trm_observada"] - pred["ln_trm_caminata_aleatoria"])
        direction_hit = float((direction == observed_direction).mean())
        metrics.append(
            {
                "modelo": label,
                "observaciones": int(errors.shape[0]),
                "mae_log": float(errors.abs().mean()),
                "rmse_log": float(np.sqrt(np.mean(np.square(errors)))),
                "mape_pct": float(
                    100
                    * np.mean(
                        np.abs(
                            np.exp(pred[forecast_col]) - np.exp(pred["ln_trm_observada"])
                        )
                        / np.exp(pred["ln_trm_observada"])
                    )
                ),
                "acierto_direccion_pct": 100 * direction_hit,
            }
        )
    return pred, pd.DataFrame(metrics)


def difference_validation(
    model_data: pd.DataFrame,
    selected: SelectedDifferenceModel,
    holdout: int = 48,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    y, x = selected.y, selected.x
    split = len(y) - holdout
    rows: list[dict[str, object]] = []
    for i in range(split, len(y)):
        train = sm.OLS(y.iloc[:i], x.iloc[:i]).fit()
        forecast_change = float(train.predict(x.iloc[[i]]).iloc[0])
        date = y.index[i]
        previous_log = float(model_data["ln_trm"].shift(1).loc[date])
        actual_log = float(model_data.loc[date, "ln_trm"])
        rows.append(
            {
                "fecha": date,
                "ln_trm_observada": actual_log,
                "ln_trm_modelo_condicional": previous_log + forecast_change,
                "ln_trm_caminata_aleatoria": previous_log,
                "cambio_log_observado": float(y.iloc[i]),
                "cambio_log_modelo": forecast_change,
            }
        )
    pred = pd.DataFrame(rows).set_index("fecha")
    pred["trm_observada"] = np.exp(pred["ln_trm_observada"])
    pred["trm_modelo_condicional"] = np.exp(pred["ln_trm_modelo_condicional"])
    pred["trm_caminata_aleatoria"] = np.exp(pred["ln_trm_caminata_aleatoria"])

    metrics: list[dict[str, object]] = []
    for label, forecast_col in [
        ("ADL diferencias condicional", "ln_trm_modelo_condicional"),
        ("Caminata aleatoria", "ln_trm_caminata_aleatoria"),
    ]:
        errors = pred[forecast_col] - pred["ln_trm_observada"]
        direction_hit = np.nan
        if label.startswith("ADL"):
            direction_hit = float(
                (
                    np.sign(pred["cambio_log_modelo"])
                    == np.sign(pred["cambio_log_observado"])
                ).mean()
            )
        metrics.append(
            {
                "modelo": label,
                "observaciones": int(errors.shape[0]),
                "mae_log": float(errors.abs().mean()),
                "rmse_log": float(np.sqrt(np.mean(np.square(errors)))),
                "mape_pct": float(
                    100
                    * np.mean(
                        np.abs(
                            np.exp(pred[forecast_col]) - np.exp(pred["ln_trm_observada"])
                        )
                        / np.exp(pred["ln_trm_observada"])
                    )
                ),
                "acierto_direccion_pct": 100 * direction_hit,
            }
        )
    return pred, pd.DataFrame(metrics)


def difference_fit_and_contributions(
    model_data: pd.DataFrame, selected: SelectedDifferenceModel
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fitted = pd.DataFrame(index=selected.y.index)
    fitted["cambio_log_observado"] = selected.y
    fitted["cambio_log_ajustado"] = selected.result.fittedvalues
    fitted["ln_trm_mes_anterior"] = model_data["ln_trm"].shift(1).reindex(fitted.index)
    fitted["trm_observada"] = np.exp(model_data["ln_trm"].reindex(fitted.index))
    fitted["trm_ajustada_un_paso"] = np.exp(
        fitted["ln_trm_mes_anterior"] + fitted["cambio_log_ajustado"]
    )
    fitted["residuo_cambio_log"] = fitted["cambio_log_observado"] - fitted[
        "cambio_log_ajustado"
    ]

    contributions = selected.x.multiply(selected.result.params, axis=1)
    contributions.index.name = "fecha"
    contributions["ajuste_total"] = contributions.sum(axis=1)
    return fitted, contributions
