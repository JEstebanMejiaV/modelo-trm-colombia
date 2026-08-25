"""Wrapper explícito para módulos de investigación de largo plazo."""

from __future__ import annotations

from importlib import import_module

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


def run(module_name: str) -> None:
    if module_name not in ALLOWED_MODULES:
        allowed = ", ".join(sorted(ALLOWED_MODULES))
        raise ValueError(f"Módulo long-term no permitido: {module_name}. Opciones: {allowed}")
    module = import_module(f"forecast_longterm.{module_name}")
    runner = getattr(module, "main", None)
    if runner is None:
        raise AttributeError(f"forecast_longterm.{module_name} no expone main()")
    runner()
