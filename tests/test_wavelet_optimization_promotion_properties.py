from __future__ import annotations

from dataclasses import dataclass

import pytest

from forecast_longterm.wavelet_optimization.config import load_research_plan
from forecast_longterm.wavelet_optimization.metrics import EvaluationMetrics
from forecast_longterm.wavelet_optimization.promotion import PromotionGate

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings, strategies as st  # noqa: E402, I001


_CANDIDATE_ID = "db4_l5_sym_D1"
_HORIZONS = (6, 12)
_SPLITS = ("full", "2008_2019", "2020_2022", "2023_2026")
_R2_BOUNDARIES = (-0.11, -0.10, 0.0, 1e-12, 0.25)
_N_OOS_BOUNDARIES = (0, 11, 12, 13, 24)


@dataclass(frozen=True)
class _GateCase:
    full_r2: float
    split_r2: tuple[float | None, float | None, float | None]
    split_n_oos: tuple[int, int, int]
    mae_passes: bool
    rmse_passes: bool
    dm_evaluable: bool
    dm_passes: bool
    causal_passes: bool
    maturity_passes: bool
    coverage_passes: bool
    provenance_passes: bool


@st.composite
def _gate_cases(draw: st.DrawFn) -> _GateCase:
    split_n_oos = tuple(
        draw(st.sampled_from(_N_OOS_BOUNDARIES))
        for _ in range(3)
    )
    split_r2 = tuple(
        None if n_oos == 0 else draw(st.sampled_from(_R2_BOUNDARIES))
        for n_oos in split_n_oos
    )
    return _GateCase(
        full_r2=draw(st.sampled_from(_R2_BOUNDARIES)),
        split_r2=split_r2,
        split_n_oos=split_n_oos,
        mae_passes=draw(st.booleans()),
        rmse_passes=draw(st.booleans()),
        dm_evaluable=draw(st.booleans()),
        dm_passes=draw(st.booleans()),
        causal_passes=draw(st.booleans()),
        maturity_passes=draw(st.booleans()),
        coverage_passes=draw(st.booleans()),
        provenance_passes=draw(st.booleans()),
    )


def _metric(
    *,
    split: str,
    r2_oos: float | None,
    n_oos: int,
    mae_passes: bool,
    rmse_passes: bool,
    dm_evaluable: bool,
    dm_passes: bool,
) -> EvaluationMetrics:
    n_requested = max(12, n_oos)
    return EvaluationMetrics(
        candidate_id=_CANDIDATE_ID,
        horizon_months=6,
        split=split,
        n_requested_origins=n_requested,
        n_scoreable_origins=n_oos,
        n_excluded_origins=n_requested - n_oos,
        n_oos=n_oos,
        sse_model=None if r2_oos is None else 1.0 - r2_oos,
        sse_random_walk=None if r2_oos is None else 1.0,
        r2_oos=r2_oos,
        mae_model=0.5 if mae_passes else 1.0,
        mae_random_walk=1.0,
        rmse_model=0.5 if rmse_passes else 1.0,
        rmse_random_walk=1.0,
        direction_accuracy_model=0.5,
        direction_accuracy_random_walk=0.5,
        dm_stat=1.0 if dm_evaluable else None,
        dm_p_value=(0.05 if dm_passes else 0.050001) if dm_evaluable else None,
        dm_status="evaluated" if dm_evaluable else "insufficient_observations",
    )


def _metrics(case: _GateCase) -> tuple[EvaluationMetrics, ...]:
    metrics: list[EvaluationMetrics] = []
    for horizon in _HORIZONS:
        full = _metric(
            split="full",
            r2_oos=case.full_r2,
            n_oos=12,
            mae_passes=case.mae_passes,
            rmse_passes=case.rmse_passes,
            dm_evaluable=case.dm_evaluable,
            dm_passes=case.dm_passes,
        )
        metrics.append(
            EvaluationMetrics(
                **{
                    **full.as_dict(),
                    "horizon_months": horizon,
                }
            )
        )
        for split, r2_oos, n_oos in zip(
            _SPLITS[1:], case.split_r2, case.split_n_oos, strict=True
        ):
            split_metric = _metric(
                split=split,
                r2_oos=r2_oos,
                n_oos=n_oos,
                mae_passes=True,
                rmse_passes=True,
                dm_evaluable=False,
                dm_passes=False,
            )
            metrics.append(
                EvaluationMetrics(
                    **{
                        **split_metric.as_dict(),
                        "horizon_months": horizon,
                    }
                )
            )
    return tuple(metrics)


def _expected_conditions(case: _GateCase) -> dict[str, bool]:
    split_r2 = (case.full_r2, *case.split_r2)
    split_n_oos = (12, *case.split_n_oos)
    scoreable_r2 = tuple(
        r2 for r2, n_oos in zip(split_r2, split_n_oos, strict=True)
        if n_oos > 0 and r2 is not None
    )
    expected: dict[str, bool] = {}
    for horizon in _HORIZONS:
        expected[f"full_r2_oos_positive_h{horizon}"] = case.full_r2 > 0.0
        expected[f"full_mae_below_benchmark_h{horizon}"] = case.mae_passes
        expected[f"full_rmse_below_benchmark_h{horizon}"] = case.rmse_passes
        expected[f"full_dm_p_value_at_most_0_05_h{horizon}"] = (
            case.dm_evaluable and case.dm_passes
        )
        expected[f"at_least_3_of_4_positive_splits_h{horizon}"] = (
            sum(
                n_oos >= 12 and r2 is not None and r2 > 0.0
                for r2, n_oos in zip(split_r2, split_n_oos, strict=True)
            )
            >= 3
        )
        expected[f"no_scoreable_split_below_r2_floor_h{horizon}"] = bool(
            scoreable_r2 and all(r2 >= -0.10 for r2 in scoreable_r2)
        )
    expected.update(
        {
            "causal_reconstruction": case.causal_passes,
            "label_maturity": case.maturity_passes,
            "complete_pit_coverage": case.coverage_passes,
            "complete_provenance": case.provenance_passes,
        }
    )
    return expected


# Feature: long-horizon-wavelet-optimization, Property 11: El gate es una conjunción conservadora y explica cada rechazo
# Validates: Requirements 10.1, 10.2, 10.3, 10.4
@settings(max_examples=10, deadline=None)
@given(case=_gate_cases())
def test_promotion_gate_is_conservative_and_explains_every_rejection(
    case: _GateCase,
) -> None:
    plan = load_research_plan(
        data_cutoff="2026-04-01",
        origin_dates=("2020-01-01", "2023-01-01"),
    )
    metrics = _metrics(case)
    coverage = [
        {
            "candidate_id": _CANDIDATE_ID,
            "causal_reconstruction": case.causal_passes,
            "label_maturity": case.maturity_passes,
            "coverage_complete": case.coverage_passes,
            "coverage_status": "complete" if case.coverage_passes else "incomplete",
            "n_missing": 0 if case.coverage_passes else 1,
        }
    ]
    provenance = {"provenance_complete": case.provenance_passes}

    result = PromotionGate().evaluate(
        plan,
        metrics=metrics,
        coverage=coverage,
        provenance=provenance,
    )
    decision = result["by_candidate"][_CANDIDATE_ID]
    expected_conditions = _expected_conditions(case)
    expected_eligible = all(expected_conditions.values())

    assert result["eligible"] is expected_eligible
    assert decision["eligible"] is expected_eligible

    expected_failed = {
        condition for condition, passed in expected_conditions.items() if not passed
    }
    actual_failed = set(decision["failed_conditions"])
    actual_failed_details = {
        detail["condition"] for detail in decision["failed_condition_details"]
    }
    assert actual_failed == expected_failed
    assert actual_failed_details == expected_failed

    actual_conditions = {
        condition["condition"]: condition["passed"]
        for condition in decision["conditions"]
    }
    assert actual_conditions == expected_conditions
