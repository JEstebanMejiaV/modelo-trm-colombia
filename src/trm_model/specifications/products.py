"""Carga de configuraciones de producto en TOML y manifests JSON."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from ..paths import ProjectPaths, project_paths
from ..types import ProductSpec


def load_product(product_id: str, *, paths: ProjectPaths | None = None) -> ProductSpec:
    project = paths or project_paths()
    path = project.product_config(product_id)
    if not path.is_file():
        raise FileNotFoundError(f"No existe configuración del producto: {path}")
    value = tomllib.loads(path.read_text(encoding="utf-8"))
    return ProductSpec.from_mapping(value)


def load_products(*, paths: ProjectPaths | None = None) -> dict[str, ProductSpec]:
    project = paths or project_paths()
    product_dir = project.configs / "products"
    products: dict[str, ProductSpec] = {}
    for path in sorted(product_dir.glob("*.toml")):
        value = tomllib.loads(path.read_text(encoding="utf-8"))
        spec = ProductSpec.from_mapping(value)
        if spec.product_id in products:
            raise ValueError(f"Producto duplicado: {spec.product_id}")
        products[spec.product_id] = spec
    return products


def load_product_manifest(
    product_id: str, *, paths: ProjectPaths | None = None
) -> dict[str, Any]:
    project = paths or project_paths()
    path = project.product_manifest(product_id)
    if not path.is_file():
        raise FileNotFoundError(f"No existe manifest del producto: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"El manifest del producto debe ser un objeto: {path}")
    return value


def load_output_catalog(*, paths: ProjectPaths | None = None) -> dict[str, Any]:
    project = paths or project_paths()
    path = project.results / "output_catalog.json"
    if not path.is_file():
        raise FileNotFoundError(f"No existe el catálogo de outputs: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"El catálogo de outputs debe ser un objeto: {path}")
    return value


def validate_product_output_ownership(
    product_id: str,
    manifest: dict[str, Any],
    *,
    paths: ProjectPaths | None = None,
) -> None:
    """Comprueba que los outputs declarados pertenezcan al grupo del producto."""
    catalog = load_output_catalog(paths=paths)
    groups = [group for group in catalog.get("groups", []) if group.get("product_id") == product_id]
    if len(groups) != 1:
        raise ValueError(f"El catálogo debe tener un único grupo para {product_id!r}.")
    group = groups[0]
    if manifest.get("status") != group.get("status"):
        raise ValueError(
            f"El estado de {product_id!r} no concilia: manifest={manifest.get('status')!r}, "
            f"catálogo={group.get('status')!r}."
        )
    catalog_paths = set(group.get("paths", []))
    declared_outputs = manifest.get("outputs", [])
    declared_paths = [output.get("path") for output in declared_outputs]
    if len(declared_paths) != len(set(declared_paths)):
        raise ValueError(f"El manifest de {product_id!r} repite paths de outputs.")
    missing = sorted(catalog_paths - set(declared_paths))
    extra = sorted(set(declared_paths) - catalog_paths)
    if missing or extra:
        raise ValueError(
            f"El ownership de {product_id!r} no coincide con el catálogo: "
            f"missing={missing}, extra={extra}"
        )
    expected_status = group.get("kind")
    wrong_status = sorted(
        output.get("path")
        for output in declared_outputs
        if output.get("status") != expected_status
    )
    if wrong_status:
        raise ValueError(
            f"Outputs con estado incompatible para {product_id!r}: {wrong_status}"
        )
