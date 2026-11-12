from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trm_model.monthly.mediation import (
    MediationEdge,
    MediationNode,
    MediationSpec,
    estimate_dynamic_mediation,
    validate_mediation_spec,
)


def _two_stage_spec(*, direct_path: bool = True) -> MediationSpec:
    edges = [MediationEdge("x_to_z", "x", "z", 1), MediationEdge("z_to_y", "z", "y", 1)]
    if direct_path:
        edges.append(MediationEdge("x_to_y", "x", "y", 0))
    return MediationSpec(
        nodes=(
            MediationNode("x", "D.x", "X", "source"),
            MediationNode("z", "D.z", "Z"),
            MediationNode("y", "D.y", "Y", "outcome"),
        ),
        edges=tuple(edges),
        outcome="y",
        path_sources=("x",),
    )


def _synthetic_components(seed: int = 41, periods: int = 72) -> pd.DataFrame:
    index = pd.date_range("2010-01-01", periods=periods, freq="MS")
    rng = np.random.default_rng(seed)
    x = pd.Series(rng.normal(size=periods), index=index)
    z = 0.75 * x.shift(1).fillna(0.0) + pd.Series(
        rng.normal(scale=0.08, size=periods), index=index
    )
    y = -0.55 * z.shift(1).fillna(0.0) + 0.05 * x + pd.Series(
        rng.normal(scale=0.08, size=periods), index=index
    )
    return pd.DataFrame({"D.x": x, "D.z": z, "D.y": y}, index=index)


def test_mediation_graph_is_topological_and_rejects_cycles() -> None:
    spec = _two_stage_spec()
    assert validate_mediation_spec(spec) == ("x", "z", "y")

    cyclic = MediationSpec(
        nodes=spec.nodes,
        edges=(*spec.edges, MediationEdge("y_to_z", "y", "z", 1)),
        outcome="y",
        path_sources=("x",),
    )
    with pytest.raises(ValueError, match="acíclica|ciclo"):
        validate_mediation_spec(cyclic)

    with pytest.raises(ValueError, match="no negativos"):
        MediationEdge("future", "x", "z", -1)


def test_mediation_uses_common_sample_and_never_future_lags() -> None:
    components = _synthetic_components()
    missing_date = components.index[24]
    components.loc[missing_date, "D.x"] = np.nan
    result = estimate_dynamic_mediation(
        components,
        spec=_two_stage_spec(),
        bootstrap_replicates=16,
        block_months=6,
        seed=7,
    )

    assert missing_date not in result.common_index
    assert components.index[25] not in result.common_index
    assert result.common_index.is_monotonic_increasing
    assert result.paths["rezago_total_meses"].ge(0).all()
    assert result.coefficients.loc[
        result.coefficients["tipo_termino"].eq("arista"), "rezago_meses"
    ].ge(0).all()


def test_mediation_path_product_preserves_signs() -> None:
    result = estimate_dynamic_mediation(
        _synthetic_components(),
        spec=_two_stage_spec(direct_path=False),
        bootstrap_replicates=24,
        block_months=8,
        seed=19,
    )
    indirect = result.paths.set_index("ruta_id").loc["ruta_x_to_z_z_to_y"]
    assert indirect["tipo_ruta"] == "indirecta"
    assert int(indirect["rezago_total_meses"]) == 2
    assert indirect["signo_ruta"] == "negativo"
    assert float(indirect["producto_coeficientes"]) < 0


def test_mediation_final_equation_closes_and_bootstrap_is_deterministic() -> None:
    components = _synthetic_components(seed=8)
    kwargs = {
        "components": components,
        "spec": _two_stage_spec(),
        "bootstrap_replicates": 20,
        "block_months": 5,
        "seed": 123,
    }
    first = estimate_dynamic_mediation(**kwargs)
    second = estimate_dynamic_mediation(**kwargs)

    assert first.contributions["cierre_contable"].abs().max() < 1e-8
    pd.testing.assert_frame_equal(first.bootstrap, second.bootstrap)
    assert first.bootstrap["replicas_validas"].eq(20).all()
