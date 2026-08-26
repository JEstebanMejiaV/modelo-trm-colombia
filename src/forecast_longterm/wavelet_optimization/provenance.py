"""Provenance extendida para la investigación wavelet point-in-time.

El recorder es deliberadamente independiente del publisher y del runner de la
variante. Construye el manifest común del repositorio mediante
``build_run_manifest`` y agrega, bajo ``run_context.wavelet_optimization``, la
identidad preinscrita, los snapshots/vintages, la cobertura y los outputs de la
investigación. El estado de ejecución del manifest común sigue el contrato
``running/success/failed``; el estado de producto de esta variante se conserva
siempre como ``research`` dentro del contexto extendido.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from trm_model.paths import ProjectPaths
from trm_model.provenance.environment import environment_snapshot
from trm_model.provenance.hashes import file_records, sha256_file
from trm_model.provenance.manifest import (
    build_run_manifest,
    git_state,
    make_run_id,
    utc_now,
    write_run_manifest,
)

from .config import (
    BENCHMARK_ID,
    BENCHMARK_RETURN_PREDICTION,
    BOUNDARY_MODE,
    DWT_LEVELS,
    EXPERIMENT_ID,
    H1,
    H2,
    LABEL_MATURITY_RULE,
    MINIMUM_MATURE_TRAINING,
    PRODUCT_ID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    RESEARCH_STATUS,
    SEED,
    SIGNAL_SCALE,
    TARGET_DEFINITION,
    TARGET_SERIES,
    WAVELET_FAMILY,
)

OUTPUT_NAMESPACE = "results/pronostico/wavelet_optimization"
DEFAULT_OUTPUT_PATHS = (
    f"{OUTPUT_NAMESPACE}/predicciones_por_origen.csv",
    f"{OUTPUT_NAMESPACE}/evaluacion_por_candidato.csv",
    f"{OUTPUT_NAMESPACE}/cobertura_point_in_time.csv",
    f"{OUTPUT_NAMESPACE}/hipotesis_decision.json",
)
DEFAULT_CONFIG_PATHS = (
    "research/configs/long_horizon_wavelet_optimization.toml",
    "schemas/long_horizon_wavelet_optimization.json",
)

# Estas advertencias son parte del contrato de investigación y no se eliminan
# aunque no haya fallas de cobertura. Sirven para que un manifest aislado siga
# siendo interpretable fuera del repositorio.
RESEARCH_WARNINGS = (
    "exploratory_research: predictive association does not identify a causal effect",
    "research_output_not_financial_advice: results are not instructions for hedging, portfolio allocation or economic policy",
    "wavelet_outputs_isolated_from_monthly_forecast",
)


class ProvenanceError(ValueError):
    """Error de identidad, integridad o estructura del provenance."""


class MissingProvenanceError(ProvenanceError):
    """La corrida no tiene los campos necesarios para declararse completa."""


class OutputReconciliationError(ProvenanceError):
    """Los outputs declarados no concilian con los records del manifest."""


def _value(value: Any, *names: str, default: Any = None) -> Any:
    """Lee un campo de mappings, dataclasses y adaptadores ligeros."""

    if value is None:
        return default
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    for method_name in ("as_dict", "to_dict", "as_record", "to_record"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            converted = method()
        except TypeError:
            continue
        if isinstance(converted, Mapping):
            return converted
    return None


def _materialize(value: Any) -> tuple[Any, ...]:
    """Materializa listas, frames y ledgers sin depender de una clase concreta."""

    if value is None:
        return ()
    if isinstance(value, pd.DataFrame):
        return tuple(value.to_dict(orient="records"))
    for method_name in (
        "as_dicts",
        "to_dicts",
        "as_records",
        "to_records",
        "to_dict",
    ):
        method = getattr(value, method_name, None)
        if not callable(method) or isinstance(value, Mapping):
            continue
        try:
            converted = method()
        except TypeError:
            continue
        if isinstance(converted, Mapping):
            # ``DataFrame.to_dict()`` sin orient no es una lista de filas; en
            # ese caso se deja que la rama de DataFrame anterior lo maneje.
            return (converted,)
        if isinstance(converted, Iterable) and not isinstance(converted, (str, bytes)):
            return tuple(converted)
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (str, bytes, bytearray)):
        return ()
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _date_text(value: Any) -> str | None:
    if value is None or value is pd.NaT:
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize().strftime("%Y-%m-%d")


def _datetime_utc(value: datetime | None) -> datetime:
    if value is None:
        return utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_safe(value: Any) -> Any:
    """Convierte objetos de pandas/numpy/path a valores JSON sin NaN."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, (pd.Timestamp, datetime)):
        if isinstance(value, pd.Timestamp) and value.tzinfo is None:
            return value.isoformat()
        return value.isoformat()
    if isinstance(value, pd.Period):
        return str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    mapped = _as_mapping(value)
    if mapped is not None:
        return _json_safe(mapped)
    try:
        import json

        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return str(value)
    return value


def _dedupe(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for raw in values:
        text = str(raw).strip()
        if text and text not in result:
            result.append(text)
    return result


def _plan_mapping(plan: Any) -> dict[str, Any]:
    mapped = _as_mapping(plan)
    if mapped is not None:
        result = dict(mapped)
    else:
        result = {}
        for name in (
            "experiment_id",
            "product_id",
            "status",
            "information_set",
            "vintage_policy",
            "target_series",
            "horizons",
            "splits",
            "candidates",
            "minimum_mature_training",
            "dm_min_observations",
            "dm_max_lag_rule",
            "data_cutoff",
            "origin_dates",
            "primary_metric",
            "selection_rule",
            "tie_break_rule",
            "seed",
            "hypotheses",
            "plan_hash",
        ):
            if hasattr(plan, name):
                result[name] = getattr(plan, name)
    if "horizons_months" in result and "horizons" not in result:
        result["horizons"] = result["horizons_months"]
    if "evaluation_splits" in result and "splits" not in result:
        result["splits"] = result["evaluation_splits"]
    return result


def _candidate_records(plan: Any) -> list[dict[str, Any]]:
    values = _value(plan, "candidates", "candidate_grid", default=())
    records: list[dict[str, Any]] = []
    for candidate in _materialize(values):
        mapped = _as_mapping(candidate)
        if mapped is None:
            continue
        record = _json_safe(dict(mapped))
        candidate_id = str(record.get("candidate_id", record.get("id", ""))).strip()
        if candidate_id:
            record.setdefault("candidate_id", candidate_id)
        records.append(record)
    return sorted(records, key=lambda item: str(item.get("candidate_id", item.get("id", ""))))


def _hypothesis_records(plan: Any) -> list[dict[str, str]]:
    values = _value(plan, "hypotheses", default=())
    records: list[dict[str, str]] = []
    for value in _materialize(values):
        mapped = _as_mapping(value)
        if mapped is None:
            continue
        code = next(
            (
                str(mapped[key]).strip()
                for key in ("id", "hypothesis_id", "code", "name", "key")
                if mapped.get(key) is not None
            ),
            None,
        )
        if code is None:
            for candidate_code in (H1, H2):
                if candidate_code in mapped:
                    code = candidate_code
                    break
        text = next(
            (
                str(mapped[key]).strip()
                for key in ("statement", "text", "description", "hypothesis")
                if mapped.get(key) is not None
            ),
            None,
        )
        if code and text:
            records.append({"id": code, "statement": text})
    return sorted(records, key=lambda item: item["id"])


def _rows_from_bundle(bundle: Any, name: str) -> tuple[Any, ...]:
    if bundle is None:
        return ()
    value = _value(bundle, name, default=None)
    if value is None and name == "predictions":
        value = _value(bundle, "all_predictions", "origin_predictions", default=None)
    return _materialize(value)


def _row_record(row: Any) -> dict[str, Any]:
    mapped = _as_mapping(row)
    if mapped is None:
        return {"value": _json_safe(row)}
    return {str(key): _json_safe(value) for key, value in mapped.items()}


def _origin_key(row: Mapping[str, Any]) -> str | None:
    value = row.get("origin_date", row.get("origin"))
    if isinstance(value, Mapping):
        value = value.get("origin_date")
    return _date_text(value)


def _coverage_records(bundle: Any) -> list[dict[str, Any]]:
    rows = [_row_record(row) for row in _rows_from_bundle(bundle, "coverage")]
    predictions = [_row_record(row) for row in _rows_from_bundle(bundle, "predictions")]
    known = {
        (str(row.get("source_id", TARGET_SERIES)), _origin_key(row), int(row.get("horizon_months", 0) or 0))
        for row in rows
        if _origin_key(row) is not None
    }
    # Un bundle construido manualmente puede contener solo predicciones. Se
    # conserva igualmente una fila de cobertura separada del desempeño.
    for prediction in predictions:
        origin = _origin_key(prediction)
        try:
            horizon = int(prediction.get("horizon_months"))
        except (TypeError, ValueError):
            continue
        key = (TARGET_SERIES, origin, horizon)
        if origin is None or key in known:
            continue
        rows.append(
            {
                "source_id": TARGET_SERIES,
                "origin_date": origin,
                "horizon_months": horizon,
                "snapshot_manifest": prediction.get("snapshot_manifest"),
                "source_vintage": prediction.get("source_vintage"),
                "available_through": prediction.get("prefix_last_date"),
                "sha256": None,
                "n_observations_available": 0,
                "n_missing": 0,
                "coverage_status": prediction.get("coverage_status", "incomplete"),
                "scoreability_status": prediction.get("scoreability_status"),
                "required_for_candidate": True,
                "excluded_origins": [origin]
                if prediction.get("scoreability_status") not in {None, "scoreable"}
                else [],
                "reason": prediction.get("warning"),
            }
        )
        known.add(key)

    normalized: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        if record.get("origin_date") is not None:
            record["origin_date"] = _date_text(record["origin_date"])
        if record.get("available_through") is not None:
            record["available_through"] = _date_text(record["available_through"])
        if "excluded_origins" in record:
            excluded = record["excluded_origins"]
            if isinstance(excluded, (str, bytes)):
                excluded = [excluded]
            record["excluded_origins"] = sorted(
                _dedupe(_date_text(item) or str(item) for item in (excluded or ()))
            )
        record.setdefault("coverage_status", "incomplete")
        record.setdefault("scoreability_status", "not_scoreable_coverage_incomplete")
        record.setdefault("n_observations_available", 0)
        record.setdefault("n_missing", 0)
        # A coverage row must never carry predictive metrics. This is an
        # explicit defence against accidentally serializing an EvaluationMetrics
        # record into the PIT ledger.
        for metric_name in (
            "r2_oos",
            "sse_model",
            "sse_random_walk",
            "mae_model",
            "mae_random_walk",
            "rmse_model",
            "rmse_random_walk",
            "dm_p_value",
        ):
            record.pop(metric_name, None)
        normalized.append(_json_safe(record))
    return sorted(
        normalized,
        key=lambda row: (
            str(row.get("origin_date", "")),
            int(row.get("horizon_months", 0) or 0),
            str(row.get("source_id", "")),
        ),
    )


def _prediction_records(bundle: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _rows_from_bundle(bundle, "predictions"):
        record = _row_record(row)
        if record.get("origin_date") is not None:
            record["origin_date"] = _date_text(record["origin_date"])
        if record.get("label_end_date") is not None:
            record["label_end_date"] = _date_text(record["label_end_date"])
        if record.get("prefix_last_date") is not None:
            record["prefix_last_date"] = _date_text(record["prefix_last_date"])
        if record.get("data_cutoff") is not None:
            record["data_cutoff"] = _date_text(record["data_cutoff"])
        records.append(_json_safe(record))
    return sorted(
        records,
        key=lambda row: (
            str(row.get("origin_date", "")),
            int(row.get("horizon_months", 0) or 0),
            str(row.get("candidate_id", "")),
            str(row.get("split", "full")),
        ),
    )


def _metrics_records(bundle: Any) -> list[dict[str, Any]]:
    records = [_row_record(row) for row in _rows_from_bundle(bundle, "metrics")]
    return sorted(
        [_json_safe(record) for record in records],
        key=lambda row: (
            str(row.get("candidate_id", "")),
            int(row.get("horizon_months", 0) or 0),
            str(row.get("split", "")),
        ),
    )


def _decision_records(bundle: Any) -> list[dict[str, Any]]:
    records = [_row_record(row) for row in _rows_from_bundle(bundle, "decisions")]
    return sorted([_json_safe(record) for record in records], key=lambda row: str(row))


def _normalise_path(value: Any, *, paths: ProjectPaths) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("path", value.get("archived_path", value.get("snapshot_manifest")))
    if value is None:
        return None
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (paths.root / path).resolve()


def _safe_relative(path: Path, *, paths: ProjectPaths) -> str:
    try:
        return paths.relative(path)
    except ValueError as error:
        raise ProvenanceError(f"La ruta está fuera de la raíz del proyecto: {path}") from error


def _unique_paths(values: Iterable[Path]) -> tuple[Path, ...]:
    result: dict[Path, None] = {}
    for value in values:
        result[value.resolve()] = None
    return tuple(sorted(result, key=str))


def _snapshot_and_vintage_records(
    plan: Any,
    bundle: Any,
    snapshots: Iterable[Any],
    *,
    paths: ProjectPaths,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], tuple[Path, ...], list[str]]:
    """Construye registros ricos a partir de snapshots reales y/o cobertura."""

    groups: dict[str, dict[str, Any]] = {}
    vintage_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    warnings: list[str] = []

    def group_for(origin: Any) -> dict[str, Any]:
        origin_text = _date_text(origin) or "unknown"
        return groups.setdefault(
            origin_text,
            {
                "origin_date": origin_text,
                "snapshot_manifest": None,
                "manifest_sha256": None,
                "mode": None,
                "status": "not_recorded",
                "reason": None,
                "source_vintages": [],
            },
        )

    for snapshot in _materialize(snapshots):
        snap_map = _as_mapping(snapshot) or {}
        origin_object = _value(snapshot, "origin", default=None)
        origin = _value(origin_object, "origin_date", default=None)
        if origin is None:
            origin = _value(snapshot, "origin_date", default=None)
        if origin is None:
            warnings.append("snapshot_without_origin_date")
            continue
        group = group_for(origin)
        manifest = _value(snapshot, "snapshot_manifest", default=None)
        if manifest is None:
            manifest = _value(origin_object, "snapshot_manifest", default=None)
        if manifest is None:
            manifest = snap_map.get("manifest")
        group["snapshot_manifest"] = manifest
        group["manifest_sha256"] = _value(snapshot, "manifest_sha256", default=None)
        group["mode"] = _value(snapshot, "mode", default=None)
        group["status"] = _value(snapshot, "status", default="valid")
        group["reason"] = _value(snapshot, "reason", default=None)
        for vintage in _materialize(_value(snapshot, "source_vintages", default=())):
            source_id = str(_value(vintage, "source_id", "id", default="")).strip()
            vintage_id = str(_value(vintage, "vintage_id", "source_vintage", default="")).strip()
            if not source_id:
                warnings.append("source_vintage_without_source_id")
                continue
            source_manifest = _value(vintage, "snapshot_manifest", default=manifest)
            key = (_date_text(origin) or "unknown", source_id, vintage_id)
            record = {
                "origin_date": _date_text(origin),
                "source_id": source_id,
                "vintage_id": vintage_id or None,
                "snapshot_manifest": source_manifest,
                "archived_path": _value(vintage, "archived_path", "path", default=None),
                "available_through": _date_text(
                    _value(vintage, "available_through", default=None)
                ),
                "sha256": _value(vintage, "sha256", "source_sha256", default=None),
                "manifest_sha256": group["manifest_sha256"],
            }
            vintage_by_key[key] = _json_safe(record)
            group["source_vintages"].append(vintage_by_key[key])

    # La EvaluationBundle no conserva los objetos PointInTimeSnapshot. Sus
    # filas de cobertura son la segunda fuente canónica para reconstruir la
    # identidad observable de cada origen/vintage.
    for row in _coverage_records(bundle):
        origin = _origin_key(row)
        if origin is None:
            continue
        group = group_for(origin)
        manifest = row.get("snapshot_manifest")
        if manifest and not group.get("snapshot_manifest"):
            group["snapshot_manifest"] = manifest
        if manifest:
            group["status"] = "observed"
        source_id = str(row.get("source_id", TARGET_SERIES)).strip()
        vintage_id = str(row.get("source_vintage", "")).strip()
        key = (origin, source_id, vintage_id)
        if key not in vintage_by_key and (vintage_id or row.get("sha256")):
            vintage_by_key[key] = _json_safe(
                {
                    "origin_date": origin,
                    "source_id": source_id,
                    "vintage_id": vintage_id or None,
                    "snapshot_manifest": manifest,
                    "archived_path": row.get("archived_path"),
                    "available_through": _date_text(row.get("available_through")),
                    "sha256": row.get("sha256"),
                    "manifest_sha256": row.get("manifest_sha256"),
                }
            )
        if key in vintage_by_key and vintage_by_key[key] not in group["source_vintages"]:
            group["source_vintages"].append(vintage_by_key[key])

    plan_origins = _value(plan, "origin_dates", default=()) or ()
    for origin in plan_origins:
        group_for(origin)

    input_paths: list[Path] = []
    for group in groups.values():
        manifest = group.get("snapshot_manifest")
        manifest_path = _normalise_path(manifest, paths=paths)
        if manifest_path is not None:
            try:
                group["snapshot_manifest"] = _safe_relative(manifest_path, paths=paths)
                if manifest_path.is_file():
                    group["manifest_sha256"] = sha256_file(manifest_path)
                    input_paths.append(manifest_path)
                else:
                    warnings.append(f"snapshot_manifest_missing:{group['origin_date']}")
            except ProvenanceError:
                warnings.append(f"snapshot_manifest_outside_project:{manifest}")
        for vintage in group["source_vintages"]:
            archived_path = _normalise_path(vintage.get("archived_path"), paths=paths)
            if archived_path is not None:
                try:
                    vintage["archived_path"] = _safe_relative(archived_path, paths=paths)
                    if archived_path.is_file():
                        input_paths.append(archived_path)
                        actual_hash = sha256_file(archived_path)
                        vintage["archived_file_sha256"] = actual_hash
                        declared_hash = vintage.get("sha256")
                        if declared_hash and str(declared_hash).lower() != actual_hash:
                            warnings.append(
                                f"source_vintage_hash_mismatch:{vintage.get('source_id')}:{group['origin_date']}"
                            )
                    else:
                        warnings.append(
                            f"source_vintage_file_missing:{vintage.get('source_id')}:{group['origin_date']}"
                        )
                except ProvenanceError:
                    warnings.append(f"source_vintage_outside_project:{archived_path}")

    snapshot_records = []
    for origin in sorted(groups):
        group = groups[origin]
        group["source_vintages"] = sorted(
            group["source_vintages"],
            key=lambda row: (str(row.get("source_id", "")), str(row.get("vintage_id", ""))),
        )
        snapshot_records.append(_json_safe(group))
    vintage_records = sorted(
        vintage_by_key.values(),
        key=lambda row: (
            str(row.get("origin_date", "")),
            str(row.get("source_id", "")),
            str(row.get("vintage_id", "")),
        ),
    )
    return snapshot_records, vintage_records, _unique_paths(input_paths), _dedupe(warnings)


def _output_descriptors(
    values: Iterable[Any] | Any,
    *,
    paths: ProjectPaths,
) -> tuple[list[dict[str, Any]], tuple[Path, ...]]:
    if values is None:
        values = DEFAULT_OUTPUT_PATHS
    if isinstance(values, Mapping) or isinstance(values, (str, Path)):
        values = (values,)
    descriptors: list[dict[str, Any]] = []
    resolved: list[Path] = []
    seen: set[str] = set()
    for value in _materialize(values):
        path_value = _value(value, "path", default=value)
        path = _normalise_path(path_value, paths=paths)
        if path is None:
            continue
        relative = _safe_relative(path, paths=paths)
        if not relative.startswith(OUTPUT_NAMESPACE + "/"):
            raise OutputReconciliationError(
                f"Output fuera del namespace de investigación: {relative}"
            )
        if relative in seen:
            raise OutputReconciliationError(f"Output repetido en provenance: {relative}")
        seen.add(relative)
        descriptor = {
            "path": relative,
            "kind": str(_value(value, "kind", default="research")),
            "status": str(_value(value, "status", default="versioned")),
        }
        if descriptor["kind"] != "research" or descriptor["status"] != "versioned":
            raise OutputReconciliationError(
                f"El output {relative} debe conservar kind=research y status=versioned"
            )
        if path.is_file():
            descriptor.update(
                {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            )
        descriptors.append(descriptor)
        resolved.append(path)
    descriptors.sort(key=lambda row: str(row["path"]))
    return descriptors, _unique_paths(resolved)


def _coverage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(row.get("coverage_status", "incomplete")) for row in rows)
    excluded = sorted(
        {
            str(origin)
            for row in rows
            for origin in row.get("excluded_origins", ()) or ()
        }
    )
    return {
        "n_records": len(rows),
        "n_complete": statuses.get("complete", 0),
        "n_incomplete": statuses.get("incomplete", 0),
        "n_missing": statuses.get("missing", 0),
        "n_invalid": statuses.get("invalid", 0),
        "coverage_status_counts": dict(sorted(statuses.items())),
        "excluded_origins": excluded,
    }


def _missing_fields(context: Mapping[str, Any]) -> list[str]:
    """Devuelve campos de provenance ausentes, no estados de desempeño."""

    missing: list[str] = []
    nonempty_fields = (
        "experiment_id",
        "plan_hash",
        "hypotheses",
        "candidate_grid",
        "dwt",
        "target_definition",
        "horizons",
        "splits",
        "benchmark",
        "label_maturity_rule",
        "minimum_mature_training",
        "data_cutoff",
        "seed",
        "output_paths",
        "git_commit",
        "environment",
        "input_files",
        "coverage",
        "snapshots",
        "source_vintages",
        "warnings",
    )
    for field_name in nonempty_fields:
        value = context.get(field_name)
        if value is None or value == "" or value == [] or value == {}:
            missing.append(field_name)
    if context.get("evaluation_bundle_present") is not True:
        missing.append("evaluation_bundle")
    return missing


def _output_reconciliation_errors(
    manifest: Mapping[str, Any], *, paths: ProjectPaths
) -> list[str]:
    context = _value(manifest.get("run_context"), "wavelet_optimization", default={}) or {}
    declared = tuple(str(item) for item in context.get("output_paths", ()) or ())
    actual = tuple(
        str(item.get("path"))
        for item in manifest.get("output_files", ())
        if isinstance(item, Mapping) and item.get("path")
    )
    errors: list[str] = []
    if not declared:
        errors.append("output_paths")
    if set(declared) != set(actual):
        errors.append("output_paths/output_files")
    for relative in declared:
        path = paths.resolve(relative)
        if not path.is_file():
            errors.append(f"output_file_missing:{relative}")
    return errors


class ProvenanceRecorder:
    """Construye y escribe el manifest extendido de una corrida wavelet.

    ``build_manifest`` puede devolver un manifest incompleto para dejar una
    advertencia auditable. ``write_manifest(..., complete=True)`` y
    ``record(..., complete=True)`` son las operaciones estrictas: no permiten
    persistir una corrida como completa si falta provenance o si los outputs no
    concilian.
    """

    def __init__(
        self,
        paths: ProjectPaths | Path | str | None = None,
        *,
        config_files: Iterable[Path | str] = (),
        input_files: Iterable[Path | str] = (),
        output_paths: Iterable[Path | str | Mapping[str, Any]] | None = None,
        snapshots: Iterable[Any] = (),
        warnings: Iterable[str] = (),
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        if isinstance(paths, ProjectPaths):
            self.paths = paths
        else:
            self.paths = ProjectPaths.from_root(Path(paths) if paths is not None else None)
        self.config_files = tuple(config_files)
        self.input_files = tuple(input_files)
        self.output_paths = tuple(output_paths) if output_paths is not None else None
        self.snapshots = tuple(snapshots)
        self.warnings = tuple(str(item) for item in warnings)
        self.started_at = _datetime_utc(started_at)
        self.finished_at = _datetime_utc(finished_at) if finished_at is not None else None

    def manifest_path(self, run_id: str) -> Path:
        """Devuelve siempre ``artifacts/runs/<Run_ID>/manifest.json``."""

        return self.paths.run_directory(str(run_id)) / "manifest.json"

    def _config_paths(self, values: Iterable[Path | str] | None) -> tuple[Path, ...]:
        selected = tuple(values) if values is not None else self.config_files
        if not selected:
            selected = DEFAULT_CONFIG_PATHS
        paths = [_normalise_path(value, paths=self.paths) for value in selected]
        return _unique_paths(path for path in paths if path is not None and path.is_file())

    def _input_paths(
        self,
        values: Iterable[Path | str] | None,
        *,
        config_paths: tuple[Path, ...],
        snapshot_paths: tuple[Path, ...],
    ) -> tuple[Path, ...]:
        selected = tuple(values) if values is not None else self.input_files
        paths = [_normalise_path(value, paths=self.paths) for value in selected]
        # El catálogo y el registro son contratos de la corrida, aunque el
        # caller no los repita como inputs explícitos.
        paths.extend(
            candidate
            for candidate in (
                self.paths.source_registry(),
                self.paths.root / "experiments" / "registry.json",
            )
            if candidate.is_file()
        )
        paths.extend(config_paths)
        paths.extend(snapshot_paths)
        return _unique_paths(path for path in paths if path is not None and path.is_file())

    def _plan_context(self, plan: Any) -> tuple[dict[str, Any], list[str]]:
        values = _plan_mapping(plan)
        warnings: list[str] = []
        plan_hash = str(values.get("plan_hash", "")).strip()
        compute = getattr(plan, "compute_plan_hash", None)
        if callable(compute):
            try:
                computed = str(compute()).strip()
            except Exception as error:  # pragma: no cover - adaptador externo
                computed = ""
                warnings.append(f"plan_hash_not_computable:{type(error).__name__}")
            if not plan_hash:
                plan_hash = computed
            elif computed and plan_hash != computed:
                warnings.append("plan_hash_mismatch")
        if not plan_hash:
            warnings.append("plan_hash_missing")

        candidates = _candidate_records(plan)
        hypotheses = _hypothesis_records(plan)
        if {item.get("id") for item in hypotheses} != {H1, H2}:
            warnings.append("hypotheses_h1_h2_incomplete")

        candidate = candidates[0] if candidates else {}
        dwt = {
            "wavelet": candidate.get("wavelet_family", WAVELET_FAMILY),
            "wavelet_family": candidate.get("wavelet_family", WAVELET_FAMILY),
            "levels": candidate.get("levels", DWT_LEVELS),
            "boundary_mode": candidate.get("boundary_mode", BOUNDARY_MODE),
            "signal_scale": candidate.get("signal_scale", SIGNAL_SCALE),
        }
        context = {
            "variant_id": "long_horizon_wavelet_optimization",
            "experiment_id": values.get("experiment_id", EXPERIMENT_ID),
            "product_id": values.get("product_id", PRODUCT_ID),
            "status": RESEARCH_STATUS,
            "variant_status": RESEARCH_STATUS,
            "information_set": values.get("information_set", "vintage_backtest"),
            "vintage_policy": values.get("vintage_policy", "vintage_backtest"),
            "target_series": values.get("target_series", TARGET_SERIES),
            "target_definition": TARGET_DEFINITION,
            "hypotheses": hypotheses,
            "plan_hash": plan_hash,
            "candidate_grid": candidates,
            "dwt": dwt,
            "dwt_parameters": dwt,
            "horizons": [int(item) for item in (values.get("horizons") or ())],
            "splits": [str(item) for item in (values.get("splits") or ())],
            "benchmark": {
                "id": BENCHMARK_ID,
                "name": "Random_Walk_Benchmark",
                "prediction": BENCHMARK_RETURN_PREDICTION,
                "target_definition": TARGET_DEFINITION,
            },
            "label_maturity_rule": LABEL_MATURITY_RULE,
            "minimum_mature_training": values.get(
                "minimum_mature_training", MINIMUM_MATURE_TRAINING
            ),
            "data_cutoff": _date_text(values.get("data_cutoff")),
            "primary_metric": values.get("primary_metric", "r2_oos"),
            "selection_rule": values.get("selection_rule"),
            "tie_break_rule": values.get("tie_break_rule"),
            "seed": values.get("seed", SEED),
            "origin_dates": sorted(
                _date_text(origin) for origin in (values.get("origin_dates") or ())
            ),
        }
        if context["product_id"] != PRODUCT_ID:
            warnings.append("product_id_mismatch")
        if context["status"] != RESEARCH_STATUS:
            warnings.append("research_status_mismatch")
        if tuple(context["horizons"]) != REQUIRED_HORIZONS:
            warnings.append("horizons_do_not_match_preregistered_variant")
        if tuple(context["splits"]) != REQUIRED_SPLITS:
            warnings.append("splits_do_not_match_preregistered_variant")
        return _json_safe(context), warnings

    def build_manifest(
        self,
        plan: Any,
        bundle: Any = None,
        run_id: str | None = None,
        *,
        complete: bool | None = None,
        config_files: Iterable[Path | str] | None = None,
        input_files: Iterable[Path | str] | None = None,
        output_paths: Iterable[Path | str | Mapping[str, Any]] | None = None,
        snapshots: Iterable[Any] | None = None,
        warnings: Iterable[str] = (),
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Construye el manifest común más el contexto wavelet extendido."""

        plan_values = _plan_mapping(plan)
        experiment_id = str(plan_values.get("experiment_id", EXPERIMENT_ID)).strip()
        if not experiment_id:
            raise ProvenanceError("experiment_id no puede estar vacío")
        if experiment_id != EXPERIMENT_ID:
            raise ProvenanceError(
                f"La variante wavelet requiere experiment_id={EXPERIMENT_ID!r}"
            )

        start = _datetime_utc(started_at or self.started_at)
        finish = _datetime_utc(finished_at or self.finished_at or start)
        effective_run_id = str(run_id or make_run_id(started_at=start, product_id=PRODUCT_ID))
        config_paths = self._config_paths(config_files)
        output_descriptors, resolved_output_paths = _output_descriptors(
            self.output_paths if output_paths is None and self.output_paths is not None else output_paths,
            paths=self.paths,
        )
        snapshot_values = self.snapshots if snapshots is None else tuple(snapshots)
        snapshot_records, vintage_records, snapshot_paths, snapshot_warnings = (
            _snapshot_and_vintage_records(
                plan,
                bundle,
                snapshot_values,
                paths=self.paths,
            )
        )
        coverage = _coverage_records(bundle)
        predictions = _prediction_records(bundle)
        metrics = _metrics_records(bundle)
        decisions = _decision_records(bundle)
        input_paths = self._input_paths(
            input_files,
            config_paths=config_paths,
            snapshot_paths=snapshot_paths,
        )
        input_records = file_records(input_paths, root=self.paths.root)

        variant_context, plan_warnings = self._plan_context(plan)
        variant_context.update(
            {
                "snapshots": snapshot_records,
                "snapshot_manifests": snapshot_records,
                "source_vintages": vintage_records,
                "vintages": vintage_records,
                "coverage": coverage,
                "coverage_records": coverage,
                "coverage_summary": _coverage_summary(coverage),
                "predictions": predictions,
                "metrics": metrics,
                "promotion_gate": {"decisions": decisions},
                "output_paths": [str(item["path"]) for item in output_descriptors],
                "outputs": output_descriptors,
                "input_files": input_records,
                "evaluation_bundle_present": bundle is not None,
            }
        )
        variant_context["git_commit"], variant_context["git_dirty"], variant_context["git_status"] = git_state(
            self.paths.root
        )
        variant_context["code_revision"] = {
            "git_commit": variant_context["git_commit"],
            "git_dirty": variant_context["git_dirty"],
            "git_status": variant_context["git_status"],
        }
        variant_context["environment"] = environment_snapshot()
        variant_context["run_id"] = effective_run_id
        variant_context["started_at_utc"] = start.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        variant_context["finished_at_utc"] = finish.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )

        warning_values = list(RESEARCH_WARNINGS)
        warning_values.extend(self.warnings)
        warning_values.extend(str(item) for item in warnings)
        warning_values.extend(plan_warnings)
        warning_values.extend(snapshot_warnings)
        warning_values.extend(
            str(record["warning"])
            for record in predictions
            if record.get("warning")
        )
        if any(str(row.get("coverage_status", "complete")) != "complete" for row in coverage):
            warning_values.append("point_in_time_coverage_incomplete_or_partial")
        if any(not bool(row.get("causal_reconstruction", True)) for row in predictions):
            warning_values.append("causal_reconstruction_evidence_incomplete")
        if any(str(row.get("scoreability_status", "scoreable")) != "scoreable" for row in predictions):
            warning_values.append("not_all_origins_are_scoreable")
        if variant_context["git_commit"] == "unknown":
            warning_values.append("git_state_unavailable")
        if not input_records:
            warning_values.append("input_file_records_empty")
        if any(not path.is_file() for path in resolved_output_paths):
            warning_values.append("output_files_not_materialized")

        all_warnings = _dedupe(warning_values)
        variant_context["warnings"] = all_warnings
        variant_context["audit_warnings"] = all_warnings
        missing = _missing_fields(variant_context)
        materialization_errors = [
            f"output_file_missing:{self.paths.relative(path)}"
            for path in resolved_output_paths
            if not path.is_file()
        ]
        missing.extend(item for item in materialization_errors if item not in missing)
        missing = _dedupe(missing)
        variant_context["missing_required_fields"] = missing
        variant_context["provenance_complete"] = not missing

        if complete is None:
            complete_requested = bundle is not None and bool(output_descriptors)
        else:
            complete_requested = bool(complete)
        is_complete = complete_requested and not missing
        variant_context["complete"] = is_complete
        variant_context["completion_status"] = "complete" if is_complete else "incomplete"

        # Las advertencias no convierten la variante en producto. El estado
        # común de corrida solo refleja su ciclo de persistencia; el estado
        # research se conserva en todos los aliases del contexto.
        run_status = "success" if is_complete else "running"
        base_context = {
            "information_set": "vintage_backtest",
            "vintage_policy": "vintage_backtest",
            "origin_date": None,
            "snapshot_manifest": None,
            "product_status": RESEARCH_STATUS,
            "variant_status": RESEARCH_STATUS,
            "status": RESEARCH_STATUS,
            "runner": "forecast_longterm.wavelet_optimization",
            "imputation": False,
            "input_policy": "snapshot_only",
            "plan_hash": variant_context.get("plan_hash"),
            "wavelet_optimization": variant_context,
        }
        # Los aliases planos facilitan consumidores que todavía usan el
        # contexto legacy, pero la estructura canónica es wavelet_optimization.
        base_context.update(
            {
                key: variant_context[key]
                for key in (
                    "experiment_id",
                    "hypotheses",
                    "candidate_grid",
                    "dwt",
                    "target_definition",
                    "horizons",
                    "splits",
                    "benchmark",
                    "label_maturity_rule",
                    "minimum_mature_training",
                    "data_cutoff",
                    "snapshot_manifests",
                    "source_vintages",
                    "coverage_summary",
                    "output_paths",
                    "seed",
                    "warnings",
                )
            }
        )

        manifest = build_run_manifest(
            product_id=PRODUCT_ID,
            config_files=config_paths,
            input_files=input_paths,
            output_files=resolved_output_paths,
            paths=self.paths,
            status=run_status,
            run_id=effective_run_id,
            started_at=start,
            finished_at=finish,
            error=error,
            warnings=all_warnings,
            run_context=base_context,
            experiment_id=experiment_id,
        )
        # build_run_manifest already captures environment/Git with the legacy
        # primitives; retain its exact values in the wavelet context as well.
        variant_context["git_commit"] = manifest["git_commit"]
        variant_context["git_dirty"] = manifest["git_dirty"]
        variant_context["git_status"] = manifest["git_status"]
        variant_context["environment"] = manifest["environment"]
        variant_context["code_revision"] = {
            "git_commit": manifest["git_commit"],
            "git_dirty": manifest["git_dirty"],
            "git_status": manifest["git_status"],
            "source_tree_sha256": manifest["source_tree_sha256"],
        }
        # Recalculate only the status-derived context values; the original
        # missing list remains the authoritative audit result.
        manifest["warnings"] = all_warnings
        manifest["run_context"] = base_context
        manifest["run_context"]["wavelet_optimization"] = variant_context
        return manifest

    def validate_complete_manifest(self, manifest: Mapping[str, Any]) -> None:
        """Exige provenance y outputs completos antes de persistir ``success``."""

        run_context = manifest.get("run_context")
        variant = _value(run_context, "wavelet_optimization", default=None)
        if not isinstance(variant, Mapping):
            raise MissingProvenanceError("Falta run_context.wavelet_optimization")
        missing = _missing_fields(variant)
        if variant.get("missing_required_fields"):
            missing.extend(str(item) for item in variant["missing_required_fields"])
        missing = _dedupe(missing)
        if missing:
            raise MissingProvenanceError(
                "No se puede marcar la corrida como completa; falta provenance: "
                + ", ".join(missing)
            )
        if str(manifest.get("product_id")) != PRODUCT_ID:
            raise ProvenanceError(f"product_id debe ser {PRODUCT_ID!r}")
        if str(variant.get("product_id")) != PRODUCT_ID:
            raise ProvenanceError(f"product_id de la variante debe ser {PRODUCT_ID!r}")
        if str(variant.get("status")) != RESEARCH_STATUS:
            raise ProvenanceError("status de la variante debe conservarse como 'research'")
        output_errors = _output_reconciliation_errors(manifest, paths=self.paths)
        if output_errors:
            raise OutputReconciliationError(
                "Los outputs no concilian o no están materializados: "
                + ", ".join(output_errors)
            )

    def write_manifest(
        self,
        manifest: Mapping[str, Any],
        *,
        complete: bool | None = None,
    ) -> Path:
        """Escribe el manifest en su ruta canónica y conserva ``research``."""

        document = dict(manifest)
        run_context = dict(document.get("run_context") or {})
        variant = dict(run_context.get("wavelet_optimization") or {})
        variant["status"] = RESEARCH_STATUS
        variant["variant_status"] = RESEARCH_STATUS
        variant["product_id"] = PRODUCT_ID
        run_context["wavelet_optimization"] = variant
        run_context["product_status"] = RESEARCH_STATUS
        run_context["variant_status"] = RESEARCH_STATUS
        run_context["status"] = RESEARCH_STATUS
        document["run_context"] = run_context
        document["product_id"] = PRODUCT_ID
        should_complete = (
            bool(variant.get("complete", False))
            if complete is None
            else bool(complete)
        )
        if should_complete:
            self.validate_complete_manifest(document)
            variant["complete"] = True
            variant["completion_status"] = "complete"
            document["status"] = "success"
        else:
            variant["complete"] = False
            variant["completion_status"] = "incomplete"
            if document.get("status") not in {"running", "failed", "success"}:
                document["status"] = "running"
        document["run_context"]["wavelet_optimization"] = variant
        return write_run_manifest(document, paths=self.paths)

    def record(
        self,
        plan: Any,
        bundle: Any = None,
        run_id: str | None = None,
        *,
        complete: bool = True,
        **kwargs: Any,
    ) -> Path:
        """Construye y persiste una corrida, con validación estricta opcional."""

        manifest = self.build_manifest(
            plan,
            bundle,
            run_id,
            complete=complete,
            **kwargs,
        )
        return self.write_manifest(manifest, complete=complete)

    # Nombres explícitos para callers que prefieren la terminología del diseño.
    build_extended_manifest = build_manifest
    write_extended_manifest = write_manifest


__all__ = [
    "DEFAULT_CONFIG_PATHS",
    "DEFAULT_OUTPUT_PATHS",
    "MissingProvenanceError",
    "OUTPUT_NAMESPACE",
    "OutputReconciliationError",
    "ProvenanceError",
    "ProvenanceRecorder",
    "RESEARCH_WARNINGS",
]
