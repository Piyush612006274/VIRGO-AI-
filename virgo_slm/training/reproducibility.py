"""Deterministic seed handling.

Sets Python's ``random``, NumPy's, and PyTorch's (CPU + CUDA, if present)
RNGs from one seed. Also asks PyTorch for deterministic algorithms where
supported.

DOCUMENTED LIMITATION (Task 17 requires this be stated, not hidden):
bit-perfect determinism is only claimed for CPU. This is not merely a
disclaimer -- it reflects an actual PyTorch limitation: some CUDA
kernels (e.g. certain reductions/atomics) are not bit-reproducible
across runs even with a fixed seed and
``torch.use_deterministic_algorithms(True)``, and GPU hardware/driver
differences can affect results further. The reproducibility smoke test
in this repo (``test_reproducibility.py``) only asserts CPU determinism,
matching what is actually verified.
"""

from __future__ import annotations

import random

import numpy as np
import torch


def set_seed(seed: int, *, deterministic_algorithms: bool = True) -> None:
    """Seed Python/NumPy/PyTorch RNGs from ``seed``.

    ``deterministic_algorithms=True`` additionally asks PyTorch to error
    (rather than silently produce non-deterministic results) if an op
    without a deterministic CPU/CUDA implementation is used -- catching
    accidental non-determinism early rather than discovering it via a
    flaky reproducibility test.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic_algorithms:
        torch.use_deterministic_algorithms(True, warn_only=True)
