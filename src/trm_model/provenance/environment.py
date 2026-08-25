"""Huella del ambiente de ejecución sin incluir secretos."""

from __future__ import annotations

import importlib.metadata
import platform
import sys


CORE_PACKAGES = (
    "numpy",
    "pandas",
    "scipy",
    "statsmodels",
    "openpyxl",
    "matplotlib",
)


def package_versions(names: tuple[str, ...] = CORE_PACKAGES) -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def environment_snapshot() -> dict[str, object]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": package_versions(),
        "executable": sys.executable,
    }
