from __future__ import annotations

import pytest

import pipelines.long_horizon as long_horizon
from trm_model.experiments.registry import research_experiment_id
from trm_model.provenance import ProductRun


def test_legacy_wavelets_keep_product_run_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[ProductRun] = []
    executed: list[str] = []

    def fake_product_wrapper(spec: ProductRun) -> None:
        received.append(spec)
        spec.runner()

    monkeypatch.setattr(long_horizon, "run_product", fake_product_wrapper)
    monkeypatch.setattr(
        long_horizon,
        "_run_module",
        lambda module_name: executed.append(module_name),
    )

    assert long_horizon.run("wavelets") is None
    assert executed == ["wavelets"]
    assert len(received) == 1
    assert received[0].product_id == "long_horizon_research"
    assert received[0].experiment_id == research_experiment_id("wavelets")
