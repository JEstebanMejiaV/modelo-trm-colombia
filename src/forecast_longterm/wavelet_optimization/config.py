"""Contratos de preinscripción para la investigación wavelet de largo horizonte.

Este módulo contiene únicamente la configuración inmutable de la variante. No
lee snapshots, ejecuta backtests ni publica resultados. La separación es
intencional: el resto de la investigación solo puede empezar con un
:class:`ResearchPlan` validado y congelado.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd


class ConfigurationError(ValueError):
    """Error de configuración de la investigación wavelet."""


class PlanValidationError(ConfigurationError):
    """El plan no satisface un contrato de preinscripción."""


class VariantSchemaError(ConfigurationError):
    """El documento TOML no satisface el schema de la variante."""


class PlanMutationError(RuntimeError):
    """El plan cambió después de haber sido registrado para la evaluación."""


# Identidad y valores fijados por el diseño de la variante.
EXPERIMENT_ID = "long_horizon_research.wavelet_optimization.v1"
LEGACY_EXPERIMENT_ID = "long_horizon_research.wavelets.v1"
PRODUCT_ID = "long_horizon_research"
RESEARCH_STATUS = "research"
INFORMATION_SET = "vintage_backtest"
VINTAGE_POLICY = "vintage_backtest"
TARGET_SERIES = "banrep_trm_1"
REQUIRED_HORIZONS = (6, 12)
REQUIRED_SPLITS = ("full", "2008_2019", "2020_2022", "2023_2026")
PHASE_FULL = "full"
PHASE_SELECTION = "selection"
PHASE_HOLDOUT = "holdout"
REQUIRED_PHASES = (PHASE_FULL, PHASE_SELECTION, PHASE_HOLDOUT)
SELECTION_SPLITS = ("2008_2019", "2020_2022")
HOLDOUT_SPLITS = ("2023_2026",)
MINIMUM_MATURE_TRAINING = 60
DM_MIN_OBSERVATIONS = 12
DM_MAX_LAG_RULE = "horizon_minus_one"
PRIMARY_METRIC = "r2_oos"
SELECTION_RULE = "rank_full_r2_then_mae_then_candidate_id"
TIE_BREAK_RULE = "candidate_id_ascending"
SEED = "not_applicable"
WAVELET_FAMILY = "db4"
DWT_LEVELS = 5
BOUNDARY_MODE = "symmetric"
SIGNAL_SCALE = 100.0
ESTIMATOR = "ols_intercept_signal"
ESTIMATION_WINDOW = "expanding"

SUPPORTED_COMPONENTS = ("D1", "D2", "D3", "D4", "D5", "A5")
_COMPONENT_ORDER = {name: index for index, name in enumerate(SUPPORTED_COMPONENTS)}

H1 = "H1"
H2 = "H2"
H1_TEXT = (
    "Al menos una Candidate_Specification con Causal_Reconstruction obtiene "
    "R2_OOS mayor que cero frente al Random_Walk_Benchmark en al menos uno de "
    "los horizontes de 6 o 12 meses."
)
H2_TEXT = (
    "La mejora, si existe, se concentra en D5 (32-64m) o en la combinación "
    "preinscrita D3+D4+D5 (8-64m)."
)
DEFAULT_HYPOTHESES: tuple[dict[str, str], ...] = (
    {"id": H1, "statement": H1_TEXT},
    {"id": H2, "statement": H2_TEXT},
)

DEFAULT_VARIANT_CONFIG = Path("research/configs/long_horizon_wavelet_optimization.toml")
DEFAULT_VARIANT_SCHEMA = Path("schemas/long_horizon_wavelet_optimization.json")
VARIANT_ID = "long_horizon_wavelet_optimization"
TARGET_DEFINITION = "100 * (ln(TRM[t+h]) - ln(TRM[t]))"
BENCHMARK_ID = "random_walk"
BENCHMARK_RETURN_PREDICTION = 0.0
LABEL_MATURITY_RULE = "i_plus_h_strictly_before_origin"

_MISSING = object()
_EXPLICIT_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)


def _project_root(root: Path | None = None) -> Path:
    """Obtiene la raíz del repositorio sin hacer depender al loader del cwd."""

    if root is not None:
        return Path(root).resolve()
    try:
        from trm_model.paths import project_paths

        return project_paths().root
    except (ImportError, RuntimeError):
        # Fallback útil para una instalación aislada del paquete de investigación.
        return Path(__file__).resolve().parents[3]


def default_variant_config_path(*, root: Path | None = None) -> Path:
    """Devuelve la ruta canónica del TOML específico de la variante."""

    return _project_root(root) / DEFAULT_VARIANT_CONFIG


def default_variant_schema_path(*, root: Path | None = None) -> Path:
    """Devuelve la ruta canónica del schema JSON específico de la variante."""

    return _project_root(root) / DEFAULT_VARIANT_SCHEMA


def _as_timestamp(value: Any) -> pd.Timestamp | None:
    """Convierte una fecha a timestamp naive normalizado, o devuelve ``None``.

    La conversión es deliberadamente tolerante durante la construcción del
    dataclass. La validación estricta ocurre en ``ResearchPlan.freeze()``, lo
    que permite que un loader acumule y reporte errores de configuración en un
    único punto.
    """

    if value is None or value is pd.NaT:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _timestamp_text(value: Any) -> str:
    timestamp = _as_timestamp(value)
    if timestamp is None:
        return str(value)
    return timestamp.isoformat()


def _component_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value,)
    else:
        try:
            values = tuple(value)
        except TypeError:
            values = (value,)
    return tuple(str(component).strip() for component in values)


def _candidate_sort_key(candidate: "CandidateSpecification") -> str:
    return candidate.candidate_id


def _hypothesis_code_and_text(value: Any) -> tuple[str | None, str | None]:
    """Obtiene el identificador y el texto de las formas de mapping admitidas."""

    if not isinstance(value, Mapping):
        return None, None

    for code in (H1, H2):
        if code in value:
            text = value[code]
            return code, None if text is None else str(text).strip()

    raw_code = next(
        (
            value.get(key)
            for key in ("id", "hypothesis_id", "code", "name", "key")
            if value.get(key) is not None
        ),
        None,
    )
    code = str(raw_code).strip() if raw_code is not None else None
    raw_text = next(
        (
            value.get(key)
            for key in ("statement", "text", "description", "hypothesis")
            if value.get(key) is not None
        ),
        None,
    )
    text = str(raw_text).strip() if raw_text is not None else None
    return code, text


def _canonical_json(value: Any) -> str:
    """Serializa JSON con orden y separadores estables."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonicalize(value: Any) -> str:
    """Devuelve la representación JSON canónica de un mapping serializable.

    Para un :class:`ResearchPlan` se utiliza su payload sin ``plan_hash``. La
    función se expone para que provenance y tests puedan usar exactamente la
    misma representación que el cálculo de SHA-256.
    """

    if isinstance(value, ResearchPlan):
        value = value.canonical_dict()
    elif isinstance(value, CandidateSpecification):
        value = value.to_dict()
    return _canonical_json(value)


def canonical_json(value: Any) -> str:
    """Alias explícito de :func:`canonicalize` para consumidores externos."""

    return canonicalize(value)


def sha256_canonical(value: Any) -> str:
    """Calcula SHA-256 hexadecimal sobre JSON canónico UTF-8."""

    return hashlib.sha256(canonicalize(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CandidateSpecification:
    """Especificación individual preinscrita de señal wavelet."""

    candidate_id: str
    wavelet_family: str = WAVELET_FAMILY
    levels: int = DWT_LEVELS
    boundary_mode: str = BOUNDARY_MODE
    components: tuple[str, ...] = ()
    signal_scale: float = SIGNAL_SCALE
    estimator: str = ESTIMATOR
    estimation_window: str = ESTIMATION_WINDOW

    def __post_init__(self) -> None:
        candidate_id = str(self.candidate_id).strip()
        if not candidate_id:
            raise ValueError("CandidateSpecification.candidate_id no puede estar vacío")
        object.__setattr__(self, "candidate_id", candidate_id)

        components = _component_tuple(self.components)
        object.__setattr__(self, "components", components)

        for component in components:
            if component not in SUPPORTED_COMPONENTS:
                raise ValueError(
                    "CandidateSpecification.components contiene un componente no soportado: "
                    f"{component!r}"
                )
        if len(set(components)) != len(components):
            raise ValueError("CandidateSpecification.components no puede contener duplicados")
        if tuple(sorted(components, key=_COMPONENT_ORDER.__getitem__)) != components:
            raise ValueError("CandidateSpecification.components debe estar en orden canónico")

        if not isinstance(self.levels, int) or isinstance(self.levels, bool) or self.levels < 1:
            raise ValueError("CandidateSpecification.levels debe ser un entero positivo")
        if not str(self.wavelet_family).strip():
            raise ValueError("CandidateSpecification.wavelet_family no puede estar vacío")
        if not str(self.boundary_mode).strip():
            raise ValueError("CandidateSpecification.boundary_mode no puede estar vacío")
        if not str(self.estimator).strip():
            raise ValueError("CandidateSpecification.estimator no puede estar vacío")
        if not str(self.estimation_window).strip():
            raise ValueError("CandidateSpecification.estimation_window no puede estar vacío")
        try:
            signal_scale = float(self.signal_scale)
        except (TypeError, ValueError):
            raise ValueError("CandidateSpecification.signal_scale debe ser numérico") from None
        if not math.isfinite(signal_scale):
            raise ValueError("CandidateSpecification.signal_scale debe ser finito")
        object.__setattr__(self, "signal_scale", signal_scale)

    def to_dict(self) -> dict[str, Any]:
        """Representación JSON-friendly con nombres del contrato Python."""

        return {
            "candidate_id": self.candidate_id,
            "wavelet_family": self.wavelet_family,
            "levels": self.levels,
            "boundary_mode": self.boundary_mode,
            "components": list(self.components),
            "signal_scale": self.signal_scale,
            "estimator": self.estimator,
            "estimation_window": self.estimation_window,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateSpecification":
        """Construye un candidato desde TOML/JSON usando ``id`` o ``candidate_id``."""

        if not isinstance(value, Mapping):
            raise TypeError("CandidateSpecification requiere un mapping")
        candidate_id = value.get("candidate_id", value.get("id"))
        if candidate_id is None:
            raise ValueError("Falta candidate_id/id en CandidateSpecification")
        return cls(
            candidate_id=str(candidate_id),
            wavelet_family=str(value.get("wavelet_family", WAVELET_FAMILY)),
            levels=int(value.get("levels", DWT_LEVELS)),
            boundary_mode=str(value.get("boundary_mode", BOUNDARY_MODE)),
            components=_component_tuple(value.get("components", ())),
            signal_scale=float(value.get("signal_scale", SIGNAL_SCALE)),
            estimator=str(value.get("estimator", ESTIMATOR)),
            estimation_window=str(value.get("estimation_window", ESTIMATION_WINDOW)),
        )


BASE_CANDIDATE_GRID: tuple[CandidateSpecification, ...] = (
    CandidateSpecification("db4_l5_sym_D1", components=("D1",)),
    CandidateSpecification("db4_l5_sym_D2", components=("D2",)),
    CandidateSpecification("db4_l5_sym_D3", components=("D3",)),
    CandidateSpecification("db4_l5_sym_D4", components=("D4",)),
    CandidateSpecification("db4_l5_sym_D5", components=("D5",)),
    CandidateSpecification("db4_l5_sym_A5", components=("A5",)),
    CandidateSpecification("db4_l5_sym_D3_D4", components=("D3", "D4")),
    CandidateSpecification(
        "db4_l5_sym_D3_D4_D5", components=("D3", "D4", "D5")
    ),
)

# Nombres de conveniencia para consumidores que prefieren explicitar que la
# constante contiene especificaciones completas, no solo IDs.
BASE_CANDIDATES = BASE_CANDIDATE_GRID
BASE_CANDIDATE_SPECIFICATIONS = BASE_CANDIDATE_GRID
DEFAULT_CANDIDATES = BASE_CANDIDATE_GRID


@dataclass(frozen=True)
class ResearchPlan:
    """Plan completo de investigación antes de observar resultados OOS."""

    experiment_id: str
    product_id: str
    status: str
    information_set: str
    vintage_policy: str
    target_series: str
    horizons: tuple[int, ...]
    splits: tuple[str, ...]
    candidates: tuple[CandidateSpecification, ...]
    minimum_mature_training: int
    dm_min_observations: int
    dm_max_lag_rule: str
    data_cutoff: pd.Timestamp
    origin_dates: tuple[pd.Timestamp, ...]
    primary_metric: str
    selection_rule: str
    tie_break_rule: str
    seed: str
    hypotheses: tuple[dict[str, str], ...]
    selection_splits: tuple[str, ...] = SELECTION_SPLITS
    holdout_splits: tuple[str, ...] = HOLDOUT_SPLITS
    plan_hash: str = ""

    # Estos valores son parte del contrato y no deben derivarse de inputs.
    _REQUIRED_EXPERIMENT_ID: ClassVar[str] = EXPERIMENT_ID
    _REQUIRED_GRID: ClassVar[tuple[CandidateSpecification, ...]] = BASE_CANDIDATE_GRID

    def __post_init__(self) -> None:
        object.__setattr__(self, "horizons", tuple(self.horizons))
        object.__setattr__(self, "splits", tuple(str(split) for split in self.splits))
        object.__setattr__(
            self,
            "selection_splits",
            tuple(str(split) for split in self.selection_splits),
        )
        object.__setattr__(
            self,
            "holdout_splits",
            tuple(str(split) for split in self.holdout_splits),
        )

        candidates: list[CandidateSpecification] = []
        for candidate in self.candidates:
            if isinstance(candidate, CandidateSpecification):
                candidates.append(candidate)
            elif isinstance(candidate, Mapping):
                candidates.append(CandidateSpecification.from_mapping(candidate))
            else:
                candidates.append(candidate)  # validation gives the useful field error
        object.__setattr__(self, "candidates", tuple(candidates))

        origin_dates = []
        for origin in self.origin_dates:
            origin_dates.append(_as_timestamp(origin) or origin)
        object.__setattr__(self, "origin_dates", tuple(origin_dates))
        object.__setattr__(
            self,
            "data_cutoff",
            _as_timestamp(self.data_cutoff) or self.data_cutoff,
        )

        hypotheses = []
        for hypothesis in self.hypotheses:
            hypotheses.append(dict(hypothesis) if isinstance(hypothesis, Mapping) else hypothesis)
        object.__setattr__(self, "hypotheses", tuple(hypotheses))
        if isinstance(self.plan_hash, str):
            object.__setattr__(self, "plan_hash", self.plan_hash.strip())

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        data_cutoff: Any = _MISSING,
        origin_dates: Iterable[Any] | Any = _MISSING,
    ) -> "ResearchPlan":
        """Construye y congela un plan desde el documento de la variante.

        ``data_cutoff`` y ``origin_dates`` pueden venir del documento, pero la
        configuración distribuida de la variante omite deliberadamente ambos
        valores. En ese caso deben suministrarse explícitamente al loader.
        """

        return _research_plan_from_document(
            value,
            data_cutoff=data_cutoff,
            origin_dates=origin_dates,
        )

    @classmethod
    def from_toml(
        cls,
        path: str | Path | None = None,
        *,
        data_cutoff: Any = _MISSING,
        origin_dates: Iterable[Any] | Any = _MISSING,
        schema_path: str | Path | None = None,
        root: Path | None = None,
        paths: Any | None = None,
    ) -> "ResearchPlan":
        """Carga el TOML específico y devuelve un plan ya validado/congelado."""

        return load_research_plan(
            path,
            data_cutoff=data_cutoff,
            origin_dates=origin_dates,
            schema_path=schema_path,
            root=root,
            paths=paths,
        )

    def _validation_errors(self) -> list[str]:
        errors: list[str] = []

        exact_values = (
            ("experiment_id", self.experiment_id, EXPERIMENT_ID),
            ("product_id", self.product_id, PRODUCT_ID),
            ("status", self.status, RESEARCH_STATUS),
            ("information_set", self.information_set, INFORMATION_SET),
            ("vintage_policy", self.vintage_policy, VINTAGE_POLICY),
            ("target_series", self.target_series, TARGET_SERIES),
            ("dm_max_lag_rule", self.dm_max_lag_rule, DM_MAX_LAG_RULE),
            ("primary_metric", self.primary_metric, PRIMARY_METRIC),
            ("selection_rule", self.selection_rule, SELECTION_RULE),
            ("tie_break_rule", self.tie_break_rule, TIE_BREAK_RULE),
            ("seed", self.seed, SEED),
        )
        for field_name, actual, expected in exact_values:
            if actual != expected:
                errors.append(f"{field_name} debe ser {expected!r}; llegó {actual!r}")

        if self.experiment_id == LEGACY_EXPERIMENT_ID:
            errors.append(
                "experiment_id no puede reutilizar el ID histórico "
                f"{LEGACY_EXPERIMENT_ID!r}"
            )

        if tuple(self.horizons) != REQUIRED_HORIZONS:
            errors.append(f"horizons debe ser exactamente {REQUIRED_HORIZONS!r}")
        if tuple(self.splits) != REQUIRED_SPLITS:
            errors.append(f"splits debe ser exactamente {REQUIRED_SPLITS!r}")
        if tuple(self.selection_splits) != SELECTION_SPLITS:
            errors.append(
                f"selection_splits debe ser exactamente {SELECTION_SPLITS!r}"
            )
        if tuple(self.holdout_splits) != HOLDOUT_SPLITS:
            errors.append(f"holdout_splits debe ser exactamente {HOLDOUT_SPLITS!r}")
        if set(self.selection_splits) & set(self.holdout_splits):
            errors.append("selection_splits y holdout_splits no pueden solaparse")
        if set(self.selection_splits) | set(self.holdout_splits) != set(REQUIRED_SPLITS) - {PHASE_FULL}:
            errors.append("selection_splits y holdout_splits deben cubrir todos los splits no-full")

        if self.minimum_mature_training != MINIMUM_MATURE_TRAINING:
            errors.append(
                "minimum_mature_training debe ser "
                f"{MINIMUM_MATURE_TRAINING}; llegó {self.minimum_mature_training!r}"
            )
        if self.dm_min_observations != DM_MIN_OBSERVATIONS:
            errors.append(
                f"dm_min_observations debe ser {DM_MIN_OBSERVATIONS}; "
                f"llegó {self.dm_min_observations!r}"
            )

        cutoff = _as_timestamp(self.data_cutoff)
        if cutoff is None:
            errors.append("data_cutoff/Data_Cutoff debe ser una fecha explícita válida")

        if not self.origin_dates:
            errors.append("origin_dates no puede estar vacío")
        else:
            parsed_origins: list[pd.Timestamp] = []
            for index, origin in enumerate(self.origin_dates):
                timestamp = _as_timestamp(origin)
                if timestamp is None:
                    errors.append(f"origin_dates[{index}] no es una fecha válida: {origin!r}")
                else:
                    parsed_origins.append(timestamp)
            if len(parsed_origins) != len(set(parsed_origins)):
                errors.append("origin_dates no puede contener fechas duplicadas")
            if cutoff is not None and any(origin > cutoff for origin in parsed_origins):
                errors.append("origin_dates no puede contener fechas posteriores a data_cutoff")

        expected_by_id = {candidate.candidate_id: candidate for candidate in self._REQUIRED_GRID}
        seen_ids: list[str] = []
        for index, candidate in enumerate(self.candidates):
            if not isinstance(candidate, CandidateSpecification):
                errors.append(f"candidates[{index}] no es CandidateSpecification")
                continue
            seen_ids.append(candidate.candidate_id)
            if candidate.wavelet_family != WAVELET_FAMILY:
                errors.append(f"candidates[{index}].wavelet_family debe ser 'db4'")
            if candidate.levels != DWT_LEVELS:
                errors.append(f"candidates[{index}].levels debe ser 5")
            if candidate.boundary_mode != BOUNDARY_MODE:
                errors.append(f"candidates[{index}].boundary_mode debe ser 'symmetric'")
            if candidate.signal_scale != SIGNAL_SCALE:
                errors.append(f"candidates[{index}].signal_scale debe ser {SIGNAL_SCALE}")
            if candidate.estimator != ESTIMATOR:
                errors.append(
                    f"candidates[{index}].estimator debe ser {ESTIMATOR!r}"
                )
            if candidate.estimation_window != ESTIMATION_WINDOW:
                errors.append(
                    f"candidates[{index}].estimation_window debe ser {ESTIMATION_WINDOW!r}"
                )
            expected = expected_by_id.get(candidate.candidate_id)
            if expected is None:
                errors.append(
                    f"candidates[{index}].candidate_id fuera de la grilla base: "
                    f"{candidate.candidate_id!r}"
                )
            elif candidate.to_dict() != expected.to_dict():
                errors.append(
                    f"candidates[{index}] no concilia con la especificación base "
                    f"{candidate.candidate_id!r}"
                )

        if len(seen_ids) != len(set(seen_ids)):
            errors.append("candidates no puede contener candidate_id duplicados")
        expected_ids = set(expected_by_id)
        actual_ids = set(seen_ids)
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        if missing:
            errors.append(f"faltan candidatos de la grilla base: {missing!r}")
        if extra:
            errors.append(f"hay candidatos fuera de la grilla base: {extra!r}")

        hypothesis_codes: set[str] = set()
        for index, hypothesis in enumerate(self.hypotheses):
            code, text = _hypothesis_code_and_text(hypothesis)
            if code not in (H1, H2):
                errors.append(
                    f"hypotheses[{index}] debe identificar H1 o H2; llegó {code!r}"
                )
            else:
                hypothesis_codes.add(code)
            if not text:
                errors.append(f"hypotheses[{index}] requiere texto no vacío")
        missing_hypotheses = sorted({H1, H2} - hypothesis_codes)
        if missing_hypotheses:
            errors.append(f"faltan hipótesis preinscritas: {missing_hypotheses!r}")

        if self.plan_hash and (
            len(self.plan_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.plan_hash.lower())
        ):
            errors.append("plan_hash debe ser SHA-256 hexadecimal de 64 caracteres")

        return errors

    def validate(self) -> None:
        """Valida todos los invariantes de preinscripción del plan."""

        errors = self._validation_errors()
        if errors:
            raise PlanValidationError("ResearchPlan inválido:\n- " + "\n- ".join(errors))

    def phase_for_split(self, split: str) -> str:
        """Devuelve la fase canónica de un split preinscrito."""

        value = str(split).strip()
        if value == PHASE_FULL:
            return PHASE_FULL
        if value in self.selection_splits:
            return PHASE_SELECTION
        if value in self.holdout_splits:
            return PHASE_HOLDOUT
        raise PlanValidationError(f"split no pertenece a una fase preinscrita: {split!r}")

    def splits_for_phase(self, phase: str, *, include_full: bool = False) -> tuple[str, ...]:
        """Devuelve los splits autorizados para una fase de evaluación."""

        value = str(phase).strip().lower()
        if value == PHASE_FULL:
            return (PHASE_FULL,)
        if value == PHASE_SELECTION:
            result = self.selection_splits
        elif value == PHASE_HOLDOUT:
            result = self.holdout_splits
        else:
            raise PlanValidationError(f"phase no soportada: {phase!r}")
        if include_full:
            return (PHASE_FULL, *result)
        return tuple(result)

    @property
    def phases(self) -> tuple[str, ...]:
        """Fases de la variante en orden de ejecución/reporting."""

        return REQUIRED_PHASES

    def to_dict(self, *, include_plan_hash: bool = True) -> dict[str, Any]:
        """Devuelve el plan en una forma apta para JSON/TOML provenance."""

        value: dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "product_id": self.product_id,
            "status": self.status,
            "information_set": self.information_set,
            "vintage_policy": self.vintage_policy,
            "target_series": self.target_series,
            "horizons": list(self.horizons),
            "splits": list(self.splits),
            "selection_splits": list(self.selection_splits),
            "holdout_splits": list(self.holdout_splits),
            "phases": {
                PHASE_FULL: [PHASE_FULL],
                PHASE_SELECTION: list(self.selection_splits),
                PHASE_HOLDOUT: list(self.holdout_splits),
            },
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "minimum_mature_training": self.minimum_mature_training,
            "dm_min_observations": self.dm_min_observations,
            "dm_max_lag_rule": self.dm_max_lag_rule,
            "data_cutoff": _timestamp_text(self.data_cutoff),
            "origin_dates": [_timestamp_text(origin) for origin in self.origin_dates],
            "primary_metric": self.primary_metric,
            "selection_rule": self.selection_rule,
            "tie_break_rule": self.tie_break_rule,
            "seed": self.seed,
            "hypotheses": [dict(hypothesis) for hypothesis in self.hypotheses],
        }
        if include_plan_hash:
            value["plan_hash"] = self.plan_hash
        return value

    def canonical_dict(self) -> dict[str, Any]:
        """Payload orden-independent usado para canonicalización y hash."""

        value = self.to_dict(include_plan_hash=False)
        value["candidates"] = sorted(
            value["candidates"], key=lambda candidate: str(candidate["candidate_id"])
        )
        value["origin_dates"] = sorted(value["origin_dates"])
        value["hypotheses"] = sorted(
            value["hypotheses"],
            key=lambda hypothesis: str(
                _hypothesis_code_and_text(hypothesis)[0] or ""
            ),
        )
        return value

    def canonical_json(self) -> str:
        """JSON canónico del plan, excluyendo el hash derivado."""

        return _canonical_json(self.canonical_dict())

    def compute_plan_hash(self) -> str:
        """Calcula el SHA-256 del payload canónico sin ``plan_hash``."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    # Alias legibles para callers que prefieran ``hash`` o ``fingerprint``.
    canonical_hash = compute_plan_hash
    fingerprint = compute_plan_hash

    def freeze(self) -> "ResearchPlan":
        """Valida y registra el hash del plan antes de cualquier predicción.

        El dataclass permanece ``frozen`` para impedir asignaciones normales.
        ``plan_hash`` es el único campo derivado que se completa internamente
        durante el freeze; el guard compara siempre el payload completo, de
        modo que también detecta mutaciones de mappings anidados.
        """

        self.validate()
        computed_hash = self.compute_plan_hash()
        if self.plan_hash and self.plan_hash != computed_hash:
            raise PlanValidationError(
                "plan_hash existente no concilia con la canonicalización actual: "
                f"{self.plan_hash} != {computed_hash}"
            )
        object.__setattr__(self, "plan_hash", computed_hash)
        return self

    @property
    def is_frozen(self) -> bool:
        """Indica si el hash almacenado concilia con el payload actual."""

        return bool(self.plan_hash) and self.plan_hash == self.compute_plan_hash()


def _effective_root(root: Path | None, paths: Any | None) -> Path | None:
    """Acepta el mismo objeto ``paths`` que usan los loaders del repositorio."""

    if paths is None:
        return root
    paths_root = getattr(paths, "root", None)
    if paths_root is None:
        raise TypeError("paths debe exponer una raíz de proyecto en paths.root")
    resolved_paths_root = Path(paths_root).resolve()
    if root is not None and Path(root).resolve() != resolved_paths_root:
        raise ConfigurationError("root y paths.root no pueden apuntar a raíces distintas")
    return resolved_paths_root


def _resolve_variant_path(
    value: str | Path | None,
    *,
    default: Path,
    root: Path | None,
) -> Path:
    if value is None:
        return _project_root(root) / default
    path = Path(value)
    return path if path.is_absolute() else _project_root(root) / path


def _read_variant_toml(
    path: str | Path | None,
    *,
    root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    config_path = _resolve_variant_path(path, default=DEFAULT_VARIANT_CONFIG, root=root)
    if not config_path.is_file():
        raise FileNotFoundError(f"No existe configuración de la variante: {config_path}")
    try:
        value = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise VariantSchemaError(
            f"TOML inválido en la configuración de la variante {config_path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise VariantSchemaError(
            f"La configuración de la variante debe ser un objeto TOML: {config_path}"
        )
    return value, config_path


def validate_variant_document(
    document: Mapping[str, Any],
    *,
    schema_path: str | Path | None = None,
    root: Path | None = None,
) -> None:
    """Valida la estructura TOML contra el schema y sus requisitos de seguridad."""

    if not isinstance(document, Mapping):
        raise VariantSchemaError("La configuración de la variante debe ser un mapping")
    resolved_schema = _resolve_variant_path(
        schema_path,
        default=DEFAULT_VARIANT_SCHEMA,
        root=root,
    )
    if not resolved_schema.is_file():
        raise FileNotFoundError(f"No existe schema de la variante: {resolved_schema}")
    try:
        from trm_model.validation.contracts import validate_document

        validate_document(dict(document), resolved_schema)
    except ValueError as exc:
        # ContractError hereda de ValueError; se expone un error específico del
        # loader sin ocultar el detalle de la ruta/campo inválido.
        raise VariantSchemaError(str(exc)) from exc

    if document.get("data_cutoff_required") is not True:
        raise VariantSchemaError(
            "data_cutoff_required debe ser true: Data_Cutoff no se puede inferir "
            "ni completar con la última observación disponible"
        )
    if "data_cutoff" in document:
        _require_explicit_date(document["data_cutoff"], "data_cutoff/Data_Cutoff")
    if "origin_dates" in document:
        _require_origin_dates(document["origin_dates"])
    _require_variant_semantics(document)


def _require_explicit_date(value: Any, field_name: str) -> pd.Timestamp:
    """Acepta una fecha dada por el caller, nunca marcadores ni fechas dinámicas."""

    if value is _MISSING or value is None:
        raise ConfigurationError(
            f"{field_name} es obligatorio: entregue una fecha ISO explícita al loader; "
            "no se infiere ni se extrapola"
        )
    if isinstance(value, str):
        text = value.strip()
        if not text or _EXPLICIT_DATE_PATTERN.fullmatch(text) is None:
            raise ConfigurationError(
                f"{field_name} debe ser una fecha ISO explícita (YYYY-MM-DD); "
                f"llegó {value!r}"
            )
    elif isinstance(value, (int, float, complex, bool)):
        raise ConfigurationError(
            f"{field_name} debe ser una fecha explícita, no un número: {value!r}"
        )
    timestamp = _as_timestamp(value)
    if timestamp is None:
        raise ConfigurationError(
            f"{field_name} debe ser una fecha ISO explícita válida; llegó {value!r}"
        )
    return timestamp


def _require_origin_dates(value: Any) -> tuple[pd.Timestamp, ...]:
    if value is _MISSING or value is None:
        raise ConfigurationError(
            "origin_dates es obligatorio cuando el TOML no declara orígenes; "
            "el loader no puede fabricar fechas de evaluación"
        )
    if isinstance(value, (str, bytes)):
        raise ConfigurationError("origin_dates debe ser una secuencia de fechas explícitas")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ConfigurationError(
            "origin_dates debe ser una secuencia de fechas explícitas"
        ) from exc
    if not values:
        raise ConfigurationError("origin_dates no puede estar vacío")
    return tuple(
        _require_explicit_date(origin, f"origin_dates[{index}]")
        for index, origin in enumerate(values)
    )


def _document_value_or_override(
    document: Mapping[str, Any],
    key: str,
    override: Any,
) -> Any:
    return document.get(key, _MISSING) if override is _MISSING else override


def _require_variant_semantics(document: Mapping[str, Any]) -> None:
    """Valida contratos que el schema estructural no puede expresar."""

    expected_top_level = {
        "schema_version": 1,
        "variant_id": VARIANT_ID,
        "experiment_id": EXPERIMENT_ID,
        "product_id": PRODUCT_ID,
        "status": RESEARCH_STATUS,
        "information_set": INFORMATION_SET,
        "vintage_policy": VINTAGE_POLICY,
        "target_series": TARGET_SERIES,
        "target_definition": TARGET_DEFINITION,
        "horizons_months": list(REQUIRED_HORIZONS),
        "evaluation_splits": list(REQUIRED_SPLITS),
        "selection_splits": list(SELECTION_SPLITS),
        "holdout_splits": list(HOLDOUT_SPLITS),
        "minimum_mature_training": MINIMUM_MATURE_TRAINING,
        "dm_min_observations": DM_MIN_OBSERVATIONS,
        "dm_max_lag_rule": DM_MAX_LAG_RULE,
        "primary_metric": PRIMARY_METRIC,
        "selection_rule": SELECTION_RULE,
        "tie_break_rule": TIE_BREAK_RULE,
        "seed": SEED,
    }
    for key, expected in expected_top_level.items():
        if document.get(key) != expected:
            raise ConfigurationError(
                f"{key} debe ser {expected!r}; llegó {document.get(key)!r}"
            )

    dwt = document["dwt"]
    expected_dwt = {
        "wavelet": WAVELET_FAMILY,
        "levels": DWT_LEVELS,
        "boundary_mode": BOUNDARY_MODE,
        "signal_scale": SIGNAL_SCALE,
    }
    for key, expected in expected_dwt.items():
        if dwt.get(key) != expected:
            raise ConfigurationError(
                f"dwt.{key} debe ser {expected!r}; llegó {dwt.get(key)!r}"
            )

    benchmark = document["benchmark"]
    expected_benchmark = {
        "id": BENCHMARK_ID,
        "return_prediction": BENCHMARK_RETURN_PREDICTION,
        "same_observations": True,
    }
    for key, expected in expected_benchmark.items():
        if benchmark.get(key) != expected:
            raise ConfigurationError(
                f"benchmark.{key} debe ser {expected!r}; llegó {benchmark.get(key)!r}"
            )

    label_maturity = document["label_maturity"]
    expected_maturity = {
        "rule": LABEL_MATURITY_RULE,
        "minimum_mature_training": MINIMUM_MATURE_TRAINING,
        "observable_by_cutoff": True,
    }
    for key, expected in expected_maturity.items():
        if label_maturity.get(key) != expected:
            raise ConfigurationError(
                f"label_maturity.{key} debe ser {expected!r}; "
                f"llegó {label_maturity.get(key)!r}"
            )

    expected_gate = {
        "full_r2_positive": True,
        "full_mae_below_benchmark": True,
        "full_rmse_below_benchmark": True,
        "dm_p_value_max": 0.05,
        "minimum_positive_splits": 3,
        "split_min_observations": DM_MIN_OBSERVATIONS,
        "minimum_r2": -0.10,
        "require_causal_reconstruction": True,
        "require_label_maturity": True,
        "require_complete_pit_coverage": True,
        "require_complete_provenance": True,
    }
    gate = document["promotion_gate"]
    for key, expected in expected_gate.items():
        if gate.get(key) != expected:
            raise ConfigurationError(
                f"promotion_gate.{key} debe ser {expected!r}; llegó {gate.get(key)!r}"
            )

    expected_hypotheses = {item["id"]: item["statement"] for item in DEFAULT_HYPOTHESES}
    actual_hypotheses: dict[str, Any] = {}
    for hypothesis in document["hypotheses"]:
        code = hypothesis["id"]
        if code in actual_hypotheses:
            raise ConfigurationError(f"hypotheses no puede repetir {code!r}")
        actual_hypotheses[code] = hypothesis["statement"]
    if actual_hypotheses != expected_hypotheses:
        raise ConfigurationError(
            "hypotheses debe declarar exactamente H1 y H2 con sus textos preinscritos"
        )


def _research_plan_from_document(
    document: Mapping[str, Any],
    *,
    data_cutoff: Any = _MISSING,
    origin_dates: Iterable[Any] | Any = _MISSING,
) -> ResearchPlan:
    if not isinstance(document, Mapping):
        raise VariantSchemaError("La configuración de la variante debe ser un mapping")
    _require_variant_semantics(document)

    cutoff_value = _document_value_or_override(document, "data_cutoff", data_cutoff)
    cutoff = _require_explicit_date(cutoff_value, "data_cutoff/Data_Cutoff")
    origins_value = _document_value_or_override(document, "origin_dates", origin_dates)
    origins = _require_origin_dates(origins_value)

    candidates = tuple(
        CandidateSpecification.from_mapping(candidate)
        for candidate in document["candidates"]
    )
    plan = ResearchPlan(
        experiment_id=str(document["experiment_id"]),
        product_id=str(document["product_id"]),
        status=str(document["status"]),
        information_set=str(document["information_set"]),
        vintage_policy=str(document["vintage_policy"]),
        target_series=str(document["target_series"]),
        horizons=tuple(document["horizons_months"]),
        splits=tuple(document["evaluation_splits"]),
        candidates=candidates,
        minimum_mature_training=int(document["minimum_mature_training"]),
        dm_min_observations=int(document["dm_min_observations"]),
        dm_max_lag_rule=str(document["dm_max_lag_rule"]),
        data_cutoff=cutoff,
        origin_dates=origins,
        primary_metric=str(document["primary_metric"]),
        selection_rule=str(document["selection_rule"]),
        tie_break_rule=str(document["tie_break_rule"]),
        seed=str(document["seed"]),
        hypotheses=tuple(dict(item) for item in document["hypotheses"]),
        selection_splits=tuple(document.get("selection_splits", SELECTION_SPLITS)),
        holdout_splits=tuple(document.get("holdout_splits", HOLDOUT_SPLITS)),
    )
    return plan.freeze()


def load_research_plan(
    path: str | Path | None = None,
    *,
    data_cutoff: Any = _MISSING,
    origin_dates: Iterable[Any] | Any = _MISSING,
    schema_path: str | Path | None = None,
    root: Path | None = None,
    paths: Any | None = None,
) -> ResearchPlan:
    """Carga, valida y congela el plan de wavelet desde su TOML aislado.

    El archivo distribuido no fija una fecha de evaluación. ``data_cutoff``
    debe ser una fecha ISO/``Timestamp`` explícita, ya sea en un documento
    personalizado o como argumento de esta función; si no está disponible la
    carga falla antes de producir un plan. Los orígenes también deben ser
    explícitos para evitar que el loader fabrique una muestra de evaluación.
    """

    effective_root = _effective_root(root, paths)
    document, config_path = _read_variant_toml(path, root=effective_root)
    try:
        validate_variant_document(document, schema_path=schema_path, root=effective_root)
        if "data_cutoff" in document:
            _require_explicit_date(document["data_cutoff"], "data_cutoff/Data_Cutoff")
        if "origin_dates" in document:
            _require_origin_dates(document["origin_dates"])
        return _research_plan_from_document(
            document,
            data_cutoff=data_cutoff,
            origin_dates=origin_dates,
        )
    except ConfigurationError:
        raise
    except Exception as exc:
        raise ConfigurationError(
            f"No se pudo cargar la configuración de la variante {config_path}: {exc}"
        ) from exc


# Nombres explícitos para callers que distinguen la variante de otros planes.
load_wavelet_optimization_plan = load_research_plan
load_wavelet_optimization_config = load_research_plan
load_variant_plan = load_research_plan
load_variant_config = load_research_plan


class PreRegistrationGuard:
    """Guarda el fingerprint del plan y bloquea cambios post-registro."""

    def __init__(self, plan: ResearchPlan):
        if not isinstance(plan, ResearchPlan):
            raise TypeError("PreRegistrationGuard requiere un ResearchPlan")
        self._plan = plan.freeze()
        self._registered_hash = self._plan.plan_hash
        self._first_prediction_hash: str | None = None

    @property
    def plan(self) -> ResearchPlan:
        return self._plan

    @property
    def registered_hash(self) -> str:
        return self._registered_hash

    @property
    def first_prediction_started(self) -> bool:
        return self._first_prediction_hash is not None

    @property
    def is_frozen(self) -> bool:
        return self._plan.is_frozen

    def _resolve_plan(self, plan: ResearchPlan | None) -> ResearchPlan:
        candidate = self._plan if plan is None else plan
        if not isinstance(candidate, ResearchPlan):
            raise TypeError("El plan a comprobar debe ser ResearchPlan")
        return candidate

    def assert_unchanged(self, plan: ResearchPlan | None = None) -> bool:
        """Comprueba que el payload actual coincide con el fingerprint registrado."""

        candidate = self._resolve_plan(plan)
        current_hash = candidate.compute_plan_hash()
        stored_hash = candidate.plan_hash
        hash_mismatch = stored_hash not in ("", current_hash)
        original_hash_changed = candidate is self._plan and stored_hash != self._registered_hash
        if current_hash != self._registered_hash or hash_mismatch or original_hash_changed:
            phase = "después de la primera predicción" if self.first_prediction_started else "tras el freeze"
            raise PlanMutationError(
                "ResearchPlan mutado "
                f"{phase}: esperado {self._registered_hash}, llegó {current_hash}"
            )
        return True

    def first_prediction(self, plan: ResearchPlan | None = None) -> str:
        """Registra el hash justo antes de producir la primera predicción."""

        self.assert_unchanged(plan)
        if self._first_prediction_hash is None:
            self._first_prediction_hash = self._registered_hash
        return self._first_prediction_hash

    # Nombre alternativo útil para un evaluador que expresa la operación como
    # "marcar" en lugar de "notificar" la primera predicción.
    mark_first_prediction = first_prediction

    def freeze(self) -> ResearchPlan:
        """Revalida el plan y devuelve la instancia congelada."""

        self.assert_unchanged()
        return self._plan


# Aliases de compatibilidad semántica para integradores futuros.
PreRegistrationError = PlanMutationError


def plan_hash(plan: ResearchPlan) -> str:
    """Calcula el hash canónico de un plan sin modificarlo."""

    if not isinstance(plan, ResearchPlan):
        raise TypeError("plan_hash requiere un ResearchPlan")
    return plan.compute_plan_hash()


__all__ = [
    "BASE_CANDIDATE_GRID",
    "BASE_CANDIDATE_SPECIFICATIONS",
    "BASE_CANDIDATES",
    "BENCHMARK_ID",
    "BENCHMARK_RETURN_PREDICTION",
    "BOUNDARY_MODE",
    "CandidateSpecification",
    "ConfigurationError",
    "DEFAULT_CANDIDATES",
    "DEFAULT_HYPOTHESES",
    "DEFAULT_VARIANT_CONFIG",
    "DEFAULT_VARIANT_SCHEMA",
    "DM_MAX_LAG_RULE",
    "DM_MIN_OBSERVATIONS",
    "DWT_LEVELS",
    "ESTIMATION_WINDOW",
    "ESTIMATOR",
    "EXPERIMENT_ID",
    "H1",
    "H1_TEXT",
    "H2",
    "H2_TEXT",
    "INFORMATION_SET",
    "LABEL_MATURITY_RULE",
    "LEGACY_EXPERIMENT_ID",
    "MINIMUM_MATURE_TRAINING",
    "PlanMutationError",
    "PlanValidationError",
    "PreRegistrationError",
    "PreRegistrationGuard",
    "PRIMARY_METRIC",
    "PRODUCT_ID",
    "RESEARCH_STATUS",
    "ResearchPlan",
    "REQUIRED_HORIZONS",
    "REQUIRED_SPLITS",
    "SEED",
    "SELECTION_RULE",
    "SIGNAL_SCALE",
    "SUPPORTED_COMPONENTS",
    "TARGET_DEFINITION",
    "TARGET_SERIES",
    "TIE_BREAK_RULE",
    "VARIANT_ID",
    "VariantSchemaError",
    "VINTAGE_POLICY",
    "WAVELET_FAMILY",
    "canonical_json",
    "canonicalize",
    "default_variant_config_path",
    "default_variant_schema_path",
    "load_research_plan",
    "load_variant_config",
    "load_variant_plan",
    "load_wavelet_optimization_config",
    "load_wavelet_optimization_plan",
    "plan_hash",
    "sha256_canonical",
    "validate_variant_document",
]
