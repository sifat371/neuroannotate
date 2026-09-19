import json
import os
import time
from datetime import UTC, datetime

import pytest

from app.core.errors import ApiError
from app.core.release import RELEASE_VERSION
from app.db.models import (
    AnnotationRevision,
    Case,
    ExportArtifact,
    InferenceJob,
    SegmentationArtifact,
    SourceArtifact,
)
from app.services.provenance import _timestamp, build_provenance, validate_provenance


def _source(modality: str) -> SourceArtifact:
    return SourceArtifact(
        id=f"{modality.lower()}-id",
        case_id="case-id",
        modality=modality,
        original_filename="patient-name.nii.gz",
        relative_path=f"cases/case-id/source/{modality.lower()}.nii.gz",
        sha256="a" * 64,
        file_size=1,
        shape_x=2,
        shape_y=3,
        shape_z=4,
        spacing_x=1.0,
        spacing_y=1.5,
        spacing_z=2.0,
        affine_json="[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]",
        datatype="float32",
    )


@pytest.fixture
def provenance() -> dict[str, object]:
    timestamp = datetime(2026, 9, 18, tzinfo=UTC)
    case = Case(id="case-id", name="private patient", created_at=timestamp)
    job = InferenceJob(
        id="job-id",
        case_id=case.id,
        provider="demo",
        model_name="model",
        model_version="1",
        service_version="2",
        status="completed",
        created_at=timestamp,
        started_at=timestamp,
        completed_at=timestamp,
        provenance_json='{"configuration":{"threshold":1},"runtime":{"device":"cpu"}}',
    )
    segmentation = SegmentationArtifact(
        id="segmentation-id",
        case_id=case.id,
        inference_job_id=job.id,
        relative_path="inference/job-id/segmentation.nii.gz",
        sha256="b" * 64,
        shape_x=2,
        shape_y=3,
        shape_z=4,
        spacing_x=1.0,
        spacing_y=1.5,
        spacing_z=2.0,
        affine_json="[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]",
        datatype="uint8",
        created_at=timestamp,
    )
    revision = AnnotationRevision(
        id="revision-id",
        case_id=case.id,
        source_segmentation_id=segmentation.id,
        relative_path="cases/case-id/revisions/revision-id.nii.gz",
        sha256="c" * 64,
        note="reviewed",
        edit_stats_json="{\"added_voxels\": 2}",
        created_at=timestamp,
    )
    export = ExportArtifact(
        id="export-id",
        case_id=case.id,
        revision_id=revision.id,
        mask_path="exports/export-id/lesion-mask.nii.gz",
        provenance_path="exports/export-id/provenance.json",
        mask_sha256="c" * 64,
        created_at=timestamp,
    )
    return build_provenance(
        case=case,
        sources=[_source("DWI"), _source("ADC"), _source("FLAIR")],
        job=job,
        segmentation=segmentation,
        revision=revision,
        export=export,
        software={"name": "NeuroAnnotate", "version": RELEASE_VERSION, "git_commit": None},
        lineage=[revision.id],
    )


def test_provenance_is_portable_and_has_required_sections(provenance: dict[str, object]) -> None:
    """Removing the portable document fields should make this contract fail."""
    assert provenance["schema"] == "neuroannotate.provenance"
    assert provenance["schema_version"] == "1.0"
    assert provenance["software"]["version"] == RELEASE_VERSION
    assert provenance["case"] == {"case_id": "case-id", "annotation_space": "DWI"}
    assert set(provenance["sources"]) == {"DWI", "ADC", "FLAIR"}
    assert provenance["output"]["label_map"] == {"0": "background", "1": "lesion"}
    text = json.dumps(provenance)
    assert "/home/" not in text
    assert "original_filename" not in text
    assert "patient-name.nii.gz" not in text


@pytest.mark.parametrize(
    "leak",
    [
        {"nested": {"original_filename": "patient-name.nii.gz"}},
        {"nested": {"working_directory": "/home/researcher/private"}},
    ],
)
def test_provenance_rejects_nested_portability_leaks(
    provenance: dict[str, object], leak: dict[str, object]
) -> None:
    """Passing nested private metadata through configuration would disclose it."""
    provenance["ai_segmentation"]["runtime"] = {"device": "cuda:0", **leak}

    with pytest.raises(ApiError) as raised:
        validate_provenance(provenance)

    assert raised.value.code == "invalid_provenance"


def test_naive_persisted_timestamp_is_interpreted_as_utc_under_non_utc_process_timezone() -> None:
    """Using local timezone conversion would shift naive SQLite timestamps."""
    previous_timezone = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Dhaka"
    time.tzset()
    try:
        rendered = _timestamp(datetime(2026, 9, 18, 12, 30), "test timestamp")
    finally:
        if previous_timezone is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous_timezone
        time.tzset()

    assert rendered == "2026-09-18T12:30:00Z"
