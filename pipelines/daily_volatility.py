"""Runner instalable de volatilidad diaria y VaR.

El cálculo legacy se conserva, pero la corrida queda registrada con el runner
común y los tres outputs de volatilidad declarados.
"""

from __future__ import annotations

from trm_model.experiments.registry import DAILY_VOLATILITY_EXPERIMENT_ID
from trm_model.provenance import ProductRun, run_product


OUTPUT_FILES = (
    "results/pronostico/volatilidad_modelos_garch.csv",
    "results/pronostico/volatilidad_var_backtest.csv",
    "results/pronostico/volatilidad_serie_condicional.csv",
)


def _run_legacy() -> None:
    from volatility_model import main

    main()


def run() -> None:
    run_product(
        ProductRun(
            product_id="daily_volatility",
            runner=_run_legacy,
            output_files=OUTPUT_FILES,
            experiment_id=DAILY_VOLATILITY_EXPERIMENT_ID,
        )
    )


if __name__ == "__main__":
    run()
