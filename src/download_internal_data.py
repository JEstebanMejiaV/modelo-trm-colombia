"""Descarga y audita variables internas colombianas.

Las fuentes se conservan en ``data/raw`` y la matriz de cobertura se escribe en
``data/variables_internas_cobertura.csv``. La auditoría nunca rellena huecos:
una serie solo puede quedar ``activa`` si cubre todos los meses de la muestra
2006-01--2026-04.

Uso desde la raíz del repositorio::

    python src/download_internal_data.py
    python src/download_internal_data.py --force
"""
from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import pandas as pd

from model.config import RAW, SAMPLE_END, SAMPLE_START
from model.loaders import (
    GEIH_COMPONENTS,
    ISE_COMPONENTS,
    build_dataset,
    load_fiscal,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SAMPLE_INDEX = pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")

INTERNAL_DOWNLOADS = {
    "ise_dane_12actividades_jun2026.xlsx": "https://www.dane.gov.co/files/operaciones/ISE/anex-ISE-12actividades-jun2026.xlsx",
    "ise_dane_9actividades_jun2026.xlsx": "https://www.dane.gov.co/files/operaciones/ISE/anex-ISE-9actividades-jun2026.xlsx",
    "ipi_dane_jun2026.xlsx": "https://www.dane.gov.co/files/operaciones/IPI/anex-IPI-jun2026.xlsx",
    "ipp_dane_jul2026.xlsx": "https://www.dane.gov.co/files/operaciones/IPP/anex-IPP-jul2026.xlsx",
    "geih_dane_jun2026.xlsx": "https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-jun2026.xlsx",
    "geih_dane_desestacionalizado_jun2026.xlsx": "https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-Desestacionalizado-jun2026.xlsx",
    "ipc_colombia_banrep.json": "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15000",
}

DANE_SOURCE_PAGE = {
    "ise": "https://www.dane.gov.co/index.php/en/statistics-by-topic/national-accounts/economic-monitor-index-ise",
    "ipi": "https://www.dane.gov.co/index.php/estadisticas-por-tema/industria/indice-de-produccion-industrial-ipi",
    "ipp": "https://www.dane.gov.co/index.php/estadisticas-por-tema/precios-y-costos/indice-de-precios-del-productor-ipp",
    "geih": "https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/mercado-laboral-historicos",
    "ipc": "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15000",
}


def download_sources(force: bool = False) -> None:
    """Descarga instantáneas oficiales sin sobrescribir por defecto."""
    RAW.mkdir(parents=True, exist_ok=True)
    for filename, url in INTERNAL_DOWNLOADS.items():
        target = RAW / filename
        if target.exists() and not force:
            print(f"  EXISTE: {target.relative_to(ROOT)}")
            continue
        request = urllib.request.Request(url, headers={"User-Agent": "modelo-trm-colombia/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            target.write_bytes(response.read())
        print(f"  DESCARGA: {target.relative_to(ROOT)}")


def _date(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _record(
    data: pd.DataFrame,
    *,
    variable: str,
    component: str,
    provider: str,
    identifier: str,
    raw_file: str,
    frequency: str,
    unit: str,
    transformation: str,
    forecast_lag: str,
    declared_status: str,
    reason: str,
    url: str,
) -> dict[str, object]:
    series = data[variable] if variable in data else pd.Series(dtype="float64")
    sample = series.reindex(SAMPLE_INDEX)
    complete = bool(sample.notna().all())
    status = declared_status
    status_reason = reason
    if declared_status == "activa" and not complete:
        status = "inactiva_por_cobertura"
        status_reason = "La fuente no cubre toda la muestra; no se imputan meses faltantes."
    return {
        "variable": variable,
        "componente_modelo": component,
        "proveedor": provider,
        "identificador": identifier,
        "archivo_raw": raw_file,
        "frecuencia": frequency,
        "unidad": unit,
        "primera_fecha": _date(series.first_valid_index()),
        "ultima_fecha": _date(series.last_valid_index()),
        "observaciones_muestra": int(sample.notna().sum()),
        "meses_muestra": len(SAMPLE_INDEX),
        "meses_faltantes_muestra": int(sample.isna().sum()),
        "cubre_muestra_completa": complete,
        "transformacion_historica": transformation,
        "rezago_pronostico_meses": forecast_lag,
        "estado": status,
        "motivo": status_reason,
        "fuente_url": url,
    }


def build_coverage() -> pd.DataFrame:
    """Construye la matriz auditable de variables internas y candidatas."""
    data = build_dataset()
    rows: list[dict[str, object]] = []

    rows.extend(
        _record(
            data,
            variable=variable,
            component="ln_ise_total_dane" if variable == "ise_total_dane" else "",
            provider="DANE",
            identifier="ISE; Cuadro 2; 12 agrupaciones; fila conceptual",
            raw_file="ise_dane_12actividades_jun2026.xlsx",
            frequency="Mensual",
            unit="Índice 2015=100",
            transformation="ln(x) y primera diferencia; el total se activa para evitar 15 términos sectoriales colineales",
            forecast_lag="2",
            declared_status="activa" if variable == "ise_total_dane" else "candidata_no_activa",
            reason=(
                "Indicador total activo en el bloque de condiciones internas."
                if variable == "ise_total_dane"
                else "Cobertura completa, pero se conserva como desagregación auditada y no se añaden términos sectoriales simultáneos."
            ),
            url=DANE_SOURCE_PAGE["ise"],
        )
        for variable in ISE_COMPONENTS.values()
    )

    rows.append(
        _record(
            data,
            variable="ipc_colombia_indice",
            component="ln_ipc_colombia",
            provider="Banco de la República",
            identifier="15000",
            raw_file="ipc_colombia_banrep.json",
            frequency="Mensual",
            unit="Índice de precios",
            transformation="ln(x) y primera diferencia; no se interpola ni se rellena el índice",
            forecast_lag="2",
            declared_status="activa",
            reason="Cobertura mensual completa en la muestra del modelo.",
            url=DANE_SOURCE_PAGE["ipc"],
        )
    )

    for seasonally_adjusted, filename in [
        (False, "geih_dane_jun2026.xlsx"),
        (True, "geih_dane_desestacionalizado_jun2026.xlsx"),
    ]:
        suffix = "_sa_" if seasonally_adjusted else "_"
        for output_name in GEIH_COMPONENTS.values():
            variable = output_name.replace("_dane_", "_dane_sa_") if seasonally_adjusted else output_name
            rows.append(
                _record(
                    data,
                    variable=variable,
                    component="",
                    provider="DANE",
                    identifier="GEIH; Total nacional",
                    raw_file=filename,
                    frequency="Mensual",
                    unit="Porcentaje" if "tasa_" in output_name else "Miles de personas",
                    transformation="Primera diferencia; se conserva la serie oficial y se evita empalmar o imputar la ruptura metodológica",
                    forecast_lag="2",
                    declared_status="candidata_no_activa",
                    reason=(
                        "La serie desestacionalizada tiene dos meses faltantes dentro de la muestra."
                        if seasonally_adjusted
                        else "La serie original no tiene observaciones durante varios meses de 2020 y además requiere cautela por el cambio metodológico."
                    ),
                    url=DANE_SOURCE_PAGE["geih"],
                )
            )

    rows.extend(
        [
            _record(
                data,
                variable="ipi_total_dane",
                component="",
                provider="DANE",
                identifier="IPI; hoja 3; T_IPI",
                raw_file="ipi_dane_jun2026.xlsx",
                frequency="Mensual",
                unit="Índice 2018=100",
                transformation="ln(x) y primera diferencia; no se extiende antes de la primera observación",
                forecast_lag="2",
                declared_status="candidata_no_activa",
                reason="La serie comienza en 2014-01 y no cubre la muestra 2006-01--2026-04.",
                url=DANE_SOURCE_PAGE["ipi"],
            ),
            _record(
                data,
                variable="ipp_produccion_nacional_dane",
                component="",
                provider="DANE",
                identifier="IPP; hoja 1.1; Producción Nacional; TOTAL",
                raw_file="ipp_dane_jul2026.xlsx",
                frequency="Mensual",
                unit="Índice diciembre 2014=100",
                transformation="ln(x) y primera diferencia; no se empalma artificialmente con una base anterior",
                forecast_lag="2",
                declared_status="candidata_no_activa",
                reason="La serie disponible comienza en 2014-12 y no cubre la muestra 2006-01--2026-04.",
                url=DANE_SOURCE_PAGE["ipp"],
            ),
        ]
    )

    existing_specs = [
        ("trm_cop_usd", "", "BanRep", "1", "trm_diaria_banrep.json", "Diaria", "COP por USD", "Promedio mensual; variable objetivo", "0", "activa", "Serie objetivo con cobertura completa.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=1"),
        ("tasa_politica_colombia_pct", "", "BanRep", "59", "tasa_politica_diaria_banrep.json", "Diaria", "% efectivo anual", "Promedio mensual; diferencia dentro del diferencial de tasas", "1", "activa", "Serie interna ya incorporada.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=59"),
        ("terminos_intercambio", "", "BanRep", "15360", "series_15360_15368.json", "Mensual", "Índice", "ln(x) y primera diferencia", "3", "activa", "Serie verificada y activa; publicación tardía.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15360"),
        ("remesas_usd_millones", "", "BanRep", "15363", "remesas_mensuales_banrep.json", "Mensual", "Millones de USD", "Suma móvil de 12 meses, ln(x) y primera diferencia", "2", "activa", "Serie verificada y activa.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15363"),
        ("reservas_netas_sin_flar_usd_millones", "", "BanRep", "15053", "reservas_netas_sin_flar_banrep.json", "Mensual", "Millones de USD", "ln(x) y primera diferencia", "2", "activa", "Serie verificada y activa.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15053"),
        ("tes_5y_pesos_colombia_pct", "", "BanRep", "15273", "tes_5y_pesos_banrep.json", "Diaria", "%", "Promedio mensual; diferencial BEI Colombia", "1", "activa", "Curva nominal verificada.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15273"),
        ("tes_5y_uvr_colombia_pct", "", "BanRep", "15276", "tes_5y_uvr_banrep.json", "Diaria", "% real", "Promedio mensual; diferencial BEI Colombia", "1", "activa", "Curva real verificada.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=15276"),
        ("balanza_comercial_cambiaria_usd_millones", "", "BanRep", "16702", "balanza_comercial_cambiaria_banrep.json", "Mensual", "Millones de USD", "asinh(x/1000) y primera diferencia", "2", "activa", "Serie verificada y activa.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16702"),
        ("flujos_capital_usd_millones", "", "BanRep", "16706", "flujos_capital_totales_banrep.json", "Mensual", "Millones de USD", "asinh(x/1000) y primera diferencia", "2", "activa", "Serie verificada y activa.", "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/consultaSerieParaGraficar?idSerie=16706"),
        ("balance_fiscal_miles_millones_cop", "", "MinHacienda", "GNC mensual", "balance_fiscal_gnc_mensual_trimestral.xlsx", "Mensual", "Miles de millones de COP", "Suma móvil de 12 meses y déficit como porcentaje del PIB", "3", "activa", "Fuente fiscal oficial; puede revisarse.", "https://www.minhacienda.gov.co/documents/d/portal/balance-fiscal-gnc-mensual-y-trimestral?download=true"),
    ]
    for variable, component, provider, identifier, raw_file, frequency, unit, transformation, lag, status, reason, url in existing_specs:
        rows.append(
            _record(
                data,
                variable=variable,
                component=component,
                provider=provider,
                identifier=identifier,
                raw_file=raw_file,
                frequency=frequency,
                unit=unit,
                transformation=transformation,
                forecast_lag=lag,
                declared_status=status,
                reason=reason,
                url=url,
            )
        )

    unavailable = [
        ("agregados_monetarios_colombia", "M1/M2/M3/base monetaria; identificador no activado", "Mensual", "Saldos monetarios", "Δln(x) o crecimiento interanual", "No se activa hasta verificar serie, unidad, revisiones y cobertura en el catálogo BanRep.", "https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/agregados-monetarios-crediticios"),
        ("cartera_crediticia_colombia", "Cartera bruta/financiera; identificador no activado", "Mensual", "Saldo", "Δln(x) o crecimiento interanual", "Candidata documental; no se inventa un identificador por proximidad del catálogo.", "https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/agregados-monetarios-crediticios"),
        ("tasas_domesticas_ibr_dtf_cdt", "IBR/DTF/CDT; identificador no activado", "Diaria/mensual", "Tasa", "Nivel y primera diferencia", "Candidata documental; falta una definición verificable y una descarga reproducible.", "https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas/agregados-monetarios-crediticios"),
        ("mercados_financieros_colombia", "COLCAP/IDXTES/IPVU/UVR; identificador no activado", "Diaria/mensual", "Índice o precio", "Δln(x) o primera diferencia", "Candidata documental; se evita activar proxies no verificados.", "https://suameca.banrep.gov.co/estadisticas-economicas/catalogo"),
        ("sector_externo_trimestral_colombia", "Balanza de pagos/cuenta corriente/IED", "Trimestral", "USD", "No convertir a mensual; crecimiento o asinh en frecuencia original", "No entra al modelo mensual porque desagregar o interpolar sería artificial.", "https://www.banrep.gov.co/es/estadisticas-economicas/series-historicas"),
        ("intervencion_cambiaria_colombia", "Intervenciones oficiales; identificador no verificado", "Eventual", "USD", "Dummy/evento solo con serie oficial validada", "No se activa: no hay catálogo, unidad y cobertura verificadas.", "https://suameca.banrep.gov.co/estadisticas-economicas/catalogo"),
    ]
    for variable, identifier, frequency, unit, transformation, reason, url in unavailable:
        rows.append(
            {
                "variable": variable,
                "componente_modelo": "",
                "proveedor": "BanRep",
                "identificador": identifier,
                "archivo_raw": "",
                "frecuencia": frequency,
                "unidad": unit,
                "primera_fecha": "",
                "ultima_fecha": "",
                "observaciones_muestra": 0,
                "meses_muestra": len(SAMPLE_INDEX),
                "meses_faltantes_muestra": len(SAMPLE_INDEX),
                "cubre_muestra_completa": False,
                "transformacion_historica": transformation,
                "rezago_pronostico_meses": "",
                "estado": "no_disponible",
                "motivo": reason,
                "fuente_url": url,
            }
        )

    return pd.DataFrame(rows).sort_values(["estado", "proveedor", "variable"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="volver a descargar archivos existentes")
    args = parser.parse_args()
    print("Descargando fuentes internas oficiales...")
    download_sources(force=args.force)
    coverage = build_coverage()
    output = DATA / "variables_internas_cobertura.csv"
    coverage.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"Matriz guardada: {output.relative_to(ROOT)}")
    print(coverage["estado"].value_counts().to_string())
    print(f"Muestra auditada: {SAMPLE_START:%Y-%m}--{SAMPLE_END:%Y-%m} ({len(SAMPLE_INDEX)} meses)")


if __name__ == "__main__":
    main()
