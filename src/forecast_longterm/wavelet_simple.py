"""Variante wavelet simple para exploración de la TRM actual.

Esta variante es deliberadamente independiente de ``wavelet_optimization``.
Usa una descarga actual explícita de BanRep, calcula una señal causal
``D3 + D4 + D5`` y ajusta un OLS expanding a seis meses. No es un backtest
point-in-time: rechaza ``data/raw`` y declara ``pit_eligible=false`` en su
provenance, pero no exige snapshots porque su propósito es exploratorio.

Ejemplo desde la raíz del repositorio::

    python -m forecast_longterm.wavelet_simple \
        --root . \
        --input data/vintages/historical/banrep_trm_1_current_2026-08-25.json

Los resultados se escriben en un run nuevo bajo
``results/exploration/wavelet_simple_v1/<run_id>/`` y nunca sustituyen los
outputs de ``results/pronostico/wavelet_optimization``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pywt

DEFAULT_CONFIG = "research/configs/long_horizon_wavelet_simple.toml"
DEFAULT_OUTPUT_DIR = "results/exploration/wavelet_simple_v1"
SOURCE_URL = (
    "https://suameca.banrep.gov.co/graficador-series/rest/graficadorService/"
    "consultaSerieParaGraficar?idSerie=1"
)
SOURCE_ID = "banrep_trm_1"
VARIANT_ID = "wavelet_simple_v1"
CANDIDATE_ID = "db4_l5_sym_D3_D4_D5"
WAVELET = "db4"
LEVELS = 5
BOUNDARY_MODE = "symmetric"
COMPONENTS = ("D3", "D4", "D5")
SIGNAL_SCALE = 100.0
HORIZON_MONTHS = 6
MINIMUM_MATURE_TRAINING = 60
MINIMUM_TRAINING_START = "2006-01-01"
BENCHMARK_RETURN = 0.0
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


class SimpleWaveletError(RuntimeError):
    """Error de validación o ejecución de la variante exploratoria."""


@dataclass(frozen=True)
class SimpleWaveletConfig:
    """Configuración congelada de una corrida simple."""

    variant_id: str = VARIANT_ID
    source_id: str = SOURCE_ID
    horizon_months: int = HORIZON_MONTHS
    minimum_mature_training: int = MINIMUM_MATURE_TRAINING
    minimum_training_start: str = MINIMUM_TRAINING_START
    wavelet: str = WAVELET
    levels: int = LEVELS
    boundary_mode: str = BOUNDARY_MODE
    signal_scale: float = SIGNAL_SCALE
    candidate_id: str = CANDIDATE_ID
    components: tuple[str, ...] = COMPONENTS
    benchmark_id: str = "random_walk"
    benchmark_return: float = BENCHMARK_RETURN
    input_must_be_explicit: bool = True
    reject_data_raw: bool = True
    pit_eligible: bool = False
    not_for_promotion: bool = True
    no_imputation: bool = True

    @classmethod
    def from_toml(cls, path: Path) -> "SimpleWaveletConfig":
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
            raise SimpleWaveletError(f"No se pudo leer la configuración {path}: {error}") from error

        dwt = document.get("dwt", {})
        candidate = document.get("candidate", {})
        benchmark = document.get("benchmark", {})
        policy = document.get("policy", {})
        config = cls(
            variant_id=str(document.get("variant_id", VARIANT_ID)),
            source_id=str(document.get("source_id", SOURCE_ID)),
            horizon_months=int(document.get("horizon_months", HORIZON_MONTHS)),
            minimum_mature_training=int(
                document.get("minimum_mature_training", MINIMUM_MATURE_TRAINING)
            ),
            minimum_training_start=str(
                document.get("minimum_training_start", MINIMUM_TRAINING_START)
            ),
            wavelet=str(dwt.get("wavelet", WAVELET)),
            levels=int(dwt.get("levels", LEVELS)),
            boundary_mode=str(dwt.get("boundary_mode", BOUNDARY_MODE)),
            signal_scale=float(dwt.get("signal_scale", SIGNAL_SCALE)),
            candidate_id=str(candidate.get("id", CANDIDATE_ID)),
            components=tuple(str(item) for item in candidate.get("components", COMPONENTS)),
            benchmark_id=str(benchmark.get("id", "random_walk")),
            benchmark_return=float(benchmark.get("return_prediction", BENCHMARK_RETURN)),
            input_must_be_explicit=bool(policy.get("input_must_be_explicit", True)),
            reject_data_raw=bool(policy.get("reject_data_raw", True)),
            pit_eligible=bool(policy.get("pit_eligible", False)),
            not_for_promotion=bool(policy.get("not_for_promotion", True)),
            no_imputation=bool(policy.get("no_imputation", True)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.variant_id != VARIANT_ID:
            raise SimpleWaveletError(f"variant_id no soportado: {self.variant_id!r}")
        if self.source_id != SOURCE_ID:
            raise SimpleWaveletError(f"source_id no soportado: {self.source_id!r}")
        if self.horizon_months != HORIZON_MONTHS:
            raise SimpleWaveletError("wavelet_simple_v1 requiere horizonte de 6 meses")
        if self.minimum_mature_training < 2:
            raise SimpleWaveletError("minimum_mature_training debe ser al menos 2")
        try:
            start = pd.Timestamp(self.minimum_training_start)
        except (TypeError, ValueError) as error:
            raise SimpleWaveletError("minimum_training_start no es una fecha válida") from error
        if start.day != 1:
            raise SimpleWaveletError("minimum_training_start debe ser el primer día del mes")
        if self.wavelet != WAVELET or self.levels != LEVELS:
            raise SimpleWaveletError("wavelet_simple_v1 requiere db4 con cinco niveles")
        if self.boundary_mode != BOUNDARY_MODE:
            raise SimpleWaveletError("wavelet_simple_v1 requiere boundary_mode='symmetric'")
        if tuple(self.components) != COMPONENTS:
            raise SimpleWaveletError("wavelet_simple_v1 requiere exactamente D3+D4+D5")
        if self.candidate_id != CANDIDATE_ID:
            raise SimpleWaveletError(f"candidate_id no soportado: {self.candidate_id!r}")
        if not np.isfinite(self.signal_scale) or self.signal_scale <= 0:
            raise SimpleWaveletError("signal_scale debe ser positivo y finito")
        if self.benchmark_id != "random_walk" or self.benchmark_return != BENCHMARK_RETURN:
            raise SimpleWaveletError("El benchmark simple debe ser random_walk con retorno cero")
        if self.input_must_be_explicit is not True:
            raise SimpleWaveletError("La entrada debe ser explícita")
        if self.reject_data_raw is not True or self.pit_eligible is not False:
            raise SimpleWaveletError("La variante simple no puede aceptar raw ni declararse PIT")
        if self.not_for_promotion is not True or self.no_imputation is not True:
            raise SimpleWaveletError("La variante simple es exploratoria y no imputa")

    def as_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "source_id": self.source_id,
            "horizon_months": self.horizon_months,
            "minimum_mature_training": self.minimum_mature_training,
            "minimum_training_start": self.minimum_training_start,
            "dwt": {
                "wavelet": self.wavelet,
                "levels": self.levels,
                "boundary_mode": self.boundary_mode,
                "signal_scale": self.signal_scale,
            },
            "candidate": {
                "id": self.candidate_id,
                "components": list(self.components),
                "estimator": "ols_intercept_signal",
                "estimation_window": "expanding",
            },
            "benchmark": {
                "id": self.benchmark_id,
                "return_prediction": self.benchmark_return,
            },
            "policy": {
                "input_must_be_explicit": self.input_must_be_explicit,
                "reject_data_raw": self.reject_data_raw,
                "pit_eligible": self.pit_eligible,
                "not_for_promotion": self.not_for_promotion,
                "no_imputation": self.no_imputation,
            },
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _root_path(root: Path | None) -> Path:
    return (root or Path.cwd()).resolve()


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _date_text(value: pd.Timestamp | pd.Period) -> str:
    timestamp = value.start_time if isinstance(value, pd.Period) else pd.Timestamp(value)
    return timestamp.date().isoformat()


def _period(value: Any, name: str) -> pd.Period:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise SimpleWaveletError(f"{name} no es una fecha válida: {value!r}") from error
    return timestamp.to_period("M")


def _reject_unsafe_input(root: Path, path: Path) -> None:
    try:
        relative_parts = path.resolve().relative_to(root.resolve()).parts
    except ValueError as error:
        raise SimpleWaveletError(
            "La entrada debe estar dentro de la raíz del proyecto"
        ) from error
    if len(relative_parts) >= 2 and relative_parts[0:2] == ("data", "raw"):
        raise SimpleWaveletError(
            "La variante exploratoria no acepta data/raw; use el artefacto actual explícito"
        )
    if relative_parts[:2] == ("results", "pronostico"):
        raise SimpleWaveletError(
            "La variante exploratoria no puede leer outputs históricos de pronóstico"
        )


def load_banrep_monthly(path: Path) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
    """Carga la respuesta JSON de BanRep y mensualiza sin imputar."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SimpleWaveletError(f"No se pudo leer el JSON BanRep {path}: {error}") from error
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SimpleWaveletError("La respuesta BanRep debe contener exactamente una serie JSON")
    series = payload[0]
    if series.get("id") != 1:
        raise SimpleWaveletError(f"Se esperaba la serie BanRep id=1; llegó {series.get('id')!r}")
    points = series.get("data")
    if not isinstance(points, list) or not points:
        raise SimpleWaveletError("La serie BanRep no contiene data")

    dates: list[pd.Timestamp] = []
    values: list[float] = []
    for position, point in enumerate(points):
        if not isinstance(point, list) or len(point) != 2:
            raise SimpleWaveletError(f"Punto BanRep inválido en posición {position}")
        try:
            timestamp = float(point[0])
            value = float(point[1])
        except (TypeError, ValueError) as error:
            raise SimpleWaveletError(f"Punto BanRep no numérico en posición {position}") from error
        if not np.isfinite(timestamp) or not np.isfinite(value) or value <= 0:
            raise SimpleWaveletError(f"Punto BanRep no válido en posición {position}")
        date = pd.Timestamp(timestamp, unit="ms", tz="UTC").tz_localize(None).normalize()
        dates.append(date)
        values.append(value)

    daily = pd.Series(values, index=pd.DatetimeIndex(dates), name=SOURCE_ID).sort_index()
    if not daily.index.is_unique:
        raise SimpleWaveletError("La serie BanRep contiene fechas diarias duplicadas")
    if not daily.index.is_monotonic_increasing:
        raise SimpleWaveletError("La serie BanRep no está ordenada temporalmente")
    monthly_index = daily.index.to_period("M").to_timestamp()
    monthly = daily.groupby(monthly_index).mean().sort_index()
    monthly.name = SOURCE_ID
    if monthly.empty or not np.isfinite(monthly.to_numpy()).all():
        raise SimpleWaveletError("La serie mensual resultante no es válida")
    if (monthly <= 0).any():
        raise SimpleWaveletError("La serie mensual contiene valores no positivos")

    expected = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    missing = expected.difference(monthly.index)
    if not missing.empty:
        raise SimpleWaveletError(
            "Hay meses sin observaciones; la variante no imputa: "
            + ", ".join(item.date().isoformat() for item in missing[:5])
        )
    metadata = {
        "series_id": series["id"],
        "series_name": series.get("nombre"),
        "unit": series.get("unidad"),
        "metadata_start": series.get("fechaInicialFormateada"),
        "metadata_end": series.get("fechaFinalFormateada"),
        "metadata_last_load": series.get("fechaUltimoCargueFormateada"),
        "daily_observations": int(len(daily)),
        "monthly_observations": int(len(monthly)),
        "data_start": _date_text(daily.index.min()),
        "data_end": _date_text(daily.index.max()),
        "monthly_start": _date_text(monthly.index.min()),
        "monthly_end": _date_text(monthly.index.max()),
    }
    return daily, monthly, metadata


def _wavelet_signal(prefix: pd.Series, config: SimpleWaveletConfig) -> float:
    values = pd.to_numeric(prefix, errors="coerce").to_numpy(dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or (values <= 0).any():
        raise SimpleWaveletError("El prefijo TRM no es positivo y finito")
    maximum_level = int(pywt.dwt_max_level(values.size, config.wavelet))
    if maximum_level < config.levels:
        raise SimpleWaveletError(
            f"Prefijo insuficiente para {config.wavelet} nivel {config.levels}: "
            f"dwt_max_level={maximum_level}, n={values.size}"
        )
    try:
        coefficients = pywt.wavedec(
            np.log(values),
            config.wavelet,
            mode=config.boundary_mode,
            level=config.levels,
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise SimpleWaveletError(f"No se pudo calcular la DWT causal: {error}") from error

    positions = {f"D{level}": config.levels - level + 1 for level in range(1, config.levels + 1)}
    combined = np.zeros(values.size, dtype=float)
    for component in config.components:
        isolated = [np.zeros_like(coefficient, dtype=float) for coefficient in coefficients]
        isolated[positions[component]] = np.asarray(coefficients[positions[component]], dtype=float)
        try:
            reconstructed = np.asarray(
                pywt.waverec(isolated, config.wavelet, mode=config.boundary_mode),
                dtype=float,
            )[: values.size]
        except (TypeError, ValueError, RuntimeError) as error:
            raise SimpleWaveletError(
                f"No se pudo reconstruir el componente {component}: {error}"
            ) from error
        if reconstructed.size != values.size or not np.isfinite(reconstructed).all():
            raise SimpleWaveletError(f"Reconstrucción inválida para {component}")
        combined += reconstructed
    signal = float(config.signal_scale * combined[-1])
    if not np.isfinite(signal):
        raise SimpleWaveletError("La señal wavelet no es finita")
    return signal


def _fit_ols(signal: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    if signal.size != target.size or signal.size < 2:
        raise SimpleWaveletError("OLS requiere al menos dos señales y targets alineados")
    design = np.column_stack((np.ones(signal.size, dtype=float), signal))
    try:
        coefficients, _residuals, rank, _singular = np.linalg.lstsq(
            design, target, rcond=None
        )
    except (np.linalg.LinAlgError, ValueError, TypeError) as error:
        raise SimpleWaveletError(f"Fallo numérico en OLS: {error}") from error
    if int(rank) < 2 or not np.isfinite(coefficients).all():
        raise SimpleWaveletError("La matriz OLS no tiene rango completo")
    return float(coefficients[0]), float(coefficients[1])


def _forward_return(monthly_by_period: Mapping[pd.Period, float], origin: pd.Period, horizon: int) -> float | None:
    target_period = origin + horizon
    if target_period not in monthly_by_period:
        return None
    current = float(monthly_by_period[origin])
    future = float(monthly_by_period[target_period])
    return float(100.0 * (np.log(future) - np.log(current)))


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _build_predictions(
    monthly: pd.Series,
    origin_period: pd.Period,
    config: SimpleWaveletConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    monthly_by_period = {
        timestamp.to_period("M"): float(value)
        for timestamp, value in monthly.items()
    }
    start_period = max(_period(config.minimum_training_start, "minimum_training_start"), monthly.index[0].to_period("M"))
    if origin_period < start_period:
        raise SimpleWaveletError("origin_date es anterior al inicio de entrenamiento")
    if origin_period > monthly.index[-1].to_period("M"):
        raise SimpleWaveletError("origin_date es posterior a la serie disponible")

    requested_periods = pd.period_range(start_period, origin_period, freq="M")
    periods: list[pd.Period] = []
    for period in requested_periods:
        prefix_index = monthly.index[monthly.index.to_period("M") <= period]
        prefix = monthly.loc[prefix_index]
        maximum_level = int(pywt.dwt_max_level(len(prefix), config.wavelet))
        if maximum_level >= config.levels:
            periods.append(period)
    if not periods:
        raise SimpleWaveletError(
            "No hay ningún origen con prefijo suficiente para la DWT configurada"
        )

    signals: dict[pd.Period, float] = {}
    for period in periods:
        prefix_index = monthly.index[monthly.index.to_period("M") <= period]
        prefix = monthly.loc[prefix_index]
        signals[period] = _wavelet_signal(prefix, config)

    rows: list[dict[str, Any]] = []
    for period in periods:
        target_period = period + config.horizon_months
        observed = _forward_return(monthly_by_period, period, config.horizon_months)
        mature = [
            item
            for item in rows
            if item["_target_period"] < period
            and item["observed_forward_return"] is not None
        ]
        n_mature = len(mature)
        prediction: float | None = None
        intercept: float | None = None
        slope: float | None = None
        status = "insufficient_mature_training"
        if n_mature >= config.minimum_mature_training:
            train_signal = np.asarray([item["signal"] for item in mature], dtype=float)
            train_target = np.asarray(
                [item["observed_forward_return"] for item in mature], dtype=float
            )
            intercept, slope = _fit_ols(train_signal, train_target)
            prediction = float(intercept + slope * signals[period])
            status = "scoreable" if observed is not None else "forecast_only"

        rows.append(
            {
                "origin_date": _date_text(period),
                "horizon_months": config.horizon_months,
                "source_id": config.source_id,
                "candidate_id": config.candidate_id,
                "signal": signals[period],
                "prediction_wavelet": prediction,
                "prediction_random_walk": config.benchmark_return if prediction is not None else None,
                "observed_forward_return": observed,
                "target_end_date": _date_text(target_period),
                "n_mature_labels": n_mature,
                "fit_intercept": intercept,
                "fit_slope": slope,
                "scoreability_status": status,
                "_target_period": target_period,
            }
        )

    public_rows = [_public_row(row) for row in rows]
    scoreable = [
        row
        for row in public_rows
        if row["scoreability_status"] == "scoreable"
        and row["prediction_wavelet"] is not None
        and row["observed_forward_return"] is not None
    ]
    if scoreable:
        actual = np.asarray([row["observed_forward_return"] for row in scoreable], dtype=float)
        prediction = np.asarray([row["prediction_wavelet"] for row in scoreable], dtype=float)
        benchmark = np.asarray(
            [row["prediction_random_walk"] for row in scoreable], dtype=float
        )
        model_error = actual - prediction
        benchmark_error = actual - benchmark
        denominator = float(np.sum(benchmark_error**2))
        metrics = {
            "status": "computed_exploratory",
            "n_oos": int(len(scoreable)),
            "mae": float(np.mean(np.abs(model_error))),
            "rmse": float(np.sqrt(np.mean(model_error**2))),
            "benchmark_mae": float(np.mean(np.abs(benchmark_error))),
            "benchmark_rmse": float(np.sqrt(np.mean(benchmark_error**2))),
            "r2_oos": float(1.0 - np.sum(model_error**2) / denominator)
            if denominator > 0
            else None,
            "direction_accuracy": float(
                np.mean(np.sign(prediction) == np.sign(actual))
            ),
        }
    else:
        metrics = {
            "status": "insufficient_oos_observations",
            "n_oos": 0,
            "mae": None,
            "rmse": None,
            "benchmark_mae": None,
            "benchmark_rmse": None,
            "r2_oos": None,
            "direction_accuracy": None,
        }
    latest = next(row for row in public_rows if row["origin_date"] == _date_text(origin_period))
    metrics.update(
        {
            "variant_id": config.variant_id,
            "candidate_id": config.candidate_id,
            "horizon_months": config.horizon_months,
            "requested_training_start": _date_text(start_period),
            "effective_signal_start": public_rows[0]["origin_date"],
            "excluded_wavelet_warmup_origins": int(len(requested_periods) - len(periods)),
            "evaluation_origin_start": public_rows[0]["origin_date"],
            "forecast_origin": latest["origin_date"],
            "latest_forecast": latest,
        }
    )
    return public_rows, metrics


def _output_records(root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": _relative(root, path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in paths
    ]


def run_simple_wavelet(
    *,
    root: Path | None = None,
    input_path: str | Path,
    config_path: str | Path | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    origin_date: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Ejecuta la variante exploratoria y devuelve su resumen serializable."""

    project_root = _root_path(root)
    resolved_input = _resolve(project_root, input_path)
    if not resolved_input.is_file():
        raise SimpleWaveletError(f"No existe la entrada BanRep: {resolved_input}")
    _reject_unsafe_input(project_root, resolved_input)
    resolved_config = _resolve(project_root, config_path or DEFAULT_CONFIG)
    config = SimpleWaveletConfig.from_toml(resolved_config)
    daily, monthly, source_metadata = load_banrep_monthly(resolved_input)

    latest_period = monthly.index[-1].to_period("M")
    default_origin_period = latest_period - 1
    selected_origin = _period(origin_date, "origin_date") if origin_date else default_origin_period
    rows, metrics = _build_predictions(monthly, selected_origin, config)

    effective_run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not _RUN_ID_PATTERN.fullmatch(effective_run_id):
        raise SimpleWaveletError("run_id contiene caracteres no permitidos")
    base_output = _resolve(project_root, output_dir)
    run_directory = base_output / effective_run_id
    if run_directory.exists():
        raise SimpleWaveletError(f"No se sobrescribe el run exploratorio existente: {run_directory}")

    run_directory.mkdir(parents=True, exist_ok=False)
    predictions_path = run_directory / "predicciones.csv"
    metrics_path = run_directory / "metricas.json"
    provenance_path = run_directory / "provenance.json"
    pd.DataFrame(rows).to_csv(predictions_path, index=False, encoding="utf-8-sig")
    metrics_document = {
        **metrics,
        "mode": "exploratory_current_series",
        "pit_eligible": False,
        "not_for_promotion": True,
    }
    metrics_path.write_text(
        json.dumps(metrics_document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    provenance = {
        "run_id": effective_run_id,
        "variant_id": config.variant_id,
        "status": "exploratory_current_series",
        "pit_eligible": False,
        "not_for_promotion": True,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "input_path": _relative(project_root, resolved_input),
        "input_bytes": resolved_input.stat().st_size,
        "input_sha256": _sha256(resolved_input),
        "input_metadata": source_metadata,
        "input_mode": "current_download",
        "forecast_origin": _date_text(selected_origin),
        "data_cutoff": source_metadata["data_end"],
        "config_path": _relative(project_root, resolved_config),
        "config": config.as_dict(),
        "causal_prefix_per_origin": True,
        "no_imputation": True,
        "uses_current_revised_series": True,
        "warning": (
            "No es un backtest PIT. Las señales y outcomes históricos se calculan "
            "con la descarga vigente de BanRep; no demuestra información disponible "
            "en tiempo real ni autoriza promoción al forecast mensual."
        ),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "outputs": _output_records(project_root, [predictions_path, metrics_path]),
    }
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "run_id": effective_run_id,
        "run_directory": _relative(project_root, run_directory),
        "predictions": _relative(project_root, predictions_path),
        "metrics": _relative(project_root, metrics_path),
        "provenance": _relative(project_root, provenance_path),
        "forecast_origin": _date_text(selected_origin),
        "latest_forecast": metrics["latest_forecast"],
        "n_oos": metrics["n_oos"],
        "r2_oos": metrics["r2_oos"],
        "pit_eligible": False,
        "not_for_promotion": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wavelet-simple",
        description=(
            "Ejecuta wavelet_simple_v1 sobre una descarga actual explícita de BanRep; "
            "no es un backtest PIT."
        ),
    )
    parser.add_argument("--root", type=Path, default=None, help="Raíz del repositorio")
    parser.add_argument(
        "--input",
        dest="input_path",
        required=True,
        type=Path,
        help="JSON actual explícito de BanRep; data/raw se rechaza",
    )
    parser.add_argument("--config", dest="config_path", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help="Directorio base de runs exploratorios",
    )
    parser.add_argument(
        "--origin-date",
        default=None,
        help="Origen mensual ISO; por defecto, el último mes cerrado antes del último dato",
    )
    parser.add_argument("--run-id", default=None, help="Identificador único del run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_simple_wavelet(
        root=args.root,
        input_path=args.input_path,
        config_path=args.config_path,
        output_dir=args.output_dir,
        origin_date=args.origin_date,
        run_id=args.run_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by CLI smoke
    raise SystemExit(main())


__all__ = [
    "CANDIDATE_ID",
    "SimpleWaveletConfig",
    "SimpleWaveletError",
    "load_banrep_monthly",
    "main",
    "run_simple_wavelet",
]
