import json

import numpy as np

from app.services.nifti_codec import load_volume
from tests.helpers import create_case, upload_case_modalities


def prepare(client, tmp_path, shape=(3, 4, 2)):
    case_id = create_case(client)["id"]
    upload_case_modalities(client, tmp_path, case_id, shape)
    run = client.post(f"/api/cases/{case_id}/segment").json()
    return case_id, run


def test_revision_round_trip_is_immutable_and_exportable(client, tmp_path):
    shape = (3, 4, 2)
    case_id, run = prepare(client, tmp_path, shape)
    mask = np.zeros(shape, dtype=np.uint8)
    mask[0, 0, 0] = 1
    mask[2, 3, 1] = 1
    payload = mask.reshape(-1, order="F").tobytes()

    def save(note):
        return client.post(
            f"/api/cases/{case_id}/revisions",
            files={
                "voxels": (
                    "labelmap.bin",
                    payload,
                    "application/octet-stream",
                )
            },
            data={
                "shape": json.dumps(shape),
                "source_inference_id": run["id"],
                "note": note,
            },
        )

    first = save("first")
    assert first.status_code == 201
    second = save("second")
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]

    revision_file = client.get(
        f"/api/cases/{case_id}/revisions/{first.json()['id']}/file"
    )
    revision_path = tmp_path / "rev.nii.gz"
    revision_path.write_bytes(revision_file.content)
    array = load_volume(revision_path).data
    assert array[0, 0, 0] == 1
    assert array[2, 3, 1] == 1
    assert array.sum() == 2

    listed = client.get(f"/api/cases/{case_id}/revisions").json()
    assert listed[0]["note"] == "second"

    exported = client.get(
        f"/api/cases/{case_id}/export",
        params={"revision_id": first.json()["id"]},
    )
    assert exported.status_code == 200


def test_revision_validation(client, tmp_path):
    shape = (3, 4, 2)
    case_id, run = prepare(client, tmp_path, shape)
    response = client.post(
        f"/api/cases/{case_id}/revisions",
        files={"voxels": ("x.bin", b"123", "application/octet-stream")},
        data={"shape": json.dumps(shape), "source_inference_id": run["id"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_labelmap_buffer"
