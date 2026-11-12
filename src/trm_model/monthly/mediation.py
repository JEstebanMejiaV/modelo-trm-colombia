"""Diagnóstico de canales dinámicos mediados para la explicación mensual.

Este módulo estima una red observacional de ecuaciones por etapas. La red hace
explícitos los nodos, las aristas y los rezagos; no convierte la secuencia
cronológica en identificación causal. Los productos publicados separan:

* coeficientes de cada ecuación de etapa;
* productos de coeficientes por ruta;
* incertidumbre de esos productos con un bootstrap conjunto por bloques; y
* valores ajustados de los mediadores y la contabilidad de la ecuación final.

La ecuación final puede recibir el diseño del marco macroeconómico integral
vigente. Así, el diagnóstico no cambia los 14 jugadores, el Shapley ni los CSV
existentes.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd
import statsmodels.api as sm

from trm_model.features.monthly_transforms import design_term_name


DYNAMIC_MEDIATION_WARNING = (
    "Asociación dinámica compatible con una ruta de transmisión bajo la "
    "especificación observacional; no es un efecto causal, identificación "
    "estructural ni escenario contrafactual."
)
DYNAMIC_MEDIATION_METHOD = (
    "Ecuaciones de etapa OLS-HAC con nodos, aristas y rezagos preespecificados; "
    "productos de coeficientes y bootstrap circular conjunto por bloques mensuales."
)
MEDIATION_BOOTSTRAP_REPLICATIONS = 200
MEDIATION_BOOTSTRAP_BLOCK_MONTHS = 12
MEDIATION_BOOTSTRAP_SEED = 20260823
MEDIATION_OUTPUTS = (
    "results/explicacion/mediacion_dinamica_coeficientes_etapas.csv",
    "results/explicacion/mediacion_dinamica_rutas.csv",
    "results/explicacion/mediacion_dinamica_bootstrap.csv",
    "results/explicacion/mediacion_dinamica_contribuciones.csv",
)

COEFFICIENT_COLUMNS = [
    "ecuacion_id",
    "objetivo",
    "objetivo_label",
    "tipo_ecuacion",
    "edge_id",
    "origen",
    "destino",
    "origen_label",
    "termino",
    "rezago_meses",
    "tipo_termino",
    "coeficiente",
    "error_estandar_hac",
    "p_valor_hac",
    "ic_95_inferior",
    "ic_95_superior",
    "signo_coeficiente",
    "observaciones",
    "muestra_inicio",
    "muestra_fin",
    "advertencia_interpretacion",
]
PATH_COLUMNS = [
    "ruta_id",
    "origen",
    "origen_label",
    "destino",
    "nodos",
    "nodos_legibles",
    "aristas",
    "tipo_ruta",
    "n_etapas",
    "rezago_total_meses",
    "termino_origen",
    "producto_coeficientes",
    "signo_ruta",
    "observaciones",
    "muestra_inicio",
    "muestra_fin",
    "advertencia_interpretacion",
]
BOOTSTRAP_COLUMNS = [
    "ruta_id",
    "origen",
    "destino",
    "tipo_ruta",
    "producto_puntual",
    "producto_bootstrap_mediana",
    "ic_95_inferior",
    "ic_95_superior",
    "probabilidad_signo_coincidente_pct",
    "replicas_solicitadas",
    "replicas_validas",
    "bloque_meses",
    "semilla",
    "advertencia_interpretacion",
]
CONTRIBUTION_REQUIRED_COLUMNS = [
    "fecha",
    "D.ln_trm_observada",
    "ajuste_total",
    "suma_ecuacion_final",
    "cierre_contable",
    "suma_rutas_diagnosticas",
]


@dataclass(frozen=True)
class MediationNode:
    """Nodo de la red y columna transformada que lo representa."""

    key: str
    component: str
    label: str
    role: str = "mediator"

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.component.strip() or not self.label.strip():
            raise ValueError("Un nodo de mediación requiere key, component y label.")
        if self.role not in {"source", "mediator", "outcome"}:
            raise ValueError(f"Rol de nodo no reconocido: {self.role!r}.")


@dataclass(frozen=True)
class MediationEdge:
    """Arista dirigida; ``lag`` es el rezago de la fuente en la ecuación destino."""

    edge_id: str
    source: str
    target: str
    lag: int
    label: str = ""

    def __post_init__(self) -> None:
        if not self.edge_id.strip() or not self.source.strip() or not self.target.strip():
            raise ValueError("Una arista de mediación requiere edge_id, source y target.")
        if isinstance(self.lag, bool) or int(self.lag) != self.lag or self.lag < 0:
            raise ValueError("Los rezagos de mediación deben ser enteros no negativos.")
        object.__setattr__(self, "lag", int(self.lag))


@dataclass(frozen=True)
class MediationSpec:
    """Registro completo y estable de la red de mediación."""

    nodes: tuple[MediationNode, ...]
    edges: tuple[MediationEdge, ...]
    outcome: str = "trm"
    path_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes))
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "path_sources", tuple(self.path_sources))


@dataclass
class _Equation:
    equation_id: str
    target: str
    y: pd.Series
    x: pd.DataFrame
    edge_terms: dict[str, str]
    result: object | None = None


@dataclass(frozen=True)
class _Route:
    route_id: str
    edge_ids: tuple[str, ...]
    node_keys: tuple[str, ...]
    source: str
    total_lag: int


@dataclass
class DynamicMediationResult:
    """Tablas y metadata de una corrida de mediación dinámica."""

    coefficients: pd.DataFrame
    paths: pd.DataFrame
    bootstrap: pd.DataFrame
    contributions: pd.DataFrame
    common_index: pd.DatetimeIndex
    metadata: dict[str, object]


_DEFAULT_NODES = (
    MediationNode(
        "deficit",
        "D.deficit_fiscal_12m_pct_pib",
        "Déficit fiscal",
        "source",
    ),
    MediationNode("rates", "D.diferencial_tasas_pp", "Diferencial de tasas"),
    MediationNode("embig", "D.embig_colombia_pp", "EMBIG Colombia"),
    MediationNode("bei", "D.diferencial_bei_5y_pp", "Diferencial BEI 5 años"),
    MediationNode("flows", "D.asinh_flujos_capital", "Flujos netos de capital"),
    MediationNode("trm", "D.ln_trm", "Δln(TRM)", "outcome"),
)

# Los rezagos declaran una secuencia temporal compatible con la ecuación
# observacional. L0 en EMBIG -> TRM se conserva porque el modelo histórico es
# ex post/nowcast; la advertencia no causal forma parte de todas las tablas.
_DEFAULT_EDGES = (
    MediationEdge("deficit_to_rates", "deficit", "rates", 1, "déficit → tasas"),
    MediationEdge("deficit_to_embig", "deficit", "embig", 1, "déficit → EMBIG"),
    MediationEdge("rates_to_embig", "rates", "embig", 1, "tasas → EMBIG"),
    MediationEdge("rates_to_bei", "rates", "bei", 1, "tasas → BEI"),
    MediationEdge("embig_to_bei", "embig", "bei", 1, "EMBIG → BEI"),
    MediationEdge("rates_to_flows", "rates", "flows", 1, "tasas → flujos"),
    MediationEdge("embig_to_flows", "embig", "flows", 1, "EMBIG → flujos"),
    MediationEdge("deficit_to_trm", "deficit", "trm", 1, "déficit → TRM"),
    MediationEdge("rates_to_trm", "rates", "trm", 1, "tasas → TRM"),
    MediationEdge("embig_to_trm", "embig", "trm", 0, "EMBIG → TRM"),
    MediationEdge("bei_to_trm", "bei", "trm", 1, "BEI → TRM"),
    MediationEdge("flows_to_trm", "flows", "trm", 1, "flujos → TRM"),
)

DEFAULT_MEDIATION_SPEC = MediationSpec(
    nodes=_DEFAULT_NODES,
    edges=_DEFAULT_EDGES,
    outcome="trm",
    path_sources=("deficit", "rates", "embig", "bei", "flows"),
)


def validate_mediation_spec(spec: MediationSpec) -> tuple[str, ...]:
    """Valida nodos, rezagos y DAG; devuelve el orden topológico estable."""
    if not isinstance(spec, MediationSpec):
        raise TypeError("spec debe ser una instancia de MediationSpec.")
    node_keys = [node.key for node in spec.nodes]
    if len(node_keys) != len(set(node_keys)):
        raise ValueError("La especificación repite keys de nodos.")
    nodes = set(node_keys)
    if spec.outcome not in nodes:
        raise ValueError(f"El nodo de resultado no existe: {spec.outcome!r}.")
    outcome_nodes = [node.key for node in spec.nodes if node.role == "outcome"]
    if outcome_nodes != [spec.outcome]:
        raise ValueError(
            "La especificación debe tener exactamente un nodo outcome y debe coincidir "
            "con spec.outcome."
        )
    if len({node.component for node in spec.nodes}) != len(spec.nodes):
        raise ValueError("Cada nodo debe tener un componente transformado distinto.")
    edge_ids = [edge.edge_id for edge in spec.edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("La especificación repite edge_id.")
    incoming: dict[str, list[MediationEdge]] = defaultdict(list)
    adjacency: dict[str, list[str]] = defaultdict(list)
    edge_terms: set[tuple[str, str]] = set()
    for edge in spec.edges:
        if edge.source not in nodes or edge.target not in nodes:
            raise ValueError(
                f"La arista {edge.edge_id!r} referencia un nodo inexistente: "
                f"{edge.source!r} -> {edge.target!r}."
            )
        if edge.source == edge.target:
            raise ValueError(f"La arista {edge.edge_id!r} forma un auto-ciclo.")
        if edge.lag < 0:
            raise ValueError(f"La arista {edge.edge_id!r} tiene un rezago futuro.")
        term_key = (edge.target, design_term_name(_node_by_key(spec, edge.source).component, edge.lag))
        if term_key in edge_terms:
            raise ValueError(
                f"La ecuación de {edge.target!r} repite el término {term_key[1]!r}."
            )
        edge_terms.add(term_key)
        incoming[edge.target].append(edge)
        adjacency[edge.source].append(edge.target)

    declared_sources = spec.path_sources or tuple(
        node.key for node in spec.nodes if node.key != spec.outcome
    )
    unknown_sources = set(declared_sources) - nodes
    if unknown_sources:
        raise ValueError(f"Las fuentes de rutas no existen: {sorted(unknown_sources)}.")
    if spec.outcome in declared_sources:
        raise ValueError("El outcome no puede ser una fuente de rutas.")

    position = {key: index for index, key in enumerate(node_keys)}
    indegree = {key: 0 for key in node_keys}
    for source, targets in adjacency.items():
        del source
        for target in targets:
            indegree[target] += 1
    queue = deque(sorted((key for key, degree in indegree.items() if degree == 0), key=position.get))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for target in sorted(adjacency.get(current, []), key=position.get):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(order) != len(node_keys):
        cyclic = sorted(key for key, degree in indegree.items() if degree > 0)
        raise ValueError(f"La red de mediación debe ser acíclica; ciclo en {cyclic}.")
    return tuple(order)


def _node_by_key(spec: MediationSpec, key: str) -> MediationNode:
    for node in spec.nodes:
        if node.key == key:
            return node
    raise KeyError(key)


def _edge_by_id(spec: MediationSpec) -> dict[str, MediationEdge]:
    return {edge.edge_id: edge for edge in spec.edges}


def _normalise_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    result = frame.copy()
    if "fecha" in result.columns:
        result["fecha"] = pd.to_datetime(result["fecha"], errors="raise")
        result = result.set_index("fecha")
    try:
        result.index = pd.DatetimeIndex(pd.to_datetime(result.index, errors="raise"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} debe tener un índice mensual convertible a fecha.") from error
    if result.index.has_duplicates:
        raise ValueError(f"{label} repite fechas.")
    return result.sort_index()


def _add_constant(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "const" not in result.columns:
        result.insert(0, "const", 1.0)
    return result


def _numeric_series(series: pd.Series, label: str) -> pd.Series:
    result = pd.to_numeric(series, errors="coerce")
    if result.index.has_duplicates:
        raise ValueError(f"{label} repite fechas.")
    return result


def _numeric_frame(frame: pd.DataFrame, label: str) -> pd.DataFrame:
    result = frame.apply(pd.to_numeric, errors="coerce")
    if result.columns.duplicated().any():
        raise ValueError(f"{label} repite términos.")
    return result


def _build_equations(
    components: pd.DataFrame,
    spec: MediationSpec,
    topological_order: tuple[str, ...],
    *,
    outcome_y: pd.Series | None,
    outcome_design: pd.DataFrame | None,
) -> list[_Equation]:
    nodes = {node.key: node for node in spec.nodes}
    incoming: dict[str, list[MediationEdge]] = defaultdict(list)
    for edge in spec.edges:
        incoming[edge.target].append(edge)
    outcome_y_frame = None if outcome_y is None else _numeric_series(outcome_y, "outcome_y")
    outcome_x_frame = None if outcome_design is None else _numeric_frame(
        _normalise_frame(outcome_design, "outcome_design"), "outcome_design"
    )
    equations: list[_Equation] = []
    for target in topological_order:
        target_edges = incoming.get(target, [])
        if not target_edges:
            continue
        target_node = nodes[target]
        if target == spec.outcome and outcome_x_frame is not None:
            y = outcome_y_frame if outcome_y_frame is not None else _numeric_series(
                components[target_node.component], target_node.component
            )
            x = outcome_x_frame.copy()
            edge_terms: dict[str, str] = {}
            for edge in target_edges:
                source_component = nodes[edge.source].component
                term = design_term_name(source_component, edge.lag)
                if term not in x.columns:
                    raise ValueError(
                        f"El diseño de la ecuación final no contiene la arista "
                        f"{edge.edge_id!r} como {term!r}."
                    )
                edge_terms[edge.edge_id] = term
            x = _add_constant(x)
        else:
            y = _numeric_series(components[target_node.component], target_node.component)
            x = pd.DataFrame(index=components.index)
            edge_terms = {}
            for edge in target_edges:
                source_component = nodes[edge.source].component
                if source_component not in components.columns:
                    raise KeyError(
                        f"Falta el componente {source_component!r} de la arista {edge.edge_id!r}."
                    )
                term = design_term_name(source_component, edge.lag)
                if term in x.columns:
                    raise ValueError(f"La ecuación {target!r} repite el término {term!r}.")
                x[term] = components[source_component].shift(edge.lag)
                edge_terms[edge.edge_id] = term
            x = _add_constant(x)
        equations.append(
            _Equation(
                equation_id=f"stage_{target}" if target != spec.outcome else "final_trm",
                target=target,
                y=y.rename(target_node.component),
                x=x,
                edge_terms=edge_terms,
            )
        )
    if not any(equation.target == spec.outcome for equation in equations):
        raise ValueError("La red no tiene una ecuación para el nodo outcome.")
    return equations


def _common_index(
    equations: list[_Equation],
    requested: pd.Index | None,
) -> pd.DatetimeIndex:
    if not equations:
        raise ValueError("La red no contiene ecuaciones estimables.")
    common = equations[0].y.index
    if requested is not None:
        requested_dates = pd.DatetimeIndex(pd.to_datetime(requested, errors="raise"))
        common = common.intersection(requested_dates)
    for equation in equations:
        equation_index = equation.y.index.intersection(equation.x.index)
        y_values = equation.y.reindex(equation_index)
        x_numeric = _numeric_frame(equation.x.reindex(equation_index), equation.equation_id)
        valid = y_values.notna() & np.isfinite(y_values.to_numpy(dtype=float))
        valid &= x_numeric.notna().all(axis=1).to_numpy()
        valid &= np.isfinite(x_numeric.to_numpy(dtype=float)).all(axis=1)
        common = common.intersection(equation_index[valid])
    common = pd.DatetimeIndex(common).sort_values()
    if common.empty:
        raise ValueError("Las ecuaciones de mediación no comparten observaciones completas.")
    max_parameters = max(equation.x.shape[1] for equation in equations)
    if len(common) <= max_parameters:
        raise ValueError(
            "La muestra común de mediación no tiene observaciones suficientes: "
            f"{len(common)} para hasta {max_parameters} parámetros."
        )
    for equation in equations:
        equation.y = equation.y.reindex(common).astype(float)
        equation.x = _numeric_frame(equation.x.reindex(common), equation.equation_id).astype(float)
    return common


def _fit_hac(y: pd.Series, x: pd.DataFrame, maxlags: int) -> object:
    lag = min(max(0, int(maxlags)), max(0, len(y) - 1))
    return sm.OLS(y, x, missing="raise").fit(
        cov_type="HAC",
        cov_kwds={"maxlags": lag, "use_correction": True},
        use_t=True,
    )


def _sign_label(value: float) -> str:
    if not np.isfinite(value) or np.isclose(value, 0.0):
        return "sin signo definido"
    return "positivo" if value > 0 else "negativo"


def _safe_column(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z]+", "_", str(text)).strip("_")
    return value or "termino"


def _enumerate_routes(spec: MediationSpec) -> list[_Route]:
    edges_by_source: dict[str, list[MediationEdge]] = defaultdict(list)
    for edge in spec.edges:
        edges_by_source[edge.source].append(edge)
    sources = spec.path_sources or tuple(
        node.key for node in spec.nodes if node.key != spec.outcome
    )
    routes: list[_Route] = []

    def visit(source: str, current: str, edge_ids: tuple[str, ...], nodes: tuple[str, ...], lag: int) -> None:
        for edge in edges_by_source.get(current, []):
            if edge.target in nodes:
                continue
            next_edges = (*edge_ids, edge.edge_id)
            next_nodes = (*nodes, edge.target)
            next_lag = lag + edge.lag
            if edge.target == spec.outcome:
                route_id = "ruta_" + "_".join(next_edges)
                routes.append(
                    _Route(route_id, next_edges, next_nodes, source, next_lag)
                )
            else:
                visit(source, edge.target, next_edges, next_nodes, next_lag)

    for source in sources:
        if source == spec.outcome:
            continue
        visit(source, source, (), (source,), 0)
    return routes


def _coefficient_rows(
    equations: list[_Equation],
    spec: MediationSpec,
    common: pd.DatetimeIndex,
    *,
    hac_maxlags: int,
) -> tuple[pd.DataFrame, dict[str, float]]:
    nodes = {node.key: node for node in spec.nodes}
    edges = _edge_by_id(spec)
    edge_coefficients: dict[str, float] = {}
    rows: list[dict[str, object]] = []
    for equation in equations:
        equation.result = _fit_hac(equation.y, equation.x, hac_maxlags)
        result = equation.result
        params = pd.Series(result.params, index=equation.x.columns)
        bse = pd.Series(result.bse, index=equation.x.columns)
        pvalues = pd.Series(result.pvalues, index=equation.x.columns)
        interval = pd.DataFrame(result.conf_int(alpha=0.05), index=equation.x.columns)
        target_node = nodes[equation.target]
        mapped_edges = {term: edge_id for edge_id, term in equation.edge_terms.items()}
        for term in equation.x.columns:
            edge_id = mapped_edges.get(term, "")
            edge = edges.get(edge_id)
            source_node = nodes[edge.source] if edge is not None else None
            coefficient = float(params[term])
            if edge is not None:
                edge_coefficients[edge_id] = coefficient
            rows.append(
                {
                    "ecuacion_id": equation.equation_id,
                    "objetivo": equation.target,
                    "objetivo_label": target_node.label,
                    "tipo_ecuacion": "ecuacion_final" if equation.target == spec.outcome else "etapa",
                    "edge_id": edge_id,
                    "origen": edge.source if edge is not None else "",
                    "destino": edge.target if edge is not None else equation.target,
                    "origen_label": source_node.label if source_node is not None else "",
                    "termino": term,
                    "rezago_meses": edge.lag if edge is not None else np.nan,
                    "tipo_termino": "arista" if edge is not None else "control",
                    "coeficiente": coefficient,
                    "error_estandar_hac": float(bse[term]),
                    "p_valor_hac": float(pvalues[term]),
                    "ic_95_inferior": float(interval.loc[term, 0]),
                    "ic_95_superior": float(interval.loc[term, 1]),
                    "signo_coeficiente": _sign_label(coefficient),
                    "observaciones": int(len(common)),
                    "muestra_inicio": common.min().strftime("%Y-%m-%d"),
                    "muestra_fin": common.max().strftime("%Y-%m-%d"),
                    "advertencia_interpretacion": DYNAMIC_MEDIATION_WARNING,
                }
            )
    return pd.DataFrame(rows, columns=COEFFICIENT_COLUMNS), edge_coefficients


def _path_table(
    routes: list[_Route],
    spec: MediationSpec,
    edge_coefficients: Mapping[str, float],
    common: pd.DatetimeIndex,
) -> pd.DataFrame:
    nodes = {node.key: node for node in spec.nodes}
    edge_lookup = _edge_by_id(spec)
    rows: list[dict[str, object]] = []
    for route in routes:
        product = float(np.prod([edge_coefficients[edge_id] for edge_id in route.edge_ids]))
        source_component = nodes[route.source].component
        rows.append(
            {
                "ruta_id": route.route_id,
                "origen": route.source,
                "origen_label": nodes[route.source].label,
                "destino": spec.outcome,
                "nodos": " -> ".join(route.node_keys),
                "nodos_legibles": " -> ".join(nodes[key].label for key in route.node_keys),
                "aristas": " -> ".join(route.edge_ids),
                "tipo_ruta": "directa" if len(route.edge_ids) == 1 else "indirecta",
                "n_etapas": len(route.edge_ids),
                "rezago_total_meses": route.total_lag,
                "termino_origen": design_term_name(source_component, route.total_lag),
                "producto_coeficientes": product,
                "signo_ruta": _sign_label(product),
                "observaciones": int(len(common)),
                "muestra_inicio": common.min().strftime("%Y-%m-%d"),
                "muestra_fin": common.max().strftime("%Y-%m-%d"),
                "advertencia_interpretacion": DYNAMIC_MEDIATION_WARNING,
            }
        )
        for edge_id in route.edge_ids:
            if edge_id not in edge_lookup:
                raise AssertionError(f"La ruta {route.route_id} referencia una arista inexistente.")
    return pd.DataFrame(rows, columns=PATH_COLUMNS)


def _circular_block_positions(n: int, block_months: int, rng: np.random.Generator) -> np.ndarray:
    if n < 1:
        raise ValueError("No se puede remuestrear una muestra vacía.")
    block = max(1, min(int(block_months), n))
    positions: list[int] = []
    while len(positions) < n:
        start = int(rng.integers(0, n))
        positions.extend((start + np.arange(block)) % n)
    return np.asarray(positions[:n], dtype=int)


def _bootstrap_paths(
    equations: list[_Equation],
    routes: list[_Route],
    point_paths: pd.DataFrame,
    *,
    repetitions: int,
    block_months: int,
    seed: int,
) -> pd.DataFrame:
    if repetitions < 1:
        raise ValueError("bootstrap_replicates debe ser positivo.")
    if block_months < 1:
        raise ValueError("block_months debe ser positivo.")
    rng = np.random.default_rng(seed)
    values: dict[str, list[float]] = {route.route_id: [] for route in routes}
    for _ in range(int(repetitions)):
        positions = _circular_block_positions(len(equations[0].y), block_months, rng)
        edge_coefficients: dict[str, float] = {}
        try:
            for equation in equations:
                result = sm.OLS(
                    equation.y.to_numpy(dtype=float)[positions],
                    equation.x.to_numpy(dtype=float)[positions, :],
                    missing="raise",
                ).fit()
                params = np.asarray(result.params, dtype=float)
                term_positions = {term: index for index, term in enumerate(equation.x.columns)}
                for edge_id, term in equation.edge_terms.items():
                    edge_coefficients[edge_id] = float(params[term_positions[term]])
            for route in routes:
                product = float(np.prod([edge_coefficients[edge_id] for edge_id in route.edge_ids]))
                if np.isfinite(product):
                    values[route.route_id].append(product)
        except (np.linalg.LinAlgError, ValueError, FloatingPointError):
            continue
    point_lookup = point_paths.set_index("ruta_id")
    rows: list[dict[str, object]] = []
    for route in routes:
        sample = np.asarray(values[route.route_id], dtype=float)
        if sample.size == 0:
            raise ValueError(f"El bootstrap no produjo réplicas válidas para {route.route_id}.")
        point = float(point_lookup.loc[route.route_id, "producto_coeficientes"])
        sign_probability = 100.0 * float(
            np.mean(np.sign(sample) == np.sign(point))
        )
        rows.append(
            {
                "ruta_id": route.route_id,
                "origen": point_lookup.loc[route.route_id, "origen"],
                "destino": point_lookup.loc[route.route_id, "destino"],
                "tipo_ruta": point_lookup.loc[route.route_id, "tipo_ruta"],
                "producto_puntual": point,
                "producto_bootstrap_mediana": float(np.percentile(sample, 50)),
                "ic_95_inferior": float(np.percentile(sample, 2.5)),
                "ic_95_superior": float(np.percentile(sample, 97.5)),
                "probabilidad_signo_coincidente_pct": sign_probability,
                "replicas_solicitadas": int(repetitions),
                "replicas_validas": int(sample.size),
                "bloque_meses": int(block_months),
                "semilla": int(seed),
                "advertencia_interpretacion": DYNAMIC_MEDIATION_WARNING,
            }
        )
    return pd.DataFrame(rows, columns=BOOTSTRAP_COLUMNS)


def _contribution_table(
    components: pd.DataFrame,
    spec: MediationSpec,
    equations: list[_Equation],
    routes: list[_Route],
    path_table: pd.DataFrame,
    common: pd.DatetimeIndex,
) -> pd.DataFrame:
    nodes = {node.key: node for node in spec.nodes}
    outcome_equation = next(equation for equation in equations if equation.target == spec.outcome)
    final_result = outcome_equation.result
    if final_result is None:
        raise AssertionError("La ecuación final debe estimarse antes de construir contribuciones.")
    params = pd.Series(final_result.params, index=outcome_equation.x.columns)
    frame = pd.DataFrame(index=common)
    frame.index.name = "fecha"
    frame["D.ln_trm_observada"] = outcome_equation.y
    frame["ajuste_total"] = pd.Series(final_result.fittedvalues, index=common)
    equation_columns: list[str] = []
    for term in outcome_equation.x.columns:
        column = f"contribucion_ecuacion_final_{_safe_column(term)}"
        equation_columns.append(column)
        frame[column] = outcome_equation.x[term] * float(params[term])
    frame["suma_ecuacion_final"] = frame[equation_columns].sum(axis=1)
    frame["cierre_contable"] = frame["suma_ecuacion_final"] - frame["ajuste_total"]

    for equation in equations:
        if equation.target == spec.outcome or equation.result is None:
            continue
        node_key = equation.target
        frame[f"valor_observado_{node_key}"] = equation.y
        frame[f"valor_ajustado_{node_key}"] = pd.Series(
            equation.result.fittedvalues, index=common
        )
        frame[f"residuo_{node_key}"] = equation.y - frame[f"valor_ajustado_{node_key}"]

    path_sum_columns: list[str] = []
    path_lookup = path_table.set_index("ruta_id")
    for route in routes:
        source_component = nodes[route.source].component
        source_signal = components[source_component].shift(route.total_lag).reindex(common)
        column = f"contribucion_ruta_{route.route_id}"
        frame[column] = float(path_lookup.loc[route.route_id, "producto_coeficientes"]) * source_signal
        path_sum_columns.append(column)
    frame["suma_rutas_diagnosticas"] = frame[path_sum_columns].sum(axis=1) if path_sum_columns else 0.0
    return frame.reset_index()


def estimate_dynamic_mediation(
    components: pd.DataFrame,
    *,
    spec: MediationSpec = DEFAULT_MEDIATION_SPEC,
    common_index: pd.Index | None = None,
    outcome_y: pd.Series | None = None,
    outcome_design: pd.DataFrame | None = None,
    hac_maxlags: int = 6,
    bootstrap_replicates: int = MEDIATION_BOOTSTRAP_REPLICATIONS,
    block_months: int = MEDIATION_BOOTSTRAP_BLOCK_MONTHS,
    seed: int = MEDIATION_BOOTSTRAP_SEED,
) -> DynamicMediationResult:
    """Estima el grafo dinámico y devuelve sus cuatro productos tabulares.

    ``outcome_design`` permite reutilizar la matriz seleccionada del marco
    macroeconómico integral. Si no se entrega, la ecuación final usa sólo las
    aristas entrantes del grafo y una constante; esto resulta útil para tests y
    diagnósticos sintéticos.
    """
    topological_order = validate_mediation_spec(spec)
    component_frame = _normalise_frame(components, "components")
    for node in spec.nodes:
        if node.component not in component_frame.columns:
            raise KeyError(f"Falta el componente del nodo {node.key!r}: {node.component!r}.")
    equations = _build_equations(
        component_frame,
        spec,
        topological_order,
        outcome_y=outcome_y,
        outcome_design=outcome_design,
    )
    common = _common_index(equations, common_index)
    coefficients, edge_coefficients = _coefficient_rows(
        equations,
        spec,
        common,
        hac_maxlags=hac_maxlags,
    )
    routes = _enumerate_routes(spec)
    if not routes:
        raise ValueError("La red no contiene rutas desde las fuentes hasta el outcome.")
    missing_edge_coefficients = sorted(
        edge_id
        for route in routes
        for edge_id in route.edge_ids
        if edge_id not in edge_coefficients
    )
    if missing_edge_coefficients:
        raise ValueError(
            "Faltan coeficientes de aristas para rutas: "
            + ", ".join(sorted(set(missing_edge_coefficients)))
        )
    paths = _path_table(routes, spec, edge_coefficients, common)
    bootstrap = _bootstrap_paths(
        equations,
        routes,
        paths,
        repetitions=bootstrap_replicates,
        block_months=block_months,
        seed=seed,
    )
    contributions = _contribution_table(
        component_frame,
        spec,
        equations,
        routes,
        paths,
        common,
    )
    metadata: dict[str, object] = {
        "metodo": DYNAMIC_MEDIATION_METHOD,
        "advertencia": DYNAMIC_MEDIATION_WARNING,
        "muestra_inicio": common.min().strftime("%Y-%m-%d"),
        "muestra_fin": common.max().strftime("%Y-%m-%d"),
        "observaciones": int(len(common)),
        "nodos": int(len(spec.nodes)),
        "aristas": int(len(spec.edges)),
        "rutas": int(len(routes)),
        "orden_topologico": list(topological_order),
        "rezagos_futuro_permitidos": False,
        "bootstrap_replicas": int(bootstrap_replicates),
        "bootstrap_bloque_meses": int(block_months),
        "bootstrap_semilla": int(seed),
        "ecuacion_final_reutiliza_diseno_integrado": outcome_design is not None,
        "componentes_fuente": {
            node.key: node.component for node in spec.nodes
        },
        "aristas_registradas": [
            {
                "edge_id": edge.edge_id,
                "source": edge.source,
                "target": edge.target,
                "lag": edge.lag,
                "label": edge.label,
            }
            for edge in spec.edges
        ],
    }
    return DynamicMediationResult(
        coefficients=coefficients,
        paths=paths,
        bootstrap=bootstrap,
        contributions=contributions,
        common_index=common,
        metadata=metadata,
    )


def validate_dynamic_mediation_outputs(results_dir: Path) -> None:
    """Valida la estructura, rezagos y cierres de los cuatro CSV publicados."""
    paths = [results_dir / relative.split("/", 1)[1] for relative in MEDIATION_OUTPUTS]
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise AssertionError(
            "Faltan outputs de mediación dinámica: "
            + ", ".join(str(path) for path in missing)
        )
    coefficients = pd.read_csv(paths[0])
    routes = pd.read_csv(paths[1])
    bootstrap = pd.read_csv(paths[2])
    contributions = pd.read_csv(paths[3])
    if list(coefficients.columns) != COEFFICIENT_COLUMNS:
        raise AssertionError("Las columnas de coeficientes de mediación no concilian.")
    if list(routes.columns) != PATH_COLUMNS:
        raise AssertionError("Las columnas de rutas de mediación no concilian.")
    if list(bootstrap.columns) != BOOTSTRAP_COLUMNS:
        raise AssertionError("Las columnas de bootstrap de mediación no concilian.")
    if not set(CONTRIBUTION_REQUIRED_COLUMNS).issubset(contributions.columns):
        raise AssertionError("La tabla de contribuciones no contiene su contrato mínimo.")
    if coefficients.empty or routes.empty or bootstrap.empty or contributions.empty:
        raise AssertionError("Los outputs de mediación dinámica no pueden estar vacíos.")
    edge_rows = coefficients.loc[coefficients["tipo_termino"].eq("arista")]
    if edge_rows["edge_id"].duplicated().any():
        raise AssertionError("Una arista de mediación tiene más de un coeficiente publicado.")
    lags = pd.to_numeric(edge_rows["rezago_meses"], errors="coerce")
    if lags.isna().any() or (lags < 0).any() or not np.allclose(lags, np.round(lags)):
        raise AssertionError("Las aristas publicadas contienen rezagos futuros o inválidos.")
    route_ids = set(routes["ruta_id"])
    if route_ids != set(bootstrap["ruta_id"]):
        raise AssertionError("Las rutas y su bootstrap no concilian.")
    for column in ["producto_coeficientes", "rezago_total_meses"]:
        values = pd.to_numeric(routes[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            raise AssertionError(f"La tabla de rutas contiene {column} no finito.")
    if (pd.to_numeric(routes["rezago_total_meses"], errors="coerce") < 0).any():
        raise AssertionError("Una ruta publicada tiene rezago total negativo.")
    for column in ["producto_puntual", "ic_95_inferior", "ic_95_superior"]:
        values = pd.to_numeric(bootstrap[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            raise AssertionError(f"El bootstrap contiene {column} no finito.")
    if not pd.to_numeric(bootstrap["replicas_validas"], errors="coerce").gt(0).all():
        raise AssertionError("El bootstrap no tiene réplicas válidas.")
    dates = pd.to_datetime(contributions["fecha"], errors="coerce")
    if dates.isna().any() or not dates.is_unique or not dates.is_monotonic_increasing:
        raise AssertionError("Las fechas de contribuciones no son únicas y ordenadas.")
    numeric_columns = [
        "D.ln_trm_observada",
        "ajuste_total",
        "suma_ecuacion_final",
        "cierre_contable",
        "suma_rutas_diagnosticas",
    ]
    numeric = contributions[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise AssertionError("La conciliación de mediación contiene valores no finitos.")
    if float(numeric["cierre_contable"].abs().max()) > 1e-8:
        raise AssertionError("La ecuación final de mediación no cierra contablemente.")
    warning_columns = [
        coefficients["advertencia_interpretacion"],
        routes["advertencia_interpretacion"],
        bootstrap["advertencia_interpretacion"],
    ]
    if any(not values.astype(str).str.contains(DYNAMIC_MEDIATION_WARNING, regex=False).all() for values in warning_columns):
        raise AssertionError("Una tabla de mediación perdió la advertencia no causal.")


__all__ = [
    "BOOTSTRAP_COLUMNS",
    "COEFFICIENT_COLUMNS",
    "CONTRIBUTION_REQUIRED_COLUMNS",
    "DEFAULT_MEDIATION_SPEC",
    "DYNAMIC_MEDIATION_METHOD",
    "DYNAMIC_MEDIATION_WARNING",
    "MEDIATION_BOOTSTRAP_BLOCK_MONTHS",
    "MEDIATION_BOOTSTRAP_REPLICATIONS",
    "MEDIATION_BOOTSTRAP_SEED",
    "MEDIATION_OUTPUTS",
    "MediationEdge",
    "MediationNode",
    "MediationSpec",
    "DynamicMediationResult",
    "estimate_dynamic_mediation",
    "validate_dynamic_mediation_outputs",
    "validate_mediation_spec",
]
