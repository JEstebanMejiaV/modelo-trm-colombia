from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DATA = ROOT / "data"
EXCEL = ROOT / "deliverables" / "modelo_trm_colombia.xlsx"


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

    monthly = pd.read_csv(DATA / "modelo_trm_datos_mensuales.csv", nrows=1)
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

    workbook = load_workbook(EXCEL, read_only=True, data_only=False)
    required_sheets = {
        "Resumen",
        "Modelo_principal",
        "Modelo_ampliado",
        "Pesos_explicativos",
        "Validacion",
        "Fuentes",
    }
    missing_sheets = required_sheets.difference(workbook.sheetnames)
    if missing_sheets:
        raise AssertionError(f"Faltan hojas en el archivo Excel: {sorted(missing_sheets)}")

    print(
        "OK: 12 factores, pesos Shapley = 100%, misma muestra y archivo Excel completo."
    )


if __name__ == "__main__":
    main()
