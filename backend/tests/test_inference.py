import numpy as np

from app.services.nifti_codec import load_volume
from tests.helpers import create_case, upload_case_modalities


def test_incomplete_case_rejected(client):
    case_id = create_case(client)["id"]
    response = client.post(f"/api/cases/{case_id}/segment")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "case_not_ready"


def test_demo_inference_is_deterministic_and_downloadable(client, tmp_path):
    case_id = create_case(client)["id"]
    upload_case_modalities(client, tmp_path, case_id, (12, 12, 12))

    first_run = client.post(f"/api/cases/{case_id}/segment")
    assert first_run.status_code == 201
    first_file = client.get(f"/api/cases/{case_id}/segmentations/latest/file.nii.gz")
    assert first_file.status_code == 200
    first_path = tmp_path / "m1.nii.gz"
    first_path.write_bytes(first_file.content)
    first_volume = load_volume(first_path)
    first_array = first_volume.data

    second_run = client.post(f"/api/cases/{case_id}/segment")
    assert second_run.status_code == 201
    second_file = client.get(f"/api/cases/{case_id}/segmentations/latest/file.nii.gz")
    second_path = tmp_path / "m2.nii.gz"
    second_path.write_bytes(second_file.content)
    second_array = load_volume(second_path).data

    np.testing.assert_array_equal(first_array, second_array)
    assert first_volume.data.shape == (12, 12, 12)
    assert set(np.unique(first_array)).issubset({0, 1})
    assert second_run.json()["provider"] == "demo"
