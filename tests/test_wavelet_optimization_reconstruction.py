from __future__ import annotations

import importlib
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization import reconstruction as reconstruction_module
from forecast_longterm.wavelet_optimization.config import load_research_plan
from forecast_longterm.wavelet_optimization.reconstruction import (
    CausalReconstructionError,
    OriginReconstructor,
    ReconstructionResult,
)
from forecast_longterm.wavelet_optimization.snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSnapshot,
    SourceVintage,
)


def _fixture(length: int = 262):
    dates = pd.date_range("1999-09-01", periods=length, freq="MS")
    origin_date = dates[min(255, length - 1)]
    origin = ForecastOrigin(
        origin_date=origin_date,
        data_cutoff=origin_date,
        snapshot_manifest="memory/2020-12-01/manifest.json",
    )
    vintage = SourceVintage(
        source_id=BANREP_TRM_SOURCE_ID,
        vintage_id="memory-vintage-2020-12",
        snapshot_manifest=origin.snapshot_manifest,
        archived_path="memory/2020-12-01/trm.csv",
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
    values = 1000.0 + np.linspace(0.0, 100.0, length) + 8.0 * np.sin(
        np.arange(length) / 7.0
    )
    return dates, origin, snapshot, plan, pd.Series(values, index=dates, name="banrep_trm_1")


def test_reconstruction_uses_only_prefix_and_exposes_scaled_candidate_signals() -> None:
    dates, origin, snapshot, plan, trm = _fixture()
    changed_future = trm.copy()
    changed_future.iloc[256:] = np.linspace(10_000.0, 20_000.0, len(changed_future) - 256)

    first = OriginReconstructor().reconstruct(origin, snapshot, trm, plan)
    second = OriginReconstructor().reconstruct(origin, snapshot, changed_future, plan)

    assert set(first.components) == {"D1", "D2", "D3", "D4", "D5", "A5"}
    assert set(first.signals) == {candidate.candidate_id for candidate in plan.candidates}
    assert first.metadata.prefix_length == 256
    assert first.metadata.prefix_first_date == dates[0]
    assert first.metadata.prefix_last_date == origin.origin_date
    assert first.metadata.available_through == origin.origin_date
    assert first.metadata.uses_future_observations is False
    assert first.metadata.prefix_sha256 == second.metadata.prefix_sha256
    for name in first.components:
        pd.testing.assert_series_equal(first.components[name], second.components[name])

    candidate = next(item for item in plan.candidates if item.candidate_id == "db4_l5_sym_D3_D4")
    expected_signal = (first.components["D3"] + first.components["D4"]) * candidate.signal_scale
    expected_signal.name = candidate.candidate_id
    pd.testing.assert_series_equal(first.signals[candidate.candidate_id], expected_signal)
    assert first.signal_value(candidate.candidate_id) == pytest.approx(float(expected_signal.iloc[-1]))


def test_reconstruction_rejects_insufficient_level_and_nonpositive_trm() -> None:
    dates, origin, snapshot, plan, trm = _fixture(length=100)
    with pytest.raises(CausalReconstructionError, match="Prefijo insuficiente"):
        OriginReconstructor().reconstruct(origin, snapshot, trm, plan)

    dates, origin, snapshot, plan, trm = _fixture()
    invalid = trm.copy()
    invalid.loc[dates[100]] = 0.0
    with pytest.raises(CausalReconstructionError, match="TRM no positiva"):
        OriginReconstructor().reconstruct(origin, snapshot, invalid, plan)


def test_reconstruction_rejects_future_vintage_metadata() -> None:
    dates, origin, snapshot, plan, trm = _fixture()
    future_vintage = SourceVintage(
        source_id=BANREP_TRM_SOURCE_ID,
        vintage_id="future-vintage",
        snapshot_manifest=origin.snapshot_manifest,
        archived_path="memory/2020-12-01/trm.csv",
        available_through=dates[256],
        sha256="2" * 64,
    )
    future_snapshot = PointInTimeSnapshot(
        origin=origin,
        source_vintages=(future_vintage,),
        manifest_sha256="3" * 64,
    )
    with pytest.raises(CausalReconstructionError, match="posterior al corte"):
        OriginReconstructor().reconstruct(origin, future_snapshot, trm, plan)


def test_reconstruction_rejects_reported_dwt_max_level_even_with_long_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _dates, origin, snapshot, plan, trm = _fixture()

    monkeypatch.setattr(
        reconstruction_module.pywt,
        "dwt_max_level",
        lambda *_args, **_kwargs: 4,
    )

    with pytest.raises(CausalReconstructionError, match="dwt_max_level=4"):
        OriginReconstructor().reconstruct(origin, snapshot, trm, plan)


def test_reconstruction_drops_missing_prefix_values_without_imputation() -> None:
    dates, origin, snapshot, plan, trm = _fixture()
    missing = trm.astype(float).copy()
    missing.iloc[100] = np.nan

    result = OriginReconstructor().reconstruct(origin, snapshot, missing, plan)
    expected = OriginReconstructor().reconstruct(
        origin,
        snapshot,
        trm.drop(index=dates[100]),
        plan,
    )

    assert result.metadata.prefix_length == expected.metadata.prefix_length == 255
    assert dates[100] not in result.components["D1"].index
    assert result.metadata.prefix_sha256 == expected.metadata.prefix_sha256
    for name in result.components:
        pd.testing.assert_series_equal(result.components[name], expected.components[name])


def test_reconstruction_rejects_non_numeric_prefix_values() -> None:
    _dates, origin, snapshot, plan, trm = _fixture()
    non_numeric = trm.astype(object).copy()
    non_numeric.iloc[100] = "not-a-number"

    with pytest.raises(CausalReconstructionError, match="no numéricos"):
        OriginReconstructor().reconstruct(origin, snapshot, non_numeric, plan)


def test_reconstruction_passes_symmetric_mode_to_dwt_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _dates, origin, snapshot, plan, trm = _fixture()
    original_wavedec = reconstruction_module.pywt.wavedec
    original_waverec = reconstruction_module.pywt.waverec
    wavedec_modes: list[object] = []
    waverec_modes: list[object] = []

    def recording_wavedec(*args, **kwargs):
        wavedec_modes.append(kwargs.get("mode"))
        return original_wavedec(*args, **kwargs)

    def recording_waverec(*args, **kwargs):
        waverec_modes.append(kwargs.get("mode"))
        return original_waverec(*args, **kwargs)

    monkeypatch.setattr(reconstruction_module.pywt, "wavedec", recording_wavedec)
    monkeypatch.setattr(reconstruction_module.pywt, "waverec", recording_waverec)

    result = OriginReconstructor().reconstruct(origin, snapshot, trm, plan)

    assert result.status == "causal"
    assert wavedec_modes == ["symmetric"]
    assert waverec_modes == ["symmetric"] * 6


@pytest.mark.parametrize(
    ("metadata_mutation", "error_match"),
    [
        pytest.param(
            lambda metadata: replace(metadata, uses_future_observations=True),
            "uses_future_observations=True",
            id="future-observations-flag",
        ),
        pytest.param(
            lambda metadata: replace(
                metadata,
                prefix_last_date=metadata.origin_date + pd.offsets.MonthBegin(1),
            ),
            "posterior al ForecastOrigin",
            id="complete-sample-prefix",
        ),
    ],
)
def test_reconstruction_rejects_metadata_indicating_future_or_full_sample(
    metadata_mutation,
    error_match: str,
) -> None:
    _dates, origin, snapshot, plan, trm = _fixture()
    valid = OriginReconstructor().reconstruct(origin, snapshot, trm, plan)
    invalid_metadata = metadata_mutation(valid.metadata)

    with pytest.raises(CausalReconstructionError, match=error_match):
        ReconstructionResult(
            components=valid.components,
            metadata=invalid_metadata,
            status="causal",
            signals=valid.signals,
        )


def test_reconstruction_does_not_use_historical_wavelet_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical = importlib.import_module("forecast_longterm.wavelets")

    def forbidden_historical_decomposition(*_args, **_kwargs):
        raise AssertionError("no debe invocarse la implementación wavelet histórica")

    monkeypatch.setattr(
        historical,
        "wavelet_decomposition",
        forbidden_historical_decomposition,
    )
    _dates, origin, snapshot, plan, trm = _fixture()

    result = OriginReconstructor().reconstruct(origin, snapshot, trm, plan)

    assert result.status == "causal"
    assert result.metadata.uses_future_observations is False
