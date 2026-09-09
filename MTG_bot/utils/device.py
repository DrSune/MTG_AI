"""Centralised device selection.

Single source of truth for where tensors live. Never call ``torch.device("cuda")``
directly anywhere else in the codebase: the training target (DGX Spark, CUDA/ARM64)
and the development box (Intel Arc, XPU) disagree, and hardcoding either one breaks
the other.

Priority: CUDA (DGX Spark / any NVIDIA) > XPU (Intel Arc) > MPS > CPU.
Override with the MTG_DEVICE environment variable, e.g. ``MTG_DEVICE=cpu``.
"""

from __future__ import annotations

import os
from functools import lru_cache

import torch

from MTG_bot.utils.logger import setup_logger

logger = setup_logger("DeviceSelection")


@lru_cache(maxsize=1)
def get_device() -> torch.device:
    """Return the best available torch device, logging the choice once."""
    override = os.environ.get("MTG_DEVICE")
    if override:
        logger.info("Device forced by MTG_DEVICE=%s", override)
        return torch.device(override)

    if torch.cuda.is_available():
        logger.info("Using NVIDIA GPU (CUDA): %s", torch.cuda.get_device_name(0))
        return torch.device("cuda")

    # Intel Arc / Xe. Present on the Windows development box.
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        logger.info("Using Intel GPU (XPU): %s", torch.xpu.get_device_name(0))
        return torch.device("xpu")

    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        logger.info("Using Apple MPS.")
        return torch.device("mps")

    logger.info("Using CPU for execution.")
    return torch.device("cpu")


def autocast_dtype(device: torch.device | None = None) -> torch.dtype:
    """Preferred mixed-precision dtype for a device.

    Blackwell and Arc both do bfloat16 well; CPU autocast is bfloat16 too.
    """
    device = device or get_device()
    if device.type == "cuda" and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    if device.type in ("xpu", "cpu"):
        return torch.bfloat16
    return torch.float16
