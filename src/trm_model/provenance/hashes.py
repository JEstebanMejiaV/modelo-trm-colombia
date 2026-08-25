"""Funciones de hash y registros de archivos para manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    display = resolved.relative_to(root.resolve()).as_posix() if root else str(resolved)
    return {"path": display, "sha256": sha256_file(resolved), "bytes": resolved.stat().st_size}


def file_records(paths: Iterable[Path], *, root: Path | None = None) -> list[dict[str, Any]]:
    return [file_record(path, root=root) for path in sorted(paths, key=lambda item: str(item))]


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def file_records_hash(paths: Iterable[Path], *, root: Path | None = None) -> str:
    """Calcula una huella estable de rutas, tamaños y contenidos de archivos."""
    return canonical_json_hash(file_records(paths, root=root))
