"""Bounded, privacy-safe runtime diagnostics."""

from typing import Any

import httpx
from fastapi import APIRouter
from httpx import HTTPError, Timeout
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])
_UPSTREAM_COMMIT = "7658b608fc0d890cf14448ff3e58c47ad5c761e7"
_HEALTH_TIMEOUT_SECONDS = 2.0


def _probe_storage() -> bool:
    """Ensure the managed root exists without reading user artifacts."""
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        return settings.data_dir.is_dir()
    except OSError:
        return False


def _probe_database() -> bool:
    """Check database connectivity with a constant, side-effect-free query."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except (OSError, SQLAlchemyError):
        return False


def _deepisles_health() -> dict[str, Any]:
    """Return safe DeepISLES facts only after validating the private service."""
    if not settings.deepisles_url:
        return {"mode": "gpu", "deepisles": "unavailable", "ready": False}
    try:
        timeout = Timeout(_HEALTH_TIMEOUT_SECONDS)
        with httpx.Client(timeout=timeout) as client:
            liveness = client.get(f"{settings.deepisles_url.rstrip('/')}/health")
            liveness.raise_for_status()
            info = client.get(f"{settings.deepisles_url.rstrip('/')}/v1/info")
            info.raise_for_status()
            payload = info.json()
    except (HTTPError, ValueError, TypeError):
        return {"mode": "gpu", "deepisles": "unavailable", "ready": False}

    required_strings = (
        "service",
        "service_version",
        "model_name",
        "model_version",
        "upstream_commit",
        "device",
    )
    if (
        not isinstance(payload, dict)
        or any(
            not isinstance(payload.get(key), str) or not payload[key]
            for key in required_strings
        )
        or payload["upstream_commit"] != _UPSTREAM_COMMIT
        or payload["model_version"] != _UPSTREAM_COMMIT
        or payload.get("cuda_available") is not True
        or payload.get("ready") is not True
    ):
        return {"mode": "gpu", "deepisles": "unavailable", "ready": False}

    return {
        "mode": "gpu",
        "deepisles": "ready",
        "ready": True,
        "service": payload["service"],
        "service_version": payload["service_version"],
        "model_name": payload["model_name"],
        "model_version": payload["model_version"],
        "device": payload["device"],
        "cuda_available": payload["cuda_available"],
    }


def _inference_health() -> dict[str, Any]:
    """Select the configured provider mode and fail closed for unknown modes."""
    if settings.inference_provider == "demo":
        return {"mode": "demo", "deepisles": "not_enabled", "ready": True}
    if settings.inference_provider == "deepisles":
        return _deepisles_health()
    return {"mode": "unknown", "deepisles": "unavailable", "ready": False}


def _health_payload() -> dict[str, Any]:
    """Build the stable health response without exposing host implementation details."""
    storage_ready = _probe_storage()
    database_ready = _probe_database()
    inference = _inference_health()
    return {
        "status": "ok" if storage_ready and database_ready else "unavailable",
        "service": "neuroannotate-api",
        "storage": "ok" if storage_ready else "unavailable",
        "database": "ok" if database_ready else "unavailable",
        "inference": inference,
    }


@router.get("/health")
@router.get("/api/health")
def health() -> dict[str, Any]:
    """Return backend, persistence, and configured inference readiness."""
    return _health_payload()
