"""Runner común para productos y provenance por corrida.

El runner no conoce econometría ni modelos concretos. Valida el contrato del
producto, registra inputs/configuración, ejecuta un callable legacy o target y
escribe un manifest ``running`` seguido de ``success`` o ``failed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from ..data.registry import load_source_registry
from ..paths import ProjectPaths, project_paths
from ..specifications.products import (
    load_product_manifest,
    validate_product_output_ownership,
)
from ..validation.contracts import validate_product_manifest
from .hashes import sha256_file
from .manifest import (
    build_run_manifest,
    make_run_id,
    write_run_manifest,
)
from ..output_contract import ownership_records, validate_run_output_ownership


@dataclass(frozen=True)
class ProductRun:
    """Contrato mínimo para envolver un entry point existente."""

    product_id: str
    runner: Callable[[], None]
    output_files: tuple[str, ...] | None = None
    input_files: tuple[Path, ...] | None = None
    config_files: tuple[Path, ...] | None = None
    run_context: Mapping[str, object] | None = None
    warnings: tuple[str, ...] = ()


def declared_product_outputs(
    product_id: str,
    *,
    paths: ProjectPaths | None = None,
) -> tuple[str, ...]:
    """Valida y devuelve los paths declarados por un manifest de producto."""
    project = paths or project_paths()
    manifest = load_product_manifest(product_id, paths=project)
    validate_product_output_ownership(product_id, manifest, paths=project)
    validate_product_manifest(manifest, paths=project)
    return tuple(str(output["path"]) for output in manifest.get("outputs", []))


def run_product(spec: ProductRun, *, paths: ProjectPaths | None = None) -> Path:
    """Ejecuta un producto y escribe su manifest de provenance.

    ``output_files`` puede ser un subconjunto del manifest cuando un entry point
    legacy genera solo una parte del catálogo del producto. Nunca puede contener
    paths fuera del ownership declarado.
    """
    project = paths or project_paths()
    product_manifest = load_product_manifest(spec.product_id, paths=project)
    validate_product_output_ownership(spec.product_id, product_manifest, paths=project)
    validate_product_manifest(product_manifest, paths=project)

    declared = tuple(sorted(declared_product_outputs(spec.product_id, paths=project)))
    selected_output_names = declared if spec.output_files is None else tuple(spec.output_files)
    unexpected = sorted(set(selected_output_names) - set(declared))
    if unexpected:
        raise ValueError(
            f"El runner {spec.product_id!r} intenta escribir outputs fuera del contrato: "
            f"{unexpected}"
        )
    output_paths = tuple(project.resolve(path) for path in selected_output_names)
    discover_outputs = spec.output_files is None

    registry = load_source_registry(paths=project)
    if spec.input_files is None:
        input_paths = tuple(registry.raw_paths(root=project.root))
    else:
        input_paths = tuple(path.resolve() for path in spec.input_files)
    missing_inputs = [path for path in input_paths if not path.is_file()]
    if missing_inputs:
        missing = ", ".join(project.relative(path) for path in missing_inputs)
        raise FileNotFoundError(f"Faltan inputs del producto {spec.product_id}: {missing}")

    config_paths = (
        tuple(spec.config_files)
        if spec.config_files is not None
        else (
            project.product_config(spec.product_id),
            project.product_manifest(spec.product_id),
        )
    )
    context = _normalize_context(spec, product_manifest, project)
    started = datetime.now(timezone.utc)
    run_id = make_run_id(started_at=started, product_id=spec.product_id)
    ownership = {spec.product_id: [project.relative(path) for path in output_paths]}

    before = {path: _file_state(path) for path in output_paths}
    running = build_run_manifest(
        product_id=spec.product_id,
        config_files=config_paths,
        input_files=input_paths,
        output_files=[],
        paths=project,
        status="running",
        run_id=run_id,
        started_at=started,
        finished_at=started,
        warnings=spec.warnings,
        run_context=context,
    )
    running["products"] = ownership_records({spec.product_id: []})
    write_run_manifest(running, paths=project)

    try:
        spec.runner()
        if discover_outputs:
            output_paths = tuple(
                path
                for path in output_paths
                if _file_state(path) is not None and _file_state(path) != before[path]
            )
            if not output_paths:
                raise RuntimeError(
                    f"El runner {spec.product_id!r} no modificó ningún output declarado."
                )
        else:
            _assert_outputs_written(output_paths, before, project=project)
        ownership = {spec.product_id: [project.relative(path) for path in output_paths]}
        completed = build_run_manifest(
            product_id=spec.product_id,
            config_files=config_paths,
            input_files=input_paths,
            output_files=output_paths,
            paths=project,
            status="success",
            run_id=run_id,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            warnings=spec.warnings,
            run_context=context,
        )
        completed["products"] = ownership_records(ownership)
        validate_run_output_ownership(
            completed,
            expected_product_ids={spec.product_id},
        )
        return write_run_manifest(completed, paths=project)
    except Exception as error:
        failed = build_run_manifest(
            product_id=spec.product_id,
            config_files=config_paths,
            input_files=input_paths,
            output_files=[],
            paths=project,
            status="failed",
            run_id=run_id,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(error).__name__}: {error}",
            warnings=spec.warnings,
            run_context=context,
        )
        failed["products"] = ownership_records({spec.product_id: []})
        write_run_manifest(failed, paths=project)
        raise


def _normalize_context(
    spec: ProductRun,
    product_manifest: Mapping[str, object],
    project: ProjectPaths,
) -> dict[str, object]:
    context = {
        "information_set": product_manifest.get("information_set", "unspecified"),
        "vintage_policy": product_manifest.get("vintage_policy", "unspecified"),
        "origin_date": None,
        "snapshot_manifest": None,
        "product_status": product_manifest.get("status", "unknown"),
        "runner": getattr(spec.runner, "__qualname__", repr(spec.runner)),
        "imputation": False,
        "input_policy": "latest_available",
    }
    context.update(dict(spec.run_context or {}))
    if context.get("imputation") is True:
        raise ValueError(
            "La provenance no permite declarar imputación artificial en un runner de producto."
        )
    if context.get("vintage_policy") == "vintage_backtest":
        origin_date = context.get("origin_date")
        snapshot_manifest = context.get("snapshot_manifest")
        if not origin_date or not snapshot_manifest:
            raise ValueError(
                "Un vintage_backtest requiere origin_date y snapshot_manifest explícitos."
            )
        from ..data.vintages import validate_vintage_for_backtest, vintage_manifest_path

        expected_manifest = project.relative(vintage_manifest_path(str(origin_date), paths=project))
        if str(snapshot_manifest) not in {expected_manifest, str(vintage_manifest_path(str(origin_date), paths=project))}:
            raise ValueError(
                "snapshot_manifest no coincide con la carpeta del origin_date: "
                f"esperado={expected_manifest}, recibido={snapshot_manifest}"
            )
        required_inputs = context.get("required_raw_paths", ())
        if not isinstance(required_inputs, (list, tuple, set)):
            raise ValueError("required_raw_paths debe ser una colección de rutas relativas.")
        report = validate_vintage_for_backtest(
            str(origin_date),
            required_raw_paths=[str(path) for path in required_inputs],
            paths=project,
        )
        context["snapshot_validated"] = True
        context["snapshot_files_checked"] = report.files_checked
        context["input_policy"] = "snapshot_only"
    return context


def _file_state(path: Path) -> tuple[str, int, int] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return sha256_file(path), stat.st_size, stat.st_mtime_ns


def _assert_outputs_written(
    output_paths: Iterable[Path],
    before: Mapping[Path, tuple[str, int, int] | None],
    *,
    project: ProjectPaths,
) -> None:
    paths = tuple(output_paths)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        names = ", ".join(project.relative(path) for path in missing)
        raise FileNotFoundError(f"El runner no produjo outputs declarados: {names}")
    unchanged = [
        path
        for path in paths
        if _file_state(path) == before.get(path)
    ]
    if unchanged:
        names = ", ".join(project.relative(path) for path in unchanged)
        raise RuntimeError(
            "El runner terminó sin actualizar outputs declarados; "
            f"se rechazan artifacts posiblemente stale: {names}"
        )
