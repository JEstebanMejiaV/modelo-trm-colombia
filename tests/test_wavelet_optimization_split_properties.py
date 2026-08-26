from __future__ import annotations

from itertools import product

import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization.config import (
    BASE_CANDIDATE_GRID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
)
from forecast_longterm.wavelet_optimization.evaluation import (
    NOT_SCOREABLE_COVERAGE_INCOMPLETE,
    NOT_SCOREABLE_RECONSTRUCTION,
    EvaluationBundle,
    OriginPrediction,
    assign_evaluation_splits,
)
from forecast_longterm.wavelet_optimization.labels import (
    NOT_EVALUABLE_LABEL_NOT_MATURE,
    NOT_SCOREABLE_INSUFFICIENT_TRAINING,
    SCOREABLE,
)

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings, strategies as st  # noqa: E402, I001


_CANDIDATE_IDS = tuple(candidate.candidate_id for candidate in BASE_CANDIDATE_GRID)
_BOUNDED_WINDOWS = {
    "2008_2019": (pd.Period("2008-01", freq="M"), pd.Period("2019-12", freq="M")),
    "2020_2022": (pd.Period("2020-01", freq="M"), pd.Period("2022-12", freq="M")),
    "2023_2026": (pd.Period("2023-01", freq="M"), pd.Period("2026-12", freq="M")),
}
_ORIGIN_ANCHORS = tuple(
    pd.Period(value, freq="M")
    for value in (
        "2007-12",
        "2008-01",
        "2019-12",
        "2020-01",
        "2022-12",
        "2023-01",
        "2026-12",
        "2027-01",
        "2028-01",
    )
)
_STATE_NAMES = (
    "scoreable",
    "insufficient_training",
    "coverage_incomplete",
    "reconstruction_invalid",
)


@st.composite
def _split_cases(
    draw: st.DrawFn,
) -> tuple[
    tuple[pd.Timestamp, ...],
    pd.Timestamp,
    tuple[str, ...],
    tuple[int, ...],
    tuple[str, ...],
    int,
    int,
]:
    base_origin = pd.Period("2007-12", freq="M")
    extra_offsets = draw(
        st.lists(
            st.integers(min_value=0, max_value=240),
            min_size=0,
            max_size=8,
            unique=True,
        )
    )
    extra_origins = tuple(base_origin + offset for offset in extra_offsets)
    origins = tuple(
        sorted({period.start_time for period in (*_ORIGIN_ANCHORS, *extra_origins)})
    )

    cutoff_period = pd.Period("2010-01", freq="M") + draw(
        st.integers(min_value=0, max_value=215)
    )
    cutoff_day = draw(st.integers(min_value=1, max_value=28))
    data_cutoff = cutoff_period.start_time + pd.Timedelta(days=cutoff_day - 1)

    candidate_ids = tuple(
        draw(
            st.lists(
                st.sampled_from(_CANDIDATE_IDS),
                min_size=2,
                max_size=4,
                unique=True,
            )
        )
    )
    horizons = tuple(draw(st.permutations(REQUIRED_HORIZONS)))

    logical_count = len(origins) * len(horizons) * len(candidate_ids)
    mandatory_states = _STATE_NAMES
    state_tail = draw(
        st.lists(
            st.sampled_from(_STATE_NAMES),
            min_size=logical_count - len(mandatory_states),
            max_size=logical_count - len(mandatory_states),
        )
    )
    states = mandatory_states + tuple(state_tail)

    scoreable_mature_labels = draw(st.integers(min_value=60, max_value=120))
    insufficient_mature_labels = draw(st.integers(min_value=0, max_value=59))
    return (
        origins,
        data_cutoff,
        candidate_ids,
        horizons,
        states,
        scoreable_mature_labels,
        insufficient_mature_labels,
    )


def _expected_splits(origin: pd.Timestamp, data_cutoff: pd.Timestamp) -> tuple[str, ...]:
    period = origin.to_period("M")
    if period > data_cutoff.to_period("M"):
        return ()
    bounded = tuple(
        split
        for split, (start, end) in _BOUNDED_WINDOWS.items()
        if start <= period <= end
    )
    assert len(bounded) <= 1
    return ("full", *bounded)


def _payload(row: OriginPrediction) -> dict[str, object]:
    payload = row.as_dict()
    payload.pop("split")
    return payload


# Feature: long-horizon-wavelet-optimization, Property 8: Splits y conteos son proyecciones de una tabla común
# Validates: Requirements 7.2, 7.3, 7.5, 7.6
@settings(max_examples=10, deadline=None)
@given(case=_split_cases())
def test_splits_and_counts_are_projections_of_one_logical_table(case: tuple) -> None:
    (
        origins,
        data_cutoff,
        candidate_ids,
        horizons,
        states,
        scoreable_mature_labels,
        insufficient_mature_labels,
    ) = case

    logical_rows: dict[tuple[pd.Timestamp, int, str], OriginPrediction] = {}
    for row_number, ((origin, horizon, candidate_id), state_name) in enumerate(
        zip(product(origins, horizons, candidate_ids), states, strict=True)
    ):
        label_end_date = origin + pd.DateOffset(months=horizon)
        effective_state = state_name
        if (
            state_name == "scoreable"
            and label_end_date.to_period("M") > data_cutoff.to_period("M")
        ):
            effective_state = "label_not_mature"

        if effective_state == "scoreable":
            prediction_wavelet = float(row_number) + 0.125
            prediction_random_walk = 0.0
            observed_forward_return = float(row_number) - 0.375
            n_mature_labels = scoreable_mature_labels
            scoreability_status = SCOREABLE
            coverage_status = "complete"
            causal_reconstruction = True
            warning = None
        elif effective_state == "insufficient_training":
            prediction_wavelet = None
            prediction_random_walk = None
            observed_forward_return = None
            n_mature_labels = insufficient_mature_labels
            scoreability_status = NOT_SCOREABLE_INSUFFICIENT_TRAINING
            coverage_status = "complete"
            causal_reconstruction = True
            warning = "insufficient_mature_training"
        elif effective_state == "coverage_incomplete":
            prediction_wavelet = None
            prediction_random_walk = None
            observed_forward_return = None
            n_mature_labels = scoreable_mature_labels
            scoreability_status = NOT_SCOREABLE_COVERAGE_INCOMPLETE
            coverage_status = "incomplete"
            causal_reconstruction = False
            warning = "coverage_incomplete"
        elif effective_state == "reconstruction_invalid":
            prediction_wavelet = None
            prediction_random_walk = None
            observed_forward_return = None
            n_mature_labels = scoreable_mature_labels
            scoreability_status = NOT_SCOREABLE_RECONSTRUCTION
            coverage_status = "complete"
            causal_reconstruction = False
            warning = "reconstruction_invalid"
        else:
            prediction_wavelet = None
            prediction_random_walk = None
            observed_forward_return = None
            n_mature_labels = scoreable_mature_labels
            scoreability_status = NOT_EVALUABLE_LABEL_NOT_MATURE
            coverage_status = "complete"
            causal_reconstruction = True
            warning = "forward_label_not_mature"

        logical_row = OriginPrediction(
            origin_date=origin,
            horizon_months=horizon,
            candidate_id=candidate_id,
            prediction_wavelet=prediction_wavelet,
            prediction_random_walk=prediction_random_walk,
            observed_forward_return=observed_forward_return,
            label_end_date=label_end_date,
            n_mature_labels=n_mature_labels,
            scoreability_status=scoreability_status,
            coverage_status=coverage_status,
            causal_reconstruction=causal_reconstruction,
            snapshot_manifest=f"snapshot/{origin:%Y-%m-%d}.json",
            source_vintage=f"vintage-{origin:%Y-%m}",
            split="full",
            prefix_last_date=origin,
            prefix_length=100 + row_number,
            prefix_sha256=f"{row_number + 1:064x}",
            warning=warning,
            minimum_mature_training=60,
            data_cutoff=data_cutoff,
            experiment_id="property-8-experiment",
            product_id="long_horizon_research",
        )
        logical_rows[logical_row.logical_key] = logical_row

    for origin in origins:
        actual = assign_evaluation_splits(
            origin,
            data_cutoff=data_cutoff,
            splits=REQUIRED_SPLITS,
        )
        expected = _expected_splits(origin, data_cutoff)
        assert actual == expected
        assert actual.count("full") <= 1
        assert len(set(actual).difference({"full"})) <= 1

    projected_rows = [
        logical_row.with_split(split)
        for logical_row in logical_rows.values()
        for split in _expected_splits(logical_row.origin_date, data_cutoff)
    ]
    projected_rows.sort(
        key=lambda row: (
            row.origin_date,
            row.horizon_months,
            row.candidate_id,
            REQUIRED_SPLITS.index(row.split),
        )
    )
    bundle = EvaluationBundle(predictions=tuple(projected_rows))
    rows_by_key = {(row.logical_key, row.split): row for row in bundle.all_predictions}

    expected_logical_keys = {
        logical_key
        for logical_key, logical_row in logical_rows.items()
        if _expected_splits(logical_row.origin_date, data_cutoff)
    }
    assert {row.logical_key for row in bundle.logical_predictions} == expected_logical_keys

    for logical_key, logical_row in logical_rows.items():
        assigned = _expected_splits(logical_row.origin_date, data_cutoff)
        full = rows_by_key.get((logical_key, "full"))
        if not assigned:
            assert full is None
            continue

        assert full is not None
        assert _payload(full) == _payload(logical_row)
        assert full.split == "full"
        assert full.is_scoreable == logical_row.is_scoreable
        if full.is_scoreable:
            assert full.n_mature_labels >= full.minimum_mature_training
            assert full.prediction_random_walk == 0.0
        else:
            assert full.prediction_random_walk is None

        for split in assigned[1:]:
            projected = rows_by_key[(logical_key, split)]
            assert _payload(projected) == _payload(full)
            assert projected.prediction_wavelet == full.prediction_wavelet
            assert projected.prediction_random_walk == full.prediction_random_walk
            assert projected.observed_forward_return == full.observed_forward_return
            assert projected.n_mature_labels == full.n_mature_labels
            assert projected.scoreability_status == full.scoreability_status
            assert projected.is_scoreable == full.is_scoreable

    expected_counts: dict[tuple[str, int, str], dict[str, int]] = {}
    for candidate_id in candidate_ids:
        for horizon in horizons:
            for split in REQUIRED_SPLITS:
                rows = [
                    logical_row
                    for logical_row in logical_rows.values()
                    if logical_row.candidate_id == candidate_id
                    and logical_row.horizon_months == horizon
                    and split in _expected_splits(logical_row.origin_date, data_cutoff)
                ]
                if not rows:
                    continue
                requested = len({row.origin_date for row in rows})
                scoreable = sum(row.is_scoreable for row in rows)
                expected_counts[(candidate_id, horizon, split)] = {
                    "n_requested_origins": requested,
                    "n_scoreable_origins": scoreable,
                    "n_excluded_origins": requested - scoreable,
                    "n_oos": scoreable,
                }

    assert bundle.counts == expected_counts
    for counts in bundle.counts.values():
        assert counts["n_requested_origins"] == (
            counts["n_scoreable_origins"] + counts["n_excluded_origins"]
        )
        assert counts["n_oos"] == counts["n_scoreable_origins"]
