from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import SourceArtifact
from app.db.session import new_session
from app.services.nifti_codec import save_volume


@pytest.fixture
def sample_nifti_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "sample.nii.gz"
    save_volume(path, np.zeros((6, 7, 8), dtype=np.int16), np.eye(4), dtype=np.int16)
    return path.read_bytes()


def test_case_creation_imports_immutable_source_triad(
    client,
    tmp_path: Path,
) -> None:
    paths: dict[str, Path] = {}
    geometries = {
        "dwi": ((6, 7, 8), (1.0, 1.0, 2.0)),
        "adc": ((5, 6, 7), (1.2, 1.2, 3.0)),
        "flair": ((9, 8, 7), (0.8, 0.8, 1.5)),
    }
    for modality, (shape, spacing) in geometries.items():
        path = tmp_path / f"patient-provided-{modality}.nii.gz"
        save_volume(
            path,
            np.ones(shape, dtype=np.int16),
            np.diag((*spacing, 1.0)),
            dtype=np.int16,
        )
        paths[modality] = path

    response = client.post(
        "/api/cases",
        data={"name": "Case A"},
        files={
            modality: (path.name, path.read_bytes(), "application/gzip")
            for modality, path in paths.items()
        },
    )

    assert response.status_code == 201, response.text
    case_id = response.json()["id"]
    assert response.json()["ready_for_inference"] is True
    assert response.json()["modalities"] == ["ADC", "DWI", "FLAIR"]

    with new_session() as session:
        artifacts = list(
            session.scalars(
                select(SourceArtifact)
                .where(SourceArtifact.case_id == case_id)
                .order_by(SourceArtifact.modality)
            )
        )

    assert [artifact.modality for artifact in artifacts] == ["ADC", "DWI", "FLAIR"]
    for artifact in artifacts:
        upload_key = artifact.modality.lower()
        original = paths[upload_key]
        expected_relative_path = f"cases/{case_id}/source/{upload_key}.nii.gz"
        assert artifact.original_filename == original.name
        assert artifact.relative_path == expected_relative_path
        assert artifact.sha256 == hashlib.sha256(original.read_bytes()).hexdigest()
        assert artifact.file_size == original.stat().st_size
        assert artifact.datatype == "int16"
        assert (settings.data_dir / expected_relative_path).read_bytes() == original.read_bytes()


def test_case_creation_rolls_back_if_flair_is_invalid(
    client,
    sample_nifti_bytes: bytes,
) -> None:
    response = client.post(
        "/api/cases",
        data={"name": "Case A"},
        files={
            "dwi": ("dwi.nii.gz", sample_nifti_bytes, "application/gzip"),
            "adc": ("adc.nii.gz", sample_nifti_bytes, "application/gzip"),
            "flair": ("flair.nii.gz", b"invalid", "application/gzip"),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_nifti"
    assert client.get("/api/cases").json() == []
    assert not list((settings.data_dir / "cases").glob("*"))
    assert not list((settings.data_dir / ".staging").glob("*"))


def test_case_creation_normalizes_uncompressed_nifti_to_gzip(
    client,
    tmp_path: Path,
) -> None:
    source = tmp_path / "dwi.nii"
    save_volume(source, np.ones((4, 5, 6), dtype=np.float32), np.eye(4))
    source_bytes = source.read_bytes()

    response = client.post(
        "/api/cases",
        data={"name": "Uncompressed inputs"},
        files={
            modality: (f"{modality}.nii", source_bytes, "application/octet-stream")
            for modality in ("dwi", "adc", "flair")
        },
    )

    assert response.status_code == 201, response.text
    case_id = response.json()["id"]
    managed = settings.data_dir / "cases" / case_id / "source" / "dwi.nii.gz"
    assert managed.read_bytes().startswith(b"\x1f\x8b")
    assert client.get(f"/api/cases/{case_id}/modalities/DWI/file.nii.gz").status_code == 200


def test_case_creation_cleans_final_directory_if_atomic_move_fails(
    client,
    sample_nifti_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_replace = os.replace

    def fail_adc_move(source: Path, destination: Path) -> None:
        destination_path = Path(destination)
        if destination_path.parent.name == "source" and destination_path.name == "adc.nii.gz":
            raise OSError("simulated storage failure")
        real_replace(source, destination)

    monkeypatch.setattr("app.services.cases.os.replace", fail_adc_move)

    with pytest.raises(OSError, match="simulated storage failure"):
        client.post(
            "/api/cases",
            data={"name": "Case A"},
            files={
                modality: (f"{modality}.nii.gz", sample_nifti_bytes, "application/gzip")
                for modality in ("dwi", "adc", "flair")
            },
        )

    assert client.get("/api/cases").json() == []
    assert not list((settings.data_dir / "cases").glob("*"))
    assert not list((settings.data_dir / ".staging").glob("*"))
