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
VINTAGES = DATA / "vintages"
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

    weights = pd.read_csv(RESULTS / "explicacion/pesos_explicativos_modelo_ampliado.csv")
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

    bootstrap = pd.read_csv(RESULTS / "explicacion/intervalos_bootstrap_pesos_shapley.csv")
    if set(bootstrap["factor"]) != set(weights["factor"]) or len(bootstrap) != 12:
        raise AssertionError("Los intervalos bootstrap no cubren los 12 factores Shapley.")
    if not bootstrap["replicas_validas"].eq(200).all():
        raise AssertionError("Los intervalos Shapley deben usar 200 réplicas válidas.")
    if not bootstrap["bloque_meses"].eq(12).all():
        raise AssertionError("El bootstrap Shapley debe conservar bloques de 12 meses.")
    if not bootstrap["probabilidad_top3_pct"].between(0, 100).all():
        raise AssertionError("Una probabilidad top 3 quedó fuera de [0, 100].")
    if not np.isclose(bootstrap["probabilidad_top3_pct"].sum(), 300.0, atol=1e-8):
        raise AssertionError("Las probabilidades top 3 no suman tres posiciones.")
    bootstrap_by_factor = bootstrap.set_index("factor")
    weights_by_factor = weights.set_index("factor")
    if not np.allclose(
        bootstrap_by_factor.loc[weights_by_factor.index, "peso_puntual_pct"],
        weights_by_factor["peso_entre_factores_pct"],
        rtol=0.0,
        atol=1e-10,
    ):
        raise AssertionError("Los pesos puntuales del bootstrap no concilian con Shapley exacto.")

    stability_detail = pd.read_csv(
        RESULTS / "explicacion/estabilidad_submuestras_modelo_ampliado.csv"
    )
    stability_summary = pd.read_csv(RESULTS / "explicacion/estabilidad_submuestras_resumen.csv")
    expected_subsamples = {
        "Muestra completa",
        "Primera mitad",
        "Segunda mitad",
        "Prepandemia",
        "2020 en adelante",
    }
    if set(stability_summary["submuestra"]) != expected_subsamples:
        raise AssertionError("Faltan cortes de estabilidad en el resumen.")
    if len(stability_detail) != 60 or not stability_detail.groupby("submuestra").size().eq(12).all():
        raise AssertionError("La estabilidad detallada debe tener 12 factores en cinco cortes.")
    if not stability_summary["correlacion_spearman_rangos_vs_completa"].between(-1, 1).all():
        raise AssertionError("Una correlación de rangos de estabilidad quedó fuera de [-1, 1].")

    baseline_manifest = json.loads(
        (VINTAGES / "2026-08-23" / "manifest.json").read_text(encoding="utf-8")
    )
    if baseline_manifest["origin_date"] != "2026-08-23" or not baseline_manifest["immutable"]:
        raise AssertionError("El baseline de vintages no está marcado como inmutable.")
    for record in baseline_manifest["files"]:
        path = ROOT / record["raw_path"]
        if sha256_file(path) != record["sha256"]:
            raise AssertionError(f"No concilia el baseline de vintages: {record['id']}.")

    alfred_manifest_path = (
        VINTAGES / "historical" / "alfred_factores_pronostico.manifest.json"
    )
    if alfred_manifest_path.exists():
        alfred_manifest = json.loads(alfred_manifest_path.read_text(encoding="utf-8"))
        alfred_path = ROOT / alfred_manifest["path"]
        if sha256_file(alfred_path) != alfred_manifest["sha256"]:
            raise AssertionError("No concilia la huella del histórico ALFRED.")
        alfred = pd.read_csv(alfred_path)
        if alfred["origen_vintage"].nunique() != 48 or alfred["serie_id"].nunique() != 6:
            raise AssertionError("El histórico ALFRED no cubre 48 orígenes y seis series.")
        alfred["origen_vintage"] = pd.to_datetime(alfred["origen_vintage"])
        alfred["fecha_observacion"] = pd.to_datetime(alfred["fecha_observacion"])
        if (alfred["fecha_observacion"] >= alfred["origen_vintage"]).any():
            raise AssertionError("El histórico ALFRED contiene observaciones futuras al origen.")

    fiscal_history = json.loads(
        (VINTAGES / "historical" / "minhacienda" / "version_history.json").read_text(
            encoding="utf-8"
        )
    )
    if len(fiscal_history["versions"]) != 8:
        raise AssertionError("El catálogo fiscal no contiene las ocho versiones verificadas.")

    vintage_coverage = pd.read_csv(RESULTS / "pronostico/cobertura_vintages_pronostico.csv")
    if len(vintage_coverage) != 12:
        raise AssertionError("La cobertura de vintages debe reportar los 12 factores.")
    complete_vintage = vintage_coverage["apto_backtest_genuino"].astype("string").str.lower().eq("true")
    alfred_csv = DATA / "vintages" / "historical" / "alfred_factores_pronostico.csv"
    expected_complete = 3 if alfred_csv.exists() else 0
    if int(complete_vintage.sum()) != expected_complete:
        raise AssertionError(
            f"Se esperan {expected_complete} factores aptos, hay {int(complete_vintage.sum())}."
        )
    if bool(metadata["backtest_genuino_disponible"]):
        raise AssertionError("El backtest no puede rotularse como genuino con cobertura parcial.")

    comparison = pd.read_csv(RESULTS / "explicacion/comparacion_modelos.csv")
    if set(comparison["modelo"]) != {"Base", "Ampliado historico"}:
        raise AssertionError("La comparación no contiene las dos especificaciones esperadas.")
    if comparison["observaciones"].nunique() != 1:
        raise AssertionError("Base y ampliado no usan la misma muestra efectiva.")

    expanded_coefficients = pd.read_csv(
        RESULTS / "explicacion/coeficientes_modelo_ampliado.csv"
    )
    expanded_terms = set(expanded_coefficients["termino"])
    required_active_terms = {
        "D.ln_terminos_intercambio.L0",
        "D.embig_colombia_pp.L0",
        "D.asinh_balanza_comercial.L1",
        "D.asinh_flujos_capital.L1",
        "D.diferencial_bei_5y_pp.L1",
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

    integration = pd.read_csv(RESULTS / "explicacion/pruebas_integracion.csv")
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
        "diferencial_bei_5y_comun_pp",
        "diferencia_comun_menos_separada_pp",
        "dias_comunes",
        "tes_5y_pesos_comun_pct",
        "tes_5y_uvr_comun_pct",
        "bei_eeuu_5y_comun_pct",
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
        "diferencial BEI sobre fechas comunes": (
            monthly["diferencial_bei_5y_comun_pp"],
            monthly["tes_5y_pesos_comun_pct"]
            - monthly["tes_5y_uvr_comun_pct"]
            - monthly["bei_eeuu_5y_comun_pct"],
        ),
    }
    for label, (actual, expected) in identities.items():
        comparable = actual.notna() & expected.notna()
        if not comparable.any() or not np.allclose(
            actual.loc[comparable], expected.loc[comparable], rtol=0.0, atol=1e-8
        ):
            raise AssertionError(f"No concilia la construcción de {label}.")

    bei_aggregation = pd.read_csv(RESULTS / "robustez/comparacion_agregacion_bei_5y.csv")
    if len(bei_aggregation) != 244 or bei_aggregation["dias_comunes"].isna().any():
        raise AssertionError("La comparación BEI debe cubrir 244 meses con fechas comunes.")
    if bei_aggregation["dias_comunes"].min() < 1:
        raise AssertionError("Existe un mes sin cruce diario para las tres curvas BEI.")
    if bei_aggregation["diferencial_bei_5y_pp"].corr(
        bei_aggregation["diferencial_bei_5y_comun_pp"]
    ) < 0.99:
        raise AssertionError("Las dos agregaciones BEI divergen de forma inesperada.")

    bei_stationarity = pd.read_csv(RESULTS / "robustez/pruebas_estacionariedad_bei_5y.csv")
    if len(bei_stationarity) != 24:
        raise AssertionError("Las pruebas BEI no cubren agregaciones, transformaciones y determinísticos.")
    differenced_tests = bei_stationarity.loc[
        bei_stationarity["transformacion"].eq("primera_diferencia")
    ]
    if not differenced_tests.loc[differenced_tests["prueba"].eq("ADF"), "p_valor"].lt(0.05).all():
        raise AssertionError("ADF no respalda la primera diferencia BEI en todas las variantes.")
    if not differenced_tests.loc[differenced_tests["prueba"].eq("KPSS"), "p_valor"].ge(0.05).all():
        raise AssertionError("KPSS rechaza estacionariedad de una primera diferencia BEI.")

    bei_trends = pd.read_csv(RESULTS / "robustez/tendencias_quiebres_bei_5y.csv")
    if len(bei_trends) != 6 or bei_trends["fecha_quiebre_za"].nunique() != 1:
        raise AssertionError("La comparación de tendencias/quiebres BEI está incompleta.")

    bei_specs = pd.read_csv(RESULTS / "robustez/comparacion_especificaciones_bei_5y.csv")
    if len(bei_specs) != 6 or bei_specs["observaciones"].nunique() != 1:
        raise AssertionError("Las seis especificaciones BEI no usan una muestra común.")
    active_bei = bei_specs.loc[bei_specs["especificacion"].str.contains("vigente")].iloc[0]
    if active_bei["bic"] > bei_specs["bic"].min() + 1e-9:
        raise AssertionError("La especificación BEI activa no minimiza el BIC comparado.")

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

    regional_comparison = pd.read_csv(RESULTS / "explicacion/comparacion_factor_regional.csv")
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
        RESULTS / "pronostico/coeficientes_modelo_pronostico.csv"
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

    forecast_metrics = pd.read_csv(RESULTS / "pronostico/validacion_metricas_pronostico.csv")
    forecast_predictions = pd.read_csv(
        RESULTS / "pronostico/validacion_predicciones_pronostico.csv"
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
        "diferencial_bei_5y_comun_pp",
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
        "Robustez",
        "BEI_robustez",
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

    robustness_sheet = workbook["Robustez"]
    bootstrap_header = next(
        (
            row
            for row in range(1, robustness_sheet.max_row + 1)
            if robustness_sheet.cell(row, 1).value == "Factor"
            and robustness_sheet.cell(row, 2).value == "Peso puntual"
        ),
        None,
    )
    if bootstrap_header is None:
        raise AssertionError("No se encontró la tabla bootstrap en Robustez.")
    excel_bootstrap = {
        str(robustness_sheet.cell(row, 1).value): [
            robustness_sheet.cell(row, column).value for column in range(2, 8)
        ]
        for row in range(bootstrap_header + 1, bootstrap_header + 1 + len(bootstrap))
    }
    for record in bootstrap.to_dict("records"):
        values = excel_bootstrap.get(record["factor"])
        if values is None:
            raise AssertionError(f"Falta {record['factor']} en Robustez.")
        expected = [
            record["peso_puntual_pct"] / 100.0,
            record["peso_bootstrap_mediana_pct"] / 100.0,
            record["ic_95_inferior_pct"] / 100.0,
            record["ic_95_superior_pct"] / 100.0,
            (record["ic_95_superior_pct"] - record["ic_95_inferior_pct"]) / 100.0,
            record["probabilidad_top3_pct"] / 100.0,
        ]
        for label, actual, expected_value in zip(
            ["peso", "mediana", "límite inferior", "límite superior", "ancho", "top 3"],
            values,
            expected,
        ):
            assert_close(actual, expected_value, f"Robustez {record['factor']} — {label}")

    bei_sheet = workbook["BEI_robustez"]
    bei_header = next(
        (
            row
            for row in range(1, bei_sheet.max_row + 1)
            if bei_sheet.cell(row, 1).value == "Especificación"
            and bei_sheet.cell(row, 2).value == "Agregación"
        ),
        None,
    )
    if bei_header is None:
        raise AssertionError("No se encontró la comparación de especificaciones en BEI_robustez.")
    excel_bei = {
        str(bei_sheet.cell(row, 1).value): [
            bei_sheet.cell(row, column).value for column in range(5, 11)
        ]
        for row in range(bei_header + 1, bei_header + 1 + len(bei_specs))
    }
    for record in bei_specs.to_dict("records"):
        values = excel_bei.get(record["especificacion"])
        if values is None:
            raise AssertionError(f"Falta {record['especificacion']} en BEI_robustez.")
        expected = [
            record["r_cuadrado_ajustado"],
            record["bic"],
            record["coeficiente_bei_pre_quiebre"],
            record["p_valor_hac_bei_pre_quiebre"],
            record["mape_condicional_pct"] / 100.0,
            record["r2_validacion_condicional_vs_caminata"],
        ]
        for label, actual, expected_value in zip(
            ["R² ajustado", "BIC", "coeficiente", "p HAC", "MAPE", "R² validación"],
            values,
            expected,
        ):
            assert_close(
                actual,
                expected_value,
                f"BEI_robustez {record['especificacion']} — {label}",
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
        "OK: robustez BEI, vintages, bootstrap Shapley, submuestras, pronóstico rezagado y archivo Excel sincronizado."
    )


if __name__ == "__main__":
    main()
