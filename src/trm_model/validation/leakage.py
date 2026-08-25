"""Auditorías de leakage para especificaciones con información temporal."""

from __future__ import annotations

from typing import Any, Mapping

from ..features.transforms import term_lags


class LeakageError(ValueError):
    """La especificación usa información no disponible al momento declarado."""


def validate_forecast_specs(
    factor_specs: Mapping[str, Mapping[str, Any]], *, minimum_lag: int = 1
) -> dict[str, list[int]]:
    """Exige que todos los términos de un pronóstico tengan al menos un rezago."""
    lags_by_factor = term_lags(factor_specs)
    violations = {
        factor: lags
        for factor, lags in lags_by_factor.items()
        if any(lag < minimum_lag for lag in lags)
    }
    if violations:
        details = ", ".join(f"{factor}: {lags}" for factor, lags in violations.items())
        raise LeakageError(
            f"La especificación pseudo-tiempo-real contiene términos contemporáneos "
            f"(rezago mínimo {minimum_lag}): {details}"
        )
    return lags_by_factor


def validate_information_set(
    information_set: str, factor_specs: Mapping[str, Mapping[str, Any]]
) -> None:
    """Aplica la regla temporal según la etiqueta de información del producto."""
    if information_set in {"pseudo_real_time", "vintage_backtest"}:
        validate_forecast_specs(factor_specs)


def leakage_report(
    factor_specs: Mapping[str, Mapping[str, Any]], *, minimum_lag: int = 1
) -> dict[str, Any]:
    lags = term_lags(factor_specs)
    violations = {
        name: values for name, values in lags.items() if any(v < minimum_lag for v in values)
    }
    return {
        "minimum_lag_months": minimum_lag,
        "factors": lags,
        "violations": violations,
        "passes": not violations,
    }
