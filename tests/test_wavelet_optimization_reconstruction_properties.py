from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st

from forecast_longterm.wavelet_optimization.config import load_research_plan
from forecast_longterm.wavelet_optimization.reconstruction import OriginReconstructor
from forecast_longterm.wavelet_optimization.snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSnapshot,
    SourceVintage,
)


@st.composite
def _positive_monthly_fixture(
    draw: st.DrawFn,
) -> tuple[list[int], list[int]]:
    prefix = draw(
        st.lists(
            st.integers(min_value=500, max_value=5000),
            min_size=256,
            max_size=320,
        )
    )
    future_tail = draw(
        st.lists(
            st.integers(min_value=500, max_value=5000),
            min_size=1,
            max_size=12,
        )
    )
    return prefix, future_tail


def _in_memory_origin_fixture(
    prefix_length: int,
) -> tuple[ForecastOrigin, PointInTimeSnapshot, object, pd.DatetimeIndex]:
    dates = pd.date_range(
        "2000-01-01",
        periods=prefix_length + 12,
        freq="MS",
    )
    origin_date = dates[prefix_length - 1]
    snapshot_manifest = f"memory/{origin_date:%Y-%m-%d}/manifest.json"
    origin = ForecastOrigin(
        origin_date=origin_date,
        data_cutoff=origin_date,
        snapshot_manifest=snapshot_manifest,
    )
    vintage = SourceVintage(
        source_id=BANREP_TRM_SOURCE_ID,
        vintage_id=f"memory-vintage-{origin_date:%Y-%m}",
        snapshot_manifest=snapshot_manifest,
        archived_path=f"memory/{origin_date:%Y-%m-%d}/trm.csv",
        available_through=origin_date,
        sha256="0" * 64,
    )
    snapshot = PointInTimeSnapshot(
        origin=origin,
        source_vintages=(vintage,),
        manifest_sha256="1" * 64,
    )
    plan = load_research_plan(
        data_cutoff=origin_date,
        origin_dates=(origin_date,),
    )
    return origin, snapshot, plan, dates


# Feature: long-horizon-wavelet-optimization, Property 2: Reconstrucción causal depende solo del prefijo permitido
# Validates: Requirements 3.1, 3.2, 3.3
@settings(max_examples=10, deadline=None)
@given(fixture=_positive_monthly_fixture())
def test_causal_reconstruction_depends_only_on_allowed_prefix(
    fixture: tuple[list[int], list[int]],
) -> None:
    prefix_values, future_tail = fixture
    origin, snapshot, plan, dates = _in_memory_origin_fixture(len(prefix_values))

    first_values = np.asarray(prefix_values + future_tail, dtype=float)
    second_values = np.asarray(
        prefix_values + [value + 10_000 for value in future_tail],
        dtype=float,
    )
    changed_prefix_values = prefix_values.copy()
    changed_prefix_values[0] += 1
    changed_prefix = np.asarray(
        changed_prefix_values + future_tail,
        dtype=float,
    )
    series_dates = dates[: len(first_values)]
    first_series = pd.Series(first_values, index=series_dates, name="banrep_trm_1")
    second_series = pd.Series(second_values, index=series_dates, name="banrep_trm_1")
    changed_prefix_series = pd.Series(
        changed_prefix,
        index=series_dates,
        name="banrep_trm_1",
    )

    cache: dict[tuple[object, ...], object] = {}
    reconstructor = OriginReconstructor(cache=cache)
    first = reconstructor.reconstruct(origin, snapshot, first_series, plan)
    second = reconstructor.reconstruct(origin, snapshot, second_series, plan)

    assert first.status == second.status == "causal"
    assert first.metadata == second.metadata
    assert first.metadata.prefix_last_date <= origin.origin_date
    assert first.metadata.uses_future_observations is False
    assert second.metadata.prefix_last_date <= origin.origin_date
    assert second.metadata.uses_future_observations is False
    assert first.metadata.prefix_sha256 == second.metadata.prefix_sha256
    assert len(cache) == 1

    assert set(first.components) == set(second.components)
    for component_name in first.components:
        pd.testing.assert_series_equal(
            first.components[component_name],
            second.components[component_name],
        )
    assert set(first.signals) == set(second.signals)
    for candidate_id in first.signals:
        pd.testing.assert_series_equal(
            first.signals[candidate_id],
            second.signals[candidate_id],
        )

    different_prefix = reconstructor.reconstruct(
        origin,
        snapshot,
        changed_prefix_series,
        plan,
    )
    assert different_prefix.metadata.prefix_last_date <= origin.origin_date
    assert different_prefix.metadata.uses_future_observations is False
    assert different_prefix.metadata.prefix_sha256 != first.metadata.prefix_sha256
    assert len(cache) == 2

    cache_prefix_hashes = {
        key[key.index("prefix_sha256") + 1]
        for key in cache
    }
    assert cache_prefix_hashes == {
        first.metadata.prefix_sha256,
        different_prefix.metadata.prefix_sha256,
    }
    assert any(
        not first.components[component_name].equals(
            different_prefix.components[component_name]
        )
        for component_name in first.components
    )
