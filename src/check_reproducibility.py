from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


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
        "results/metadata.json",
        "graficos/metadata.json",
    ).decode("utf-8").splitlines()
    return [ROOT / path for path in paths]


def compare_csv(path: Path, committed: bytes) -> None:
    expected = pd.read_csv(BytesIO(committed))
    actual = pd.read_csv(path)
    try:
        pd.testing.assert_frame_equal(
            actual,
            expected,
            check_dtype=False,
            check_exact=False,
            rtol=1e-8,
            atol=1e-10,
            check_like=False,
        )
    except AssertionError as error:
        raise AssertionError(f"Resultado no reproducible: {path.relative_to(ROOT)}\n{error}") from error


def compare_json(actual: Any, expected: Any, location: str = "metadata") -> None:
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
            float(actual), float(expected), rtol=1e-8, atol=1e-10
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
