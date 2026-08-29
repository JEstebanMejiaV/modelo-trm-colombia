from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from .config import (
    SHAPLEY_BOOTSTRAP_REPLICATIONS,
    SHAPLEY_BOOTSTRAP_BLOCK_MONTHS,
    SHAPLEY_BOOTSTRAP_PERMUTATIONS,
    SHAPLEY_BOOTSTRAP_SEED,
    SAMPLE_START,
    SAMPLE_END,
    SelectedDifferenceModel,
)
from .transforms import make_timed_difference_design, select_timed_difference_model


def exact_shapley_r2(
    selected: SelectedDifferenceModel,
    factor_specs: dict[str, dict[str, object]],
    robust_coefficients: pd.DataFrame,
) -> pd.DataFrame:
    """Descompone exactamente el incremento del R2 mediante Shapley/LMG."""
    from .transforms import design_term_name

    factor_columns = {
        name: [design_term_name(component, lag) for component, lag in spec["terminos"]]
        for name, spec in factor_specs.items()
    }
    assigned = {column for columns in factor_columns.values() for column in columns}
    base_columns = [column for column in selected.x.columns if column not in assigned]
    missing = assigned.difference(selected.x.columns)
    if missing:
        raise ValueError(f"Faltan terminos para Shapley: {sorted(missing)}")

    y = selected.y.to_numpy(dtype=float)
    total_ss = float(np.square(y - y.mean()).sum())

    def r_squared(columns: list[str]) -> float:
        matrix = selected.x[columns].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(matrix, y, rcond=None)
        residual = y - matrix @ beta
        return 1.0 - float(np.square(residual).sum()) / total_ss

    names = list(factor_specs)
    player_count = len(names)
    cache: dict[int, float] = {}
    for mask in range(1 << player_count):
        columns = list(base_columns)
        for player, factor_name in enumerate(names):
            if mask & (1 << player):
                columns.extend(factor_columns[factor_name])
        cache[mask] = r_squared(columns)

    empty_r2 = cache[0]
    full_r2 = cache[(1 << player_count) - 1]
    incremental_r2 = full_r2 - empty_r2
    coefficient_lookup = robust_coefficients.set_index("termino")
    rows: list[dict[str, object]] = []
    for player, factor_name in enumerate(names):
        shapley = 0.0
        for mask in range(1 << player_count):
            if mask & (1 << player):
                continue
            subset_size = mask.bit_count()
            weight = (
                math.factorial(subset_size)
                * math.factorial(player_count - subset_size - 1)
                / math.factorial(player_count)
            )
            shapley += weight * (cache[mask | (1 << player)] - cache[mask])

        terms = factor_columns[factor_name]
        coefficient = math.nan
        p_value = math.nan
        if len(terms) == 1 and terms[0] in coefficient_lookup.index:
            coefficient = float(coefficient_lookup.loc[terms[0], "coeficiente"])
            p_value = float(coefficient_lookup.loc[terms[0], "p_valor"])
        rows.append(
            {
                "factor": factor_name,
                "grupo": factor_specs[factor_name]["grupo"],
                "terminos": ", ".join(terms),
                "coeficiente_modelo": coefficient,
                "p_valor_hac": p_value,
                "shapley_r2": shapley,
                "aporte_r2_puntos_porcentuales": 100.0 * shapley,
                "peso_entre_factores_pct": 100.0 * shapley / incremental_r2,
                "peso_r2_total_pct": 100.0 * shapley / full_r2,
                "r2_base": empty_r2,
                "r2_completo": full_r2,
                "r2_incremental": incremental_r2,
            }
        )

    result = pd.DataFrame(rows).sort_values("shapley_r2", ascending=False).reset_index(drop=True)
    if not np.isclose(result["shapley_r2"].sum(), incremental_r2, atol=1e-10):
        raise AssertionError("La suma Shapley no cierra contra el incremento del R2.")
    if not np.isclose(result["peso_entre_factores_pct"].sum(), 100.0, atol=1e-8):
        raise AssertionError("Los pesos Shapley no suman 100%.")
    return result


def factor_columns_from_specs(
    factor_specs: dict[str, dict[str, object]],
) -> dict[str, list[str]]:
    from .transforms import design_term_name

    return {
        name: [design_term_name(component, lag) for component, lag in spec["terminos"]]
        for name, spec in factor_specs.items()
    }


def moving_block_indices(
    observations: int, block_months: int, rng: np.random.Generator
) -> np.ndarray:
    """Bootstrap circular de bloques móviles para conservar dependencia mensual local."""
    blocks = math.ceil(observations / block_months)
    starts = rng.integers(0, observations, size=blocks)
    offsets = np.arange(block_months)
    return ((starts[:, None] + offsets[None, :]) % observations).ravel()[:observations]


def permutation_shapley_weights(
    y: np.ndarray,
    x: pd.DataFrame,
    factor_specs: dict[str, dict[str, object]],
    permutations: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Aproxima Shapley con permutaciones antitéticas dentro de una réplica."""
    factor_columns = factor_columns_from_specs(factor_specs)
    assigned = {column for columns in factor_columns.values() for column in columns}
    base_columns = [column for column in x.columns if column not in assigned]
    names = list(factor_specs)
    total_ss = float(np.square(y - y.mean()).sum())
    matrix = x.to_numpy(dtype=float)
    gram = matrix.T @ matrix
    cross = matrix.T @ y
    y_square = float(y @ y)
    column_positions = {column: position for position, column in enumerate(x.columns)}
    base_positions = [column_positions[column] for column in base_columns]
    factor_positions = [
        [column_positions[column] for column in factor_columns[name]] for name in names
    ]
    cache: dict[int, float] = {}

    def r_squared(mask: int) -> float:
        if mask in cache:
            return cache[mask]
        positions = list(base_positions)
        for player, columns in enumerate(factor_positions):
            if mask & (1 << player):
                positions.extend(columns)
        sub_gram = gram[np.ix_(positions, positions)]
        sub_cross = cross[positions]
        beta, *_ = np.linalg.lstsq(sub_gram, sub_cross, rcond=None)
        rss = max(0.0, y_square - float(beta @ sub_cross))
        value = 1.0 - rss / total_ss
        cache[mask] = value
        return value

    contributions = np.zeros(len(names), dtype=float)
    evaluated = 0
    for _ in range(math.ceil(permutations / 2)):
        random_order = rng.permutation(len(names))
        for order in (random_order, random_order[::-1]):
            if evaluated >= permutations:
                break
            mask = 0
            previous_r2 = r_squared(mask)
            for player in order:
                mask |= 1 << int(player)
                current_r2 = r_squared(mask)
                contributions[int(player)] += current_r2 - previous_r2
                previous_r2 = current_r2
            evaluated += 1
    contributions /= evaluated
    incremental = float(contributions.sum())
    if incremental <= 0:
        raise ValueError("El R² incremental bootstrap no es positivo.")
    return 100.0 * contributions / incremental


def block_bootstrap_shapley(
    selected: SelectedDifferenceModel,
    factor_specs: dict[str, dict[str, object]],
    point_shapley: pd.DataFrame,
) -> pd.DataFrame:
    """Intervalos percentiles de pesos Shapley mediante bootstrap por bloques."""
    rng = np.random.default_rng(SHAPLEY_BOOTSTRAP_SEED)
    bootstrap_weights: list[np.ndarray] = []
    for _ in range(SHAPLEY_BOOTSTRAP_REPLICATIONS):
        sample_positions = moving_block_indices(
            len(selected.y), SHAPLEY_BOOTSTRAP_BLOCK_MONTHS, rng
        )
        y_bootstrap = selected.y.to_numpy(dtype=float)[sample_positions]
        x_bootstrap = selected.x.iloc[sample_positions].reset_index(drop=True)
        bootstrap_weights.append(
            permutation_shapley_weights(
                y_bootstrap,
                x_bootstrap,
                factor_specs,
                SHAPLEY_BOOTSTRAP_PERMUTATIONS,
                rng,
            )
        )
    draws = np.vstack(bootstrap_weights)
    point_lookup = point_shapley.set_index("factor")
    names = list(factor_specs)
    top_three = np.argsort(-draws, axis=1)[:, :3]
    rows = []
    for player, factor in enumerate(names):
        values = draws[:, player]
        rows.append(
            {
                "factor": factor,
                "grupo": factor_specs[factor]["grupo"],
                "peso_puntual_pct": float(
                    point_lookup.loc[factor, "peso_entre_factores_pct"]
                ),
                "peso_bootstrap_media_pct": float(values.mean()),
                "peso_bootstrap_mediana_pct": float(np.median(values)),
                "ic_95_inferior_pct": float(np.quantile(values, 0.025)),
                "ic_95_superior_pct": float(np.quantile(values, 0.975)),
                "probabilidad_top3_pct": float(
                    100.0 * np.mean(np.any(top_three == player, axis=1))
                ),
                "replicas_validas": SHAPLEY_BOOTSTRAP_REPLICATIONS,
                "bloque_meses": SHAPLEY_BOOTSTRAP_BLOCK_MONTHS,
                "permutaciones_por_replica": SHAPLEY_BOOTSTRAP_PERMUTATIONS,
                "semilla": SHAPLEY_BOOTSTRAP_SEED,
            }
        )
    return pd.DataFrame(rows).sort_values("peso_puntual_pct", ascending=False).reset_index(drop=True)


def subsample_stability(
    selected: SelectedDifferenceModel,
    factor_specs: dict[str, dict[str, object]],
    point_shapley: pd.DataFrame,
    full_coefficients: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reestima coeficientes y Shapley en cortes temporales predefinidos.

    La comparación de signos se hace para todos los términos de cada factor.
    Para un factor compuesto no se publica el primer coeficiente como si fuera
    el coeficiente del factor: se conservan los detalles por término y el
    indicador de coincidencia del factor exige que coincidan todos sus términos.
    """
    from .estimation import tidy_robust_ols

    midpoint = len(selected.y) // 2
    masks = [
        ("Muestra completa", np.ones(len(selected.y), dtype=bool)),
        ("Primera mitad", np.arange(len(selected.y)) < midpoint),
        ("Segunda mitad", np.arange(len(selected.y)) >= midpoint),
        ("Prepandemia", selected.y.index <= pd.Timestamp("2019-12-01")),
        ("2020 en adelante", selected.y.index >= pd.Timestamp("2020-01-01")),
    ]
    full_weights = point_shapley.set_index("factor")["peso_entre_factores_pct"]
    full_signs = (
        full_coefficients.set_index("termino")["coeficiente"]
        .apply(np.sign)
        .to_dict()
    )
    factor_columns = factor_columns_from_specs(factor_specs)
    detail_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for label, mask in masks:
        y_sub = selected.y.loc[mask]
        x_sub = selected.x.loc[mask]
        result_sub = sm.OLS(y_sub, x_sub).fit()
        sub_selected = SelectedDifferenceModel(
            p=selected.p, q=selected.q, result=result_sub, y=y_sub, x=x_sub
        )
        _, coefficients_sub = tidy_robust_ols(result_sub, maxlags=6)
        if label == "Muestra completa":
            shapley_sub = point_shapley.copy()
            coefficients_sub = full_coefficients.copy()
        else:
            shapley_sub = exact_shapley_r2(
                sub_selected, factor_specs, coefficients_sub
            )
        weights_sub = shapley_sub.set_index("factor")["peso_entre_factores_pct"]
        ranks_sub = weights_sub.rank(ascending=False, method="min")
        differences = weights_sub - full_weights
        coefficient_lookup = coefficients_sub.set_index("termino")
        factor_sign_matches: list[bool] = []
        term_matches_total = 0
        terms_evaluated_total = 0
        for factor, terms in factor_columns.items():
            term_coefficients: list[float] = []
            term_p_values: list[float] = []
            term_sign_matches: list[bool] = []
            for term in terms:
                coefficient = float(coefficient_lookup.loc[term, "coeficiente"])
                p_value = float(coefficient_lookup.loc[term, "p_valor"])
                term_coefficients.append(coefficient)
                term_p_values.append(p_value)
                term_sign_matches.append(bool(np.sign(coefficient) == full_signs[term]))
            terms_evaluated = len(terms)
            terms_matching = int(sum(term_sign_matches))
            factor_sign_match = terms_matching == terms_evaluated
            factor_sign_matches.append(factor_sign_match)
            term_matches_total += terms_matching
            terms_evaluated_total += terms_evaluated
            coefficient = term_coefficients[0] if terms_evaluated == 1 else np.nan
            p_value = term_p_values[0] if terms_evaluated == 1 else np.nan
            detail_rows.append(
                {
                    "submuestra": label,
                    "inicio": y_sub.index.min().strftime("%Y-%m-%d"),
                    "fin": y_sub.index.max().strftime("%Y-%m-%d"),
                    "observaciones": len(y_sub),
                    "r2": float(result_sub.rsquared),
                    "r2_ajustado": float(result_sub.rsquared_adj),
                    "factor": factor,
                    "grupo": factor_specs[factor]["grupo"],
                    "coeficiente": coefficient,
                    "p_valor_hac": p_value,
                    "coeficientes_terminos": "; ".join(
                        f"{term}={value:.12g}" for term, value in zip(terms, term_coefficients)
                    ),
                    "p_valores_terminos": "; ".join(
                        f"{term}={value:.12g}" for term, value in zip(terms, term_p_values)
                    ),
                    "terminos_evaluados": terms_evaluated,
                    "terminos_con_signo_coincidente": terms_matching,
                    "signos_terminos": "; ".join(
                        f"{term}={'igual' if match else 'distinto'}"
                        for term, match in zip(terms, term_sign_matches)
                    ),
                    "todos_los_terminos_mismo_signo": factor_sign_match,
                    "shapley_r2": float(shapley_sub.set_index("factor").loc[factor, "shapley_r2"]),
                    "peso_entre_factores_pct": float(weights_sub[factor]),
                    "rango_peso": int(ranks_sub[factor]),
                    "signo_coincide_muestra_completa": factor_sign_match,
                    "diferencia_peso_vs_completa_pp": float(differences[factor]),
                }
            )
        full_ranks = full_weights.rank(ascending=False, method="min")
        rank_correlation = float(
            stats.spearmanr(
                full_ranks.to_numpy(),
                ranks_sub.reindex(full_ranks.index).to_numpy(),
            ).statistic
        )
        summary_rows.append(
            {
                "submuestra": label,
                "inicio": y_sub.index.min().strftime("%Y-%m-%d"),
                "fin": y_sub.index.max().strftime("%Y-%m-%d"),
                "observaciones": len(y_sub),
                "r2_ajustado": float(result_sub.rsquared_adj),
                "correlacion_spearman_rangos_vs_completa": rank_correlation,
                "mediana_diferencia_abs_peso_pp": float(differences.abs().median()),
                "max_diferencia_abs_peso_pp": float(differences.abs().max()),
                "factores_mismo_signo_de_{}".format(len(factor_specs)): int(sum(factor_sign_matches)),
                "terminos_mismo_signo": term_matches_total,
                "terminos_evaluados": terms_evaluated_total,
            }
        )
    return pd.DataFrame(detail_rows), pd.DataFrame(summary_rows)
