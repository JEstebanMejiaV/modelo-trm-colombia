"""Fachada de transformaciones mensuales ya validadas."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd


def difference_components(model_data: pd.DataFrame) -> pd.DataFrame:
    """Aplica exactamente las diferencias y componentes del paquete legacy."""
    from model.transforms import difference_components as legacy_difference_components

    return legacy_difference_components(model_data)


def make_timed_difference_design(
    components: pd.DataFrame,
    p: int,
    factor_specs: Mapping[str, Mapping[str, Any]],
    index: pd.Index | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    """Construye el diseño temporal usando el mismo código econométrico vigente."""
    from model.transforms import make_timed_difference_design as legacy_design

    return legacy_design(components, p=p, factor_specs=dict(factor_specs), index=index)


def term_lags(factor_specs: Mapping[str, Mapping[str, Any]]) -> dict[str, list[int]]:
    """Normaliza términos legacy ``(componente, rezago)`` a una representación simple."""
    normalized: dict[str, list[int]] = {}
    for factor, specification in factor_specs.items():
        terms = specification.get("terminos") or specification.get("terms")
        if terms is None:
            raise ValueError(f"La especificación no tiene términos: {factor}")
        normalized[factor] = [
            int(term["lag_months"] if isinstance(term, Mapping) else term[1])
            for term in terms
        ]
    return normalized
