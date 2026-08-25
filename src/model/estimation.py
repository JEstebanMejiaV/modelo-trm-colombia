"""Fachada legacy para estimación e inferencia mensual.

Las implementaciones canónicas están separadas por responsabilidad:

- ``trm_model.monthly.estimation`` ajusta y selecciona modelos.
- ``trm_model.monthly.inference`` calcula covarianzas, intervalos, tests y
  diagnósticos post-estimación.

Este módulo conserva los imports históricos sin duplicar lógica.
"""

from trm_model.monthly.estimation import (
    estimate_explanation,
    estimate_forecast,
    select_ardl,
    select_difference_model,
    select_timed_difference_model,
)
from trm_model.monthly.inference import (
    bounds_to_frames,
    diagnostics,
    integration_tests,
    tidy_long_run,
    tidy_result,
    tidy_robust_ols,
)

__all__ = [
    "bounds_to_frames",
    "diagnostics",
    "estimate_explanation",
    "estimate_forecast",
    "integration_tests",
    "select_ardl",
    "select_difference_model",
    "select_timed_difference_model",
    "tidy_long_run",
    "tidy_result",
    "tidy_robust_ols",
]
