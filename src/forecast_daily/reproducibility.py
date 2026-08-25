"""Configuración determinista compartida por el producto diario."""
from __future__ import annotations

import os
import random


DAILY_RANDOM_SEED = 42

# Deben definirse antes de importar NumPy, PyTorch o los estimadores de árboles.
for _variable in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ.setdefault(_variable, "1")
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

_torch_threads_configured = False


def configure_determinism(seed: int = DAILY_RANDOM_SEED) -> None:
    """Fija RNGs de Python y NumPy sin importar runtimes ML pesados."""
    random.seed(seed)
    import numpy as np

    np.random.seed(seed)


def configure_torch_determinism(seed: int = DAILY_RANDOM_SEED) -> None:
    """Fija PyTorch cuando la ruta RNN ya está a punto de ejecutarse.

    Se mantiene separado para no cargar el runtime OpenMP de PyTorch antes de
    SciPy/XGBoost/LightGBM, lo que puede provocar copias incompatibles de
    ``libiomp5md.dll`` en Windows.
    """
    global _torch_threads_configured

    configure_determinism(seed)
    try:
        import torch
    except ImportError:
        return

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    if not _torch_threads_configured:
        # Si otro backend ya inicializó los hilos, conservar su configuración
        # es preferible a abortar una corrida legacy.
        try:
            torch.set_num_threads(1)
        except RuntimeError:
            pass
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
        _torch_threads_configured = True

    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except (AttributeError, RuntimeError):
        pass
