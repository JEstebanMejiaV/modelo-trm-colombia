from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization.labels import (
    NOT_EVALUABLE_LABEL_NOT_MATURE,
    NOT_SCOREABLE_INSUFFICIENT_TRAINING,
    SCOREABLE,
    ForwardLabelBuilder,
)


def _monthly_series(start: str, periods: int) -> pd.Series:
    index = pd.date_range(start, periods=periods, freq="MS")
    values = 1_000.0 + np.arange(periods, dtype=float)
    return pd.Series(values, index=index, name="banrep_trm_1")


@pytest.mark.parametrize("horizon_months", [6, 12])
@pytest.mark.parametrize("n_mature", [59, 60, 61])
def test_maturity_threshold_is_exact_and_embargo_is_strict(
    horizon_months: int,
    n_mature: int,
) -> None:
    """The 60-label boundary is evaluated with ``label_end < origin``."""

    start = pd.Timestamp("2000-01-01")
    # Keep the forward endpoint for a target that starts at the origin, while
    # retaining one label ending exactly at the origin for the embargo check.
    origin = start + pd.DateOffset(months=n_mature + horizon_months)
    target_end = origin + pd.DateOffset(months=horizon_months)
    series = _monthly_series(
        start.strftime("%Y-%m-%d"),
        periods=n_mature + 2 * horizon_months + 1,
    )
    builder = ForwardLabelBuilder(
        data_cutoff=target_end,
        horizons=(horizon_months,),
    )

    labels = builder.build_horizon(series, horizon_months)
    result = builder.assess_origin(labels, origin, horizon_months)

    assert result.n_mature_labels == n_mature
    assert result.minimum_mature_training == 60
    expected_training_status = (
        NOT_SCOREABLE_INSUFFICIENT_TRAINING if n_mature == 59 else SCOREABLE
    )
    assert result.training_status == expected_training_status
    assert result.status == expected_training_status

    origin_period = origin.to_period("M")
    assert all(
        pd.Period(label.label_end_period, freq="M") < origin_period
        for label in result.mature_labels
    )
    assert all(
        pd.Period(label.origin_period, freq="M") + horizon_months
        == pd.Period(label.label_end_period, freq="M")
        for label in result.mature_labels
    )

    boundary_label = next(
        label
        for label in labels
        if label.label_end_period == str(origin_period)
    )
    target_label = next(
        label
        for label in labels
        if label.origin_period == str(origin_period)
    )
    assert boundary_label.ends_at(origin)
    assert not boundary_label.mature_for(origin)
    assert boundary_label not in result.mature_labels
    assert target_label.observed_by_cutoff is True
    assert result.target_label == target_label


@pytest.mark.parametrize("horizon_months", [6, 12])
def test_label_after_data_cutoff_is_not_observed_or_usable(
    horizon_months: int,
) -> None:
    origin = pd.Timestamp("2023-01-01")
    # The panel contains the forward endpoint, but the explicit cutoff does
    # not.  The endpoint is retained for diagnosis, never for training/OOS.
    series = _monthly_series(
        "2017-01-01",
        periods=72 + horizon_months + 1,
    )
    builder = ForwardLabelBuilder(
        data_cutoff=origin,
        horizons=(horizon_months,),
    )

    target = builder.label_for_origin(series, origin, horizon_months)
    assert target is not None
    assert target.label_end_date > origin
    assert target.observed_by_cutoff is False
    assert target.scoreability_status == NOT_EVALUABLE_LABEL_NOT_MATURE
    assert target.reason == "forward_label_end_after_data_cutoff"
    assert target.is_observed is False
    assert target.usable_value is None

    result = builder.assess_origin(series, origin, horizon_months)
    assert result.training_status == SCOREABLE
    assert result.status == NOT_EVALUABLE_LABEL_NOT_MATURE
    assert result.target_status == NOT_EVALUABLE_LABEL_NOT_MATURE
    assert result.reason == "forward_label_end_after_data_cutoff"
    assert result.observed_forward_return is None
    assert target not in result.mature_labels
    assert all(label.observed_by_cutoff for label in result.mature_labels)
    assert all(
        pd.Period(label.label_end_period, freq="M") <= builder.cutoff_period
        for label in result.mature_labels
    )


@pytest.mark.parametrize("horizon_months", [6, 12])
def test_2023_2026_origin_without_forward_observation_is_not_extrapolated(
    horizon_months: int,
) -> None:
    """A 2023--2026 split origin has no fabricated target beyond the panel."""

    split = "2023_2026"
    origin = pd.Timestamp("2023-12-01")
    cutoff = pd.Timestamp("2023-12-31")
    assert split == "2023_2026"
    assert pd.Timestamp("2023-01-01") <= origin <= pd.Timestamp("2026-12-31")

    # The series ends at the cutoff.  Neither horizon has a forward endpoint
    # for the origin, so no label may be extrapolated or imputed.
    series = _monthly_series("2017-01-01", periods=84)
    builder = ForwardLabelBuilder(
        data_cutoff=cutoff,
        horizons=(horizon_months,),
    )

    labels = builder.build_horizon(series, horizon_months)
    result = builder.assess_origin(series, origin, horizon_months)

    assert builder.label_for_origin(series, origin, horizon_months) is None
    assert result.target_label is None
    assert result.target_status == NOT_EVALUABLE_LABEL_NOT_MATURE
    assert result.status == NOT_EVALUABLE_LABEL_NOT_MATURE
    assert result.reason == "forward_label_end_not_available_in_panel_or_cutoff"
    assert result.observed_forward_return is None
    assert result.training_status == SCOREABLE
    assert result.n_mature_labels >= 60
    assert labels[-1].label_end_period == str(origin.to_period("M"))
    assert all(not label.ends_at(origin) for label in result.mature_labels)
    assert all(
        pd.Period(label.label_end_period, freq="M") < origin.to_period("M")
        for label in result.mature_labels
    )
