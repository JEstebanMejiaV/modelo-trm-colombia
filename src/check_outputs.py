from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DATA = ROOT / "data"
EXCEL = ROOT / "deliverables" / "modelo_trm_colombia.xlsx"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_close(actual: object, expected: float, label: str, atol: float = 1e-8) -> None:
    if actual is None or not np.isclose(
        float(actual), expected, rtol=0.0, atol=atol
    ):
        raise AssertionError(f"{label}: Excel={actual!r}, CSV={expected!r}.")


def main() -> None:
    metadata = json.loads((RESULTS / "metadata.json").read_text(encoding="utf-8"))
    for filename, expected_hash in metadata["proxies_snapshot_sha256"].items():
        actual_hash = sha256_file(DATA / "raw" / filename)
        if actual_hash != expected_hash:
            raise AssertionError(
                f"La instantánea raw {filename} no coincide con su SHA-256 registrado."
            )

    weights = pd.read_csv(RESULTS / "pesos_explicativos_modelo_ampliado.csv")
    if len(weights) != 12:
        raise AssertionError("La descomposición debe contener exactamente 12 factores.")
    if (weights["shapley_r2"] < -1e-12).any():
        raise AssertionError("Un aporte Shapley dentro de muestra resultó negativo.")
    if not np.isclose(weights["peso_entre_factores_pct"].sum(), 100.0, atol=1e-8):
        raise AssertionError("Los pesos Shapley no suman 100%.")
    if not np.isclose(
        weights["shapley_r2"].sum(), weights["r2_incremental"].iloc[0], atol=1e-10
    ):
        raise AssertionError("Los aportes Shapley no cierran contra el R² incremental.")

    comparison = pd.read_csv(RESULTS / "comparacion_modelos.csv")
    if set(comparison["modelo"]) != {"Base", "Ampliado historico"}:
        raise AssertionError("La comparación no contiene las dos especificaciones esperadas.")
    if comparison["observaciones"].nunique() != 1:
        raise AssertionError("Base y ampliado no usan la misma muestra efectiva.")

    expanded_coefficients = pd.read_csv(
        RESULTS / "coeficientes_modelo_ampliado.csv"
    )
    expanded_terms = set(expanded_coefficients["termino"])
    required_active_terms = {
        "D.ln_terminos_intercambio.L0",
        "D.embig_colombia_pp.L0",
        "D.asinh_balanza_comercial.L1",
        "D.asinh_flujos_capital.L1",
        "diferencial_bei_5y_pp.L1",
        "factor_monedas_regionales_4.L0",
    }
    missing_active_terms = required_active_terms.difference(expanded_terms)
    if missing_active_terms:
        raise AssertionError(
            "Faltan términos activos en el modelo ampliado: "
            f"{sorted(missing_active_terms)}"
        )
    retired_terms = {
        "D.ln_brent.L0",
        "D.spread_tes_ust_10y_pp.L0",
        "diferencial_inflacion_pp.L1",
    }
    unexpected_retired_terms = retired_terms.intersection(expanded_terms)
    if unexpected_retired_terms:
        raise AssertionError(
            "Persisten términos sustituidos en el modelo ampliado: "
            f"{sorted(unexpected_retired_terms)}"
        )

    integration = pd.read_csv(RESULTS / "pruebas_integracion.csv")
    for variable in ["asinh_balanza_comercial", "asinh_flujos_capital"]:
        transformations = set(
            integration.loc[integration["variable"].eq(variable), "transformacion"]
        )
        if transformations != {"nivel", "primera_diferencia"}:
            raise AssertionError(
                f"Faltan pruebas de integración completas para {variable}."
            )

    monthly_path = DATA / "modelo_trm_datos_mensuales.csv"
    monthly = pd.read_csv(monthly_path)
    required_columns = {
        "terminos_intercambio",
        "ln_terminos_intercambio",
        "embig_colombia_pb",
        "embig_colombia_pp",
        "tes_5y_pesos_colombia_pct",
        "tes_5y_uvr_colombia_pct",
        "bei_colombia_5y_pct",
        "bei_eeuu_5y_pct",
        "diferencial_bei_5y_pp",
        "ln_reservas_netas_sin_flar",
        "asinh_balanza_comercial",
        "asinh_flujos_capital",
        "pen_por_usd",
        "factor_monedas_regionales_3",
        "factor_monedas_regionales_4",
        "factor_monedas_regionales",
    }
    missing_columns = required_columns.difference(monthly.columns)
    if missing_columns:
        raise AssertionError(f"Faltan variables ampliadas: {sorted(missing_columns)}")

    identities = {
        "ln(términos de intercambio)": (
            monthly["ln_terminos_intercambio"],
            np.log(monthly["terminos_intercambio"]),
        ),
        "EMBIG en puntos porcentuales": (
            monthly["embig_colombia_pp"],
            monthly["embig_colombia_pb"] / 100.0,
        ),
        "BEI Colombia a 5 años": (
            monthly["bei_colombia_5y_pct"],
            monthly["tes_5y_pesos_colombia_pct"]
            - monthly["tes_5y_uvr_colombia_pct"],
        ),
        "diferencial BEI Colombia-EE. UU.": (
            monthly["diferencial_bei_5y_pp"],
            monthly["bei_colombia_5y_pct"] - monthly["bei_eeuu_5y_pct"],
        ),
    }
    for label, (actual, expected) in identities.items():
        comparable = actual.notna() & expected.notna()
        if not comparable.any() or not np.allclose(
            actual.loc[comparable], expected.loc[comparable], rtol=0.0, atol=1e-8
        ):
            raise AssertionError(f"No concilia la construcción de {label}.")

    monthly["fecha"] = pd.to_datetime(monthly["fecha"])
    currency_levels = monthly.set_index("fecha")[[
        "brl_por_usd",
        "clp_por_usd",
        "mxn_por_usd",
        "pen_por_usd",
    ]]
    currency_changes = np.log(currency_levels).diff()
    calibration = currency_changes.loc["2006-01-01":"2019-12-01"]
    standardized = (currency_changes - calibration.mean()) / calibration.std(ddof=0)
    expected_factor_3 = standardized[[
        "brl_por_usd", "clp_por_usd", "mxn_por_usd"
    ]].mean(axis=1, skipna=False)
    expected_factor_4 = standardized.mean(axis=1, skipna=False)
    regional_identities = {
        "factor regional de tres monedas": expected_factor_3,
        "factor regional de cuatro monedas": expected_factor_4,
        "alias regional activo": expected_factor_4,
    }
    monthly_indexed = monthly.set_index("fecha")
    for label, expected in regional_identities.items():
        column = {
            "factor regional de tres monedas": "factor_monedas_regionales_3",
            "factor regional de cuatro monedas": "factor_monedas_regionales_4",
            "alias regional activo": "factor_monedas_regionales",
        }[label]
        actual = monthly_indexed[column]
        comparable = actual.notna() & expected.notna()
        if not comparable.any() or not np.allclose(
            actual.loc[comparable], expected.loc[comparable], rtol=0.0, atol=2e-8
        ):
            raise AssertionError(f"No concilia la construcción de {label}.")

    regional_comparison = pd.read_csv(RESULTS / "comparacion_factor_regional.csv")
    expected_uses = {
        "Explicación histórica",
        "Pronóstico con rezagos de publicación",
    }
    expected_compositions = {"BRL, CLP y MXN", "BRL, CLP, MXN y PEN"}
    if len(regional_comparison) != 4:
        raise AssertionError("La comparación regional debe contener exactamente cuatro variantes.")
    if set(regional_comparison["uso"]) != expected_uses:
        raise AssertionError("La comparación regional no separa explicación y pronóstico.")
    if set(regional_comparison["monedas"]) != expected_compositions:
        raise AssertionError("La comparación regional no contiene factores de tres y cuatro monedas.")
    if regional_comparison["correlacion_factores_3_4"].nunique() != 1:
        raise AssertionError("La correlación de factores regionales no es consistente.")

    historical_variants = regional_comparison.loc[
        regional_comparison["uso"].eq("Explicación histórica")
    ].set_index("monedas")
    forecast_variants = regional_comparison.loc[
        regional_comparison["uso"].eq("Pronóstico con rezagos de publicación")
    ].set_index("monedas")
    if historical_variants.loc["BRL, CLP, MXN y PEN", "bic"] >= historical_variants.loc[
        "BRL, CLP y MXN", "bic"
    ]:
        raise AssertionError("PEN no mejora el BIC de la explicación histórica.")
    if forecast_variants.loc["BRL, CLP y MXN", "bic"] >= forecast_variants.loc[
        "BRL, CLP, MXN y PEN", "bic"
    ]:
        raise AssertionError("La selección de tres monedas no minimiza el BIC del pronóstico.")

    forecast_coefficients = pd.read_csv(
        RESULTS / "coeficientes_modelo_pronostico.csv"
    )
    forecast_terms = set(forecast_coefficients["termino"])
    if "factor_monedas_regionales_3.L1" not in forecast_terms:
        raise AssertionError("El pronóstico no usa la composición regional seleccionada.")
    for term in forecast_terms.difference({"const", "dummy_pandemia_2020"}):
        match = re.search(r"\.L(\d+)$", term)
        if match is None or int(match.group(1)) < 1:
            raise AssertionError(
                f"El pronóstico contiene información contemporánea o sin rezago: {term}."
            )

    forecast_metrics = pd.read_csv(RESULTS / "validacion_metricas_pronostico.csv")
    forecast_predictions = pd.read_csv(
        RESULTS / "validacion_predicciones_pronostico.csv"
    )
    if set(forecast_metrics["modelo"]) != {
        "Pronóstico con rezagos de publicación",
        "Caminata aleatoria",
    }:
        raise AssertionError("Faltan los dos modelos de la validación de pronóstico.")
    if len(forecast_predictions) != 48 or not forecast_metrics["observaciones"].eq(48).all():
        raise AssertionError("La validación de pronóstico debe cubrir exactamente 48 meses.")

    sample = pd.read_csv(DATA / "modelo_trm_muestra_estimacion.csv")
    required_sample_columns = {
        "ln_terminos_intercambio",
        "embig_colombia_pp",
        "diferencial_bei_5y_pp",
        "factor_monedas_regionales_3",
        "factor_monedas_regionales_4",
    }
    missing_sample_columns = required_sample_columns.difference(sample.columns)
    if missing_sample_columns:
        raise AssertionError(
            "Faltan sustituciones activas en la muestra de estimación: "
            f"{sorted(missing_sample_columns)}"
        )

    workbook = load_workbook(EXCEL, data_only=True)
    required_sheets = {
        "Resumen",
        "Datos_fuente",
        "Transformaciones",
        "Modelo_principal",
        "Modelo_ampliado",
        "Pesos_explicativos",
        "Validacion",
        "Pronostico",
        "ECM_exploratorio",
        "Diagnosticos",
        "Variables",
        "Fuentes",
    }
    missing_sheets = required_sheets.difference(workbook.sheetnames)
    if missing_sheets:
        raise AssertionError(f"Faltan hojas en el archivo Excel: {sorted(missing_sheets)}")

    # El CI no reconstruye el archivo Excel. Estas conciliaciones impiden que un
    # cambio de resultados deje versionado un archivo Excel desactualizado.
    weights_sheet = workbook["Pesos_explicativos"]
    header_row = next(
        (
            row
            for row in range(1, weights_sheet.max_row + 1)
            if weights_sheet.cell(row, 1).value == "Factor"
            and weights_sheet.cell(row, 4).value == "Peso entre factores"
        ),
        None,
    )
    if header_row is None:
        raise AssertionError("No se encontró la tabla de pesos en el archivo Excel.")
    excel_weights = {}
    for row in range(header_row + 1, header_row + 1 + len(weights)):
        factor = weights_sheet.cell(row, 1).value
        if factor:
            excel_weights[str(factor)] = {
                "shapley_r2": weights_sheet.cell(row, 3).value,
                "peso": weights_sheet.cell(row, 4).value,
                "peso_total": weights_sheet.cell(row, 5).value,
            }
    if set(excel_weights) != set(weights["factor"]):
        raise AssertionError("Los factores del archivo Excel no coinciden con el CSV Shapley.")
    for record in weights.to_dict("records"):
        excel_record = excel_weights[record["factor"]]
        assert_close(excel_record["shapley_r2"], record["shapley_r2"], record["factor"])
        assert_close(
            excel_record["peso"],
            record["peso_entre_factores_pct"] / 100.0,
            f"Peso de {record['factor']}",
        )
        assert_close(
            excel_record["peso_total"],
            record["peso_r2_total_pct"] / 100.0,
            f"Peso total de {record['factor']}",
        )

    summary = workbook["Resumen"]
    comparison_header = next(
        (
            row
            for row in range(1, summary.max_row + 1)
            if summary.cell(row, 8).value == "Modelo"
            and summary.cell(row, 9).value == "Obs."
        ),
        None,
    )
    if comparison_header is None:
        raise AssertionError("No se encontró la comparación de modelos en el archivo Excel.")
    excel_comparison = {
        str(summary.cell(row, 8).value): [
            summary.cell(row, column).value for column in range(9, 15)
        ]
        for row in range(comparison_header + 1, comparison_header + 3)
    }
    for record in comparison.to_dict("records"):
        values = excel_comparison.get(record["modelo"])
        if values is None:
            raise AssertionError(f"Falta {record['modelo']} en la comparación del archivo Excel.")
        expected = [
            record["observaciones"],
            record["r_cuadrado_ajustado"],
            record["aic"],
            record["bic"],
            record["mape_pct"] / 100.0,
            record["acierto_direccion_pct"] / 100.0,
        ]
        for label, actual, expected_value in zip(
            ["observaciones", "R² ajustado", "AIC", "BIC", "MAPE", "dirección"],
            values,
            expected,
        ):
            assert_close(actual, expected_value, f"{record['modelo']} — {label}")

    forecast_sheet = workbook["Pronostico"]
    forecast_header = next(
        (
            row
            for row in range(1, forecast_sheet.max_row + 1)
            if forecast_sheet.cell(row, 1).value == "Modelo"
            and forecast_sheet.cell(row, 2).value == "Observaciones"
        ),
        None,
    )
    if forecast_header is None:
        raise AssertionError("No se encontró la tabla de pronóstico en el archivo Excel.")
    excel_forecast = {
        str(forecast_sheet.cell(row, 1).value): [
            forecast_sheet.cell(row, column).value for column in range(2, 7)
        ]
        for row in range(forecast_header + 1, forecast_header + 3)
    }
    for record in forecast_metrics.to_dict("records"):
        values = excel_forecast.get(record["modelo"])
        if values is None:
            raise AssertionError(
                f"Falta {record['modelo']} en la tabla de pronóstico del archivo Excel."
            )
        expected = [
            record["observaciones"],
            record["mae_log"],
            record["rmse_log"],
            record["mape_pct"] / 100.0,
            None
            if pd.isna(record["acierto_direccion_pct"])
            else record["acierto_direccion_pct"] / 100.0,
        ]
        for label, actual, expected_value in zip(
            ["observaciones", "MAE", "RMSE", "MAPE", "dirección"],
            values,
            expected,
        ):
            if expected_value is None:
                if actual is not None:
                    raise AssertionError(
                        f"{record['modelo']} — {label}: se esperaba una celda vacía."
                    )
            else:
                assert_close(
                    actual,
                    expected_value,
                    f"{record['modelo']} — {label}",
                )

    print(
        "OK: PEN, factores regionales 3/4, pronóstico rezagado, 12 factores y archivo Excel sincronizado."
    )


if __name__ == "__main__":
    main()
