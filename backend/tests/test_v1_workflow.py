from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app.core.errors import ApiError
from app.scripts.generate_demo_data import generate_demo_case
from app.scripts.seed_demo_case import seed_demo_case
from app.services.inference.worker import InferenceWorker
from app.services.nifti_codec import load_volume


@pytest.fixture
def worker() -> InferenceWorker:
    return InferenceWorker()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_seed_demo_case_does_not_leave_a_partial_case(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt generated modality must not leave a seeded case or source directory."""
    generated = generate_demo_case(tmp_path / "invalid-seed")
    generated["FLAIR"].write_bytes(b"not a NIfTI file")
    monkeypatch.setattr(
        "app.scripts.seed_demo_case.generate_demo_case",
        lambda _output_dir: generated,
    )

    with pytest.raises(ApiError, match="Invalid NIfTI file"):
        seed_demo_case()

    assert client.get("/api/cases").json() == []


def test_demo_path_reaches_reproducible_export(
    client, worker: InferenceWorker, tmp_path: Path
) -> None:
    """Breaking any v1 handoff must fail the complete deterministic demo path."""
    first = generate_demo_case(tmp_path / "generated-a")
    second = generate_demo_case(tmp_path / "generated-b")
    assert set(first) == {"DWI", "ADC", "FLAIR", "MASK"}
    assert set(second) == set(first)
    for artifact in first:
        assert first[artifact].read_bytes() == second[artifact].read_bytes()

    response = client.post(
        "/api/cases",
        data={"name": "Synthetic v1 workflow"},
        files={
            modality.lower(): (
                first[modality].name,
                first[modality].read_bytes(),
                "application/gzip",
            )
            for modality in ("DWI", "ADC", "FLAIR")
        },
    )
    assert response.status_code == 201, response.text
    case = response.json()
    assert case["annotation_space"] == "DWI"
    assert case["ready_for_inference"] is True

    sources = {source["modality"]: source for source in case["sources"]}
    expected_affine = [
        [1.5, 0.0, 0.0, -48.0],
        [0.0, 1.5, 0.0, -48.0],
        [0.0, 0.0, 2.0, -48.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    for modality in ("DWI", "ADC", "FLAIR"):
        source = sources[modality]
        payload = first[modality].read_bytes()
        assert source["sha256"] == _sha256(payload)
        assert source["file_size"] == len(payload)
        assert source["shape"] == [64, 64, 48]
        assert source["spacing"] == [1.5, 1.5, 2.0]
        assert source["affine"] == expected_affine
        assert source["datatype"] == "float32"

    queued_response = client.post(
        f"/api/cases/{case['id']}/inference-jobs",
        json={"provider": "demo"},
    )
    assert queued_response.status_code == 202, queued_response.text
    job = queued_response.json()
    assert job["status"] == "queued"
    assert worker.run_once() is True

    completed_response = client.get(f"/api/inference-jobs/{job['id']}")
    assert completed_response.status_code == 200
    completed = completed_response.json()
    assert completed["status"] == "completed"
    assert completed["segmentation_id"]
    assert completed["provenance"]["configuration"] == {
        "clinical_use": False,
        "dwi_percentile": 92,
        "input_modalities": ["DWI"],
        "minimum_component_voxels": 8,
    }

    segmentation_response = client.get(
        f"/api/segmentations/{completed['segmentation_id']}/file.nii.gz"
    )
    assert segmentation_response.status_code == 200
    segmentation_path = tmp_path / "segmentation.nii.gz"
    segmentation_path.write_bytes(segmentation_response.content)
    segmentation = load_volume(segmentation_path)
    expected_mask = load_volume(first["MASK"])
    np.testing.assert_array_equal(segmentation.data, expected_mask.data)
    np.testing.assert_allclose(segmentation.affine, expected_affine, atol=1e-6, rtol=0)
    assert segmentation.spacing == (1.5, 1.5, 2.0)
    assert segmentation.datatype == "uint8"

    mask = segmentation.data.astype(np.uint8)
    revision_response = client.post(
        f"/api/cases/{case['id']}/revisions",
        files={
            "voxels": (
                "labelmap.bin",
                mask.reshape(-1, order="F").tobytes(),
                "application/octet-stream",
            )
        },
        data={
            "shape": json.dumps(list(mask.shape)),
            "source_segmentation_id": completed["segmentation_id"],
            "note": "Deterministic no-op revision",
        },
    )
    assert revision_response.status_code == 201, revision_response.text
    revision = revision_response.json()
    assert revision["source_segmentation_id"] == completed["segmentation_id"]
    assert revision["edit_stats"] == {
        "added_voxels": 0,
        "removed_voxels": 0,
        "changed_voxels": 0,
        "lesion_voxels": 15728,
        "lesion_volume_ml": 70.776,
    }

    revision_file = client.get(f"/api/revisions/{revision['id']}/file.nii.gz")
    assert revision_file.status_code == 200
    revision_path = tmp_path / "revision.nii.gz"
    revision_path.write_bytes(revision_file.content)
    saved_revision = load_volume(revision_path)
    np.testing.assert_array_equal(saved_revision.data, expected_mask.data)
    np.testing.assert_allclose(saved_revision.affine, expected_affine, atol=1e-6, rtol=0)
    assert saved_revision.spacing == (1.5, 1.5, 2.0)

    export_response = client.post(
        f"/api/cases/{case['id']}/exports",
        json={"revision_id": revision["id"]},
    )
    assert export_response.status_code == 201, export_response.text
    export = export_response.json()
    bundle_response = client.get(export["bundle_url"])
    assert bundle_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle_response.content)) as archive:
        assert set(archive.namelist()) == {"lesion-mask.nii.gz", "provenance.json"}
        exported_mask = archive.read("lesion-mask.nii.gz")
        provenance = json.loads(archive.read("provenance.json"))

    assert exported_mask == revision_file.content
    assert export["mask_sha256"] == revision["sha256"] == _sha256(exported_mask)
    assert provenance["case"] == {"case_id": case["id"], "annotation_space": "DWI"}
    assert provenance["annotation"]["edit_summary"] == revision["edit_stats"]
    assert provenance["annotation"]["lineage"] == [revision["id"]]
    assert provenance["ai_segmentation"]["sha256"] == _sha256(
        segmentation_response.content
    )
    assert provenance["output"]["shape"] == [64, 64, 48]
    assert provenance["output"]["spacing"] == [1.5, 1.5, 2.0]
    assert provenance["output"]["affine"] == expected_affine
    assert {
        modality: provenance["sources"][modality]["sha256"]
        for modality in ("DWI", "ADC", "FLAIR")
    } == {modality: sources[modality]["sha256"] for modality in sources}
