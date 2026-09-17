from pathlib import Path
from time import monotonic, sleep

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.models import InferenceJob
from app.db.session import configure_database, new_session
from app.main import create_app
from app.services.inference import worker as worker_module
from tests.helpers import import_case


def test_running_jobs_fail_on_backend_restart(client, tmp_path: Path) -> None:
    case_id = import_case(client, tmp_path)["id"]
    with new_session() as session:
        job = InferenceJob(
            case_id=case_id,
            provider="demo",
            model_name="deterministic_demo_threshold",
            model_version="2",
            service_version="0.1.0",
            status="running",
            provenance_json="{}",
        )
        session.add(job)
        session.commit()
        job_id = job.id
    interrupted_output = (
        settings.data_dir / "inference" / job_id / "segmentation.nii.gz"
    )
    interrupted_output.parent.mkdir(parents=True)
    interrupted_output.write_bytes(b"uncommitted output")

    with new_session() as session:
        assert worker_module.recover_interrupted_jobs(session) == 1

    with new_session() as session:
        recovered = session.get(InferenceJob, job_id)
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.failure_category == "application_interrupted"
        assert recovered.error_message == "Interrupted by application restart"
        assert recovered.completed_at is not None
    assert not interrupted_output.exists()


def test_queued_jobs_survive_recovery(client, tmp_path: Path) -> None:
    case_id = import_case(client, tmp_path)["id"]
    queued = client.post(
        f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}
    ).json()

    with new_session() as session:
        assert worker_module.recover_interrupted_jobs(session) == 0

    response = client.get(f"/api/inference-jobs/{queued['id']}")
    assert response.json()["status"] == "queued"


def test_application_lifespan_processes_jobs_and_stops_worker(tmp_path: Path) -> None:
    settings.data_dir = tmp_path / "data"
    settings.sample_data_dir = tmp_path / "sample_data"
    configure_database(f"sqlite:///{tmp_path / 'background.db'}")
    application = create_app(start_worker=True)

    with TestClient(application) as client:
        case_id = import_case(client, tmp_path)["id"]
        queued = client.post(
            f"/api/cases/{case_id}/inference-jobs", json={"provider": "demo"}
        ).json()
        deadline = monotonic() + 3
        job = queued
        while job["status"] in {"queued", "running"} and monotonic() < deadline:
            sleep(0.02)
            job = client.get(f"/api/inference-jobs/{queued['id']}").json()

        assert job["status"] == "completed", job
        worker_thread = application.state.inference_worker_thread
        assert worker_thread.is_alive()

    assert not worker_thread.is_alive()
