"""
Descarga variables globales de FRED y las consolida en la base mensual activa.

La descarga conserva también series candidatas que no tienen cobertura completa
para la muestra del modelo. Estas series quedan identificadas en
``data/base_global_cobertura.csv`` y no se imputan ni entran automáticamente al
modelo balanceado.

Uso:
    python src/download_global_data.py
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

API_KEY = "dd22ac6406a29199a86edafc2f267524"
SAMPLE_START = pd.Timestamp("2006-01-01")
SAMPLE_END = pd.Timestamp("2026-04-01")

# Las series candidatas se descargan para dejar trazabilidad de cobertura. Solo
# ACTIVE_SERIES puede entrar al modelo mensual de muestra completa.
SERIES = {
    # Tasas, rendimientos y expectativas de inflación de EE. UU.
    "DFII10": "yield_real_10y_tips_pct",
    "DFII5": "yield_real_5y_us_pct",
    "DGS2": "yield_2y_us_pct",
    "DGS10": "yield_10y_us_pct",
    "T10Y2Y": "spread_10y_2y_us_pct",
    "T5YIE": "breakeven_5y_us_pct",
    "T10YIE": "breakeven_10y_us_pct",
    # Commodities y precios externos
    "DCOILBRENTEU": "brent_usd_barril",
    "PALLFNFINDEXM": "commodities_index_imf",
    "GOLDAMGBD228NLBM": "oro_usd_oz",
    # Riesgo e incertidumbre financiera
    "GEPUCURRENT": "epu_global",
    "STLFSI4": "estres_financiero_stl",
    "NFCI": "nfci_chicago",
    "ANFCI": "anfci_chicago",
    "TEDRATE": "ted_spread_pct",
    "BAMLH0A0HYM2": "high_yield_oas_pct",
    # Actividad, empleo y logística
    "MANEMP": "empleo_manufactura_us_miles",
    "INDPRO": "produccion_industrial_us",
    "UNRATE": "desempleo_us_bls_pct",
    "LRUN64TTUSM156S": "desempleo_us_pct",
    "TSIFRGHT": "fletes_transporte_us",
    # China: precios de importación y candidatos de actividad; no se imputan.
    "CHNTOT": "precios_importacion_china",
    "CHNPRINTO01IXPYM": "produccion_industrial_china",
    "CHNLORSGPRTSTSAM": "indicador_lider_china",
    "CHNCPIALLMINMEI": "ipc_china",
    # Dólar amplio mensual alternativo; el modelo usa la serie diaria en raw.
    "TWEXBMTH": "dolar_amplio_mensual",
}

ACTIVE_SERIES = {
    "yield_real_10y_tips_pct",
    "yield_real_5y_us_pct",
    "yield_2y_us_pct",
    "yield_10y_us_pct",
    "spread_10y_2y_us_pct",
    "breakeven_5y_us_pct",
    "breakeven_10y_us_pct",
    "brent_usd_barril",
    "commodities_index_imf",
    "epu_global",
    "estres_financiero_stl",
    "nfci_chicago",
    "anfci_chicago",
    "empleo_manufactura_us_miles",
    "produccion_industrial_us",
    "desempleo_us_pct",
    "fletes_transporte_us",
}

INACTIVE_REASONS = {
    "high_yield_oas_pct": (
        "BAMLH0A0HYM2 solo tiene cobertura reciente en la descarga de FRED; "
        "se conserva como candidata, pero no balancea 2006-01--2026-04."
    ),
    "desempleo_us_bls_pct": (
        "UNRATE tiene un faltante publicado en 2025-10; se conserva como "
        "referencia BLS, pero el modelo usa la serie OECD completa y no imputa."
    ),
    "ted_spread_pct": (
        "TEDRATE termina antes del cierre de la muestra; no se completa con "
        "interpolación ni con otra serie."
    ),
    "produccion_industrial_china": (
        "La serie de actividad industrial china termina antes del cierre de la "
        "muestra; se conserva para futuras muestras cortas."
    ),
    "indicador_lider_china": (
        "El indicador líder de China no cubre todo 2006-01--2026-04; no se "
        "imputa para forzar su entrada."
    ),
    "ipc_china": (
        "El IPC de China tiene cobertura publicada incompleta para el cierre "
        "de la muestra vigente."
    ),
    "precios_importacion_china": (
        "CHNTOT tiene un faltante publicado en 2025-10; se conserva como "
        "proxy de precios externos de China, pero no se imputa ni entra al "
        "modelo balanceado."
    ),
    "dolar_amplio_mensual": (
        "Proxy mensual alternativo; el modelo activo construye el dólar amplio "
        "desde la serie diaria de raw."
    ),
}


def download_fred(series_id: str, name: str) -> pd.Series | None:
    """Descarga una serie de FRED y la convierte a frecuencia mensual."""
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&observation_start=2000-01-01"
        f"&file_type=json&api_key={API_KEY}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "modelo-trm/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as error:
        print(f"  ERROR {series_id}: {error}")
        return None

    rows = []
    for observation in data.get("observations", []):
        if observation["value"] == ".":
            continue
        rows.append(
            {
                "fecha": pd.Timestamp(observation["date"]),
                "valor": float(observation["value"]),
            }
        )

    if not rows:
        return None

    frame = pd.DataFrame(rows).set_index("fecha")
    series = frame["valor"]
    # Series con muchos puntos son diarias/semanales y se promedian por mes.
    if len(series) > 400:
        series = series.resample("MS").mean()
    else:
        series.index = series.index.to_period("M").to_timestamp()
        series = series.groupby(level=0).mean()
    series.name = name
    return series


def coverage_record(
    fred_id: str,
    name: str,
    series: pd.Series | None,
) -> dict[str, object]:
    """Resume cobertura y estado de uso sin rellenar observaciones faltantes."""
    record: dict[str, object] = {
        "fred_id": fred_id,
        "variable": name,
        "declarada_activa": name in ACTIVE_SERIES,
        "observaciones_mensuales": 0,
        "primera_fecha": None,
        "ultima_fecha": None,
        "observaciones_muestra": 0,
        "meses_faltantes_muestra": len(pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS")),
        "cubre_muestra_completa": False,
        "estado": "no_disponible",
        "motivo": "FRED no devolvió observaciones utilizables.",
    }
    if series is None or series.empty:
        return record

    sample = series.reindex(pd.date_range(SAMPLE_START, SAMPLE_END, freq="MS"))
    complete = bool(sample.notna().all())
    record.update(
        {
            "observaciones_mensuales": int(series.notna().sum()),
            "primera_fecha": series.first_valid_index().strftime("%Y-%m-%d"),
            "ultima_fecha": series.last_valid_index().strftime("%Y-%m-%d"),
            "observaciones_muestra": int(sample.notna().sum()),
            "meses_faltantes_muestra": int(sample.isna().sum()),
            "cubre_muestra_completa": complete,
        }
    )
    if name in ACTIVE_SERIES and complete:
        record["estado"] = "activa"
        record["motivo"] = "Cobertura mensual completa en la muestra del modelo."
    elif name in ACTIVE_SERIES:
        record["estado"] = "inactiva_por_cobertura"
        record["motivo"] = (
            "Fue propuesta para el modelo, pero la cobertura mensual no es "
            "completa; no se imputa."
        )
    else:
        record["estado"] = "candidata_no_activa"
        record["motivo"] = INACTIVE_REASONS.get(
            name,
            "Se conserva como serie candidata/documental y no entra al modelo activo.",
        )
    return record


def main() -> None:
    print("=" * 70)
    print("DESCARGA DE VARIABLES GLOBALES DESDE FRED")
    print("=" * 70)

    all_series: dict[str, pd.Series] = {}
    coverage: list[dict[str, object]] = []

    for fred_id, name in SERIES.items():
        series = download_fred(fred_id, name)
        if series is not None and len(series) > 50:
            all_series[name] = series
            print(
                f"  OK: {fred_id:<22} -> {name:<32} "
                f"({len(series)} obs, {series.index.min().date()} a {series.index.max().date()})"
            )
        else:
            print(f"  FAIL: {fred_id}")
            series = None
        coverage.append(coverage_record(fred_id, name, series))
        time.sleep(0.6)

    print(f"\n  Descargadas: {len(all_series)}/{len(SERIES)}")
    base = pd.DataFrame(all_series)
    base.index.name = "fecha"
    base = base.sort_index()
    # Mantener columnas declaradas aun cuando FRED no devuelva observaciones;
    # así la ausencia de high-yield/oro queda visible y auditable, no imputada.
    for name in SERIES.values():
        if name not in base.columns:
            base[name] = pd.Series(index=base.index, dtype="float64")
    base = base.reindex(columns=list(SERIES.values()))

    output = DATA / "base_global_mensual.csv"
    base.to_csv(output, encoding="utf-8-sig", float_format="%.6g")
    coverage_path = DATA / "base_global_cobertura.csv"
    pd.DataFrame(coverage).to_csv(coverage_path, index=False, encoding="utf-8-sig")

    print(f"\n  Base guardada: {output.relative_to(ROOT)}")
    print(f"  Registro de cobertura: {coverage_path.relative_to(ROOT)}")
    print(f"  Shape: {base.shape[0]} meses x {base.shape[1]} variables")
    if not base.empty:
        print(f"  Rango: {base.index.min().date()} a {base.index.max().date()}")

    print("\n  Cobertura por variable:")
    for record in coverage:
        print(
            f"    {record['variable']:<32} {record['estado']:<22} "
            f"muestra válida={record['observaciones_muestra']:>3}/244"
        )

    print("\n" + "=" * 70)
    print(f"  Listo. {len(all_series)} variables en data/base_global_mensual.csv")
    print("  Las series incompletas se conservaron como candidatas, sin imputación.")
    print("=" * 70)


if __name__ == "__main__":
    main()
