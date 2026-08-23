from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "deliverables" / "graficos"
METADATA = CHARTS / "metadata.json"


def text_sha256(path: Path) -> str:
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def csv_semantic_sha256(path: Path) -> str:
    data = pd.read_csv(path)
    canonical = data.to_csv(
        index=False,
        lineterminator="\n",
        # Debe coincidir con build_charts.py: precisión superior a la visible,
        # pero estable ante ruido numérico irrelevante entre plataformas.
        float_format="%.6g",
        na_rep="",
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> None:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if metadata.get("version") != 2:
        raise AssertionError("Versión desconocida de metadata de gráficos.")

    generator = metadata["generator"]
    generator_path = ROOT / generator["path"]
    if text_sha256(generator_path) != generator["sha256"]:
        raise AssertionError(
            "Los gráficos no corresponden a la versión actual de build_charts.py."
        )

    for relative, expected_hash in metadata["sources"].items():
        source = ROOT / relative
        if csv_semantic_sha256(source) != expected_hash:
            raise AssertionError(
                f"Los gráficos están desactualizados frente a {relative}."
            )

    for filename, expected in metadata["images"].items():
        image_path = CHARTS / filename
        if not image_path.exists() or image_path.stat().st_size < 50_000:
            raise AssertionError(f"Falta un gráfico válido: {filename}.")
        with Image.open(image_path) as image:
            if image.format != "PNG" or image.size != (
                expected["width"],
                expected["height"],
            ):
                raise AssertionError(
                    f"Dimensiones o formato incorrectos en {filename}: "
                    f"{image.format}, {image.size}."
                )

    if set(path.name for path in CHARTS.glob("*.png")) != set(metadata["images"]):
        raise AssertionError("El conjunto de PNG no coincide con metadata.json.")

    print(
        f"OK: {len(metadata['images'])} gráficos sincronizados con sus fuentes y generador."
    )


if __name__ == "__main__":
    main()
