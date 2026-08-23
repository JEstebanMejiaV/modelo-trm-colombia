from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "graficos"
METADATA = CHARTS / "metadata.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    metadata = json.loads(METADATA.read_text(encoding="utf-8"))
    if metadata.get("version") != 1:
        raise AssertionError("Versión desconocida de metadata de gráficos.")

    generator = metadata["generator"]
    generator_path = ROOT / generator["path"]
    if sha256(generator_path) != generator["sha256"]:
        raise AssertionError(
            "Los gráficos no corresponden a la versión actual de build_charts.py."
        )

    for relative, expected_hash in metadata["sources"].items():
        source = ROOT / relative
        if sha256(source) != expected_hash:
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
