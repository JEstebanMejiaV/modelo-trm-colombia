from __future__ import annotations

from itertools import product

import pandas as pd
import pytest

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings, strategies as st  # noqa: E402, I001

from forecast_longterm.wavelet_optimization.config import (
    BASE_CANDIDATE_GRID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    load_research_plan,
)
from forecast_longterm.wavelet_optimization.evaluation import EvaluationBundle, OriginPrediction
from forecast_longterm.wavelet_optimization.metrics import (
    DM_INSUFFICIENT_OBSERVATIONS,
    EvaluationMetrics,
    ranked_candidate_ids,
)
from forecast_longterm.wavelet_optimization.publishing import (
    OutputPublisher,
    serialize_evaluation,
    serialize_predictions,
)


_CANDIDATE_IDS = tuple(candidate.candidate_id for candidate in BASE_CANDIDATE_GRID)
_GROUPS = tuple(product(REQUIRED_HORIZONS, REQUIRED_SPLITS))
_NON_SCOREABLE_STATUSES = (
    "not_scoreable_insufficient_training",
    "not_evaluable_label_not_mature",
    "not_scoreable_coverage_incomplete",
)


@st.composite
def _publication_scenario(
    draw: st.DrawFn,
) -> tuple[tuple[int, ...], tuple[bool, ...], tuple[str, ...], float, float, float]:
    """Genera ranking, exclusiones y métricas variadas para una publicación lógica."""

    winner_index = draw(st.integers(min_value=1, max_value=len(_CANDIDATE_IDS) - 1))
    remaining_indices = tuple(
        index for index in range(len(_CANDIDATE_IDS)) if index != winner_index
    )
    candidate_ranking = (
        winner_index,
        *draw(st.permutations(remaining_indices)),
    )
    group_has_scoreable = list(
        draw(
            st.lists(
                st.booleans(),
                min_size=len(_GROUPS),
                max_size=len(_GROUPS),
            )
        )
    )
    # The first group supports a non-trivial ranking; the second group proves
    # that a completely excluded group is still published with null metrics.
    group_has_scoreable[0] = True
    group_has_scoreable[1] = False
    excluded_statuses = tuple(
        draw(
            st.lists(
                st.sampled_from(_NON_SCOREABLE_STATUSES),
                min_size=len(_GROUPS),
                max_size=len(_GROUPS),
            )
        )
    )
    r2_base = draw(st.integers(min_value=200, max_value=800)) / 1000.0
    r2_step = draw(st.integers(min_value=1, max_value=20)) / 10_000.0
    mae_base = draw(st.integers(min_value=1, max_value=50)) / 100.0
    return (
        candidate_ranking,
        tuple(group_has_scoreable),
        excluded_statuses,
        r2_base,
        r2_step,
        mae_base,
    )


def _prediction(
    plan,
    *,
    origin: str,
    horizon: int,
    candidate_id: str,
    split: str,
    scoreable: bool,
    excluded_status: str,
    candidate_rank: int,
    group_index: int,
) -> OriginPrediction:
    label_end = "2020-07-01" if horizon == 6 else "2021-01-01"
    return OriginPrediction(
        origin_date=origin,
        horizon_months=horizon,
        candidate_id=candidate_id,
        prediction_wavelet=(candidate_rank + 1) / 10.0 + group_index / 1000.0
        if scoreable
        else None,
        prediction_random_walk=0.0 if scoreable else None,
        observed_forward_return=0.25 + candidate_rank / 100.0 if scoreable else None,
        label_end_date=label_end if scoreable else None,
        n_mature_labels=60 if scoreable else 59,
        scoreability_status="scoreable" if scoreable else excluded_status,
        coverage_status="complete" if scoreable else "incomplete",
        causal_reconstruction=scoreable,
        snapshot_manifest=("data/vintages/2020-01-01/manifest.json" if scoreable else None),
        source_vintage="vintage-1" if scoreable else None,
        split=split,
        prefix_last_date=origin if scoreable else None,
        prefix_length=100 if scoreable else None,
        prefix_sha256="a" * 64 if scoreable else None,
        warning=None if scoreable else excluded_status,
        data_cutoff=plan.data_cutoff,
        experiment_id=plan.experiment_id,
        product_id=plan.product_id,
    )


def _bundle_from_scenario(plan, scenario):
    (
        candidate_ranking,
        group_has_scoreable,
        excluded_statuses,
        r2_base,
        r2_step,
        mae_base,
    ) = scenario
    rank_by_index = {
        candidate_index: candidate_rank
        for candidate_rank, candidate_index in enumerate(candidate_ranking)
    }
    predictions: list[OriginPrediction] = []
    metrics: list[EvaluationMetrics] = []
    for group_index, (horizon, split) in enumerate(_GROUPS):
        has_scoreable = group_has_scoreable[group_index]
        excluded_status = excluded_statuses[group_index]
        for candidate_index in candidate_ranking:
            candidate_id = _CANDIDATE_IDS[candidate_index]
            candidate_rank = rank_by_index[candidate_index]
            predictions.append(
                _prediction(
                    plan,
                    origin="2020-01-01",
                    horizon=horizon,
                    candidate_id=candidate_id,
                    split=split,
                    scoreable=has_scoreable,
                    excluded_status=excluded_status,
                    candidate_rank=candidate_rank,
                    group_index=group_index,
                )
            )
            predictions.append(
                _prediction(
                    plan,
                    origin="2020-02-01",
                    horizon=horizon,
                    candidate_id=candidate_id,
                    split=split,
                    scoreable=False,
                    excluded_status=excluded_status,
                    candidate_rank=candidate_rank,
                    group_index=group_index,
                )
            )
            if has_scoreable:
                r2_oos = r2_base - candidate_rank * r2_step + group_index / 100_000.0
                metrics.append(
                    EvaluationMetrics(
                        candidate_id=candidate_id,
                        horizon_months=horizon,
                        split=split,
                        n_requested_origins=2,
                        n_scoreable_origins=1,
                        n_excluded_origins=1,
                        n_oos=1,
                        sse_model=1.0 - r2_oos,
                        sse_random_walk=1.0,
                        r2_oos=r2_oos,
                        mae_model=mae_base + candidate_rank / 1000.0,
                        mae_random_walk=1.0,
                        rmse_model=mae_base + candidate_rank / 1000.0,
                        rmse_random_walk=1.0,
                        direction_accuracy_model=0.5 + candidate_rank / 100.0,
                        direction_accuracy_random_walk=0.5,
                        dm_stat=None,
                        dm_p_value=None,
                        dm_status=DM_INSUFFICIENT_OBSERVATIONS,
                    )
                )
            else:
                metrics.append(
                    EvaluationMetrics(
                        candidate_id=candidate_id,
                        horizon_months=horizon,
                        split=split,
                        n_requested_origins=2,
                        n_scoreable_origins=0,
                        n_excluded_origins=2,
                        n_oos=0,
                        sse_model=None,
                        sse_random_walk=None,
                        r2_oos=None,
                        mae_model=None,
                        mae_random_walk=None,
                        rmse_model=None,
                        rmse_random_walk=None,
                        direction_accuracy_model=None,
                        direction_accuracy_random_walk=None,
                        dm_stat=None,
                        dm_p_value=None,
                        dm_status=DM_INSUFFICIENT_OBSERVATIONS,
                    )
                )
    return EvaluationBundle(
        predictions=tuple(predictions),
        metrics=tuple(metrics),
        plan=plan,
    )


# Feature: long-horizon-wavelet-optimization, Property 6: La publicación lógica conserva todos los candidatos evaluables
# Validates: Requirements 2.4
@settings(max_examples=10, deadline=None)
@given(scenario=_publication_scenario())
def test_logical_publication_retains_all_candidates_and_exclusions(scenario) -> None:
    plan = load_research_plan(
        data_cutoff="2026-04-01",
        origin_dates=("2020-01-01", "2020-02-01"),
    )
    bundle = _bundle_from_scenario(plan, scenario)
    permuted_bundle = EvaluationBundle(
        predictions=tuple(reversed(bundle.predictions)),
        metrics=tuple(reversed(bundle.metrics)),
        plan=plan,
    )

    published_predictions = serialize_predictions(
        bundle,
        plan,
        run_id="property-6-run",
    )
    permuted_predictions = serialize_predictions(
        permuted_bundle,
        plan,
        run_id="property-6-run",
    )
    published_evaluation = serialize_evaluation(
        bundle.metrics,
        plan,
        run_id="property-6-run",
    )
    permuted_evaluation = serialize_evaluation(
        permuted_bundle.metrics,
        plan,
        run_id="property-6-run",
    )
    pd.testing.assert_frame_equal(published_predictions, permuted_predictions)
    pd.testing.assert_frame_equal(published_evaluation, permuted_evaluation)

    expected_keys = {
        (candidate_id, horizon, split)
        for candidate_id in _CANDIDATE_IDS
        for horizon, split in _GROUPS
    }
    evaluation_keys = {
        (row.candidate_id, int(row.horizon_months), row.split)
        for row in published_evaluation.itertuples(index=False)
    }
    assert evaluation_keys == expected_keys
    assert len(published_evaluation) == len(expected_keys)

    ranking = ranked_candidate_ids(bundle.metrics, horizon_months=6, split="full")
    assert ranking[0] == _CANDIDATE_IDS[scenario[0][0]]
    assert ranking[0] != _CANDIDATE_IDS[0]
    assert set(ranking[1:]).issubset(
        {candidate_id for candidate_id, _horizon, _split in evaluation_keys}
    )

    for group_index, (horizon, split) in enumerate(_GROUPS):
        prediction_group = published_predictions.loc[
            (published_predictions["horizon_months"] == horizon)
            & (published_predictions["split"] == split)
        ]
        assert len(prediction_group) == 2 * len(_CANDIDATE_IDS)
        excluded = prediction_group[prediction_group["scoreability_status"] != "scoreable"]
        assert len(excluded) == len(_CANDIDATE_IDS) * (
            1 if scenario[1][group_index] else 2
        )
        assert excluded["prediction_wavelet"].isna().all()
        assert excluded["prediction_random_walk"].isna().all()
        assert excluded["observed_forward_return"].isna().all()

        evaluation_group = published_evaluation.loc[
            (published_evaluation["horizon_months"] == horizon)
            & (published_evaluation["split"] == split)
        ]
        if scenario[1][group_index]:
            assert set(evaluation_group["n_scoreable_origins"]) == {1}
            assert set(evaluation_group["n_excluded_origins"]) == {1}
            assert evaluation_group["r2_oos"].notna().all()
        else:
            assert set(evaluation_group["n_scoreable_origins"]) == {0}
            assert set(evaluation_group["n_excluded_origins"]) == {2}
            assert evaluation_group["r2_oos"].isna().all()
            assert evaluation_group["sse_model"].isna().all()

    gate = {
        "eligible": False,
        "eligibility_scope": "methodological_review",
        "candidate_decisions": [
            {
                "candidate_id": ranking[0],
                "eligible": False,
                "failed_conditions": ["property_fixture_gate"],
            }
        ],
    }
    documents = OutputPublisher(require_complete_provenance=False).build_documents(
        plan,
        bundle,
        {"run_id": "property-6-run", "experiment_id": plan.experiment_id},
        gate_decision=gate,
        metrics=bundle.metrics,
    )
    document_keys = {
        (row["candidate_id"], row["horizon_months"], row["split"])
        for row in documents.evaluation
    }
    assert document_keys == expected_keys
    assert len(documents.evaluation) == len(expected_keys)
    assert documents.decision["promotion_gate"]["eligible"] is False
    assert set(documents.decision["candidate_decisions"][0]) >= {
        "candidate_id",
        "eligible",
    }
