from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st

from forecast_longterm.wavelet_optimization.config import (
    PlanMutationError,
    PreRegistrationGuard,
    load_research_plan,
)


@st.composite
def _mutation_values(draw: st.DrawFn) -> dict[str, int]:
    token = draw(st.integers(min_value=0, max_value=10**9))
    horizon = draw(
        st.integers(min_value=1, max_value=60).filter(
            lambda value: value not in (6, 12)
        )
    )
    levels = draw(
        st.integers(min_value=1, max_value=10).filter(lambda value: value != 5)
    )
    signal_scale = draw(
        st.integers(min_value=0, max_value=200).filter(lambda value: value != 100)
    )
    return {
        "token": token,
        "horizon": horizon,
        "levels": levels,
        "signal_scale": signal_scale,
    }


def _mutations(plan, values: dict[str, int]) -> tuple[tuple[str, str, object], ...]:
    original_candidate = plan.candidates[0]
    token = values["token"]
    changed_candidate = replace(
        original_candidate,
        candidate_id=f"mutated_candidate_{token}",
    )
    changed_components = replace(original_candidate, components=("D2",))
    changed_wavelet = replace(original_candidate, wavelet_family=f"wavelet_{token}")
    changed_levels = replace(original_candidate, levels=values["levels"])
    changed_boundary = replace(original_candidate, boundary_mode=f"boundary_{token}")
    changed_signal_scale = replace(
        original_candidate,
        signal_scale=float(values["signal_scale"]),
    )

    def with_first_candidate(candidate) -> tuple:
        return (candidate, *plan.candidates[1:])

    return (
        ("candidate_id", "candidates", with_first_candidate(changed_candidate)),
        ("candidate_components", "candidates", with_first_candidate(changed_components)),
        ("horizon", "horizons", (values["horizon"], 12)),
        (
            "split",
            "splits",
            ("full", "2008_2019", "2020_2022", f"mutated_split_{token}"),
        ),
        ("primary_metric", "primary_metric", f"metric_{token}"),
        ("selection_rule", "selection_rule", f"selection_{token}"),
        ("tie_break_rule", "tie_break_rule", f"tie_break_{token}"),
        ("wavelet_family", "candidates", with_first_candidate(changed_wavelet)),
        ("dwt_levels", "candidates", with_first_candidate(changed_levels)),
        ("boundary_mode", "candidates", with_first_candidate(changed_boundary)),
        ("signal_scale", "candidates", with_first_candidate(changed_signal_scale)),
    )


# Feature: long-horizon-wavelet-optimization, Property 1: Plan preinscrito inmutable después de la primera predicción
# Validates: Requirements 1.3, 2.5
@settings(max_examples=10, deadline=None)
@given(values=_mutation_values())
def test_preregistered_plan_mutation_after_first_prediction_is_rejected(
    values: dict[str, int],
) -> None:
    plan = load_research_plan(
        data_cutoff="2026-04-01",
        origin_dates=("2020-01-01", "2023-01-01"),
    )

    for _field_name, field, changed_value in _mutations(plan, values):
        candidate_plan = replace(plan)
        guard = PreRegistrationGuard(candidate_plan)
        guard.first_prediction()

        prediction_calls: list[object] = []

        def guarded_prediction(plan_to_evaluate):
            guard.assert_unchanged(plan_to_evaluate)
            prediction_calls.append(plan_to_evaluate)
            return "prediction"

        assert guarded_prediction(candidate_plan) == "prediction"
        calls_before_mutation = len(prediction_calls)

        # ResearchPlan es frozen; esto simula una mutación externa tras el registro.
        object.__setattr__(candidate_plan, field, changed_value)

        with pytest.raises(PlanMutationError):
            guarded_prediction(candidate_plan)
        assert len(prediction_calls) == calls_before_mutation
