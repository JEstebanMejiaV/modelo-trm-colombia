"""Compatibilidad legacy para transformaciones y selección mensual.

Las transformaciones y diseños viven en ``trm_model.features``; la selección
de modelos y las pruebas de integración viven en módulos canónicos separados.
"""

from trm_model.features.monthly_transforms import *  # noqa: F401,F403
from trm_model.monthly.estimation import (  # noqa: F401
    select_difference_model,
    select_timed_difference_model,
)
from trm_model.monthly.inference import integration_tests  # noqa: F401
