"""Runner común para módulos de investigación de largo plazo.

Cada módulo conserva su cálculo y sus outputs legacy, pero la corrida se
registra como `long_horizon_research` y nunca se promociona a producto primary.
"""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from pathlib import Path
from typing import Any

from trm_model.experiments.registry import research_experiment_id
from trm_model.provenance import ProductRun, run_product

WAVELET_OPTIMIZATION_MODULE = "wavelet_optimization"
WAVELET_OPTIMIZATION_EXPERIMENT_ID = "long_horizon_research.wavelet_optimization.v1"
WAVELET_OPTIMIZATION_CONFIG = Path(
    "research/configs/long_horizon_wavelet_optimization.toml"
)
WAVELET_OPTIMIZATION_SCHEMA = Path("schemas/long_horizon_wavelet_optimization.json")
_UNSET = object()

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
    WAVELET_OPTIMIZATION_MODULE,
    "signals",
    "wavelets",
}
LEGACY_MODULES = frozenset(ALLOWED_MODULES) - {WAVELET_OPTIMIZATION_MODULE}


def _run_module(module_name: str) -> None:
    module = import_module(f"forecast_longterm.{module_name}")
    runner = getattr(module, "main", None)
    if runner is None:
        raise AttributeError(f"forecast_longterm.{module_name} no expone main()")
    runner()


def _run_wavelet_optimization(
    *,
    paths: Any | None = None,
    data_cutoff: Any = _UNSET,
    origin_dates: Iterable[Any] | Any = _UNSET,
    config_path: str | Path | None = None,
    schema_path: str | Path | None = None,
    snapshot_resolver: Any | None = None,
    series_store: Any | None = None,
    label_series: Any | None = None,
    input_files: Iterable[str | Path] = (),
) -> Any:
    """Despacha explícitamente la variante PIT sin envolverla en ``ProductRun``.

    El entry point de la variante ya compone su propio provenance y publica
    exactamente sus cuatro rutas. Envolverlo en el runner legacy generaría un
    segundo manifest y mezclaría el contrato de outputs históricos con el
    namespace nuevo.
    """

    if data_cutoff is _UNSET or data_cutoff is None:
        raise ValueError(
            "wavelet_optimization requiere Data_Cutoff explícito; "
            "no se infiere de los datos disponibles"
        )
    if origin_dates is _UNSET or origin_dates is None:
        raise ValueError(
            "wavelet_optimization requiere al menos un Forecast_Origin explícito"
        )

    # La importación es lazy para que el opt-in no cambie la carga ni el
    # comportamiento de los módulos research legacy.
    from forecast_longterm.wavelet_optimization import run_wavelet_optimization

    runner_kwargs: dict[str, Any] = {
        "paths": paths,
        "config_path": config_path or WAVELET_OPTIMIZATION_CONFIG,
        "schema_path": schema_path or WAVELET_OPTIMIZATION_SCHEMA,
        "data_cutoff": data_cutoff,
        "origin_dates": origin_dates,
        "snapshot_resolver": snapshot_resolver,
        "series_store": series_store,
    }
    if label_series is not None:
        runner_kwargs["label_series"] = label_series
    if input_files:
        runner_kwargs["input_files"] = input_files
    result = run_wavelet_optimization(**runner_kwargs)
    result_plan = getattr(result, "plan", None)
    result_experiment_id = getattr(result_plan, "experiment_id", None)
    if (
        result_experiment_id is not None
        and result_experiment_id != WAVELET_OPTIMIZATION_EXPERIMENT_ID
    ):
        raise ValueError(
            "wavelet_optimization devolvió un experiment_id inesperado: "
            f"{result_experiment_id!r}"
        )
    return result


def run(
    module_name: str,
    *,
    paths: Any | None = None,
    data_cutoff: Any = _UNSET,
    origin_dates: Iterable[Any] | Any = _UNSET,
    config_path: str | Path | None = None,
    schema_path: str | Path | None = None,
    snapshot_resolver: Any | None = None,
    series_store: Any | None = None,
    label_series: Any | None = None,
    input_files: Iterable[str | Path] = (),
) -> Any:
    if module_name not in ALLOWED_MODULES:
        allowed = ", ".join(sorted(ALLOWED_MODULES))
        raise ValueError(f"Módulo long-term no permitido: {module_name}. Opciones: {allowed}")

    if module_name == WAVELET_OPTIMIZATION_MODULE:
        return _run_wavelet_optimization(
            paths=paths,
            data_cutoff=data_cutoff,
            origin_dates=origin_dates,
            config_path=config_path,
            schema_path=schema_path,
            snapshot_resolver=snapshot_resolver,
            series_store=series_store,
            label_series=label_series,
            input_files=input_files,
        )

    run_product(
        ProductRun(
            product_id="long_horizon_research",
            runner=lambda: _run_module(module_name),
            run_context={"research_module": module_name},
            experiment_id=research_experiment_id(module_name),
        )
    )
    return None


def run_all() -> None:
    """Ejecuta los módulos legacy; la variante wavelet requiere opt-in explícito."""
    for module_name in sorted(LEGACY_MODULES):
        run(module_name)
