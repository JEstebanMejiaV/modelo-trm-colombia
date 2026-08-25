"""Runner común para módulos de investigación de largo plazo.

Cada módulo conserva su cálculo y sus outputs legacy, pero la corrida se
registra como `long_horizon_research` y nunca se promociona a producto primary.
"""

from __future__ import annotations

from importlib import import_module

from trm_model.experiments.registry import research_experiment_id
from trm_model.provenance import ProductRun, run_product

ALLOWED_MODULES = {
    "backtest",
    "beveridge_nelson",
    "carry_factor",
    "cf_markov_strategy",
    "cointegration",
    "compare_filters",
    "extended_signals",
    "global_variables",
    "panel_em",
    "signals",
    "wavelets",
}


def _run_module(module_name: str) -> None:
    module = import_module(f"forecast_longterm.{module_name}")
    runner = getattr(module, "main", None)
    if runner is None:
        raise AttributeError(f"forecast_longterm.{module_name} no expone main()")
    runner()


def run(module_name: str) -> None:
    if module_name not in ALLOWED_MODULES:
        allowed = ", ".join(sorted(ALLOWED_MODULES))
        raise ValueError(f"Módulo long-term no permitido: {module_name}. Opciones: {allowed}")

    run_product(
        ProductRun(
            product_id="long_horizon_research",
            runner=lambda: _run_module(module_name),
            run_context={"research_module": module_name},
            experiment_id=research_experiment_id(module_name),
        )
    )


def run_all() -> None:
    """Ejecuta cada módulo permitido como una corrida research independiente."""
    for module_name in sorted(ALLOWED_MODULES):
        run(module_name)
