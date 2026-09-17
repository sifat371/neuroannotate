from pathlib import Path

import numpy as np
import pytest

from app.services import nifti_codec
from app.services.nifti import inspect_nifti


@pytest.mark.parametrize(
    ("filename", "datatype", "expected"),
    [
        pytest.param("source-int16.nii.gz", np.int16, "int16", id="integer-source"),
        pytest.param("mask-uint8.nii.gz", np.uint8, "uint8", id="uint8-mask"),
    ],
)
def test_inspect_nifti_reports_stored_datatype(
    tmp_path: Path,
    filename: str,
    datatype: type[np.generic],
    expected: str,
) -> None:
    path = tmp_path / filename
    nifti_codec.save_volume(
        path,
        np.ones((2, 3, 4), dtype=datatype),
        np.eye(4),
        dtype=datatype,
    )

    assert inspect_nifti(path).datatype == expected


def test_fallback_reader_reports_stored_datatype(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "source-int16.nii.gz"
    nifti_codec.save_volume(
        path,
        np.ones((2, 3, 4), dtype=np.int16),
        np.eye(4),
        dtype=np.int16,
    )
    monkeypatch.setattr(nifti_codec, "nib", None)

    volume = nifti_codec.load_volume(path)

    assert volume.datatype == "int16"
    assert volume.data.dtype == np.float32
