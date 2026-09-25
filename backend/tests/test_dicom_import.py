from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest

from app.core.errors import ApiError
from app.services.dicom_import import (
    DicomSeries,
    _safe_extract_zip,
    score_series,
    select_required_series,
)
from app.services.nifti_codec import save_volume


def sample_series() -> list[DicomSeries]:
    return [
        DicomSeries(
            uid="dwi",
            description="DWI",
            image_type=r"DERIVED\PRIMARY\DIFFUSION\TRACEW",
            files=[Path("dwi.dcm")],
        ),
        DicomSeries(
            uid="adc",
            description="resolve_3scan_trace_tra_ADC",
            image_type=r"DERIVED\PRIMARY\DIFFUSION\ADC",
            files=[Path("adc.dcm")],
        ),
        DicomSeries(
            uid="flair",
            description="t2_tse_dark-fluid_tra",
            protocol="t2_tse_dark-fluid_tra",
            files=[Path("flair.dcm")],
        ),
        DicomSeries(
            uid="t1-dark-fluid",
            description="t1_tirm_tra_dark-fluid",
            protocol="t1_tirm_tra_dark-fluid",
            files=[Path("t1.dcm")],
        ),
    ]


def test_select_required_series_matches_hospital_naming_patterns() -> None:
    selected = select_required_series(sample_series())

    assert selected["DWI"].uid == "dwi"
    assert selected["ADC"].uid == "adc"
    assert selected["FLAIR"].uid == "flair"
    assert score_series(selected["FLAIR"], "FLAIR") > score_series(
        sample_series()[3],
        "FLAIR",
    )


def test_select_required_series_rejects_tied_candidates() -> None:
    series = sample_series()
    series.append(
        DicomSeries(
            uid="second-dwi",
            description="DWI",
            image_type=r"DERIVED\PRIMARY\DIFFUSION\TRACEW",
            files=[Path("second.dcm")],
        )
    )

    with pytest.raises(ApiError) as exc:
        select_required_series(series)

    assert exc.value.code == "ambiguous_required_series"


def test_safe_extract_rejects_zip_slip(tmp_path: Path) -> None:
    archive_path = tmp_path / "study.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../patient.txt", "unsafe")

    with pytest.raises(ApiError) as exc:
        _safe_extract_zip(archive_path, tmp_path / "out")

    assert exc.value.code == "unsafe_dicom_archive"


def test_dicom_endpoint_converts_selected_series_into_existing_case_pipeline(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "converted.nii.gz"
    save_volume(source, np.ones((6, 7, 8), dtype=np.int16), np.eye(4), dtype=np.int16)

    monkeypatch.setattr(
        "app.services.dicom_import.discover_mr_series",
        lambda _root: sample_series(),
    )

    def fake_convert(_series: DicomSeries, modality: str, work_dir: Path) -> Path:
        output = work_dir / f"{modality.lower()}.nii.gz"
        output.write_bytes(source.read_bytes())
        return output

    monkeypatch.setattr("app.services.dicom_import._convert_series", fake_convert)

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("DICOM/fake", b"placeholder")

    response = client.post(
        "/api/cases/dicom",
        data={"name": "Pilot stroke 001"},
        files={"study": ("study.zip", payload.getvalue(), "application/zip")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Pilot stroke 001"
    assert body["modalities"] == ["ADC", "DWI", "FLAIR"]
    assert body["ready_for_inference"] is True
    assert [source["original_filename"] for source in body["sources"]] == [
        "adc.nii.gz",
        "dwi.nii.gz",
        "flair.nii.gz",
    ]
