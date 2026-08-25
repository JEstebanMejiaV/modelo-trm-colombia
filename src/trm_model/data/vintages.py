"""Validación de snapshots y cobertura point-in-time.

Este módulo no descarga ni inventa observaciones. Solo acepta un snapshot
fechado cuando sus archivos, tamaños y hashes son verificables. Un baseline que
apunta a ``data/raw`` sirve para fijar el estado actual, pero no se considera
historia de revisiones ni habilita un backtest genuino.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

from ..paths import ProjectPaths, project_paths
from ..provenance.hashes import sha256_file
from ..validation.contracts import ContractError, validate_document


class VintageValidationError(ValueError):
    """El snapshot no cumple las reglas de integridad o de información disponible."""


@dataclass(frozen=True)
class VintageReport:
    origin_date: str
    mode: str
    valid: bool
    pit_eligible: bool
    files_checked: int
    missing_files: tuple[str, ...] = ()
    invalid_files: tuple[str, ...] = ()
    missing_required_inputs: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.valid and not self.missing_files and not self.invalid_files

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["complete"] = self.complete
        return value


def vintage_manifest_path(
    origin_date: str, *, paths: ProjectPaths | None = None
) -> Path:
    project = paths or project_paths()
    date.fromisoformat(origin_date)
    return project.root / "data" / "vintages" / origin_date / "manifest.json"


def load_vintage_manifest(
    origin_date: str, *, paths: ProjectPaths | None = None
) -> dict[str, object]:
    path = vintage_manifest_path(origin_date, paths=paths)
    if not path.is_file():
        raise FileNotFoundError(f"No existe manifest de vintage: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VintageValidationError(f"El manifest no es un objeto JSON: {path}")
    project = paths or project_paths()
    try:
        validate_document(value, project.schema("vintage_manifest.json"))
    except ContractError as error:
        raise VintageValidationError(str(error)) from error
    if value.get("origin_date") != origin_date:
        raise VintageValidationError(
            f"El manifest declara origin_date={value.get('origin_date')!r}, "
            f"pero la carpeta es {origin_date!r}."
        )
    if value.get("immutable") is not True:
        raise VintageValidationError("Un vintage aceptable debe declarar immutable=true.")
    return value


def validate_vintage_manifest(
    origin_date: str,
    *,
    paths: ProjectPaths | None = None,
    required_raw_paths: Iterable[str] = (),
    require_pit: bool = False,
) -> VintageReport:
    """Valida un manifest y hashes sin aplicar imputación ni fallback.

    ``require_pit=True`` exige un snapshot copiado, no el baseline que referencia
    archivos de ``data/raw``. ``required_raw_paths`` permite comprobar que un
    conjunto de factores tenga todos sus archivos en el snapshot.
    """
    project = paths or project_paths()
    manifest = load_vintage_manifest(origin_date, paths=project)
    mode = str(manifest["mode"])
    if require_pit and mode != "snapshot":
        raise VintageValidationError(
            f"El vintage {origin_date} tiene mode={mode!r}; un backtest PIT exige mode='snapshot'."
        )

    root = project.root.resolve()
    records = manifest.get("files", [])
    assert isinstance(records, list)
    seen_ids: set[str] = set()
    seen_raw_paths: set[str] = set()
    missing_files: list[str] = []
    invalid_files: list[str] = []

    for record in records:
        assert isinstance(record, dict)
        record_id = str(record["id"])
        raw_path = str(record["raw_path"])
        if record_id in seen_ids or raw_path in seen_raw_paths:
            invalid_files.append(f"{record_id}: identificador o raw_path duplicado")
            continue
        seen_ids.add(record_id)
        seen_raw_paths.add(raw_path)

        archived_path = record.get("archived_path")
        if mode == "snapshot" and not isinstance(archived_path, str):
            invalid_files.append(f"{record_id}: snapshot sin archived_path")
            continue
        stored_path = str(archived_path or raw_path)
        candidate = (root / stored_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            invalid_files.append(f"{record_id}: ruta fuera del proyecto")
            continue
        if not candidate.is_file():
            missing_files.append(stored_path)
            continue
        actual_bytes = candidate.stat().st_size
        actual_sha256 = sha256_file(candidate)
        if actual_bytes != int(record["bytes"]):
            invalid_files.append(f"{record_id}: bytes esperados={record['bytes']} reales={actual_bytes}")
        if actual_sha256 != str(record["sha256"]):
            invalid_files.append(f"{record_id}: SHA-256 no coincide")

    missing_required = sorted(set(required_raw_paths) - seen_raw_paths)
    if missing_required:
        invalid_files.append(
            "faltan inputs requeridos: " + ", ".join(missing_required)
        )

    report = VintageReport(
        origin_date=origin_date,
        mode=mode,
        valid=not missing_files and not invalid_files,
        pit_eligible=mode == "snapshot" and not missing_files and not invalid_files,
        files_checked=len(records),
        missing_files=tuple(sorted(missing_files)),
        invalid_files=tuple(invalid_files),
        missing_required_inputs=tuple(missing_required),
    )
    if require_pit and not report.complete:
        raise VintageValidationError(
            f"El vintage {origin_date} no es PIT completo: {report.as_dict()}"
        )
    return report


def validate_vintage_for_backtest(
    origin_date: str,
    *,
    required_raw_paths: Iterable[str] = (),
    paths: ProjectPaths | None = None,
) -> VintageReport:
    """Valida el contrato estricto de un origen point-in-time."""
    return validate_vintage_manifest(
        origin_date,
        paths=paths,
        required_raw_paths=required_raw_paths,
        require_pit=True,
    )


def forecast_vintage_coverage(
    *, paths: ProjectPaths | None = None
) -> dict[str, object]:
    """Lee la cobertura publicada sin convertirla en cobertura sintética."""
    project = paths or project_paths()
    path = project.results / "pronostico" / "cobertura_vintages_pronostico.csv"
    if not path.is_file():
        return {
            "path": project.relative(path),
            "factors": 0,
            "complete_factors": 0,
            "genuine_backtest_available": False,
        }
    frame = pd.read_csv(path)
    complete_column = frame["apto_backtest_genuino"].astype("string").str.lower()
    complete = int(complete_column.eq("true").sum())
    factors = int(len(frame))
    return {
        "path": project.relative(path),
        "factors": factors,
        "complete_factors": complete,
        "genuine_backtest_available": factors > 0 and complete == factors,
    }


def vintage_status(*, paths: ProjectPaths | None = None) -> dict[str, object]:
    """Devuelve el estado verificable de snapshots fechados y cobertura de factores."""
    project = paths or project_paths()
    vintage_root = project.root / "data" / "vintages"
    reports: list[dict[str, object]] = []
    if vintage_root.is_dir():
        for directory in sorted(vintage_root.iterdir()):
            if not directory.is_dir() or directory.name == "historical":
                continue
            manifest = directory / "manifest.json"
            if not manifest.is_file():
                reports.append(
                    {
                        "origin_date": directory.name,
                        "valid": False,
                        "complete": False,
                        "error": "falta manifest.json",
                    }
                )
                continue
            try:
                report = validate_vintage_manifest(directory.name, paths=project)
                reports.append(report.as_dict())
            except (ValueError, OSError, json.JSONDecodeError) as error:
                reports.append(
                    {
                        "origin_date": directory.name,
                        "valid": False,
                        "complete": False,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    return {
        "snapshots": reports,
        "forecast_coverage": forecast_vintage_coverage(paths=project),
    }
