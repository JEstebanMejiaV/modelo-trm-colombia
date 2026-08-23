from __future__ import annotations

import os
from pathlib import Path
import hashlib
import json


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "outputs" / "matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd


RESULTS = ROOT / "results"
CHARTS = ROOT / "graficos"

SOURCE_FILES = [
    RESULTS / "pesos_explicativos_modelo_ampliado.csv",
    RESULTS / "comparacion_modelos.csv",
    RESULTS / "validacion_metricas_modelo_ampliado.csv",
    RESULTS / "validacion_predicciones.csv",
    RESULTS / "validacion_predicciones_modelo_ampliado.csv",
    RESULTS / "coeficientes_modelo_ampliado.csv",
    RESULTS / "contribuciones_modelo_ampliado.csv",
    RESULTS / "coeficientes_corto_plazo_ecm.csv",
    RESULTS / "coeficientes_largo_plazo_ecm.csv",
    RESULTS / "bounds_resumen.csv",
]

IMAGE_FILES = [
    "01_pesos_explicativos.png",
    "02_desempeno_modelos.png",
    "03_validacion_trm.png",
    "04_efectos_tipicos.png",
    "05_ecm_elasticidades.png",
]

BACKGROUND = "#FFFFFF"
FOREGROUND = "#17324D"
MUTED = "#5F6F7F"
GRID = "#DCE3EA"
BASE = "#2D6FA3"
EXPANDED = "#23866F"
RANDOM_WALK = "#7B8794"
POSITIVE = "#C95D3A"
NEGATIVE = "#277DA1"

GROUP_COLORS = {
    "Global": "#2D6FA3",
    "Regional": "#7A5195",
    "Riesgo local": "#D97732",
    "Sector externo Colombia": "#23866F",
    "Política doméstica": "#B8891B",
}

LABELS = {
    "Monedas regionales": "Monedas regionales",
    "Dólar amplio": "Dólar amplio",
    "Spread TES-Treasury 10 años": "Spread TES–Treasury\n10 años",
    "Petróleo Brent": "Petróleo Brent",
    "VIX": "VIX",
    "Balanza comercial cambiaria": "Balanza comercial\ncambiaria",
    "Flujos netos de capital": "Flujos netos\nde capital",
    "Reservas internacionales": "Reservas\ninternacionales",
    "Remesas": "Remesas",
    "Diferencial de inflación": "Diferencial de\ninflación",
    "Diferencial de tasas": "Diferencial de tasas",
    "Déficit fiscal": "Déficit fiscal",
}


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 14,
            "axes.labelsize": 11,
            "axes.edgecolor": GRID,
            "axes.labelcolor": FOREGROUND,
            "axes.titlecolor": FOREGROUND,
            "xtick.color": MUTED,
            "ytick.color": FOREGROUND,
            "text.color": FOREGROUND,
            "figure.facecolor": BACKGROUND,
            "axes.facecolor": BACKGROUND,
            "savefig.facecolor": BACKGROUND,
        }
    )


def es(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def clean_axis(ax: plt.Axes, *, grid_axis: str = "x") -> None:
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, alpha=0.85)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)


def save(fig: plt.Figure, filename: str) -> None:
    path = CHARTS / filename
    fig.savefig(path, dpi=150, facecolor=BACKGROUND)
    plt.close(fig)


def text_sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def csv_semantic_sha256(path: Path) -> str:
    data = pd.read_csv(path)
    canonical = data.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.10g",
        na_rep="",
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_metadata() -> None:
    metadata = {
        "version": 2,
        "hash_method": "CSV canónico con 10 cifras significativas",
        "generator": {
            "path": "src/build_charts.py",
            "sha256": text_sha256(Path(__file__).resolve()),
        },
        "sources": {
            path.relative_to(ROOT).as_posix(): csv_semantic_sha256(path)
            for path in SOURCE_FILES
        },
        "images": {
            filename: {"width": 1920, "height": 1080} for filename in IMAGE_FILES
        },
    }
    (CHARTS / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def chart_weights(weights: pd.DataFrame) -> None:
    data = weights.sort_values("peso_entre_factores_pct", ascending=False).copy()
    data["etiqueta"] = data["factor"].map(LABELS).fillna(data["factor"])
    colors = data["grupo"].map(GROUP_COLORS)
    top_two = data.head(2)["peso_entre_factores_pct"].sum()
    top_names = " y ".join(data.head(2)["factor"].str.lower())

    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    y = np.arange(len(data))
    bars = ax.barh(y, data["peso_entre_factores_pct"], color=colors, height=0.66)
    ax.set_yticks(y, data["etiqueta"])
    ax.invert_yaxis()
    ax.set_xlim(0, data["peso_entre_factores_pct"].max() * 1.23)
    ax.set_xlabel("Participación dentro del R² incremental (%)")
    ax.tick_params(axis="y", length=0)
    clean_axis(ax)

    for bar, value in zip(bars, data["peso_entre_factores_pct"]):
        ax.text(
            bar.get_width() + 0.35,
            bar.get_y() + bar.get_height() / 2,
            f"{es(value)}%",
            va="center",
            ha="left",
            fontweight="bold",
        )

    legend = [
        Patch(facecolor=color, label=group)
        for group, color in GROUP_COLORS.items()
        if group in set(data["grupo"])
    ]
    ax.legend(
        handles=legend,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.21),
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "Qué factores pesan más en la explicación del modelo",
        x=0.04,
        y=0.975,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.925,
        f"{top_names.capitalize()} concentran {es(top_two)}% del R² incremental asignado a los factores.",
        color=MUTED,
        fontsize=12,
    )
    fig.text(
        0.04,
        0.018,
        "Descomposición Shapley/LMG exacta. Los pesos suman 100% dentro del bloque de factores; describen ajuste estadístico, no causalidad.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.subplots_adjust(left=0.28, right=0.97, top=0.86, bottom=0.18)
    save(fig, "01_pesos_explicativos.png")


def add_panel_bars(
    ax: plt.Axes,
    names: list[str],
    values: list[float],
    colors: list[str],
    title: str,
    suffix: str,
    digits: int = 1,
) -> None:
    positions = np.arange(len(names))
    bars = ax.bar(positions, values, color=colors, width=0.58)
    ax.set_xticks(positions, names)
    maximum = max(values) if values else 1.0
    ax.set_ylim(0, maximum * 1.28 if maximum > 0 else 1.0)
    ax.set_title(title, loc="left", fontweight="bold", pad=12)
    ax.tick_params(axis="x", length=0)
    clean_axis(ax, grid_axis="y")
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + maximum * 0.035,
            f"{es(value, digits)}{suffix}",
            ha="center",
            va="bottom",
            fontweight="bold",
        )


def chart_performance(comparison: pd.DataFrame, validation: pd.DataFrame) -> None:
    by_model = comparison.set_index("modelo")
    base = by_model.loc["Base"]
    expanded = by_model.loc["Ampliado historico"]
    walk = validation.loc[validation["modelo"].eq("Caminata aleatoria")].iloc[0]

    fig, axes = plt.subplots(2, 2, figsize=(12.8, 7.2))
    fig.suptitle(
        "Cuánto mejora el modelo ampliado",
        x=0.04,
        y=0.975,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.925,
        f"El R² ajustado aumenta {es((expanded['r_cuadrado_ajustado'] - base['r_cuadrado_ajustado']) * 100)} p.p. y el MAPE baja {es(base['mape_pct'] - expanded['mape_pct'], 2)} p.p.",
        color=MUTED,
        fontsize=12,
    )

    add_panel_bars(
        axes[0, 0],
        ["Principal", "Ampliado"],
        [base["r_cuadrado_ajustado"] * 100, expanded["r_cuadrado_ajustado"] * 100],
        [BASE, EXPANDED],
        "R² ajustado · más alto es mejor",
        "%",
    )
    add_panel_bars(
        axes[0, 1],
        ["Principal", "Ampliado", "Caminata"],
        [base["mape_pct"], expanded["mape_pct"], walk["mape_pct"]],
        [BASE, EXPANDED, RANDOM_WALK],
        "MAPE condicional · más bajo es mejor",
        "%",
        digits=2,
    )
    add_panel_bars(
        axes[1, 0],
        ["Principal", "Ampliado"],
        [
            base["r2_validacion_condicional_vs_caminata"] * 100,
            expanded["r2_validacion_condicional_vs_caminata"] * 100,
        ],
        [BASE, EXPANDED],
        "R² condicional frente a caminata · más alto es mejor",
        "%",
    )
    add_panel_bars(
        axes[1, 1],
        ["Principal", "Ampliado"],
        [base["acierto_direccion_pct"], expanded["acierto_direccion_pct"]],
        [BASE, EXPANDED],
        "Acierto de dirección mensual",
        "%",
    )
    fig.text(
        0.04,
        0.018,
        "Validación expansiva de 48 meses. Es condicional y pseudo-fuera de muestra: usa varios predictores contemporáneos ya realizados.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.subplots_adjust(left=0.07, right=0.98, top=0.84, bottom=0.11, wspace=0.22, hspace=0.43)
    save(fig, "02_desempeno_modelos.png")


def chart_validation(
    base_predictions: pd.DataFrame, expanded_predictions: pd.DataFrame
) -> None:
    base = base_predictions.copy()
    expanded = expanded_predictions.copy()
    base["fecha"] = pd.to_datetime(base["fecha"])
    expanded["fecha"] = pd.to_datetime(expanded["fecha"])
    data = base.merge(
        expanded[["fecha", "trm_modelo_condicional"]],
        on="fecha",
        how="inner",
        suffixes=("_principal", "_ampliado"),
        validate="one_to_one",
    )

    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    ax.plot(
        data["fecha"],
        data["trm_observada"],
        color=FOREGROUND,
        linewidth=2.8,
        label="TRM observada",
        zorder=4,
    )
    ax.plot(
        data["fecha"],
        data["trm_modelo_condicional_ampliado"],
        color=EXPANDED,
        linewidth=2.2,
        label="Modelo ampliado",
        zorder=3,
    )
    ax.plot(
        data["fecha"],
        data["trm_modelo_condicional_principal"],
        color=BASE,
        linewidth=1.8,
        linestyle="--",
        label="Modelo principal",
        zorder=2,
    )
    ax.plot(
        data["fecha"],
        data["trm_caminata_aleatoria"],
        color=RANDOM_WALK,
        linewidth=1.7,
        linestyle=":",
        label="Caminata aleatoria",
        zorder=1,
    )
    ax.set_ylabel("COP por USD")
    ax.set_xlabel("Mes de validación")
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"{value:,.0f}".replace(",", "."))
    )
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ticks = list(data["fecha"].iloc[::6])
    if ticks[-1] != data["fecha"].iloc[-1]:
        ticks.append(data["fecha"].iloc[-1])
    ax.set_xticks(ticks)
    ax.set_xlim(data["fecha"].min(), data["fecha"].max())
    ax.tick_params(axis="x", rotation=35)
    clean_axis(ax, grid_axis="both")
    ax.legend(loc="upper right", ncol=2, frameon=False)

    fig.suptitle(
        "TRM observada frente a los modelos",
        x=0.04,
        y=0.975,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.925,
        "El modelo ampliado sigue mejor varios giros de la TRM, aunque ninguno reproduce por completo los meses extremos.",
        color=MUTED,
        fontsize=12,
    )
    fig.text(
        0.04,
        0.018,
        "Ventana mayo de 2022–abril de 2026. Comparación condicional; no equivale a un pronóstico disponible al inicio de cada mes.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.subplots_adjust(left=0.085, right=0.98, top=0.86, bottom=0.17)
    save(fig, "03_validacion_trm.png")


def chart_standardized_effects(
    weights: pd.DataFrame,
    coefficients: pd.DataFrame,
    contributions: pd.DataFrame,
) -> None:
    coef_by_term = coefficients.set_index("termino")
    rows: list[dict[str, object]] = []
    for weight in weights.itertuples(index=False):
        term = str(weight.terminos)
        if term not in coef_by_term.index or term not in contributions.columns:
            raise KeyError(f"No se encontró {term} para construir el gráfico de efectos.")
        coef = coef_by_term.loc[term]
        coefficient = float(coef["coeficiente"])
        if np.isclose(coefficient, 0.0):
            raise ValueError(f"No se puede recuperar la escala del regresor para {term}.")
        regressor = contributions[term] / coefficient
        scale = float(regressor.std(ddof=1))
        rows.append(
            {
                "factor": weight.factor,
                "efecto": coefficient * scale * 100,
                "inferior": float(coef["ic_95_inferior"]) * scale * 100,
                "superior": float(coef["ic_95_superior"]) * scale * 100,
                "significativo": float(coef["p_valor"]) < 0.05,
            }
        )
    data = pd.DataFrame(rows)
    data["magnitud"] = data["efecto"].abs()
    data = data.sort_values("magnitud", ascending=False).reset_index(drop=True)
    data["etiqueta"] = data["factor"].map(LABELS).fillna(data["factor"])

    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    y = np.arange(len(data))
    for position, record in data.iterrows():
        effect = float(record["efecto"])
        lower = float(record["inferior"])
        upper = float(record["superior"])
        color = POSITIVE if effect >= 0 else NEGATIVE
        ax.hlines(position, lower, upper, color=color, linewidth=2.2, alpha=0.9)
        ax.scatter(
            effect,
            position,
            s=65,
            facecolor=color if bool(record["significativo"]) else BACKGROUND,
            edgecolor=color,
            linewidth=2,
            zorder=3,
        )

    ax.axvline(0, color=FOREGROUND, linewidth=1.1)
    ax.set_yticks(y, data["etiqueta"])
    ax.invert_yaxis()
    ax.set_xlabel("Cambio aproximado en la TRM ante +1 desviación estándar del factor (%)")
    ax.tick_params(axis="y", length=0)
    clean_axis(ax)
    limit = max(abs(data["inferior"].min()), abs(data["superior"].max())) * 1.14
    ax.set_xlim(-limit, limit)

    legend = [
        Patch(facecolor=POSITIVE, label="TRM mayor · depreciación"),
        Patch(facecolor=NEGATIVE, label="TRM menor · apreciación"),
        Line2D(
            [0],
            [0],
            marker="o",
            color=FOREGROUND,
            markerfacecolor=FOREGROUND,
            linestyle="None",
            label="p < 0,05",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color=FOREGROUND,
            markerfacecolor=BACKGROUND,
            linestyle="None",
            label="intervalo cruza cero",
        ),
    ]
    ax.legend(
        handles=legend,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=4,
        frameon=False,
    )
    fig.suptitle(
        "Dirección y magnitud típica de las asociaciones",
        x=0.04,
        y=0.975,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.925,
        "El punto es el efecto estimado de un movimiento típico; la línea muestra el intervalo de confianza HAC del 95%.",
        color=MUTED,
        fontsize=12,
    )
    fig.text(
        0.04,
        0.018,
        "Los efectos están estandarizados para hacer comparables escalas distintas. Son asociaciones parciales del modelo, no efectos causales.",
        color=MUTED,
        fontsize=9.5,
    )
    fig.subplots_adjust(left=0.28, right=0.97, top=0.86, bottom=0.19)
    save(fig, "04_efectos_tipicos.png")


def ecm_record(
    data: pd.DataFrame,
    term: str,
    estimate_column: str,
    *,
    reverse: bool = False,
    multiplier: float = 1.0,
) -> dict[str, float | bool]:
    row = data.loc[data["termino"].eq(term)]
    if len(row) != 1:
        raise KeyError(f"Se esperaba un único término ECM para {term}.")
    record = row.iloc[0]
    estimate = float(record[estimate_column])
    lower = float(record["ic_95_inferior"])
    upper = float(record["ic_95_superior"])
    if reverse:
        estimate, lower, upper = -estimate, -upper, -lower
    return {
        "estimate": estimate * multiplier,
        "lower": lower * multiplier,
        "upper": upper * multiplier,
        "significant": float(record["p_valor"]) < 0.05,
    }


def plot_ecm_horizons(
    ax: plt.Axes,
    specifications: list[tuple[str, str, str | None]],
    short_run: pd.DataFrame,
    long_run: pd.DataFrame,
    *,
    multiplier: float,
    title: str,
    xlabel: str,
) -> None:
    y = np.arange(len(specifications))
    all_limits = [0.0]
    for position, (_, short_term, long_term) in enumerate(specifications):
        short = ecm_record(
            short_run,
            short_term,
            "coeficiente",
            multiplier=multiplier,
        )
        all_limits.extend([float(short["lower"]), float(short["upper"])])
        short_y = position - 0.13
        ax.hlines(
            short_y,
            float(short["lower"]),
            float(short["upper"]),
            color=BASE,
            linewidth=2.2,
        )
        ax.scatter(
            float(short["estimate"]),
            short_y,
            marker="o",
            s=62,
            facecolor=BASE if bool(short["significant"]) else BACKGROUND,
            edgecolor=BASE,
            linewidth=2,
            zorder=3,
        )

        if long_term is not None:
            long = ecm_record(
                long_run,
                long_term,
                "coeficiente_largo_plazo",
                reverse=True,
                multiplier=multiplier,
            )
            all_limits.extend([float(long["lower"]), float(long["upper"])])
            long_y = position + 0.13
            ax.hlines(
                long_y,
                float(long["lower"]),
                float(long["upper"]),
                color=EXPANDED,
                linewidth=2.2,
            )
            ax.scatter(
                float(long["estimate"]),
                long_y,
                marker="D",
                s=58,
                facecolor=EXPANDED if bool(long["significant"]) else BACKGROUND,
                edgecolor=EXPANDED,
                linewidth=2,
                zorder=3,
            )

    minimum, maximum = min(all_limits), max(all_limits)
    padding = max((maximum - minimum) * 0.10, 0.08)
    ax.set_xlim(minimum - padding, maximum + padding)
    ax.axvline(0, color=FOREGROUND, linewidth=1.0)
    ax.set_yticks(y, [item[0] for item in specifications])
    ax.invert_yaxis()
    ax.set_title(title, loc="left", fontweight="bold", pad=12)
    ax.set_xlabel(xlabel)
    ax.tick_params(axis="y", length=0)
    clean_axis(ax)


def chart_ecm(
    short_run: pd.DataFrame,
    long_run: pd.DataFrame,
    bounds: pd.DataFrame,
) -> None:
    elasticity_specs = [
        ("Dólar amplio", "D.ln_dolar_amplio.L0", "ln_dolar_amplio"),
        ("Remesas 12 meses", "D.ln_remesas_12m.L0", "ln_remesas_12m"),
        ("Petróleo Brent", "D.ln_brent.L0", "ln_brent"),
        ("VIX", "dln_vix", None),
    ]
    semi_specs = [
        ("Diferencial de tasas", "D.diferencial_tasas_pp.L0", "diferencial_tasas_pp"),
        ("Déficit fiscal", "D.deficit_fiscal_12m_pct_pib.L0", "deficit_fiscal_12m_pct_pib"),
    ]

    adjustment = ecm_record(short_run, "ln_trm.L1", "coeficiente")
    alpha = float(adjustment["estimate"])
    if not -1.0 < alpha < 0.0:
        raise ValueError("La velocidad de ajuste ECM debe estar entre −1 y 0.")
    half_life = float(np.log(0.5) / np.log(1.0 + alpha))
    bound = bounds.iloc[0]

    fig = plt.figure(figsize=(12.8, 7.2))
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=[1.18, 1.0],
        height_ratios=[1.04, 0.96],
        wspace=0.34,
        hspace=0.48,
    )
    ax_elasticities = fig.add_subplot(grid[:, 0])
    ax_semi = fig.add_subplot(grid[0, 1])
    ax_adjustment = fig.add_subplot(grid[1, 1])

    plot_ecm_horizons(
        ax_elasticities,
        elasticity_specs,
        short_run,
        long_run,
        multiplier=1.0,
        title="Elasticidades · variables en log",
        xlabel="Cambio de TRM ante +1% del factor (%)",
    )
    plot_ecm_horizons(
        ax_semi,
        semi_specs,
        short_run,
        long_run,
        multiplier=100.0,
        title="Semielasticidades · variables en p.p.",
        xlabel="Cambio aproximado de TRM ante +1 p.p. del indicador (%)",
    )

    months = np.arange(0, 25)
    remaining = np.power(1.0 + alpha, months) * 100.0
    alpha_lower = float(adjustment["lower"])
    alpha_upper = float(adjustment["upper"])
    remaining_lower = np.power(1.0 + alpha_lower, months) * 100.0
    remaining_upper = np.power(1.0 + alpha_upper, months) * 100.0
    half_life_lower = float(np.log(0.5) / np.log(1.0 + alpha_lower))
    half_life_upper = float(np.log(0.5) / np.log(1.0 + alpha_upper))
    ax_adjustment.plot(months, remaining, color=EXPANDED, linewidth=2.6)
    ax_adjustment.fill_between(
        months,
        remaining_lower,
        remaining_upper,
        color=EXPANDED,
        alpha=0.14,
    )
    ax_adjustment.axhline(50, color=GRID, linewidth=1.0)
    ax_adjustment.scatter(half_life, 50, color=POSITIVE, s=62, zorder=3)
    ax_adjustment.annotate(
        f"Semivida ≈ {es(half_life)} meses\nIC 95%: {es(half_life_lower)}–{es(half_life_upper)}",
        xy=(half_life, 50),
        xytext=(half_life + 2.0, 67),
        arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 1.0},
        color=FOREGROUND,
        fontweight="bold",
    )
    ax_adjustment.text(
        0.02,
        0.93,
        f"Se corrige {es(-alpha * 100)}% del desequilibrio por mes",
        transform=ax_adjustment.transAxes,
        va="top",
        color=FOREGROUND,
        fontweight="bold",
    )
    ax_adjustment.text(
        0.98,
        0.08,
        "Banda: IC 95% de la velocidad",
        transform=ax_adjustment.transAxes,
        ha="right",
        va="bottom",
        color=MUTED,
        fontsize=9,
    )
    ax_adjustment.set_xlim(0, 24)
    ax_adjustment.set_ylim(0, 105)
    ax_adjustment.set_title(
        "Corrección del desequilibrio", loc="left", fontweight="bold", pad=12
    )
    ax_adjustment.set_xlabel("Meses desde el choque")
    ax_adjustment.set_ylabel("Desequilibrio restante (%)")
    clean_axis(ax_adjustment, grid_axis="both")

    horizon_legend = [
        Line2D(
            [0], [0], marker="o", color=BASE, markerfacecolor=BASE,
            linestyle="None", label="Corto plazo"
        ),
        Line2D(
            [0], [0], marker="D", color=EXPANDED, markerfacecolor=EXPANDED,
            linestyle="None", label="Largo plazo exploratorio"
        ),
        Line2D(
            [0], [0], marker="o", color=FOREGROUND, markerfacecolor=BACKGROUND,
            linestyle="None", label="Intervalo cruza cero"
        ),
    ]
    fig.legend(
        handles=horizon_legend,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.045),
        ncol=3,
        frameon=False,
    )
    fig.suptitle(
        "ECM exploratorio: corto plazo, largo plazo y corrección",
        x=0.04,
        y=0.975,
        ha="left",
        fontsize=20,
        fontweight="bold",
    )
    fig.text(
        0.04,
        0.925,
        f"Bounds F = {es(float(bound['estadistico_f']), 3)} y p-valor I(1) = {es(float(bound['p_valor_i1']), 3)}: la cointegración no es concluyente al 5%.",
        color=MUTED,
        fontsize=12,
    )
    fig.text(
        0.04,
        0.015,
        "Puntos e intervalos HAC del 95%. El largo plazo invierte el signo del vector cointegrante normalizado para expresar la respuesta de la TRM; debe leerse solo como contraste exploratorio.",
        color=MUTED,
        fontsize=9.2,
    )
    fig.subplots_adjust(left=0.12, right=0.98, top=0.83, bottom=0.15)
    save(fig, "05_ecm_elasticidades.png")


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    weights = pd.read_csv(RESULTS / "pesos_explicativos_modelo_ampliado.csv")
    comparison = pd.read_csv(RESULTS / "comparacion_modelos.csv")
    validation = pd.read_csv(RESULTS / "validacion_metricas_modelo_ampliado.csv")
    base_predictions = pd.read_csv(RESULTS / "validacion_predicciones.csv")
    expanded_predictions = pd.read_csv(
        RESULTS / "validacion_predicciones_modelo_ampliado.csv"
    )
    coefficients = pd.read_csv(RESULTS / "coeficientes_modelo_ampliado.csv")
    contributions = pd.read_csv(RESULTS / "contribuciones_modelo_ampliado.csv")
    ecm_short = pd.read_csv(RESULTS / "coeficientes_corto_plazo_ecm.csv")
    ecm_long = pd.read_csv(RESULTS / "coeficientes_largo_plazo_ecm.csv")
    bounds = pd.read_csv(RESULTS / "bounds_resumen.csv")

    configure_style()
    chart_weights(weights)
    chart_performance(comparison, validation)
    chart_validation(base_predictions, expanded_predictions)
    chart_standardized_effects(weights, coefficients, contributions)
    chart_ecm(ecm_short, ecm_long, bounds)
    write_metadata()
    print(f"OK: 5 gráficos creados en {CHARTS}")


if __name__ == "__main__":
    main()
