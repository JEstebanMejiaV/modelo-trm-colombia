"""Rutas canónicas del proyecto.

Las rutas se resuelven desde la raíz del repositorio y no desde el directorio
actual del proceso. Esto permite usar la CLI instalada y conservar los entry
points legacy ejecutados desde ``src``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_project_root(start: Path | None = None) -> Path:
    """Encuentra la raíz desde el checkout, el cwd o ``TRM_MODEL_ROOT``."""
    configured = Path(os.environ["TRM_MODEL_ROOT"]).resolve() if "TRM_MODEL_ROOT" in os.environ else None
    origins = []
    if start is not None:
        origins.append(start.resolve())
    if configured is not None:
        origins.append(configured)
    origins.extend([Path.cwd().resolve(), Path(__file__).resolve()])
    candidates = []
    for origin in origins:
        if origin.is_file():
            candidates.extend((origin.parent, *origin.parents))
        else:
            candidates.extend((origin, *origin.parents))
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ProjectPaths:
    """Mapa de directorios y archivos de contrato del repositorio."""

    root: Path

    @classmethod
    def from_root(cls, root: Path | None = None) -> "ProjectPaths":
        resolved = (root or find_project_root()).resolve()
        return cls(resolved)

    @property
    def src(self) -> Path:
        return self.root / "src"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def catalog(self) -> Path:
        return self.data / "catalog"

    @property
    def vintages(self) -> Path:
        return self.data / "vintages"

    @property
    def configs(self) -> Path:
        return self.root / "configs"

    @property
    def schemas(self) -> Path:
        return self.root / "schemas"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def runs(self) -> Path:
        return self.artifacts / "runs"

    @property
    def deliverables(self) -> Path:
        return self.root / "deliverables"

    def resolve(self, relative: str | Path) -> Path:
        """Resuelve una ruta relativa al repositorio; acepta rutas absolutas."""
        path = Path(relative)
        return path if path.is_absolute() else self.root / path

    def relative(self, path: Path) -> str:
        """Devuelve una ruta portable relativa a la raíz."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def product_config(self, product_id: str) -> Path:
        return self.configs / "products" / f"{product_id}.toml"

    def product_manifest(self, product_id: str) -> Path:
        base = self.root / "research" / "manifests" if product_id == "long_horizon_research" else self.root / "pipelines" / "manifests"
        return base / f"{product_id}.json"

    def schema(self, name: str) -> Path:
        return self.schemas / name

    def source_registry(self) -> Path:
        return self.catalog / "sources.json"

    def run_directory(self, run_id: str) -> Path:
        return self.runs / run_id


def project_paths(root: Path | None = None) -> ProjectPaths:
    """Atajo para construir el mapa de rutas."""
    return ProjectPaths.from_root(root)
