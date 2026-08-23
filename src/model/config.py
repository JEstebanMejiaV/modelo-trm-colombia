from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
DATA = ROOT / "data"
SAMPLE_START = pd.Timestamp("2006-01-01")
SAMPLE_END = pd.Timestamp("2026-04-01")
SHAPLEY_BOOTSTRAP_REPLICATIONS = 200
SHAPLEY_BOOTSTRAP_BLOCK_MONTHS = 12
SHAPLEY_BOOTSTRAP_PERMUTATIONS = 64
SHAPLEY_BOOTSTRAP_SEED = 20260823

MONTH_NUMBERS_ES = {
    "Ene": 1,
    "Feb": 2,
    "Mar": 3,
    "Abr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Ago": 8,
    "Sep": 9,
    "Set": 9,
    "Oct": 10,
    "Nov": 11,
    "Dic": 12,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


ECM_LEVEL_VARIABLES = [
    "ln_terminos_intercambio",
    "ln_remesas_12m",
    "diferencial_tasas_pp",
    "deficit_fiscal_12m_pct_pib",
    "ln_dolar_amplio",
]


# Cada factor es un jugador de la descomposicion Shapley. Todos sus terminos
# (transformaciones y rezagos) entran o salen juntos al calcular el R2 marginal.
BASE_FACTOR_SPECS = {
    "Términos de intercambio": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.ln_terminos_intercambio", 0)],
    },
    "Remesas": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.ln_remesas_12m", 1)],
    },
    "Diferencial de tasas": {
        "grupo": "Política doméstica",
        "terminos": [("D.diferencial_tasas_pp", 1)],
    },
    "Déficit fiscal": {
        "grupo": "Política doméstica",
        "terminos": [("D.deficit_fiscal_12m_pct_pib", 1)],
    },
    "Dólar amplio": {
        "grupo": "Global",
        "terminos": [("D.ln_dolar_amplio", 0)],
    },
    "VIX": {
        "grupo": "Global",
        "terminos": [("D.ln_vix", 0)],
    },
}


def expanded_factor_specs(regional_component: str) -> dict[str, dict[str, object]]:
    return {
    **BASE_FACTOR_SPECS,
    "Riesgo soberano EMBIG Colombia": {
        "grupo": "Riesgo local",
        # Contemporaneo: esta version es contabilidad historica/nowcast, no causal.
        "terminos": [("D.embig_colombia_pp", 0)],
    },
    "Reservas internacionales": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.ln_reservas_netas_sin_flar", 1)],
    },
    "Balanza comercial cambiaria": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.asinh_balanza_comercial", 1)],
    },
    "Flujos netos de capital": {
        "grupo": "Sector externo Colombia",
        "terminos": [("D.asinh_flujos_capital", 1)],
    },
    "Diferencial de compensación inflacionaria 5 años": {
        "grupo": "Política doméstica",
        "terminos": [("D.diferencial_bei_5y_pp", 1)],
    },
    "Monedas regionales": {
        "grupo": "Regional",
        "terminos": [(regional_component, 0)],
    },
}


EXPANDED_FACTOR_SPECS_3 = expanded_factor_specs("factor_monedas_regionales_3")
EXPANDED_FACTOR_SPECS_4 = expanded_factor_specs("factor_monedas_regionales_4")
EXPANDED_FACTOR_SPECS = EXPANDED_FACTOR_SPECS_4


def forecast_factor_specs(regional_component: str) -> dict[str, dict[str, object]]:
    """Especificación ex ante: ninguna variable del mes objetivo entra contemporánea."""
    return {
        "Términos de intercambio": {
            "grupo": "Sector externo Colombia",
            "terminos": [("D.ln_terminos_intercambio", 3)],
        },
        "Remesas": {
            "grupo": "Sector externo Colombia",
            "terminos": [("D.ln_remesas_12m", 2)],
        },
        "Diferencial de tasas": {
            "grupo": "Política doméstica",
            "terminos": [("D.diferencial_tasas_pp", 1)],
        },
        "Déficit fiscal": {
            "grupo": "Política doméstica",
            "terminos": [("D.deficit_fiscal_12m_pct_pib", 3)],
        },
        "Dólar amplio": {
            "grupo": "Global",
            "terminos": [("D.ln_dolar_amplio", 1)],
        },
        "VIX": {
            "grupo": "Global",
            "terminos": [("D.ln_vix", 1)],
        },
        "Riesgo soberano EMBIG Colombia": {
            "grupo": "Riesgo local",
            "terminos": [("D.embig_colombia_pp", 1)],
        },
        "Reservas internacionales": {
            "grupo": "Sector externo Colombia",
            "terminos": [("D.ln_reservas_netas_sin_flar", 2)],
        },
        "Balanza comercial cambiaria": {
            "grupo": "Sector externo Colombia",
            "terminos": [("D.asinh_balanza_comercial", 2)],
        },
        "Flujos netos de capital": {
            "grupo": "Sector externo Colombia",
            "terminos": [("D.asinh_flujos_capital", 2)],
        },
        "Diferencial de compensación inflacionaria 5 años": {
            "grupo": "Política doméstica",
            "terminos": [("D.diferencial_bei_5y_pp", 1)],
        },
        "Monedas regionales": {
            "grupo": "Regional",
            "terminos": [(regional_component, 1)],
        },
    }


FORECAST_FACTOR_SPECS_3 = forecast_factor_specs("factor_monedas_regionales_3")
FORECAST_FACTOR_SPECS_4 = forecast_factor_specs("factor_monedas_regionales_4")


FORECAST_AVAILABILITY = [
    ("Términos de intercambio", 3, "Mensual; publicación aproximada t+2", "Último cambio utilizable al inicio de t: t-3"),
    ("Remesas", 2, "Mensual; publicación posterior al mes de referencia", "Supuesto conservador: t-2"),
    ("Diferencial de tasas", 1, "Tasas observables durante el mes", "Promedios completos conocidos para t-1"),
    ("Déficit fiscal", 3, "Mensual con rezago y posibles revisiones", "Supuesto conservador: t-3"),
    ("Dólar amplio", 1, "Diaria", "Promedio completo conocido para t-1"),
    ("VIX", 1, "Diaria", "Promedio completo conocido para t-1"),
    ("Riesgo soberano EMBIG Colombia", 1, "Diaria", "Promedio completo conocido para t-1"),
    ("Reservas internacionales", 2, "Mensual; publicación posterior al cierre", "Supuesto conservador: t-2"),
    ("Balanza comercial cambiaria", 2, "Mensual; publicación posterior al cierre", "Supuesto conservador: t-2"),
    ("Flujos netos de capital", 2, "Mensual; publicación posterior al cierre", "Supuesto conservador: t-2"),
    ("Diferencial de compensación inflacionaria 5 años", 1, "Curvas diarias", "Promedios completos conocidos para t-1"),
    ("Monedas regionales", 1, "Tipos de cambio mensuales", "Promedios completos conocidos para t-1"),
]


DIFFERENCED_COMPONENTS = [
    "ln_terminos_intercambio",
    "ln_remesas_12m",
    "diferencial_tasas_pp",
    "deficit_fiscal_12m_pct_pib",
    "ln_dolar_amplio",
    "ln_vix",
    "embig_colombia_pp",
    "ln_reservas_netas_sin_flar",
    "asinh_balanza_comercial",
    "asinh_flujos_capital",
    "diferencial_bei_5y_pp",
    "diferencial_bei_5y_comun_pp",
]


LEVEL_COMPONENTS = [
    "diferencial_bei_5y_pp",
    "diferencial_bei_5y_comun_pp",
    "factor_monedas_regionales_3",
    "factor_monedas_regionales_4",
]


@dataclass
class SelectedModel:
    p: int
    q: int
    result: object


@dataclass
class SelectedDifferenceModel:
    p: int
    q: int
    result: object
    y: pd.Series
    x: pd.DataFrame
