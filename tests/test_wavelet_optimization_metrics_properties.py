from __future__ import annotations

import pytest

from forecast_longterm.wavelet_optimization.metrics import (
    EvaluationMetrics,
    ranked_candidate_ids,
)

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings, strategies as st  # noqa: E402, I001


_R2_VALUES = (-1.0, -0.25, 0.0, 0.5, 1.0)
_MAE_VALUES = (0.1, 1.0, 10.0, 100.0)


def _metric(candidate_id: str, r2_oos: float, mae_model: float) -> EvaluationMetrics:
    return EvaluationMetrics(
        candidate_id=candidate_id,
        horizon_months=6,
        split="full",
        n_requested_origins=1,
        n_scoreable_origins=1,
        n_excluded_origins=0,
        n_oos=1,
        sse_model=100.0 * (1.0 - r2_oos),
        sse_random_walk=100.0,
        r2_oos=r2_oos,
        mae_model=mae_model,
        mae_random_walk=mae_model + 1.0,
        rmse_model=mae_model,
        rmse_random_walk=mae_model + 1.0,
        direction_accuracy_model=0.5,
        direction_accuracy_random_walk=0.5,
        dm_stat=None,
        dm_p_value=None,
        dm_status="insufficient_observations",
    )


@st.composite
def _metric_table_and_permutation(
    draw: st.DrawFn,
) -> tuple[tuple[EvaluationMetrics, ...], tuple[EvaluationMetrics, ...]]:
    candidate_count = draw(st.integers(min_value=4, max_value=12))
    r2_order = draw(st.permutations(_R2_VALUES))
    mae_order = draw(st.permutations(_MAE_VALUES))

    primary_r2, secondary_r2 = r2_order[:2]
    mae_low, mae_high = sorted(mae_order[:2])
    tied_mae = mae_order[2]
    scores = [
        (primary_r2, mae_high),
        (primary_r2, mae_low),
        (secondary_r2, tied_mae),
        (secondary_r2, tied_mae),
    ]
    extra_count = candidate_count - len(scores)
    extra_scores = draw(
        st.lists(
            st.tuples(
                st.sampled_from(_R2_VALUES),
                st.sampled_from(_MAE_VALUES),
            ),
            min_size=extra_count,
            max_size=extra_count,
        )
    )
    scores.extend(extra_scores)

    table = tuple(
        _metric(f"candidate_{index:02d}", r2_oos, mae_model)
        for index, (r2_oos, mae_model) in enumerate(scores)
    )
    permutation = tuple(draw(st.permutations(table)))
    return table, permutation


# Feature: long-horizon-wavelet-optimization, Property 9: Selección y desempate son deterministas
# Validates: Requirements 6.3
@settings(max_examples=10, deadline=None)
@given(case=_metric_table_and_permutation())
def test_metric_ranking_is_deterministic_under_row_permutations(
    case: tuple[tuple[EvaluationMetrics, ...], tuple[EvaluationMetrics, ...]],
) -> None:
    table, permutation = case
    expected = tuple(
        metric.candidate_id
        for metric in sorted(
            table,
            key=lambda metric: (
                -float(metric.r2_oos),
                float(metric.mae_model),
                metric.candidate_id,
            ),
        )
    )

    ranking = ranked_candidate_ids(table)
    permuted_ranking = ranked_candidate_ids(permutation)

    assert ranking == expected
    assert permuted_ranking == expected
    assert len(ranking) == len(table)
    assert set(ranking) == {metric.candidate_id for metric in table}
