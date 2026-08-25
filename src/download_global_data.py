"""
Descarga todas las variables académicas de FRED y las consolida en un CSV.

Variables:
- DFII10: US 10Y real yield (TIPS)
- GOLDPMGBD228NLBM: Gold PM fix (London, USD/oz)
- GEPUCURRENT: Global Economic Policy Uncertainty
- PALLFNFINDEXM: All Commodities Price Index (IMF)
- MANEMP: US Manufacturing Employment (thousands)
- DGS2: US 2Y Treasury Constant Maturity
- DGS10: US 10Y Treasury (para spread 10Y-2Y)
- TEDRATE: TED spread (proxy stress interbancario)
- STLFSI4: St. Louis Financial Stress Index
- DCOILBRENTEU: Brent crude oil (EUR, diario)
- T10Y2Y: 10Y-2Y Treasury spread (yield curve)
- BAMLH0A0HYM2: US High Yield OAS (risk appetite)

Uso:
    python src/download_academic_data.py
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DATA = ROOT / "data"

API_KEY = "dd22ac6406a29199a86edafc2f267524"

SERIES = {
    # Tasas y yields
    "DFII10": "yield_real_10y_tips_pct",
    "DGS2": "yield_2y_us_pct",
    "DGS10": "yield_10y_us_pct",
    "T10Y2Y": "spread_10y_2y_us_pct",
    # Commodities
    "DCOILBRENTEU": "brent_usd_barril",
    "PALLFNFINDEXM": "commodities_index_imf",
    "GOLDPMGBD228NLBM": "gold_usd_oz",
    # Risk / Uncertainty
    "GEPUCURRENT": "epu_global",
    "STLFSI4": "estres_financiero_stl",
    "TEDRATE": "ted_spread_pct",
    "BAMLH0A0HYM2": "high_yield_oas_pct",
    # Real economy
    "MANEMP": "empleo_manufactura_us_miles",
    "INDPRO": "produccion_industrial_us",
    "UNRATE": "desempleo_us_pct",
    # Dollar
    "TWEXBMTH": "dolar_amplio_mensual",
}


def download_fred(series_id: str, name: str) -> pd.Series | None:
    """Descarga una serie de FRED y la convierte a mensual."""
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&observation_start=2000-01-01"
        f"&file_type=json&api_key={API_KEY}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "modelo-trm/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR {series_id}: {e}")
        return None

    rows = []
    for obs in data.get("observations", []):
        if obs["value"] == ".":
            continue
        rows.append({"fecha": pd.Timestamp(obs["date"]), "valor": float(obs["value"])})

    if not rows:
        return None

    df = pd.DataFrame(rows).set_index("fecha")
    series = df["valor"]
    # Si hay más de 300 obs, probablemente es diaria -> agregar a mensual
    if len(series) > 400:
        series = series.resample("MS").mean()
    else:
        series.index = series.index.to_period("M").to_timestamp()
        series = series.groupby(level=0).mean()
    series.name = name
    return series


def main():
    print("=" * 70)
    print("DESCARGA DE VARIABLES ACADÉMICAS DESDE FRED")
    print("=" * 70)

    all_series = {}
    failed = []

    for fred_id, name in SERIES.items():
        s = download_fred(fred_id, name)
        if s is not None and len(s) > 50:
            all_series[name] = s
            print(f"  OK: {fred_id:<20} -> {name:<30} ({len(s)} obs, {s.index.min().date()} a {s.index.max().date()})")
        else:
            failed.append(fred_id)
            print(f"  FAIL: {fred_id}")
        time.sleep(0.6)

    # Consolidar en un solo DataFrame
    print(f"\n  Descargadas: {len(all_series)}/{len(SERIES)}")
    if failed:
        print(f"  Fallidas: {failed}")

    # Crear base consolidada
    base = pd.DataFrame(all_series)
    base.index.name = "fecha"
    base = base.sort_index()

    # Guardar
    output = DATA / "base_variables_academicas.csv"
    base.to_csv(output, encoding="utf-8-sig", float_format="%.6g")
    print(f"\n  Base guardada: {output.relative_to(ROOT)}")
    print(f"  Shape: {base.shape[0]} meses x {base.shape[1]} variables")
    print(f"  Rango: {base.index.min().date()} a {base.index.max().date()}")

    # Resumen de cobertura
    print(f"\n  Cobertura por variable:")
    for col in base.columns:
        valid = base[col].notna().sum()
        first = base[col].first_valid_index()
        last = base[col].last_valid_index()
        print(f"    {col:<30} {valid:>4} obs  ({first.date() if first else '?'} a {last.date() if last else '?'})")

    print("\n" + "=" * 70)
    print(f"  Listo. {len(all_series)} variables en data/base_variables_academicas.csv")
    print("=" * 70)


if __name__ == "__main__":
    main()
