from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization.config import load_research_plan
from forecast_longterm.wavelet_optimization.evaluation import (
    EXCLUDED_NUMERIC_FAILURE,
    INVALID_CAUSAL_RECONSTRUCTION,
    NOT_EVALUABLE_LABEL_NOT_MATURE,
    NOT_SCOREABLE_COVERAGE_INCOMPLETE,
    NOT_SCOREABLE_INSUFFICIENT_TRAINING,
    NOT_SCOREABLE_SNAPSHOT_MISSING,
    NOT_SCOREABLE_SOURCE_MISSING,
    SCOREABLE,
    OOS_Evaluator,
)
from forecast_longterm.wavelet_optimization.snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSnapshot,
    SnapshotResolutionError,
    SourceVintage,
)

_CANDIDATE_ID = "db4_l5_sym_D1"
_START = pd.Timestamp("1998-01-01")
_TARGET = pd.Timestamp("2004-01-01")
_DEFAULT_CUTOFF = pd.Timestamp("2006-01-01")


@dataclass
class _EvaluationFixture:
    plan: object
    panel: pd.Series
    target: pd.Timestamp
    resolver: "_MemorySnapshotResolver"
    store: "_MemorySeriesStore"
    reconstructor: "_MemoryReconstructor"


class _MemorySnapshotResolver:
    def __init__(
        self,
        snapshots: dict[pd.Timestamp, PointInTimeSnapshot],
        *,
        missing_origins: Iterable[pd.Timestamp] = (),
    ) -> None:
        self.snapshots = snapshots
        self.missing_origins = set(missing_origins)

    def resolve(
        self,
        origin: ForecastOrigin,
        required_source_ids: tuple[str, ...],
    ) -> PointInTimeSnapshot:
        del required_source_ids
        if origin.origin_date in self.missing_origins:
            raise SnapshotResolutionError(
                "snapshot PIT ausente",
                origin=origin,
                source_id=BANREP_TRM_SOURCE_ID,
                coverage_status="missing",
                scoreability_status=NOT_SCOREABLE_SNAPSHOT_MISSING,
                reason="snapshot_manifest_missing",
            )
        return self.snapshots[origin.origin_date]


class _MemorySeriesStore:
    def __init__(
        self,
        panel: pd.Series,
        *,
        incomplete_origins: Iterable[pd.Timestamp] = (),
    ) -> None:
        self.panel = panel
        self.incomplete_origins = set(incomplete_origins)
        self.returned: dict[pd.Timestamp, pd.Series] = {}

    def monthly_series(
        self,
        snapshot: PointInTimeSnapshot,
        source_id: str,
        *,
        through: pd.Timestamp,
    ) -> pd.Series:
        del through
        if source_id != BANREP_TRM_SOURCE_ID:
            raise KeyError(source_id)
        origin = snapshot.origin.origin_date
        series = self.panel.loc[self.panel.index <= origin].copy(deep=True)
        if origin in self.incomplete_origins:
            missing_date = origin - pd.DateOffset(months=1)
            series = series.drop(index=missing_date)
        self.returned[origin] = series.copy(deep=True)
        return series


class _MemoryReconstruction:
    def __init__(
        self,
        origin: ForecastOrigin,
        series: pd.Series,
        vintage_id: str,
        *,
        invalid_causal: bool,
        numeric_failure: bool,
    ) -> None:
        self.status = "causal"
        self._origin = origin
        self._numeric_failure = numeric_failure
        self.metadata = SimpleNamespace(
            origin_date=origin.origin_date,
            available_through=origin.effective_cutoff,
            prefix_last_date=series.index[-1],
            prefix_length=len(series),
            prefix_sha256="a" * 64,
            source_vintage=vintage_id,
            uses_future_observations=invalid_causal,
        )

    def signal_value(self, candidate: object) -> float:
        if self._numeric_failure:
            return 1.0
        candidate_id = str(getattr(candidate, "candidate_id", candidate))
        candidate_offset = (sum(ord(character) for character in candidate_id) % 17) / 100.0
        return float(self._origin.origin_date.to_period("M").ordinal) + candidate_offset


class _MemoryReconstructor:
    def __init__(
        self,
        *,
        invalid_origins: Iterable[pd.Timestamp] = (),
        numeric_failure: bool = False,
    ) -> None:
        self.invalid_origins = set(invalid_origins)
        self.numeric_failure = numeric_failure
        self.calls: list[pd.Timestamp] = []

    def reconstruct(
        self,
        origin: ForecastOrigin,
        snapshot: PointInTimeSnapshot,
        trm_monthly: pd.Series,
        plan: object,
    ) -> _MemoryReconstruction:
        del plan
        self.calls.append(origin.origin_date)
        vintage = snapshot.source(BANREP_TRM_SOURCE_ID)
        return _MemoryReconstruction(
            origin,
            trm_monthly,
            vintage.vintage_id,
            invalid_causal=origin.origin_date in self.invalid_origins,
            numeric_failure=self.numeric_failure,
        )


def _snapshot(origin: pd.Timestamp, data_cutoff: pd.Timestamp, *, with_vintage: bool) -> PointInTimeSnapshot:
    manifest = f"memory/{origin:%Y-%m}/manifest.json"
    forecast_origin = ForecastOrigin(
        origin_date=origin,
        data_cutoff=data_cutoff,
        snapshot_manifest=manifest,
    )
    vintages: tuple[SourceVintage, ...] = ()
    if with_vintage:
        vintage = SourceVintage(
            source_id=BANREP_TRM_SOURCE_ID,
            vintage_id=f"memory-{origin:%Y%m}",
            snapshot_manifest=manifest,
            archived_path=f"memory/{origin:%Y-%m}/trm.csv",
            available_through=origin,
            sha256=(f"source-{origin:%Y%m}".encode("utf-8").hex() * 4)[:64],
        )
        vintages = (vintage,)
    return PointInTimeSnapshot(
        origin=forecast_origin,
        source_vintages=vintages,
        manifest_sha256=(f"manifest-{origin:%Y%m}".encode("utf-8").hex() * 4)[:64],
    )


def _make_fixture(
    *,
    start: pd.Timestamp = _START,
    target: pd.Timestamp = _TARGET,
    data_cutoff: pd.Timestamp = _DEFAULT_CUTOFF,
    missing_snapshot: Iterable[pd.Timestamp] = (),
    missing_vintage: Iterable[pd.Timestamp] = (),
    incomplete_coverage: Iterable[pd.Timestamp] = (),
    invalid_causal: Iterable[pd.Timestamp] = (),
    numeric_failure: bool = False,
) -> _EvaluationFixture:
    target = pd.Timestamp(target).normalize()
    data_cutoff = pd.Timestamp(data_cutoff).normalize()
    panel_end = max(data_cutoff, target + pd.DateOffset(months=12))
    dates = pd.date_range(start, panel_end, freq="MS")
    positions = np.arange(len(dates), dtype=float)
    panel = pd.Series(
        1_000.0 + 0.75 * positions + 4.0 * np.sin(positions / 5.0),
        index=dates,
        name=BANREP_TRM_SOURCE_ID,
    )
    origin_dates = tuple(date for date in dates if date <= target)
    plan = load_research_plan(data_cutoff=data_cutoff, origin_dates=origin_dates)
    snapshots = {
        origin: _snapshot(
            origin,
            data_cutoff,
            with_vintage=origin not in set(missing_vintage),
        )
        for origin in origin_dates
    }
    resolver = _MemorySnapshotResolver(
        snapshots,
        missing_origins=missing_snapshot,
    )
    store = _MemorySeriesStore(panel, incomplete_origins=incomplete_coverage)
    reconstructor = _MemoryReconstructor(
        invalid_origins=invalid_causal,
        numeric_failure=numeric_failure,
    )
    return _EvaluationFixture(
        plan=plan,
        panel=panel,
        target=target,
        resolver=resolver,
        store=store,
        reconstructor=reconstructor,
    )


def _evaluate(fixture: _EvaluationFixture):
    evaluator = OOS_Evaluator(
        snapshot_resolver=fixture.resolver,
        series_store=fixture.store,
        origin_reconstructor=fixture.reconstructor,
    )
    return evaluator.evaluate(fixture.plan, label_series=fixture.panel)


def _target_row(fixture: _EvaluationFixture, bundle, *, horizon: int = 6):
    rows = tuple(
        row
        for row in bundle.origin_predictions
        if row.origin_date == fixture.target
        and row.horizon_months == horizon
        and row.candidate_id == _CANDIDATE_ID
    )
    assert len(rows) == 1
    return rows[0]


def _target_coverage(fixture: _EvaluationFixture, bundle, *, horizon: int = 6):
    rows = tuple(
        row
        for row in bundle.coverage
        if row["origin_date"] == fixture.target.strftime("%Y-%m-%d")
        and row["horizon_months"] == horizon
    )
    assert len(rows) == 1
    return rows[0]


def _assert_null_predictions(row) -> None:
    assert row.prediction_wavelet is None
    assert row.prediction_random_walk is None
    assert not row.is_scoreable


def test_scoreable_evaluation_preserves_observed_label_and_zero_benchmark() -> None:
    fixture = _make_fixture()
    bundle = _evaluate(fixture)
    row = _target_row(fixture, bundle)

    assert row.scoreability_status == SCOREABLE
    assert row.coverage_status == "complete"
    assert row.causal_reconstruction is True
    assert row.prediction_wavelet is not None
    assert row.prediction_random_walk == 0.0
    assert row.observed_forward_return is not None
    assert row.label_end_date == fixture.target + pd.DateOffset(months=6)
    assert row.n_mature_labels >= 60
    assert _target_coverage(fixture, bundle)["coverage_status"] == "complete"


@pytest.mark.parametrize("missing_kind", ["snapshot", "vintage"])
def test_missing_snapshot_or_vintage_keeps_mature_observed_and_null_predictions(
    missing_kind: str,
) -> None:
    kwargs = (
        {"missing_snapshot": {_TARGET}}
        if missing_kind == "snapshot"
        else {"missing_vintage": {_TARGET}}
    )
    fixture = _make_fixture(**kwargs)
    bundle = _evaluate(fixture)
    row = _target_row(fixture, bundle)

    expected_status = (
        NOT_SCOREABLE_SNAPSHOT_MISSING
        if missing_kind == "snapshot"
        else NOT_SCOREABLE_SOURCE_MISSING
    )
    assert row.scoreability_status == expected_status
    assert row.coverage_status == "missing"
    assert row.observed_forward_return is not None
    assert row.causal_reconstruction is False
    _assert_null_predictions(row)

    coverage = _target_coverage(fixture, bundle)
    assert coverage["coverage_status"] == "missing"
    assert "r2_oos" not in coverage


def test_incomplete_coverage_is_not_imputed_and_keeps_mature_observed() -> None:
    fixture = _make_fixture(incomplete_coverage={_TARGET})
    bundle = _evaluate(fixture)
    row = _target_row(fixture, bundle)

    missing_date = fixture.target - pd.DateOffset(months=1)
    returned_prefix = fixture.store.returned[fixture.target]
    assert missing_date not in returned_prefix.index
    assert len(returned_prefix) == len(fixture.panel.loc[: fixture.target]) - 1
    assert fixture.target not in fixture.reconstructor.calls
    assert row.scoreability_status == NOT_SCOREABLE_COVERAGE_INCOMPLETE
    assert row.coverage_status == "incomplete"
    assert row.observed_forward_return is not None
    _assert_null_predictions(row)

    coverage = _target_coverage(fixture, bundle)
    assert coverage["n_missing"] >= 1
    assert coverage["reason"] == "missing_months_without_imputation"


def test_invalid_causal_reconstruction_is_distinct_from_predictive_failure() -> None:
    fixture = _make_fixture(invalid_causal={_TARGET})
    bundle = _evaluate(fixture)
    row = _target_row(fixture, bundle)

    assert row.scoreability_status == INVALID_CAUSAL_RECONSTRUCTION
    assert row.coverage_status == "complete"
    assert row.causal_reconstruction is False
    assert row.observed_forward_return is not None
    _assert_null_predictions(row)
    assert "future" in (row.warning or "")


def test_immature_forward_label_has_null_observed_value_without_extrapolation() -> None:
    fixture = _make_fixture(data_cutoff=_TARGET)
    bundle = _evaluate(fixture)
    row = _target_row(fixture, bundle)

    assert row.scoreability_status == NOT_EVALUABLE_LABEL_NOT_MATURE
    assert row.coverage_status == "complete"
    assert row.label_end_date == fixture.target + pd.DateOffset(months=6)
    assert row.label_end_date > fixture.plan.data_cutoff
    assert row.observed_forward_return is None
    assert row.n_mature_labels >= 60
    _assert_null_predictions(row)


def test_insufficient_mature_training_keeps_observed_label_and_excludes_fit() -> None:
    fixture = _make_fixture(
        start=pd.Timestamp("2000-01-01"),
        target=pd.Timestamp("2002-12-01"),
        data_cutoff=pd.Timestamp("2004-12-01"),
    )
    bundle = _evaluate(fixture)

    for horizon in (6, 12):
        row = _target_row(fixture, bundle, horizon=horizon)
        assert row.scoreability_status == NOT_SCOREABLE_INSUFFICIENT_TRAINING
        assert row.n_mature_labels < 60
        assert row.observed_forward_return is not None
        _assert_null_predictions(row)


def test_numeric_exclusion_keeps_observed_label_but_not_a_benchmark_value() -> None:
    fixture = _make_fixture(numeric_failure=True)
    bundle = _evaluate(fixture)
    row = _target_row(fixture, bundle)

    assert row.scoreability_status == EXCLUDED_NUMERIC_FAILURE
    assert row.coverage_status == "complete"
    assert row.causal_reconstruction is True
    assert row.observed_forward_return is not None
    _assert_null_predictions(row)
