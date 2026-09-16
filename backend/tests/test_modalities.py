import numpy as np

from tests.helpers import create_case, make_nifti


def upload(client, case_id, modality, path):
    with path.open("rb") as file_handle:
        return client.post(
            f"/api/cases/{case_id}/modalities/{modality}",
            files={"file": (path.name, file_handle, "application/octet-stream")},
        )


def test_valid_upload_duplicate_corrupt_and_readiness(client, tmp_path):
    case_id = create_case(client)["id"]
    dwi = make_nifti(tmp_path / "dwi.nii.gz")
    assert upload(client, case_id, "DWI", dwi).status_code == 201
    downloaded = client.get(f"/api/cases/{case_id}/modalities/DWI/file.nii.gz")
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"\x1f\x8b")
    assert upload(client, case_id, "DWI", dwi).status_code == 409

    bad = tmp_path / "bad.nii.gz"
    bad.write_text("not nifti")
    response = upload(client, case_id, "ADC", bad)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_nifti"

    adc = make_nifti(tmp_path / "adc.nii.gz")
    flair = make_nifti(tmp_path / "flair.nii.gz")
    assert upload(client, case_id, "ADC", adc).status_code == 201
    response = upload(client, case_id, "FLAIR", flair)
    assert response.status_code == 201
    assert response.json()["ready_for_inference"] is True


def test_geometry_mismatch_is_rejected(client, tmp_path):
    case_id = create_case(client)["id"]
    dwi = make_nifti(tmp_path / "dwi.nii.gz")
    assert upload(client, case_id, "DWI", dwi).status_code == 201

    affine = np.eye(4)
    affine[0, 3] = 5
    adc = make_nifti(tmp_path / "adc.nii.gz", affine=affine)
    response = upload(client, case_id, "ADC", adc)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "incompatible_geometry"
