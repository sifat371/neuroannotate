from __future__ import annotations

import gzip
import struct
from pathlib import Path

import numpy as np
import pytest

from app.core.errors import ApiError
from app.services.artifacts import validate_source_nifti
from app.services.checksums import sha256_file
from app.services.geometry import same_geometry
from app.services.nifti import NiftiMetadata
from app.services.nifti_codec import save_volume


def write_test_nifti(
    path: Path,
    *,
    shape: tuple[int, int, int] = (8, 8, 4),
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> Path:
    affine = np.diag((*spacing, 1.0))
    return save_volume(path, np.zeros(shape, dtype=np.int16), affine, dtype=np.int16)


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"neuroannotate")

    assert (
        sha256_file(path)
        == "e709fc9c1dc7fd898d8c3de43818e5662be4bd3aa6aa3b6bf32457ae3b3cda91"
    )


def test_source_validation_allows_different_reference_geometry(tmp_path: Path) -> None:
    dwi = write_test_nifti(
        tmp_path / "dwi.nii.gz", shape=(16, 16, 8), spacing=(1.0, 1.0, 2.0)
    )
    flair = write_test_nifti(
        tmp_path / "flair.nii.gz", shape=(20, 20, 10), spacing=(1.2, 1.2, 3.0)
    )

    dwi_metadata = validate_source_nifti(dwi)
    flair_metadata = validate_source_nifti(flair)

    assert dwi_metadata.shape == (16, 16, 8)
    assert flair_metadata.shape == (20, 20, 10)
    assert dwi_metadata.datatype == "int16"
    assert dwi_metadata.file_size == dwi.stat().st_size


def test_source_validation_rejects_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "invalid.nii.gz"
    path.write_bytes(b"not a nifti")

    with pytest.raises(ApiError, match="Invalid NIfTI file") as exc_info:
        validate_source_nifti(path)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_nifti"


def test_source_validation_rejects_zero_dimension(tmp_path: Path) -> None:
    path = write_test_nifti(tmp_path / "zero.nii.gz")
    with gzip.open(path, "rb") as file_handle:
        payload = bytearray(file_handle.read())
    struct.pack_into("<h", payload, 42, 0)
    with gzip.open(path, "wb") as file_handle:
        file_handle.write(payload)

    with pytest.raises(ApiError) as exc_info:
        validate_source_nifti(path)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_nifti"


def test_same_geometry_requires_exact_shape_and_close_affine() -> None:
    base = NiftiMetadata(
        shape=(8, 8, 4),
        spacing=(1.0, 1.0, 2.0),
        affine=np.eye(4).tolist(),
        datatype="float32",
        file_size=100,
    )
    close = NiftiMetadata(
        shape=(8, 8, 4),
        spacing=(1.0, 1.0, 2.0),
        affine=(np.eye(4) + np.diag([1e-6, 0.0, 0.0, 0.0])).tolist(),
        datatype="float32",
        file_size=200,
    )
    different_shape = NiftiMetadata(
        shape=(9, 8, 4),
        spacing=(1.0, 1.0, 2.0),
        affine=np.eye(4).tolist(),
        datatype="float32",
        file_size=100,
    )

    assert same_geometry(base, close)
    assert not same_geometry(base, different_shape)
