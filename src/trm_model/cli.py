"""CLI instalable para validación, ejecución de productos y provenance."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .data.registry import load_source_registry
from .output_contract import (
    MONTHLY_GENERATED_PRODUCT_IDS,
    monthly_generated_output_ownership,
    ownership_records,
    resolve_output_ownership,
    validate_run_output_ownership,
)
from .paths import project_paths
from .provenance.manifest import build_run_manifest, make_run_id, write_run_manifest
from .specifications.products import (
    load_product_manifest,
    load_products,
    validate_product_output_ownership,
)
from .validation.contracts import validate_product_manifest
from .validation.leakage import validate_forecast_specs


MONTHLY_BUNDLE_PRODUCTS = MONTHLY_GENERATED_PRODUCT_IDS


def _monthly_output_ownership(paths) -> dict[str, list[str]]:
    """Devuelve el contrato exacto de outputs escritos por ``estimate_model``."""
    return monthly_generated_output_ownership(paths)


def _monthly_config_files(paths) -> list:
    return [
        paths.configs / "common.toml",
        *(paths.product_config(product_id) for product_id in MONTHLY_BUNDLE_PRODUCTS),
    ]


def _monthly_output_files(paths, ownership: dict[str, list[str]]) -> list:
    return resolve_output_ownership(ownership, paths=paths, require_existing=True)


def _empty_product_records() -> list[dict[str, object]]:
    return ownership_records({product_id: [] for product_id in MONTHLY_BUNDLE_PRODUCTS})


def _validate_repository() -> int:
    paths = project_paths()
    registry = load_source_registry(paths=paths)
    missing = registry.missing_raw_files(root=paths.root)
    missing_model_inputs = registry.missing_monthly_model_inputs()
    if missing or missing_model_inputs:
        missing_text = ", ".join(paths.relative(path) for path in missing)
        if missing_model_inputs:
            missing_text = ", ".join(filter(None, [missing_text, *missing_model_inputs]))
        raise FileNotFoundError(f"Faltan fuentes activas o inputs mensuales registrados: {missing_text}")

    products = load_products(paths=paths)
    for product_id in products:
        manifest = load_product_manifest(product_id, paths=paths)
        validate_product_output_ownership(product_id, manifest, paths=paths)
        validate_product_manifest(manifest, paths=paths)

    from trm_model.monthly.specifications import (
        FORECAST_FACTOR_SPECS_3,
        FORECAST_FACTOR_SPECS_4,
    )

    validate_forecast_specs(FORECAST_FACTOR_SPECS_3)
    validate_forecast_specs(FORECAST_FACTOR_SPECS_4)
    print(
        json.dumps(
            {
                "status": "ok",
                "sources_active": len(registry.active_sources),
                "products": sorted(products),
                "forecast_leakage_check": "passed",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_monthly() -> int:
    paths = project_paths()
    product_id = "monthly_bundle"
    started = datetime.now(timezone.utc)
    run_id = make_run_id(started_at=started, product_id=product_id)
    registry = load_source_registry(paths=paths)
    missing = registry.missing_raw_files(root=paths.root)
    missing_model_inputs = registry.missing_monthly_model_inputs()
    if missing or missing_model_inputs:
        missing_text = ", ".join(paths.relative(path) for path in missing)
        if missing_model_inputs:
            missing_text = ", ".join(filter(None, [missing_text, *missing_model_inputs]))
        raise FileNotFoundError(f"Faltan fuentes activas o inputs mensuales registrados: {missing_text}")

    config_files = _monthly_config_files(paths)
    input_files = list(registry.raw_paths(root=paths.root))
    ownership = _monthly_output_ownership(paths)
    product_records = ownership_records(ownership)
    running = build_run_manifest(
        product_id=product_id,
        config_files=config_files,
        input_files=input_files,
        output_files=[],
        paths=paths,
        status="running",
        run_id=run_id,
        started_at=started,
        finished_at=started,
    )
    running["products"] = _empty_product_records()
    write_run_manifest(running, paths=paths)

    try:
        from trm_model.monthly.core import main as monthly_main

        monthly_main()
        output_files = _monthly_output_files(paths, ownership)
        completed = build_run_manifest(
            product_id=product_id,
            config_files=config_files,
            input_files=input_files,
            output_files=output_files,
            paths=paths,
            status="success",
            run_id=run_id,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
        )
        completed["products"] = product_records
        validate_run_output_ownership(
            completed,
            expected_product_ids=set(MONTHLY_BUNDLE_PRODUCTS),
        )
        destination = write_run_manifest(completed, paths=paths)
        print(f"Manifest de corrida escrito en {paths.relative(destination)}")
        return 0
    except Exception as error:
        failed = build_run_manifest(
            product_id=product_id,
            config_files=config_files,
            input_files=input_files,
            output_files=[],
            paths=paths,
            status="failed",
            run_id=run_id,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error=f"{type(error).__name__}: {error}",
        )
        failed["products"] = _empty_product_records()
        write_run_manifest(failed, paths=paths)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trm-model")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Valida contratos, fuentes y leakage mensual")
    subparsers.add_parser("run-monthly", help="Ejecuta el bundle mensual target con manifest")
    subparsers.add_parser(
        "run-daily-direction",
        help="Ejecuta el producto diario direccional con manifest",
    )
    subparsers.add_parser(
        "run-daily-volatility",
        help="Ejecuta volatilidad diaria y VaR con manifest",
    )
    subparsers.add_parser(
        "vintage-status",
        help="Valida snapshots fechados y cobertura point-in-time sin imputar",
    )
    research = subparsers.add_parser(
        "run-research",
        help="Ejecuta un módulo de investigación de largo plazo con manifest",
    )
    research.add_argument("--module", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        return _validate_repository()
    if args.command == "run-monthly":
        return _run_monthly()
    if args.command == "vintage-status":
        from trm_model.data.vintages import vintage_status

        print(json.dumps(vintage_status(paths=project_paths()), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run-daily-direction":
        from pipelines.daily_direction import run

        run()
        return 0
    if args.command == "run-daily-volatility":
        from pipelines.daily_volatility import run

        run()
        return 0
    if args.command == "run-research":
        from pipelines.long_horizon import run

        run(args.module)
        return 0
    raise AssertionError(f"Comando no implementado: {args.command}")


if __name__ == "__main__":
    sys.exit(main())
