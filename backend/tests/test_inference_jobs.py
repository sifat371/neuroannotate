import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.core.config import settings
from app.core.release import RELEASE_VERSION
from app.db.models import InferenceJob, SourceArtifact
from app.db.session import new_session
from app.services.inference import jobs as jobs_module
from app.services.inference.demo import DemoSegmentationProvider
from app.services.nifti_codec import load_volume, save_volume
from tests.helpers import import_case


def test_demo_job_moves_queued_to_completed(client, tmp_path: Path) -> None:
    case_id = import_case(client, tmp_path)["id"]
    response = client.post(f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"})
    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["segmentation_id"] is None

    from app.services.inference.worker import InferenceWorker

    assert InferenceWorker().run_once() is True
    done = client.get(f"/api/inference-jobs/{queued['id']}").json()
    assert done["status"] == "completed"
    assert done["segmentation_id"]
    assert done["started_at"] and done["completed_at"]
    assert done["model_name"] and done["model_version"] and done["service_version"]
    with new_session() as session:
        job = session.get(InferenceJob, queued["id"])
        artifact = job.segmentation
        mask_path = settings.data_dir / artifact.relative_path
        assert artifact.relative_path == f"inference/{job.id}/segmentation.nii.gz"
        assert artifact.sha256 == hashlib.sha256(mask_path.read_bytes()).hexdigest()
        provenance = json.loads(job.provenance_json)
        assert provenance["configuration"]
        assert provenance["runtime"]["duration_seconds"] >= 0
        assert provenance["result"]["sha256"] == artifact.sha256
        assert len(provenance["sources"]) == 3
        for source in provenance["sources"]:
            assert source["sha256"] == session.get(SourceArtifact, source["id"]).sha256
    volume = load_volume(mask_path)
    assert volume.data.shape == (8, 8, 8)
    assert volume.datatype == "uint8"
    assert np.isfinite(volume.data).all()
    assert set(np.unique(volume.data)) <= {0, 1}
    np.testing.assert_allclose(volume.affine, np.eye(4), atol=1e-4, rtol=0)
    download = client.get(f"/api/segmentations/{done['segmentation_id']}/file.nii.gz")
    assert download.status_code == 200
    assert download.content == mask_path.read_bytes()
    assert InferenceWorker().run_once() is False


def test_demo_supports_native_reference_geometries(client, tmp_path: Path) -> None:
    from app.services.inference.worker import InferenceWorker

    shapes = {"dwi": (8, 7, 6), "adc": (3, 4, 5), "flair": (5, 6, 7)}
    files = {}
    for modality, shape in shapes.items():
        path = tmp_path / f"{modality}.nii.gz"
        affine = np.diag((1.0, 1.0, 2.0, 1.0)) if modality == "dwi" else np.eye(4)
        save_volume(path, np.arange(np.prod(shape)).reshape(shape), affine)
        files[modality] = (path.name, path.read_bytes(), "application/gzip")
    case_id = client.post(
        "/api/cases", data={"name": "Native references"}, files=files
    ).json()["id"]
    job = client.post(f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}).json()
    InferenceWorker().run_once()
    done = client.get(f"/api/inference-jobs/{job['id']}").json()
    assert done["status"] == "completed", done
    output = tmp_path / "result.nii.gz"
    output.write_bytes(client.get(f"/api/segmentations/{done['segmentation_id']}/file.nii.gz").content)
    volume = load_volume(output)
    assert volume.data.shape == (8, 7, 6)
    np.testing.assert_allclose(volume.affine, np.diag((1.0, 1.0, 2.0, 1.0)))
    assert done["provenance"]["configuration"]["input_modalities"] == ["DWI"]


def test_case_job_history_lists_queued_jobs(client, tmp_path: Path) -> None:
    case_id = import_case(client, tmp_path)["id"]
    queued = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}
    ).json()

    response = client.get(f"/api/cases/{case_id}/inference-jobs")

    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [queued["id"]]


def test_retry_of_failed_job_creates_new_queued_job(client, tmp_path: Path) -> None:
    from app.services.inference.worker import InferenceWorker

    case_id = import_case(client, tmp_path)["id"]
    failed = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": "nnunet"}
    ).json()
    InferenceWorker().run_once()

    response = client.post(f"/api/inference-jobs/{failed['id']}/retry")

    assert response.status_code == 202
    retried = response.json()
    assert retried["id"] != failed["id"]
    assert retried["status"] == "queued"
    original = client.get(f"/api/inference-jobs/{failed['id']}").json()
    assert original["status"] == "failed"
    assert original["failure_category"] == "provider_unavailable"


def test_nonfailed_job_cannot_be_retried(client, tmp_path: Path) -> None:
    case_id = import_case(client, tmp_path)["id"]
    queued = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}
    ).json()

    response = client.post(f"/api/inference-jobs/{queued['id']}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "job_not_failed"


def test_provider_status_reports_identity_and_availability(client) -> None:
    response = client.get("/api/inference/providers")

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "demo",
            "model_name": "deterministic_demo_threshold",
            "model_version": "2",
            "service_version": RELEASE_VERSION,
            "available": True,
        },
        {
            "name": "nnunet",
            "model_name": "nnunet",
            "model_version": "unconfigured",
            "service_version": RELEASE_VERSION,
            "available": False,
        },
    ]


def test_job_state_transitions_reject_changes_to_terminal_jobs() -> None:
    job = InferenceJob(
        case_id="case-id",
        provider="demo",
        model_name="demo",
        model_version="1",
        service_version="1",
        status="queued",
    )

    jobs_module.transition_job(job, "running")
    assert job.status == "running"
    assert job.started_at is not None
    jobs_module.transition_job(job, "completed")
    assert job.status == "completed"
    assert job.completed_at is not None

    with pytest.raises(ValueError, match="completed.*failed"):
        jobs_module.transition_job(job, "failed")


def test_job_creation_rejects_client_supplied_status(client, tmp_path: Path) -> None:
    case_id = import_case(client, tmp_path)["id"]

    response = client.post(
        f"/api/cases/{case_id}/inference-jobs",
        json={"provider": "demo", "status": "completed"},
    )

    assert response.status_code == 422
    assert client.get(f"/api/cases/{case_id}/inference-jobs").json() == []


def test_run_once_processes_only_oldest_queued_job(client, tmp_path: Path) -> None:
    from app.services.inference.worker import InferenceWorker

    first_path = tmp_path / "first"
    second_path = tmp_path / "second"
    first_path.mkdir()
    second_path.mkdir()
    first_case = import_case(client, first_path, name="First")["id"]
    second_case = import_case(client, second_path, name="Second")["id"]
    first = client.post(
        f"/api/cases/{first_case}/inference-jobs", json={"provider": "demo"}
    ).json()
    second = client.post(
        f"/api/cases/{second_case}/inference-jobs", json={"provider": "demo"}
    ).json()

    assert InferenceWorker().run_once() is True

    assert client.get(f"/api/inference-jobs/{first['id']}").json()["status"] == "completed"
    assert client.get(f"/api/inference-jobs/{second['id']}").json()["status"] == "queued"


def test_demo_output_write_failure_is_artifact_persistence_failure(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import select

    from app.db.models import SegmentationArtifact
    from app.services.inference.worker import InferenceWorker

    case_id = import_case(client, tmp_path)["id"]
    queued = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}
    ).json()

    def fail_output_write(*_args, **_kwargs) -> None:
        raise OSError("disk full while writing demo mask")

    monkeypatch.setattr("app.services.inference.demo.save_volume", fail_output_write)

    assert InferenceWorker().run_once() is True
    failed = client.get(f"/api/inference-jobs/{queued['id']}").json()
    assert failed["status"] == "failed"
    assert failed["failure_category"] == "artifact_persistence_failure"
    assert failed["segmentation_id"] is None
    with new_session() as session:
        assert session.scalar(select(SegmentationArtifact)) is None
    assert not list((settings.data_dir / "inference").rglob("*.nii.gz"))


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        ("unavailable", "provider_unavailable"),
        ("runtime", "provider_runtime_failure"),
        ("shape", "invalid_model_output"),
        ("affine", "invalid_model_output"),
        ("affine_tolerance", "invalid_model_output"),
        ("dtype", "invalid_model_output"),
        ("nonbinary", "invalid_model_output"),
        ("nonfinite", "invalid_model_output"),
        ("unreadable", "invalid_model_output"),
        ("source_changed", "input_validation_failure"),
        ("source_missing", "input_validation_failure"),
        ("provenance", "input_validation_failure"),
        ("metadata", "artifact_persistence_failure"),
        ("persist", "artifact_persistence_failure"),
        ("database", "artifact_persistence_failure"),
    ],
)
def test_failure_is_terminal_without_artifact(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, category: str
) -> None:
    from sqlalchemy import event, select
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session

    from app.db.models import SegmentationArtifact
    from app.services.inference.worker import InferenceWorker

    case_id = import_case(client, tmp_path)["id"]
    provider = "nnunet" if failure == "unavailable" else "demo"
    queued = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": provider}
    ).json()

    class BrokenProvider(DemoSegmentationProvider):
        def segment(self, case, output_path):
            if failure == "runtime":
                raise RuntimeError("model exploded")
            result = super().segment(case, output_path)
            if failure == "metadata":
                result.configuration["invalid"] = object()
            if failure == "unreadable":
                output_path.write_bytes(b"not a NIfTI")
            else:
                data = np.zeros((8, 8, 8), dtype=np.uint8)
                affine = np.eye(4)
                dtype = np.uint8
                if failure == "shape":
                    data = np.zeros((4, 4, 4), dtype=np.uint8)
                elif failure == "affine":
                    affine[0, 3] = 1.0
                elif failure == "affine_tolerance":
                    affine[0, 3] = 5e-5
                elif failure in {"dtype", "nonfinite"}:
                    dtype = np.float32
                    data = data.astype(dtype)
                    if failure == "nonfinite":
                        data[0, 0, 0] = np.nan
                elif failure == "nonbinary":
                    data[0, 0, 0] = 2
                save_volume(output_path, data, affine, dtype=dtype)
            return result

    if failure in {
        "runtime",
        "shape",
        "affine",
        "affine_tolerance",
        "dtype",
        "nonbinary",
        "nonfinite",
        "unreadable",
        "metadata",
    }:
        monkeypatch.setattr(
            "app.services.inference.worker.get_provider", lambda _: BrokenProvider()
        )
    if failure in {"source_changed", "source_missing"}:
        source = settings.data_dir / "cases" / case_id / "source" / "dwi.nii.gz"
        if failure == "source_changed":
            save_volume(source, np.ones((8, 8, 8)), np.eye(4))
        else:
            source.unlink()
    if failure == "provenance":
        with new_session() as session:
            job = session.get(InferenceJob, queued["id"])
            job.provenance_json = "{invalid"
            session.commit()
    if failure == "persist":
        def fail_move(*_args):
            raise OSError("disk failure")

        monkeypatch.setattr("app.services.inference.worker.os.replace", fail_move)

    def fail_artifact_commit(session, _flush_context, _instances):
        if any(isinstance(item, SegmentationArtifact) for item in session.new):
            raise SQLAlchemyError("database failure")

    if failure == "database":
        event.listen(Session, "before_flush", fail_artifact_commit)
    try:
        assert InferenceWorker().run_once() is True
    finally:
        if failure == "database":
            event.remove(Session, "before_flush", fail_artifact_commit)
    done = client.get(f"/api/inference-jobs/{queued['id']}").json()
    assert done["status"] == "failed"
    assert done["failure_category"] == category
    assert done["error_message"]
    assert done["completed_at"]
    assert done["segmentation_id"] is None
    if category == "invalid_model_output":
        assert done["provenance"]["configuration"]["input_modalities"] == ["DWI"]
        assert done["provenance"]["runtime"]["device"] == "cpu"
    with new_session() as session:
        assert session.scalar(select(SegmentationArtifact)) is None
    assert not list((settings.data_dir / "inference").rglob("*.nii.gz"))
    assert InferenceWorker().run_once() is False
