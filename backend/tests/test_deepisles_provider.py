"""Contract tests for the backend DeepISLES HTTP adapter."""

import io
import json
import warnings
import zipfile

import httpx
import numpy as np
import pytest

from app.core.config import settings
from app.services.inference.base import CaseInput, ProviderOutputPersistenceError
from app.services.nifti_codec import save_volume


def _mask_archive(mask_bytes, metadata=None, names=None):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for name in names or ("segmentation.nii.gz", "metadata.json"):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                if name == "segmentation.nii.gz":
                    archive.writestr(name, mask_bytes)
                elif name == "metadata.json":
                    archive.writestr(
                        name,
                        json.dumps(metadata or {
                        "provider": "deepisles",
                        "service": "neuroannotate-deepisles",
                        "service_version": "1.0.0",
                        "model_name": "DeepISLES",
                        "model_version": "7658b608fc0d890cf14448ff3e58c47ad5c761e7",
                        "upstream_commit": "7658b608fc0d890cf14448ff3e58c47ad5c761e7",
                        "configuration": {
                            "skull_strip": False,
                            "fast": False,
                            "save_team_outputs": False,
                            "results_mni": False,
                            "parallelize": True,
                        },
                        "runtime": {
                            "duration_seconds": 0.1,
                            "device": "cuda:0",
                            "cuda_available": True,
                        },
                        }),
                    )
                else:
                    archive.writestr(name, b"unexpected")
    return payload.getvalue()


def _case(tmp_path):
    paths = {}
    for modality in ("DWI", "ADC", "FLAIR"):
        path = tmp_path / (modality.lower() + ".nii.gz")
        save_volume(path, np.zeros((4, 5, 6)), np.eye(4), dtype=np.float32)
        paths[modality] = path
    return CaseInput("case-1", paths)


class _Response:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content


def test_provider_posts_exact_triad_and_writes_valid_result(tmp_path, monkeypatch):
    """Wrong multipart mapping or non-atomic output write must fail this test."""
    from app.services.inference.deepisles import DeepISLESProvider

    source_mask = tmp_path / "source-mask.nii.gz"
    save_volume(source_mask, np.ones((4, 5, 6)), np.eye(4), dtype=np.uint8)
    seen = {}

    class Client:
        def __init__(self, timeout):
            assert timeout is None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, files):
            seen["url"] = url
            seen["files"] = {key: value[0] for key, value in files.items()}
            return _Response(200, _mask_archive(source_mask.read_bytes()))

    monkeypatch.setattr("app.services.inference.deepisles.httpx.Client", Client)
    output = tmp_path / "out" / "segmentation.nii.gz"
    result = DeepISLESProvider("http://service:8080").segment(_case(tmp_path), output)

    assert seen == {
        "url": "http://service:8080/v1/segment",
        "files": {"dwi": "dwi.nii.gz", "adc": "adc.nii.gz", "flair": "flair.nii.gz"},
    }
    assert output.exists()
    assert output.read_bytes() == source_mask.read_bytes()
    assert result.provider == "deepisles"
    assert result.configuration["fast"] is False
    assert result.runtime["device"] == "cuda:0"


@pytest.mark.parametrize(
    "status, archive",
    [
        (500, b"service error"),
        (200, b"not zip"),
        (200, _mask_archive(b"mask", names=("../mask.nii.gz", "metadata.json"))),
        (
            200,
            _mask_archive(
                b"mask",
                names=("segmentation.nii.gz", "segmentation.nii.gz", "metadata.json"),
            ),
        ),
        (200, _mask_archive(b"mask", names=("segmentation.nii.gz", "metadata.json", "extra"))),
        (200, _mask_archive(b"mask", metadata={"provider": "deepisles"})),
    ],
)
def test_provider_rejects_runtime_or_unsafe_response(tmp_path, monkeypatch, status, archive):
    """Permitting service failures or unsafe ZIP payloads must fail this test."""
    from app.services.inference.deepisles import DeepISLESProvider, ProviderRuntimeError

    class Client:
        def __init__(self, timeout):
            del timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _url, files):
            del files
            return _Response(status, archive)

    monkeypatch.setattr("app.services.inference.deepisles.httpx.Client", Client)
    with pytest.raises(ProviderRuntimeError):
        DeepISLESProvider("http://service:8080").segment(
            _case(tmp_path), tmp_path / "result.nii.gz"
        )


def test_connection_error_maps_to_worker_provider_unavailable(client, tmp_path, monkeypatch):
    """Transport failures must not be recorded as generic provider runtime failures."""
    from app.services.inference.worker import InferenceWorker
    from tests.helpers import import_case

    monkeypatch.setattr(settings, "deepisles_url", "http://service:8080")
    case_id = import_case(client, tmp_path)["id"]
    job = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": "deepisles"}
    ).json()

    class Client:
        def __init__(self, timeout):
            assert timeout is None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _url, files):
            del files
            raise httpx.ConnectError("service offline")

    monkeypatch.setattr("app.services.inference.deepisles.httpx.Client", Client)
    assert InferenceWorker().run_once() is True
    done = client.get("/api/inference-jobs/{}".format(job["id"])).json()
    assert done["failure_category"] == "provider_unavailable"


def test_local_output_failure_maps_to_persistence_error(tmp_path, monkeypatch):
    """A local disk write failure must not be relabelled as a service failure."""
    from app.services.inference.deepisles import DeepISLESProvider

    class Client:
        def __init__(self, timeout):
            del timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _url, files):
            del files
            return _Response(200, _mask_archive(b"mask"))

    monkeypatch.setattr("app.services.inference.deepisles.httpx.Client", Client)
    def fail_replace(*_args):
        raise OSError("full")

    monkeypatch.setattr("app.services.inference.deepisles.os.replace", fail_replace)
    with pytest.raises(ProviderOutputPersistenceError):
        DeepISLESProvider("http://service:8080").segment(
            _case(tmp_path), tmp_path / "result.nii.gz"
        )


def test_registry_keeps_demo_default_and_exposes_configured_deepisles(monkeypatch):
    """Changing demo defaults or hiding the configured provider must fail this test."""
    from app.services.inference.registry import get_provider, list_providers

    monkeypatch.setattr(settings, "inference_provider", "demo")
    monkeypatch.setattr(settings, "deepisles_url", "http://service:8080")
    assert get_provider().name == "demo"
    assert [provider.name for provider in list_providers()] == ["demo", "nnunet", "deepisles"]
    assert get_provider("deepisles").info().available is True
