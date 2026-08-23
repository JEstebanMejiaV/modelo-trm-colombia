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
]

IMAGE_FILES = [
    "01_pesos_explicativos.png",
    "02_desempeno_modelos.png",
    "03_validacion_trm.png",
    "04_efectos_tipicos.png",
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_metadata() -> None:
    metadata = {
        "version": 1,
        "generator": {
            "path": "src/build_charts.py",
            "sha256": sha256(Path(__file__).resolve()),
        },
        "sources": {
            path.relative_to(ROOT).as_posix(): sha256(path) for path in SOURCE_FILES
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

    configure_style()
    chart_weights(weights)
    chart_performance(comparison, validation)
    chart_validation(base_predictions, expanded_predictions)
    chart_standardized_effects(weights, coefficients, contributions)
    write_metadata()
    print(f"OK: 4 gráficos creados en {CHARTS}")


if __name__ == "__main__":
    main()
