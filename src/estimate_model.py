from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from openpyxl import load_workbook
from scipy import stats
from statsmodels.stats.diagnostic import (
    acorr_lm,
    acorr_ljungbox,
    breaks_cusumolsresid,
    het_arch,
    linear_reset,
)
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.tsa.ardl import ARDL, UECM
from statsmodels.tsa.stattools import adfuller, kpss


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
DATA = ROOT / "data"


CORE_VARIABLES = [
    "ln_brent",
    "ln_remesas_12m",
    "diferencial_tasas_pp",
    "deficit_fiscal_12m_pct_pib",
    "ln_dolar_amplio",
]


@dataclass
class SelectedModel:
    p: int
    q: int
    result: object


@dataclass
class SelectedDifferenceModel:
    p: int
    q: int
    result: object
    y: pd.Series
    x: pd.DataFrame


def month_start(values: pd.Series | pd.DatetimeIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(values).to_period("M").to_timestamp()


def read_fred(path: Path, output_name: str, daily: bool = False) -> pd.Series:
    raw = pd.read_csv(path)
    frame = pd.DataFrame(
        {
            "fecha": pd.to_datetime(raw.iloc[:, 0].astype("string"), errors="coerce"),
            "valor": pd.to_numeric(raw.iloc[:, 1], errors="coerce"),
        }
    ).dropna()
    series = frame.set_index("fecha")["valor"].sort_index()
    if daily:
        series = series.resample("MS").mean()
    else:
        series.index = month_start(series.index)
        series = series.groupby(level=0).mean()
    series.name = output_name
    return series


def load_remittances(path: Path) -> pd.Series:
    payload = json.loads(path.read_text(encoding="utf-8"))[0]
    data = pd.DataFrame(payload["data"], columns=["timestamp_ms", "remesas_usd_millones"])
    dates = pd.to_datetime(data.pop("timestamp_ms"), unit="ms", utc=True).dt.tz_convert(None)
    data.index = month_start(dates)
    return data["remesas_usd_millones"].astype(float).sort_index()


def load_banrep_daily(path: Path, output_name: str) -> pd.Series:
    payload = json.loads(path.read_text(encoding="utf-8"))[0]
    data = pd.DataFrame(payload["data"], columns=["timestamp_ms", output_name])
    dates = pd.to_datetime(data.pop("timestamp_ms"), unit="ms", utc=True).dt.tz_convert(None)
    data.index = pd.DatetimeIndex(dates)
    series = pd.to_numeric(data[output_name], errors="coerce").dropna().sort_index()
    series = series.resample("MS").mean()
    series.name = output_name
    return series


def load_terms_of_trade(path: Path) -> pd.Series:
    payload = json.loads(path.read_text(encoding="utf-8"))
    series_payload = next(item for item in payload if item.get("id") == 15360)
    data = pd.DataFrame(series_payload["data"], columns=["timestamp_ms", "terminos_intercambio"])
    dates = pd.to_datetime(data.pop("timestamp_ms"), unit="ms", utc=True).dt.tz_convert(None)
    data.index = month_start(dates)
    return data["terminos_intercambio"].astype(float).sort_index()


def _row_values(ws, row_number: int) -> tuple[list[object], list[object]]:
    dates = [cell.value for cell in ws[6]][1:]
    values = [cell.value for cell in ws[row_number]][1:]
    return dates, values


def load_fiscal(path: Path) -> pd.DataFrame:
    workbook = load_workbook(path, read_only=True, data_only=True)
    monthly_amounts = workbook.worksheets[0]
    monthly_pct = workbook.worksheets[3]

    dates, balance_values = _row_values(monthly_amounts, 31)
    _, income_values = _row_values(monthly_amounts, 8)
    pct_dates, income_pct_values = _row_values(monthly_pct, 8)

    fiscal = pd.DataFrame(
        {
            "fecha": pd.to_datetime(dates, errors="coerce"),
            "balance_fiscal_miles_millones_cop": pd.to_numeric(balance_values, errors="coerce"),
            "ingresos_totales_miles_millones_cop": pd.to_numeric(income_values, errors="coerce"),
        }
    ).dropna(subset=["fecha"])
    fiscal["fecha"] = month_start(fiscal["fecha"])
    fiscal = fiscal.set_index("fecha").sort_index()

    fiscal_pct = pd.DataFrame(
        {
            "fecha": pd.to_datetime(pct_dates, errors="coerce"),
            "ingresos_totales_pct_pib": pd.to_numeric(income_pct_values, errors="coerce"),
        }
    ).dropna(subset=["fecha"])
    fiscal_pct["fecha"] = month_start(fiscal_pct["fecha"])
    fiscal_pct = fiscal_pct.set_index("fecha").sort_index()

    fiscal = fiscal.join(fiscal_pct, how="left")
    valid = fiscal["ingresos_totales_pct_pib"].abs() > 1e-9
    fiscal.loc[valid, "pib_anual_miles_millones_cop_observado"] = (
        100.0
        * fiscal.loc[valid, "ingresos_totales_miles_millones_cop"]
        / fiscal.loc[valid, "ingresos_totales_pct_pib"]
    )
    year_gdp = fiscal.groupby(fiscal.index.year)["pib_anual_miles_millones_cop_observado"].median()
    fiscal["pib_anual_miles_millones_cop"] = fiscal.index.year.map(year_gdp)
    fiscal["balance_fiscal_12m_miles_millones_cop"] = fiscal[
        "balance_fiscal_miles_millones_cop"
    ].rolling(12, min_periods=12).sum()
    fiscal["deficit_fiscal_12m_pct_pib"] = (
        -100.0
        * fiscal["balance_fiscal_12m_miles_millones_cop"]
        / fiscal["pib_anual_miles_millones_cop"]
    )
    return fiscal


def build_dataset() -> pd.DataFrame:
    series = [
        load_banrep_daily(RAW / "trm_diaria_banrep.json", "trm_cop_usd"),
        read_fred(RAW / "brent_diario_fred.csv", "brent_usd_barril", daily=True),
        load_banrep_daily(
            RAW / "tasa_politica_diaria_banrep.json", "tasa_politica_colombia_pct"
        ),
        read_fred(RAW / "fed_funds_mensual_fred.csv", "fed_funds_eeuu_pct"),
        read_fred(RAW / "dolar_amplio_diario_fred.csv", "indice_dolar_amplio", daily=True),
        read_fred(RAW / "vix_diario_fred.csv", "vix", daily=True),
        load_remittances(RAW / "remesas_mensuales_banrep.json"),
        load_terms_of_trade(RAW / "series_15360_15368.json"),
    ]
    data = pd.concat(series, axis=1, sort=True).sort_index()
    data = data.join(load_fiscal(RAW / "balance_fiscal_gnc_mensual_trimestral.xlsx"), how="outer")

    data["remesas_12m_usd_millones"] = data["remesas_usd_millones"].rolling(
        12, min_periods=12
    ).sum()
    data["diferencial_tasas_pp"] = (
        data["tasa_politica_colombia_pct"] - data["fed_funds_eeuu_pct"]
    )

    positive_logs = {
        "ln_trm": "trm_cop_usd",
        "ln_brent": "brent_usd_barril",
        "ln_remesas_12m": "remesas_12m_usd_millones",
        "ln_dolar_amplio": "indice_dolar_amplio",
        "ln_vix": "vix",
        "ln_terminos_intercambio": "terminos_intercambio",
    }
    for target, source in positive_logs.items():
        data[target] = np.log(data[source].where(data[source] > 0))
    data["dln_vix"] = data["ln_vix"].diff()
    data["dummy_pandemia_2020"] = (
        (data.index >= pd.Timestamp("2020-03-01"))
        & (data.index <= pd.Timestamp("2020-05-01"))
    ).astype(int)
    data.index.name = "fecha"
    return data


def integration_tests(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for column in columns:
        for transform, series in [
            ("nivel", data[column].dropna()),
            ("primera_diferencia", data[column].diff().dropna()),
        ]:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                adf = adfuller(series, regression="c", autolag="BIC")
                try:
                    kpss_result = kpss(series, regression="c", nlags="auto")
                    kpss_stat, kpss_p = float(kpss_result[0]), float(kpss_result[1])
                except Exception:
                    kpss_stat, kpss_p = math.nan, math.nan
            rows.append(
                {
                    "variable": column,
                    "transformacion": transform,
                    "n": int(series.shape[0]),
                    "adf_estadistico": float(adf[0]),
                    "adf_p": float(adf[1]),
                    "adf_rezagos": int(adf[2]),
                    "kpss_estadistico": kpss_stat,
                    "kpss_p": kpss_p,
                }
            )
    return pd.DataFrame(rows)


def select_ardl(y: pd.Series, exog: pd.DataFrame, fixed: pd.DataFrame) -> tuple[SelectedModel, pd.DataFrame]:
    candidates: list[dict[str, float | int]] = []
    selected: SelectedModel | None = None
    for p in range(1, 5):
        for q in range(1, 3):
            result = ARDL(
                y,
                lags=p,
                exog=exog,
                order=q,
                trend="c",
                fixed=fixed,
                causal=False,
                missing="raise",
            ).fit()
            candidates.append(
                {
                    "p_trm": p,
                    "q_explicativas": q,
                    "aic": float(result.aic),
                    "bic": float(result.bic),
                    "hqic": float(result.hqic),
                    "loglik": float(result.llf),
                }
            )
            if selected is None or result.bic < selected.result.bic:
                selected = SelectedModel(p=p, q=q, result=result)
    assert selected is not None
    return selected, pd.DataFrame(candidates).sort_values("bic").reset_index(drop=True)


def difference_components(model_data: pd.DataFrame) -> pd.DataFrame:
    diff = pd.DataFrame(index=model_data.index)
    diff["D.ln_trm"] = model_data["ln_trm"].diff()
    for variable in CORE_VARIABLES:
        diff[f"D.{variable}"] = model_data[variable].diff()
    diff["D.ln_vix"] = model_data["ln_vix"].diff()
    diff["dummy_pandemia_2020"] = model_data["dummy_pandemia_2020"]
    return diff


def make_difference_design(
    components: pd.DataFrame, p: int, q: int, index: pd.Index | None = None
) -> tuple[pd.Series, pd.DataFrame]:
    y = components["D.ln_trm"].rename("D.ln_trm")
    x = pd.DataFrame(index=components.index)
    for lag in range(1, p + 1):
        x[f"D.ln_trm.L{lag}"] = components["D.ln_trm"].shift(lag)
    drivers = [f"D.{variable}" for variable in CORE_VARIABLES] + ["D.ln_vix"]
    for driver in drivers:
        for lag in range(0, q + 1):
            x[f"{driver}.L{lag}"] = components[driver].shift(lag)
    x["dummy_pandemia_2020"] = components["dummy_pandemia_2020"]
    x = sm.add_constant(x, has_constant="add")
    combined = pd.concat([y, x], axis=1).dropna()
    if index is not None:
        combined = combined.reindex(index).dropna()
    return combined["D.ln_trm"], combined.drop(columns="D.ln_trm")


def select_difference_model(model_data: pd.DataFrame) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    components = difference_components(model_data)
    common_index = make_difference_design(components, p=3, q=2)[0].index
    candidates: list[dict[str, float | int]] = []
    selected: SelectedDifferenceModel | None = None
    for p in range(0, 4):
        for q in range(0, 3):
            y, x = make_difference_design(components, p=p, q=q, index=common_index)
            result = sm.OLS(y, x).fit()
            candidates.append(
                {
                    "p_cambio_trm": p,
                    "q_cambios_explicativas": q,
                    "aic": float(result.aic),
                    "bic": float(result.bic),
                    "r_cuadrado_ajustado": float(result.rsquared_adj),
                }
            )
            if selected is None or result.bic < selected.result.bic:
                selected = SelectedDifferenceModel(p=p, q=q, result=result, y=y, x=x)
    assert selected is not None
    grid = pd.DataFrame(candidates).sort_values("bic").reset_index(drop=True)
    return selected, grid


def make_timed_difference_design(
    components: pd.DataFrame, p: int, index: pd.Index | None = None
) -> tuple[pd.Series, pd.DataFrame]:
    y = components["D.ln_trm"].rename("D.ln_trm")
    x = pd.DataFrame(index=components.index)
    for lag in range(1, p + 1):
        x[f"D.ln_trm.L{lag}"] = components["D.ln_trm"].shift(lag)

    # Los precios globales se observan dentro del mes; las variables colombianas lentas
    # se rezagan un mes para reducir simultaneidad y respetar sus fechas de publicación.
    x["D.ln_brent.L0"] = components["D.ln_brent"]
    x["D.ln_dolar_amplio.L0"] = components["D.ln_dolar_amplio"]
    x["D.ln_vix.L0"] = components["D.ln_vix"]
    x["D.ln_remesas_12m.L1"] = components["D.ln_remesas_12m"].shift(1)
    x["D.diferencial_tasas_pp.L1"] = components["D.diferencial_tasas_pp"].shift(1)
    x["D.deficit_fiscal_12m_pct_pib.L1"] = components[
        "D.deficit_fiscal_12m_pct_pib"
    ].shift(1)
    x["dummy_pandemia_2020"] = components["dummy_pandemia_2020"]
    x = sm.add_constant(x, has_constant="add")
    combined = pd.concat([y, x], axis=1).dropna()
    if index is not None:
        combined = combined.reindex(index).dropna()
    return combined["D.ln_trm"], combined.drop(columns="D.ln_trm")


def select_timed_difference_model(
    model_data: pd.DataFrame,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    components = difference_components(model_data)
    common_index = make_timed_difference_design(components, p=3)[0].index
    candidates: list[dict[str, float | int]] = []
    selected: SelectedDifferenceModel | None = None
    for p in range(0, 4):
        y, x = make_timed_difference_design(components, p=p, index=common_index)
        result = sm.OLS(y, x).fit()
        candidates.append(
            {
                "p_cambio_trm": p,
                "aic": float(result.aic),
                "bic": float(result.bic),
                "r_cuadrado_ajustado": float(result.rsquared_adj),
            }
        )
        if selected is None or result.bic < selected.result.bic:
            selected = SelectedDifferenceModel(p=p, q=0, result=result, y=y, x=x)
    assert selected is not None
    return selected, pd.DataFrame(candidates).sort_values("bic").reset_index(drop=True)


def tidy_robust_ols(result, maxlags: int = 6) -> tuple[object, pd.DataFrame]:
    robust = result.get_robustcov_results(
        cov_type="HAC", maxlags=maxlags, use_correction=True, use_t=True
    )
    names = result.model.exog_names
    confidence = robust.conf_int(alpha=0.05)
    table = pd.DataFrame(
        {
            "termino": names,
            "coeficiente": robust.params,
            "error_estandar_hac": robust.bse,
            "estadistico_t": robust.tvalues,
            "p_valor": robust.pvalues,
            "ic_95_inferior": confidence[:, 0],
            "ic_95_superior": confidence[:, 1],
        }
    )
    return robust, table


def tidy_result(result) -> pd.DataFrame:
    confidence = result.conf_int(alpha=0.05)
    return pd.DataFrame(
        {
            "termino": result.params.index,
            "coeficiente": result.params.values,
            "error_estandar_hac": result.bse.values,
            "estadistico_t": result.tvalues.values,
            "p_valor": result.pvalues.values,
            "ic_95_inferior": confidence.iloc[:, 0].values,
            "ic_95_superior": confidence.iloc[:, 1].values,
        }
    )


def tidy_long_run(result) -> pd.DataFrame:
    confidence = result.ci_conf_int(alpha=0.05)
    return pd.DataFrame(
        {
            "termino": result.ci_params.index,
            "coeficiente_largo_plazo": result.ci_params.values,
            "error_estandar": result.ci_bse.values,
            "estadistico_t": result.ci_tvalues.values,
            "p_valor": result.ci_pvalues.values,
            "ic_95_inferior": confidence.iloc[:, 0].values,
            "ic_95_superior": confidence.iloc[:, 1].values,
        }
    )


def diagnostics(result) -> pd.DataFrame:
    residuals = pd.Series(result.resid).dropna()
    lb = acorr_ljungbox(residuals, lags=[6, 12], return_df=True)
    bg = acorr_lm(residuals, nlags=12)
    arch = het_arch(residuals, nlags=12)
    jb = jarque_bera(residuals)
    if hasattr(result.model, "_y") and hasattr(result.model, "_x"):
        ols_proxy = sm.OLS(result.model._y, result.model._x).fit()
    else:
        ols_proxy = result
    reset = linear_reset(ols_proxy, power=2, use_f=True)
    cusum = breaks_cusumolsresid(residuals, ddof=int(result.df_model) + 1)
    return pd.DataFrame(
        [
            {"prueba": "Ljung-Box (6)", "estadistico": lb.loc[6, "lb_stat"], "p_valor": lb.loc[6, "lb_pvalue"]},
            {"prueba": "Ljung-Box (12)", "estadistico": lb.loc[12, "lb_stat"], "p_valor": lb.loc[12, "lb_pvalue"]},
            {"prueba": "Breusch-Godfrey (12)", "estadistico": bg[0], "p_valor": bg[1]},
            {"prueba": "ARCH-LM (12)", "estadistico": arch[0], "p_valor": arch[1]},
            {"prueba": "Jarque-Bera", "estadistico": jb[0], "p_valor": jb[1]},
            {"prueba": "Ramsey RESET", "estadistico": float(reset.fvalue), "p_valor": float(reset.pvalue)},
            {"prueba": "CUSUM estabilidad", "estadistico": cusum[0], "p_valor": cusum[1]},
            {"prueba": "Durbin-Watson", "estadistico": durbin_watson(residuals), "p_valor": np.nan},
        ]
    )


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


def bounds_to_frames(bounds_result) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = pd.DataFrame(
        [
            {
                "estadistico_f": float(bounds_result.stat),
                "p_valor_i0": float(bounds_result.p_values.loc["lower"]),
                "p_valor_i1": float(bounds_result.p_values.loc["upper"]),
            }
        ]
    )
    critical = bounds_result.crit_vals.reset_index().rename(columns={"index": "percentil"})
    return summary, critical


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    data = build_dataset()
    model_columns = ["ln_trm", *CORE_VARIABLES, "ln_vix", "dln_vix", "dummy_pandemia_2020"]
    model_data = data.loc[pd.Timestamp("2006-01-01") :, model_columns].dropna().copy().asfreq("MS")
    if model_data.isna().any().any():
        raise ValueError("La muestra balanceada contiene meses faltantes.")

    selected_diff, lag_grid_diff = select_timed_difference_model(model_data)
    _, coefficients_diff = tidy_robust_ols(selected_diff.result, maxlags=6)
    diagnostics_diff = diagnostics(selected_diff.result)
    predictions, validation = difference_validation(
        model_data, selected_diff, holdout=min(48, len(selected_diff.y) // 4)
    )
    fitted_diff, contributions_diff = difference_fit_and_contributions(
        model_data, selected_diff
    )

    y = model_data["ln_trm"]
    exog = model_data[CORE_VARIABLES]
    fixed = model_data[["dln_vix", "dummy_pandemia_2020"]]
    selected_ecm, lag_grid_ecm = select_ardl(y, exog, fixed)
    uecm_model = UECM.from_ardl(selected_ecm.result.model)
    uecm_result = uecm_model.fit(
        cov_type="HAC", cov_kwds={"maxlags": 6, "use_correction": True}, use_t=True
    )
    bounds = uecm_result.bounds_test(case=3, cov_type="nonrobust")
    bounds_summary, bounds_critical = bounds_to_frames(bounds)

    tests = integration_tests(
        model_data,
        ["ln_trm", *CORE_VARIABLES, "ln_vix"],
    )
    short_run_ecm = tidy_result(uecm_result)
    long_run_ecm = tidy_long_run(uecm_result)
    diagnostics_ecm = diagnostics(selected_ecm.result)

    data.to_csv(DATA / "modelo_trm_datos_mensuales.csv", encoding="utf-8-sig", float_format="%.10g")
    model_data.to_csv(DATA / "modelo_trm_muestra_estimacion.csv", encoding="utf-8-sig", float_format="%.10g")
    lag_grid_diff.to_csv(
        RESULTS / "seleccion_rezagos_adl_diferencias.csv", index=False, encoding="utf-8-sig"
    )
    coefficients_diff.to_csv(
        RESULTS / "coeficientes_modelo_principal.csv", index=False, encoding="utf-8-sig"
    )
    diagnostics_diff.to_csv(
        RESULTS / "diagnosticos_modelo_principal.csv", index=False, encoding="utf-8-sig"
    )
    fitted_diff.to_csv(
        RESULTS / "ajuste_historico_modelo_principal.csv", encoding="utf-8-sig"
    )
    contributions_diff.to_csv(
        RESULTS / "contribuciones_modelo_principal.csv", encoding="utf-8-sig"
    )
    lag_grid_ecm.to_csv(
        RESULTS / "seleccion_rezagos_ecm.csv", index=False, encoding="utf-8-sig"
    )
    tests.to_csv(RESULTS / "pruebas_integracion.csv", index=False, encoding="utf-8-sig")
    short_run_ecm.to_csv(
        RESULTS / "coeficientes_corto_plazo_ecm.csv", index=False, encoding="utf-8-sig"
    )
    long_run_ecm.to_csv(
        RESULTS / "coeficientes_largo_plazo_ecm.csv", index=False, encoding="utf-8-sig"
    )
    bounds_summary.to_csv(RESULTS / "bounds_resumen.csv", index=False, encoding="utf-8-sig")
    bounds_critical.to_csv(RESULTS / "bounds_criticos.csv", index=False, encoding="utf-8-sig")
    diagnostics_ecm.to_csv(
        RESULTS / "diagnosticos_ecm.csv", index=False, encoding="utf-8-sig"
    )
    predictions.to_csv(RESULTS / "validacion_predicciones.csv", encoding="utf-8-sig")
    validation.to_csv(RESULTS / "validacion_metricas.csv", index=False, encoding="utf-8-sig")

    metadata = {
        "muestra_inicio": model_data.index.min().strftime("%Y-%m-%d"),
        "muestra_fin": model_data.index.max().strftime("%Y-%m-%d"),
        "observaciones": int(model_data.shape[0]),
        "modelo_principal": "Modelo mensual en primeras diferencias con temporización económica y errores HAC",
        "adl_p_cambio_trm": selected_diff.p,
        "temporizacion": "Brent, dólar amplio y VIX contemporáneos; remesas, diferencial de tasas y déficit rezagados un mes",
        "adl_observaciones": int(selected_diff.result.nobs),
        "adl_aic": float(selected_diff.result.aic),
        "adl_bic": float(selected_diff.result.bic),
        "adl_r_cuadrado": float(selected_diff.result.rsquared),
        "adl_r_cuadrado_ajustado": float(selected_diff.result.rsquared_adj),
        "ecm_p": selected_ecm.p,
        "ecm_q_comun": selected_ecm.q,
        "bounds_f": float(bounds.stat),
        "bounds_p_i0": float(bounds.p_values.loc["lower"]),
        "bounds_p_i1": float(bounds.p_values.loc["upper"]),
        "cointegracion_5pct": "no concluyente",
        "velocidad_ajuste": float(uecm_result.params.get("ln_trm.L1", np.nan)),
    }
    (RESULTS / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    print("\nCoeficientes del modelo principal en diferencias")
    print(coefficients_diff.to_string(index=False))
    print("\nDiagnósticos del modelo principal")
    print(diagnostics_diff.to_string(index=False))
    print("\nValidación")
    print(validation.to_string(index=False))
    print("\nECM exploratorio: coeficientes de largo plazo")
    print(long_run_ecm.to_string(index=False))


if __name__ == "__main__":
    main()
