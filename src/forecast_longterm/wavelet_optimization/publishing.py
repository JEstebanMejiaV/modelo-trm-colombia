"""Publicación aislada y determinista de la investigación wavelet.

Este módulo contiene solamente los contratos de salida de
``long_horizon_wavelet_optimization``. No calcula reconstrucciones, métricas ni
provenance: consume un ``ResearchPlan``, un ``EvaluationBundle`` y un manifest
que ya haya sido construido por el caller. Esa separación evita que la
publicación fabrique snapshots, hashes, decisiones o identificadores de
corrida.

Los cuatro archivos publicados viven exclusivamente bajo
``results/pronostico/wavelet_optimization/``. La serialización es pura hasta
que :class:`OutputPublisher` recibe todos los documentos validados; la
escritura usa temporales en el mismo directorio y ``os.replace`` para evitar
archivos parcialmente escritos.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pandas as pd

from trm_model.paths import ProjectPaths, project_paths

from .config import (
    BENCHMARK_ID,
    BENCHMARK_RETURN_PREDICTION,
    H1,
    H1_TEXT,
    H2,
    H2_TEXT,
    PRODUCT_ID,
    REQUIRED_HORIZONS,
    REQUIRED_SPLITS,
    RESEARCH_STATUS,
)
from .evaluation import EvaluationBundle, OriginPrediction
from .metrics import EvaluationMetrics, MetricsCalculator

# ---------------------------------------------------------------------------
# Contrato público de rutas, columnas y metadatos
# ---------------------------------------------------------------------------

OUTPUT_NAMESPACE = "results/pronostico/wavelet_optimization"
OUTPUT_KIND = "research"
OUTPUT_STATUS = "versioned"
RESEARCH_LABEL = "exploratory_research"

PREDICTIONS_FILENAME = "predicciones_por_origen.csv"
EVALUATION_FILENAME = "evaluacion_por_candidato.csv"
COVERAGE_FILENAME = "cobertura_point_in_time.csv"
DECISION_FILENAME = "hipotesis_decision.json"

OUTPUT_FILENAMES = (
    PREDICTIONS_FILENAME,
    EVALUATION_FILENAME,
    COVERAGE_FILENAME,
    DECISION_FILENAME,
)
OUTPUT_RELATIVE_PATHS = tuple(
    f"{OUTPUT_NAMESPACE}/{filename}" for filename in OUTPUT_FILENAMES
)

PREDICTION_COLUMNS = (
    "run_id",
    "experiment_id",
    "product_id",
    "research_label",
    "data_cutoff",
    "origin_date",
    "horizon_months",
    "candidate_id",
    "split",
    "prediction_wavelet",
    "prediction_random_walk",
    "observed_forward_return",
    "label_end_date",
    "n_mature_labels",
    "scoreability_status",
    "coverage_status",
    "causal_reconstruction",
    "snapshot_manifest",
    "source_vintage",
    "prefix_last_date",
    "prefix_length",
    "prefix_sha256",
    "warning",
)

EVALUATION_COLUMNS = (
    "run_id",
    "experiment_id",
    "candidate_id",
    "horizon_months",
    "split",
    "n_requested_origins",
    "n_scoreable_origins",
    "n_excluded_origins",
    "n_oos",
    "sse_model",
    "sse_random_walk",
    "r2_oos",
    "mae_model",
    "mae_random_walk",
    "rmse_model",
    "rmse_random_walk",
    "direction_accuracy_model",
    "direction_accuracy_random_walk",
    "dm_stat",
    "dm_p_value",
    "dm_status",
    "primary_metric",
    "selection_rule",
    "eligibility_scope",
)

COVERAGE_COLUMNS = (
    "origin_date",
    "horizon_months",
    "source_id",
    "snapshot_manifest",
    "source_vintage",
    "available_through",
    "sha256",
    "n_observations_available",
    "n_missing",
    "coverage_status",
    "required_for_candidate",
    "excluded_origins",
    "reason",
)

# The design calls this table ``cobertura_point_in_time.csv`` and deliberately
# excludes experiment/run identity from its row schema. Identity belongs to the
# run manifest and to the other two tabular outputs; adding it here would break
# the exact coverage contract and make the coverage ledger less reusable.

OUTPUT_METADATA = {
    relative_path: {
        "kind": OUTPUT_KIND,
        "status": OUTPUT_STATUS,
        "product_id": PRODUCT_ID,
        "research_only": True,
    }
    for relative_path in OUTPUT_RELATIVE_PATHS
}

NON_CAUSAL_WARNING = "Una asociación predictiva no identifica un efecto causal."
NO_FINANCIAL_USE_WARNING = (
    "Los resultados no constituyen instrucciones de cobertura, asignación de "
    "portafolio ni política económica."
)
MONTHLY_FORECAST_WARNING = (
    "Los outputs de esta variante no alimentan automáticamente el producto "
    "monthly_forecast ni ningún producto primario."
)

# The order is the pre-registered order, rather than Python hash order. It also
# matches EvaluationBundle's canonical row order and remains stable if a plan
# is supplied as a different iterable implementation.
_SPLIT_ORDER = {name: index for index, name in enumerate(REQUIRED_SPLITS)}
_MISSING = object()


# ---------------------------------------------------------------------------
# Errors and small schema objects
# ---------------------------------------------------------------------------


class PublishingError(ValueError):
    """Error de contrato al preparar o publicar una corrida."""


class OutputSchemaError(PublishingError):
    """Un registro no concilia con el schema de su output."""


class MissingProvenanceError(PublishingError):
    """El manifest no contiene la identidad/provenance requerida."""


class OutputVersionConflict(PublishingError):
    """Una ruta ya contiene una versión y no puede sobrescribirse."""

    def __init__(
        self,
        message: str,
        *,
        experiment_id: str | None = None,
        run_id: str | None = None,
        paths: Sequence[Path] = (),
    ) -> None:
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.paths = tuple(paths)
        super().__init__(message)


# Backwards/adapter-friendly aliases. They intentionally refer to the same
# exception so callers can use either the design's name or a generic one.
OutputConflictError = OutputVersionConflict
VersionConflictError = OutputVersionConflict
PublicationError = PublishingError
SchemaValidationError = OutputSchemaError


@dataclass(frozen=True)
class OutputSchema:
    """Descripción inmutable de un output tabular publicado."""

    name: str
    columns: tuple[str, ...]
    relative_path: str
    kind: str = OUTPUT_KIND
    status: str = OUTPUT_STATUS

    def __post_init__(self) -> None:
        if not self.name or not self.relative_path:
            raise OutputSchemaError("OutputSchema requiere name y relative_path")
        if len(self.columns) != len(set(self.columns)):
            raise OutputSchemaError(f"{self.name}: columnas duplicadas")
        if self.kind != OUTPUT_KIND or self.status != OUTPUT_STATUS:
            raise OutputSchemaError(
                "Los outputs de esta variante deben conservar kind='research' y "
                "status='versioned'."
            )


PREDICTION_SCHEMA = OutputSchema(
    "predicciones_por_origen",
    PREDICTION_COLUMNS,
    f"{OUTPUT_NAMESPACE}/{PREDICTIONS_FILENAME}",
)
EVALUATION_SCHEMA = OutputSchema(
    "evaluacion_por_candidato",
    EVALUATION_COLUMNS,
    f"{OUTPUT_NAMESPACE}/{EVALUATION_FILENAME}",
)
COVERAGE_SCHEMA = OutputSchema(
    "cobertura_point_in_time",
    COVERAGE_COLUMNS,
    f"{OUTPUT_NAMESPACE}/{COVERAGE_FILENAME}",
)
DECISION_SCHEMA_NAME = "hipotesis_decision"


@dataclass(frozen=True)
class PublicationDocuments:
    """Documentos validados en memoria antes de escribirlos."""

    predictions: tuple[dict[str, Any], ...]
    evaluation: tuple[dict[str, Any], ...]
    coverage: tuple[dict[str, Any], ...]
    decision: dict[str, Any]
    run_id: str
    experiment_id: str

    @property
    def relative_paths(self) -> tuple[str, ...]:
        return OUTPUT_RELATIVE_PATHS


# ---------------------------------------------------------------------------
# Coerción y normalización sin inferir datos
# ---------------------------------------------------------------------------


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    for method_name in ("as_dict", "to_dict", "to_record"):
        method = getattr(value, method_name, None)
        if callable(method):
            result = method()
            if isinstance(result, Mapping):
                return result
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        result = asdict(value)
        if isinstance(result, Mapping):
            return result
    values = getattr(value, "__dict__", None)
    if isinstance(values, Mapping):
        return values
    raise OutputSchemaError(f"{field_name} no es un mapping ni un objeto serializable")


def _get(value: Mapping[str, Any], *names: str, default: Any = _MISSING) -> Any:
    for name in names:
        if name in value:
            return value[name]
    if default is not _MISSING:
        return default
    raise OutputSchemaError(f"Falta campo requerido; aliases esperados: {names!r}")


def _plan_get(plan: Any, *names: str, default: Any = _MISSING) -> Any:
    if plan is None:
        if default is not _MISSING:
            return default
        raise OutputSchemaError(f"Falta plan; aliases esperados: {names!r}")
    if isinstance(plan, Mapping):
        return _get(plan, *names, default=default)
    for name in names:
        if hasattr(plan, name):
            return getattr(plan, name)
    if default is not _MISSING:
        return default
    raise OutputSchemaError(f"El plan no expone ningún campo {names!r}")


def _timestamp_text(value: Any, *, field_name: str, allow_none: bool = True) -> str | None:
    if value is None or value is pd.NaT or (isinstance(value, str) and not value.strip()):
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no puede ser nulo")
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise OutputSchemaError(f"{field_name} no es una fecha válida: {value!r}") from error
    if pd.isna(parsed):
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no es una fecha válida")
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    return parsed.strftime("%Y-%m-%d")


def _finite_number(value: Any, *, field_name: str, allow_none: bool = True) -> float | None:
    if value is None or value is pd.NA or value is pd.NaT:
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no puede ser nulo")
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no puede ser NaN")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise OutputSchemaError(f"{field_name} debe ser numérico o nulo") from error
    if not math.isfinite(number):
        raise OutputSchemaError(f"{field_name} debe ser finito o nulo")
    return number


def _integer(value: Any, *, field_name: str, allow_none: bool = True) -> int | None:
    if value is None or value is pd.NA or value is pd.NaT:
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no puede ser nulo")
    if isinstance(value, (bool, np.bool_)):
        raise OutputSchemaError(f"{field_name} debe ser entero, no bool")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise OutputSchemaError(f"{field_name} debe ser entero o nulo") from error
    try:
        if float(value) != float(number):
            raise OutputSchemaError(f"{field_name} debe ser entero")
    except (TypeError, ValueError, OverflowError):
        raise OutputSchemaError(f"{field_name} debe ser entero") from None
    if number < 0:
        raise OutputSchemaError(f"{field_name} no puede ser negativo")
    return number


def _text(value: Any, *, field_name: str, allow_none: bool = True) -> str | None:
    if value is None or value is pd.NA or value is pd.NaT:
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no puede ser nulo")
    text = str(value).strip()
    if not text and not allow_none:
        raise OutputSchemaError(f"{field_name} no puede estar vacío")
    return text or None


def _boolean(value: Any, *, field_name: str, allow_none: bool = True) -> bool | None:
    if value is None or value is pd.NA or value is pd.NaT:
        if allow_none:
            return None
        raise OutputSchemaError(f"{field_name} no puede ser nulo")
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise OutputSchemaError(f"{field_name} debe ser booleano")


def _json_value(value: Any) -> Any:
    """Convierte valores pandas/numpy a un árbol JSON sin perder nulls."""

    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return _timestamp_text(value, field_name="date")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        if not math.isfinite(number):
            raise OutputSchemaError("No se puede serializar un float no finito")
        return number
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OutputSchemaError("No se puede serializar un float no finito")
        return value
    return value


def _json_array_text(value: Any, *, field_name: str) -> str:
    if value is None or value is pd.NA:
        values: list[Any] = []
    elif isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = sorted({str(item) for item in value})
    else:
        raise OutputSchemaError(f"{field_name} debe ser una colección o texto")
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _split_sort_key(split: Any) -> tuple[int, str]:
    text = str(split)
    return _SPLIT_ORDER.get(text, len(_SPLIT_ORDER)), text


def _record_sort_key(record: Mapping[str, Any], *fields: str) -> tuple[Any, ...]:
    values: list[Any] = []
    for field in fields:
        value = record.get(field)
        if field in {"origin_date", "data_cutoff", "label_end_date", "prefix_last_date", "available_through"}:
            values.append("" if value is None else str(value))
        elif field == "split":
            values.append(_split_sort_key(value))
        elif field == "horizon_months":
            values.append(-1 if value is None else int(value))
        else:
            values.append("" if value is None else str(value))
    return tuple(values)


def _ensure_unique(records: Iterable[Mapping[str, Any]], key_fields: Sequence[str], *, name: str) -> None:
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        key = tuple(record.get(field) for field in key_fields)
        if key in seen:
            raise OutputSchemaError(f"{name} contiene una clave duplicada: {key!r}")
        seen.add(key)


def _plan_identity(plan: Any, *, experiment_id: str | None = None) -> tuple[str, str]:
    plan_experiment = _text(
        _plan_get(plan, "experiment_id", "Experiment_ID", default=experiment_id),
        field_name="experiment_id",
        allow_none=False,
    )
    if experiment_id is not None and plan_experiment != str(experiment_id).strip():
        raise OutputSchemaError(
            "experiment_id del publisher no concilia con ResearchPlan.experiment_id"
        )
    product_id = _text(
        _plan_get(plan, "product_id", "Product_ID", default=PRODUCT_ID),
        field_name="product_id",
        allow_none=False,
    )
    if product_id != PRODUCT_ID:
        raise OutputSchemaError(
            f"La variante exige product_id={PRODUCT_ID!r}; llegó {product_id!r}"
        )
    status = _text(
        _plan_get(plan, "status", "Status", default=RESEARCH_STATUS),
        field_name="status",
        allow_none=False,
    )
    if status != RESEARCH_STATUS:
        raise OutputSchemaError(
            f"La variante exige status={RESEARCH_STATUS!r}; llegó {status!r}"
        )
    return plan_experiment, product_id


def _manifest_mapping(manifest: Any) -> Mapping[str, Any]:
    return _mapping(manifest, field_name="manifest")


def _manifest_run_id(manifest: Mapping[str, Any], *, explicit: str | None = None) -> str:
    value = explicit
    if value is None:
        value = _get(manifest, "run_id", "Run_ID", default=None)
    if value is None:
        context = manifest.get("run_context")
        if isinstance(context, Mapping):
            value = _get(context, "run_id", "Run_ID", default=None)
    result = _text(value, field_name="run_id", allow_none=False)
    return result


def _manifest_experiment_id(manifest: Mapping[str, Any]) -> str | None:
    value = _get(manifest, "experiment_id", "Experiment_ID", default=None)
    if value is not None:
        return _text(value, field_name="manifest.experiment_id")
    values = _get(manifest, "experiment_ids", "Experiment_IDs", default=None)
    if isinstance(values, (list, tuple)) and values:
        return _text(values[0], field_name="manifest.experiment_ids[0]")
    return None


def _wavelet_context(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    context = manifest.get("run_context")
    if not isinstance(context, Mapping):
        return {}
    nested = context.get("wavelet_optimization")
    if isinstance(nested, Mapping):
        return nested
    # A future recorder may expose the variant context directly. Supporting it
    # is an adapter, not an inference: only explicitly present keys are read.
    return context


def _provenance_missing(
    manifest: Mapping[str, Any],
    *,
    expected_paths: Sequence[str],
    gate_decision: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Return missing provenance fields without manufacturing placeholders."""

    missing: list[str] = []
    if _manifest_run_id(manifest, explicit=None) is None:  # pragma: no cover - guarded caller
        missing.append("run_id")
    if _manifest_experiment_id(manifest) is None:
        missing.append("experiment_id")
    if "input_files" not in manifest and "inputs" not in manifest:
        missing.append("input_files")

    context = _wavelet_context(manifest)
    required = (
        "plan_hash",
        "snapshot_manifests",
        "source_vintages",
        "data_cutoff",
        "target_definition",
        "label_maturity_rule",
        "minimum_mature_training",
        "dwt",
        "candidate_grid",
        "splits",
        "coverage_summary",
    )
    for field_name in required:
        if field_name not in context or context[field_name] is None:
            missing.append(f"run_context.wavelet_optimization.{field_name}")

    if "output_paths" not in context and "output_files" not in context:
        missing.append("run_context.wavelet_optimization.output_paths")
    else:
        declared = context.get("output_paths", context.get("output_files"))
        if isinstance(declared, Mapping):
            declared = list(declared)
        if not isinstance(declared, (list, tuple, set)):
            missing.append("run_context.wavelet_optimization.output_paths")
        else:
            normalized = sorted(str(item) for item in declared)
            if normalized != sorted(expected_paths):
                missing.append("run_context.wavelet_optimization.output_paths (conciliation)")

    if "promotion_gate" not in context and gate_decision is None:
        missing.append("run_context.wavelet_optimization.promotion_gate")
    return tuple(dict.fromkeys(missing))


def _validate_identity(
    plan: Any,
    manifest: Any,
    *,
    run_id: str | None = None,
    experiment_id: str | None = None,
) -> tuple[Mapping[str, Any], str, str, str]:
    manifest_mapping = _manifest_mapping(manifest)
    plan_experiment, _product_id = _plan_identity(plan, experiment_id=experiment_id)
    resolved_run = _manifest_run_id(manifest_mapping, explicit=run_id)
    manifest_experiment = _manifest_experiment_id(manifest_mapping)
    if manifest_experiment is not None and manifest_experiment != plan_experiment:
        raise OutputSchemaError(
            "experiment_id del manifest no concilia con ResearchPlan.experiment_id"
        )
    return manifest_mapping, resolved_run, plan_experiment, PRODUCT_ID


# ---------------------------------------------------------------------------
# Serializadores de predicciones, métricas y cobertura
# ---------------------------------------------------------------------------


def _prediction_source(source: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(source, EvaluationBundle):
        return tuple(source.all_predictions)
    if hasattr(source, "all_predictions"):
        values = getattr(source, "all_predictions")
        values = values() if callable(values) else values
        return tuple(values)
    if hasattr(source, "predictions") and not isinstance(source, (list, tuple)):
        values = getattr(source, "predictions")
        values = values() if callable(values) else values
        return tuple(values)
    if isinstance(source, Mapping) or isinstance(source, OriginPrediction):
        return (_mapping(source, field_name="prediction"),)
    try:
        return tuple(_mapping(value, field_name="prediction") for value in source)
    except TypeError as error:
        raise OutputSchemaError("predictions debe ser iterable") from error


def _prediction_records(
    source: Any,
    *,
    plan: Any,
    run_id: str,
    experiment_id: str,
) -> tuple[dict[str, Any], ...]:
    _plan_identity(plan, experiment_id=experiment_id)
    plan_cutoff = _timestamp_text(
        _plan_get(plan, "data_cutoff", "Data_Cutoff", default=None),
        field_name="data_cutoff",
        allow_none=False,
    )
    records: list[dict[str, Any]] = []
    for raw in _prediction_source(source):
        row = dict(_mapping(raw, field_name="prediction"))
        row_experiment = _text(
            _get(row, "experiment_id", "Experiment_ID", default=experiment_id),
            field_name="experiment_id",
            allow_none=False,
        )
        if row_experiment != experiment_id:
            raise OutputSchemaError("Una predicción pertenece a otro experiment_id")
        row_product = _text(
            _get(row, "product_id", "Product_ID", default=PRODUCT_ID),
            field_name="product_id",
            allow_none=False,
        )
        if row_product != PRODUCT_ID:
            raise OutputSchemaError("Una predicción pertenece a otro product_id")

        status = _text(
            _get(row, "scoreability_status", "scoreability", "status", default=None),
            field_name="scoreability_status",
            allow_none=False,
        )
        prediction = _finite_number(
            _get(row, "prediction_wavelet", "prediction_model", default=None),
            field_name="prediction_wavelet",
        )
        benchmark = _finite_number(
            _get(row, "prediction_random_walk", "prediction_benchmark", default=None),
            field_name="prediction_random_walk",
        )
        if status == "scoreable":
            if prediction is None or benchmark is None:
                raise OutputSchemaError(
                    "Una fila scoreable debe conservar ambas predicciones y el benchmark"
                )
            if benchmark != float(BENCHMARK_RETURN_PREDICTION):
                raise OutputSchemaError("Random_Walk_Benchmark debe ser exactamente 0.0")
        elif prediction is not None or benchmark is not None:
            raise OutputSchemaError(
                "Las predicciones de una fila no scoreable deben ser nulas"
            )

        row_cutoff = _timestamp_text(
            _get(row, "data_cutoff", "Data_Cutoff", default=plan_cutoff),
            field_name="data_cutoff",
            allow_none=False,
        )
        if row_cutoff != plan_cutoff:
            raise OutputSchemaError("data_cutoff de la fila no concilia con el plan")
        origin_date = _timestamp_text(
            _get(row, "origin_date", "Forecast_Origin", default=None),
            field_name="origin_date",
            allow_none=False,
        )
        label_end = _timestamp_text(
            _get(row, "label_end_date", "label_end", default=None),
            field_name="label_end_date",
        )
        prefix_last = _timestamp_text(
            _get(row, "prefix_last_date", "prefix_last", default=None),
            field_name="prefix_last_date",
        )
        prefix_length = _integer(
            _get(row, "prefix_length", default=None), field_name="prefix_length"
        )
        mature = _integer(
            _get(row, "n_mature_labels", "n_training_labels", default=0),
            field_name="n_mature_labels",
            allow_none=False,
        )
        horizon = _integer(
            _get(row, "horizon_months", "horizon", default=None),
            field_name="horizon_months",
            allow_none=False,
        )
        if horizon not in REQUIRED_HORIZONS:
            raise OutputSchemaError(f"horizon_months no soportado: {horizon!r}")
        split = _text(_get(row, "split", default="full"), field_name="split", allow_none=False)
        causal = _boolean(
            _get(row, "causal_reconstruction", "causal", default=False),
            field_name="causal_reconstruction",
            allow_none=False,
        )
        record = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "product_id": PRODUCT_ID,
            "research_label": _text(
                _get(row, "research_label", default=RESEARCH_LABEL),
                field_name="research_label",
                allow_none=False,
            ),
            "data_cutoff": row_cutoff,
            "origin_date": origin_date,
            "horizon_months": horizon,
            "candidate_id": _text(
                _get(row, "candidate_id", "Candidate_ID", default=None),
                field_name="candidate_id",
                allow_none=False,
            ),
            "split": split,
            "prediction_wavelet": prediction,
            "prediction_random_walk": benchmark,
            "observed_forward_return": _finite_number(
                _get(row, "observed_forward_return", "observed", default=None),
                field_name="observed_forward_return",
            ),
            "label_end_date": label_end,
            "n_mature_labels": mature,
            "scoreability_status": status,
            "coverage_status": _text(
                _get(row, "coverage_status", default="incomplete"),
                field_name="coverage_status",
                allow_none=False,
            ),
            "causal_reconstruction": causal,
            "snapshot_manifest": _text(
                _get(row, "snapshot_manifest", default=None), field_name="snapshot_manifest"
            ),
            "source_vintage": _text(
                _get(row, "source_vintage", default=None), field_name="source_vintage"
            ),
            "prefix_last_date": prefix_last,
            "prefix_length": prefix_length,
            "prefix_sha256": _text(
                _get(row, "prefix_sha256", default=None), field_name="prefix_sha256"
            ),
            "warning": _text(_get(row, "warning", default=None), field_name="warning"),
        }
        if record["prefix_sha256"] is not None:
            prefix_hash = str(record["prefix_sha256"]).lower()
            if len(prefix_hash) != 64 or any(char not in "0123456789abcdef" for char in prefix_hash):
                raise OutputSchemaError("prefix_sha256 debe ser SHA-256 hexadecimal o nulo")
            record["prefix_sha256"] = prefix_hash
        records.append(record)

    _ensure_unique(
        records,
        ("origin_date", "horizon_months", "candidate_id", "split"),
        name=PREDICTIONS_FILENAME,
    )
    return tuple(
        sorted(
            records,
            key=lambda row: _record_sort_key(
                row, "origin_date", "horizon_months", "candidate_id", "split"
            ),
        )
    )


def serialize_prediction_records(
    source: Any,
    plan: Any,
    *,
    run_id: str,
    experiment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Serializa predicciones a records con las columnas exactas del CSV."""

    resolved_experiment, _product = _plan_identity(plan, experiment_id=experiment_id)
    records = _prediction_records(
        source,
        plan=plan,
        run_id=_text(run_id, field_name="run_id", allow_none=False),
        experiment_id=resolved_experiment,
    )
    return [dict(record) for record in records]


def serialize_predictions(
    source: Any,
    plan: Any,
    *,
    run_id: str,
    experiment_id: str | None = None,
) -> pd.DataFrame:
    """Devuelve un DataFrame determinista para ``predicciones_por_origen.csv``."""

    records = serialize_prediction_records(
        source, plan, run_id=run_id, experiment_id=experiment_id
    )
    return pd.DataFrame(records, columns=PREDICTION_COLUMNS)


predictions_frame = serialize_predictions


def _metric_source(source: Any, *, plan: Any, candidate_ids: Sequence[str]) -> tuple[Any, ...]:
    if isinstance(source, EvaluationBundle):
        values = source.metrics
        if values:
            return tuple(values)
        return MetricsCalculator.from_plan(plan).calculate(
            source,
            plan=plan,
            candidate_ids=candidate_ids,
            horizons=tuple(_plan_get(plan, "horizons", default=REQUIRED_HORIZONS)),
            splits=tuple(_plan_get(plan, "splits", default=REQUIRED_SPLITS)),
        )
    if hasattr(source, "metrics") and not isinstance(source, (list, tuple)):
        values = getattr(source, "metrics")
        values = values() if callable(values) else values
        if values:
            return tuple(values)
        return MetricsCalculator.from_plan(plan).calculate(
            source,
            plan=plan,
            candidate_ids=candidate_ids,
        )
    if isinstance(source, Mapping) or isinstance(source, EvaluationMetrics):
        return (source,)
    try:
        return tuple(source)
    except TypeError as error:
        raise OutputSchemaError("metrics debe ser iterable") from error


def _candidate_id_value(candidate: Any) -> str:
    if isinstance(candidate, Mapping):
        value = candidate.get("candidate_id", candidate.get("id"))
    else:
        value = getattr(candidate, "candidate_id", candidate)
    return _text(value, field_name="candidate_id", allow_none=False)


def _candidate_components_value(candidate: Any) -> tuple[str, ...]:
    if isinstance(candidate, Mapping):
        value = candidate.get("components", ())
    else:
        value = getattr(candidate, "components", ())
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(str(item) for item in value)
    except TypeError:
        return ()


def _evaluation_records(
    source: Any,
    *,
    plan: Any,
    run_id: str,
    experiment_id: str,
    eligibility_scope: str,
) -> tuple[dict[str, Any], ...]:
    candidates = tuple(
        _candidate_id_value(candidate)
        for candidate in _plan_get(plan, "candidates", default=())
    )
    metric_values = _metric_source(source, plan=plan, candidate_ids=candidates)
    primary_metric = _text(
        _plan_get(plan, "primary_metric", default="r2_oos"),
        field_name="primary_metric",
        allow_none=False,
    )
    selection_rule = _text(
        _plan_get(plan, "selection_rule", default="rank_full_r2_then_mae_then_candidate_id"),
        field_name="selection_rule",
        allow_none=False,
    )
    scope = _text(eligibility_scope, field_name="eligibility_scope", allow_none=False)

    records: list[dict[str, Any]] = []
    for raw in metric_values:
        row = dict(_mapping(raw, field_name="evaluation metric"))
        candidate_id = _text(
            _get(row, "candidate_id", "Candidate_ID", default=None),
            field_name="candidate_id",
            allow_none=False,
        )
        horizon = _integer(
            _get(row, "horizon_months", "horizon", default=None),
            field_name="horizon_months",
            allow_none=False,
        )
        if horizon not in REQUIRED_HORIZONS:
            raise OutputSchemaError(f"horizon_months no soportado: {horizon!r}")
        split = _text(_get(row, "split", default=None), field_name="split", allow_none=False)
        record: dict[str, Any] = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "candidate_id": candidate_id,
            "horizon_months": horizon,
            "split": split,
        }
        for field_name in (
            "n_requested_origins",
            "n_scoreable_origins",
            "n_excluded_origins",
            "n_oos",
        ):
            value = _integer(_get(row, field_name, default=0), field_name=field_name, allow_none=False)
            record[field_name] = value
        for field_name in (
            "sse_model",
            "sse_random_walk",
            "r2_oos",
            "mae_model",
            "mae_random_walk",
            "rmse_model",
            "rmse_random_walk",
            "direction_accuracy_model",
            "direction_accuracy_random_walk",
            "dm_stat",
            "dm_p_value",
        ):
            record[field_name] = _finite_number(
                _get(row, field_name, default=None), field_name=field_name
            )
        record["dm_status"] = _text(
            _get(row, "dm_status", default="not_evaluable"),
            field_name="dm_status",
            allow_none=False,
        )
        record["primary_metric"] = primary_metric
        record["selection_rule"] = selection_rule
        record["eligibility_scope"] = scope
        records.append(record)

    _ensure_unique(
        records,
        ("candidate_id", "horizon_months", "split"),
        name=EVALUATION_FILENAME,
    )
    return tuple(
        sorted(
            records,
            key=lambda row: _record_sort_key(
                row, "candidate_id", "horizon_months", "split"
            ),
        )
    )


def serialize_evaluation_records(
    source: Any,
    plan: Any,
    *,
    run_id: str,
    experiment_id: str | None = None,
    eligibility_scope: str = "methodological_review",
) -> list[dict[str, Any]]:
    """Serializa ``EvaluationMetrics`` o un ``EvaluationBundle`` a records."""

    resolved_experiment, _product = _plan_identity(plan, experiment_id=experiment_id)
    records = _evaluation_records(
        source,
        plan=plan,
        run_id=_text(run_id, field_name="run_id", allow_none=False),
        experiment_id=resolved_experiment,
        eligibility_scope=eligibility_scope,
    )
    return [dict(record) for record in records]


def serialize_evaluation(
    source: Any,
    plan: Any,
    *,
    run_id: str,
    experiment_id: str | None = None,
    eligibility_scope: str = "methodological_review",
) -> pd.DataFrame:
    """Devuelve un DataFrame determinista para la evaluación por candidato."""

    records = serialize_evaluation_records(
        source,
        plan,
        run_id=run_id,
        experiment_id=experiment_id,
        eligibility_scope=eligibility_scope,
    )
    return pd.DataFrame(records, columns=EVALUATION_COLUMNS)


evaluation_frame = serialize_evaluation


def _coverage_source(source: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(source, EvaluationBundle):
        values = source.coverage
    elif hasattr(source, "coverage") and not isinstance(source, (list, tuple)):
        values = getattr(source, "coverage")
        values = values() if callable(values) else values
    elif isinstance(source, Mapping):
        values = (source,)
    else:
        values = source
    try:
        return tuple(_mapping(value, field_name="coverage") for value in values)
    except TypeError as error:
        raise OutputSchemaError("coverage debe ser iterable") from error


def _coverage_records(source: Any) -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for raw in _coverage_source(source):
        row = dict(raw)
        horizon = _integer(
            _get(row, "horizon_months", "horizon", default=None),
            field_name="horizon_months",
            allow_none=False,
        )
        if horizon not in REQUIRED_HORIZONS:
            raise OutputSchemaError(f"horizon_months no soportado: {horizon!r}")
        record = {
            "origin_date": _timestamp_text(
                _get(row, "origin_date", "Forecast_Origin", default=None),
                field_name="origin_date",
                allow_none=False,
            ),
            "horizon_months": horizon,
            "source_id": _text(
                _get(row, "source_id", "Source_ID", default=None),
                field_name="source_id",
                allow_none=False,
            ),
            "snapshot_manifest": _text(
                _get(row, "snapshot_manifest", default=None), field_name="snapshot_manifest"
            ),
            "source_vintage": _text(
                _get(row, "source_vintage", default=None), field_name="source_vintage"
            ),
            "available_through": _timestamp_text(
                _get(row, "available_through", default=None),
                field_name="available_through",
            ),
            "sha256": _text(_get(row, "sha256", default=None), field_name="sha256"),
            "n_observations_available": _integer(
                _get(row, "n_observations_available", default=0),
                field_name="n_observations_available",
                allow_none=False,
            ),
            "n_missing": _integer(
                _get(row, "n_missing", default=0), field_name="n_missing", allow_none=False
            ),
            "coverage_status": _text(
                _get(row, "coverage_status", default="incomplete"),
                field_name="coverage_status",
                allow_none=False,
            ),
            "required_for_candidate": _boolean(
                _get(row, "required_for_candidate", default=True),
                field_name="required_for_candidate",
                allow_none=False,
            ),
            "excluded_origins": _json_array_text(
                _get(row, "excluded_origins", default=()), field_name="excluded_origins"
            ),
            "reason": _text(_get(row, "reason", default=None), field_name="reason"),
        }
        if record["sha256"] is not None:
            sha = str(record["sha256"]).lower()
            if len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha):
                raise OutputSchemaError("sha256 debe ser SHA-256 hexadecimal o nulo")
            record["sha256"] = sha
        if record["coverage_status"] not in {"complete", "incomplete", "missing", "invalid"}:
            raise OutputSchemaError(
                f"coverage_status no soportado: {record['coverage_status']!r}"
            )
        records.append(record)

    _ensure_unique(
        records,
        ("origin_date", "horizon_months", "source_id"),
        name=COVERAGE_FILENAME,
    )
    return tuple(
        sorted(
            records,
            key=lambda row: _record_sort_key(
                row, "origin_date", "horizon_months", "source_id"
            ),
        )
    )


def serialize_coverage_records(source: Any) -> list[dict[str, Any]]:
    """Serializa un ledger/bundle de cobertura sin añadir desempeño."""

    return [dict(record) for record in _coverage_records(source)]


def serialize_coverage(source: Any) -> pd.DataFrame:
    """Devuelve un DataFrame para ``cobertura_point_in_time.csv``."""

    records = serialize_coverage_records(source)
    return pd.DataFrame(records, columns=COVERAGE_COLUMNS)


coverage_frame = serialize_coverage


# ---------------------------------------------------------------------------
# Documento de hipótesis y decisión
# ---------------------------------------------------------------------------


def _hypothesis_mapping(plan: Any) -> dict[str, dict[str, Any]]:
    raw_values = _plan_get(plan, "hypotheses", default=())
    result: dict[str, dict[str, Any]] = {}
    for raw in raw_values:
        if not isinstance(raw, Mapping):
            continue
        code = raw.get("id")
        statement = raw.get("statement")
        if code in {H1, H2}:
            result[str(code)] = {
                "id": str(code),
                "statement": str(statement).strip() if statement is not None else "",
            }
    result.setdefault(H1, {"id": H1, "statement": H1_TEXT})
    result.setdefault(H2, {"id": H2, "statement": H2_TEXT})
    return result


def _metric_records_for_decision(source: Any, plan: Any) -> tuple[Mapping[str, Any], ...]:
    candidates = tuple(
        _candidate_id_value(candidate)
        for candidate in _plan_get(plan, "candidates", default=())
    )
    values = _metric_source(source, plan=plan, candidate_ids=candidates)
    return tuple(_mapping(value, field_name="evaluation metric") for value in values)


def _hypothesis_result(
    metrics: Sequence[Mapping[str, Any]],
    *,
    candidate_ids: set[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    observed = False
    for row in metrics:
        r2 = _finite_number(row.get("r2_oos"), field_name="r2_oos")
        if r2 is None:
            continue
        observed = True
        if r2 > 0 and (candidate_ids is None or str(row.get("candidate_id")) in candidate_ids):
            evidence.append(
                {
                    "candidate_id": str(row.get("candidate_id")),
                    "horizon_months": int(row.get("horizon_months")),
                    "split": str(row.get("split")),
                    "r2_oos": r2,
                }
            )
    if evidence:
        return "supported", evidence
    return ("not_supported" if observed else "not_evaluable"), evidence


def _decision_records(source: Any, plan: Any, gate_decision: Any) -> list[dict[str, Any]]:
    if gate_decision is None:
        return []
    mapping = _mapping(gate_decision, field_name="promotion gate decision")
    decisions = mapping.get("candidate_decisions", mapping.get("decisions", ()))
    if decisions is None:
        return []
    if isinstance(decisions, Mapping):
        decisions = tuple(decisions.values())
    if not isinstance(decisions, (list, tuple)):
        raise OutputSchemaError("candidate_decisions del gate debe ser una colección")
    return [dict(_mapping(item, field_name="candidate decision")) for item in decisions]


def serialize_decision(
    plan: Any,
    *,
    run_id: str,
    experiment_id: str | None = None,
    metrics: Any = (),
    gate_decision: Any = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construye ``hipotesis_decision.json`` sin crear provenance faltante.

    Los resultados de H1/H2 se derivan únicamente de métricas suministradas.
    Si no hay observaciones métricas, el resultado es explícitamente
    ``not_evaluable``; nunca se convierte la ausencia en un resultado negativo.
    """

    resolved_experiment, _product = _plan_identity(plan, experiment_id=experiment_id)
    resolved_run = _text(run_id, field_name="run_id", allow_none=False)
    metric_rows = _metric_records_for_decision(metrics, plan) if metrics is not None else ()
    hypotheses = _hypothesis_mapping(plan)
    h1_result, h1_evidence = _hypothesis_result(metric_rows)
    frequency_candidates: set[str] = set()
    for candidate in _plan_get(plan, "candidates", default=()):
        candidate_id = _candidate_id_value(candidate)
        components = _candidate_components_value(candidate)
        if components in (("D5",), ("D3", "D4", "D5")):
            frequency_candidates.add(candidate_id)
    h2_result, h2_evidence = _hypothesis_result(
        metric_rows, candidate_ids=frequency_candidates
    )

    plan_hash = _text(
        _plan_get(plan, "plan_hash", default=None), field_name="plan_hash", allow_none=False
    )
    data_cutoff = _timestamp_text(
        _plan_get(plan, "data_cutoff", "Data_Cutoff", default=None),
        field_name="data_cutoff",
        allow_none=False,
    )
    gate_mapping = None if gate_decision is None else dict(_mapping(gate_decision, field_name="promotion gate"))
    decision_rows = _decision_records(metrics, plan, gate_decision)
    if not decision_rows and gate_mapping is not None:
        decision_rows = _decision_records(metrics, plan, gate_mapping)

    context: dict[str, Any] = {
        "schema_version": 1,
        "run_id": resolved_run,
        "experiment_id": resolved_experiment,
        "product_id": PRODUCT_ID,
        "status": RESEARCH_STATUS,
        "exploratory": True,
        "research_label": RESEARCH_LABEL,
        "kind": OUTPUT_KIND,
        "output_status": OUTPUT_STATUS,
        "hypotheses": {
            H1: {
                **hypotheses[H1],
                "result": h1_result,
                "evidence": h1_evidence,
            },
            H2: {
                **hypotheses[H2],
                "result": h2_result,
                "evidence": h2_evidence,
            },
        },
        "plan_hash": plan_hash,
        "selection_rule": _text(
            _plan_get(plan, "selection_rule", default="rank_full_r2_then_mae_then_candidate_id"),
            field_name="selection_rule",
            allow_none=False,
        ),
        "primary_metric": _text(
            _plan_get(plan, "primary_metric", default="r2_oos"),
            field_name="primary_metric",
            allow_none=False,
        ),
        "target_series": _text(
            _plan_get(plan, "target_series", default="banrep_trm_1"),
            field_name="target_series",
            allow_none=False,
        ),
        "target_definition": "100 * (ln(TRM[t+h]) - ln(TRM[t]))",
        "data_cutoff": data_cutoff,
        "horizons_months": [int(value) for value in _plan_get(plan, "horizons", default=REQUIRED_HORIZONS)],
        "evaluation_splits": [str(value) for value in _plan_get(plan, "splits", default=REQUIRED_SPLITS)],
        "benchmark": {
            "id": BENCHMARK_ID,
            "return_prediction": float(BENCHMARK_RETURN_PREDICTION),
            "same_observations": True,
        },
        "label_maturity_rule": "i_plus_h_strictly_before_origin",
        "minimum_mature_training": int(
            _plan_get(plan, "minimum_mature_training", default=60)
        ),
        "promotion_gate": gate_mapping,
        "candidate_decisions": decision_rows,
        "eligibility_scope": (
            gate_mapping.get("eligibility_scope", "methodological_review")
            if gate_mapping is not None
            else "methodological_review"
        ),
        "warnings": [NON_CAUSAL_WARNING, NO_FINANCIAL_USE_WARNING, MONTHLY_FORECAST_WARNING],
        "warning_no_causality": NON_CAUSAL_WARNING,
        "warning_no_financial_use": NO_FINANCIAL_USE_WARNING,
        "monthly_forecast_connected": False,
        "limitations": {
            "target_series": "banrep_trm_1",
            "horizons_months": [int(value) for value in _plan_get(plan, "horizons", default=REQUIRED_HORIZONS)],
            "evaluation_splits": [str(value) for value in _plan_get(plan, "splits", default=REQUIRED_SPLITS)],
            "interpretation": "La evidencia es exploratoria y no causal.",
        },
    }
    return _json_value(context)


hypothesis_decision = serialize_decision


# ---------------------------------------------------------------------------
# CSV/JSON bytes and publisher
# ---------------------------------------------------------------------------


def _csv_cell(value: Any) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            raise OutputSchemaError("No se puede escribir un float no finito en CSV")
        return repr(number)
    if isinstance(value, (list, tuple, set, frozenset, Mapping)):
        return json.dumps(_json_value(value), ensure_ascii=False, separators=(",", ":"))
    return str(value)


def records_to_csv(records: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    """Serializa records con columnas y saltos de línea estables."""

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for record in records:
        unknown = sorted(set(record) - set(columns))
        missing = sorted(set(columns) - set(record))
        if unknown or missing:
            raise OutputSchemaError(
                f"Registro no concilia con columnas: missing={missing}, extra={unknown}"
            )
        writer.writerow([_csv_cell(record[column]) for column in columns])
    return output.getvalue()


def _decision_json(document: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            _json_value(document),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise OutputSchemaError(f"hipotesis_decision.json no es JSON válido: {error}") from error


def _relative_path(path: Path, project: ProjectPaths) -> str:
    return project.relative(path)


def _target_paths(project: ProjectPaths) -> tuple[Path, ...]:
    namespace = project.root / OUTPUT_NAMESPACE
    return tuple(namespace / filename for filename in OUTPUT_FILENAMES)


def _existing_identity(path: Path) -> tuple[str | None, str | None]:
    """Lee solo la identidad de un output existente para el error de conflicto."""

    try:
        if path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, Mapping):
                return (
                    _text(value.get("experiment_id"), field_name="experiment_id"),
                    _text(value.get("run_id"), field_name="run_id"),
                )
            return None, None
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            first = next(reader, None)
            if first is None:
                return None, None
            return (
                _text(first.get("experiment_id"), field_name="experiment_id"),
                _text(first.get("run_id"), field_name="run_id"),
            )
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error, OutputSchemaError):
        return None, None


def _check_no_conflict(
    targets: Sequence[Path], *, experiment_id: str, run_id: str
) -> None:
    existing = [path for path in targets if path.exists()]
    if not existing:
        return
    identities = [_existing_identity(path) for path in existing]
    same_pair = [
        path
        for path, identity in zip(existing, identities)
        if identity == (experiment_id, run_id)
    ]
    if same_pair:
        message = (
            "Ya existe una versión para el par "
            f"(Experiment_ID={experiment_id!r}, Run_ID={run_id!r}): "
            + ", ".join(str(path) for path in same_pair)
        )
    else:
        # A fixed route cannot safely replace another run: doing so would erase
        # historical evidence even when its pair differs.
        message = (
            "Las rutas de wavelet_optimization ya están versionadas y no se "
            "sobrescriben; conserve el histórico antes de publicar otra corrida: "
            + ", ".join(str(path) for path in existing)
        )
    raise OutputVersionConflict(
        message,
        experiment_id=experiment_id,
        run_id=run_id,
        paths=existing,
    )


def _write_group_atomically(files: Sequence[tuple[Path, str]]) -> None:
    """Escribe un grupo de archivos con temporales locales y rollback best effort."""

    if not files:
        return
    parent = files[0][0].parent
    parent.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    committed: list[Path] = []
    try:
        for target, content in files:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
            )
            temporary = Path(temporary_name)
            staged.append((temporary, target))
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
            committed.append(target)
    except Exception:
        for temporary, _target in staged:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        for target in committed:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
        raise


class OutputPublisher:
    """Valida y publica los cuatro outputs de la variante.

    ``require_complete_provenance`` es estricto por defecto. Un caller que
    todavía está construyendo el manifest puede usar los serializadores puros
    o pasar ``False`` explícitamente en una prueba/control intermedio; la
    publicación oficial no debe marcar una corrida incompleta como completa.
    """

    output_namespace: ClassVar[str] = OUTPUT_NAMESPACE
    output_kind: ClassVar[str] = OUTPUT_KIND
    output_status: ClassVar[str] = OUTPUT_STATUS

    def __init__(
        self,
        *,
        paths: ProjectPaths | Path | str | None = None,
        require_complete_provenance: bool = True,
    ) -> None:
        if paths is None:
            self.paths = project_paths()
        elif isinstance(paths, ProjectPaths):
            self.paths = paths
        else:
            self.paths = ProjectPaths.from_root(Path(paths))
        self.require_complete_provenance = bool(require_complete_provenance)

    @property
    def output_paths(self) -> tuple[Path, ...]:
        return _target_paths(self.paths)

    @property
    def output_metadata(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in OUTPUT_METADATA.items()}

    def build_documents(
        self,
        plan: Any,
        bundle: Any,
        manifest: Any,
        *,
        gate_decision: Any = None,
        decision: Any = None,
        promotion_gate: Any = None,
        gate: Any = None,
        metrics: Any = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
    ) -> PublicationDocuments:
        """Construye y valida todo en memoria, sin tocar el filesystem."""

        manifest_mapping, resolved_run, resolved_experiment, _product = _validate_identity(
            plan,
            manifest,
            run_id=run_id,
            experiment_id=experiment_id,
        )
        selected_gate = gate_decision if gate_decision is not None else decision
        if selected_gate is None:
            selected_gate = promotion_gate
        if selected_gate is None:
            selected_gate = _get(manifest_mapping, "promotion_gate", "gate", default=None)
        selected_metrics = metrics
        if selected_metrics is None:
            selected_metrics = bundle

        if selected_gate is None:
            gate_object = gate
            if gate_object is None and promotion_gate is not None and not isinstance(promotion_gate, Mapping):
                gate_object = promotion_gate
            if gate_object is not None:
                evaluator = getattr(gate_object, "evaluate_bundle", None)
                if callable(evaluator):
                    selected_gate = evaluator(plan, bundle, manifest_mapping)
                else:
                    evaluator = getattr(gate_object, "evaluate", None)
                    if callable(evaluator):
                        selected_gate = evaluator(
                            plan,
                            selected_metrics,
                            getattr(bundle, "coverage", ()),
                            manifest_mapping,
                        )
                    elif callable(gate_object):
                        selected_gate = gate_object(
                            plan,
                            selected_metrics,
                            getattr(bundle, "coverage", ()),
                            manifest_mapping,
                        )
        if selected_gate is None:
            bundle_decisions = getattr(bundle, "decisions", ())
            bundle_decisions = bundle_decisions() if callable(bundle_decisions) else bundle_decisions
            if bundle_decisions:
                decision_rows = [
                    dict(_mapping(item, field_name="candidate decision"))
                    for item in bundle_decisions
                ]
                selected_gate = {
                    "schema_version": 1,
                    "gate": "promotion_eligibility",
                    "eligibility_scope": "methodological_review",
                    "candidate_decisions": decision_rows,
                    "decisions": decision_rows,
                    "research_only": True,
                    "review_only": True,
                    "promotion_authorized": False,
                }
        if selected_gate is not None and not isinstance(selected_gate, Mapping):
            selected_gate = _mapping(selected_gate, field_name="promotion gate")
        selected_gate_mapping = None if selected_gate is None else dict(selected_gate)

        if self.require_complete_provenance:
            missing = _provenance_missing(
                manifest_mapping,
                expected_paths=OUTPUT_RELATIVE_PATHS,
                gate_decision=selected_gate_mapping,
            )
            if missing:
                raise MissingProvenanceError(
                    "No se puede publicar una corrida con provenance incompleto; "
                    f"faltan: {', '.join(missing)}"
                )

        prediction_source = bundle
        prediction_records = tuple(
            serialize_prediction_records(
                prediction_source,
                plan,
                run_id=resolved_run,
                experiment_id=resolved_experiment,
            )
        )
        evaluation_source = selected_metrics if metrics is not None else bundle
        eligibility_scope = (
            selected_gate_mapping.get("eligibility_scope", "methodological_review")
            if selected_gate_mapping is not None
            else "methodological_review"
        )
        evaluation_records = tuple(
            serialize_evaluation_records(
                evaluation_source,
                plan,
                run_id=resolved_run,
                experiment_id=resolved_experiment,
                eligibility_scope=str(eligibility_scope),
            )
        )
        coverage_records = tuple(serialize_coverage_records(bundle))
        decision_document = serialize_decision(
            plan,
            run_id=resolved_run,
            experiment_id=resolved_experiment,
            metrics=evaluation_source,
            gate_decision=selected_gate_mapping,
            provenance=manifest_mapping,
        )
        # The decision JSON must preserve an explicit gate result if one was
        # supplied. ``serialize_decision`` has no hidden fallback decision.
        return PublicationDocuments(
            predictions=prediction_records,
            evaluation=evaluation_records,
            coverage=coverage_records,
            decision=decision_document,
            run_id=resolved_run,
            experiment_id=resolved_experiment,
        )

    def publish(
        self,
        plan: Any,
        bundle: Any,
        manifest: Any,
        *,
        gate_decision: Any = None,
        decision: Any = None,
        promotion_gate: Any = None,
        gate: Any = None,
        metrics: Any = None,
        run_id: str | None = None,
        experiment_id: str | None = None,
    ) -> tuple[str, ...]:
        """Publica exactamente cuatro rutas relativas y conserva históricos."""

        documents = self.build_documents(
            plan,
            bundle,
            manifest,
            gate_decision=gate_decision,
            decision=decision,
            promotion_gate=promotion_gate,
            gate=gate,
            metrics=metrics,
            run_id=run_id,
            experiment_id=experiment_id,
        )
        targets = self.output_paths
        _check_no_conflict(
            targets,
            experiment_id=documents.experiment_id,
            run_id=documents.run_id,
        )
        contents = (
            records_to_csv(documents.predictions, PREDICTION_COLUMNS),
            records_to_csv(documents.evaluation, EVALUATION_COLUMNS),
            records_to_csv(documents.coverage, COVERAGE_COLUMNS),
            _decision_json(documents.decision),
        )
        _write_group_atomically(tuple(zip(targets, contents)))
        return tuple(_relative_path(path, self.paths) for path in targets)

    # Explicit aliases make the API easy to discover from the design's name.
    publish_outputs = publish
    write = publish


# Functional facade for callers that do not need a publisher instance.
def publish_outputs(
    plan: Any,
    bundle: Any,
    manifest: Any,
    *,
    paths: ProjectPaths | Path | str | None = None,
    require_complete_provenance: bool = True,
    **kwargs: Any,
) -> tuple[str, ...]:
    return OutputPublisher(
        paths=paths,
        require_complete_provenance=require_complete_provenance,
    ).publish(plan, bundle, manifest, **kwargs)


# Public aliases used by integrations/tests that name the files rather than
# the generic table type.
serialize_predicciones_por_origen = serialize_predictions
serialize_evaluacion_por_candidato = serialize_evaluation
serialize_cobertura_point_in_time = serialize_coverage
serialize_hipotesis_decision = serialize_decision


__all__ = [
    "COVERAGE_COLUMNS",
    "COVERAGE_FILENAME",
    "COVERAGE_SCHEMA",
    "DECISION_FILENAME",
    "DECISION_SCHEMA_NAME",
    "EVALUATION_COLUMNS",
    "EVALUATION_FILENAME",
    "EVALUATION_SCHEMA",
    "H1",
    "H2",
    "MissingProvenanceError",
    "MONTHLY_FORECAST_WARNING",
    "NON_CAUSAL_WARNING",
    "NO_FINANCIAL_USE_WARNING",
    "OUTPUT_FILENAMES",
    "OUTPUT_KIND",
    "OUTPUT_METADATA",
    "OUTPUT_NAMESPACE",
    "OUTPUT_RELATIVE_PATHS",
    "OUTPUT_STATUS",
    "OutputConflictError",
    "OutputPublisher",
    "OutputSchema",
    "OutputSchemaError",
    "OutputVersionConflict",
    "PREDICTION_COLUMNS",
    "PREDICTIONS_FILENAME",
    "PREDICTION_SCHEMA",
    "PublicationDocuments",
    "PublicationError",
    "PublishingError",
    "RESEARCH_LABEL",
    "SchemaValidationError",
    "VersionConflictError",
    "coverage_frame",
    "evaluation_frame",
    "hypothesis_decision",
    "publish_outputs",
    "records_to_csv",
    "serialize_cobertura_point_in_time",
    "serialize_coverage",
    "serialize_coverage_records",
    "serialize_decision",
    "serialize_evaluacion_por_candidato",
    "serialize_evaluation",
    "serialize_evaluation_records",
    "serialize_hipotesis_decision",
    "serialize_predicciones_por_origen",
    "serialize_prediction_records",
    "serialize_predictions",
    "predictions_frame",
]
