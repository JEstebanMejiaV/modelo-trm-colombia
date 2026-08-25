"""Runner instalable del pronóstico diario direccional.

El cálculo legacy se conserva, pero la corrida queda registrada con el runner
común y solo se incluyen los outputs que este entry point produce.
"""

from __future__ import annotations

from trm_model.provenance import ProductRun, run_product
from forecast_daily.reproducibility import DAILY_RANDOM_SEED


OUTPUT_FILES = (
    "results/pronostico/comparacion_modelos_diarios.csv",
    "results/pronostico/feature_importance_ml_diario.csv",
)


def _run_legacy() -> None:
    from forecast_daily.run import main

    main()


def run() -> None:
    run_product(
        ProductRun(
            product_id="daily_direction",
            runner=_run_legacy,
            output_files=OUTPUT_FILES,
            run_context={
                "random_seed": DAILY_RANDOM_SEED,
                "deterministic": True,
                "thread_limit": 1,
            },
        )
    )


if __name__ == "__main__":
    run()
