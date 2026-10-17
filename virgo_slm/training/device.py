"""Device and precision resolution.

Never assumes CUDA exists. ``"auto"`` picks CUDA if
``torch.cuda.is_available()``, else CPU. Requesting ``"cuda"`` explicitly
on a machine without CUDA raises :class:`UnavailableDeviceError` rather
than silently falling back to CPU (Task 20: don't silently continue after
a request that can't be honored).
"""

from __future__ import annotations

import torch

from virgo_slm.training.config import DeviceConfig, PrecisionConfig
from virgo_slm.training.errors import UnavailableDeviceError, UnsupportedPrecisionError


def resolve_device(config: DeviceConfig) -> torch.device:
    if config.device == "cpu":
        return torch.device("cpu")
    if config.device == "cuda":
        if not torch.cuda.is_available():
            raise UnavailableDeviceError(
                "device='cuda' was requested but torch.cuda.is_available() "
                "is False on this machine."
            )
        return torch.device("cuda")
    # "auto"
    return torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")


def resolve_dtype(config: PrecisionConfig, device: torch.device) -> torch.dtype:
    """Resolve a requested precision to a concrete ``torch.dtype`` for ``device``.

    ``"fp16"``/``"bf16"`` on CPU are rejected rather than silently
    downgraded to fp32 -- PyTorch's CPU autocast support for these is
    inconsistent across versions/ops, and this repo's smoke tests are
    CPU-only, so claiming fp16/bf16 "works" on CPU without exercising the
    actual autocast path would be an unverified claim. Use ``"auto"`` to
    get a device-appropriate choice instead.
    """
    if config.precision == "fp32":
        return torch.float32
    if config.precision == "fp16":
        if device.type != "cuda":
            raise UnsupportedPrecisionError(
                "precision='fp16' requires a CUDA device; "
                f"resolved device is {device.type!r}."
            )
        return torch.float16
    if config.precision == "bf16":
        if device.type != "cuda":
            raise UnsupportedPrecisionError(
                "precision='bf16' requires a CUDA device; "
                f"resolved device is {device.type!r}."
            )
        if not torch.cuda.is_bf16_supported():
            raise UnsupportedPrecisionError(
                "precision='bf16' was requested but this CUDA device does "
                "not support bf16 (torch.cuda.is_bf16_supported() is False)."
            )
        return torch.bfloat16
    # "auto"
    if device.type == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    if device.type == "cuda":
        return torch.float16
    return torch.float32
