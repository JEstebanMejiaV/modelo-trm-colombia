"""Métricas descriptivas de utilidad para la investigación wavelet.

Esta capa es deliberadamente independiente de ``metrics.py`` y del
``PromotionGate``. No decide qué candidato promocionar: transforma una tabla
OOS ya construida en una lectura económica reproducible, con posición
``sign(prediction)``, turnover y un costo explícito. Los retornos de la
variante están en puntos porcentuales (``100 * log-return``); por eso un costo
expresado en basis points se convierte a ``bps / 100`` puntos porcentuales.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from typing import Any

import numpy as np
import pandas as pd

from .config import PHASE_FULL, PHASE_HOLDOUT, PHASE_SELECTION

ECONOMIC_EVALUATED = "evaluated"
ECONOMIC_INSUFFICIENT_OBSERVATIONS = "insufficient_observations"
ECONOMIC_NO_SCOREABLE_OBSERVATIONS = "no_scoreable_observations"
DEFAULT_MIN_OBSERVATIONS = 12
DEFAULT_TRANSACTION_COST_BPS = 0.0
POSITION_RULE = "sign_prediction"
RETURN_UNITS = "percentage_points"


class EconomicMetricsError(ValueError):
    """Entrada incompatible con las métricas económicas descriptivas."""


@dataclass(frozen=True)
class EconomicMetrics:
    """Utilidad neta descriptiva de un candidato, horizonte y fase."""

    candidate_id: str
    horizon_months: int
    split: str
    phase: str
    n_observations: int
    minimum_observations: int
    transaction_cost_bps: float
    gross_return: float | None
    total_cost: float | None
    net_return: float | None
    turnover: float | None
    max_drawdown: float | None
    volatility: float | None
    hit_rate: float | None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    status: str = ECONOMIC_INSUFFICIENT_OBSERVATIONS

    def __post_init__(self) -> None:
        candidate = str(self.candidate_id).strip()
        split = str(self.split).strip()
        phase = str(self.phase).strip().lower()
        if not candidate or not split:
            raise EconomicMetricsError("candidate_id y split no pueden estar vacíos")
        if phase not in {PHASE_FULL, PHASE_SELECTION, PHASE_HOLDOUT}:
            raise EconomicMetricsError(f"phase no soportada: {phase!r}")
        try:
            horizon = int(self.horizon_months)
            observations = int(self.n_observations)
            minimum = int(self.minimum_observations)
            cost_bps = float(self.transaction_cost_bps)
        except (TypeError, ValueError, OverflowError) as error:
            raise EconomicMetricsError("identidad y costos económicos inválidos") from error
        if horizon < 1 or observations < 0 or minimum < 1:
            raise EconomicMetricsError("horizonte/conteos económicos inválidos")
        if not np.isfinite(cost_bps) or cost_bps < 0:
            raise EconomicMetricsError("transaction_cost_bps debe ser finito no negativo")
        status = str(self.status).strip().lower()
        if not status:
            raise EconomicMetricsError("status no puede estar vacío")
        object.__setattr__(self, "candidate_id", candidate)
        object.__setattr__(self, "split", split)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "horizon_months", horizon)
        object.__setattr__(self, "n_observations", observations)
        object.__setattr__(self, "minimum_observations", minimum)
        object.__setattr__(self, "transaction_cost_bps", cost_bps)
        object.__setattr__(self, "status", status)
        for field in fields(self):
            name = field.name
            if name in {
                "candidate_id",
                "horizon_months",
                "split",
                "phase",
                "n_observations",
                "minimum_observations",
                "transaction_cost_bps",
                "status",
            }:
                continue
            value = getattr(self, name)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as error:
                raise EconomicMetricsError(f"{name} debe ser numérico o nulo") from error
            if not np.isfinite(number):
                raise EconomicMetricsError(f"{name} debe ser finito o nulo")
            if name == "hit_rate" and not 0.0 <= number <= 1.0:
                raise EconomicMetricsError("hit_rate debe estar en [0, 1]")
            object.__setattr__(self, name, number)

    @property
    def key(self) -> tuple[str, int, str, str]:
        return self.candidate_id, self.horizon_months, self.split, self.phase

    @property
    def is_evaluable(self) -> bool:
        return self.status == ECONOMIC_EVALUATED

    def as_dict(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}

    to_dict = as_dict
    to_record = as_dict


def _value(row: Any, *names: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        for name in names:
            if name in row:
                return row[name]
    else:
        for name in names:
            if hasattr(row, name):
                return getattr(row, name)
    return default


def _finite(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if np.isfinite(result) else None


def _phase(row: Any, split: str) -> str:
    value = _value(row, "phase", "evaluation_phase", default=None)
    if value is None or not str(value).strip():
        value = {
            "full": PHASE_FULL,
            "2008_2019": PHASE_SELECTION,
            "2020_2022": PHASE_SELECTION,
            "2023_2026": PHASE_HOLDOUT,
        }.get(split, PHASE_FULL)
    result = str(value).strip().lower()
    if result not in {PHASE_FULL, PHASE_SELECTION, PHASE_HOLDOUT}:
        raise EconomicMetricsError(f"phase no soportada: {value!r}")
    return result


def _rows(predictions: Any) -> tuple[Any, ...]:
    if predictions is None:
        return ()
    if isinstance(predictions, pd.DataFrame):
        return tuple(predictions.to_dict(orient="records"))
    value = getattr(predictions, "predictions", None)
    if value is not None and value is not predictions:
        return tuple(value)
    if isinstance(predictions, Mapping) and "predictions" in predictions:
        return tuple(predictions["predictions"])
    if isinstance(predictions, (str, bytes, bytearray)):
        raise EconomicMetricsError("predictions debe ser una tabla o iterable de filas")
    try:
        return tuple(predictions)
    except TypeError as error:
        raise EconomicMetricsError("predictions debe ser una tabla o iterable de filas") from error


def _candidate_ids(value: Iterable[Any] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (str(value),)
    result: list[str] = []
    for item in value:
        candidate = _value(item, "candidate_id", default=item)
        text = str(candidate).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)


def _phase_for_plan(plan: Any, split: str) -> str:
    method = getattr(plan, "phase_for_split", None)
    if callable(method):
        return str(method(split))
    return _phase({}, split)


def _economic_row(
    rows: tuple[Any, ...],
    *,
    candidate_id: str,
    horizon: int,
    split: str,
    phase: str,
    minimum_observations: int,
    transaction_cost_bps: float,
) -> EconomicMetrics:
    ordered = sorted(
        rows,
        key=lambda row: str(_value(row, "origin_date", "origin", default="")),
    )
    model: list[float] = []
    observed: list[float] = []
    for row in ordered:
        status = str(_value(row, "scoreability_status", "status", default="scoreable")).strip().lower()
        prediction = _finite(
            _value(row, "prediction_wavelet", "prediction_model", "model_prediction")
        )
        actual = _finite(
            _value(row, "observed_forward_return", "observed", "target", "actual")
        )
        coverage = str(_value(row, "coverage_status", default="complete")).strip().lower()
        if status != "scoreable" or coverage not in {"complete", ""}:
            continue
        if prediction is None or actual is None:
            continue
        model.append(prediction)
        observed.append(actual)

    n = len(model)
    if n < minimum_observations:
        return EconomicMetrics(
            candidate_id=candidate_id,
            horizon_months=horizon,
            split=split,
            phase=phase,
            n_observations=n,
            minimum_observations=minimum_observations,
            transaction_cost_bps=transaction_cost_bps,
            gross_return=None,
            total_cost=None,
            net_return=None,
            turnover=None,
            max_drawdown=None,
            volatility=None,
            hit_rate=None,
            status=(
                ECONOMIC_NO_SCOREABLE_OBSERVATIONS
                if n == 0
                else ECONOMIC_INSUFFICIENT_OBSERVATIONS
            ),
        )

    predictions_array = np.asarray(model, dtype=float)
    observed_array = np.asarray(observed, dtype=float)
    positions = np.sign(predictions_array)
    turnover_values = np.abs(np.diff(np.concatenate(([0.0], positions))))
    cost_per_turnover = float(transaction_cost_bps) / 100.0
    gross_values = positions * observed_array
    cost_values = turnover_values * cost_per_turnover
    net_values = gross_values - cost_values
    wealth = np.cumprod(1.0 + net_values / 100.0)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], wealth)))[1:]
    drawdowns = (1.0 - wealth / peaks) * 100.0
    volatility = float(np.std(net_values, ddof=1)) if n > 1 else None
    annualized_volatility = None if volatility is None else volatility * np.sqrt(12.0)
    mean_net = float(np.mean(net_values))
    sharpe = None
    if volatility is not None and volatility > 0:
        sharpe = mean_net / volatility * np.sqrt(12.0)
    downside = net_values[net_values < 0]
    sortino = None
    if downside.size:
        downside_deviation = float(np.sqrt(np.mean(np.square(downside))))
        if downside_deviation > 0:
            sortino = mean_net / downside_deviation * np.sqrt(12.0)
    return EconomicMetrics(
        candidate_id=candidate_id,
        horizon_months=horizon,
        split=split,
        phase=phase,
        n_observations=n,
        minimum_observations=minimum_observations,
        transaction_cost_bps=transaction_cost_bps,
        gross_return=float(np.sum(gross_values)),
        total_cost=float(np.sum(cost_values)),
        net_return=float(np.sum(net_values)),
        turnover=float(np.sum(turnover_values)),
        max_drawdown=float(np.max(drawdowns)) if len(drawdowns) else 0.0,
        volatility=annualized_volatility,
        hit_rate=float(np.mean(np.sign(predictions_array) == np.sign(observed_array))),
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        status=ECONOMIC_EVALUATED,
    )


def calculate_economic_metrics(
    predictions: Any,
    *,
    plan: Any | None = None,
    candidate_ids: Iterable[Any] | None = None,
    horizons: Iterable[int] | None = None,
    splits: Iterable[str] | None = None,
    phases: Iterable[str] | None = None,
    minimum_observations: int = DEFAULT_MIN_OBSERVATIONS,
    transaction_cost_bps: float = DEFAULT_TRANSACTION_COST_BPS,
) -> tuple[EconomicMetrics, ...]:
    """Calcula utilidad por grupo sin participar en el ranking ni en el gate."""

    if isinstance(minimum_observations, bool) or int(minimum_observations) != minimum_observations:
        raise EconomicMetricsError("minimum_observations debe ser entero")
    minimum = int(minimum_observations)
    if minimum < 1:
        raise EconomicMetricsError("minimum_observations debe ser positivo")
    try:
        cost_bps = float(transaction_cost_bps)
    except (TypeError, ValueError, OverflowError) as error:
        raise EconomicMetricsError("transaction_cost_bps debe ser numérico") from error
    if not np.isfinite(cost_bps) or cost_bps < 0:
        raise EconomicMetricsError("transaction_cost_bps debe ser finito no negativo")

    rows = _rows(predictions)
    candidates = _candidate_ids(candidate_ids)
    if not candidates:
        candidates = tuple(
            sorted(
                {
                    str(_value(row, "candidate_id", "candidate", default="")).strip()
                    for row in rows
                    if str(_value(row, "candidate_id", "candidate", default="")).strip()
                }
            )
        )
    else:
        candidates = tuple(dict.fromkeys(candidates))
    horizon_values = (
        tuple(dict.fromkeys(int(value) for value in horizons))
        if horizons is not None
        else tuple(sorted({int(_value(row, "horizon_months", "horizon")) for row in rows}))
    )
    split_values = (
        tuple(dict.fromkeys(str(value) for value in splits))
        if splits is not None
        else tuple(sorted({str(_value(row, "split", default="full")) for row in rows}))
    )
    phase_values = None if phases is None else tuple(dict.fromkeys(str(value).lower() for value in phases))

    grouped: dict[tuple[str, int, str, str], list[Any]] = {}
    for row in rows:
        candidate = str(_value(row, "candidate_id", "candidate", default="")).strip()
        if candidate not in candidates:
            continue
        try:
            horizon = int(_value(row, "horizon_months", "horizon"))
        except (TypeError, ValueError, OverflowError):
            continue
        split = str(_value(row, "split", default="full")).strip()
        phase = _phase(row, split)
        if phase_values is not None and phase not in phase_values:
            continue
        grouped.setdefault((candidate, horizon, split, phase), []).append(row)

    result: list[EconomicMetrics] = []
    for candidate in sorted(candidates):
        for horizon in sorted(horizon_values):
            for split in sorted(split_values):
                phase = _phase_for_plan(plan, split)
                if phase_values is not None and phase not in phase_values:
                    continue
                result.append(
                    _economic_row(
                        tuple(grouped.get((candidate, horizon, split, phase), ())),
                        candidate_id=candidate,
                        horizon=horizon,
                        split=split,
                        phase=phase,
                        minimum_observations=minimum,
                        transaction_cost_bps=cost_bps,
                    )
                )
    return tuple(result)


calculate_utility_metrics = calculate_economic_metrics
utility_metrics = calculate_economic_metrics


def economic_metrics_frame(metrics: Iterable[EconomicMetrics]) -> pd.DataFrame:
    rows = [item.as_dict() if isinstance(item, EconomicMetrics) else dict(item) for item in metrics]
    return pd.DataFrame(rows, columns=[field.name for field in fields(EconomicMetrics)])


__all__ = [
    "DEFAULT_MIN_OBSERVATIONS",
    "DEFAULT_TRANSACTION_COST_BPS",
    "ECONOMIC_EVALUATED",
    "ECONOMIC_INSUFFICIENT_OBSERVATIONS",
    "ECONOMIC_NO_SCOREABLE_OBSERVATIONS",
    "EconomicMetrics",
    "EconomicMetricsError",
    "POSITION_RULE",
    "RETURN_UNITS",
    "calculate_economic_metrics",
    "calculate_utility_metrics",
    "economic_metrics_frame",
    "utility_metrics",
]
