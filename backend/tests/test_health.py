"""Observable runtime health contract tests."""

from threading import Event
from time import monotonic, sleep
from typing import Any

import httpx

from app.api.routes import health as health_route
from app.core.config import settings


def test_health_routes_report_expected_demo_mode_without_network(client, monkeypatch):
    """A demo deployment must be ready without contacting DeepISLES."""
    monkeypatch.setattr(settings, "inference_provider", "demo")
    monkeypatch.setattr(settings, "deepisles_url", None)

    def forbidden_client(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("demo health must not construct an HTTP client")

    monkeypatch.setattr(
        health_route,
        "httpx",
        type("Httpx", (), {"Client": forbidden_client}),
        raising=False,
    )

    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "service": "neuroannotate-api",
            "storage": "ok",
            "database": "ok",
            "inference": {
                "mode": "demo",
                "deepisles": "not_enabled",
                "ready": True,
            },
        }


def test_health_reports_ready_deepisles_runtime_facts(client, monkeypatch):
    """A healthy GPU provider exposes only the identity facts the UI needs."""
    monkeypatch.setattr(settings, "inference_provider", "deepisles")
    monkeypatch.setattr(settings, "deepisles_url", "http://deepisles:8080")

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    class Client:
        def __init__(self, *, timeout: httpx.Timeout) -> None:
            assert timeout.connect is not None
            assert timeout.read is not None

        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, path: str) -> Response:
            if path.endswith("/health"):
                return Response({"status": "ok"})
            assert path.endswith("/v1/info")
            return Response(
                {
                    "service": "neuroannotate-deepisles",
                    "service_version": "1.0.0",
                    "model_name": "DeepISLES",
                    "model_version": "7658b608fc0d890cf14448ff3e58c47ad5c761e7",
                    "upstream_commit": "7658b608fc0d890cf14448ff3e58c47ad5c761e7",
                    "cuda_available": True,
                    "device": "cuda:0",
                    "ready": True,
                }
            )

    monkeypatch.setattr(
        health_route,
        "httpx",
        type("Httpx", (), {"Client": Client, "Timeout": httpx.Timeout}),
        raising=False,
    )

    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["inference"] == {
        "mode": "gpu",
        "deepisles": "ready",
        "ready": True,
        "service": "neuroannotate-deepisles",
        "service_version": "1.0.0",
        "model_name": "DeepISLES",
        "model_version": "7658b608fc0d890cf14448ff3e58c47ad5c761e7",
        "device": "cuda:0",
        "cuda_available": True,
    }


def test_health_fails_closed_for_missing_or_unavailable_deepisles(client, monkeypatch):
    """Missing or unreachable GPU services are not ready."""
    monkeypatch.setattr(settings, "inference_provider", "deepisles")

    monkeypatch.setattr(settings, "deepisles_url", None)
    assert client.get("/api/health").json()["inference"] == {
        "mode": "gpu", "deepisles": "unavailable", "ready": False
    }


def test_health_rejects_malformed_or_wrong_commit_deepisles_info(client, monkeypatch):
    """A liveness response alone cannot make an unverified GPU model ready."""
    monkeypatch.setattr(settings, "inference_provider", "deepisles")
    monkeypatch.setattr(settings, "deepisles_url", "http://deepisles:8080")

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    class Client:
        def __init__(self, *, timeout: httpx.Timeout) -> None:
            del timeout

        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, path: str) -> Response:
            if path.endswith("/health"):
                return Response({"status": "ok"})
            return Response({"upstream_commit": "wrong"})

    monkeypatch.setattr(
        health_route,
        "httpx",
        type("Httpx", (), {"Client": Client}),
        raising=False,
    )
    assert client.get("/api/health").json()["inference"] == {
        "mode": "gpu", "deepisles": "unavailable", "ready": False
    }


def test_health_rejects_non_success_deepisles_response(client, monkeypatch):
    """A non-2xx private service response cannot make GPU mode ready."""
    monkeypatch.setattr(settings, "inference_provider", "deepisles")
    monkeypatch.setattr(settings, "deepisles_url", "http://deepisles:8080")
    request = httpx.Request("GET", "http://deepisles:8080/health")
    response = httpx.Response(503, request=request)

    class Client:
        def __init__(self, *, timeout: httpx.Timeout) -> None:
            del timeout

        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, _path: str) -> httpx.Response:
            return response

    monkeypatch.setattr(
        health_route,
        "httpx",
        type("Httpx", (), {"Client": Client}),
        raising=False,
    )
    assert client.get("/api/health").json()["inference"] == {
        "mode": "gpu", "deepisles": "unavailable", "ready": False
    }

    monkeypatch.setattr(settings, "deepisles_url", "http://deepisles:8080")

    class FailingClient:
        def __init__(self, **_: object) -> None:
            pass

        def __enter__(self) -> "FailingClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, _path: str) -> object:
            raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(
        health_route,
        "httpx",
        type("Httpx", (), {"Client": FailingClient, "Timeout": httpx.Timeout}),
        raising=False,
    )
    assert client.get("/api/health").json()["inference"] == {
        "mode": "gpu", "deepisles": "unavailable", "ready": False
    }


def test_health_reports_component_degradation_without_exception_text(client, monkeypatch):
    """Storage/database probe failures remain bounded diagnostics, not endpoint failures."""
    monkeypatch.setattr(health_route, "_probe_storage", lambda: False, raising=False)
    monkeypatch.setattr(health_route, "_probe_database", lambda: False, raising=False)

    body = client.get("/api/health").json()
    assert body["status"] == "unavailable"
    assert body["storage"] == "unavailable"
    assert body["database"] == "unavailable"
    assert "error" not in body


def test_health_distinguishes_legacy_nnunet_from_unknown_provider(client, monkeypatch):
    """The legacy provider is diagnosable without treating unknown config as demo."""
    monkeypatch.setattr(settings, "inference_provider", "nnunet")
    assert client.get("/api/health").json()["inference"] == {
        "mode": "legacy",
        "provider": "nnunet",
        "deepisles": "not_enabled",
        "ready": False,
    }

    monkeypatch.setattr(settings, "inference_provider", "unexpected-provider")
    assert client.get("/api/health").json()["inference"] == {
        "mode": "unknown",
        "provider": "unknown",
        "deepisles": "unavailable",
        "ready": False,
    }


def test_database_probe_returns_before_a_stalled_connection_completes(monkeypatch):
    """A wedged database operation cannot indefinitely block a health request."""
    started = Event()
    release = Event()
    calls = 0

    def blocked_check() -> bool:
        nonlocal calls
        calls += 1
        started.set()
        release.wait(timeout=0.4)
        return True

    probe = health_route._DatabaseProbe(blocked_check, wait_seconds=0.02)
    started_at = monotonic()
    try:
        assert probe.probe() is False
        assert started.wait(timeout=0.1)
        assert all(probe.probe() is False for _ in range(4))
        assert calls == 1
        assert monotonic() - started_at < 0.15
    finally:
        release.set()
    sleep(0.03)
    assert probe.probe() is True


def test_database_probe_recovers_after_an_unexpected_worker_exception():
    """An unexpected callback error must not leave the single worker permanently busy."""
    calls = 0

    def flaky_check() -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("unexpected driver failure")
        return True

    probe = health_route._DatabaseProbe(
        flaky_check,
        wait_seconds=0.05,
        cache_seconds=0,
    )

    assert probe.probe() is False
    assert probe.probe() is True
    assert calls == 2
