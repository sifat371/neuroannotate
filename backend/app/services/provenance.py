"""Build portable, schema-validated provenance for immutable exports."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath

from jsonschema import Draft202012Validator, FormatChecker

from app.core.errors import ApiError
from app.db.models import (
    AnnotationRevision,
    Case,
    ExportArtifact,
    InferenceJob,
    SegmentationArtifact,
    SourceArtifact,
)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "provenance_schema_v1.json"
)
_DISCLAIMER = "Research software only. Not for diagnosis or clinical decision-making."


def _assert_portable(value: object) -> None:
    """Reject nested identifiers or values that can disclose host-local information."""
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key.lower() == "original_filename":
                raise ApiError(
                    409,
                    "invalid_provenance",
                    "Portable provenance cannot include original filenames",
                )
            _assert_portable(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_portable(nested_value)
    elif isinstance(value, str) and (
        value.startswith("/") or PureWindowsPath(value).is_absolute()
    ):
        raise ApiError(
            409, "invalid_provenance", "Portable provenance cannot include absolute paths"
        )


def _timestamp(value: datetime | None, field: str) -> str:
    """Return a canonical UTC timestamp or reject missing export metadata."""
    if value is None:
        raise ApiError(409, "incomplete_provenance", f"Missing {field} metadata")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_value(value: str, field: str) -> object:
    """Parse persisted JSON without allowing incomplete provenance."""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ApiError(409, "incomplete_provenance", f"Invalid {field} metadata") from exc
    return decoded


def _json_object(value: str, field: str) -> dict[str, object]:
    """Parse a persisted JSON object without allowing incomplete provenance."""
    decoded = _json_value(value, field)
    if not isinstance(decoded, dict):
        raise ApiError(409, "incomplete_provenance", f"Invalid {field} metadata")
    return decoded


def _hash(value: str | None, field: str) -> str:
    """Return a required digest, rejecting migrated records without one."""
    if value is None:
        raise ApiError(409, "incomplete_provenance", f"Missing {field} checksum")
    return value


def _geometry(
    *,
    artifact_id: str,
    sha256: str | None,
    shape: tuple[int, int, int],
    spacing: tuple[float, float, float],
    datatype: str | None,
    affine_json: str,
    field: str,
) -> dict[str, object]:
    """Serialize portable artifact identity and geometry."""
    if datatype is None:
        raise ApiError(409, "incomplete_provenance", f"Missing {field} datatype")
    return {
        "artifact_id": artifact_id,
        "sha256": _hash(sha256, field),
        "shape": list(shape),
        "spacing": list(spacing),
        "datatype": datatype,
        "affine": _json_value(affine_json, f"{field} affine"),
    }


def build_provenance(
    *,
    case: Case,
    sources: list[SourceArtifact],
    job: InferenceJob,
    segmentation: SegmentationArtifact,
    revision: AnnotationRevision,
    export: ExportArtifact,
    software: dict[str, object],
    lineage: list[str] | None = None,
) -> dict[str, object]:
    """Build the portable provenance document for one immutable export snapshot."""
    by_modality = {source.modality: source for source in sources}
    if set(by_modality) != {"DWI", "ADC", "FLAIR"}:
        raise ApiError(409, "incomplete_provenance", "The complete source triad is required")
    source_document = {
        modality: _geometry(
            artifact_id=source.id,
            sha256=source.sha256,
            shape=(source.shape_x, source.shape_y, source.shape_z),
            spacing=(source.spacing_x, source.spacing_y, source.spacing_z),
            datatype=source.datatype,
            affine_json=source.affine_json,
            field=f"{modality} source",
        )
        for modality, source in sorted(by_modality.items())
    }
    job_provenance = _json_object(job.provenance_json, "inference provenance")
    configuration = job_provenance.get("configuration")
    runtime = job_provenance.get("runtime")
    if not isinstance(configuration, dict) or not isinstance(runtime, dict):
        raise ApiError(
            409, "incomplete_provenance", "Inference configuration or runtime is missing"
        )
    segmentation_document = _geometry(
        artifact_id=segmentation.id,
        sha256=segmentation.sha256,
        shape=(segmentation.shape_x, segmentation.shape_y, segmentation.shape_z),
        spacing=(segmentation.spacing_x, segmentation.spacing_y, segmentation.spacing_z),
        datatype=segmentation.datatype,
        affine_json=segmentation.affine_json,
        field="segmentation",
    )
    document: dict[str, object] = {
        "schema": "neuroannotate.provenance",
        "schema_version": "1.0",
        "software": software,
        "export": {
            "export_id": export.id,
            "created_at": _timestamp(export.created_at, "export creation"),
        },
        "case": {"case_id": case.id, "annotation_space": "DWI"},
        "sources": source_document,
        "ai_segmentation": {
            "artifact_id": segmentation_document["artifact_id"],
            "sha256": segmentation_document["sha256"],
            "inference_job_id": job.id,
            "provider": job.provider,
            "model_name": job.model_name,
            "model_version": job.model_version,
            "service_version": job.service_version,
            "timestamps": {
                "created_at": _timestamp(job.created_at, "inference creation"),
                "started_at": _timestamp(job.started_at, "inference start"),
                "completed_at": _timestamp(job.completed_at, "inference completion"),
            },
            "configuration": configuration,
            "runtime": runtime,
        },
        "annotation": {
            "revision_id": revision.id,
            "parent_revision_id": revision.parent_revision_id,
            "created_at": _timestamp(revision.created_at, "revision creation"),
            "note": revision.note,
            "lineage": lineage if lineage is not None else [revision.id],
            "edit_summary": _json_object(revision.edit_stats_json, "revision edit summary"),
        },
        "output": {
            "filename": "lesion-mask.nii.gz",
            "sha256": _hash(export.mask_sha256, "export mask"),
            "datatype": "uint8",
            "label_map": {"0": "background", "1": "lesion"},
            "shape": [
                by_modality["DWI"].shape_x,
                by_modality["DWI"].shape_y,
                by_modality["DWI"].shape_z,
            ],
            "spacing": [
                by_modality["DWI"].spacing_x,
                by_modality["DWI"].spacing_y,
                by_modality["DWI"].spacing_z,
            ],
            "affine": _json_value(by_modality["DWI"].affine_json, "DWI source affine"),
        },
        "disclaimer": _DISCLAIMER,
    }
    return document


def validate_provenance(document: dict[str, object]) -> None:
    """Validate a document against the committed v1 portable schema."""
    _assert_portable(document)
    schema = _json_object(_SCHEMA_PATH.read_text(encoding="utf-8"), "provenance schema")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        raise ApiError(409, "invalid_provenance", errors[0].message)


def serialize_provenance(document: dict[str, object]) -> bytes:
    """Encode canonical human-readable provenance bytes."""
    return (json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
