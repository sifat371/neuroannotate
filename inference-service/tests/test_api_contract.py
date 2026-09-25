"""Black-box contract tests for the isolated DeepISLES HTTP service."""

import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _nifti_bytes(
    shape=(4, 5, 6), affine=None, data=None, dtype=np.float32
):
    array = np.zeros(shape, dtype=dtype) if data is None else np.asarray(data, dtype=dtype)
    image = nib.Nifti1Image(array, np.eye(4) if affine is None else affine)
    image.header.set_data_dtype(array.dtype)
    return gzip.compress(image.to_bytes())


def _uploads(dwi=None):
    return {
        "dwi": ("dwi.nii.gz", dwi or _nifti_bytes(), "application/gzip"),
        "adc": ("adc.nii.gz", _nifti_bytes(), "application/gzip"),
        "flair": ("flair.nii.gz", _nifti_bytes(), "application/gzip"),
    }


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_health_and_info_identify_pinned_service_without_loading_model(client):
    """Removing the pinned identity/readiness contract must fail this test."""
    health = client.get("/health")
    info = client.get("/v1/info")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert info.status_code == 200
    assert info.json()["service"] == "neuroannotate-deepisles"
    assert info.json()["upstream_commit"] == "BrainLesion/stroke_segmentor@0.0.3"
    assert info.json()["model_name"] == "DeepISLES NVAUTO via BrainLesion stroke_segmentor"
    assert {"cuda_available", "device", "ready"} <= set(info.json())


def test_segment_returns_exact_safe_archive_and_dwi_geometry(client, monkeypatch):
    """Wrong archive members, metadata leakage, or runner ordering must fail."""
    from app import main

    seen = []

    def fake_runner(dwi, adc, flair, output_dir):
        seen.append((dwi, adc, flair, output_dir))
        output = output_dir / "lesion_msk.nii.gz"
        output.write_bytes(_nifti_bytes(data=np.ones((4, 5, 6)), dtype=np.uint8))
        return output

    monkeypatch.setattr(main, "run_deepisles", fake_runner)
    response = client.post("/v1/segment", files=_uploads())

    assert response.status_code == 200, response.text
    assert [path.name for path in seen[0][:3]] == ["dwi.nii.gz", "adc.nii.gz", "flair.nii.gz"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["segmentation.nii.gz", "metadata.json"]
        metadata = json.loads(archive.read("metadata.json"))
        mask = nib.Nifti1Image.from_bytes(gzip.decompress(archive.read("segmentation.nii.gz")))
    assert metadata["provider"] == "deepisles"
    assert metadata["upstream_commit"] == "BrainLesion/stroke_segmentor@0.0.3"
    assert metadata["configuration"] == {
        "implementation": "BrainLesion stroke_segmentor",
        "modalities": ["ADC", "DWI"],
        "flair_used": False,
    }
    assert "path" not in json.dumps(metadata).lower()
    assert mask.shape == (4, 5, 6)
    assert mask.get_data_dtype() == np.dtype("uint8")
    np.testing.assert_allclose(mask.affine, np.eye(4), atol=1e-5, rtol=0)
    assert set(np.unique(np.asanyarray(mask.dataobj))) == {1}


def test_segment_rejects_missing_or_extra_multipart_fields(client):
    """Accepting an incomplete or ambiguous modality triad is a contract bug."""
    missing = _uploads()
    del missing["flair"]
    assert client.post("/v1/segment", files=missing).status_code == 422

    extra = _uploads()
    extra["other"] = ("other.nii.gz", _nifti_bytes(), "application/gzip")
    assert client.post("/v1/segment", files=extra).status_code == 422

    duplicated = list(_uploads().items())
    duplicated.append(("dwi", ("another-dwi.nii.gz", _nifti_bytes(), "application/gzip")))
    assert client.post("/v1/segment", files=duplicated).status_code == 422


@pytest.mark.parametrize(
    "shape, affine, data",
    [
        ((3, 5, 6), np.eye(4), np.zeros((3, 5, 6), dtype=np.uint8)),
        ((4, 5, 6), np.diag((2.0, 1.0, 1.0, 1.0)), np.zeros((4, 5, 6), dtype=np.uint8)),
        ((4, 5, 6), np.eye(4), np.full((4, 5, 6), 2, dtype=np.uint8)),
        ((4, 5, 6), np.eye(4), np.full((4, 5, 6), np.nan, dtype=np.float32)),
    ],
)
def test_segment_rejects_noncanonical_or_nonbinary_runner_output(
    client, monkeypatch, shape, affine, data
):
    """Removing DWI-space, binary, or uint8 checks must fail this test."""
    from app import main

    def fake_runner(_dwi, _adc, _flair, output_dir):
        output = output_dir / "lesion_msk.nii.gz"
        output.write_bytes(_nifti_bytes(shape=shape, affine=affine, data=data, dtype=data.dtype))
        return output

    monkeypatch.setattr(main, "run_deepisles", fake_runner)
    assert client.post("/v1/segment", files=_uploads()).status_code == 422


def test_segment_cleans_request_files_when_runner_fails(client, monkeypatch):
    """Keeping request-owned files after a model failure must fail this test."""
    from app import main

    inputs = []

    def broken_runner(dwi, adc, flair, _output_dir):
        inputs.extend((dwi, adc, flair))
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(main, "run_deepisles", broken_runner)
    response = client.post("/v1/segment", files=_uploads())

    assert response.status_code == 500
    assert inputs and not any(path.exists() for path in inputs)


def test_segment_keeps_health_responsive_while_model_runs(client, monkeypatch):
    """A long synchronous model call must not block the FastAPI event loop."""
    import concurrent.futures
    import threading

    from app import main

    started = threading.Event()
    release = threading.Event()

    def delayed_runner(dwi, _adc, _flair, output_dir):
        started.set()
        assert release.wait(2), "test did not release the fake model"
        dwi_image = nib.load(dwi)
        output = output_dir / "lesion_msk.nii.gz"
        output.write_bytes(
            _nifti_bytes(
                shape=dwi_image.shape,
                affine=dwi_image.affine,
                data=np.zeros(dwi_image.shape, dtype=np.uint8),
                dtype=np.uint8,
            )
        )
        return output

    monkeypatch.setattr(main, "run_deepisles", delayed_runner)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        segment_future = pool.submit(client.post, "/v1/segment", files=_uploads())
        assert started.wait(1)
        health_future = pool.submit(client.get, "/health")
        try:
            health = health_future.result(timeout=0.4)
        except concurrent.futures.TimeoutError:
            health = None
        finally:
            release.set()
        segment_response = segment_future.result(timeout=3)

    assert health is not None, "health request was blocked by model inference"
    assert health.status_code == 200
    assert segment_response.status_code == 200


def test_segment_serializes_model_execution(client, monkeypatch):
    """Offloaded requests must still enforce one model execution at a time."""
    import concurrent.futures
    import threading
    import time

    from app import main

    state_lock = threading.Lock()
    active = 0
    max_active = 0

    def delayed_runner(dwi, _adc, _flair, output_dir):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.08)
            dwi_image = nib.load(dwi)
            output = output_dir / "lesion_msk.nii.gz"
            output.write_bytes(
                _nifti_bytes(
                    shape=dwi_image.shape,
                    affine=dwi_image.affine,
                    data=np.zeros(dwi_image.shape, dtype=np.uint8),
                    dtype=np.uint8,
                )
            )
            return output
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr(main, "run_deepisles", delayed_runner)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(client.post, "/v1/segment", files=_uploads()) for _ in range(2)]
        responses = [future.result(timeout=3) for future in futures]

    assert [response.status_code for response in responses] == [200, 200]
    assert max_active == 1
