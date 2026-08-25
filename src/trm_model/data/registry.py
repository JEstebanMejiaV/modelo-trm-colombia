"""Registro canónico de fuentes y snapshots raw."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..paths import ProjectPaths, project_paths


MONTHLY_MODEL_INPUT_PATHS = frozenset(
    {
        "data/raw/trm_diaria_banrep.json",
        "data/raw/tasa_politica_diaria_banrep.json",
        "data/raw/fed_funds_mensual_fred.csv",
        "data/raw/dolar_amplio_diario_fred.csv",
        "data/raw/vix_diario_fred.csv",
        "data/raw/remesas_mensuales_banrep.json",
        "data/raw/series_15360_15368.json",
        "data/raw/reservas_netas_sin_flar_banrep.json",
        "data/raw/tes_5y_pesos_banrep.json",
        "data/raw/tes_5y_uvr_banrep.json",
        "data/raw/bei_5y_eeuu_diario_fed.csv",
        "data/raw/embig_colombia_diario_bcrp.json",
        "data/raw/balanza_comercial_cambiaria_banrep.json",
        "data/raw/flujos_capital_totales_banrep.json",
        "data/raw/brl_usd_mensual_fred.csv",
        "data/raw/clp_usd_mensual_fred.csv",
        "data/raw/mxn_usd_mensual_fred.csv",
        "data/raw/pen_usd_mensual_bcrp.json",
        "data/raw/ipc_colombia_banrep.json",
        "data/raw/ise_dane_12actividades_jun2026.xlsx",
        "data/raw/geih_dane_jun2026.xlsx",
        "data/raw/geih_dane_desestacionalizado_jun2026.xlsx",
        "data/raw/ipi_dane_jun2026.xlsx",
        "data/raw/ipp_dane_jul2026.xlsx",
        "data/raw/balance_fiscal_gnc_mensual_trimestral.xlsx",
        "data/base_global_mensual.csv",
    }
)


@dataclass(frozen=True)
class SourceRegistry:
    path: Path
    payload: dict[str, Any]

    @property
    def sources(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.payload.get("sources", ()))

    @property
    def active_sources(self) -> tuple[dict[str, Any], ...]:
        return tuple(source for source in self.sources if source.get("status") == "active")

    def raw_paths(self, *, active_only: bool = True, root: Path | None = None) -> tuple[Path, ...]:
        base = (root or self.path.parents[2]).resolve()
        selected = self.active_sources if active_only else self.sources
        return tuple((base / source["raw_path"]).resolve() for source in selected)

    def source_ids(self) -> tuple[str, ...]:
        return tuple(str(source["source_id"]) for source in self.sources)

    def validate_unique_ids(self) -> None:
        ids = self.source_ids()
        duplicates = sorted({source_id for source_id in ids if ids.count(source_id) > 1})
        if duplicates:
            raise ValueError(f"source_id duplicados en {self.path}: {duplicates}")

    def missing_raw_files(self, *, root: Path | None = None) -> list[Path]:
        return [path for path in self.raw_paths(root=root) if not path.is_file()]

    def missing_monthly_model_inputs(self) -> list[str]:
        registered = {
            str(source["raw_path"])
            for source in self.active_sources
        }
        return sorted(MONTHLY_MODEL_INPUT_PATHS - registered)


def load_source_registry(
    path: Path | None = None,
    *,
    paths: ProjectPaths | None = None,
    validate_contract: bool = True,
) -> SourceRegistry:
    """Carga y valida el registro canónico de fuentes."""
    project = paths or project_paths()
    registry_path = (path or project.source_registry()).resolve()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"El registro de fuentes debe ser un objeto JSON: {registry_path}")
    registry = SourceRegistry(path=registry_path, payload=payload)
    registry.validate_unique_ids()
    if validate_contract:
        from ..validation.contracts import validate_document

        validate_document(payload, project.schema("source_registry.json"))
    return registry
