"""Stable, privacy-safe identity and runtime metadata for the service."""
# ruff: noqa: UP006, UP035

from __future__ import annotations

from typing import Any, Dict

SERVICE_NAME = "neuroannotate-deepisles"
SERVICE_VERSION = "1.1.0"
MODEL_NAME = "DeepISLES NVAUTO via BrainLesion stroke_segmentor"
MODEL_VERSION = "stroke-segmentor-0.0.3"
UPSTREAM_COMMIT = "BrainLesion/stroke_segmentor@0.0.3"


def runtime_metadata() -> Dict[str, Any]:
    """Return lightweight runtime facts without loading model checkpoints."""
    cuda_available = False
    device = "cpu"
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        if cuda_available:
            device = "cuda:0"
    except (ImportError, OSError):
        pass
    return {
        "cuda_available": cuda_available,
        "device": device,
        "ready": cuda_available,
    }


def service_info() -> Dict[str, Any]:
    """Return the public service identity used by the backend provider."""
    info = runtime_metadata()
    info.update(
        {
            "service": SERVICE_NAME,
            "service_version": SERVICE_VERSION,
            "engine": "stroke_segmentor",
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "upstream_commit": UPSTREAM_COMMIT,
        }
    )
    return info
