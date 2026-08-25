"""Validador local de los contratos JSON del repositorio.

Se implementa un subconjunto intencional y suficiente del vocabulario usado por
los schemas versionados, sin añadir una dependencia obligatoria de runtime.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..paths import ProjectPaths, project_paths


class ContractError(ValueError):
    """Error de contrato con ubicación del campo inválido."""


def _type_matches(value: Any, expected: str) -> bool:
    checks = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
    }
    if expected not in checks:
        raise ContractError(f"Tipo de schema no soportado: {expected}")
    return checks[expected](value)


def _path_text(path: tuple[str, ...]) -> str:
    return "$" if not path else "$." + ".".join(path)


def _validate(value: Any, schema: dict[str, Any], path: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_matches(value, str(item)) for item in allowed):
            return [f"{_path_text(path)}: se esperaba tipo {allowed}, llegó {type(value).__name__}"]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{_path_text(path)}: valor fuera de enum {schema['enum']}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            errors.append(f"{_path_text(path)}: longitud menor que minLength")
        pattern = schema.get("pattern")
        if pattern and re.fullmatch(pattern, value) is None:
            errors.append(f"{_path_text(path)}: no cumple pattern {pattern!r}")
    if isinstance(value, (int, float)) and "minimum" in schema:
        if value < schema["minimum"]:
            errors.append(f"{_path_text(path)}: valor menor que minimum")

    if isinstance(value, dict):
        required = set(schema.get("required", []))
        missing = sorted(required - value.keys())
        errors.extend(f"{_path_text(path)}: falta campo requerido {name!r}" for name in missing)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            errors.extend(f"{_path_text(path)}: campo no permitido {name!r}" for name in unknown)
        for name, child in value.items():
            if name in properties:
                errors.extend(_validate(child, properties[name], path + (str(name),)))
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            errors.append(f"{_path_text(path)}: menos elementos que minItems")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                errors.extend(_validate(item, item_schema, path + (str(index),)))
    return errors


def validate_document(document: Any, schema_path: Path) -> None:
    """Valida un documento y lanza ``ContractError`` con todos los hallazgos."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = _validate(document, schema, ())
    if errors:
        raise ContractError(f"Contrato inválido ({schema_path}):\n- " + "\n- ".join(errors))


def load_json_and_validate(path: Path, schema_path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_document(value, schema_path)
    return value


def validate_source_registry(document: Any, *, paths: ProjectPaths | None = None) -> None:
    project = paths or project_paths()
    validate_document(document, project.schema("source_registry.json"))


def validate_factor_spec(document: Any, *, paths: ProjectPaths | None = None) -> None:
    project = paths or project_paths()
    validate_document(document, project.schema("factor_spec.json"))


def validate_product_manifest(document: Any, *, paths: ProjectPaths | None = None) -> None:
    project = paths or project_paths()
    validate_document(document, project.schema("product_manifest.json"))


def validate_run_manifest(document: Any, *, paths: ProjectPaths | None = None) -> None:
    project = paths or project_paths()
    validate_document(document, project.schema("run_manifest.json"))
    from ..provenance.hashes import file_records_hash
    from ..provenance.manifest import contract_files

    expected_hash = file_records_hash(contract_files(project.root), root=project.root)
    if document["contract_tree_sha256"] != expected_hash:
        raise ContractError(
            "El contract_tree_sha256 del manifest no concilia con los contratos actuales: "
            f"manifest={document['contract_tree_sha256']}, esperado={expected_hash}."
        )
