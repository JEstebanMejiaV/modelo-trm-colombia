"""Entry point legacy compatible con el core mensual target.

La implementación vive en ``trm_model.monthly.core``. Este módulo conserva
``python src/estimate_model.py`` y los imports históricos sin duplicar lógica.
"""

from trm_model.monthly.core import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
