"""Construcción y escritura de manifests por corrida."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..paths import ProjectPaths, project_paths
from .environment import environment_snapshot
from .hashes import canonical_json_hash, file_records, file_records_hash


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def git_state(root: Path) -> tuple[str, bool, list[str]]:
    try:
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True, ["git state unavailable"]
    status = [line for line in status_result.stdout.splitlines() if line]
    return commit_result.stdout.strip(), bool(status), status


def git_commit(root: Path) -> str:
    return git_state(root)[0]


def source_code_files(root: Path) -> list[Path]:
    code_roots = (root / "src", root / "pipelines", root / "research")
    return sorted(
        path
        for code_root in code_roots
        if code_root.is_dir()
        for path in code_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def contract_files(root: Path) -> list[Path]:
    """Devuelve todos los contratos que deben quedar fijados en provenance."""
    candidates: list[Path] = []
    for path in (
        root / "pyproject.toml",
        root / "requirements.lock",
        root / "requirements-optional.lock",
    ):
        if path.is_file():
            candidates.append(path)
    for directory in (root / "configs", root / "schemas"):
        if directory.is_dir():
            candidates.extend(
                path
                for pattern in ("*.toml", "*.json")
                for path in directory.rglob(pattern)
                if path.is_file()
            )
    explicit_files = (
        root / "data" / "catalog" / "sources.json",
        root / "results" / "output_catalog.json",
    )
    candidates.extend(path for path in explicit_files if path.is_file())
    for directory in (
        root / "pipelines" / "manifests",
        root / "research" / "manifests",
    ):
        if directory.is_dir():
            candidates.extend(path for path in directory.rglob("*.json") if path.is_file())

    vintages = root / "data" / "vintages"
    if vintages.is_dir():
        candidates.extend(
            path
            for path in vintages.rglob("*.json")
            if path.is_file() and (path.name == "manifest.json" or path.name == "version_history.json")
        )

    return sorted({path.resolve() for path in candidates}, key=str)


def make_run_id(*, started_at: datetime | None = None, product_id: str = "run") -> str:
    started = started_at or utc_now()
    timestamp = started.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = canonical_json_hash({"product_id": product_id, "started_at": iso_utc(started)})[:12]
    return f"{timestamp}-{suffix}"


def build_run_manifest(
    *,
    product_id: str,
    config_files: Iterable[Path],
    input_files: Iterable[Path],
    output_files: Iterable[Path],
    paths: ProjectPaths | None = None,
    status: str = "success",
    run_id: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    error: str | None = None,
    warnings: Iterable[str] = (),
    run_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    project = paths or project_paths()
    selected_config_paths = {path.resolve() for path in config_files}
    contracts = contract_files(project.root)
    record_paths = sorted(selected_config_paths.union(contracts), key=str)
    start = started_at or utc_now()
    finish = finished_at or utc_now()
    commit, dirty, status_lines = git_state(project.root)
    manifest_warnings = list(warnings)
    if commit == "unknown":
        manifest_warnings.append(
            "Git state unavailable; manifest marked dirty and commit set to 'unknown'."
        )
    code_hash = file_records_hash(source_code_files(project.root), root=project.root)
    return {
        "schema_version": 1,
        "run_id": run_id or make_run_id(started_at=start, product_id=product_id),
        "product_id": product_id,
        "status": status,
        "started_at_utc": iso_utc(start),
        "finished_at_utc": iso_utc(finish),
        "git_commit": commit,
        "git_dirty": dirty,
        "git_status": status_lines,
        "config_files": [project.relative(path) for path in record_paths],
        "config_records": file_records(record_paths, root=project.root),
        "contract_tree_sha256": file_records_hash(contracts, root=project.root),
        "source_tree_sha256": code_hash,
        "input_files": file_records(
            (path for path in input_files if path.is_file()), root=project.root
        ),
        "output_files": file_records(
            (path for path in output_files if path.is_file()), root=project.root
        ),
        "environment": environment_snapshot(),
        "run_context": dict(run_context or {}),
        "error": error,
        "warnings": manifest_warnings,
    }


def write_run_manifest(
    manifest: dict[str, Any], *, paths: ProjectPaths | None = None
) -> Path:
    from ..validation.contracts import validate_run_manifest

    project = paths or project_paths()
    validate_run_manifest(manifest, paths=project)
    run_directory = project.run_directory(str(manifest["run_id"]))
    run_directory.mkdir(parents=True, exist_ok=True)
    destination = run_directory / "manifest.json"
    destination.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return destination
