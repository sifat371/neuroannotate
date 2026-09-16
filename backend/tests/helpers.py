from pathlib import Path

import numpy as np

from app.services.nifti_codec import save_volume


def make_nifti(
    path: Path,
    shape: tuple[int, int, int] = (8, 8, 8),
    affine=None,
    value: float = 0.0,
):
    affine = np.eye(4) if affine is None else affine
    array = np.full(shape, value, dtype=np.float32)
    save_volume(path, array, affine, dtype=np.float32)
    return path


def create_case(client, name="Case"):
    response = client.post("/api/cases", json={"name": name})
    assert response.status_code == 201
    return response.json()


def upload_case_modalities(
    client,
    tmp_path: Path,
    case_id: str,
    shape: tuple[int, int, int] = (8, 8, 8),
):
    paths = {}
    for modality in ("DWI", "ADC", "FLAIR"):
        path = tmp_path / f"{modality.lower()}.nii.gz"
        array = np.zeros(shape, dtype=np.float32)
        x, y, z = np.indices(shape)
        lesion = (
            (x - shape[0] / 2) ** 2
            + (y - shape[1] / 2) ** 2
            + (z - shape[2] / 2) ** 2
            < 4
        )
        if modality == "DWI":
            array += lesion * 2 + 0.2
        elif modality == "ADC":
            array += (~lesion) * 1.0 + lesion * 0.1
        else:
            array += lesion * 1.2 + 0.3

        save_volume(path, array, np.eye(4), dtype=np.float32)
        paths[modality] = path
        with path.open("rb") as file_handle:
            response = client.post(
                f"/api/cases/{case_id}/modalities/{modality}",
                files={
                    "file": (
                        path.name,
                        file_handle,
                        "application/octet-stream",
                    )
                },
            )
        assert response.status_code == 201, response.text
    return paths
