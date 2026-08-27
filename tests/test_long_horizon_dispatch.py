from __future__ import annotations

from pathlib import Path

import pytest

import pipelines.long_horizon as long_horizon
from forecast_longterm import wavelet_optimization as wavelet_variant
from trm_model import cli
from trm_model.experiments.registry import research_experiment_id
from trm_model.provenance import ProductRun


def test_wavelet_optimization_dispatch_forwards_pit_contract_without_product_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    expected = object()

    def fake_runner(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    def fail_product_wrapper(*_args: object, **_kwargs: object) -> None:
        pytest.fail("wavelet_optimization no debe envolverse en ProductRun")

    monkeypatch.setattr(wavelet_variant, "run_wavelet_optimization", fake_runner)
    monkeypatch.setattr(long_horizon, "run_product", fail_product_wrapper)

    resolver = object()
    store = object()
    result = long_horizon.run(
        "wavelet_optimization",
        paths=tmp_path,
        data_cutoff="2026-04-01",
        origin_dates=("2020-01-01", "2021-01-01"),
        config_path="fixtures/variant.toml",
        schema_path="fixtures/variant.json",
        snapshot_resolver=resolver,
        series_store=store,
    )

    assert result is expected
    assert captured == {
        "paths": tmp_path,
        "config_path": "fixtures/variant.toml",
        "schema_path": "fixtures/variant.json",
        "data_cutoff": "2026-04-01",
        "origin_dates": ("2020-01-01", "2021-01-01"),
        "snapshot_resolver": resolver,
        "series_store": store,
    }
    assert long_horizon.WAVELET_OPTIMIZATION_EXPERIMENT_ID == (
        "long_horizon_research.wavelet_optimization.v1"
    )


def test_wavelet_optimization_requires_explicit_cutoff_and_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_runner(**_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(wavelet_variant, "run_wavelet_optimization", fake_runner)

    with pytest.raises(ValueError, match="Data_Cutoff explícito"):
        long_horizon.run("wavelet_optimization", origin_dates=("2020-01-01",))
    with pytest.raises(ValueError, match="Forecast_Origin explícito"):
        long_horizon.run("wavelet_optimization", data_cutoff="2026-04-01")

    assert called is False


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


def test_cli_dispatch_passes_variant_arguments_only_for_wavelet_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(long_horizon, "run", fake_run)

    assert cli.main(
        [
            "run-research",
            "--module",
            "wavelet_optimization",
            "--data-cutoff",
            "2026-04-01",
            "--forecast-origin",
            "2020-01-01",
            "--origin-date",
            "2021-01-01",
            "--config-path",
            "fixtures/variant.toml",
            "--schema-path",
            "fixtures/variant.json",
        ]
    ) == 0
    assert cli.main(["run-research", "--module", "wavelets"]) == 0

    assert calls == [
        (
            ("wavelet_optimization",),
            {
                "data_cutoff": "2026-04-01",
                "origin_dates": ["2020-01-01", "2021-01-01"],
                "config_path": "fixtures/variant.toml",
                "schema_path": "fixtures/variant.json",
            },
        ),
        (("wavelets",), {}),
    ]


def test_run_all_keeps_wavelet_variant_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[str] = []
    monkeypatch.setattr(
        long_horizon,
        "run",
        lambda module_name: executed.append(module_name),
    )

    long_horizon.run_all()

    assert long_horizon.WAVELET_OPTIMIZATION_MODULE in long_horizon.ALLOWED_MODULES
    assert long_horizon.WAVELET_OPTIMIZATION_MODULE not in executed
    assert set(executed) == set(long_horizon.LEGACY_MODULES)
