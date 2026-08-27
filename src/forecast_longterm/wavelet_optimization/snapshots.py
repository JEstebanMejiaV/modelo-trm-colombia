"""Primitivas point-in-time para la investigación wavelet de largo horizonte.

Este módulo es deliberadamente estricto: una serie solo puede entrar por el
archivo ``archived_path`` de un manifest ``mode="snapshot"``. No hay fallback a
``data/raw``, datasets construidos, políticas ``latest_available`` ni outputs
históricos. La resolución de una fuente ausente se representa como una
exclusión de cobertura (y, en modo estricto, como una excepción tipada) para
que el evaluador no pueda convertir falta de información en desempeño.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from trm_model.data.vintages import (
    VintageValidationError,
    validate_vintage_for_backtest,
)
from trm_model.paths import ProjectPaths, project_paths
from trm_model.provenance.hashes import sha256_file

BANREP_TRM_SOURCE_ID = "banrep_trm_1"
SNAPSHOT_MODE = "snapshot"
NOT_SCOREABLE_SNAPSHOT_MISSING = "not_scoreable_snapshot_missing"
NOT_SCOREABLE_SNAPSHOT_INVALID = "not_scoreable_snapshot_invalid"
NOT_SCOREABLE_SOURCE_MISSING = "not_scoreable_source_missing"
NOT_SCOREABLE_COVERAGE_INCOMPLETE = "not_scoreable_coverage_incomplete"
NOT_EVALUABLE_LABEL_NOT_MATURE = "not_evaluable_label_not_mature"

CoverageStatus = Literal["complete", "incomplete", "missing", "invalid"]
ScoreabilityStatus = Literal[
    "scoreable",
    "not_scoreable_snapshot_missing",
    "not_scoreable_snapshot_invalid",
    "not_scoreable_source_missing",
    "not_scoreable_coverage_incomplete",
]


class SnapshotError(ValueError):
    """Error de integridad, disponibilidad o lectura de un snapshot PIT."""


class SnapshotResolutionError(SnapshotError):
    """Un origen no tiene un snapshot/fuente PIT utilizable.

    ``coverage_status`` y ``scoreability_status`` permiten que el caller
    registre la exclusión sin tener que inferirla desde el texto de la
    excepción. El error no contiene ni propone una ruta de fallback.
    """

    def __init__(
        self,
        message: str,
        *,
        origin: ForecastOrigin | None = None,
        source_id: str | None = None,
        coverage_status: CoverageStatus = "incomplete",
        scoreability_status: str = "not_scoreable_snapshot_invalid",
        reason: str | None = None,
        snapshot_manifest: str | None = None,
    ) -> None:
        self.origin = origin
        self.source_id = source_id
        self.coverage_status = coverage_status
        self.scoreability_status = scoreability_status
        self.reason = reason or message
        self.snapshot_manifest = snapshot_manifest
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        """Representación estable para un warning o una fila de cobertura."""

        return {
            "origin_date": _date_text(self.origin.origin_date) if self.origin else None,
            "source_id": self.source_id,
            "snapshot_manifest": self.snapshot_manifest,
            "coverage_status": self.coverage_status,
            "scoreability_status": self.scoreability_status,
            "reason": self.reason,
        }


class SnapshotSeriesError(SnapshotError):
    """El archivo archivado no contiene una serie TRM válida y completa."""

    def __init__(
        self,
        message: str,
        *,
        origin: ForecastOrigin | None = None,
        source_id: str | None = None,
        coverage_status: CoverageStatus = "incomplete",
        scoreability_status: str = "not_scoreable_coverage_incomplete",
        reason: str | None = None,
    ) -> None:
        self.origin = origin
        self.source_id = source_id
        self.coverage_status = coverage_status
        self.scoreability_status = scoreability_status
        self.reason = reason or message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Normalización de fechas y rutas
# ---------------------------------------------------------------------------


def _timestamp(value: Any, field_name: str) -> pd.Timestamp:
    """Convierte una fecha a timestamp naive de medianoche sin inferir fechas."""

    if value is None or value is pd.NaT:
        raise ValueError(f"{field_name} no puede ser nulo")
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field_name} no es una fecha válida: {value!r}") from error
    if pd.isna(result):
        raise ValueError(f"{field_name} no es una fecha válida: {value!r}")
    if result.tzinfo is not None:
        result = result.tz_convert("UTC").tz_localize(None)
    return result.normalize()


def _optional_timestamp(value: Any, field_name: str) -> pd.Timestamp | None:
    if value is None or value is pd.NaT or (isinstance(value, str) and not value.strip()):
        return None
    return _timestamp(value, field_name)


def _date_text(value: pd.Timestamp | None) -> str | None:
    return None if value is None else value.strftime("%Y-%m-%d")


def _origin_date(value: ForecastOrigin | pd.Timestamp | str) -> pd.Timestamp:
    if isinstance(value, ForecastOrigin):
        return value.origin_date
    return _timestamp(value, "origin_date")


def _project(value: ProjectPaths | Path | str | None) -> ProjectPaths:
    if value is None:
        return project_paths()
    if isinstance(value, ProjectPaths):
        return value
    return ProjectPaths.from_root(Path(value))


def _within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _resolve_project_path(path_value: str | Path, paths: ProjectPaths) -> Path:
    path = Path(path_value)
    return (path if path.is_absolute() else paths.root / path).resolve()


def _canonical_manifest_path(origin_date: pd.Timestamp, paths: ProjectPaths) -> Path:
    return paths.vintages / origin_date.strftime("%Y-%m-%d") / "manifest.json"


def _manifest_relative(path: Path, paths: ProjectPaths) -> str:
    try:
        return path.resolve().relative_to(paths.root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Modelos PIT
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ForecastOrigin:
    """Origen mensual y corte explícito al que queda ligado un snapshot.

    ``origin_date`` conserva el día explícito del snapshot, normalizado a
    medianoche. ``origin_period`` es la clave mensual que consumirán los
    módulos posteriores; no se fabrican períodos adicionales aquí.
    """

    origin_date: pd.Timestamp
    origin_period: str | None = None
    data_cutoff: pd.Timestamp | None = None
    snapshot_manifest: str | None = None

    def __post_init__(self) -> None:
        origin_date = _timestamp(self.origin_date, "origin_date")
        object.__setattr__(self, "origin_date", origin_date)

        expected_period = origin_date.strftime("%Y-%m")
        supplied_period = self.origin_period
        if supplied_period is None or not str(supplied_period).strip():
            supplied_period = expected_period
        else:
            supplied_period = str(supplied_period).strip()
            try:
                parsed_period = pd.Period(supplied_period, freq="M")
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "origin_period debe tener formato YYYY-MM"
                ) from error
            if str(parsed_period) != expected_period:
                raise ValueError(
                    "origin_period no concilia con origin_date: "
                    f"{supplied_period!r} != {expected_period!r}"
                )
        object.__setattr__(self, "origin_period", expected_period)

        cutoff = self.data_cutoff
        if cutoff is None:
            cutoff = origin_date
        object.__setattr__(self, "data_cutoff", _timestamp(cutoff, "data_cutoff"))

        manifest = self.snapshot_manifest
        if manifest is not None:
            manifest = str(manifest).strip() or None
        object.__setattr__(self, "snapshot_manifest", manifest)

    @property
    def effective_cutoff(self) -> pd.Timestamp:
        """Fecha más temprana que puede observarse para este origen."""

        return min(self.origin_date, self.data_cutoff)

    def as_dict(self) -> dict[str, object]:
        return {
            "origin_date": _date_text(self.origin_date),
            "origin_period": self.origin_period,
            "data_cutoff": _date_text(self.data_cutoff),
            "snapshot_manifest": self.snapshot_manifest,
        }


@dataclass(frozen=True)
class SourceVintage:
    """Identidad y disponibilidad de una fuente archivada dentro del snapshot."""

    source_id: str
    vintage_id: str
    snapshot_manifest: str
    archived_path: str
    available_through: pd.Timestamp
    sha256: str

    def __post_init__(self) -> None:
        source_id = str(self.source_id).strip()
        vintage_id = str(self.vintage_id).strip()
        snapshot_manifest = str(self.snapshot_manifest).strip()
        archived_path = str(self.archived_path).strip()
        sha256 = str(self.sha256).strip().lower()
        if not source_id:
            raise ValueError("SourceVintage.source_id no puede estar vacío")
        if not vintage_id:
            raise ValueError("SourceVintage.vintage_id no puede estar vacío")
        if not snapshot_manifest:
            raise ValueError("SourceVintage.snapshot_manifest no puede estar vacío")
        if not archived_path:
            raise ValueError("SourceVintage.archived_path no puede estar vacío")
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise ValueError("SourceVintage.sha256 debe ser SHA-256 hexadecimal")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "vintage_id", vintage_id)
        object.__setattr__(self, "snapshot_manifest", snapshot_manifest)
        object.__setattr__(self, "archived_path", archived_path)
        object.__setattr__(
            self,
            "available_through",
            _timestamp(self.available_through, "available_through"),
        )
        object.__setattr__(self, "sha256", sha256)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "vintage_id": self.vintage_id,
            "snapshot_manifest": self.snapshot_manifest,
            "archived_path": self.archived_path,
            "available_through": _date_text(self.available_through),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class PointInTimeSnapshot:
    """Snapshot validado y ligado a un único ``ForecastOrigin``."""

    origin: ForecastOrigin
    source_vintages: tuple[SourceVintage, ...]
    manifest_sha256: str
    mode: str = SNAPSHOT_MODE
    status: str = "valid"
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.origin, ForecastOrigin):
            raise TypeError("PointInTimeSnapshot.origin debe ser ForecastOrigin")
        object.__setattr__(self, "source_vintages", tuple(self.source_vintages))
        mode = str(self.mode).strip().lower()
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "status", str(self.status).strip())
        if self.reason is not None:
            object.__setattr__(self, "reason", str(self.reason).strip())
        manifest_sha256 = str(self.manifest_sha256).strip().lower()
        if manifest_sha256 and (
            len(manifest_sha256) != 64
            or any(c not in "0123456789abcdef" for c in manifest_sha256)
        ):
            raise ValueError("manifest_sha256 debe ser SHA-256 hexadecimal o vacío")
        object.__setattr__(self, "manifest_sha256", manifest_sha256)

    @property
    def valid(self) -> bool:
        return self.mode == SNAPSHOT_MODE and self.status == "valid"

    @property
    def snapshot_manifest(self) -> str | None:
        return self.origin.snapshot_manifest

    def source(self, source_id: str) -> SourceVintage:
        matches = [item for item in self.source_vintages if item.source_id == source_id]
        if not matches:
            raise KeyError(f"La fuente {source_id!r} no está en el snapshot")
        if len(matches) > 1:
            raise SnapshotError(f"El snapshot tiene vintages duplicados para {source_id!r}")
        return matches[0]

    def source_vintage(self, source_id: str) -> SourceVintage:
        """Alias explícito para consumidores de provenance/evaluación."""

        return self.source(source_id)

    get_source_vintage = source_vintage

    def has_source(self, source_id: str) -> bool:
        return any(item.source_id == source_id for item in self.source_vintages)

    def as_dict(self) -> dict[str, object]:
        return {
            "origin": self.origin.as_dict(),
            "source_vintages": [item.as_dict() for item in self.source_vintages],
            "manifest_sha256": self.manifest_sha256,
            "mode": self.mode,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CoverageRecord:
    """Una fila de cobertura, sin campos de desempeño predictivo."""

    source_id: str
    origin_date: pd.Timestamp
    horizon_months: int
    snapshot_manifest: str | None = None
    source_vintage: str | None = None
    available_through: pd.Timestamp | None = None
    sha256: str | None = None
    n_observations_available: int = 0
    n_missing: int = 0
    coverage_status: CoverageStatus = "incomplete"
    scoreability_status: str = "not_scoreable_coverage_incomplete"
    required_for_candidate: bool | str = True
    excluded_origins: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", str(self.source_id).strip())
        object.__setattr__(self, "origin_date", _timestamp(self.origin_date, "origin_date"))
        if not isinstance(self.horizon_months, int) or self.horizon_months <= 0:
            raise ValueError("CoverageRecord.horizon_months debe ser entero positivo")
        for field_name in ("n_observations_available", "n_missing"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"CoverageRecord.{field_name} debe ser entero no negativo")
        if self.available_through is not None:
            object.__setattr__(
                self,
                "available_through",
                _timestamp(self.available_through, "available_through"),
            )
        status = str(self.coverage_status).strip().lower()
        if status not in {"complete", "incomplete", "missing", "invalid"}:
            raise ValueError(f"coverage_status no soportado: {status!r}")
        object.__setattr__(self, "coverage_status", status)
        exclusions = (
            (self.excluded_origins,)
            if isinstance(self.excluded_origins, str)
            else tuple(self.excluded_origins)
        )
        exclusions = tuple(dict.fromkeys(str(item) for item in exclusions))
        object.__setattr__(self, "excluded_origins", exclusions)
        if self.sha256 is not None:
            sha256 = str(self.sha256).strip().lower()
            if sha256 and (
                len(sha256) != 64
                or any(c not in "0123456789abcdef" for c in sha256)
            ):
                raise ValueError("CoverageRecord.sha256 debe ser SHA-256 o nulo")
            object.__setattr__(self, "sha256", sha256 or None)

    @property
    def key(self) -> tuple[str, pd.Timestamp, int]:
        return self.source_id, self.origin_date, self.horizon_months

    def as_dict(self) -> dict[str, object]:
        """Serializa solo cobertura; deliberadamente no incluye ``r2_oos``."""

        return {
            "source_id": self.source_id,
            "origin_date": _date_text(self.origin_date),
            "horizon_months": self.horizon_months,
            "snapshot_manifest": self.snapshot_manifest,
            "source_vintage": self.source_vintage,
            "available_through": _date_text(self.available_through),
            "sha256": self.sha256,
            "n_observations_available": self.n_observations_available,
            "n_missing": self.n_missing,
            "coverage_status": self.coverage_status,
            "scoreability_status": self.scoreability_status,
            "required_for_candidate": self.required_for_candidate,
            "excluded_origins": list(self.excluded_origins),
            "reason": self.reason,
        }


# Aliases útiles para callers que usen el nombre del registro en singular.
CoverageLedgerRecord = CoverageRecord
CoverageEntry = CoverageRecord


class CoverageLedger:
    """Ledger único por ``(source_id, origin_date, horizon_months)``.

    La tabla de cobertura y los registros de desempeño viven en estructuras
    separadas. En particular, ``to_frame()`` nunca puede recibir accidentalmente
    ``r2_oos`` o una pérdida predictiva desde el evaluador.
    """

    def __init__(
        self,
        records: Iterable[CoverageRecord | Mapping[str, Any]] = (),
        *,
        default_horizons: Iterable[int] = (6, 12),
    ) -> None:
        self.default_horizons = tuple(int(horizon) for horizon in default_horizons)
        self._records: dict[tuple[str, pd.Timestamp, int], CoverageRecord] = {}
        self._performance_records: list[dict[str, object]] = []
        for record in records:
            self.record(record)

    @staticmethod
    def _coerce_record(record: CoverageRecord | Mapping[str, Any]) -> CoverageRecord:
        if isinstance(record, CoverageRecord):
            return record
        if not isinstance(record, Mapping):
            raise TypeError("CoverageLedger.record requiere CoverageRecord o mapping")
        value = dict(record)
        if "origin" in value and "origin_date" not in value:
            value["origin_date"] = _origin_date(value.pop("origin"))
        return CoverageRecord(**value)

    def record(self, record: CoverageRecord | Mapping[str, Any]) -> CoverageRecord:
        """Inserta o actualiza una fila sin crear duplicados de clave."""

        item = self._coerce_record(record)
        self._records[item.key] = item
        return item

    add = record
    add_record = record
    register = record
    upsert = record

    def record_coverage(
        self,
        *,
        source_id: str,
        origin: ForecastOrigin | pd.Timestamp | str,
        horizon_months: int,
        snapshot_manifest: str | None = None,
        source_vintage: str | None = None,
        available_through: pd.Timestamp | None = None,
        sha256: str | None = None,
        n_observations_available: int = 0,
        n_missing: int = 0,
        coverage_status: CoverageStatus = "complete",
        scoreability_status: str = "scoreable",
        required_for_candidate: bool | str = True,
        reason: str | None = None,
    ) -> CoverageRecord:
        origin_date = _origin_date(origin)
        return self.record(
            CoverageRecord(
                source_id=source_id,
                origin_date=origin_date,
                horizon_months=horizon_months,
                snapshot_manifest=snapshot_manifest,
                source_vintage=source_vintage,
                available_through=available_through,
                sha256=sha256,
                n_observations_available=n_observations_available,
                n_missing=n_missing,
                coverage_status=coverage_status,
                scoreability_status=scoreability_status,
                required_for_candidate=required_for_candidate,
                reason=reason,
            )
        )

    def record_exclusion(
        self,
        *,
        source_id: str,
        origin: ForecastOrigin | pd.Timestamp | str,
        horizon_months: int,
        reason: str,
        coverage_status: CoverageStatus = "incomplete",
        scoreability_status: str = "not_scoreable_coverage_incomplete",
        snapshot_manifest: str | None = None,
        source_vintage: str | None = None,
        available_through: pd.Timestamp | None = None,
        sha256: str | None = None,
        n_observations_available: int = 0,
        n_missing: int = 0,
        required_for_candidate: bool | str = True,
    ) -> CoverageRecord:
        """Registra una exclusión manteniendo la causa separada de métricas."""

        origin_date = _origin_date(origin)
        key = (str(source_id).strip(), origin_date, int(horizon_months))
        existing = self._records.get(key)
        exclusions = set(existing.excluded_origins if existing else ())
        exclusions.add(origin_date.strftime("%Y-%m-%d"))
        record = CoverageRecord(
            source_id=source_id,
            origin_date=origin_date,
            horizon_months=horizon_months,
            snapshot_manifest=(
                snapshot_manifest
                if snapshot_manifest is not None
                else existing.snapshot_manifest if existing else None
            ),
            source_vintage=(
                source_vintage if source_vintage is not None else existing.source_vintage if existing else None
            ),
            available_through=(
                available_through
                if available_through is not None
                else existing.available_through if existing else None
            ),
            sha256=sha256 if sha256 is not None else existing.sha256 if existing else None,
            n_observations_available=n_observations_available
            if existing is None
            else max(existing.n_observations_available, n_observations_available),
            n_missing=n_missing if existing is None else max(existing.n_missing, n_missing),
            coverage_status=coverage_status,
            scoreability_status=scoreability_status,
            required_for_candidate=required_for_candidate,
            excluded_origins=tuple(sorted(exclusions)),
            reason=reason,
        )
        return self.record(record)

    @property
    def records(self) -> tuple[CoverageRecord, ...]:
        return tuple(
            self._records[key]
            for key in sorted(self._records, key=lambda value: (value[1], value[0], value[2]))
        )

    @property
    def rows(self) -> tuple[CoverageRecord, ...]:
        return self.records

    def __iter__(self) -> Iterator[CoverageRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self._records)

    def get(
        self,
        source_id: str,
        origin: ForecastOrigin | pd.Timestamp | str,
        horizon_months: int,
    ) -> CoverageRecord | None:
        return self._records.get((str(source_id).strip(), _origin_date(origin), int(horizon_months)))

    def as_dicts(self) -> list[dict[str, object]]:
        return [record.as_dict() for record in self.records]

    def to_dicts(self) -> list[dict[str, object]]:
        return self.as_dicts()

    def to_frame(self) -> pd.DataFrame:
        columns = [
            "source_id",
            "origin_date",
            "horizon_months",
            "snapshot_manifest",
            "source_vintage",
            "available_through",
            "sha256",
            "n_observations_available",
            "n_missing",
            "coverage_status",
            "scoreability_status",
            "required_for_candidate",
            "excluded_origins",
            "reason",
        ]
        return pd.DataFrame(self.as_dicts(), columns=columns)

    coverage_frame = to_frame

    def record_performance(
        self,
        *,
        origin: ForecastOrigin | pd.Timestamp | str,
        horizon_months: int,
        candidate_id: str | None = None,
        **values: object,
    ) -> dict[str, object]:
        """Guarda datos de desempeño en un registro distinto al de cobertura."""

        record: dict[str, object] = {
            "origin_date": _date_text(_origin_date(origin)),
            "horizon_months": int(horizon_months),
        }
        if candidate_id is not None:
            record["candidate_id"] = str(candidate_id)
        record.update(values)
        self._performance_records.append(record)
        return dict(record)

    @property
    def performance_records(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(record) for record in self._performance_records)

    def performance_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.performance_records)


# ---------------------------------------------------------------------------
# Lectura estricta del archivo archivado
# ---------------------------------------------------------------------------


def _json_rows(payload: Any) -> tuple[list[Any], str | None]:
    """Extrae filas y, si existe, el nombre de la columna de fecha."""

    item = payload
    if isinstance(payload, list) and payload and isinstance(payload[0], Mapping):
        if "data" in payload[0] or "observations" in payload[0]:
            item = payload[0]
    if isinstance(item, Mapping):
        for key in ("data", "observations", "rows", "records"):
            if key in item:
                rows = item[key]
                if not isinstance(rows, list):
                    raise SnapshotSeriesError(f"El campo JSON {key!r} no es una lista")
                return rows, None
        # Fixtures compactos pueden ser un solo registro.
        return [item], None
    if isinstance(item, list):
        return item, None
    raise SnapshotSeriesError("El archivo JSON archivado no contiene filas de observaciones")


def _row_to_pair(row: Any, source_id: str) -> tuple[Any, Any, str | None]:
    if isinstance(row, Mapping):
        date_keys = (
            "timestamp_ms",
            "timestamp",
            "fecha",
            "fecha_observacion",
            "date",
            "datetime",
            "time",
        )
        value_keys = (
            source_id,
            "valor",
            "value",
            "valor_trm",
            "trm",
            "observation",
        )
        date_key = next((key for key in date_keys if key in row), None)
        value_key = next((key for key in value_keys if key in row), None)
        if date_key is None or value_key is None:
            raise SnapshotSeriesError(
                f"Fila archivada sin fecha/valor reconocibles para {source_id!r}"
            )
        return row[date_key], row[value_key], date_key
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        if len(row) < 2:
            raise SnapshotSeriesError("Fila archivada debe tener fecha y valor")
        return row[0], row[1], None
    raise SnapshotSeriesError("Fila archivada no tiene formato de observación")


def _parse_date_values(values: pd.Series, key_hint: str | None) -> pd.Series:
    # Solo ``timestamp_ms`` tiene una unidad implícita. Un campo llamado
    # ``timestamp`` puede contener ISO-8601 y no debe convertirse como ms.
    numeric = pd.to_numeric(values, errors="coerce")
    numeric_epoch = numeric.notna().all() and bool(numeric.abs().median() >= 1e8)
    if key_hint and key_hint.lower().endswith("_ms"):
        parsed = pd.to_datetime(numeric, unit="ms", errors="coerce", utc=True)
    elif numeric_epoch:
        # Las filas nativas de BanRep son [timestamp_ms, value] y no tienen
        # nombre de columna. Epoch seconds también se admite en fixtures, pero
        # nunca se infiere una fecha calendario desde un número pequeño.
        unit = "ms" if float(numeric.abs().median()) >= 1e11 else "s"
        parsed = pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True)
    else:
        parsed = pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
    if parsed.isna().any():
        bad = int(parsed.isna().sum())
        raise SnapshotSeriesError(f"El archivo archivado contiene {bad} fecha(s) inválida(s)")
    # UTC explícito evita que la fecha cambie según la zona horaria del proceso.
    return parsed.dt.tz_convert(None).dt.normalize()


def _observations_from_rows(
    rows: list[Any], source_id: str, *, date_hint: str | None = None
) -> pd.DataFrame:
    if not rows:
        raise SnapshotSeriesError("El archivo archivado no contiene observaciones")
    pairs = [_row_to_pair(row, source_id) for row in rows]
    dates = pd.Series([pair[0] for pair in pairs], dtype="object")
    date_hint = date_hint or next((pair[2] for pair in pairs if pair[2] is not None), None)
    parsed_dates = _parse_date_values(dates, date_hint)
    raw_values = pd.Series([pair[1] for pair in pairs], dtype="object")
    values = pd.to_numeric(raw_values, errors="coerce")
    invalid = values.isna() | ~np.isfinite(values.astype(float)) | (values <= 0)
    if invalid.any():
        count = int(invalid.sum())
        raise SnapshotSeriesError(
            f"El archivo archivado contiene {count} valor(es) TRM inválido(s); "
            "no se imputan ni se descartan silenciosamente"
        )
    frame = pd.DataFrame({"date": parsed_dates, "value": values.astype(float)})
    return frame.sort_values("date", kind="mergesort").reset_index(drop=True)


def _read_archived_observations(path: Path, source_id: str) -> pd.DataFrame:
    """Lee exclusivamente un archivo archivado JSON/CSV como observaciones diarias."""

    suffix = path.suffix.lower()
    try:
        if suffix == ".json" or suffix == "":
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows, _ = _json_rows(payload)
            return _observations_from_rows(rows, source_id)

        if suffix in {".csv", ".txt"}:
            frame = pd.read_csv(path)
            if frame.empty:
                raise SnapshotSeriesError("El archivo CSV archivado está vacío")
            date_column = next(
                (
                    column
                    for column in frame.columns
                    if str(column).lower()
                    in {"timestamp_ms", "timestamp", "fecha", "fecha_observacion", "date", "datetime", "time"}
                ),
                frame.columns[0],
            )
            value_column = next(
                (
                    column
                    for column in frame.columns
                    if str(column) in {source_id, "valor", "value", "valor_trm", "trm", "observation"}
                ),
                None,
            )
            if value_column is None:
                candidates = [column for column in frame.columns if column != date_column]
                if len(candidates) != 1:
                    raise SnapshotSeriesError(
                        f"CSV archivado sin columna de valor inequívoca para {source_id!r}"
                    )
                value_column = candidates[0]
            rows = list(zip(frame[date_column].tolist(), frame[value_column].tolist()))
            # Preserva el nombre para interpretar correctamente timestamp_ms.
            converted = _observations_from_rows(
                rows, source_id, date_hint=str(date_column)
            )
            if str(date_column).lower() != "timestamp_ms":
                return converted
            return converted

        raise SnapshotSeriesError(
            f"Formato de archivo archivado no soportado: {path.suffix or '<sin extensión>'}"
        )
    except SnapshotSeriesError:
        raise
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, pd.errors.ParserError) as error:
        raise SnapshotSeriesError(f"No se pudo leer el archivo archivado {path}: {error}") from error


# ---------------------------------------------------------------------------
# Resolución y store PIT
# ---------------------------------------------------------------------------


class SnapshotResolver:
    """Resuelve y valida el snapshot de cada origen sin usar fallbacks."""

    def __init__(
        self,
        paths: ProjectPaths | Path | str | None = None,
        *,
        coverage_ledger: CoverageLedger | None = None,
        horizons: Iterable[int] = (6, 12),
    ) -> None:
        self.paths = _project(paths)
        self.horizons = tuple(int(horizon) for horizon in horizons)
        self.coverage_ledger = (
            coverage_ledger
            if coverage_ledger is not None
            else CoverageLedger(default_horizons=self.horizons)
        )

    def _manifest_path(self, origin: ForecastOrigin) -> Path:
        if origin.snapshot_manifest:
            path = _resolve_project_path(origin.snapshot_manifest, self.paths)
        else:
            path = _canonical_manifest_path(origin.origin_date, self.paths).resolve()
        if not _within(path, self.paths.root):
            raise SnapshotResolutionError(
                "El manifest del snapshot está fuera de la raíz del proyecto",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_manifest_outside_project",
                snapshot_manifest=str(path),
            )
        return path

    def _load_manifest(self, path: Path, origin: ForecastOrigin) -> dict[str, Any]:
        if not path.is_file():
            raise SnapshotResolutionError(
                f"No existe manifest PIT para el origen {origin.origin_date:%Y-%m-%d}: {path}",
                origin=origin,
                coverage_status="missing",
                scoreability_status="not_scoreable_snapshot_missing",
                reason="snapshot_manifest_missing",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SnapshotResolutionError(
                f"No se pudo leer el manifest PIT {path}: {error}",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_manifest_unreadable",
                snapshot_manifest=_manifest_relative(path, self.paths),
            ) from error
        if not isinstance(value, dict):
            raise SnapshotResolutionError(
                f"El manifest PIT no es un objeto JSON: {path}",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_manifest_not_object",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )
        manifest_origin = value.get("origin_date")
        try:
            parsed_manifest_origin = _timestamp(manifest_origin, "manifest.origin_date")
        except ValueError as error:
            raise SnapshotResolutionError(
                str(error),
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_origin_invalid",
                snapshot_manifest=_manifest_relative(path, self.paths),
            ) from error
        if parsed_manifest_origin != origin.origin_date:
            raise SnapshotResolutionError(
                "El snapshot está ligado a otro origen: "
                f"manifest={parsed_manifest_origin:%Y-%m-%d}, "
                f"requested={origin.origin_date:%Y-%m-%d}",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_origin_mismatch",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )
        return value

    def _validate_manifest_integrity(
        self,
        path: Path,
        manifest: Mapping[str, Any],
        origin: ForecastOrigin,
    ) -> list[Mapping[str, Any]]:
        """Ejecuta el validador canónico cuando es posible y cierra sus huecos PIT."""

        mode = manifest.get("mode")
        if mode != SNAPSHOT_MODE:
            raise SnapshotResolutionError(
                f"El vintage {origin.origin_date:%Y-%m-%d} tiene mode={mode!r}; "
                "solo mode='snapshot' es elegible",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_mode_not_snapshot",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )
        if manifest.get("immutable") is not True:
            raise SnapshotResolutionError(
                "El manifest PIT debe declarar immutable=true",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_not_immutable",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )

        # Reutiliza la validación existente para manifests ubicados en la ruta
        # canónica. Un fixture externo puede no tener el schema instalado, por lo
        # que se valida estructuralmente abajo sin relajar hashes ni rutas.
        canonical = _canonical_manifest_path(origin.origin_date, self.paths).resolve()
        try:
            if (
                path.resolve() == canonical
                and self.paths.schema("vintage_manifest.json").is_file()
            ):
                validate_vintage_for_backtest(
                    origin.origin_date.strftime("%Y-%m-%d"),
                    paths=self.paths,
                )
        except (FileNotFoundError, OSError, ValueError, VintageValidationError) as error:
            if isinstance(error, SnapshotResolutionError):
                raise
            raise SnapshotResolutionError(
                f"Falló la validación del vintage PIT {path}: {error}",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_integrity_invalid",
                snapshot_manifest=_manifest_relative(path, self.paths),
            ) from error

        schema_version = manifest.get("schema_version")
        if (
            not isinstance(schema_version, int)
            or isinstance(schema_version, bool)
            or schema_version < 1
        ):
            raise SnapshotResolutionError(
                "El manifest PIT debe declarar schema_version entero positivo",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_schema_version_invalid",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )

        records = manifest.get("files")
        if not isinstance(records, list) or not records:
            raise SnapshotResolutionError(
                "El manifest PIT debe contener una lista no vacía de files",
                origin=origin,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_files_missing",
                snapshot_manifest=_manifest_relative(path, self.paths),
            )

        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        root = self.paths.root.resolve()
        snapshot_dir = path.parent.resolve()
        for raw_record in records:
            if not isinstance(raw_record, Mapping):
                raise SnapshotResolutionError(
                    "El manifest PIT contiene un registro de archivo inválido",
                    origin=origin,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="snapshot_file_record_invalid",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            record = raw_record
            record_id = str(record.get("id", "")).strip()
            if not record_id:
                raise SnapshotResolutionError(
                    "Un archivo del manifest PIT no tiene id",
                    origin=origin,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="snapshot_file_id_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            if record_id in seen_ids:
                raise SnapshotResolutionError(
                    f"El manifest PIT repite el source_id {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="snapshot_source_duplicate",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            seen_ids.add(record_id)

            raw_path = record.get("raw_path")
            storage = record.get("storage")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise SnapshotResolutionError(
                    f"El manifest PIT no tiene raw_path descriptivo para {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="snapshot_raw_path_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            if not isinstance(storage, str) or not storage.strip():
                raise SnapshotResolutionError(
                    f"El manifest PIT no tiene storage para {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="snapshot_storage_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )

            archived_value = record.get("archived_path")
            if not isinstance(archived_value, str) or not archived_value.strip():
                raise SnapshotResolutionError(
                    f"El snapshot no tiene archived_path para {record_id!r}; no se usa raw_path",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="missing",
                    scoreability_status="not_scoreable_source_missing",
                    reason="archived_path_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            candidate = _resolve_project_path(archived_value, self.paths)
            if not _within(candidate, root) or not _within(candidate, snapshot_dir):
                raise SnapshotResolutionError(
                    f"El archivo de {record_id!r} no pertenece al directorio archivado del snapshot",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="archived_path_outside_snapshot",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            normalized_path = candidate.as_posix()
            if normalized_path in seen_paths:
                raise SnapshotResolutionError(
                    f"El manifest PIT repite archived_path para {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="archived_path_duplicate",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            seen_paths.add(normalized_path)
            if not candidate.is_file():
                raise SnapshotResolutionError(
                    f"No existe el archivo archivado de {record_id!r}: {candidate}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="missing",
                    scoreability_status="not_scoreable_source_missing",
                    reason="archived_file_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )

            expected_bytes = record.get("bytes")
            expected_sha = str(record.get("sha256", "")).strip().lower()
            if (
                not isinstance(expected_bytes, int)
                or isinstance(expected_bytes, bool)
                or expected_bytes < 0
            ):
                raise SnapshotResolutionError(
                    f"El manifest PIT no tiene bytes válidos para {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="archived_bytes_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
                raise SnapshotResolutionError(
                    f"El manifest PIT no tiene SHA-256 válido para {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="archived_sha256_missing",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )
            actual_bytes = candidate.stat().st_size
            actual_sha = sha256_file(candidate)
            if actual_bytes != expected_bytes or actual_sha != expected_sha:
                raise SnapshotResolutionError(
                    f"Hash o tamaño inválido para el archivo archivado de {record_id!r}",
                    origin=origin,
                    source_id=record_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="archived_hash_mismatch",
                    snapshot_manifest=_manifest_relative(path, self.paths),
                )

        return records

    def _record_error(
        self,
        error: SnapshotResolutionError,
        origin: ForecastOrigin,
        source_ids: Iterable[str],
    ) -> None:
        if self.coverage_ledger is None:
            return
        for source_id in source_ids:
            for horizon in self.horizons:
                self.coverage_ledger.record_exclusion(
                    source_id=source_id,
                    origin=origin,
                    horizon_months=horizon,
                    reason=error.reason,
                    coverage_status=error.coverage_status,
                    scoreability_status=error.scoreability_status,
                    snapshot_manifest=error.snapshot_manifest,
                )

    def resolve(
        self,
        origin: ForecastOrigin,
        required_source_ids: tuple[str, ...] = (BANREP_TRM_SOURCE_ID,),
        *,
        source_id: str | None = None,
        strict: bool = True,
    ) -> PointInTimeSnapshot:
        """Resuelve un snapshot válido y solo sus fuentes archivadas.

        ``strict=True`` (por defecto) lanza ``SnapshotResolutionError`` ante
        cualquier ausencia o inconsistencia. Con ``strict=False`` devuelve un
        objeto inválido con estado explícito, después de registrar el ledger;
        ambos modos evitan cualquier fallback silencioso.
        """

        if not isinstance(origin, ForecastOrigin):
            raise TypeError("SnapshotResolver.resolve requiere ForecastOrigin")
        requested = (str(source_id).strip(),) if source_id is not None else tuple(
            dict.fromkeys(str(item).strip() for item in required_source_ids)
        )
        if not requested:
            requested = (BANREP_TRM_SOURCE_ID,)
        unsupported = [item for item in requested if item != BANREP_TRM_SOURCE_ID]
        if unsupported:
            error = SnapshotResolutionError(
                "Esta capa PIT solo resuelve explícitamente banrep_trm_1; "
                f"fuentes solicitadas no soportadas: {unsupported!r}",
                origin=origin,
                source_id=unsupported[0],
                coverage_status="invalid",
                scoreability_status="not_scoreable_source_missing",
                reason="source_not_supported_by_pit_layer",
            )
            self._record_error(error, origin, requested)
            if strict:
                raise error
            return PointInTimeSnapshot(
                origin=origin,
                source_vintages=(),
                manifest_sha256="",
                mode=SNAPSHOT_MODE,
                status=error.scoreability_status,
                reason=error.reason,
            )

        try:
            manifest_path = self._manifest_path(origin)
            manifest = self._load_manifest(manifest_path, origin)
            records = self._validate_manifest_integrity(manifest_path, manifest, origin)
            by_id = {str(record["id"]): record for record in records}
            manifest_ref = _manifest_relative(manifest_path, self.paths)
            vintages: list[SourceVintage] = []
            observation_counts: dict[str, int] = {}
            for requested_id in requested:
                record = by_id.get(requested_id)
                if record is None:
                    raise SnapshotResolutionError(
                        f"El snapshot no contiene la fuente requerida {requested_id!r}",
                        origin=origin,
                        source_id=requested_id,
                        coverage_status="missing",
                        scoreability_status="not_scoreable_source_missing",
                        reason="source_vintage_missing",
                        snapshot_manifest=manifest_ref,
                    )
                archived_path = str(record["archived_path"])
                candidate = _resolve_project_path(archived_path, self.paths)
                observations = _read_archived_observations(candidate, requested_id)
                observation_counts[requested_id] = int(len(observations))
                observed_through = observations["date"].max()
                declared_through = _optional_timestamp(
                    record.get(
                        "available_through",
                        record.get("available_until", manifest.get("available_through")),
                    ),
                    f"{requested_id}.available_through",
                )
                available_through = declared_through or observed_through
                limit = origin.effective_cutoff
                if available_through > limit:
                    raise SnapshotResolutionError(
                        f"La disponibilidad de {requested_id!r} ({available_through:%Y-%m-%d}) "
                        f"es posterior al corte PIT ({limit:%Y-%m-%d})",
                        origin=origin,
                        source_id=requested_id,
                        coverage_status="incomplete",
                        scoreability_status="not_scoreable_coverage_incomplete",
                        reason="available_through_after_origin_or_cutoff",
                        snapshot_manifest=manifest_ref,
                    )
                if (observations["date"] > limit).any():
                    future_date = observations.loc[observations["date"] > limit, "date"].max()
                    raise SnapshotResolutionError(
                        f"El archivo de {requested_id!r} contiene observaciones posteriores "
                        f"al origen/corte ({future_date:%Y-%m-%d})",
                        origin=origin,
                        source_id=requested_id,
                        coverage_status="incomplete",
                        scoreability_status="not_scoreable_coverage_incomplete",
                        reason="observation_after_origin_or_cutoff",
                        snapshot_manifest=manifest_ref,
                    )
                if observed_through > available_through:
                    raise SnapshotResolutionError(
                        f"El archivo de {requested_id!r} excede available_through declarado",
                        origin=origin,
                        source_id=requested_id,
                        coverage_status="invalid",
                        scoreability_status="not_scoreable_snapshot_invalid",
                        reason="observation_after_declared_availability",
                        snapshot_manifest=manifest_ref,
                    )
                vintage_id = str(
                    record.get(
                        "vintage_id",
                        record.get("vintage", manifest.get("vintage_id", manifest["origin_date"])),
                    )
                )
                vintages.append(
                    SourceVintage(
                        source_id=requested_id,
                        vintage_id=vintage_id,
                        snapshot_manifest=manifest_ref,
                        archived_path=archived_path,
                        available_through=available_through,
                        sha256=str(record["sha256"]),
                    )
                )
            snapshot = PointInTimeSnapshot(
                origin=origin,
                source_vintages=tuple(vintages),
                manifest_sha256=sha256_file(manifest_path),
                mode=SNAPSHOT_MODE,
                status="valid",
            )
            for vintage in snapshot.source_vintages:
                for horizon in self.horizons:
                    self.coverage_ledger.record_coverage(
                        source_id=vintage.source_id,
                        origin=origin,
                        horizon_months=horizon,
                        snapshot_manifest=manifest_ref,
                        source_vintage=vintage.vintage_id,
                        available_through=vintage.available_through,
                        sha256=vintage.sha256,
                        n_observations_available=observation_counts[vintage.source_id],
                        n_missing=0,
                        coverage_status="complete",
                        scoreability_status="scoreable",
                    )
            return snapshot
        except SnapshotResolutionError as error:
            self._record_error(error, origin, requested)
            if strict:
                raise
            return PointInTimeSnapshot(
                origin=origin,
                source_vintages=(),
                manifest_sha256="",
                mode=SNAPSHOT_MODE,
                status=error.scoreability_status,
                reason=error.reason,
            )
        except SnapshotSeriesError as error:
            resolution_error = SnapshotResolutionError(
                str(error),
                origin=origin,
                source_id=error.source_id or requested[0],
                coverage_status=error.coverage_status,
                scoreability_status=error.scoreability_status,
                reason=error.reason,
            )
            self._record_error(resolution_error, origin, requested)
            if strict:
                raise resolution_error from error
            return PointInTimeSnapshot(
                origin=origin,
                source_vintages=(),
                manifest_sha256="",
                mode=SNAPSHOT_MODE,
                status=resolution_error.scoreability_status,
                reason=resolution_error.reason,
            )
        except (KeyError, TypeError, ValueError) as error:
            resolution_error = SnapshotResolutionError(
                f"Metadato PIT inválido: {error}",
                origin=origin,
                source_id=requested[0],
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="snapshot_metadata_invalid",
            )
            self._record_error(resolution_error, origin, requested)
            if strict:
                raise resolution_error from error
            return PointInTimeSnapshot(
                origin=origin,
                source_vintages=(),
                manifest_sha256="",
                mode=SNAPSHOT_MODE,
                status=resolution_error.scoreability_status,
                reason=resolution_error.reason,
            )


class PointInTimeSeriesStore:
    """Lee y mensualiza una fuente exclusivamente desde un snapshot validado."""

    def __init__(
        self,
        paths: ProjectPaths | Path | str | None = None,
        *,
        coverage_ledger: CoverageLedger | None = None,
        horizons: Iterable[int] = (6, 12),
    ) -> None:
        self.paths = _project(paths)
        self.horizons = tuple(int(horizon) for horizon in horizons)
        self.coverage_ledger = (
            coverage_ledger
            if coverage_ledger is not None
            else CoverageLedger(default_horizons=self.horizons)
        )

    def _archived_file(
        self,
        snapshot: PointInTimeSnapshot,
        vintage: SourceVintage,
    ) -> Path:
        if not snapshot.valid:
            raise SnapshotSeriesError(
                "El snapshot no es válido para lectura PIT",
                origin=snapshot.origin,
                source_id=vintage.source_id,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason=snapshot.reason or "snapshot_not_valid",
            )
        manifest_path = _resolve_project_path(vintage.snapshot_manifest, self.paths)
        if not manifest_path.is_file():
            raise SnapshotSeriesError(
                f"No existe el manifest asociado a la fuente archivada: {manifest_path}",
                origin=snapshot.origin,
                source_id=vintage.source_id,
                coverage_status="missing",
                scoreability_status="not_scoreable_snapshot_missing",
                reason="snapshot_manifest_missing",
            )
        candidate = _resolve_project_path(vintage.archived_path, self.paths)
        if not _within(candidate, manifest_path.parent):
            raise SnapshotSeriesError(
                "PointInTimeSeriesStore solo acepta archivos dentro del snapshot archivado",
                origin=snapshot.origin,
                source_id=vintage.source_id,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="archived_path_outside_snapshot",
            )
        if not candidate.is_file():
            raise SnapshotSeriesError(
                f"No existe el archivo archivado: {candidate}",
                origin=snapshot.origin,
                source_id=vintage.source_id,
                coverage_status="missing",
                scoreability_status="not_scoreable_source_missing",
                reason="archived_file_missing",
            )
        if sha256_file(candidate) != vintage.sha256:
            raise SnapshotSeriesError(
                f"Cambió el archivo archivado de {vintage.source_id!r}; hash inválido",
                origin=snapshot.origin,
                source_id=vintage.source_id,
                coverage_status="invalid",
                scoreability_status="not_scoreable_snapshot_invalid",
                reason="archived_hash_mismatch",
            )
        return candidate

    def _record_error(self, error: SnapshotSeriesError, snapshot: PointInTimeSnapshot) -> None:
        if self.coverage_ledger is None:
            return
        for horizon in self.horizons:
            self.coverage_ledger.record_exclusion(
                source_id=error.source_id or BANREP_TRM_SOURCE_ID,
                origin=snapshot.origin,
                horizon_months=horizon,
                reason=error.reason,
                coverage_status=error.coverage_status,
                scoreability_status=error.scoreability_status,
                snapshot_manifest=snapshot.snapshot_manifest,
            )

    def monthly_series(
        self,
        snapshot: PointInTimeSnapshot,
        source_id: str = BANREP_TRM_SOURCE_ID,
        *,
        through: pd.Timestamp,
    ) -> pd.Series:
        """Devuelve TRM mensual con exactamente ``resample("MS").mean()``.

        La función valida todo el archivo antes de mensualizarlo. Por eso una
        observación futura, una fecha inválida o un valor no positivo no se
        puede ocultar filtrando filas o completando meses.
        """

        if not isinstance(snapshot, PointInTimeSnapshot):
            raise TypeError("monthly_series requiere PointInTimeSnapshot")
        source_id = str(source_id).strip()
        if source_id != BANREP_TRM_SOURCE_ID:
            error = SnapshotSeriesError(
                "PointInTimeSeriesStore solo admite source_id='banrep_trm_1'",
                origin=snapshot.origin,
                source_id=source_id,
                coverage_status="invalid",
                scoreability_status="not_scoreable_source_missing",
                reason="source_not_supported_by_pit_layer",
            )
            self._record_error(error, snapshot)
            raise error
        try:
            requested_through = _timestamp(through, "through")
            effective_limit = snapshot.origin.effective_cutoff
            if requested_through > effective_limit:
                raise SnapshotSeriesError(
                    "through no puede ser posterior al origen o Data_Cutoff",
                    origin=snapshot.origin,
                    source_id=source_id,
                    coverage_status="invalid",
                    scoreability_status="not_scoreable_snapshot_invalid",
                    reason="through_after_origin_or_cutoff",
                )
            vintage = snapshot.source(source_id)
            if vintage.available_through > effective_limit:
                raise SnapshotSeriesError(
                    "available_through es posterior al origen o Data_Cutoff",
                    origin=snapshot.origin,
                    source_id=source_id,
                    coverage_status="incomplete",
                    scoreability_status="not_scoreable_coverage_incomplete",
                    reason="available_through_after_origin_or_cutoff",
                )
            archived_file = self._archived_file(snapshot, vintage)
            observations = _read_archived_observations(archived_file, source_id)
            if (observations["date"] > effective_limit).any():
                future_date = observations.loc[
                    observations["date"] > effective_limit, "date"
                ].max()
                raise SnapshotSeriesError(
                    f"El snapshot contiene observaciones posteriores al origen: {future_date:%Y-%m-%d}",
                    origin=snapshot.origin,
                    source_id=source_id,
                    coverage_status="incomplete",
                    scoreability_status="not_scoreable_coverage_incomplete",
                    reason="observation_after_origin",
                )
            if (observations["date"] > requested_through).any():
                future_date = observations.loc[
                    observations["date"] > requested_through, "date"
                ].max()
                raise SnapshotSeriesError(
                    f"El archivo contiene observaciones posteriores a through: {future_date:%Y-%m-%d}",
                    origin=snapshot.origin,
                    source_id=source_id,
                    coverage_status="incomplete",
                    scoreability_status="not_scoreable_coverage_incomplete",
                    reason="observation_after_requested_through",
                )
            selected = observations.loc[observations["date"] <= requested_through]
            if selected.empty:
                raise SnapshotSeriesError(
                    "No hay observaciones TRM dentro del corte PIT solicitado",
                    origin=snapshot.origin,
                    source_id=source_id,
                    coverage_status="missing",
                    scoreability_status="not_scoreable_coverage_incomplete",
                    reason="no_observations_through_cutoff",
                )
            series = selected.set_index("date")["value"].sort_index().resample("MS").mean()
            series.name = source_id
            return series.sort_index()
        except SnapshotSeriesError as error:
            self._record_error(error, snapshot)
            raise

    def register_monthly_coverage(
        self,
        snapshot: PointInTimeSnapshot,
        *,
        source_id: str = BANREP_TRM_SOURCE_ID,
        horizon_months: int,
        through: pd.Timestamp,
        required_for_candidate: bool | str = True,
    ) -> CoverageRecord:
        """Mensualiza y registra faltantes sin alterar la serie ni imputar."""

        series = self.monthly_series(snapshot, source_id, through=through)
        through_date = _timestamp(through, "through")
        first_date = series.index.min()
        expected = pd.date_range(first_date, through_date.to_period("M").to_timestamp(), freq="MS")
        missing_index = expected.difference(series.index[series.notna()])
        missing = int(len(missing_index))
        status: CoverageStatus = "complete" if missing == 0 else "incomplete"
        scoreability = "scoreable" if missing == 0 else "not_scoreable_coverage_incomplete"
        vintage = snapshot.source(source_id)
        return self.coverage_ledger.record_coverage(
            source_id=source_id,
            origin=snapshot.origin,
            horizon_months=horizon_months,
            snapshot_manifest=snapshot.snapshot_manifest,
            source_vintage=vintage.vintage_id,
            available_through=vintage.available_through,
            sha256=vintage.sha256,
            n_observations_available=int(series.notna().sum()),
            n_missing=missing,
            coverage_status=status,
            scoreability_status=scoreability,
            required_for_candidate=required_for_candidate,
            reason=None if status == "complete" else "missing_months_without_imputation",
        ) if self.coverage_ledger is not None else CoverageRecord(
            source_id=source_id,
            origin_date=snapshot.origin.origin_date,
            horizon_months=horizon_months,
            snapshot_manifest=snapshot.snapshot_manifest,
            source_vintage=vintage.vintage_id,
            available_through=vintage.available_through,
            sha256=vintage.sha256,
            n_observations_available=int(series.notna().sum()),
            n_missing=missing,
            coverage_status=status,
            scoreability_status=scoreability,
            required_for_candidate=required_for_candidate,
            reason=None if status == "complete" else "missing_months_without_imputation",
        )


# Protocol-like aliases retained for code that imports the interface names from
# the design document. The concrete classes above are intentionally usable.
SnapshotResolverProtocol = SnapshotResolver
PointInTimeSeriesStoreProtocol = PointInTimeSeriesStore

__all__ = [
    "BANREP_TRM_SOURCE_ID",
    "SNAPSHOT_MODE",
    "NOT_EVALUABLE_LABEL_NOT_MATURE",
    "NOT_SCOREABLE_COVERAGE_INCOMPLETE",
    "NOT_SCOREABLE_SNAPSHOT_INVALID",
    "NOT_SCOREABLE_SNAPSHOT_MISSING",
    "NOT_SCOREABLE_SOURCE_MISSING",
    "CoverageEntry",
    "CoverageLedger",
    "CoverageLedgerRecord",
    "CoverageRecord",
    "CoverageStatus",
    "ForecastOrigin",
    "PointInTimeSeriesStore",
    "PointInTimeSeriesStoreProtocol",
    "PointInTimeSnapshot",
    "ScoreabilityStatus",
    "SnapshotError",
    "SnapshotResolutionError",
    "SnapshotResolver",
    "SnapshotResolverProtocol",
    "SnapshotSeriesError",
    "SourceVintage",
]
