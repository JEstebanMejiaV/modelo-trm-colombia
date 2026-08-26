from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from forecast_longterm.wavelet_optimization.snapshots import (
    BANREP_TRM_SOURCE_ID,
    CoverageLedger,
    ForecastOrigin,
    PointInTimeSeriesStore,
    SnapshotResolutionError,
    SnapshotResolver,
)
from trm_model.paths import ProjectPaths

DEFAULT_ROWS: tuple[tuple[str, float], ...] = (
    ("2020-01-03", 100.0),
    ("2020-01-31", 110.0),
    ("2020-03-15", 130.0),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_snapshot(
    tmp_path: Path,
    *,
    origin_date: str = "2020-03-31",
    data_cutoff: str | None = None,
    rows: tuple[tuple[str, float], ...] = DEFAULT_ROWS,
    source_id: str = BANREP_TRM_SOURCE_ID,
    source_format: str = "csv",
    mode: str = "snapshot",
    archived_location: str = "snapshot",
    available_through: str | None = None,
) -> tuple[ProjectPaths, ForecastOrigin, Path, Path]:
    """Create a minimal manifest and archived source under an isolated project."""

    paths = ProjectPaths.from_root(tmp_path)
    snapshot_dir = paths.vintages / origin_date
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    suffix = ".json" if source_format == "json" else ".csv"
    if archived_location == "snapshot":
        archived_file = snapshot_dir / f"trm{suffix}"
    elif archived_location == "raw":
        archived_file = paths.raw / f"trm{suffix}"
    elif archived_location == "outside":
        archived_file = paths.root / "outside" / f"trm{suffix}"
    else:
        raise ValueError(f"Unsupported archived_location: {archived_location}")
    archived_file.parent.mkdir(parents=True, exist_ok=True)

    if source_format == "json":
        archived_file.write_text(json.dumps(list(rows)), encoding="utf-8")
    elif source_format == "csv":
        pd.DataFrame({"date": [date for date, _ in rows], source_id: [value for _, value in rows]}).to_csv(
            archived_file, index=False
        )
    else:
        raise ValueError(f"Unsupported source_format: {source_format}")

    archived_path = paths.relative(archived_file)
    observed_through = max(pd.Timestamp(date) for date, _ in rows).strftime("%Y-%m-%d")
    manifest = {
        "schema_version": 1,
        "origin_date": origin_date,
        "mode": mode,
        "immutable": True,
        "files": [
            {
                "id": source_id,
                "raw_path": f"data/raw/{source_id}.csv",
                "storage": "snapshot",
                "archived_path": archived_path,
                "vintage_id": f"vintage-{origin_date}",
                "available_through": available_through or observed_through,
                "bytes": archived_file.stat().st_size,
                "sha256": _sha256(archived_file),
            }
        ],
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    origin = ForecastOrigin(
        origin_date=pd.Timestamp(origin_date),
        data_cutoff=pd.Timestamp(data_cutoff or origin_date),
    )
    return paths, origin, manifest_path, archived_file


def _assert_rejected_with_coverage(
    paths: ProjectPaths,
    origin: ForecastOrigin,
    *,
    coverage_status: str,
    scoreability_status: str,
    reason: str,
    source_id: str = BANREP_TRM_SOURCE_ID,
) -> None:
    ledger = CoverageLedger(default_horizons=(6, 12))
    resolver = SnapshotResolver(paths, coverage_ledger=ledger)

    with pytest.raises(SnapshotResolutionError) as raised:
        resolver.resolve(origin)

    error = raised.value
    assert error.coverage_status == coverage_status
    assert error.scoreability_status == scoreability_status
    assert error.reason == reason
    assert error.source_id in {None, source_id}

    for horizon in (6, 12):
        record = ledger.get(source_id, origin, horizon)
        assert record is not None
        assert record.coverage_status == coverage_status
        assert record.scoreability_status == scoreability_status
        assert record.reason == reason
        assert "r2_oos" not in record.as_dict()


def test_snapshot_mode_baseline_is_rejected_and_coverage_state_is_preserved(
    tmp_path: Path,
) -> None:
    paths, origin, _manifest_path, _archived_file = _write_snapshot(
        tmp_path, mode="baseline"
    )

    _assert_rejected_with_coverage(
        paths,
        origin,
        coverage_status="invalid",
        scoreability_status="not_scoreable_snapshot_invalid",
        reason="snapshot_mode_not_snapshot",
    )


def test_missing_manifest_is_not_replaced_by_a_fallback(tmp_path: Path) -> None:
    paths = ProjectPaths.from_root(tmp_path)
    origin_date = "2020-03-31"
    (paths.vintages / origin_date).mkdir(parents=True)
    origin = ForecastOrigin(origin_date=pd.Timestamp(origin_date))

    _assert_rejected_with_coverage(
        paths,
        origin,
        coverage_status="missing",
        scoreability_status="not_scoreable_snapshot_missing",
        reason="snapshot_manifest_missing",
    )


@pytest.mark.parametrize("tampered_field", ["sha256", "bytes"])
def test_invalid_archived_hash_or_bytes_is_rejected(
    tmp_path: Path,
    tampered_field: str,
) -> None:
    paths, origin, manifest_path, _archived_file = _write_snapshot(tmp_path)
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["files"][0]
    if tampered_field == "sha256":
        original = str(record["sha256"])
        record["sha256"] = ("0" if original[0] != "0" else "1") + original[1:]
    else:
        record["bytes"] = int(record["bytes"]) + 1
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _assert_rejected_with_coverage(
        paths,
        origin,
        coverage_status="invalid",
        scoreability_status="not_scoreable_snapshot_invalid",
        reason="archived_hash_mismatch",
    )


def test_required_banrep_source_missing_is_not_filled_from_raw_or_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, origin, _manifest_path, archived_file = _write_snapshot(
        tmp_path, source_id="another_source"
    )
    raw_file = paths.raw / f"{BANREP_TRM_SOURCE_ID}.csv"
    historical_file = paths.results / "pronostico" / "wavelets_componentes.csv"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    historical_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(
        "date,banrep_trm_1\n2020-01-01,999.0\n", encoding="utf-8"
    )
    historical_file.write_text(
        "date,banrep_trm_1\n2020-01-01,888.0\n", encoding="utf-8"
    )

    read_paths: list[Path] = []
    original_read_csv = pd.read_csv

    def tracking_read_csv(filepath_or_buffer, *args, **kwargs):
        if isinstance(filepath_or_buffer, (str, Path)):
            read_paths.append(Path(filepath_or_buffer).resolve())
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", tracking_read_csv)
    _assert_rejected_with_coverage(
        paths,
        origin,
        coverage_status="missing",
        scoreability_status="not_scoreable_source_missing",
        reason="source_vintage_missing",
    )

    assert read_paths == []
    assert archived_file.exists()
    assert raw_file.exists()
    assert historical_file.exists()


@pytest.mark.parametrize("archived_location", ["outside", "raw"])
def test_archived_path_locations_are_parameterized(
    tmp_path: Path,
    archived_location: str,
) -> None:
    """Keep the two forbidden path forms explicit in the integration suite."""

    paths, origin, _manifest_path, archived_file = _write_snapshot(
        tmp_path, archived_location=archived_location
    )
    assert archived_file.exists()
    _assert_rejected_with_coverage(
        paths,
        origin,
        coverage_status="invalid",
        scoreability_status="not_scoreable_snapshot_invalid",
        reason="archived_path_outside_snapshot",
    )


def test_observation_after_origin_or_cutoff_is_incomplete_not_scoreable(
    tmp_path: Path,
) -> None:
    paths, origin, _manifest_path, _archived_file = _write_snapshot(
        tmp_path,
        origin_date="2020-02-29",
        data_cutoff="2020-02-01",
        rows=(("2020-01-15", 100.0), ("2020-02-02", 101.0)),
        available_through="2020-02-01",
    )

    _assert_rejected_with_coverage(
        paths,
        origin,
        coverage_status="incomplete",
        scoreability_status="not_scoreable_coverage_incomplete",
        reason="observation_after_origin_or_cutoff",
    )


def test_store_reads_json_snapshot_using_only_archived_file(tmp_path: Path) -> None:
    paths, origin, _manifest_path, archived_file = _write_snapshot(
        tmp_path,
        source_format="json",
        rows=(("2020-01-03", 100.0), ("2020-01-31", 110.0)),
    )
    ledger = CoverageLedger(default_horizons=(6, 12))
    snapshot = SnapshotResolver(paths, coverage_ledger=ledger).resolve(origin)

    series = PointInTimeSeriesStore(paths, coverage_ledger=ledger).monthly_series(
        snapshot,
        through=origin.origin_date,
    )

    assert archived_file == paths.root / snapshot.source(BANREP_TRM_SOURCE_ID).archived_path
    assert series.index.tolist() == [pd.Timestamp("2020-01-01")]
    assert series.iloc[0] == pytest.approx(105.0)
    assert ledger.get(BANREP_TRM_SOURCE_ID, origin, 6).coverage_status == "complete"
    assert ledger.get(BANREP_TRM_SOURCE_ID, origin, 6).scoreability_status == "scoreable"


def test_store_monthlyizes_ms_without_imputation_and_ignores_raw_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths, origin, _manifest_path, archived_file = _write_snapshot(tmp_path)
    raw_file = paths.raw / f"{BANREP_TRM_SOURCE_ID}.csv"
    historical_file = paths.results / "pronostico" / "wavelets_comparacion_bandas.csv"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    historical_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(
        "date,banrep_trm_1\n2020-01-01,9999.0\n", encoding="utf-8"
    )
    historical_file.write_text(
        "date,banrep_trm_1\n2020-01-01,8888.0\n", encoding="utf-8"
    )

    read_paths: list[Path] = []
    original_read_csv = pd.read_csv

    def tracking_read_csv(filepath_or_buffer, *args, **kwargs):
        if isinstance(filepath_or_buffer, (str, Path)):
            read_paths.append(Path(filepath_or_buffer).resolve())
        return original_read_csv(filepath_or_buffer, *args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", tracking_read_csv)
    ledger = CoverageLedger(default_horizons=(6, 12))
    snapshot = SnapshotResolver(paths, coverage_ledger=ledger).resolve(origin)
    store = PointInTimeSeriesStore(paths, coverage_ledger=ledger)
    series = store.monthly_series(snapshot, through=origin.origin_date)
    coverage = store.register_monthly_coverage(
        snapshot,
        horizon_months=6,
        through=origin.origin_date,
    )

    assert set(read_paths) == {archived_file.resolve()}
    assert raw_file.resolve() not in read_paths
    assert historical_file.resolve() not in read_paths
    assert series.loc[pd.Timestamp("2020-01-01")] == pytest.approx(105.0)
    assert pd.isna(series.loc[pd.Timestamp("2020-02-01")])
    assert series.loc[pd.Timestamp("2020-03-01")] == pytest.approx(130.0)
    assert coverage.coverage_status == "incomplete"
    assert coverage.scoreability_status == "not_scoreable_coverage_incomplete"
    assert coverage.n_missing == 1
    assert coverage.reason == "missing_months_without_imputation"
    assert ledger.get(BANREP_TRM_SOURCE_ID, origin, 6).coverage_status == "incomplete"
    assert ledger.get(BANREP_TRM_SOURCE_ID, origin, 6).scoreability_status == (
        "not_scoreable_coverage_incomplete"
    )
    # The other horizon retains its resolver-level complete state; coverage is
    # keyed by horizon and never becomes a predictive metric.
    assert ledger.get(BANREP_TRM_SOURCE_ID, origin, 12).coverage_status == "complete"
    assert "r2_oos" not in coverage.as_dict()
