"""Puente de datos curados hacia los loaders mensuales validados.

Durante la migración, ``model.loaders`` sigue siendo la única implementación
canónica de la consolidación mensual. Este módulo evita que las nuevas capas
importen scripts o manipulen ``sys.path`` y deja explícito el punto de corte
para una futura extracción del loader.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..paths import ProjectPaths, project_paths


def build_monthly_dataset(*, paths: ProjectPaths | None = None) -> pd.DataFrame:
    """Construye la base mensual usando el loader legacy sin duplicar lógica."""
    project = paths or project_paths()
    legacy_root = project.root
    from model.loaders import build_dataset as legacy_build_dataset

    # ``model.config`` conserva la raíz del repositorio para compatibilidad.
    # La comprobación evita ejecutar accidentalmente una base distinta.
    from model.config import ROOT as legacy_root_config

    if legacy_root_config.resolve() != legacy_root.resolve():
        raise RuntimeError(
            "La raíz de ProjectPaths no coincide con la raíz que usa model.config: "
            f"{legacy_root} != {legacy_root_config}"
        )
    return legacy_build_dataset()


def load_monthly_estimation_sample(
    *, paths: ProjectPaths | None = None, filename: str = "modelo_trm_muestra_estimacion.csv"
) -> pd.DataFrame:
    """Lee una muestra mensual versionada como artefacto de compatibilidad."""
    project = paths or project_paths()
    path = project.data / filename
    if not path.is_file():
        raise FileNotFoundError(f"No existe la muestra mensual: {path}")
    frame = pd.read_csv(path, parse_dates=["fecha"])
    return frame.set_index("fecha").sort_index()
