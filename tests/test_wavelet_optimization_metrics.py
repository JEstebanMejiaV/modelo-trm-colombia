from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from forecast_longterm.wavelet_optimization.config import (
    PRODUCT_ID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    RESEARCH_STATUS,
)
from forecast_longterm.wavelet_optimization.metrics import (
    DM_EVALUATED,
    DM_INSUFFICIENT_OBSERVATIONS,
    DM_NON_POSITIVE_HAC_VARIANCE,
    EvaluationMetrics,
    MetricsCalculator,
    calculate_r2_oos,
    compute_dm_hac,
)
from forecast_longterm.wavelet_optimization.promotion import (
    CONDITION_FAILED,
    PromotionGate,
)

CANDIDATE_ID = "candidate_test"


def _metric(
    horizon_months: int,
    split: str,
    *,
    r2_oos: float,
    n_oos: int = 12,
    dm_p_value: float = 0.05,
) -> EvaluationMetrics:
    return EvaluationMetrics(
        candidate_id=CANDIDATE_ID,
        horizon_months=horizon_months,
        split=split,
        n_requested_origins=n_oos,
        n_scoreable_origins=n_oos,
        n_excluded_origins=0,
        n_oos=n_oos,
        sse_model=100.0 * (1.0 - r2_oos),
        sse_random_walk=100.0,
        r2_oos=r2_oos,
        mae_model=0.5,
        mae_random_walk=1.0,
        rmse_model=0.75,
        rmse_random_walk=1.25,
        direction_accuracy_model=0.75,
        direction_accuracy_random_walk=0.5,
        dm_stat=1.0,
        dm_p_value=dm_p_value,
        dm_status=DM_EVALUATED,
    )


def _gate_metrics(
    *,
    full_r2: float = 0.01,
    third_positive_split_n: int = 12,
    fourth_split_r2: float = -0.10,
) -> tuple[EvaluationMetrics, ...]:
    rows: list[EvaluationMetrics] = []
    for horizon in REQUIRED_HORIZONS:
        rows.extend(
            (
                _metric(horizon, "full", r2_oos=full_r2),
                _metric(horizon, "2008_2019", r2_oos=0.02),
                _metric(
                    horizon,
                    "2020_2022",
                    r2_oos=0.03,
                    n_oos=third_positive_split_n,
                ),
                _metric(horizon, "2023_2026", r2_oos=fourth_split_r2),
            )
        )
    return tuple(rows)


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        candidates=(CANDIDATE_ID,),
        horizons=REQUIRED_HORIZONS,
        splits=REQUIRED_SPLITS,
        dm_min_observations=12,
        dm_max_lag_rule="horizon_minus_one",
        product_id=PRODUCT_ID,
        status=RESEARCH_STATUS,
    )


def _complete_provenance() -> dict[str, object]:
    return {
        "causal_reconstruction": True,
        "label_maturity": True,
        "provenance_complete": True,
    }


def _evaluate_gate(
    metrics: tuple[EvaluationMetrics, ...],
    *,
    provenance: dict[str, object] | None = None,
) -> dict[str, object]:
    return PromotionGate().evaluate(
        _plan(),
        metrics=metrics,
        coverage=({"coverage_status": "complete"},),
        provenance=_complete_provenance() if provenance is None else provenance,
    )


def _decision(result: dict[str, object]) -> dict[str, object]:
    decisions = result["candidate_decisions"]
    return next(
        decision for decision in decisions if decision["candidate_id"] == CANDIDATE_ID
    )


def _conditions(decision: dict[str, object]) -> dict[str, dict[str, object]]:
    return {condition["condition"]: condition for condition in decision["conditions"]}


@pytest.mark.parametrize(
    ("sse_model", "expected"),
    [(100.0, 0.0), (110.0, -0.10)],
    ids=["zero", "negative-ten-percent"],
)
def test_r2_oos_preserves_zero_and_negative_tenth_boundaries(
    sse_model: float,
    expected: float,
) -> None:
    assert calculate_r2_oos(sse_model, 100.0) == pytest.approx(expected)


def test_metrics_do_not_invent_r2_when_benchmark_sse_is_zero() -> None:
    metrics = MetricsCalculator().calculate(
        (
            {
                "candidate_id": CANDIDATE_ID,
                "horizon_months": 6,
                "split": "full",
                "prediction_wavelet": 0.0,
                "prediction_random_walk": 0.0,
                "observed_forward_return": 0.0,
            },
        )
    )

    assert len(metrics) == 1
    assert metrics[0].sse_random_walk == 0.0
    assert metrics[0].r2_oos is None


def test_dm_requires_twelve_observations_and_evaluates_at_twelve() -> None:
    model = np.zeros(12)
    random_walk = np.sqrt(np.arange(1.0, 13.0))
    observed = np.zeros(12)

    insufficient = compute_dm_hac(
        model[:11],
        random_walk[:11],
        observed[:11],
        horizon_months=6,
    )
    evaluated = compute_dm_hac(
        model,
        random_walk,
        observed,
        horizon_months=6,
    )

    assert insufficient.n_observations == 11
    assert insufficient.status == DM_INSUFFICIENT_OBSERVATIONS
    assert insufficient.p_value is None
    assert evaluated.n_observations == 12
    assert evaluated.status == DM_EVALUATED
    assert evaluated.hac_variance is not None and evaluated.hac_variance > 0
    assert evaluated.p_value is not None


def test_dm_marks_zero_hac_variance_as_not_evaluable() -> None:
    result = compute_dm_hac(
        np.zeros(12),
        np.ones(12),
        np.zeros(12),
        horizon_months=6,
    )

    assert result.status == DM_NON_POSITIVE_HAC_VARIANCE
    assert result.dm_stat is None
    assert result.p_value is None
    assert result.hac_variance == 0.0


def test_gate_accepts_p_value_boundary_three_positive_splits_and_floor() -> None:
    result = _evaluate_gate(_gate_metrics())
    decision = _decision(result)
    conditions = _conditions(decision)

    assert result["eligible"] is True
    assert decision["eligible"] is True
    for horizon in REQUIRED_HORIZONS:
        assert conditions[f"full_r2_oos_positive_h{horizon}"]["status"] == "passed"
        dm_condition = conditions[f"full_dm_p_value_at_most_0_05_h{horizon}"]
        assert dm_condition["status"] == "passed"
        assert dm_condition["evidence"]["dm_p_value"] == 0.05

        split_condition = conditions[f"at_least_3_of_4_positive_splits_h{horizon}"]
        assert split_condition["status"] == "passed"
        assert split_condition["evidence"]["n_positive_splits"] == 3

        floor_condition = conditions[f"no_scoreable_split_below_r2_floor_h{horizon}"]
        assert floor_condition["status"] == "passed"
        assert floor_condition["evidence"]["violating_splits"] == []


def test_gate_rejects_r2_equal_to_zero_for_full_split() -> None:
    result = _evaluate_gate(_gate_metrics(full_r2=0.0))
    conditions = _conditions(_decision(result))

    assert result["eligible"] is False
    for horizon in REQUIRED_HORIZONS:
        condition = conditions[f"full_r2_oos_positive_h{horizon}"]
        assert condition["status"] == CONDITION_FAILED
        assert condition["reason"] == "threshold_not_met"


def test_gate_requires_twelve_observations_for_the_third_positive_split() -> None:
    for n_oos, expected_eligibility, expected_positive in (
        (11, False, 2),
        (12, True, 3),
    ):
        result = _evaluate_gate(_gate_metrics(third_positive_split_n=n_oos))
        decision = _decision(result)
        conditions = _conditions(decision)

        assert decision["eligible"] is expected_eligibility
        for horizon in REQUIRED_HORIZONS:
            split_condition = conditions[f"at_least_3_of_4_positive_splits_h{horizon}"]
            assert split_condition["evidence"]["n_positive_splits"] == expected_positive


def test_gate_rejects_false_causal_reconstruction_evidence() -> None:
    provenance = _complete_provenance()
    provenance["causal_reconstruction"] = False

    result = _evaluate_gate(_gate_metrics(), provenance=provenance)
    condition = _conditions(_decision(result))["causal_reconstruction"]

    assert result["eligible"] is False
    assert condition["status"] == CONDITION_FAILED
    assert condition["reason"] == "evidence_flag_false"


def test_gate_rejects_incomplete_provenance() -> None:
    provenance = _complete_provenance()
    provenance["provenance_complete"] = False

    result = _evaluate_gate(_gate_metrics(), provenance=provenance)
    condition = _conditions(_decision(result))["complete_provenance"]

    assert result["eligible"] is False
    assert condition["status"] == CONDITION_FAILED
    assert condition["reason"] == "provenance_fields_missing"
