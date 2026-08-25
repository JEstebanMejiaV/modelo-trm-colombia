"""Loaders mensuales curados de la capa target."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..paths import ProjectPaths, project_paths
from .monthly_loaders import build_dataset
from ..monthly.specifications import ROOT as monthly_root


def build_monthly_dataset(*, paths: ProjectPaths | None = None) -> pd.DataFrame:
    """Construye la base mensual con el loader canónico de ``trm_model``."""
    project = paths or project_paths()
    if monthly_root.resolve() != project.root.resolve():
        raise RuntimeError(
            "La raíz de ProjectPaths no coincide con la raíz del dominio mensual: "
            f"{project.root} != {monthly_root}"
        )
    return build_dataset()


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
