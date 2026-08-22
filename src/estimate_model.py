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


ECM_LEVEL_VARIABLES = [
    "ln_brent",
    "ln_remesas_12m",
    "diferencial_tasas_pp",
    "deficit_fiscal_12m_pct_pib",
    "ln_dolar_amplio",
]


# Cada factor es un jugador de la descomposicion Shapley. Todos sus terminos
# (transformaciones y rezagos) entran o salen juntos al calcular el R2 marginal.
BASE_FACTOR_SPECS = {
    "Petróleo Brent": {
        "grupo": "Global",
        "terminos": [("D.ln_brent", 0)],
    },
    "Remesas": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.ln_remesas_12m", 1)],
    },
    "Diferencial de tasas": {
        "grupo": "Política doméstica",
        "terminos": [("D.diferencial_tasas_pp", 1)],
    },
    "Déficit fiscal": {
        "grupo": "Política doméstica",
        "terminos": [("D.deficit_fiscal_12m_pct_pib", 1)],
    },
    "Dólar amplio": {
        "grupo": "Global",
        "terminos": [("D.ln_dolar_amplio", 0)],
    },
    "VIX": {
        "grupo": "Global",
        "terminos": [("D.ln_vix", 0)],
    },
}


EXPANDED_FACTOR_SPECS = {
    **BASE_FACTOR_SPECS,
    "Spread TES-Treasury 10 años": {
        "grupo": "Riesgo local",
        # Contemporaneo: esta version es contabilidad historica/nowcast, no causal.
        "terminos": [("D.spread_tes_ust_10y_pp", 0)],
    },
    "Reservas internacionales": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.ln_reservas_netas_sin_flar", 1)],
    },
    "Balanza comercial cambiaria": {
        "grupo": "Sector externo Colombia",
        "terminos": [("asinh_balanza_comercial", 1)],
    },
    "Flujos netos de capital": {
        "grupo": "Sector externo Colombia",
        "terminos": [("asinh_flujos_capital", 1)],
    },
    "Diferencial de inflación": {
        "grupo": "Política doméstica",
        "terminos": [("diferencial_inflacion_pp", 1)],
    },
    "Monedas regionales": {
        "grupo": "Regional",
        "terminos": [("factor_monedas_regionales", 0)],
    },
}


DIFFERENCED_COMPONENTS = [
    "ln_brent",
    "ln_remesas_12m",
    "diferencial_tasas_pp",
    "deficit_fiscal_12m_pct_pib",
    "ln_dolar_amplio",
    "ln_vix",
    "spread_tes_ust_10y_pp",
    "ln_reservas_netas_sin_flar",
]


LEVEL_COMPONENTS = [
    "asinh_balanza_comercial",
    "asinh_flujos_capital",
    "diferencial_inflacion_pp",
    "factor_monedas_regionales",
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


def load_banrep_series(path: Path, output_name: str, daily: bool = False) -> pd.Series:
    """Lee el JSON publico del graficador de BanRep y lo lleva a frecuencia mensual."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    item = payload[0] if isinstance(payload, list) else payload
    data = pd.DataFrame(item["data"], columns=["timestamp_ms", output_name])
    dates = pd.to_datetime(data.pop("timestamp_ms"), unit="ms", utc=True).dt.tz_convert(None)
    data.index = pd.DatetimeIndex(dates)
    series = pd.to_numeric(data[output_name], errors="coerce").dropna().sort_index()
    if daily:
        # Se promedia cada mercado por separado; no se cruzan calendarios diarios.
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
    return load_banrep_series(path, output_name, daily=True)


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
        load_banrep_series(
            RAW / "reservas_netas_sin_flar_banrep.json",
            "reservas_netas_sin_flar_usd_millones",
        ),
        load_banrep_series(
            RAW / "tes_10y_banrep.json", "tes_10y_colombia_pct", daily=True
        ),
        read_fred(
            RAW / "treasury_10y_diario_fred.csv",
            "treasury_10y_eeuu_pct",
            daily=True,
        ),
        load_banrep_series(
            RAW / "balanza_comercial_cambiaria_banrep.json",
            "balanza_comercial_cambiaria_usd_millones",
        ),
        load_banrep_series(
            RAW / "flujos_capital_totales_banrep.json",
            "flujos_capital_usd_millones",
        ),
        load_banrep_series(RAW / "ipc_colombia_banrep.json", "ipc_colombia"),
        read_fred(RAW / "ipc_eeuu_mensual_fred.csv", "ipc_eeuu"),
        read_fred(RAW / "brl_usd_mensual_fred.csv", "brl_por_usd"),
        read_fred(RAW / "clp_usd_mensual_fred.csv", "clp_por_usd"),
        read_fred(RAW / "mxn_usd_mensual_fred.csv", "mxn_por_usd"),
    ]
    data = pd.concat(series, axis=1, sort=True).sort_index()
    data = data.join(load_fiscal(RAW / "balance_fiscal_gnc_mensual_trimestral.xlsx"), how="outer")

    data["remesas_12m_usd_millones"] = data["remesas_usd_millones"].rolling(
        12, min_periods=12
    ).sum()
    data["diferencial_tasas_pp"] = (
        data["tasa_politica_colombia_pct"] - data["fed_funds_eeuu_pct"]
    )
    data["spread_tes_ust_10y_pp"] = (
        data["tes_10y_colombia_pct"] - data["treasury_10y_eeuu_pct"]
    )

    # CPIAUCNS no publico octubre de 2025. Se interpola solamente ese hueco
    # interno para poder formar la inflacion interanual sin cortar la muestra.
    ipc_eeuu_original = data["ipc_eeuu"].copy()
    ipc_eeuu_completo = ipc_eeuu_original.interpolate(limit=1, limit_area="inside")
    data["ipc_eeuu_interpolado"] = (
        ipc_eeuu_original.isna() & ipc_eeuu_completo.notna()
    ).astype(int)
    data["ipc_eeuu"] = ipc_eeuu_completo
    data["inflacion_colombia_interanual_pct"] = 100.0 * (
        data["ipc_colombia"] / data["ipc_colombia"].shift(12) - 1.0
    )
    data["inflacion_eeuu_interanual_pct"] = 100.0 * (
        data["ipc_eeuu"] / data["ipc_eeuu"].shift(12) - 1.0
    )
    data["diferencial_inflacion_pp"] = (
        data["inflacion_colombia_interanual_pct"]
        - data["inflacion_eeuu_interanual_pct"]
    )

    data["asinh_balanza_comercial"] = np.arcsinh(
        data["balanza_comercial_cambiaria_usd_millones"] / 1000.0
    )
    data["asinh_flujos_capital"] = np.arcsinh(
        data["flujos_capital_usd_millones"] / 1000.0
    )

    regional_returns = pd.DataFrame(
        {
            currency: np.log(data[currency].where(data[currency] > 0)).diff()
            for currency in ["brl_por_usd", "clp_por_usd", "mxn_por_usd"]
        }
    )
    calibration = regional_returns.loc["2006-01-01":"2019-12-01"]
    regional_z = (regional_returns - calibration.mean()) / calibration.std(ddof=0)
    data["factor_monedas_regionales"] = regional_z.mean(axis=1, skipna=False)

    positive_logs = {
        "ln_trm": "trm_cop_usd",
        "ln_brent": "brent_usd_barril",
        "ln_remesas_12m": "remesas_12m_usd_millones",
        "ln_dolar_amplio": "indice_dolar_amplio",
        "ln_vix": "vix",
        "ln_terminos_intercambio": "terminos_intercambio",
        "ln_reservas_netas_sin_flar": "reservas_netas_sin_flar_usd_millones",
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
    for variable in DIFFERENCED_COMPONENTS:
        if variable in model_data:
            diff[f"D.{variable}"] = model_data[variable].diff()
    for variable in LEVEL_COMPONENTS:
        if variable in model_data:
            diff[variable] = model_data[variable]
    diff["dummy_pandemia_2020"] = model_data["dummy_pandemia_2020"]
    return diff


def make_difference_design(
    components: pd.DataFrame, p: int, q: int, index: pd.Index | None = None
) -> tuple[pd.Series, pd.DataFrame]:
    y = components["D.ln_trm"].rename("D.ln_trm")
    x = pd.DataFrame(index=components.index)
    for lag in range(1, p + 1):
        x[f"D.ln_trm.L{lag}"] = components["D.ln_trm"].shift(lag)
    drivers = [f"D.{variable}" for variable in ECM_LEVEL_VARIABLES] + ["D.ln_vix"]
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


def design_term_name(component: str, lag: int) -> str:
    return f"{component}.L{lag}"


def make_timed_difference_design(
    components: pd.DataFrame,
    p: int,
    factor_specs: dict[str, dict[str, object]],
    index: pd.Index | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    y = components["D.ln_trm"].rename("D.ln_trm")
    x = pd.DataFrame(index=components.index)
    for lag in range(1, p + 1):
        x[f"D.ln_trm.L{lag}"] = components["D.ln_trm"].shift(lag)

    for factor in factor_specs.values():
        for component, lag in factor["terminos"]:
            x[design_term_name(component, lag)] = components[component].shift(lag)
    x["dummy_pandemia_2020"] = components["dummy_pandemia_2020"]
    x = sm.add_constant(x, has_constant="add")
    combined = pd.concat([y, x], axis=1).dropna()
    if index is not None:
        combined = combined.reindex(index).dropna()
    return combined["D.ln_trm"], combined.drop(columns="D.ln_trm")


def select_timed_difference_model(
    model_data: pd.DataFrame,
    factor_specs: dict[str, dict[str, object]],
    common_index: pd.Index | None = None,
) -> tuple[SelectedDifferenceModel, pd.DataFrame]:
    components = difference_components(model_data)
    if common_index is None:
        common_index = make_timed_difference_design(
            components, p=3, factor_specs=factor_specs
        )[0].index
    candidates: list[dict[str, float | int]] = []
    selected: SelectedDifferenceModel | None = None
    for p in range(0, 4):
        y, x = make_timed_difference_design(
            components, p=p, factor_specs=factor_specs, index=common_index
        )
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


def exact_shapley_r2(
    selected: SelectedDifferenceModel,
    factor_specs: dict[str, dict[str, object]],
    robust_coefficients: pd.DataFrame,
) -> pd.DataFrame:
    """Descompone exactamente el incremento del R2 mediante Shapley/LMG."""
    factor_columns = {
        name: [design_term_name(component, lag) for component, lag in spec["terminos"]]
        for name, spec in factor_specs.items()
    }
    assigned = {column for columns in factor_columns.values() for column in columns}
    base_columns = [column for column in selected.x.columns if column not in assigned]
    missing = assigned.difference(selected.x.columns)
    if missing:
        raise ValueError(f"Faltan terminos para Shapley: {sorted(missing)}")

    y = selected.y.to_numpy(dtype=float)
    total_ss = float(np.square(y - y.mean()).sum())

    def r_squared(columns: list[str]) -> float:
        matrix = selected.x[columns].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        residual = y - matrix @ beta
        return 1.0 - float(np.square(residual).sum()) / total_ss

    names = list(factor_specs)
    player_count = len(names)
    cache: dict[int, float] = {}
    for mask in range(1 << player_count):
        columns = list(base_columns)
        for player, factor_name in enumerate(names):
            if mask & (1 << player):
                columns.extend(factor_columns[factor_name])
        cache[mask] = r_squared(columns)

    empty_r2 = cache[0]
    full_r2 = cache[(1 << player_count) - 1]
    incremental_r2 = full_r2 - empty_r2
    coefficient_lookup = robust_coefficients.set_index("termino")
    rows: list[dict[str, object]] = []
    for player, factor_name in enumerate(names):
        shapley = 0.0
        for mask in range(1 << player_count):
            if mask & (1 << player):
                continue
            subset_size = mask.bit_count()
            weight = (
                math.factorial(subset_size)
                * math.factorial(player_count - subset_size - 1)
                / math.factorial(player_count)
            )
            shapley += weight * (cache[mask | (1 << player)] - cache[mask])

        terms = factor_columns[factor_name]
        coefficient = math.nan
        p_value = math.nan
        if len(terms) == 1 and terms[0] in coefficient_lookup.index:
            coefficient = float(coefficient_lookup.loc[terms[0], "coeficiente"])
            p_value = float(coefficient_lookup.loc[terms[0], "p_valor"])
        rows.append(
            {
                "factor": factor_name,
                "grupo": factor_specs[factor_name]["grupo"],
                "terminos": ", ".join(terms),
                "coeficiente_modelo": coefficient,
                "p_valor_hac": p_value,
                "shapley_r2": shapley,
                "aporte_r2_puntos_porcentuales": 100.0 * shapley,
                "peso_entre_factores_pct": 100.0 * shapley / incremental_r2,
                "peso_r2_total_pct": 100.0 * shapley / full_r2,
                "r2_base": empty_r2,
                "r2_completo": full_r2,
                "r2_incremental": incremental_r2,
            }
        )

    result = pd.DataFrame(rows).sort_values("shapley_r2", ascending=False).reset_index(drop=True)
    if not np.isclose(result["shapley_r2"].sum(), incremental_r2, atol=1e-10):
        raise AssertionError("La suma Shapley no cierra contra el incremento del R2.")
    if not np.isclose(result["peso_entre_factores_pct"].sum(), 100.0, atol=1e-8):
        raise AssertionError("Los pesos Shapley no suman 100%.")
    return result


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
    model_columns = [
        "ln_trm",
        *ECM_LEVEL_VARIABLES,
        "ln_vix",
        "dln_vix",
        "spread_tes_ust_10y_pp",
        "ln_reservas_netas_sin_flar",
        *LEVEL_COMPONENTS,
        "dummy_pandemia_2020",
    ]
    model_data = data.loc[pd.Timestamp("2006-01-01") :, model_columns].dropna().copy().asfreq("MS")
    if model_data.isna().any().any():
        raise ValueError("La muestra balanceada contiene meses faltantes.")

    components = difference_components(model_data)
    common_index = make_timed_difference_design(
        components, p=3, factor_specs=EXPANDED_FACTOR_SPECS
    )[0].index

    selected_diff, lag_grid_diff = select_timed_difference_model(
        model_data, BASE_FACTOR_SPECS, common_index=common_index
    )
    _, coefficients_diff = tidy_robust_ols(selected_diff.result, maxlags=6)
    diagnostics_diff = diagnostics(selected_diff.result)
    predictions, validation = difference_validation(
        model_data, selected_diff, holdout=min(48, len(selected_diff.y) // 4)
    )
    fitted_diff, contributions_diff = difference_fit_and_contributions(
        model_data, selected_diff
    )

    selected_expanded, lag_grid_expanded = select_timed_difference_model(
        model_data, EXPANDED_FACTOR_SPECS, common_index=common_index
    )
    _, coefficients_expanded = tidy_robust_ols(selected_expanded.result, maxlags=6)
    diagnostics_expanded = diagnostics(selected_expanded.result)
    predictions_expanded, validation_expanded = difference_validation(
        model_data, selected_expanded, holdout=min(48, len(selected_expanded.y) // 4)
    )
    fitted_expanded, contributions_expanded = difference_fit_and_contributions(
        model_data, selected_expanded
    )
    shapley_expanded = exact_shapley_r2(
        selected_expanded, EXPANDED_FACTOR_SPECS, coefficients_expanded
    )

    def out_of_sample_r2(predictions_frame: pd.DataFrame) -> float:
        model_error = (
            predictions_frame["ln_trm_modelo_condicional"]
            - predictions_frame["ln_trm_observada"]
        )
        benchmark_error = (
            predictions_frame["ln_trm_caminata_aleatoria"]
            - predictions_frame["ln_trm_observada"]
        )
        return 1.0 - float(np.square(model_error).sum()) / float(
            np.square(benchmark_error).sum()
        )

    base_validation_row = validation.iloc[0]
    expanded_validation_row = validation_expanded.iloc[0]
    comparison = pd.DataFrame(
        [
            {
                "modelo": "Base",
                "observaciones": int(selected_diff.result.nobs),
                "r_cuadrado": float(selected_diff.result.rsquared),
                "r_cuadrado_ajustado": float(selected_diff.result.rsquared_adj),
                "aic": float(selected_diff.result.aic),
                "bic": float(selected_diff.result.bic),
                "mape_pct": float(base_validation_row["mape_pct"]),
                "acierto_direccion_pct": float(
                    base_validation_row["acierto_direccion_pct"]
                ),
                "r2_fuera_muestra_vs_caminata": out_of_sample_r2(predictions),
            },
            {
                "modelo": "Ampliado historico",
                "observaciones": int(selected_expanded.result.nobs),
                "r_cuadrado": float(selected_expanded.result.rsquared),
                "r_cuadrado_ajustado": float(selected_expanded.result.rsquared_adj),
                "aic": float(selected_expanded.result.aic),
                "bic": float(selected_expanded.result.bic),
                "mape_pct": float(expanded_validation_row["mape_pct"]),
                "acierto_direccion_pct": float(
                    expanded_validation_row["acierto_direccion_pct"]
                ),
                "r2_fuera_muestra_vs_caminata": out_of_sample_r2(
                    predictions_expanded
                ),
            },
        ]
    )

    y = model_data["ln_trm"]
    exog = model_data[ECM_LEVEL_VARIABLES]
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
        [
            "ln_trm",
            *ECM_LEVEL_VARIABLES,
            "ln_vix",
            "spread_tes_ust_10y_pp",
            "ln_reservas_netas_sin_flar",
            "diferencial_inflacion_pp",
        ],
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
    lag_grid_expanded.to_csv(
        RESULTS / "seleccion_rezagos_modelo_ampliado.csv",
        index=False,
        encoding="utf-8-sig",
    )
    coefficients_expanded.to_csv(
        RESULTS / "coeficientes_modelo_ampliado.csv", index=False, encoding="utf-8-sig"
    )
    diagnostics_expanded.to_csv(
        RESULTS / "diagnosticos_modelo_ampliado.csv", index=False, encoding="utf-8-sig"
    )
    fitted_expanded.to_csv(
        RESULTS / "ajuste_historico_modelo_ampliado.csv", encoding="utf-8-sig"
    )
    contributions_expanded.to_csv(
        RESULTS / "contribuciones_modelo_ampliado.csv", encoding="utf-8-sig"
    )
    shapley_expanded.to_csv(
        RESULTS / "pesos_explicativos_modelo_ampliado.csv",
        index=False,
        encoding="utf-8-sig",
    )
    comparison.to_csv(
        RESULTS / "comparacion_modelos.csv", index=False, encoding="utf-8-sig"
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
    predictions_expanded.to_csv(
        RESULTS / "validacion_predicciones_modelo_ampliado.csv", encoding="utf-8-sig"
    )
    validation_expanded.to_csv(
        RESULTS / "validacion_metricas_modelo_ampliado.csv",
        index=False,
        encoding="utf-8-sig",
    )

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
        "modelo_ampliado": "Contabilidad historica mensual en primeras diferencias con 12 factores y errores HAC",
        "ampliado_p_cambio_trm": selected_expanded.p,
        "ampliado_observaciones": int(selected_expanded.result.nobs),
        "ampliado_aic": float(selected_expanded.result.aic),
        "ampliado_bic": float(selected_expanded.result.bic),
        "ampliado_r_cuadrado": float(selected_expanded.result.rsquared),
        "ampliado_r_cuadrado_ajustado": float(
            selected_expanded.result.rsquared_adj
        ),
        "ampliado_temporizacion": "Brent, dolar amplio, VIX, spread TES-Treasury y monedas regionales contemporaneos; variables colombianas de publicacion lenta rezagadas un mes",
        "pesos_metodo": "Shapley/LMG exacto del incremento del R2 sobre intercepto, dinamica de TRM y dummy de pandemia",
        "pesos_suma_pct": float(shapley_expanded["peso_entre_factores_pct"].sum()),
        "shapley_r2_base": float(shapley_expanded["r2_base"].iloc[0]),
        "shapley_r2_completo": float(shapley_expanded["r2_completo"].iloc[0]),
        "shapley_r2_incremental": float(
            shapley_expanded["r2_incremental"].iloc[0]
        ),
        "factor_regional": "Promedio de cambios log estandarizados de BRL, CLP y MXN por USD; parametros calibrados 2006-2019",
        "ipc_eeuu": "CPIAUCNS; octubre de 2025 interpolado linealmente por ausencia de dato oficial",
        "flujos_capital": "Movimientos netos de capital de la balanza cambiaria, BanRep serie 16706",
        "validacion_base_mape_pct": float(base_validation_row["mape_pct"]),
        "validacion_ampliado_mape_pct": float(expanded_validation_row["mape_pct"]),
        "validacion_base_acierto_direccion_pct": float(
            base_validation_row["acierto_direccion_pct"]
        ),
        "validacion_ampliado_acierto_direccion_pct": float(
            expanded_validation_row["acierto_direccion_pct"]
        ),
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
    print("\nComparacion base vs. ampliado")
    print(comparison.to_string(index=False))
    print("\nPesos explicativos Shapley del modelo ampliado")
    print(
        shapley_expanded[
            ["factor", "grupo", "shapley_r2", "peso_entre_factores_pct"]
        ].to_string(index=False)
    )
    print("\nECM exploratorio: coeficientes de largo plazo")
    print(long_run_ecm.to_string(index=False))


if __name__ == "__main__":
    main()
