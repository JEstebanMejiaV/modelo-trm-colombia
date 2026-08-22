from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DATA = ROOT / "data"
EXCEL = ROOT / "deliverables" / "modelo_trm_colombia.xlsx"


def assert_close(actual: object, expected: float, label: str, atol: float = 1e-8) -> None:
    if actual is None or not np.isclose(
        float(actual), expected, rtol=0.0, atol=atol
    ):
        raise AssertionError(f"{label}: Excel={actual!r}, CSV={expected!r}.")


def main() -> None:
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
    required_flow_terms = {
        "D.asinh_balanza_comercial.L1",
        "D.asinh_flujos_capital.L1",
    }
    if not required_flow_terms.issubset(set(expanded_coefficients["termino"])):
        raise AssertionError(
            "Balanza y capitales deben entrar como primeras diferencias rezagadas."
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
        "spread_tes_ust_10y_pp",
        "ln_reservas_netas_sin_flar",
        "asinh_balanza_comercial",
        "asinh_flujos_capital",
        "diferencial_inflacion_pp",
        "factor_monedas_regionales",
    }
    missing_columns = required_columns.difference(monthly.columns)
    if missing_columns:
        raise AssertionError(f"Faltan variables ampliadas: {sorted(missing_columns)}")
    interpolated_dates = monthly.loc[
        monthly["ipc_eeuu_interpolado"].eq(1), "fecha"
    ].tolist()
    if interpolated_dates != ["2025-10-01"]:
        raise AssertionError(
            "La bandera de interpolación del IPC de EE. UU. debe identificar solo 2025-10."
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

    print(
        "OK: 12 factores, pesos Shapley = 100%, misma muestra y archivo Excel sincronizado."
    )


if __name__ == "__main__":
    main()
