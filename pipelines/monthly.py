"""Orquestación mensual declarativa.

La implementación mensual target vive en ``trm_model.monthly.core`` detrás de
la CLI instalable. Este módulo conserva el entry point ``trm-monthly`` y
permite inyectar un runner en usos programáticos o pruebas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from trm_model.output_contract import (
    MONTHLY_GENERATED_PRODUCT_IDS,
    monthly_generated_output_ownership,
    resolve_output_ownership,
)
from trm_model.paths import ProjectPaths, project_paths

MONTHLY_PRODUCTS = MONTHLY_GENERATED_PRODUCT_IDS


def run_monthly(*, runner: Callable[[], None] | None = None) -> None:
    """Ejecuta la ruta mensual con manifest, conservando el runner legacy."""
    if runner is not None:
        runner()
        return

    from trm_model.cli import main

    main(["run-monthly"])


def declared_outputs(*, paths: ProjectPaths | None = None) -> list[Path]:
    """Devuelve los 42 outputs mensuales conocidos, sin crear ni mover archivos."""
    project = paths or project_paths()
    return resolve_output_ownership(
        monthly_generated_output_ownership(project),
        paths=project,
        require_existing=False,
    )
