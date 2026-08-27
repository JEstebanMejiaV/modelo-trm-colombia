"""QA estructural para contratos, ownership de outputs y residuos inseguros."""

from __future__ import annotations

import json
from pathlib import Path

from trm_model.data.registry import load_source_registry
from trm_model.paths import project_paths
from trm_model.specifications.products import (
    load_product_manifest,
    load_products,
    validate_product_output_ownership,
)
from trm_model.validation.contracts import validate_product_manifest
from trm_model.validation.leakage import validate_forecast_specs

FORBIDDEN_LITERALS = (
    "dd22ac6406a29199a86edafc2f267524",
    "sys.path.insert",
    "sys.path.append",
)
TEXT_SUFFIXES = {".py", ".toml", ".json", ".md", ".yml", ".yaml", ".txt"}
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".egg-info"}
DEFERRED_OUTPUT_PREFIXES = ("results/pronostico/wavelet_optimization/",)


def _scan_forbidden_text(root: Path) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if path.resolve() == Path(__file__).resolve():
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for literal in FORBIDDEN_LITERALS:
            if literal in text:
                findings.append(f"{root.joinpath(path.relative_to(root))}: {literal}")
    return findings


def _catalog_paths(root: Path) -> set[str]:
    catalog = json.loads((root / "results" / "output_catalog.json").read_text(encoding="utf-8"))
    return {
        path
        for group in catalog["groups"]
        for path in group["paths"]
    }


def _actual_result_paths(paths) -> set[str]:
    actual = {
        paths.relative(path)
        for folder in (paths.results / "explicacion", paths.results / "pronostico", paths.results / "robustez")
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in {".csv", ".json"}
    }
    actual.add(paths.relative(paths.results / "metadata.json"))
    return actual


def main() -> int:
    paths = project_paths()
    findings = _scan_forbidden_text(paths.root)
    if findings:
        raise AssertionError("Residuos prohibidos encontrados:\n- " + "\n- ".join(findings))

    registry = load_source_registry(paths=paths)
    missing = registry.missing_raw_files(root=paths.root)
    missing_model_inputs = registry.missing_monthly_model_inputs()
    if missing or missing_model_inputs:
        missing_text = ", ".join(paths.relative(path) for path in missing)
        if missing_model_inputs:
            missing_text = ", ".join(filter(None, [missing_text, *missing_model_inputs]))
        raise FileNotFoundError(f"Fuentes activas o inputs mensuales faltantes: {missing_text}")

    products = load_products(paths=paths)
    for product_id in products:
        manifest = load_product_manifest(product_id, paths=paths)
        validate_product_output_ownership(product_id, manifest, paths=paths)
        validate_product_manifest(manifest, paths=paths)

    from model.config import FORECAST_FACTOR_SPECS_3, FORECAST_FACTOR_SPECS_4

    validate_forecast_specs(FORECAST_FACTOR_SPECS_3)
    validate_forecast_specs(FORECAST_FACTOR_SPECS_4)

    catalog_paths = _catalog_paths(paths.root)
    actual_paths = _actual_result_paths(paths)
    required_catalog_paths = {
        path for path in catalog_paths if not path.startswith(DEFERRED_OUTPUT_PREFIXES)
    }
    actual_required_paths = {
        path for path in actual_paths if not path.startswith(DEFERRED_OUTPUT_PREFIXES)
    }
    # La investigación wavelet publica sus cuatro outputs solo cuando se
    # ejecuta explícitamente. Si alguno ya está materializado, sigue sujeto al
    # catálogo; la validación mensual no debe exigir que exista de antemano.
    missing = sorted(actual_paths - catalog_paths)
    extra = sorted(required_catalog_paths - actual_required_paths)
    if missing or extra:
        raise AssertionError(f"Ownership de outputs inconsistente; missing={missing}, extra={extra}")

    print(
        json.dumps(
            {
                "status": "ok",
                "sources_active": len(registry.active_sources),
                "products": sorted(products),
                "catalogued_outputs": len(actual_paths),
                "forbidden_literals": "none",
                "forecast_leakage": "passed",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
