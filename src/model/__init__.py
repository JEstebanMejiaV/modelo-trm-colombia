"""Paquete de estimación del modelo TRM Colombia.

Importar desde este paquete en vez de desde estimate_model.py directamente:

    from model.loaders import build_dataset
    from model.transforms import difference_components, make_timed_difference_design
    from model.estimation import tidy_robust_ols, diagnostics, select_ardl
    from model.validation import difference_validation
    from model.shapley import exact_shapley_r2, block_bootstrap_shapley
    from model.bei import bei_stationarity_tests, bei_model_specification_comparison
    from model.readme_sync import update_readme_fragments
    from model.config import (
        ROOT, RESULTS, DATA, RAW,
        SAMPLE_START, SAMPLE_END,
        INTEGRATED_FACTOR_SPECS_4, FORECAST_FACTOR_SPECS_3,
    )
"""
