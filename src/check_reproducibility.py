from __future__ import annotations

import json
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# Cross-platform BLAS/linear-algebra differences affect derived statistics.
NUMERIC_RTOL = 2e-5


def git_output(*args: str) -> bytes:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT}", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def tracked_outputs() -> list[Path]:
    paths = git_output(
        "ls-files",
        "--",
        "data/modelo_trm_datos_mensuales.csv",
        "data/modelo_trm_muestra_estimacion.csv",
        "results/*.csv",
        "results/explicacion/*.csv",
        "results/pronostico/*.csv",
        "results/robustez/*.csv",
        "results/metadata.json",
        "deliverables/graficos/metadata.json",
    ).decode("utf-8").splitlines()
    return [ROOT / path for path in paths]


def _parse_serialized_numeric(value: Any) -> tuple[tuple[str, float], ...] | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    pairs: list[tuple[str, float]] = []
    for item in text.split(";"):
        token = item.strip()
        if not token:
            continue
        if "=" not in token:
            return None
        name, raw_value = token.rsplit("=", 1)
        try:
            pairs.append((name.strip(), float(raw_value)))
        except ValueError:
            return None
    return tuple(pairs)


def _compare_serialized_numeric_column(
    actual: pd.Series,
    expected: pd.Series,
    *,
    path: Path,
    column: str,
) -> None:
    if len(actual) != len(expected):
        raise AssertionError(f"Longitud distinta en {path.relative_to(ROOT)}: {column}.")
    for index, (actual_value, expected_value) in enumerate(zip(actual, expected)):
        actual_pairs = _parse_serialized_numeric(actual_value)
        expected_pairs = _parse_serialized_numeric(expected_value)
        if actual_pairs is None or expected_pairs is None:
            if actual_value != expected_value:
                raise AssertionError(
                    f"Valor distinto en {path.relative_to(ROOT)}[{index}].{column}: "
                    f"actual={actual_value!r}, esperado={expected_value!r}."
                )
            continue
        if tuple(name for name, _value in actual_pairs) != tuple(
            name for name, _value in expected_pairs
        ):
            raise AssertionError(
                f"Términos distintos en {path.relative_to(ROOT)}[{index}].{column}."
            )
        actual_numbers = np.asarray([value for _name, value in actual_pairs], dtype=float)
        expected_numbers = np.asarray([value for _name, value in expected_pairs], dtype=float)
        if not np.allclose(
            actual_numbers,
            expected_numbers,
            rtol=NUMERIC_RTOL,
            atol=1e-10,
            equal_nan=True,
        ):
            raise AssertionError(
                f"Valores numéricos distintos en {path.relative_to(ROOT)}[{index}].{column}."
            )


def compare_csv(path: Path, committed: bytes) -> None:
    expected = pd.read_csv(BytesIO(committed))
    actual = pd.read_csv(path)
    serialized_columns = [
        column
        for column in ("coeficientes_terminos", "p_valores_terminos")
        if column in actual.columns and column in expected.columns
    ]
    for column in serialized_columns:
        _compare_serialized_numeric_column(
            actual[column],
            expected[column],
            path=path,
            column=column,
        )
    actual_for_comparison = actual.drop(columns=serialized_columns)
    expected_for_comparison = expected.drop(columns=serialized_columns)
    try:
        pd.testing.assert_frame_equal(
            actual_for_comparison,
            expected_for_comparison,
            check_dtype=False,
            check_exact=False,
            rtol=NUMERIC_RTOL,
            atol=1e-10,
            check_like=False,
        )
    except AssertionError as error:
        raise AssertionError(f"Resultado no reproducible: {path.relative_to(ROOT)}\n{error}") from error


def compare_json(actual: Any, expected: Any, location: str = "metadata") -> None:
    if location == "metadata.sources":
        if not isinstance(actual, dict) or not isinstance(expected, dict) or set(actual) != set(expected):
            raise AssertionError(f"Claves distintas en {location}.")
        # Los hashes de fuentes son un índice derivado; check_charts.py los
        # recalcula contra los CSV generados después de validar cada gráfico.
        return
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise AssertionError(f"Claves distintas en {location}.")
        for key in expected:
            compare_json(actual[key], expected[key], f"{location}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError(f"Lista distinta en {location}.")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            compare_json(actual_item, expected_item, f"{location}[{index}]")
        return
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or not np.isclose(
            float(actual), float(expected), rtol=NUMERIC_RTOL, atol=1e-10
        ):
            raise AssertionError(
                f"Valor numérico distinto en {location}: actual={actual!r}, esperado={expected!r}."
            )
        return
    if actual != expected:
        raise AssertionError(
            f"Valor distinto en {location}: actual={actual!r}, esperado={expected!r}."
        )


def main() -> None:
    outputs = tracked_outputs()
    if not outputs:
        raise AssertionError("No se encontraron resultados versionados para comparar.")
    for path in outputs:
        relative = path.relative_to(ROOT).as_posix()
        committed = git_output("show", f"HEAD:{relative}")
        if path.suffix == ".csv":
            compare_csv(path, committed)
        elif path.suffix == ".json":
            compare_json(
                json.loads(path.read_text(encoding="utf-8")),
                json.loads(committed.decode("utf-8")),
            )
    print(f"OK: {len(outputs)} resultados reproducibles dentro de tolerancias numéricas.")


if __name__ == "__main__":
    main()
