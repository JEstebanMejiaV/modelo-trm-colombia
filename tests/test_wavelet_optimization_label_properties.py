from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization.labels import ForwardLabelBuilder

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings, strategies as st  # noqa: E402, I001


@st.composite
def _positive_monthly_series_and_origin(
    draw: st.DrawFn,
) -> tuple[pd.Series, int, int]:
    """Generate a positive contiguous monthly panel and an origin position."""

    horizon = draw(st.sampled_from((6, 12)))
    length = draw(st.integers(min_value=24, max_value=96))
    values = draw(
        st.lists(
            st.integers(min_value=1, max_value=1_000_000),
            min_size=length,
            max_size=length,
        )
    )
    origin_index = draw(
        st.integers(min_value=horizon + 1, max_value=length - 1)
    )
    dates = pd.date_range("2000-01-01", periods=length, freq="MS")
    series = pd.Series(
        np.asarray(values, dtype=float),
        index=dates,
        name="banrep_trm_1",
    )
    return series, horizon, origin_index


# Feature: long-horizon-wavelet-optimization, Property 3: Objetivo y embargo estricto son consistentes
# Validates: Requirements 4.2, 4.3, 4.6
@settings(max_examples=10, deadline=None)
@given(case=_positive_monthly_series_and_origin())
def test_forward_returns_and_strict_label_embargo_are_consistent(
    case: tuple[pd.Series, int, int],
) -> None:
    series, horizon, origin_index = case
    periods = series.index.to_period("M")
    origin_period = periods[origin_index]
    builder = ForwardLabelBuilder(
        data_cutoff=series.index[-1],
        horizons=(horizon,),
    )

    labels = builder.build_horizon(series, horizon)
    assert labels

    for label in labels:
        start_index = int(periods.get_loc(pd.Period(label.origin_period, freq="M")))
        end_index = start_index + horizon
        expected = 100.0 * (
            np.log(float(series.iloc[end_index]))
            - np.log(float(series.iloc[start_index]))
        )
        assert label.value == pytest.approx(expected)
        assert label.label_end_period == str(periods[end_index])

    training_labels = builder.mature_labels(
        labels,
        origin_period,
        horizon_months=horizon,
    )
    for label in training_labels:
        start_index = int(periods.get_loc(pd.Period(label.origin_period, freq="M")))
        assert start_index + horizon < origin_index
        assert pd.Period(label.label_end_period, freq="M") < origin_period

    boundary_start = origin_index - horizon
    boundary_label = next(
        label
        for label in labels
        if label.origin_period == str(periods[boundary_start])
    )
    assert boundary_label.label_end_period == str(origin_period)
    assert boundary_label not in training_labels
