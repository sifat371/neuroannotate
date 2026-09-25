from __future__ import annotations

from app.services.inference.worker import InferenceWorker
from tests.helpers import import_case


def test_segmentation_metrics_reports_candidate_volume(client, tmp_path):
    case = import_case(client, tmp_path, name="Volume case")
    queued = client.post(
        f"/api/cases/{case['id']}/inference-jobs",
        json={"provider": "demo"},
    )
    assert queued.status_code == 202, queued.text

    assert InferenceWorker().run_once() is True
    job = client.get(f"/api/inference-jobs/{queued.json()['id']}").json()
    assert job["status"] == "completed"
    assert job["segmentation_id"]

    response = client.get(
        f"/api/segmentations/{job['segmentation_id']}/metrics"
    )
    assert response.status_code == 200, response.text
    metrics = response.json()
    assert metrics["lesion_voxels"] == 8 * 8 * 8
    assert metrics["lesion_volume_ml"] == 0.512
