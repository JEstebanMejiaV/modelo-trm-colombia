from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip(
    "hypothesis",
    reason="Hypothesis is declared in the locked test dependencies but is not installed locally",
)
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st

from forecast_longterm.wavelet_optimization.snapshots import (  # noqa: E402
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    SnapshotResolver,
)
from trm_model.paths import ProjectPaths


@st.composite
def _origin_vintage_specs(draw: st.DrawFn) -> list[tuple[int, int]]:
    """Genera índices de origen únicos y desfases de disponibilidad válidos."""

    return draw(
        st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=240),
                st.integers(min_value=0, max_value=6),
            ),
            min_size=2,
            max_size=8,
            unique_by=lambda item: item[0],
        )
    )


def _write_snapshot(
    root: Path,
    origin_index: int,
    availability_lag: int,
) -> tuple[ForecastOrigin, dict[str, object]]:
    origin_date = pd.Timestamp("2000-01-01") + pd.DateOffset(months=origin_index)
    available_through = origin_date - pd.DateOffset(months=availability_lag)
    origin_text = origin_date.strftime("%Y-%m-%d")
    manifest_relative = f"data/vintages/{origin_text}/manifest.json"
    snapshot_dir = root / "data" / "vintages" / origin_text
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    value = 1000.0 + origin_index * 10.0 + availability_lag
    csv_text = (
        "date,banrep_trm_1\n"
        f"{available_through:%Y-%m-%d},{value:.6f}\n"
    )
    csv_bytes = csv_text.encode("utf-8")
    archived_path = snapshot_dir / "trm.csv"
    archived_path.write_bytes(csv_bytes)
    source_hash = hashlib.sha256(csv_bytes).hexdigest()
    vintage_id = f"vintage-origin-{origin_index}-lag-{availability_lag}"
    manifest = {
        "schema_version": 1,
        "origin_date": origin_text,
        "mode": "snapshot",
        "immutable": True,
        "files": [
            {
                "id": BANREP_TRM_SOURCE_ID,
                "raw_path": f"data/raw/fixture-{origin_index}.csv",
                "storage": "snapshot",
                "archived_path": f"data/vintages/{origin_text}/trm.csv",
                "bytes": len(csv_bytes),
                "sha256": source_hash,
                "vintage_id": vintage_id,
                "available_through": available_through.strftime("%Y-%m-%d"),
            }
        ],
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True),
        encoding="utf-8",
    )

    origin = ForecastOrigin(
        origin_date=origin_date,
        data_cutoff=origin_date,
        snapshot_manifest=manifest_relative,
    )
    expected = {
        "manifest": manifest_relative,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_hash": source_hash,
        "available_through": available_through,
        "vintage_id": vintage_id,
    }
    return origin, expected


# Feature: long-horizon-wavelet-optimization, Property 4: Resolución de vintage no cruza orígenes
# Validates: Requirements 5.2
@settings(max_examples=10, deadline=None)
@given(specs=_origin_vintage_specs())
def test_snapshot_resolution_keeps_each_origin_vintage_bound(
    specs: list[tuple[int, int]],
) -> None:
    with tempfile.TemporaryDirectory() as temporary_root:
        project_root = Path(temporary_root)
        expected_by_origin: dict[pd.Timestamp, dict[str, object]] = {}
        origins: list[ForecastOrigin] = []
        for origin_index, availability_lag in specs:
            origin, expected = _write_snapshot(
                project_root,
                origin_index,
                availability_lag,
            )
            origins.append(origin)
            expected_by_origin[origin.origin_date] = expected

        resolver = SnapshotResolver(paths=ProjectPaths.from_root(project_root))
        all_vintage_ids = {item["vintage_id"] for item in expected_by_origin.values()}
        all_manifest_paths = {item["manifest"] for item in expected_by_origin.values()}
        all_source_hashes = {item["source_hash"] for item in expected_by_origin.values()}

        for origin in origins:
            resolved = resolver.resolve(
                origin,
                required_source_ids=(BANREP_TRM_SOURCE_ID,),
            )
            expected = expected_by_origin[origin.origin_date]
            vintage = resolved.source(BANREP_TRM_SOURCE_ID)

            assert resolved.valid
            assert resolved.origin == origin
            assert resolved.snapshot_manifest == expected["manifest"]
            assert resolved.manifest_sha256 == expected["manifest_sha256"]
            assert vintage.source_id == BANREP_TRM_SOURCE_ID
            assert vintage.snapshot_manifest == expected["manifest"]
            assert vintage.vintage_id == expected["vintage_id"]
            assert vintage.sha256 == expected["source_hash"]
            assert vintage.available_through == expected["available_through"]

            # Ninguna identidad de otra carpeta/origen puede satisfacer esta consulta.
            assert vintage.vintage_id in all_vintage_ids
            assert vintage.snapshot_manifest in all_manifest_paths
            assert vintage.sha256 in all_source_hashes
            assert vintage.vintage_id == expected["vintage_id"]
            assert vintage.snapshot_manifest == expected["manifest"]
            assert vintage.sha256 == expected["source_hash"]
