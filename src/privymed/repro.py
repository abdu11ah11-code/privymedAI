"""Reproducibility helpers.

Notes on what seeding can and cannot do:

* ``PYTHONHASHSEED`` only takes effect at interpreter start-up. Setting it
  at runtime does **not** make ``hash(str)`` or ``set`` iteration order
  reproducible in the current process. Generation code must therefore never
  depend on ``set`` iteration order (iterate sorted lists instead), and
  :func:`check_hash_seed` warns when the variable is not set.
* Libraries with private RNGs (e.g. Faker) must be seeded explicitly by the
  component that owns them (``Faker.seed_instance(seed)``).
"""

from __future__ import annotations

import importlib
import logging
import os
import random

_log = logging.getLogger(__name__)


def check_hash_seed() -> bool:
    """Return True if ``PYTHONHASHSEED`` was fixed at start-up; warn otherwise."""
    value = os.environ.get("PYTHONHASHSEED")
    if value is None or value == "random":
        _log.warning(
            "PYTHONHASHSEED is not set; str hashing / set order vary between runs. "
            "Code must not depend on set iteration order."
        )
        return False
    return True


def set_global_seed(seed: int, *, deterministic_torch: bool = False) -> None:
    """Seed Python's ``random`` and, if installed, NumPy and PyTorch.

    ``deterministic_torch=True`` additionally requests deterministic CUDA
    kernels (slower; use for final reproducibility runs).
    """
    random.seed(seed)
    try:
        np = importlib.import_module("numpy")
        np.random.seed(seed)
    except ModuleNotFoundError:
        pass
    try:
        torch = importlib.import_module("torch")
    except (ModuleNotFoundError, OSError):  # OSError: broken CUDA DLLs on Windows
        return
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic_torch:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True)
