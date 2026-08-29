"""Fichas y contabilidad no causal para la explicación mensual de la TRM.

Este módulo separa tres objetos que no deben mezclarse:

* la asociación parcial de cada término en una regresión histórica;
* la contabilidad firmada de la variación mensual ajustada; y
* la participación Shapley en el R² incremental.

Ninguna función de este módulo identifica efectos causales ni construye
escenarios contrafactuales. Las salidas están diseñadas para que esa
limitación sea visible en CSV, README y workbook.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

import numpy as np
import pandas as pd

from trm_model.features.monthly_transforms import design_term_name


NO_CAUSAL_WARNING = (
    "Asociación histórica parcial; no es un efecto causal ni un escenario contrafactual."
)

# Metadata económica que acompaña a los nombres técnicos del modelo. El texto
# describe el contenido de la señal, no afirma que exista un mecanismo identificado.
FACTOR_METADATA: dict[str, dict[str, str]] = {
    "Términos de intercambio": {
        "dominio": "Sector externo",
        "descripcion": "Precios relativos de exportaciones e importaciones de Colombia.",
        "pregunta_guia": "¿Cómo se movieron los precios relativos externos junto con la TRM?",
        "canal_descriptivo": "Señal de ingresos externos y condiciones comerciales; puede recoger otros cambios simultáneos.",
    },
    "Remesas": {
        "dominio": "Sector externo",
        "descripcion": "Remesas recibidas, agregadas en una ventana móvil de 12 meses.",
        "pregunta_guia": "¿Qué relación histórica hubo entre la variación de remesas y la variación de la TRM?",
        "canal_descriptivo": "Señal de flujos de divisas de hogares y de actividad externa.",
    },
    "Diferencial de tasas": {
        "dominio": "Política doméstica",
        "descripcion": "Diferencial de tasas de interés entre Colombia y Estados Unidos.",
        "pregunta_guia": "¿Cómo coincidieron los cambios relativos de tasas con la TRM?",
        "canal_descriptivo": "Señal de condiciones monetarias relativas y de valoración financiera.",
    },
    "Déficit fiscal": {
        "dominio": "Política doméstica",
        "descripcion": "Cambio del déficit fiscal acumulado como proporción del PIB.",
        "pregunta_guia": "¿Qué asociación histórica aparece entre la posición fiscal y la TRM?",
        "canal_descriptivo": "Señal de condiciones fiscales y percepción de riesgo, potencialmente correlacionada con el ciclo.",
    },
    "Dólar amplio": {
        "dominio": "Mercados financieros globales",
        "descripcion": "Índice amplio del dólar estadounidense frente a otras monedas.",
        "pregunta_guia": "¿Cómo se movió el dólar global en los meses de variación de la TRM?",
        "canal_descriptivo": "Señal agregada de valoración internacional del dólar.",
    },
    "VIX": {
        "dominio": "Mercados financieros globales",
        "descripcion": "Índice de volatilidad implícita del mercado accionario estadounidense.",
        "pregunta_guia": "¿Qué asociación tuvo la aversión a la volatilidad con la TRM?",
        "canal_descriptivo": "Señal de tensión y volatilidad financiera internacional.",
    },
    "Riesgo soberano EMBIG Colombia": {
        "dominio": "Riesgo local",
        "descripcion": "Prima EMBIG de Colombia expresada en puntos porcentuales.",
        "pregunta_guia": "¿Cómo coincidieron los cambios en la prima soberana con la TRM?",
        "canal_descriptivo": "Señal de riesgo soberano percibido y condiciones de financiamiento externo.",
    },
    "Reservas internacionales": {
        "dominio": "Sector externo",
        "descripcion": "Reservas internacionales netas sin FLAR, en logaritmos.",
        "pregunta_guia": "¿Qué asociación histórica tuvo la variación de reservas con la TRM?",
        "canal_descriptivo": "Señal de liquidez externa y de operaciones que pueden responder a la propia dinámica cambiaria.",
    },
    "Balanza comercial cambiaria": {
        "dominio": "Sector externo",
        "descripcion": "Balanza comercial cambiaria transformada con asinh.",
        "pregunta_guia": "¿Cómo se movió el saldo comercial cambiario junto con la TRM?",
        "canal_descriptivo": "Señal de flujos comerciales; la transformación asinh conserva el signo y reduce la influencia de extremos.",
    },
    "Flujos netos de capital": {
        "dominio": "Sector externo",
        "descripcion": "Flujos netos de capital de la balanza cambiaria transformados con asinh.",
        "pregunta_guia": "¿Qué relación histórica tuvieron los flujos de capital y la TRM?",
        "canal_descriptivo": "Señal de entradas y salidas de capital que también pueden reaccionar a la TRM.",
    },
    "Diferencial de compensación inflacionaria 5 años": {
        "dominio": "Política doméstica",
        "descripcion": "Diferencia entre la compensación inflacionaria de Colombia y Estados Unidos a cinco años.",
        "pregunta_guia": "¿Cómo coincidieron las variaciones de compensación inflacionaria con la TRM?",
        "canal_descriptivo": "Señal financiera que combina expectativas, primas de riesgo y liquidez; no es una expectativa pura de inflación.",
    },
    "Actividad y precios domésticos": {
        "dominio": "Condiciones internas",
        "descripcion": "Bloque compuesto por actividad económica (ISE) y precios al consumidor (IPC).",
        "pregunta_guia": "¿Qué aportes contables tuvieron actividad y precios internos en cada mes?",
        "canal_descriptivo": "Bloque de dos señales internas con coeficientes separados; su suma mensual es interpretable como contabilidad, no como un parámetro único.",
    },
    "Monedas regionales": {
        "dominio": "Regional",
        "descripcion": "Promedio estandarizado de cambios de BRL, CLP, MXN y PEN por dólar estadounidense.",
        "pregunta_guia": "¿Qué parte de la variación mensual coincide con el movimiento regional común?",
        "canal_descriptivo": "Señal común de monedas comparables; no separa shocks regionales simultáneos.",
    },
    "Condiciones financieras, commodities y actividad internacional": {
        "dominio": "Condiciones financieras y actividad internacional",
        "descripcion": "Bloque compuesto por rendimientos, compensación inflacionaria, condiciones financieras, commodities, empleo, desempleo, producción y fletes internacionales.",
        "pregunta_guia": "¿Cómo se repartió la contabilidad mensual entre las señales internacionales agrupadas?",
        "canal_descriptivo": "Bloque de múltiples términos con escalas y rezagos distintos; no tiene un coeficiente ni un signo económico único.",
    },
}

_TERM_BASE_LABELS: dict[str, str] = {
    "const": "constante",
    "dummy_pandemia_2020": "dummy de pandemia",
    "D.ln_terminos_intercambio": "cambio logarítmico de términos de intercambio",
    "D.ln_remesas_12m": "cambio logarítmico de remesas de 12 meses",
    "D.diferencial_tasas_pp": "cambio del diferencial de tasas",
    "D.deficit_fiscal_12m_pct_pib": "cambio del déficit fiscal de 12 meses sobre PIB",
    "D.ln_dolar_amplio": "cambio logarítmico del dólar amplio",
    "D.ln_vix": "cambio logarítmico del VIX",
    "D.embig_colombia_pp": "cambio del EMBIG Colombia",
    "D.ln_reservas_netas_sin_flar": "cambio logarítmico de reservas netas sin FLAR",
    "D.asinh_balanza_comercial": "cambio de asinh de la balanza comercial cambiaria",
    "D.asinh_flujos_capital": "cambio de asinh de flujos netos de capital",
    "D.diferencial_bei_5y_pp": "cambio del diferencial de compensación inflacionaria a 5 años",
    "D.ln_ise_total_dane": "cambio logarítmico del ISE total DANE",
    "D.ln_ipc_colombia": "cambio logarítmico del IPC Colombia",
    "factor_monedas_regionales_3": "factor regional de BRL, CLP y MXN",
    "factor_monedas_regionales_4": "factor regional de BRL, CLP, MXN y PEN",
    "D.yield_real_10y_tips_pct": "cambio del rendimiento real TIPS de EE. UU. a 10 años",
    "D.yield_real_5y_us_pct": "cambio del rendimiento real de EE. UU. a 5 años",
    "D.yield_2y_us_pct": "cambio del Treasury de EE. UU. a 2 años",
    "D.yield_10y_us_pct": "cambio del Treasury de EE. UU. a 10 años",
    "D.spread_10y_2y_us_pct": "cambio de la pendiente Treasury 10Y–2Y",
    "D.breakeven_5y_us_pct": "cambio de la compensación inflacionaria de EE. UU. a 5 años",
    "D.breakeven_10y_us_pct": "cambio de la compensación inflacionaria de EE. UU. a 10 años",
    "D.epu_global": "cambio de incertidumbre de política económica global",
    "D.estres_financiero_stl": "cambio del estrés financiero STL",
    "D.nfci_chicago": "cambio del índice de condiciones financieras de Chicago",
    "D.anfci_chicago": "cambio del índice ajustado de condiciones financieras de Chicago",
    "D.ln_brent_global": "cambio logarítmico del Brent global",
    "D.ln_commodities_global": "cambio logarítmico del índice global de commodities",
    "D.desempleo_us_pct": "cambio del desempleo armonizado de EE. UU.",
    "D.ln_empleo_manufactura_us": "cambio logarítmico del empleo manufacturero de EE. UU.",
    "D.ln_produccion_industrial_us": "cambio logarítmico de la producción industrial de EE. UU.",
    "D.ln_fletes_transporte_us": "cambio logarítmico de fletes de transporte",
}


def _term_names(factor_specs: Mapping[str, Mapping[str, object]]) -> dict[str, list[str]]:
    return {
        factor: [design_term_name(component, lag) for component, lag in spec["terminos"]]
        for factor, spec in factor_specs.items()
    }


def term_label(term: str) -> str:
    """Devuelve una etiqueta legible conservando transformación y rezago."""
    if term in {"const", "dummy_pandemia_2020"}:
        return _TERM_BASE_LABELS.get(term, term)
    match = re.match(r"^(?P<component>.+)\.L(?P<lag>\d+)$", term)
    if not match:
        return term
    component = match.group("component")
    lag = int(match.group("lag"))
    base = _TERM_BASE_LABELS.get(component, component)
    timing = "contemporáneo" if lag == 0 else f"rezago {lag}"
    return f"{base}, {timing}"


def _sign_label(value: float) -> str:
    if not np.isfinite(value) or np.isclose(value, 0.0):
        return "sin signo definido"
    return "positivo" if value > 0 else "negativo"


def _float_or_nan(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return result


def _format_number(value: object, decimals: int = 4) -> str:
    number = _float_or_nan(value)
    if not np.isfinite(number):
        return "no disponible"
    return f"{number:.{decimals}f}".replace(".", ",")


def _normalise_contributions(contributions: pd.DataFrame) -> pd.DataFrame:
    frame = contributions.copy()
    if "fecha" in frame.columns:
        frame["fecha"] = pd.to_datetime(frame["fecha"])
        frame = frame.set_index("fecha")
    if frame.index.name is None:
        frame.index.name = "fecha"
    return frame


def aggregate_factor_contributions(
    contributions: pd.DataFrame,
    factor_specs: Mapping[str, Mapping[str, object]],
) -> pd.DataFrame:
    """Agrega la contribución ``coeficiente × regresor`` por factor.

    Las columnas ``otros_componentes`` contienen la constante, la dinámica
    propia de la TRM y la dummy de pandemia (o cualquier término no asignado a
    un factor). Por diseño, ``suma_factores + otros_componentes`` cierra contra
    ``ajuste_total``; ``cierre_contable`` permite auditar esa igualdad.
    """
    frame = _normalise_contributions(contributions)
    names_by_factor = _term_names(factor_specs)
    assigned_terms = [term for terms in names_by_factor.values() for term in terms]
    missing = sorted(set(assigned_terms).difference(frame.columns))
    if missing:
        raise ValueError(
            "Faltan términos de contribución para agregar factores: "
            + ", ".join(missing)
        )

    result = pd.DataFrame(index=frame.index)
    for factor, terms in names_by_factor.items():
        result[factor] = frame[terms].sum(axis=1, min_count=1)

    excluded = set(assigned_terms) | {"ajuste_total"}
    other_terms = [column for column in frame.columns if column not in excluded]
    if other_terms:
        result["otros_componentes"] = frame[other_terms].sum(axis=1, min_count=1)
    else:
        result["otros_componentes"] = 0.0
    result["suma_factores"] = result[list(names_by_factor)].sum(axis=1, min_count=1)
    if "ajuste_total" in frame.columns:
        result["ajuste_total"] = pd.to_numeric(frame["ajuste_total"], errors="coerce")
    else:
        result["ajuste_total"] = result["suma_factores"] + result["otros_componentes"]
    result["cierre_contable"] = (
        result["suma_factores"] + result["otros_componentes"] - result["ajuste_total"]
    )
    if not np.allclose(
        result["cierre_contable"].fillna(0.0).to_numpy(),
        0.0,
        rtol=1e-9,
        atol=1e-10,
    ):
        raise AssertionError("La agregación por factores no cierra contra el ajuste total.")
    result.index.name = "fecha"
    return result


def _stability_metrics(
    factor: str,
    stability_detail: pd.DataFrame | None,
) -> dict[str, object]:
    if stability_detail is None or stability_detail.empty:
        return {
            "estabilidad_signo_factor_pct_submuestras": np.nan,
            "estabilidad_signos_terminos_pct_submuestras": np.nan,
            "estabilidad_signos_terminos_pct_2020_en_adelante": np.nan,
            "peso_entre_factores_pct_2020_en_adelante": np.nan,
        }
    rows = stability_detail.loc[stability_detail["factor"].eq(factor)].copy()
    if rows.empty:
        return {
            "estabilidad_signo_factor_pct_submuestras": np.nan,
            "estabilidad_signos_terminos_pct_submuestras": np.nan,
            "estabilidad_signos_terminos_pct_2020_en_adelante": np.nan,
            "peso_entre_factores_pct_2020_en_adelante": np.nan,
        }
    non_full = rows.loc[rows["submuestra"].ne("Muestra completa")]
    factor_sign_column = "signo_coincide_muestra_completa"
    sign_share = (
        100.0 * non_full[factor_sign_column].astype(bool).mean()
        if not non_full.empty and factor_sign_column in non_full
        else np.nan
    )
    if not non_full.empty and {
        "terminos_con_signo_coincidente",
        "terminos_evaluados",
    }.issubset(non_full.columns):
        evaluated = pd.to_numeric(non_full["terminos_evaluados"], errors="coerce").sum()
        matched = pd.to_numeric(non_full["terminos_con_signo_coincidente"], errors="coerce").sum()
        term_share = 100.0 * matched / evaluated if evaluated else np.nan
    else:
        term_share = sign_share
    recent = rows.loc[rows["submuestra"].eq("2020 en adelante")]
    if not recent.empty and {
        "terminos_con_signo_coincidente",
        "terminos_evaluados",
    }.issubset(recent.columns):
        evaluated_recent = _float_or_nan(recent["terminos_evaluados"].iloc[0])
        matched_recent = _float_or_nan(recent["terminos_con_signo_coincidente"].iloc[0])
        recent_term_share = (
            100.0 * matched_recent / evaluated_recent
            if np.isfinite(evaluated_recent) and evaluated_recent > 0
            else np.nan
        )
    else:
        recent_term_share = (
            100.0 * bool(recent[factor_sign_column].iloc[0])
            if not recent.empty and factor_sign_column in recent
            else np.nan
        )
    return {
        "estabilidad_signo_factor_pct_submuestras": sign_share,
        "estabilidad_signos_terminos_pct_submuestras": term_share,
        "estabilidad_signos_terminos_pct_2020_en_adelante": recent_term_share,
        "peso_entre_factores_pct_2020_en_adelante": (
            _float_or_nan(recent["peso_entre_factores_pct"].iloc[0])
            if not recent.empty and "peso_entre_factores_pct" in recent
            else np.nan
        ),
    }


def _dynamic_reading(row: Mapping[str, object]) -> str:
    factor = str(row["factor"])
    metadata = str(row.get("canal_descriptivo", ""))
    lag_text = str(row.get("rezagos_modelo", "no disponible"))
    contribution_mean = _float_or_nan(row.get("contribucion_media_mensual_pct"))
    contribution_share = _float_or_nan(row.get("meses_contribucion_positiva_pct"))
    stability = _float_or_nan(row.get("estabilidad_signos_terminos_pct_2020_en_adelante"))
    if bool(row.get("es_compuesto", False)):
        signs = str(row.get("signos_terminos", "no disponibles"))
        text = (
            f"{factor} es un bloque compuesto por {int(row['n_terminos'])} términos "
            f"({str(row['terminos_legibles'])}). No tiene un coeficiente ni un signo único; "
            f"los signos estimados por término son {signs}. "
            f"La lectura recomendada es su suma de contribuciones mensuales y no una dirección global."
        )
    else:
        coefficient = _float_or_nan(row.get("coeficiente"))
        sign = _sign_label(coefficient)
        if sign == "positivo":
            direction = "un aumento del regresor se asocia con una variación mensual de la TRM mayor"
        elif sign == "negativo":
            direction = "un aumento del regresor se asocia con una variación mensual de la TRM menor"
        else:
            direction = "no se observa una dirección lineal definida"
        text = (
            f"En la ecuación de variación mensual, {direction}; "
            f"coeficiente { _format_number(coefficient) } y {lag_text}."
        )
        if bool(row.get("ic95_cruza_cero", False)):
            text += " El IC95% cruza cero, por lo que la dirección es imprecisa en esta muestra."
        elif bool(row.get("p_valor_menor_05", False)):
            text += " El IC95% no cruza cero al 5% en la inferencia HAC."
        else:
            text += " La inferencia HAC no alcanza el umbral convencional del 5%."
    if np.isfinite(contribution_mean):
        text += (
            f" Su contribución contable media fue {contribution_mean:.3f}% de Δln TRM "
            f"y fue positiva en {contribution_share:.1f}% de los meses."
        )
    if np.isfinite(stability):
        text += (
            f" En 2020 en adelante coincidieron los signos de {stability:.1f}% de sus términos "
            "con los de la muestra completa."
        )
    if metadata:
        text += f" Señal económica: {metadata}"
    return text + f" {NO_CAUSAL_WARNING}"


def build_factor_interpretation_table(
    factor_specs: Mapping[str, Mapping[str, object]],
    coefficients: pd.DataFrame,
    *,
    model_id: str,
    model_label: str,
    shapley: pd.DataFrame | None = None,
    bootstrap: pd.DataFrame | None = None,
    stability_detail: pd.DataFrame | None = None,
    factor_contributions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Construye la ficha integrada de factores y su lectura dinámica."""
    names_by_factor = _term_names(factor_specs)
    coefficient_lookup = coefficients.set_index("termino", drop=False)
    missing = sorted(
        {
            term
            for terms in names_by_factor.values()
            for term in terms
            if term not in coefficient_lookup.index
        }
    )
    if missing:
        raise ValueError("Faltan coeficientes para los términos: " + ", ".join(missing))
    shapley_lookup = (
        shapley.set_index("factor", drop=False) if shapley is not None else pd.DataFrame()
    )
    bootstrap_lookup = (
        bootstrap.set_index("factor", drop=False) if bootstrap is not None else pd.DataFrame()
    )
    contributions = (
        _normalise_contributions(factor_contributions)
        if factor_contributions is not None
        else None
    )
    rows: list[dict[str, object]] = []
    for factor, spec in factor_specs.items():
        terms = names_by_factor[factor]
        term_rows = coefficient_lookup.loc[terms]
        composite = len(terms) > 1
        coefficients_text = "; ".join(
            f"{term}={_format_number(term_rows.loc[term, 'coeficiente'])}"
            for term in terms
        )
        signs_text = "; ".join(
            f"{term_label(term)}: {_sign_label(_float_or_nan(term_rows.loc[term, 'coeficiente']))}"
            for term in terms
        )
        lags = sorted({int(re.search(r"\.L(\d+)$", term).group(1)) for term in terms})
        lag_text = ", ".join("0 (contemporáneo)" if lag == 0 else str(lag) for lag in lags)
        first = term_rows.iloc[0]
        coefficient = np.nan if composite else _float_or_nan(first["coeficiente"])
        p_value = np.nan if composite else _float_or_nan(first["p_valor"])
        lower = np.nan if composite else _float_or_nan(first["ic_95_inferior"])
        upper = np.nan if composite else _float_or_nan(first["ic_95_superior"])
        contribution_mean = np.nan
        contribution_median = np.nan
        contribution_abs_mean = np.nan
        positive_share = np.nan
        last_contribution = np.nan
        if contributions is not None and factor in contributions.columns:
            series = pd.to_numeric(contributions[factor], errors="coerce").dropna()
            if not series.empty:
                contribution_mean = 100.0 * float(series.mean())
                contribution_median = 100.0 * float(series.median())
                contribution_abs_mean = 100.0 * float(series.abs().mean())
                positive_share = 100.0 * float((series > 0).mean())
                last_contribution = 100.0 * float(series.iloc[-1])
        row: dict[str, object] = {
            "modelo_id": model_id,
            "modelo": model_label,
            "factor": factor,
            "grupo": spec["grupo"],
            "dominio": FACTOR_METADATA.get(factor, {}).get("dominio", spec["grupo"]),
            "descripcion": FACTOR_METADATA.get(factor, {}).get("descripcion", ""),
            "pregunta_guia": FACTOR_METADATA.get(factor, {}).get("pregunta_guia", ""),
            "canal_descriptivo": FACTOR_METADATA.get(factor, {}).get("canal_descriptivo", ""),
            "terminos": ", ".join(terms),
            "terminos_legibles": "; ".join(term_label(term) for term in terms),
            "rezagos_modelo": lag_text,
            "n_terminos": len(terms),
            "es_compuesto": composite,
            "coeficiente": coefficient,
            "coeficientes_terminos": coefficients_text,
            "signos_terminos": signs_text,
            "p_valor_hac": p_value,
            "ic_95_inferior": lower,
            "ic_95_superior": upper,
            "ic95_cruza_cero": (
                bool(lower <= 0 <= upper)
                if np.isfinite(lower) and np.isfinite(upper)
                else np.nan
            ),
            "p_valor_menor_05": bool(p_value < 0.05) if np.isfinite(p_value) else np.nan,
            "estado_inferencia": (
                "Factor compuesto: sin coeficiente único ni IC agregado"
                if composite
                else "Coeficiente único con inferencia HAC"
            ),
            "contribucion_media_mensual_pct": contribution_mean,
            "contribucion_mediana_mensual_pct": contribution_median,
            "contribucion_abs_media_mensual_pct": contribution_abs_mean,
            "meses_contribucion_positiva_pct": positive_share,
            "ultima_contribucion_mensual_pct": last_contribution,
            "participacion_shapley_r2_pct": np.nan,
            "aporte_shapley_r2_pp": np.nan,
            "ic95_shapley_inferior_pct": np.nan,
            "ic95_shapley_superior_pct": np.nan,
            "probabilidad_shapley_top3_pct": np.nan,
            "advertencia_interpretacion": NO_CAUSAL_WARNING,
        }
        if factor in shapley_lookup.index:
            shapley_row = shapley_lookup.loc[factor]
            row["participacion_shapley_r2_pct"] = _float_or_nan(
                shapley_row["peso_entre_factores_pct"]
            )
            row["aporte_shapley_r2_pp"] = _float_or_nan(
                shapley_row["aporte_r2_puntos_porcentuales"]
            )
        if factor in bootstrap_lookup.index:
            bootstrap_row = bootstrap_lookup.loc[factor]
            row["ic95_shapley_inferior_pct"] = _float_or_nan(
                bootstrap_row["ic_95_inferior_pct"]
            )
            row["ic95_shapley_superior_pct"] = _float_or_nan(
                bootstrap_row["ic_95_superior_pct"]
            )
            row["probabilidad_shapley_top3_pct"] = _float_or_nan(
                bootstrap_row["probabilidad_top3_pct"]
            )
        row.update(_stability_metrics(factor, stability_detail))
        row["lectura_dinamica"] = _dynamic_reading(row)
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = [
    "FACTOR_METADATA",
    "NO_CAUSAL_WARNING",
    "aggregate_factor_contributions",
    "build_factor_interpretation_table",
    "term_label",
]
