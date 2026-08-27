from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from trm_model.data.fred import redact_fred_api_key, require_fred_api_key
from trm_model.paths import project_paths

ROOT = project_paths().root
VINTAGES = ROOT / "data" / "vintages"
SOURCES = ROOT / "data" / "catalog" / "sources.json"
HISTORICAL = VINTAGES / "historical"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "modelo-trm-colombia-vintage-archive/1.0"
)

ALFRED_SERIES = [
    "FEDFUNDS",
    "DTWEXBGS",
    "VIXCLS",
    "CCUSMA02BRM618N",
    "CCUSMA02CLM618N",
    "CCUSMA02MXM618N",
]

FISCAL_VERSIONS = [
    ("2025-10-17", "18.0"),
    ("2025-11-14", "19.0"),
    ("2025-11-28", "20.0"),
    ("2025-12-15", "21.0"),
    ("2026-02-06", "22.0"),
    ("2026-03-02", "23.0"),
    ("2026-04-14", "24.0"),
    ("2026-06-22", "25.0"),
]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sources() -> list[dict[str, str]]:
    payload = json.loads(SOURCES.read_text(encoding="utf-8"))
    return [source for source in payload["sources"] if source.get("status") == "active"]


def request_bytes(url: str) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
        metadata = {
            "final_url": response.geturl(),
            "content_type": response.headers.get("Content-Type", ""),
            "last_modified": response.headers.get("Last-Modified", ""),
        }
    if not content:
        raise ValueError(f"La descarga quedó vacía: {url}")
    return content, metadata


def request_bytes_with_retries(
    url: str, attempts: int = 4
) -> tuple[bytes, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return request_bytes(url)
        except Exception as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def dated_url(template: str, origin_date: str) -> str:
    origin = date.fromisoformat(origin_date)
    return template.format(
        origin_date_bcrp=f"{origin.year}-{origin.month}-{origin.day}",
        origin_month_bcrp=f"{origin.year}-{origin.month}",
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def baseline(origin_date: str) -> None:
    target = VINTAGES / origin_date
    manifest_path = target / "manifest.json"
    if target.exists():
        raise FileExistsError(f"Ya existe el vintage {origin_date}; no se sobrescribe.")
    target.mkdir(parents=True)
    files = []
    for source in load_sources():
        path = ROOT / source["raw_path"]
        if not path.exists():
            raise FileNotFoundError(path)
        files.append(
            {
                **source,
                "id": source["source_id"],
                "storage": "referencia_inmutable_al_raw_versionado",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_json(
        manifest_path,
        {
            "schema_version": 1,
            "origin_date": origin_date,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "baseline",
            "immutable": True,
            "files": files,
        },
    )
    print(f"Baseline archivado: {manifest_path.relative_to(ROOT)}")


def snapshot(origin_date: str) -> None:
    target = VINTAGES / origin_date
    if target.exists():
        raise FileExistsError(f"Ya existe el vintage {origin_date}; no se sobrescribe.")
    files_dir = target / "files"
    files_dir.mkdir(parents=True)
    files = []
    try:
        for source in load_sources():
            if source.get("input_kind", "raw") == "derived" or not source.get("url"):
                path = ROOT / source["raw_path"]
                if not path.exists():
                    raise FileNotFoundError(path)
                suffix = Path(source["raw_path"]).suffix
                output = files_dir / f"{source['source_id']}{suffix}"
                output.write_bytes(path.read_bytes())
                files.append(
                    {
                        **source,
                        "id": source["source_id"],
                        "requested_url": None,
                        "archived_path": output.relative_to(ROOT).as_posix(),
                        "storage": "copia_local_versionada",
                        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                        "bytes": output.stat().st_size,
                        "sha256": sha256_file(output),
                    }
                )
                continue
            requested_url = dated_url(source["url"], origin_date)
            content, response = request_bytes(requested_url)
            suffix = Path(source["raw_path"]).suffix
            output = files_dir / f"{source['source_id']}{suffix}"
            output.write_bytes(content)
            files.append(
                {
                    **source,
                    "id": source["source_id"],
                    "requested_url": requested_url,
                    "archived_path": output.relative_to(ROOT).as_posix(),
                    "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                    "bytes": len(content),
                    "sha256": sha256_bytes(content),
                    **response,
                }
            )
        write_json(
            target / "manifest.json",
            {
                "schema_version": 1,
                "origin_date": origin_date,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "mode": "snapshot",
                "immutable": True,
                "files": files,
            },
        )
    except Exception:
        # Se conserva el directorio parcial para auditoría; nunca se presenta como
        # snapshot completo porque carece de manifest.json.
        raise
    print(f"Snapshot completo: {target.relative_to(ROOT)}")


def month_origins(start: str, end: str) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="MS")


def parse_alfred_response(
    content: bytes,
    origin: pd.Timestamp,
    series_id: str,
    observation_start: str,
    observation_end: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    sources: list[tuple[str, object]] = []
    if content.startswith(b"PK"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.namelist():
                if member.lower().endswith(".csv"):
                    sources.append((Path(member).stem, archive.read(member)))
    else:
        sources.append(("serie", content))
    for frequency, source in sources:
        frame = pd.read_csv(io.BytesIO(source), dtype="string")
        if frame.empty:
            continue
        date_column = frame.columns[0]
        value_column = next(
            (
                column
                for column in frame.columns[1:]
                if column == series_id or column.startswith(f"{series_id}_")
            ),
            None,
        )
        if value_column is None:
            continue
        observed_dates = pd.to_datetime(frame[date_column], errors="coerce")
        values = pd.to_numeric(frame[value_column], errors="coerce")
        valid = (
            observed_dates.between(observation_start, observation_end)
            & values.notna()
        )
        for observed, value in zip(observed_dates.loc[valid], values.loc[valid]):
            rows.append(
                {
                    "origen_vintage": origin.strftime("%Y-%m-%d"),
                    "frecuencia_archivo": frequency,
                    "fecha_observacion": observed.strftime("%Y-%m-%d"),
                    "serie_id": series_id,
                    "valor": float(value),
                }
            )
    if not rows:
        raise ValueError(f"ALFRED no devolvió {series_id} para {origin:%Y-%m-%d}.")
    if max(row["fecha_observacion"] for row in rows) > observation_end:
        raise AssertionError(f"{series_id} contiene observaciones futuras en {origin:%Y-%m-%d}.")
    return rows


def download_alfred_vintage(
    origin: pd.Timestamp, series_id: str, api_key: str
) -> list[dict[str, object]]:
    """Descarga un vintage desde la API oficial de FRED (realtime)."""
    observation_start = (origin - pd.DateOffset(months=4)).strftime("%Y-%m-%d")
    observation_end = (origin - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    origin_str = origin.strftime("%Y-%m-%d")
    cache_dir = HISTORICAL / "alfred_cache" / origin_str
    cache_path = cache_dir / f"{series_id}.json"

    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}"
            f"&realtime_start={origin_str}&realtime_end={origin_str}"
            f"&observation_start={observation_start}&observation_end={observation_end}"
            f"&file_type=json"
            f"&api_key={api_key}"
        )
        try:
            content, _ = request_bytes_with_retries(url)
        except Exception as error:
            raise RuntimeError(redact_fred_api_key(error, api_key)) from None
        data = json.loads(content)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    rows: list[dict[str, object]] = []
    for obs in data.get("observations", []):
        value = obs.get("value", ".")
        if value == ".":
            continue
        obs_date = obs["date"]
        if obs_date >= origin_str:
            continue
        rows.append({
            "origen_vintage": origin_str,
            "serie_id": series_id,
            "fecha_observacion": obs_date,
            "valor": float(value),
            "realtime_start": obs.get("realtime_start", ""),
            "realtime_end": obs.get("realtime_end", ""),
        })
    return rows


def alfred_history(start: str, end: str, force: bool) -> None:
    """Descarga vintages completos de las series FRED via API oficial."""
    api_key = require_fred_api_key()

    HISTORICAL.mkdir(parents=True, exist_ok=True)
    output = HISTORICAL / "alfred_factores_pronostico.csv"
    manifest_path = HISTORICAL / "alfred_factores_pronostico.manifest.json"
    if (output.exists() or manifest_path.exists()) and not force:
        raise FileExistsError(
            "El archivo ALFRED ya existe; use --force para regenerarlo."
        )

    all_rows: list[dict[str, object]] = []
    origins = month_origins(start, end)
    total = len(origins) * len(ALFRED_SERIES)
    errors: list[str] = []
    count = 0

    for origin in origins:
        for series_id in ALFRED_SERIES:
            try:
                rows = download_alfred_vintage(origin, series_id, api_key)
                all_rows.extend(rows)
            except Exception as error:
                message = redact_fred_api_key(error, api_key)
                errors.append(f"{origin:%Y-%m-%d} {series_id}: {message}")
            count += 1
            if count % 24 == 0 or count == total:
                print(
                    f"  {count}/{total} requests ({count - len(errors)} OK, {len(errors)} errores)",
                    flush=True,
                )
            time.sleep(0.6)  # respetar rate limit de 120 req/min

    if errors:
        preview = "\n".join(errors[:10])
        raise RuntimeError(
            f"Quedaron {len(errors)} solicitudes ALFRED pendientes.\n{preview}"
        )

    frame = pd.DataFrame(all_rows).sort_values(
        ["origen_vintage", "serie_id", "fecha_observacion"]
    )
    frame.to_csv(output, index=False, encoding="utf-8-sig", float_format="%.10g")
    write_json(
        manifest_path,
        {
            "schema_version": 2,
            "provider": "Federal Reserve Bank of St. Louis, FRED API",
            "endpoint": "https://api.stlouisfed.org/fred/series/observations",
            "method": "realtime_start=realtime_end=origin_date",
            "series": ALFRED_SERIES,
            "origin_start": origins.min().strftime("%Y-%m-%d"),
            "origin_end": origins.max().strftime("%Y-%m-%d"),
            "origins": len(origins),
            "rows": len(frame),
            "raw_responses": total,
            "cache_path": "data/vintages/historical/alfred_cache",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "path": output.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(output),
        },
    )
    print(f"\nDescarga completa: {output.relative_to(ROOT)} ({len(frame)} filas)")


def fiscal_history(force: bool) -> None:
    target = HISTORICAL / "minhacienda"
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "manifest.json"
    if manifest_path.exists() and not force:
        raise FileExistsError("El archivo fiscal histórico ya existe; use --force para regenerarlo.")
    files = []
    for origin_date, version in FISCAL_VERSIONS:
        url = (
            "https://www.minhacienda.gov.co/documents/d/portal/"
            f"balance-fiscal-gnc-mensual-y-trimestral?download=true&version={version}"
        )
        content, response = request_bytes(url)
        if not content.startswith(b"PK"):
            raise ValueError(f"La versión fiscal {version} no es un XLSX válido.")
        output = target / f"{origin_date}_v{version}.xlsx"
        if output.exists() and not force:
            raise FileExistsError(output)
        output.write_bytes(content)
        files.append(
            {
                "origin_date": origin_date,
                "version": version,
                "requested_url": url,
                "path": output.relative_to(ROOT).as_posix(),
                "bytes": len(content),
                "sha256": sha256_bytes(content),
                **response,
            }
        )
        print(f"MinHacienda: versión {version}")
    write_json(
        manifest_path,
        {
            "schema_version": 1,
            "provider": "Ministerio de Hacienda y Crédito Público",
            "document": "Balance fiscal GNC mensual y trimestral",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "immutable": True,
            "files": files,
        },
    )


def import_pit(
    *,
    origin_date: str,
    source_file: str,
    evidence_file: str,
    available_through: str,
    vintage_id: str,
    source_id: str = "banrep_trm_1",
) -> None:
    """Importa un artefacto oficial PIT sin convertir raw ni sobrescribir vintages."""

    from forecast_longterm.wavelet_optimization.ingestion import materialize_pit_snapshot

    archive = materialize_pit_snapshot(
        source_file=source_file,
        evidence_file=evidence_file,
        origin_date=origin_date,
        available_through=available_through,
        vintage_id=vintage_id,
        source_id=source_id,
        paths=ROOT,
    )
    print(
        "Snapshot PIT materializado: "
        f"{archive.manifest_path.relative_to(ROOT)} "
        f"(sha256={archive.sha256})"
    )


def coverage() -> None:
    output = ROOT / "results" / "pronostico" / "cobertura_vintages_pronostico.csv"
    alfred_csv = HISTORICAL / "alfred_factores_pronostico.csv"

    # Determinar cobertura real: si el CSV ALFRED existe, contar orígenes por serie
    alfred_coverage: dict[str, int] = {}
    if alfred_csv.exists():
        alfred = pd.read_csv(alfred_csv)
        alfred_coverage = (
            alfred.groupby("serie_id")["origen_vintage"].nunique().to_dict()
        )

    def alfred_origins(series_id: str) -> int:
        return alfred_coverage.get(series_id, 0)

    # Cobertura del diferencial de tasas = min(BanRep 59, FEDFUNDS)
    # BanRep no tiene vintages; FEDFUNDS sí → parcial
    diff_tasas_origins = min(0, alfred_origins("FEDFUNDS"))  # BanRep limita

    # Factor regional 3 monedas = min(BRL, CLP, MXN)
    regional_origins = min(
        alfred_origins("CCUSMA02BRM618N"),
        alfred_origins("CCUSMA02CLM618N"),
        alfred_origins("CCUSMA02MXM618N"),
    )

    rows = [
        ("Términos de intercambio", "BanRep 15360", "No disponible", 0, "BanRep no publica vintages"),
        ("Remesas", "BanRep 15363", "No disponible", 0, "BanRep no publica vintages"),
        ("Diferencial de tasas", "BanRep 59 + FRED FEDFUNDS", "Parcial (FEDFUNDS completo, BanRep sin vintages)", diff_tasas_origins, "FEDFUNDS descargado via API FRED; BanRep 59 sin histórico"),
        ("Déficit fiscal", "MinHacienda", "Catalogado, descarga bloqueada", 0, "8 versiones identificadas; portal impide descarga automatizada"),
        ("Dólar amplio", "FRED DTWEXBGS", "Completo" if alfred_origins("DTWEXBGS") == 48 else "Pendiente", alfred_origins("DTWEXBGS"), "API FRED con realtime vintage"),
        ("VIX", "FRED VIXCLS", "Completo" if alfred_origins("VIXCLS") == 48 else "Pendiente", alfred_origins("VIXCLS"), "API FRED con realtime vintage"),
        ("Riesgo soberano EMBIG Colombia", "BCRPData PD04715XD", "No disponible", 0, "BCRPData no publica vintages"),
        ("Reservas internacionales", "BanRep 15053", "No disponible", 0, "BanRep no publica vintages"),
        ("Balanza comercial cambiaria", "BanRep 16702", "No disponible", 0, "BanRep no publica vintages"),
        ("Flujos netos de capital", "BanRep 16706", "No disponible", 0, "BanRep no publica vintages"),
        ("Diferencial de compensación inflacionaria 5 años", "BanRep 15273/15276 + Fed GSW", "No disponible", 0, "Ningún componente tiene vintages completos"),
        ("Actividad y precios domésticos", "DANE ISE total + BanRep IPC 15000", "No disponible", 0, "ISE e IPC no publican vintages históricos; se conserva el snapshot actual sin imputación"),
        ("Condiciones financieras, commodities y actividad internacional", "FRED: TIPS, Treasury, Brent, commodities, EPU, STLFSI, empleo y producción industrial", "No disponible", 0, "Base global mensual sin vintages históricos consolidados"),
        ("Monedas regionales", "FRED BRL/CLP/MXN", "Completo" if regional_origins == 48 else "Parcial", regional_origins, "Factor de 3 monedas; API FRED con realtime vintage"),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "factor",
            "fuentes",
            "estado_vintages_2022_05_a_2026_04",
            "origenes_completos_de_48",
            "detalle",
        ],
    )
    frame["cobertura_pct"] = 100.0 * frame["origenes_completos_de_48"] / 48.0
    frame["archivo_hacia_adelante_desde"] = "2026-08-23"
    frame["apto_backtest_genuino"] = frame["origenes_completos_de_48"].eq(48)
    frame.to_csv(output, index=False, encoding="utf-8-sig", float_format="%.10g")
    print(f"Cobertura escrita: {output.relative_to(ROOT)}")
    apt = int(frame["apto_backtest_genuino"].sum())
    print(f"  Factores aptos para backtest genuino: {apt}/14")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archivo inmutable de vintages del modelo TRM.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ["baseline", "snapshot"]:
        child = subparsers.add_parser(command)
        child.add_argument("--origin-date", required=True)
    alfred = subparsers.add_parser("alfred-history")
    alfred.add_argument("--start", default="2022-05-01")
    alfred.add_argument("--end", default="2026-04-01")
    alfred.add_argument("--force", action="store_true")
    fiscal = subparsers.add_parser("fiscal-history")
    fiscal.add_argument("--force", action="store_true")
    pit = subparsers.add_parser(
        "import-pit",
        help="Materializa un archivo oficial histórico como snapshot PIT inmutable",
    )
    pit.add_argument("--origin-date", required=True)
    pit.add_argument("--source-file", required=True)
    pit.add_argument("--evidence-file", required=True)
    pit.add_argument("--available-through", required=True)
    pit.add_argument("--vintage-id", required=True)
    pit.add_argument("--source-id", default="banrep_trm_1")
    subparsers.add_parser("coverage")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "baseline":
        baseline(args.origin_date)
    elif args.command == "snapshot":
        snapshot(args.origin_date)
    elif args.command == "alfred-history":
        alfred_history(args.start, args.end, args.force)
    elif args.command == "fiscal-history":
        fiscal_history(args.force)
    elif args.command == "import-pit":
        import_pit(
            origin_date=args.origin_date,
            source_file=args.source_file,
            evidence_file=args.evidence_file,
            available_through=args.available_through,
            vintage_id=args.vintage_id,
            source_id=args.source_id,
        )
    elif args.command == "coverage":
        coverage()


if __name__ == "__main__":
    main()
