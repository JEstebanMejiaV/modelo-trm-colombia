"""Cliente mínimo y seguro para descargas autenticadas de FRED."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

import pandas as pd


class FredConfigurationError(RuntimeError):
    """Indica que falta la credencial necesaria para usar la API de FRED."""


class FredDownloadError(RuntimeError):
    """Indica que FRED no respondió, sin propagar credenciales en el mensaje."""


def redact_fred_api_key(message: object, api_key: str | None = None) -> str:
    """Redacta una clave FRED aunque aparezca dentro de una URL de excepción."""
    text = str(message)
    candidates = [api_key, os.environ.get("FRED_API_KEY")]
    for secret in candidates:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return re.sub(
        r"([?&]api_key=)[^&\s'\"}]+",
        r"\1[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )


def require_fred_api_key(environ: dict[str, str] | None = None) -> str:
    """Obtiene ``FRED_API_KEY`` del ambiente y falla con un mensaje accionable."""
    source = environ if environ is not None else os.environ
    key = source.get("FRED_API_KEY", "").strip()
    if not key:
        raise FredConfigurationError(
            "Falta FRED_API_KEY. Defina la variable de entorno antes de descargar "
            "series de FRED; nunca coloque la clave en el código o en el repositorio."
        )
    return key


def download_fred_series(
    series_id: str,
    name: str,
    *,
    observation_start: str = "2000-01-01",
    timeout: int = 30,
    environ: dict[str, str] | None = None,
) -> pd.Series | None:
    """Descarga una serie FRED y la agrega a mensual sin imputar faltantes."""
    api_key = require_fred_api_key(environ)
    query = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&observation_start={observation_start}"
        f"&file_type=json&api_key={api_key}"
    )
    request = urllib.request.Request(query, headers={"User-Agent": "modelo-trm/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: dict[str, Any] = json.loads(response.read())
    except Exception as error:
        message = redact_fred_api_key(error, api_key)
        raise FredDownloadError(
            f"No fue posible descargar la serie FRED {series_id}: {message}"
        ) from None

    rows = [
        {"fecha": pd.Timestamp(obs["date"]), "valor": float(obs["value"])}
        for obs in payload.get("observations", [])
        if obs.get("value") not in (None, ".")
    ]
    if not rows:
        return None

    frame = pd.DataFrame(rows).set_index("fecha").sort_index()
    series = frame["valor"]
    if len(series) > 400:
        series = series.resample("MS").mean()
    else:
        series.index = series.index.to_period("M").to_timestamp()
        series = series.groupby(level=0).mean()
    series.name = name
    return series
