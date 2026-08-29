from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    ROOT,
    REFERENCE_MODEL_LABEL,
    INTEGRATED_MODEL_LABEL,
)


# ---------------------------------------------------------------------------
# Etiquetas legibles para los términos del modelo en las tablas del README.
# Cualquier término no listado aquí se muestra con su nombre técnico tal cual.
# ---------------------------------------------------------------------------
_TERM_LABELS: dict[str, str] = {
    "const": "Constante",
    "D.ln_terminos_intercambio.L0": "Δln términos de intercambio, mes actual",
    "D.ln_remesas_12m.L1": "Δln remesas 12 meses, rezago 1",
    "D.diferencial_tasas_pp.L1": "Δ diferencial de tasas, rezago 1",
    "D.deficit_fiscal_12m_pct_pib.L1": "Δ déficit fiscal 12 meses/PIB, rezago 1",
    "D.ln_dolar_amplio.L0": "Δln dólar amplio, mes actual",
    "D.ln_vix.L0": "Δln VIX, mes actual",
    "D.embig_colombia_pp.L0": "Δ EMBIG Colombia (pp), mes actual",
    "D.ln_reservas_netas_sin_flar.L1": "Δln reservas netas sin FLAR, rezago 1",
    "D.asinh_balanza_comercial.L1": "Δ asinh(balanza comercial), rezago 1",
    "D.asinh_flujos_capital.L1": "Δ asinh(flujos de capital), rezago 1",
    "D.diferencial_bei_5y_pp.L1": "Δ diferencial BEI 5 años (pp), rezago 1",
    "factor_monedas_regionales_4.L0": "Factor regional BRL+CLP+MXN+PEN, mes actual",
    "factor_monedas_regionales_3.L1": "Factor regional BRL+CLP+MXN, rezago 1",
    "D.yield_real_10y_tips_pct.L0": "Δ rendimiento real EE. UU. 10 años, mes actual",
    "D.yield_2y_us_pct.L0": "Δ Treasury EE. UU. 2 años, mes actual",
    "D.yield_10y_us_pct.L0": "Δ Treasury EE. UU. 10 años, mes actual",
    "D.spread_10y_2y_us_pct.L0": "Δ pendiente 10Y–2Y EE. UU., mes actual",
    "D.ln_brent_global.L0": "Δln Brent global, mes actual",
    "D.ln_commodities_global.L0": "Δln índice global de commodities, mes actual",
    "D.epu_global.L0": "Δ incertidumbre económica global, mes actual",
    "D.estres_financiero_stl.L0": "Δ estrés financiero STL, mes actual",
    "D.ln_empleo_manufactura_us.L0": "Δln empleo manufacturero EE. UU., mes actual",
    "D.ln_produccion_industrial_us.L0": "Δln producción industrial EE. UU., mes actual",
    "D.yield_real_10y_tips_pct.L1": "Δ rendimiento real EE. UU. 10 años, rezago 1",
    "D.yield_2y_us_pct.L1": "Δ Treasury EE. UU. 2 años, rezago 1",
    "D.yield_10y_us_pct.L1": "Δ Treasury EE. UU. 10 años, rezago 1",
    "D.spread_10y_2y_us_pct.L1": "Δ pendiente 10Y–2Y EE. UU., rezago 1",
    "D.ln_brent_global.L1": "Δln Brent global, rezago 1",
    "D.ln_commodities_global.L1": "Δln índice global de commodities, rezago 1",
    "D.epu_global.L1": "Δ incertidumbre económica global, rezago 1",
    "D.estres_financiero_stl.L1": "Δ estrés financiero STL, rezago 1",
    "D.ln_empleo_manufactura_us.L2": "Δln empleo manufacturero EE. UU., rezago 2",
    "D.ln_produccion_industrial_us.L2": "Δln producción industrial EE. UU., rezago 2",
    "D.yield_real_5y_us_pct.L0": "Δ rendimiento real EE. UU. 5 años, mes actual",
    "D.breakeven_5y_us_pct.L0": "Δ compensación inflacionaria EE. UU. 5 años, mes actual",
    "D.breakeven_10y_us_pct.L0": "Δ compensación inflacionaria EE. UU. 10 años, mes actual",
    "D.nfci_chicago.L0": "Δ índice de condiciones financieras Chicago, mes actual",
    "D.anfci_chicago.L0": "Δ índice ajustado de condiciones financieras Chicago, mes actual",
    "D.desempleo_us_pct.L0": "Δ desempleo EE. UU. armonizado, mes actual",
    "D.ln_fletes_transporte_us.L0": "Δln fletes de transporte, mes actual",
    "D.yield_real_5y_us_pct.L1": "Δ rendimiento real EE. UU. 5 años, rezago 1",
    "D.breakeven_5y_us_pct.L1": "Δ compensación inflacionaria EE. UU. 5 años, rezago 1",
    "D.breakeven_10y_us_pct.L1": "Δ compensación inflacionaria EE. UU. 10 años, rezago 1",
    "D.nfci_chicago.L1": "Δ índice de condiciones financieras Chicago, rezago 1",
    "D.anfci_chicago.L1": "Δ índice ajustado de condiciones financieras Chicago, rezago 1",
    "D.desempleo_us_pct.L2": "Δ desempleo EE. UU. armonizado, rezago 2",
    "D.ln_fletes_transporte_us.L2": "Δln fletes de transporte, rezago 2",
    "D.ln_ise_total_dane.L0": "Δln ISE total DANE, mes actual",
    "D.ln_ipc_colombia.L0": "Δln IPC Colombia, mes actual",
    "D.ln_ise_total_dane.L2": "Δln ISE total DANE, rezago 2",
    "D.ln_ipc_colombia.L2": "Δln IPC Colombia, rezago 2",
    "dummy_pandemia_2020": "Pandemia marzo–mayo 2020",
}

# Lectura del coeficiente de la especificación de controles externos (sin
# lectura económica distinta; se mantiene el texto de referencia).
_REFERENCE_READINGS: dict[str, str] = {
    "const": "No hay evidencia de una deriva mensual adicional.",
    "D.ln_terminos_intercambio.L0": (
        "Una mejora de 10% se asocia con una TRM cerca de {:.1f}% menor."
    ),
    "D.ln_remesas_12m.L1": (
        "Un aumento de 10% se asocia con una TRM cerca de {:.1f}% mayor; "
        "el signo contrario al canal simple de oferta de divisas aconseja cautela por endogeneidad."
    ),
    "D.diferencial_tasas_pp.L1": (
        "Un aumento de 1 punto porcentual en el cambio del diferencial "
        "se asocia con una TRM cerca de {:.2f}% menor."
    ),
    "D.deficit_fiscal_12m_pct_pib.L1": (
        "Un aumento de 1 punto porcentual se asocia con una TRM cerca de {:.2f}% mayor, "
        "pero la estimación no es precisa al 5%."
    ),
    "D.ln_dolar_amplio.L0": (
        "Un aumento de 1% del dólar global se asocia con una TRM cerca de {:.2f}% mayor."
    ),
    "D.ln_vix.L0": (
        "Un aumento de 10% del VIX se asocia con una TRM cerca de {:.2f}% mayor."
    ),
    "dummy_pandemia_2020": (
        "Se asocia con una TRM alrededor de {:.1f}% mayor, condicionado a los demás factores."
    ),
}


def _pval_str(p: float) -> str:
    """Formatea un p-valor como '<0,0001' o con 4 decimales, usando coma decimal."""
    if p < 0.0001:
        return "<0,0001"
    return f"{p:.4f}".replace(".", ",")


def _coef_str(c: float) -> str:
    """Formatea un coeficiente con 5 decimales y coma decimal, con signo −."""
    s = f"{abs(c):.5f}".replace(".", ",")
    return f"−{s}" if c < 0 else s


def _pct_str(v: float, decimals: int = 2) -> str:
    """Formatea un porcentaje con coma decimal."""
    return f"{v:.{decimals}f}".replace(".", ",") + "%"


def _replace_auto_block(text: str, tag: str, new_content: str) -> str:
    """Reemplaza el contenido entre marcadores <!-- AUTO:tag --> en el README."""
    open_marker = f"<!-- AUTO:{tag} -->\n"
    close_marker = f"<!-- /AUTO:{tag} -->"
    start = text.find(open_marker)
    if start < 0:
        raise ValueError(
            f"Marcador AUTO:{tag} no encontrado en el README. "
            f"Añade <!-- AUTO:{tag} --> ... <!-- /AUTO:{tag} --> manualmente."
        )
    end = text.find(close_marker, start + len(open_marker))
    if end < 0:
        raise ValueError(f"Cierre <!-- /AUTO:{tag} --> no encontrado en el README.")
    return text[:start + len(open_marker)] + new_content + "\n" + text[end:]


def update_readme_fragments(
    coefficients_diff: pd.DataFrame,
    coefficients_integrated: pd.DataFrame,
    comparison: pd.DataFrame,
    shapley_integrated: pd.DataFrame,
    shapley_bootstrap: pd.DataFrame,
    validation: pd.DataFrame,
    validation_integrated: pd.DataFrame,
    validation_forecast: pd.DataFrame,
    predictions_forecast: pd.DataFrame,
    factor_interpretation: pd.DataFrame | None = None,
) -> None:
    """Sobreescribe los bloques AUTO del README raíz con los valores actuales."""
    readme_path = ROOT / "README.md"
    text = readme_path.read_text(encoding="utf-8")

    # ── 1. Coeficientes de controles externos ────────────────────────────────
    base_row = validation.loc[validation["modelo"].ne("Caminata aleatoria")].iloc[0]
    mape_base = float(base_row["mape_pct"])
    acierto_base = float(base_row["acierto_direccion_pct"])
    r2_vs_walk_base = float(
        comparison.loc[comparison["modelo"].eq(REFERENCE_MODEL_LABEL), "r2_validacion_condicional_vs_caminata"].iloc[0]
    )

    rows_reference = [
        "| Término | Coeficiente | p-valor HAC | Lectura aproximada |",
        "|---|---:|---:|---|",
    ]
    for _, row in coefficients_diff.iterrows():
        term = str(row["termino"])
        coef = float(row["coeficiente"])
        pval = float(row["p_valor"])
        label = _TERM_LABELS.get(term, f"`{term}`")
        reading_tpl = _REFERENCE_READINGS.get(term, "")
        if reading_tpl and "{" in reading_tpl:
            # Magnitud del efecto: para log-log usamos abs(coef)*10; para otros abs(coef)*100
            if "10%" in reading_tpl:
                mag = abs(coef) * 10 * 100
            elif "1 punto porcentual" in reading_tpl and "diferencial" in reading_tpl:
                mag = abs(coef) * 100
            elif "1 punto porcentual" in reading_tpl:
                mag = abs(coef) * 100
            elif "1%" in reading_tpl:
                mag = abs(coef) * 100
            else:
                mag = abs(coef) * 100
            reading = reading_tpl.format(mag)
        else:
            reading = reading_tpl
        rows_reference.append(
            f"| {label} | {_coef_str(coef)} | {_pval_str(pval)} | {reading} |"
        )
    text = _replace_auto_block(text, "coeficientes_controles_externos", "\n".join(rows_reference))

    # ── 2. Métricas de controles externos ────────────────────────────────────
    lines_metricas_base = [
        f"- MAPE condicional: **{_pct_str(mape_base)}**.",
        f"- Acierto de dirección: **{_pct_str(acierto_base)}**.",
        f"- R² condicional frente a caminata aleatoria: **{_pct_str(r2_vs_walk_base * 100)}**.",
    ]
    text = _replace_auto_block(text, "metricas_controles_externos", "\n".join(lines_metricas_base))

    # ── 3. Coeficientes del marco macroeconómico integral ────────────────────
    rows_integrated = [
        "| Término | Coeficiente | p-valor |",
        "|---|---:|---:|",
    ]
    for _, row in coefficients_integrated.iterrows():
        term = str(row["termino"])
        coef = float(row["coeficiente"])
        pval = float(row["p_valor"])
        label = _TERM_LABELS.get(term, f"`{term}`")
        rows_integrated.append(f"| {label} | {_coef_str(coef)} | {_pval_str(pval)} |")
    text = _replace_auto_block(text, "coeficientes_marco_macro_integral", "\n".join(rows_integrated))

    # ── 4. Comparación de especificaciones descriptivas ─────────────────────
    base = comparison.loc[comparison["modelo"].eq(REFERENCE_MODEL_LABEL)].iloc[0]
    amp = comparison.loc[comparison["modelo"].eq(INTEGRATED_MODEL_LABEL)].iloc[0]
    r2_vs_walk_amp = float(amp["r2_validacion_condicional_vs_caminata"])
    rows_comp = [
        "| Métrica | Controles externos y financieros | Marco macroeconómico integral |",
        "|---|---:|---:|",
        f"| Observaciones efectivas | {int(base['observaciones'])} | {int(amp['observaciones'])} |",
        f"| R² | {_pct_str(base['r_cuadrado'] * 100)} | {_pct_str(amp['r_cuadrado'] * 100)} |",
        f"| R² ajustado | {_pct_str(base['r_cuadrado_ajustado'] * 100)} | {_pct_str(amp['r_cuadrado_ajustado'] * 100)} |",
        f"| MAPE, validación condicional de 48 meses | {_pct_str(base['mape_pct'])} | {_pct_str(amp['mape_pct'])} |",
        f"| Acierto de dirección | {_pct_str(base['acierto_direccion_pct'])} | {_pct_str(amp['acierto_direccion_pct'])} |",
        f"| R² condicional frente a caminata aleatoria | {_pct_str(base['r2_validacion_condicional_vs_caminata'] * 100)} | {_pct_str(r2_vs_walk_amp * 100)} |",
    ]
    text = _replace_auto_block(text, "comparacion_especificaciones", "\n".join(rows_comp))

    # ── 5. Pesos Shapley ─────────────────────────────────────────────────────
    shapley_sorted = shapley_integrated.sort_values(
        "peso_entre_factores_pct", ascending=False
    )
    rows_shapley = [
        f"| Factor | Peso entre los {len(shapley_integrated)} factores | Aporte al R² |",
        "|---|---:|---:|",
    ]
    for _, row in shapley_sorted.iterrows():
        peso = float(row["peso_entre_factores_pct"])
        aporte = float(row["aporte_r2_puntos_porcentuales"])
        aporte_str = f"{aporte:.2f}".replace(".", ",")
        rows_shapley.append(
            f"| {row['factor']} | {_pct_str(peso)} | {aporte_str} p.p. |"
        )
    text = _replace_auto_block(text, "pesos_shapley", "\n".join(rows_shapley))

    # ── 6. Intervalos bootstrap de los 3 factores top ────────────────
    top3 = shapley_bootstrap.nlargest(3, "peso_puntual_pct").reset_index(drop=True)
    partes = []
    for _, row in top3.iterrows():
        lo = f"{row['ic_95_inferior_pct']:.2f}".replace(".", ",")
        hi = f"{row['ic_95_superior_pct']:.2f}".replace(".", ",")
        partes.append(f"{row['factor']}, **{lo}%–{hi}%**")
    top3_str = "; ".join(partes)
    nreplicas = int(top3.iloc[0]["replicas_validas"])
    bloque = int(top3.iloc[0]["bloque_meses"])
    lines_bootstrap = [
        f"La incertidumbre se evalúa con {nreplicas} réplicas de un *bootstrap* circular de "
        f"bloques de {bloque} meses. Los intervalos percentiles del 95% de los tres factores "
        f"principales son: {top3_str}. Son intervalos de la asignación Shapley bajo remuestreo "
        "temporal, no intervalos de un efecto causal.",
    ]
    text = _replace_auto_block(text, "bootstrap_intervalos", "\n".join(lines_bootstrap))

    # ── 7. Métricas del pronóstico ────────────────────────────────────────────
    pronostico_row = validation_forecast.loc[
        validation_forecast["modelo"].ne("Caminata aleatoria")
    ].iloc[0]
    caminata_row = validation_forecast.loc[
        validation_forecast["modelo"].eq("Caminata aleatoria")
    ].iloc[0]
    mape_fc = float(pronostico_row["mape_pct"])
    acierto_fc = float(pronostico_row["acierto_direccion_pct"])
    mape_walk = float(caminata_row["mape_pct"])

    # Calcula R² vs caminata aleatoria directamente desde las predicciones
    fc_col = "ln_trm_pronostico_publicacion"
    if fc_col not in predictions_forecast.columns:
        fc_col = "ln_trm_modelo_condicional"
    model_err = predictions_forecast[fc_col] - predictions_forecast["ln_trm_observada"]
    bench_err = predictions_forecast["ln_trm_caminata_aleatoria"] - predictions_forecast["ln_trm_observada"]
    mse_model = float((model_err ** 2).mean())
    mse_bench = float((bench_err ** 2).mean())
    r2_fc = 1.0 - mse_model / mse_bench if mse_bench != 0 else float("nan")
    r2_fc_str = _pct_str(r2_fc * 100) if r2_fc >= 0 else f"−{_pct_str(abs(r2_fc) * 100)}"

    lines_fc = [
        f"La validación expansiva de 48 meses obtiene MAPE de **{_pct_str(mape_fc)}**, "
        f"acierto de dirección de **{_pct_str(acierto_fc, 2)}** y R² frente a la caminata "
        f"aleatoria de **{r2_fc_str}**. La caminata obtiene MAPE de **{_pct_str(mape_walk)}**. "
        "Es decir, la ecuación explicativa no se convierte automáticamente en un buen pronóstico "
        "y, con esta información, el benchmark simple sigue siendo superior.",
    ]
    text = _replace_auto_block(text, "metricas_pronostico", "\n".join(lines_fc))

    # ── 8. Ficha dinámica por factor ────────────────────────────────────────
    if factor_interpretation is None or factor_interpretation.empty:
        factor_lines = [
            "La ficha se genera desde `results/explicacion/interpretacion_factores_marco_macro_integral.csv`.",
            "La lectura es de asociación histórica y contabilidad mensual; no es causal.",
        ]
    else:
        def _table_pct(value: object) -> str:
            number = float(value)
            return "—" if np.isnan(number) else _pct_str(number)

        factor_lines = [
            "La tabla distingue asociación parcial HAC, contribución mensual firmada y participación Shapley en el R² incremental. "
            "Los factores compuestos no tienen coeficiente ni signo único; todas las lecturas son no causales.",
            "| Factor | Grupo | Términos y rezagos | Participación en R² incremental | Contribución media mensual | Lectura dinámica |",
            "|---|---|---|---:|---:|---|",
        ]
        for _, row in factor_interpretation.iterrows():
            factor_lines.append(
                f"| {row['factor']} | {row['grupo']} | {row['terminos_legibles']} | "
                f"{_table_pct(row['participacion_shapley_r2_pct'])} | "
                f"{_table_pct(row['contribucion_media_mensual_pct'])} | "
                f"{row['lectura_dinamica']} |"
            )
    text = _replace_auto_block(text, "interpretacion_factores", "\n".join(factor_lines))

    readme_path.write_text(text, encoding="utf-8")
    print("README.md actualizado con los valores del modelo.")
