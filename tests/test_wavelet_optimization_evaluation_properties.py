from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings, strategies as st  # noqa: E402, I001

from forecast_longterm.wavelet_optimization.evaluation import (  # noqa: E402
    EvaluationBundle,
    OriginPrediction,
)
from forecast_longterm.wavelet_optimization.labels import SCOREABLE  # noqa: E402
from forecast_longterm.wavelet_optimization.metrics import (  # noqa: E402
    MetricsCalculator,
    build_common_sample,
    compute_dm_hac,
)


_CANDIDATE_ID = "property_7_candidate"
_HORIZON = 6
_SPLIT = "full"
_FINITE = st.floats(
    min_value=-100.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
    allow_subnormal=False,
)


@st.composite
def _prediction_bundle(draw: st.DrawFn) -> tuple[OriginPrediction, ...]:
    """Construye una tabla con filas scoreables y exclusiones con faltantes."""

    n_scoreable = draw(st.integers(min_value=1, max_value=24))
    n_excluded = draw(st.integers(min_value=1, max_value=8))
    scoreable_model = draw(
        st.lists(_FINITE, min_size=n_scoreable, max_size=n_scoreable)
    )
    scoreable_observed = draw(
        st.lists(_FINITE, min_size=n_scoreable, max_size=n_scoreable)
    )
    excluded_model = draw(
        st.lists(_FINITE, min_size=n_excluded, max_size=n_excluded)
    )
    excluded_observed = draw(
        st.lists(_FINITE, min_size=n_excluded, max_size=n_excluded)
    )
    missing_masks = draw(
        st.lists(
            st.integers(min_value=1, max_value=7),
            min_size=n_excluded,
            max_size=n_excluded,
        )
    )

    rows: list[OriginPrediction] = []
    values: list[tuple[float | None, float | None, float | None]] = [
        (model, 0.0, observed)
        for model, observed in zip(scoreable_model, scoreable_observed, strict=True)
    ]
    for model, observed, missing_mask in zip(
        excluded_model,
        excluded_observed,
        missing_masks,
        strict=True,
    ):
        values.append(
            (
                None if missing_mask & 1 else model,
                None if missing_mask & 2 else 0.0,
                None if missing_mask & 4 else observed,
            )
        )

    for index, (model, random_walk, observed) in enumerate(values):
        has_all_values = model is not None and random_walk is not None and observed is not None
        rows.append(
            OriginPrediction(
                origin_date=pd.Timestamp("2000-01-01") + pd.DateOffset(months=index),
                horizon_months=_HORIZON,
                candidate_id=_CANDIDATE_ID,
                prediction_wavelet=model,
                prediction_random_walk=random_walk,
                observed_forward_return=observed,
                scoreability_status=(
                    SCOREABLE if has_all_values else "not_scoreable_property_missing"
                ),
                coverage_status="complete" if has_all_values else "incomplete",
            )
        )

    permutation = draw(st.permutations(tuple(range(len(rows)))))
    return tuple(rows[index] for index in permutation)


def _numeric(values: tuple[float | None, ...] | list[float | None]) -> np.ndarray:
    return np.asarray(
        [np.nan if value is None else float(value) for value in values],
        dtype=float,
    )


def _assert_metric_value(actual: float | None, expected: float | None) -> None:
    if expected is None:
        assert actual is None
    else:
        assert actual == pytest.approx(expected)


# Feature: long-horizon-wavelet-optimization, Property 7: Modelo y caminata comparten muestra y métricas auditables
# Validates: Requirements 6.1, 6.2, 6.4
@settings(max_examples=10, deadline=None)
@given(rows=_prediction_bundle())
def test_model_and_benchmark_metrics_use_one_common_auditable_sample(
    rows: tuple[OriginPrediction, ...],
) -> None:
    bundle = EvaluationBundle(predictions=rows)
    metrics = MetricsCalculator().calculate(bundle)
    assert len(metrics) == 1
    metric = metrics[0]

    temporal_rows = tuple(sorted(rows, key=lambda row: row.origin_date))
    model = _numeric(tuple(row.prediction_wavelet for row in temporal_rows))
    random_walk = _numeric(tuple(row.prediction_random_walk for row in temporal_rows))
    observed = _numeric(tuple(row.observed_forward_return for row in temporal_rows))
    sample = build_common_sample(model, random_walk, observed)

    value_mask = np.isfinite(model) & np.isfinite(random_walk) & np.isfinite(observed)
    assert np.array_equal(sample.mask, value_mask)
    assert sample.n == int(value_mask.sum())
    assert np.array_equal(sample.model_common, model[value_mask])
    assert np.array_equal(sample.random_walk_common, random_walk[value_mask])
    assert np.array_equal(sample.observed_common, observed[value_mask])

    expected_keys = tuple(
        row.key for row, included in zip(temporal_rows, value_mask, strict=True) if included
    )
    scoreable_keys = tuple(row.key for row in temporal_rows if row.is_scoreable)
    assert scoreable_keys == expected_keys
    assert all(row.observed_forward_return is not None for row in temporal_rows if row.is_scoreable)
    assert all(row.prediction_random_walk == 0.0 for row in temporal_rows if row.is_scoreable)

    model_common = sample.model_common
    random_walk_common = sample.random_walk_common
    observed_common = sample.observed_common
    model_error = model_common - observed_common
    random_walk_error = random_walk_common - observed_common
    model_squared = np.square(model_error)
    random_walk_squared = np.square(random_walk_error)
    expected_sse_model = float(np.sum(model_squared))
    expected_sse_random_walk = float(np.sum(random_walk_squared))
    expected_r2 = (
        None
        if expected_sse_random_walk <= 0.0
        else 1.0 - expected_sse_model / expected_sse_random_walk
    )
    expected_dm = compute_dm_hac(
        model_common,
        random_walk_common,
        observed_common,
        horizon_months=_HORIZON,
    )

    assert metric.n_requested_origins == len(rows)
    assert metric.n_scoreable_origins == sample.n
    assert metric.n_excluded_origins == len(rows) - sample.n
    assert metric.n_oos == sample.n
    _assert_metric_value(metric.sse_model, expected_sse_model)
    _assert_metric_value(metric.sse_random_walk, expected_sse_random_walk)
    _assert_metric_value(metric.r2_oos, expected_r2)
    _assert_metric_value(metric.mae_model, float(np.mean(np.abs(model_error))))
    _assert_metric_value(metric.mae_random_walk, float(np.mean(np.abs(random_walk_error))))
    _assert_metric_value(metric.rmse_model, float(np.sqrt(np.mean(model_squared))))
    _assert_metric_value(metric.rmse_random_walk, float(np.sqrt(np.mean(random_walk_squared))))
    _assert_metric_value(
        metric.direction_accuracy_model,
        float(np.mean(np.sign(model_common) == np.sign(observed_common))),
    )
    _assert_metric_value(
        metric.direction_accuracy_random_walk,
        float(np.mean(np.sign(random_walk_common) == np.sign(observed_common))),
    )
    assert metric.dm_status == expected_dm.status
    _assert_metric_value(metric.dm_stat, expected_dm.dm_stat)
    _assert_metric_value(metric.dm_p_value, expected_dm.p_value)
    assert expected_dm.n_observations == sample.n

    bundle_counts = bundle.counts[(_CANDIDATE_ID, _HORIZON, _SPLIT)]
    assert bundle_counts == {
        "n_requested_origins": len(rows),
        "n_scoreable_origins": sample.n,
        "n_excluded_origins": len(rows) - sample.n,
        "n_oos": sample.n,
    }

    # El orden de entrada no puede cambiar la muestra temporal usada por DM.
    ordered_metrics = MetricsCalculator().calculate(
        EvaluationBundle(predictions=temporal_rows)
    )
    assert metrics == ordered_metrics
