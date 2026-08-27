"""Reconstrucción wavelet causal por origen para la variante de investigación.

Este módulo no conoce los outputs históricos de ``forecast_longterm.wavelets``.
Cada llamada recibe un origen y un snapshot PIT, recorta la serie al corte
permitido y calcula una DWT nueva sobre ese prefijo. La descomposición completa
nunca se calcula ni se conserva para reutilizarla entre orígenes.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pywt

from .config import (
    BOUNDARY_MODE,
    DWT_LEVELS,
    SIGNAL_SCALE,
    SUPPORTED_COMPONENTS,
    TARGET_SERIES,
    WAVELET_FAMILY,
    CandidateSpecification,
    ResearchPlan,
)
from .snapshots import (
    BANREP_TRM_SOURCE_ID,
    ForecastOrigin,
    PointInTimeSnapshot,
    SourceVintage,
)


class ReconstructionError(ValueError):
    """Error de validación o de cálculo de una reconstrucción causal."""


class CausalReconstructionError(ReconstructionError):
    """La entrada no puede demostrar una reconstrucción causal válida."""


# Alias explícitos para callers que nombran el error según el estado de la
# fila de evaluación. Todos conservan la misma excepción concreta.
InvalidCausalReconstruction = CausalReconstructionError
CausalReconstructionInvalid = CausalReconstructionError


_COMPONENT_NAMES = SUPPORTED_COMPONENTS


def _timestamp(value: Any, field_name: str) -> pd.Timestamp:
    """Normaliza una fecha a medianoche sin inferir fechas faltantes."""

    if value is None or value is pd.NaT:
        raise CausalReconstructionError(f"{field_name} no puede ser nulo")
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise CausalReconstructionError(
            f"{field_name} no es una fecha válida: {value!r}"
        ) from error
    if pd.isna(timestamp):
        raise CausalReconstructionError(f"{field_name} no es una fecha válida: {value!r}")
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.normalize()


def _sha256_prefix(prefix: pd.Series) -> str:
    """Hash determinista de fechas y valores del prefijo usado por la DWT.

    Se incluyen las fechas y los ``float64`` crudos, pero no el nombre ni los
    atributos de pandas. Así, dos prefijos con igual contenido producen la
    misma identidad aun cuando provengan de objetos Series distintos, y un
    cambio de fecha o valor no puede colisionar con el mismo prefijo lógico.
    """

    try:
        index = pd.DatetimeIndex(prefix.index)
    except (TypeError, ValueError) as error:
        raise CausalReconstructionError(
            "El índice del prefijo no se puede representar como fechas"
        ) from error
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    dates = np.ascontiguousarray(index.asi8, dtype="<i8")
    values = np.ascontiguousarray(prefix.to_numpy(dtype=np.float64), dtype="<f8")
    length = np.asarray([len(prefix)], dtype="<u8").tobytes()
    payload = length + dates.tobytes() + values.tobytes()
    return hashlib.sha256(payload).hexdigest()


def hash_prefix(prefix: pd.Series) -> str:
    """API pública para obtener el mismo hash usado en metadata/cache."""

    return _sha256_prefix(prefix)


def _index_for_comparison(index: pd.Index) -> pd.DatetimeIndex:
    """Obtiene un índice temporal comparable sin cambiar el índice de salida."""

    if isinstance(index, pd.PeriodIndex):
        comparable = index.to_timestamp(how="start")
    elif isinstance(index, pd.DatetimeIndex):
        comparable = index
    else:
        try:
            comparable = pd.DatetimeIndex(index)
        except (TypeError, ValueError) as error:
            raise CausalReconstructionError(
                "trm_monthly debe tener un índice mensual de fechas"
            ) from error
    if comparable.tz is not None:
        comparable = comparable.tz_convert("UTC").tz_localize(None)
    if comparable.hasnans:
        raise CausalReconstructionError("El índice de trm_monthly contiene fechas faltantes")
    if not comparable.is_monotonic_increasing:
        raise CausalReconstructionError(
            "El índice de trm_monthly debe estar ordenado cronológicamente"
        )
    if not comparable.is_unique:
        raise CausalReconstructionError(
            "El índice de trm_monthly no puede contener fechas duplicadas"
        )
    return comparable


def _attribute_date(attrs: Mapping[str, Any], key: str) -> pd.Timestamp | None:
    """Lee una marca temporal opcional del objeto Series sin fabricar valores."""

    if key not in attrs or attrs[key] is None or attrs[key] is pd.NaT:
        return None
    try:
        return _timestamp(attrs[key], f"trm_monthly.attrs[{key!r}]")
    except CausalReconstructionError:
        raise


def _copy_series(series: pd.Series) -> pd.Series:
    """Copia una señal sin compartir el buffer mutable con otra reconstrucción."""

    return series.copy(deep=True)


@dataclass(frozen=True)
class ReconstructionMetadata:
    """Evidencia temporal y de parámetros de una reconstrucción causal."""

    origin_date: pd.Timestamp
    available_through: pd.Timestamp
    prefix_length: int
    prefix_first_date: pd.Timestamp
    prefix_last_date: pd.Timestamp
    prefix_sha256: str
    wavelet_family: str
    levels: int
    boundary_mode: str
    dwt_max_level: int
    uses_future_observations: bool
    source_vintage: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin_date", _timestamp(self.origin_date, "origin_date"))
        object.__setattr__(
            self,
            "available_through",
            _timestamp(self.available_through, "available_through"),
        )
        object.__setattr__(
            self,
            "prefix_first_date",
            _timestamp(self.prefix_first_date, "prefix_first_date"),
        )
        object.__setattr__(
            self,
            "prefix_last_date",
            _timestamp(self.prefix_last_date, "prefix_last_date"),
        )
        if (
            not isinstance(self.prefix_length, int)
            or isinstance(self.prefix_length, bool)
            or self.prefix_length <= 0
        ):
            raise CausalReconstructionError(
                "ReconstructionMetadata.prefix_length debe ser entero positivo"
            )
        prefix_hash = str(self.prefix_sha256).strip().lower()
        if len(prefix_hash) != 64 or any(char not in "0123456789abcdef" for char in prefix_hash):
            raise CausalReconstructionError(
                "ReconstructionMetadata.prefix_sha256 debe ser SHA-256 hexadecimal"
            )
        object.__setattr__(self, "prefix_sha256", prefix_hash)
        wavelet = str(self.wavelet_family).strip()
        boundary = str(self.boundary_mode).strip().lower()
        if not wavelet:
            raise CausalReconstructionError("wavelet_family no puede estar vacío")
        if not boundary:
            raise CausalReconstructionError("boundary_mode no puede estar vacío")
        object.__setattr__(self, "wavelet_family", wavelet)
        object.__setattr__(self, "boundary_mode", boundary)
        if (
            not isinstance(self.levels, int)
            or isinstance(self.levels, bool)
            or self.levels <= 0
        ):
            raise CausalReconstructionError("levels debe ser entero positivo")
        if (
            not isinstance(self.dwt_max_level, int)
            or isinstance(self.dwt_max_level, bool)
            or self.dwt_max_level < 0
        ):
            raise CausalReconstructionError("dwt_max_level debe ser entero no negativo")
        if not isinstance(self.uses_future_observations, bool):
            raise CausalReconstructionError("uses_future_observations debe ser bool")
        vintage = str(self.source_vintage).strip()
        if not vintage:
            raise CausalReconstructionError("source_vintage no puede estar vacío")
        object.__setattr__(self, "source_vintage", vintage)

    def validate_causal(self) -> None:
        """Falla si la metadata no puede describir un prefijo causal."""

        if self.wavelet_family != WAVELET_FAMILY:
            raise CausalReconstructionError(
                f"La metadata usa wavelet no permitida: {self.wavelet_family!r}"
            )
        if self.levels != DWT_LEVELS:
            raise CausalReconstructionError(
                f"La metadata usa levels={self.levels}; se requiere {DWT_LEVELS}"
            )
        if self.boundary_mode != BOUNDARY_MODE:
            raise CausalReconstructionError(
                f"La metadata usa boundary_mode={self.boundary_mode!r}; "
                f"se requiere {BOUNDARY_MODE!r}"
            )
        if self.uses_future_observations:
            raise CausalReconstructionError(
                "La metadata indica uses_future_observations=True"
            )
        if self.available_through > self.origin_date:
            raise CausalReconstructionError(
                "available_through es posterior al ForecastOrigin"
            )
        if self.prefix_first_date > self.prefix_last_date:
            raise CausalReconstructionError(
                "prefix_first_date es posterior a prefix_last_date"
            )
        if self.prefix_last_date > self.origin_date:
            raise CausalReconstructionError(
                "prefix_last_date es posterior al ForecastOrigin"
            )
        if self.prefix_last_date > self.available_through:
            raise CausalReconstructionError(
                "prefix_last_date excede available_through del vintage"
            )
        if self.dwt_max_level < self.levels:
            raise CausalReconstructionError(
                "dwt_max_level no alcanza el número de niveles solicitado"
            )

    @property
    def prefix_first(self) -> pd.Timestamp:
        """Alias breve para consumidores que usan nombres de serie."""

        return self.prefix_first_date

    @property
    def prefix_last(self) -> pd.Timestamp:
        """Alias breve para consumidores que usan nombres de serie."""

        return self.prefix_last_date

    def as_dict(self) -> dict[str, object]:
        """Serializa metadata a valores aptos para provenance/CSV."""

        return {
            "origin_date": self.origin_date.strftime("%Y-%m-%d"),
            "available_through": self.available_through.strftime("%Y-%m-%d"),
            "prefix_length": self.prefix_length,
            "prefix_first_date": self.prefix_first_date.strftime("%Y-%m-%d"),
            "prefix_last_date": self.prefix_last_date.strftime("%Y-%m-%d"),
            "prefix_sha256": self.prefix_sha256,
            "wavelet_family": self.wavelet_family,
            "levels": self.levels,
            "boundary_mode": self.boundary_mode,
            "dwt_max_level": self.dwt_max_level,
            "uses_future_observations": self.uses_future_observations,
            "source_vintage": self.source_vintage,
        }


@dataclass(frozen=True)
class ReconstructionResult:
    """Componentes reconstruidos y señales escaladas para los candidatos."""

    components: Mapping[str, pd.Series]
    metadata: ReconstructionMetadata
    status: str = "causal"
    signals: Mapping[str, pd.Series] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.metadata, ReconstructionMetadata):
            raise TypeError("ReconstructionResult.metadata debe ser ReconstructionMetadata")
        self.metadata.validate_causal()
        status = str(self.status).strip()
        if not status:
            raise CausalReconstructionError("ReconstructionResult.status no puede estar vacío")
        object.__setattr__(self, "status", status)

        components = dict(self.components)
        unknown = set(components) - set(_COMPONENT_NAMES)
        if unknown:
            raise CausalReconstructionError(
                f"Componentes reconstruidos no soportados: {sorted(unknown)!r}"
            )
        if status == "causal" and set(components) != set(_COMPONENT_NAMES):
            raise CausalReconstructionError(
                "Una reconstrucción causal debe exponer D1..D5 y A5"
            )
        for name, series in components.items():
            if not isinstance(series, pd.Series):
                raise TypeError(f"components[{name!r}] debe ser pandas.Series")
            if len(series) != self.metadata.prefix_length:
                raise CausalReconstructionError(
                    f"components[{name!r}] no concilia con prefix_length"
                )
            comparison = _index_for_comparison(series.index)
            if len(comparison) and (
                comparison[0] != self.metadata.prefix_first_date
                or comparison[-1] != self.metadata.prefix_last_date
            ):
                raise CausalReconstructionError(
                    f"components[{name!r}] no concilia con las fechas del prefijo"
                )
            if not np.isfinite(series.to_numpy(dtype=float)).all():
                raise CausalReconstructionError(
                    f"components[{name!r}] contiene valores no finitos"
                )
        object.__setattr__(self, "components", components)

        signals = dict(self.signals)
        for candidate_id, signal in signals.items():
            if not isinstance(signal, pd.Series):
                raise TypeError(f"signals[{candidate_id!r}] debe ser pandas.Series")
            if len(signal) != self.metadata.prefix_length:
                raise CausalReconstructionError(
                    f"signals[{candidate_id!r}] no concilia con prefix_length"
                )
            if not np.isfinite(signal.to_numpy(dtype=float)).all():
                raise CausalReconstructionError(
                    f"signals[{candidate_id!r}] contiene valores no finitos"
                )
        object.__setattr__(self, "signals", signals)

    @property
    def candidate_signals(self) -> Mapping[str, pd.Series]:
        """Alias de ``signals`` para el vocabulario del evaluador."""

        return self.signals

    @property
    def signal_series(self) -> Mapping[str, pd.Series]:
        """Alias de ``signals`` para serializadores de features."""

        return self.signals

    @property
    def signal_at_origin(self) -> Mapping[str, float]:
        """Última señal escalada de cada candidato en este origen."""

        return {
            candidate_id: float(signal.iloc[-1])
            for candidate_id, signal in self.signals.items()
        }

    def signal_for(
        self,
        candidate: CandidateSpecification | str,
        *,
        at_origin: bool = False,
    ) -> pd.Series | float:
        """Obtiene la señal completa o su último valor para un candidato."""

        candidate_id = (
            candidate.candidate_id if isinstance(candidate, CandidateSpecification) else str(candidate)
        )
        try:
            signal = self.signals[candidate_id]
        except KeyError as error:
            raise KeyError(f"No hay señal reconstruida para {candidate_id!r}") from error
        return float(signal.iloc[-1]) if at_origin else signal

    def signal_value(self, candidate: CandidateSpecification | str) -> float:
        """Devuelve el valor de la señal en el último mes del prefijo."""

        return float(self.signal_for(candidate, at_origin=True))

    def component_signal(
        self,
        components: tuple[str, ...] | list[str],
        *,
        signal_scale: float = SIGNAL_SCALE,
    ) -> pd.Series:
        """Suma componentes y aplica una escala, útil para adaptadores."""

        names = tuple(components)
        if not names:
            raise CausalReconstructionError("component_signal requiere al menos un componente")
        if any(name not in self.components for name in names):
            raise KeyError(f"Componente no reconstruido en {names!r}")
        try:
            scale = float(signal_scale)
        except (TypeError, ValueError) as error:
            raise CausalReconstructionError("signal_scale debe ser numérico") from error
        if not np.isfinite(scale):
            raise CausalReconstructionError("signal_scale debe ser finito")
        result = self.components[names[0]].copy(deep=True)
        for name in names[1:]:
            result = result + self.components[name]
        result = result * scale
        result.name = "signal"
        return result

    def as_dict(self) -> dict[str, object]:
        """Serializa el estado sin convertir las Series a datos históricos."""

        return {
            "status": self.status,
            "metadata": self.metadata.as_dict(),
            "candidate_ids": sorted(self.signals),
        }


class OriginReconstructor:
    """Calcula una DWT nueva sobre el prefijo PIT de un único origen.

    El cache es opcional y externo. Si se proporciona, la clave contiene el
    origen, el hash del manifest/vintage, el hash del prefijo y todos los
    parámetros DWT/candidato; por tanto nunca puede compartir componentes entre
    orígenes o snapshots distintos por accidente.
    """

    def __init__(
        self,
        *,
        cache: MutableMapping[tuple[object, ...], ReconstructionResult] | None = None,
        source_id: str = BANREP_TRM_SOURCE_ID,
    ) -> None:
        self.cache = cache
        self.source_id = str(source_id).strip()
        if self.source_id != BANREP_TRM_SOURCE_ID:
            raise ValueError(
                "OriginReconstructor solo admite source_id='banrep_trm_1'"
            )

    @staticmethod
    def _validate_plan(plan: ResearchPlan) -> tuple[CandidateSpecification, ...]:
        if not isinstance(plan, ResearchPlan):
            raise TypeError("reconstruct requiere un ResearchPlan")
        try:
            plan.validate()
        except Exception as error:
            raise CausalReconstructionError(
                f"ResearchPlan inválido para reconstrucción: {error}"
            ) from error
        candidates = tuple(plan.candidates)
        if not candidates:
            raise CausalReconstructionError("ResearchPlan no contiene candidatos")
        for candidate in candidates:
            if (
                candidate.wavelet_family != WAVELET_FAMILY
                or candidate.levels != DWT_LEVELS
                or candidate.boundary_mode != BOUNDARY_MODE
            ):
                raise CausalReconstructionError(
                    "Todos los candidatos deben usar db4, cinco niveles y symmetric"
                )
        if plan.target_series != TARGET_SERIES:
            raise CausalReconstructionError(
                f"target_series debe ser {TARGET_SERIES!r}; llegó {plan.target_series!r}"
            )
        return candidates

    @staticmethod
    def _validate_snapshot(
        origin: ForecastOrigin,
        snapshot: PointInTimeSnapshot,
        plan: ResearchPlan,
    ) -> SourceVintage:
        if not isinstance(origin, ForecastOrigin):
            raise TypeError("reconstruct requiere un ForecastOrigin")
        if not isinstance(snapshot, PointInTimeSnapshot):
            raise TypeError("reconstruct requiere un PointInTimeSnapshot")
        if not snapshot.valid:
            raise CausalReconstructionError(
                "El PointInTimeSnapshot no es válido para reconstrucción causal: "
                f"{snapshot.reason or snapshot.status or snapshot.mode}"
            )
        if snapshot.origin.origin_date != origin.origin_date:
            raise CausalReconstructionError(
                "El snapshot está ligado a un ForecastOrigin distinto"
            )
        if snapshot.origin.effective_cutoff != origin.effective_cutoff:
            raise CausalReconstructionError(
                "El corte efectivo del snapshot no concilia con el origen solicitado"
            )
        if origin.origin_date > _timestamp(plan.data_cutoff, "plan.data_cutoff"):
            raise CausalReconstructionError(
                "ForecastOrigin es posterior al Data_Cutoff del ResearchPlan"
            )
        try:
            vintage = snapshot.source(plan.target_series)
        except (KeyError, ValueError) as error:
            raise CausalReconstructionError(
                f"El snapshot no contiene un SourceVintage para {plan.target_series!r}"
            ) from error
        if vintage.source_id != plan.target_series:
            raise CausalReconstructionError(
                "SourceVintage.source_id no concilia con target_series"
            )
        limit = origin.effective_cutoff
        if vintage.available_through > limit:
            raise CausalReconstructionError(
                "SourceVintage.available_through es posterior al corte permitido"
            )
        if snapshot.snapshot_manifest and vintage.snapshot_manifest:
            if snapshot.snapshot_manifest != vintage.snapshot_manifest:
                raise CausalReconstructionError(
                    "SourceVintage pertenece a otro snapshot_manifest"
                )
        return vintage

    @staticmethod
    def _prefix(
        origin: ForecastOrigin,
        trm_monthly: pd.Series,
    ) -> pd.Series:
        if not isinstance(trm_monthly, pd.Series):
            raise TypeError("trm_monthly debe ser pandas.Series")
        if trm_monthly.empty:
            raise CausalReconstructionError("trm_monthly no contiene observaciones")
        comparison_index = _index_for_comparison(trm_monthly.index)
        limit = min(origin.origin_date, origin.effective_cutoff)
        # Se inspeccionan solamente valores del prefijo. Una cola posterior
        # puede existir en un fixture, pero nunca entra a la transformación ni
        # a las validaciones numéricas de la reconstrucción.
        mask = comparison_index <= limit
        if not bool(mask.any()):
            raise CausalReconstructionError(
                "trm_monthly no contiene observaciones dentro del corte del origen"
            )
        prefix = trm_monthly.iloc[np.flatnonzero(mask)].copy(deep=True)
        prefix.index = trm_monthly.index[mask]

        values = pd.to_numeric(prefix, errors="coerce")
        non_numeric = values.isna() & ~prefix.isna()
        if bool(non_numeric.any()):
            raise CausalReconstructionError(
                "El prefijo contiene valores TRM no numéricos"
            )
        # Los faltantes explícitos se eliminan, nunca se imputan. Si la
        # eliminación deja un prefijo demasiado corto, dwt_max_level lo
        # rechazará explícitamente más adelante.
        prefix = values.astype(float).dropna()
        if prefix.empty:
            raise CausalReconstructionError(
                "El prefijo no tiene observaciones TRM válidas después de eliminar faltantes"
            )
        finite = np.isfinite(prefix.to_numpy(dtype=float))
        if not bool(finite.all()):
            raise CausalReconstructionError(
                "El prefijo contiene TRM infinitas o no finitas"
            )
        if bool((prefix <= 0).any()):
            raise CausalReconstructionError(
                "El prefijo contiene TRM no positiva; no se puede calcular ln(TRM)"
            )
        prefix_dates = _index_for_comparison(prefix.index)
        if prefix_dates[-1] > limit:
            raise CausalReconstructionError(
                "El prefijo contiene una observación posterior al corte permitido"
            )
        return prefix

    @staticmethod
    def _validate_series_metadata(
        trm_monthly: pd.Series,
        *,
        origin: ForecastOrigin,
        vintage: SourceVintage,
    ) -> None:
        limit = origin.effective_cutoff
        attrs = trm_monthly.attrs
        for key in ("available_through", "origin_date", "data_cutoff", "cutoff", "through"):
            value = _attribute_date(attrs, key)
            if value is not None and value > limit:
                raise CausalReconstructionError(
                    f"trm_monthly.attrs[{key!r}] es posterior al corte permitido"
                )
        if vintage.available_through > limit:
            raise CausalReconstructionError(
                "metadata del vintage indica disponibilidad futura"
            )

    @staticmethod
    def _cache_key(
        origin: ForecastOrigin,
        snapshot: PointInTimeSnapshot,
        vintage: SourceVintage,
        prefix_sha256: str,
        candidates: tuple[CandidateSpecification, ...],
    ) -> tuple[object, ...]:
        return (
            "origin_date",
            origin.origin_date.isoformat(),
            "snapshot_manifest_sha256",
            snapshot.manifest_sha256,
            "snapshot_manifest",
            snapshot.snapshot_manifest or vintage.snapshot_manifest,
            "source_id",
            vintage.source_id,
            "source_vintage",
            vintage.vintage_id,
            "source_sha256",
            vintage.sha256,
            "prefix_sha256",
            prefix_sha256,
            "wavelet_family",
            WAVELET_FAMILY,
            "levels",
            DWT_LEVELS,
            "boundary_mode",
            BOUNDARY_MODE,
            "candidates",
            tuple(
                (
                    candidate.candidate_id,
                    tuple(candidate.components),
                    float(candidate.signal_scale),
                )
                for candidate in candidates
            ),
        )

    @staticmethod
    def _copy_result(result: ReconstructionResult) -> ReconstructionResult:
        return ReconstructionResult(
            components={name: _copy_series(series) for name, series in result.components.items()},
            metadata=result.metadata,
            status=result.status,
            signals={name: _copy_series(series) for name, series in result.signals.items()},
        )

    def reconstruct(
        self,
        origin: ForecastOrigin,
        snapshot: PointInTimeSnapshot,
        trm_monthly: pd.Series,
        plan: ResearchPlan,
    ) -> ReconstructionResult:
        """Reconstruye D1..D5/A5 exclusivamente sobre el prefijo PIT.

        ``trm_monthly`` se interpreta como TRM mensual positiva. La DWT se
        calcula sobre ``ln(TRM)`` y sus componentes se devuelven con el índice
        del prefijo válido. Las observaciones posteriores al origen pueden
        permanecer en la Series recibida para permitir fixtures compartidos,
        pero nunca se leen ni participan en el hash, nivel, DWT o señales.
        """

        candidates = self._validate_plan(plan)
        vintage = self._validate_snapshot(origin, snapshot, plan)
        self._validate_series_metadata(trm_monthly, origin=origin, vintage=vintage)
        prefix = self._prefix(origin, trm_monthly)
        prefix_dates = _index_for_comparison(prefix.index)
        prefix_sha256 = _sha256_prefix(prefix)

        key = self._cache_key(origin, snapshot, vintage, prefix_sha256, candidates)
        if self.cache is not None and key in self.cache:
            cached = self.cache[key]
            if not isinstance(cached, ReconstructionResult):
                raise CausalReconstructionError(
                    "El cache contiene un objeto que no es ReconstructionResult"
                )
            cached.metadata.validate_causal()
            return self._copy_result(cached)

        try:
            dwt_max_level = int(pywt.dwt_max_level(len(prefix), WAVELET_FAMILY))
        except (TypeError, ValueError, RuntimeError) as error:
            raise CausalReconstructionError(
                f"No se pudo calcular dwt_max_level para el prefijo: {error}"
            ) from error
        if dwt_max_level < DWT_LEVELS:
            raise CausalReconstructionError(
                f"Prefijo insuficiente para db4 nivel {DWT_LEVELS}: "
                f"dwt_max_level={dwt_max_level}, prefix_length={len(prefix)}"
            )

        log_values = np.log(prefix.to_numpy(dtype=float))
        if not np.isfinite(log_values).all():
            raise CausalReconstructionError(
                "ln(TRM) contiene valores no finitos después de validar TRM positiva"
            )

        try:
            coeffs = pywt.wavedec(
                log_values,
                WAVELET_FAMILY,
                mode=BOUNDARY_MODE,
                level=DWT_LEVELS,
            )
        except (TypeError, ValueError, RuntimeError) as error:
            raise CausalReconstructionError(
                f"No se pudo descomponer el prefijo causal: {error}"
            ) from error
        if len(coeffs) != DWT_LEVELS + 1:
            raise CausalReconstructionError(
                "wavedec no devolvió la aproximación y los cinco detalles esperados"
            )

        reconstructed: dict[str, pd.Series] = {}
        coefficient_positions = {
            f"D{level}": DWT_LEVELS - level + 1 for level in range(1, DWT_LEVELS + 1)
        }
        for name in _COMPONENT_NAMES:
            isolated = [np.zeros_like(coefficient, dtype=float) for coefficient in coeffs]
            position = 0 if name == "A5" else coefficient_positions[name]
            isolated[position] = np.asarray(coeffs[position], dtype=float)
            try:
                values = np.asarray(
                    pywt.waverec(
                        isolated,
                        WAVELET_FAMILY,
                        mode=BOUNDARY_MODE,
                    ),
                    dtype=float,
                )
            except (TypeError, ValueError, RuntimeError) as error:
                raise CausalReconstructionError(
                    f"No se pudo reconstruir el componente {name}: {error}"
                ) from error
            if values.size < len(prefix):
                raise CausalReconstructionError(
                    f"waverec devolvió menos observaciones para {name}: "
                    f"{values.size} < {len(prefix)}"
                )
            values = values[: len(prefix)]
            if not np.isfinite(values).all():
                raise CausalReconstructionError(
                    f"El componente {name} contiene valores no finitos"
                )
            reconstructed[name] = pd.Series(
                values,
                index=prefix.index,
                name=name,
            )

        source_vintage = vintage.vintage_id
        metadata = ReconstructionMetadata(
            origin_date=origin.origin_date,
            available_through=vintage.available_through,
            prefix_length=len(prefix),
            prefix_first_date=prefix_dates[0],
            prefix_last_date=prefix_dates[-1],
            prefix_sha256=prefix_sha256,
            wavelet_family=WAVELET_FAMILY,
            levels=DWT_LEVELS,
            boundary_mode=BOUNDARY_MODE,
            dwt_max_level=dwt_max_level,
            uses_future_observations=False,
            source_vintage=source_vintage,
        )
        metadata.validate_causal()

        signals: dict[str, pd.Series] = {}
        for candidate in candidates:
            signal = reconstructed[candidate.components[0]].copy(deep=True)
            for component_name in candidate.components[1:]:
                signal = signal + reconstructed[component_name]
            signal = signal * float(candidate.signal_scale)
            signal.name = candidate.candidate_id
            signals[candidate.candidate_id] = signal

        result = ReconstructionResult(
            components=reconstructed,
            metadata=metadata,
            status="causal",
            signals=signals,
        )
        if self.cache is not None:
            self.cache[key] = self._copy_result(result)
        return result

    # Method name used by a few adapters that mirror the protocol verb.
    reconstruct_origin = reconstruct


__all__ = [
    "CausalReconstructionError",
    "CausalReconstructionInvalid",
    "InvalidCausalReconstruction",
    "OriginReconstructor",
    "ReconstructionError",
    "ReconstructionMetadata",
    "ReconstructionResult",
    "hash_prefix",
]
