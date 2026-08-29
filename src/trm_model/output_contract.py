"""Contratos de ownership para outputs generados por la corrida mensual.

``results/output_catalog.json`` clasifica todo el legado versionado, incluidos
archivos producidos por investigaciones anteriores. Este módulo distingue ese
catálogo completo de los 45 archivos que ``estimate_model.main`` escribe en
una corrida mensual actual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .paths import ProjectPaths, project_paths

MONTHLY_GENERATED_OUTPUTS: dict[str, tuple[str, ...]] = {
    "monthly_explanation": (
        "results/explicacion/ajuste_historico_controles_externos.csv",
        "results/explicacion/ajuste_historico_marco_macro_integral.csv",
        "results/explicacion/coeficientes_controles_externos.csv",
        "results/explicacion/coeficientes_marco_macro_integral.csv",
        "results/explicacion/comparacion_especificaciones.csv",
        "results/explicacion/comparacion_factor_regional.csv",
        "results/explicacion/contribuciones_controles_externos.csv",
        "results/explicacion/contribuciones_factores_controles_externos.csv",
        "results/explicacion/contribuciones_factores_marco_macro_integral.csv",
        "results/explicacion/contribuciones_marco_macro_integral.csv",
        "results/explicacion/diagnosticos_controles_externos.csv",
        "results/explicacion/diagnosticos_marco_macro_integral.csv",
        "results/explicacion/estabilidad_submuestras_marco_macro_integral.csv",
        "results/explicacion/estabilidad_submuestras_resumen.csv",
        "results/explicacion/intervalos_bootstrap_pesos_shapley.csv",
        "results/explicacion/interpretacion_factores_marco_macro_integral.csv",
        "results/explicacion/pesos_explicativos_marco_macro_integral.csv",
        "results/explicacion/pruebas_integracion.csv",
        "results/explicacion/seleccion_rezagos_adl_diferencias.csv",
        "results/explicacion/seleccion_rezagos_marco_macro_integral.csv",
        "results/explicacion/validacion_metricas_controles_externos.csv",
        "results/explicacion/validacion_metricas_marco_macro_integral.csv",
        "results/explicacion/validacion_predicciones_controles_externos.csv",
        "results/explicacion/validacion_predicciones_marco_macro_integral.csv",
        "results/metadata.json",
        "data/modelo_trm_datos_mensuales.csv",
        "data/modelo_trm_muestra_estimacion.csv",
    ),
    "monthly_forecast": (
        "results/pronostico/calendario_disponibilidad_pronostico.csv",
        "results/pronostico/seleccion_rezagos_modelo_pronostico.csv",
        "results/pronostico/coeficientes_modelo_pronostico.csv",
        "results/pronostico/diagnosticos_modelo_pronostico.csv",
        "results/pronostico/validacion_predicciones_pronostico.csv",
        "results/pronostico/validacion_metricas_pronostico.csv",
        "results/pronostico/diebold_mariano_pronostico.csv",
        "results/pronostico/comparacion_parsimoniosos_pronostico.csv",
    ),
    "robustness": (
        "results/robustez/comparacion_agregacion_bei_5y.csv",
        "results/robustez/pruebas_estacionariedad_bei_5y.csv",
        "results/robustez/tendencias_quiebres_bei_5y.csv",
        "results/robustez/comparacion_especificaciones_bei_5y.csv",
        "results/robustez/seleccion_rezagos_ecm.csv",
        "results/robustez/coeficientes_corto_plazo_ecm.csv",
        "results/robustez/coeficientes_largo_plazo_ecm.csv",
        "results/robustez/bounds_resumen.csv",
        "results/robustez/bounds_criticos.csv",
        "results/robustez/diagnosticos_ecm.csv",
    ),
}

MONTHLY_GENERATED_PRODUCT_IDS = tuple(MONTHLY_GENERATED_OUTPUTS)
MONTHLY_GENERATED_OUTPUT_COUNT = sum(
    len(output_paths) for output_paths in MONTHLY_GENERATED_OUTPUTS.values()
)
if MONTHLY_GENERATED_OUTPUT_COUNT != 45:  # pragma: no cover - contrato estático
    raise RuntimeError(
        "El contrato mensual debe contener exactamente 45 outputs generados; "
        f"encontrados {MONTHLY_GENERATED_OUTPUT_COUNT}."
    )


def monthly_generated_output_ownership(
    paths: ProjectPaths | None = None,
) -> dict[str, list[str]]:
    """Devuelve el ownership relativo de los 45 outputs de una corrida mensual."""
    del paths  # El contrato usa rutas relativas; se acepta para una API uniforme.
    ownership = {
        product_id: list(output_paths)
        for product_id, output_paths in MONTHLY_GENERATED_OUTPUTS.items()
    }
    _assert_disjoint_ownership(ownership)
    return ownership


def flatten_output_ownership(ownership: Mapping[str, list[str]]) -> list[str]:
    """Aplana ownership y exige que cada output tenga un único propietario."""
    _assert_disjoint_ownership(ownership)
    return sorted(path for output_paths in ownership.values() for path in output_paths)


def resolve_output_ownership(
    ownership: Mapping[str, list[str]],
    *,
    paths: ProjectPaths | None = None,
    require_existing: bool = True,
) -> list[Path]:
    """Resuelve outputs relativos y opcionalmente exige que ya existan."""
    project = paths or project_paths()
    relative_paths = flatten_output_ownership(ownership)
    resolved = [project.resolve(relative_path) for relative_path in relative_paths]
    if require_existing:
        missing = [path for path in resolved if not path.is_file()]
        if missing:
            missing_text = ", ".join(project.relative(path) for path in missing)
            raise FileNotFoundError(f"Faltan outputs mensuales declarados: {missing_text}")
    return resolved


def ownership_records(ownership: Mapping[str, list[str]]) -> list[dict[str, object]]:
    """Convierte ownership en la representación de un manifest de corrida."""
    _assert_disjoint_ownership(ownership)
    return [
        {"product_id": product_id, "output_files": list(ownership[product_id])}
        for product_id in sorted(ownership)
    ]


def validate_run_output_ownership(
    manifest: Mapping[str, Any],
    *,
    expected_product_ids: set[str] | None = None,
) -> None:
    """Concilia outputs top-level, productos y ausencia de ownership doble."""
    products = manifest.get("products")
    if not isinstance(products, list):
        raise ValueError("El manifest de corrida debe contener products para validar ownership.")
    product_ids = [str(product.get("product_id")) for product in products]
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("El manifest de corrida contiene productos duplicados.")
    if expected_product_ids is not None and set(product_ids) != expected_product_ids:
        raise ValueError(
            "Los productos del manifest no concilian: "
            f"esperados={sorted(expected_product_ids)}, encontrados={sorted(product_ids)}."
        )

    ownership = {
        str(product["product_id"]): list(product.get("output_files", []))
        for product in products
    }
    product_paths = flatten_output_ownership(ownership)
    top_level = [str(record["path"]) for record in manifest.get("output_files", [])]
    if len(top_level) != len(set(top_level)):
        raise ValueError("El manifest de corrida contiene outputs top-level duplicados.")
    if set(top_level) != set(product_paths):
        raise ValueError(
            "Los outputs top-level y los outputs por producto no concilian: "
            f"missing={sorted(set(product_paths) - set(top_level))}, "
            f"extra={sorted(set(top_level) - set(product_paths))}."
        )


def _assert_disjoint_ownership(ownership: Mapping[str, list[str]]) -> None:
    owners: dict[str, str] = {}
    for product_id, output_paths in ownership.items():
        if len(output_paths) != len(set(output_paths)):
            raise ValueError(f"El producto {product_id!r} repite outputs.")
        for output_path in output_paths:
            previous = owners.setdefault(output_path, product_id)
            if previous != product_id:
                raise ValueError(
                    f"El output {output_path!r} tiene ownership doble: "
                    f"{previous!r} y {product_id!r}."
                )
