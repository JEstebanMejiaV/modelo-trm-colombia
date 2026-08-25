"""Registro local, versionado y consultable de experimentos.

Un ``experiment_id`` identifica una especificación, hipótesis y decisión de
modelo. Un ``run_id`` identifica una ejecución concreta. El registro vive en
``experiments/registry.json`` para que los cambios de especificación queden en
Git; las corridas observadas se descubren desde ``artifacts/runs`` cuando están
disponibles localmente.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..paths import ProjectPaths, project_paths
from ..validation.contracts import validate_document


class ExperimentError(ValueError):
    """Error de identidad, contrato o relación entre experimentos."""


MONTHLY_EXPERIMENT_IDS = (
    "monthly_explanation.controles_externos.v1",
    "monthly_explanation.marco_macro_integral.v1",
    "monthly_forecast.full.v1",
    "robustness.bei_ecm.v1",
)
DAILY_DIRECTION_EXPERIMENT_ID = "daily_direction.model_comparison.v1"
DAILY_VOLATILITY_EXPERIMENT_ID = "daily_volatility.garch_family.v1"
RESEARCH_EXPERIMENT_PREFIX = "long_horizon_research."


def experiment_registry_path(*, paths: ProjectPaths | None = None) -> Path:
    project = paths or project_paths()
    return project.root / "experiments" / "registry.json"


def experiment_record_schema_path(*, paths: ProjectPaths | None = None) -> Path:
    project = paths or project_paths()
    return project.schema("experiment_record.json")


def experiment_registry_schema_path(*, paths: ProjectPaths | None = None) -> Path:
    project = paths or project_paths()
    return project.schema("experiment_registry.json")


def validate_experiment_record(
    record: Mapping[str, Any], *, paths: ProjectPaths | None = None
) -> None:
    project = paths or project_paths()
    validate_document(dict(record), experiment_record_schema_path(paths=project))


def _validate_registry_invariants(document: Mapping[str, Any]) -> None:
    records = document.get("experiments", [])
    ids = [str(record["experiment_id"]) for record in records]
    if len(ids) != len(set(ids)):
        duplicates = sorted({experiment_id for experiment_id in ids if ids.count(experiment_id) > 1})
        raise ExperimentError(f"El registro repite experiment_id: {duplicates}")
    known = set(ids)
    for record in records:
        parent = record.get("parent_experiment_id")
        if parent is not None and parent not in known:
            raise ExperimentError(
                f"El experimento {record['experiment_id']!r} referencia un padre inexistente: {parent!r}"
            )


def load_experiment_registry(*, paths: ProjectPaths | None = None) -> dict[str, Any]:
    project = paths or project_paths()
    registry_path = experiment_registry_path(paths=project)
    if not registry_path.is_file():
        raise ExperimentError(f"No existe el registro de experimentos: {project.relative(registry_path)}")
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    validate_document(document, experiment_registry_schema_path(paths=project))
    for record in document["experiments"]:
        validate_experiment_record(record, paths=project)
    _validate_registry_invariants(document)
    return document


def validate_experiment_registry(*, paths: ProjectPaths | None = None) -> dict[str, Any]:
    """Valida y devuelve el registro completo."""
    return load_experiment_registry(paths=paths)


def list_experiments(
    *,
    product_id: str | None = None,
    status: str | None = None,
    paths: ProjectPaths | None = None,
) -> list[dict[str, Any]]:
    records = load_experiment_registry(paths=paths)["experiments"]
    selected = [
        record
        for record in records
        if (product_id is None or record["product_id"] == product_id)
        and (status is None or record["status"] == status)
    ]
    return [dict(record) for record in selected]


def _ids_from_values(
    *, experiment_id: str | None = None, experiment_ids: Iterable[str] = ()
) -> list[str]:
    values: list[str] = []
    if experiment_id:
        values.append(str(experiment_id))
    values.extend(str(value) for value in experiment_ids if value)
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def experiment_ids_from_manifest(manifest: Mapping[str, Any]) -> list[str]:
    return _ids_from_values(
        experiment_id=manifest.get("experiment_id"),
        experiment_ids=manifest.get("experiment_ids", ()),
    )


def validate_experiment_references(
    experiment_ids: Iterable[str], *, paths: ProjectPaths | None = None
) -> None:
    ids = _ids_from_values(experiment_ids=experiment_ids)
    if not ids:
        return
    registry = load_experiment_registry(paths=paths)
    known = {str(record["experiment_id"]) for record in registry["experiments"]}
    missing = sorted(set(ids) - known)
    if missing:
        raise ExperimentError(
            "La corrida referencia experimentos no registrados: "
            + ", ".join(missing)
        )


def research_experiment_id(module_name: str) -> str:
    return f"{RESEARCH_EXPERIMENT_PREFIX}{module_name}.v1"


def observed_runs_by_experiment(
    *, paths: ProjectPaths | None = None
) -> dict[str, list[dict[str, Any]]]:
    project = paths or project_paths()
    observed: dict[str, list[dict[str, Any]]] = {}
    if not project.runs.is_dir():
        return observed
    for manifest_path in sorted(project.runs.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_ids = experiment_ids_from_manifest(manifest)
        run_record = {
            "run_id": manifest.get("run_id", manifest_path.parent.name),
            "product_id": manifest.get("product_id"),
            "status": manifest.get("status"),
            "path": project.relative(manifest_path),
        }
        for experiment_id in run_ids:
            observed.setdefault(experiment_id, []).append(run_record)
    return observed


def experiment_details(
    experiment_id: str, *, paths: ProjectPaths | None = None
) -> dict[str, Any]:
    project = paths or project_paths()
    records = list_experiments(paths=project)
    record = next(
        (candidate for candidate in records if candidate["experiment_id"] == experiment_id),
        None,
    )
    if record is None:
        raise ExperimentError(f"Experiment no encontrado: {experiment_id}")
    record["observed_runs"] = observed_runs_by_experiment(paths=project).get(experiment_id, [])
    return record


def register_experiment_file(
    record_path: str | Path, *, paths: ProjectPaths | None = None
) -> dict[str, Any]:
    """Agrega un registro nuevo; los IDs existentes nunca se sobrescriben."""
    project = paths or project_paths()
    source = project.resolve(record_path)
    record = json.loads(source.read_text(encoding="utf-8"))
    validate_experiment_record(record, paths=project)
    document = load_experiment_registry(paths=project)
    existing_ids = {item["experiment_id"] for item in document["experiments"]}
    experiment_id = record["experiment_id"]
    if experiment_id in existing_ids:
        raise ExperimentError(
            f"experiment_id ya existe: {experiment_id}. Cree una nueva versión o variante."
        )
    parent = record.get("parent_experiment_id")
    if parent is not None and parent not in existing_ids:
        raise ExperimentError(f"parent_experiment_id no existe: {parent}")
    document["experiments"].append(record)
    _validate_registry_invariants(document)
    destination = experiment_registry_path(paths=project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=destination.parent, suffix=".tmp", delete=False
    ) as temporary:
        temporary.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, destination)
    return dict(record)
