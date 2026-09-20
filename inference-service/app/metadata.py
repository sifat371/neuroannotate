"""Stable, privacy-safe identity and runtime metadata for the service."""
# ruff: noqa: UP006, UP035

from __future__ import annotations

from typing import Any, Dict

SERVICE_NAME = "neuroannotate-deepisles"
SERVICE_VERSION = "1.0.0"
MODEL_NAME = "DeepISLES"
UPSTREAM_COMMIT = "7658b608fc0d890cf14448ff3e58c47ad5c761e7"


def runtime_metadata() -> Dict[str, Any]:
    """Return lightweight runtime facts without loading the DeepISLES model."""
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
        "ready": True,
    }


def service_info() -> Dict[str, Any]:
    """Return the public service identity used by the backend provider."""
    info = runtime_metadata()
    info.update(
        {
            "service": SERVICE_NAME,
            "service_version": SERVICE_VERSION,
            "engine": "DeepISLES",
            "model_name": MODEL_NAME,
            "model_version": UPSTREAM_COMMIT,
            "upstream_commit": UPSTREAM_COMMIT,
        }
    )
    return info
