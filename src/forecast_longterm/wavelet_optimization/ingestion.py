"""Ingestión explícita de insumos PIT para la investigación wavelet.

Este módulo no descarga ni convierte automáticamente ``data/raw`` en historia
PIT. Solo materializa un archivo oficial que el caller aporta junto con una
evidencia de su fecha de información. La materialización es inmutable y se
valida con el mismo resolver que usa el backtest.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import pandas as pd

from trm_model.data.vintages import validate_vintage_for_backtest
from trm_model.paths import ProjectPaths
from trm_model.provenance.hashes import sha256_file

from .snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    SnapshotResolver,
    _read_archived_observations,
)

TRM_RAW_PATH = "data/raw/trm_diaria_banrep.json"
_ALLOWED_INPUT_SUFFIXES = {".csv", ".json", ".txt"}
_REQUIRED_EVIDENCE_FIELDS = (
    "provider",
    "source_url",
    "as_of_date",
    "retrieved_utc",
    "method",
)


class PITIngestionError(ValueError):
    """El insumo aportado no demuestra un snapshot PIT consumible."""


@dataclass(frozen=True)
class PITSnapshotArchive:
    """Rutas y huella del snapshot PIT materializado."""

    origin_date: str
    manifest_path: Path
    archived_path: Path
    provenance_path: Path
    sha256: str


def _project(paths: ProjectPaths | Path | str | None) -> ProjectPaths:
    if isinstance(paths, ProjectPaths):
        return paths
    return ProjectPaths.from_root(None if paths is None else Path(paths))


def _date_text(value: Any, field_name: str) -> str:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise PITIngestionError(f"{field_name} no es una fecha válida: {value!r}") from error
    if pd.isna(timestamp):
        raise PITIngestionError(f"{field_name} no puede ser NaT")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize().strftime("%Y-%m-%d")


def _timestamp(value: Any, field_name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise PITIngestionError(f"{field_name} no es una fecha válida: {value!r}") from error
    if pd.isna(timestamp):
        raise PITIngestionError(f"{field_name} no puede ser NaT")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _resolve_input(
    value: Path | str,
    *,
    field_name: str,
    base: Path | None = None,
) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    path = path.resolve()
    if not path.is_file():
        raise PITIngestionError(f"{field_name} no existe o no es un archivo: {path}")
    if path.suffix.lower() not in _ALLOWED_INPUT_SUFFIXES:
        raise PITIngestionError(
            f"{field_name} debe ser CSV/JSON/TXT; extensión recibida: {path.suffix or '<sin extensión>'}"
        )
    return path


def _reject_non_historical_substitutes(path: Path, *, project: ProjectPaths) -> None:
    """Impide usar raw u outputs como si fueran evidencia PIT."""

    if _within(path, project.raw):
        raise PITIngestionError(
            "No se puede materializar un snapshot PIT desde data/raw; "
            "aporte un archivo oficial archivado para el origen solicitado."
        )
    results = project.results.resolve()
    if _within(path, results):
        raise PITIngestionError(
            "No se puede materializar un snapshot PIT desde results/ ni desde un output histórico."
        )


def _load_evidence(path: Path, *, origin_date: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PITIngestionError(f"No se pudo leer evidence_file={path}: {error}") from error
    if not isinstance(value, Mapping):
        raise PITIngestionError("evidence_file debe contener un objeto JSON")

    evidence = {str(key): item for key, item in value.items()}
    missing = [field for field in _REQUIRED_EVIDENCE_FIELDS if not str(evidence.get(field, "")).strip()]
    if missing:
        raise PITIngestionError(
            "La evidencia PIT no contiene los campos obligatorios: " + ", ".join(missing)
        )
    source_url = str(evidence["source_url"]).strip()
    parsed_url = urlparse(source_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise PITIngestionError("evidence.source_url debe ser una URL HTTPS verificable")
    if _date_text(evidence["as_of_date"], "evidence.as_of_date") != origin_date:
        raise PITIngestionError(
            "evidence.as_of_date debe coincidir exactamente con origin_date; "
            "no se acepta una fecha de descarga como sustituto PIT"
        )
    retrieved = pd.Timestamp(evidence["retrieved_utc"])
    if pd.isna(retrieved):
        raise PITIngestionError("evidence.retrieved_utc no es una fecha válida")
    evidence["as_of_date"] = origin_date
    evidence["retrieved_utc"] = retrieved.isoformat()
    evidence["source_url"] = source_url
    evidence["provider"] = str(evidence["provider"]).strip()
    evidence["method"] = str(evidence["method"]).strip()
    return evidence


def _validate_observations(
    path: Path,
    *,
    source_id: str,
    origin_date: str,
    available_through: str,
) -> None:
    try:
        observations = _read_archived_observations(path, source_id)
    except Exception as error:
        raise PITIngestionError(
            f"El archivo oficial no tiene un formato de observaciones válido: {error}"
        ) from error
    if observations.empty:
        raise PITIngestionError("El archivo oficial no contiene observaciones")
    origin = _timestamp(origin_date, "origin_date")
    available = _timestamp(available_through, "available_through")
    if available > origin:
        raise PITIngestionError("available_through no puede ser posterior a origin_date")
    latest = observations["date"].max()
    if latest > available:
        raise PITIngestionError(
            f"El archivo contiene observaciones hasta {latest:%Y-%m-%d}, "
            f"posteriores a available_through={available:%Y-%m-%d}"
        )
    if (observations["date"] > origin).any():
        raise PITIngestionError("El archivo contiene observaciones posteriores al origen PIT")


def materialize_pit_snapshot(
    *,
    source_file: Path | str,
    evidence_file: Path | str,
    origin_date: Any,
    available_through: Any,
    vintage_id: str,
    paths: ProjectPaths | Path | str | None = None,
    source_id: str = BANREP_TRM_SOURCE_ID,
) -> PITSnapshotArchive:
    """Materializa un snapshot verificable sin sobrescribir ningún vintage.

    ``source_file`` debe ser un artefacto oficial externo al raw/output local y
    ``evidence_file`` debe documentar que el contenido estaba disponible en el
    ``origin_date``. La función no descarga, recorta, imputa ni corrige datos.
    """

    project = _project(paths)
    normalized_origin = _date_text(origin_date, "origin_date")
    normalized_available = _date_text(available_through, "available_through")
    if source_id != BANREP_TRM_SOURCE_ID:
        raise PITIngestionError(
            f"La ingestión wavelet solo admite source_id={BANREP_TRM_SOURCE_ID!r}"
        )
    vintage = str(vintage_id).strip()
    if not vintage:
        raise PITIngestionError("vintage_id no puede estar vacío")

    source_path = _resolve_input(source_file, field_name="source_file")
    evidence_path = _resolve_input(evidence_file, field_name="evidence_file")
    _reject_non_historical_substitutes(source_path, project=project)
    evidence = _load_evidence(evidence_path, origin_date=normalized_origin)
    _validate_observations(
        source_path,
        source_id=source_id,
        origin_date=normalized_origin,
        available_through=normalized_available,
    )
    expected_source_sha = str(
        evidence.get("source_sha256", evidence.get("sha256", ""))
    ).strip().lower()
    source_sha = sha256_file(source_path)
    if expected_source_sha and expected_source_sha != source_sha:
        raise PITIngestionError(
            "El SHA-256 del source_file no coincide con el declarado en la evidencia"
        )

    target = project.vintages / normalized_origin
    if target.exists():
        raise PITIngestionError(
            f"Ya existe data/vintages/{normalized_origin}; no se modifica ni se sobrescribe."
        )
    target.mkdir(parents=True)
    try:
        files_dir = target / "files"
        files_dir.mkdir()
        archived_path = files_dir / f"{source_id}{source_path.suffix.lower()}"
        shutil.copyfile(source_path, archived_path)
        archived_sha = sha256_file(archived_path)
        archived_bytes = archived_path.stat().st_size

        provenance_path = target / "provenance.json"
        provenance = {
            "schema_version": 1,
            "source_id": source_id,
            "origin_date": normalized_origin,
            "available_through": normalized_available,
            "vintage_id": vintage,
            "input_sha256": source_sha,
            "input_bytes": source_path.stat().st_size,
            "archived_sha256": archived_sha,
            "archived_bytes": archived_bytes,
            "evidence": evidence,
            "evidence_file_sha256": sha256_file(evidence_path),
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
        provenance_path.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        manifest_path = target / "manifest.json"
        manifest = {
            "schema_version": 1,
            "origin_date": normalized_origin,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "snapshot",
            "immutable": True,
            "provenance_path": project.relative(provenance_path),
            "provenance_sha256": sha256_file(provenance_path),
            "files": [
                {
                    "id": source_id,
                    "provider": evidence["provider"],
                    "series_id": "1",
                    "raw_path": TRM_RAW_PATH,
                    "url": evidence["source_url"],
                    "storage": "copia_oficial_pit_versionada",
                    "archived_path": project.relative(archived_path),
                    "vintage_id": vintage,
                    "available_through": normalized_available,
                    "retrieved_utc": evidence["retrieved_utc"],
                    "bytes": archived_bytes,
                    "sha256": archived_sha,
                }
            ],
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Validación final con ambos contratos existentes: schema/hash y
        # resolución PIT usada por el evaluador. Si falla, no queda un snapshot
        # parcialmente elegible en el repositorio.
        validate_vintage_for_backtest(normalized_origin, paths=project)
        resolver = SnapshotResolver(paths=project)
        resolver.resolve(
            ForecastOrigin(
                origin_date=pd.Timestamp(normalized_origin),
                data_cutoff=pd.Timestamp(normalized_origin),
            ),
            required_source_ids=(source_id,),
        )
    except Exception as error:
        shutil.rmtree(target, ignore_errors=True)
        if isinstance(error, PITIngestionError):
            raise
        raise PITIngestionError(
            f"El snapshot materializado no pasó la validación PIT: {error}"
        ) from error

    return PITSnapshotArchive(
        origin_date=normalized_origin,
        manifest_path=manifest_path,
        archived_path=archived_path,
        provenance_path=provenance_path,
        sha256=archived_sha,
    )


def _monthly_outcome_series(path: Path, *, data_cutoff: Any) -> pd.Series:
    try:
        observations = _read_archived_observations(path, BANREP_TRM_SOURCE_ID)
    except Exception as error:
        raise PITIngestionError(f"No se pudo leer el panel de outcomes: {error}") from error
    cutoff = _timestamp(data_cutoff, "data_cutoff")
    if observations.empty:
        raise PITIngestionError("El panel de outcomes está vacío")
    if (observations["date"] > cutoff).any():
        future = observations.loc[observations["date"] > cutoff, "date"].max()
        raise PITIngestionError(
            f"El panel de outcomes contiene datos posteriores al Data_Cutoff: {future:%Y-%m-%d}"
        )
    series = (
        observations.set_index("date")["value"]
        .sort_index()
        .resample("MS")
        .mean()
        .dropna()
    )
    if series.empty:
        raise PITIngestionError("El panel de outcomes no tiene meses utilizables")
    expected = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    missing = expected.difference(series.index)
    if len(missing):
        raise PITIngestionError(
            "El panel de outcomes tiene meses ausentes; no se imputan: "
            + ", ".join(item.strftime("%Y-%m-%d") for item in missing[:5])
        )
    series.name = BANREP_TRM_SOURCE_ID
    return series


def load_outcome_panel(
    path: Path | str,
    *,
    data_cutoff: Any,
    paths: ProjectPaths | Path | str | None = None,
) -> pd.Series:
    """Carga un panel externo de outcomes y lo limita estrictamente al cutoff."""

    project = _project(paths)
    panel_path = _resolve_input(path, field_name="label_panel", base=project.root)
    _reject_non_historical_substitutes(panel_path, project=project)
    if not _within(panel_path, project.root):
        raise PITIngestionError(
            "label_panel debe vivir dentro de la raíz del proyecto para que provenance "
            "pueda registrar su hash; no se lee un archivo externo silenciosamente."
        )
    return _monthly_outcome_series(panel_path, data_cutoff=data_cutoff)


__all__ = [
    "PITIngestionError",
    "PITSnapshotArchive",
    "load_outcome_panel",
    "materialize_pit_snapshot",
]
