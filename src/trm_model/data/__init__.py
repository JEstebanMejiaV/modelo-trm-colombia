"""Interfaces de datos del modelo TRM."""

from .curated import build_monthly_dataset
from .registry import SourceRegistry, load_source_registry
from .vintages import (
    VintageReport,
    VintageValidationError,
    forecast_vintage_coverage,
    validate_vintage_for_backtest,
    validate_vintage_manifest,
    vintage_status,
)

__all__ = [
    "SourceRegistry",
    "VintageReport",
    "VintageValidationError",
    "build_monthly_dataset",
    "forecast_vintage_coverage",
    "load_source_registry",
    "validate_vintage_for_backtest",
    "validate_vintage_manifest",
    "vintage_status",
]
