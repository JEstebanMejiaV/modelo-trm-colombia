from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd
from trm_model.paths import find_project_root


ROOT = find_project_root()
RAW = ROOT / "data" / "raw"
RESULTS = ROOT / "results"
DATA = ROOT / "data"
SAMPLE_START = pd.Timestamp("2006-01-01")
SAMPLE_END = pd.Timestamp("2026-04-01")

# IDs canónicos de las dos especificaciones históricas. Los IDs se usan en
# nombres de archivos y contratos reproducibles; las etiquetas son las que se
# muestran a lectores no técnicos.
REFERENCE_MODEL_ID = "controles_externos"
REFERENCE_MODEL_LABEL = "Controles externos y financieros"
INTEGRATED_MODEL_ID = "marco_macro_integral"
INTEGRATED_MODEL_LABEL = "Marco macroeconómico integral"

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

# Componentes globales con cobertura completa en 2006-01--2026-04. Las series
# candidatas como TED, high-yield y actividad industrial china se descargan y se
# documentan, pero quedan fuera por cobertura incompleta y sin imputación.
GLOBAL_RAW_COMPONENTS = [
    "yield_real_10y_tips_pct",
    "yield_real_5y_us_pct",
    "yield_2y_us_pct",
    "yield_10y_us_pct",
    "spread_10y_2y_us_pct",
    "breakeven_5y_us_pct",
    "breakeven_10y_us_pct",
    "ln_brent_global",
    "ln_commodities_global",
    "epu_global",
    "estres_financiero_stl",
    "nfci_chicago",
    "anfci_chicago",
    "desempleo_us_pct",
    "ln_empleo_manufactura_us",
    "ln_produccion_industrial_us",
    "ln_fletes_transporte_us",
]
GLOBAL_BASE_FILE = DATA / "base_global_mensual.csv"

# Series internas colombianas con cobertura mensual completa en la ventana
# activa. La GEIH, IPI e IPP se cargan y auditan, pero no entran aquí si dejan
# meses faltantes o empiezan después de 2006; no se rellenan artificialmente.
INTERNAL_RAW_COMPONENTS = [
    "ln_ise_total_dane",
    "ln_ipc_colombia",
]


# Cada factor es un jugador de la descomposicion Shapley. Todos sus terminos
# (transformaciones y rezagos) entran o salen juntos al calcular el R2 marginal.
REFERENCE_FACTOR_SPECS = {
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
        "grupo": "Mercados financieros globales",
        "terminos": [("D.ln_dolar_amplio", 0)],
    },
    "VIX": {
        "grupo": "Mercados financieros globales",
        "terminos": [("D.ln_vix", 0)],
    },
}


def _global_terms(lag_market: int, lag_monthly: int) -> list[tuple[str, int]]:
    """Construye términos globales con rezagos por disponibilidad de publicación."""
    market_terms = [
        "D.yield_real_10y_tips_pct",
        "D.yield_real_5y_us_pct",
        "D.yield_2y_us_pct",
        "D.yield_10y_us_pct",
        "D.spread_10y_2y_us_pct",
        "D.breakeven_5y_us_pct",
        "D.breakeven_10y_us_pct",
        "D.epu_global",
        "D.estres_financiero_stl",
        "D.nfci_chicago",
        "D.anfci_chicago",
        "D.ln_brent_global",
        "D.ln_commodities_global",
    ]
    monthly_terms = [
        "D.desempleo_us_pct",
        "D.ln_empleo_manufactura_us",
        "D.ln_produccion_industrial_us",
        "D.ln_fletes_transporte_us",
    ]
    return [
        *[(term, lag_market) for term in market_terms],
        *[(term, lag_monthly) for term in monthly_terms],
    ]


def integrated_factor_specs(regional_component: str) -> dict[str, dict[str, object]]:
    return {
        **REFERENCE_FACTOR_SPECS,
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
        "Actividad y precios domésticos": {
            "grupo": "Condiciones internas",
            # ISE e IPC contemporáneos: explicación histórica/nowcast, no pronóstico.
            "terminos": [
                ("D.ln_ise_total_dane", 0),
                ("D.ln_ipc_colombia", 0),
            ],
        },
        "Monedas regionales": {
            "grupo": "Regional",
            "terminos": [(regional_component, 0)],
        },
        "Condiciones financieras, commodities y actividad internacional": {
            "grupo": "Condiciones financieras y actividad internacional",
            "terminos": _global_terms(0, 0),
        },
    }


INTEGRATED_FACTOR_SPECS_3 = integrated_factor_specs("factor_monedas_regionales_3")
INTEGRATED_FACTOR_SPECS_4 = integrated_factor_specs("factor_monedas_regionales_4")
INTEGRATED_FACTOR_SPECS = INTEGRATED_FACTOR_SPECS_4


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
            "grupo": "Mercados financieros globales",
            "terminos": [("D.ln_dolar_amplio", 1)],
        },
        "VIX": {
            "grupo": "Mercados financieros globales",
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
        "Actividad y precios domésticos": {
            "grupo": "Condiciones internas",
            # Bloque DANE con rezago conservador de publicación de dos meses.
            "terminos": [
                ("D.ln_ise_total_dane", 2),
                ("D.ln_ipc_colombia", 2),
            ],
        },
        "Monedas regionales": {
            "grupo": "Regional",
            "terminos": [(regional_component, 1)],
        },
        "Condiciones financieras, commodities y actividad internacional": {
            "grupo": "Condiciones financieras y actividad internacional",
            "terminos": _global_terms(1, 2),
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
    ("Actividad y precios domésticos", 2, "DANE; ISE mensual e IPC mensual", "Supuesto conservador: últimas observaciones completas conocidas para t-2"),
    ("Monedas regionales", 1, "Tipos de cambio mensuales", "Promedios completos conocidos para t-1"),
    (
        "Condiciones financieras, commodities y actividad internacional",
        2,
        "FRED; mercados diarios/semanales e indicadores mensuales",
        "Rendimientos, expectativas, riesgo y commodities t-1; empleo, desempleo, fletes y China t-2",
    ),
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
    "ln_ise_total_dane",
    "ln_ipc_colombia",
    *GLOBAL_RAW_COMPONENTS,
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
