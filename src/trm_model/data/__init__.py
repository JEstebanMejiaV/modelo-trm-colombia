"""Interfaces de datos del modelo TRM."""

from .curated import build_monthly_dataset
from .registry import SourceRegistry, load_source_registry

__all__ = ["SourceRegistry", "build_monthly_dataset", "load_source_registry"]
