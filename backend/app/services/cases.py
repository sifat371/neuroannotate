from __future__ import annotations

import gzip
import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import Case, SourceArtifact, new_uuid
from app.repositories.cases import CaseRepository
from app.services.artifacts import validate_source_nifti
from app.services.checksums import sha256_file
from app.services.nifti import NiftiMetadata
from app.services.storage import Storage

REQUIRED_MODALITIES = {"DWI", "ADC", "FLAIR"}


def is_ready_for_inference(modalities: set[str]) -> bool:
    return modalities == REQUIRED_MODALITIES


def case_to_dict(case: Case) -> dict[str, object]:
    modalities = sorted(artifact.modality for artifact in case.source_artifacts)
    return {
        "id": case.id,
        "name": case.name,
        "created_at": case.created_at,
        "modalities": modalities,
        "ready_for_inference": is_ready_for_inference(set(modalities)),
    }


def case_to_detail(case: Case) -> dict[str, object]:
    """Serialize a case with its immutable source artifact metadata."""
    summary = case_to_dict(case)
    summary.update(
        {
            "annotation_space": "DWI",
            "sources": sorted(
                (
                    {
                        "id": artifact.id,
                        "modality": artifact.modality,
                        "original_filename": artifact.original_filename,
                        "relative_path": artifact.relative_path,
                        "sha256": artifact.sha256,
                        "file_size": artifact.file_size,
                        "shape": (
                            artifact.shape_x,
                            artifact.shape_y,
                            artifact.shape_z,
                        ),
                        "spacing": (
                            artifact.spacing_x,
                            artifact.spacing_y,
                            artifact.spacing_z,
                        ),
                        "affine": json.loads(artifact.affine_json),
                        "datatype": artifact.datatype,
                        "created_at": artifact.created_at,
                    }
                    for artifact in case.source_artifacts
                ),
                key=lambda source: str(source["modality"]),
            ),
        }
    )
    return summary


def _stage_upload(upload: UploadFile, staging_dir: Path, modality: str) -> Path:
    incoming_path = staging_dir / f"{modality.lower()}.incoming"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0
    upload.file.seek(0)
    with incoming_path.open("wb") as destination:
        while chunk := upload.file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise ApiError(
                    413,
                    "file_too_large",
                    "Uploaded file exceeds the configured size limit",
                )
            destination.write(chunk)

    with incoming_path.open("rb") as source:
        compressed = source.read(2) == b"\x1f\x8b"
    staged_path = staging_dir / f"{modality.lower()}.nii{'.gz' if compressed else ''}"
    os.replace(incoming_path, staged_path)
    return staged_path


def _normalize_compression(path: Path) -> Path:
    if path.suffix == ".gz":
        return path

    compressed_path = path.with_suffix(f"{path.suffix}.gz")
    with (
        path.open("rb") as source,
        compressed_path.open("wb") as compressed_file,
        gzip.GzipFile(fileobj=compressed_file, mode="wb", mtime=0) as target,
    ):
        shutil.copyfileobj(source, target)
    path.unlink()
    return compressed_path


def _source_artifact(
    *,
    case_id: str,
    modality: str,
    original_filename: str,
    relative_path: str,
    metadata: NiftiMetadata,
    sha256: str,
) -> SourceArtifact:
    return SourceArtifact(
        case_id=case_id,
        modality=modality,
        original_filename=original_filename,
        relative_path=relative_path,
        sha256=sha256,
        file_size=metadata.file_size,
        shape_x=metadata.shape[0],
        shape_y=metadata.shape[1],
        shape_z=metadata.shape[2],
        spacing_x=metadata.spacing[0],
        spacing_y=metadata.spacing[1],
        spacing_z=metadata.spacing[2],
        affine_json=json.dumps(metadata.affine),
        datatype=metadata.datatype,
    )


def import_case_triad(
    session: Session,
    storage: Storage,
    name: str,
    uploads: dict[str, UploadFile],
) -> Case:
    """Atomically import one immutable DWI/ADC/FLAIR source triad."""
    if set(uploads) != REQUIRED_MODALITIES:
        raise ApiError(
            422,
            "invalid_source_triad",
            "A case requires exactly one DWI, ADC, and FLAIR source",
        )

    import_id = str(uuid.uuid4())
    case_id = new_uuid()
    staging_dir = storage.staging_dir(import_id)
    final_case_dir = storage.root / "cases" / case_id
    moved_to_final = False
    try:
        staged: dict[str, tuple[Path, NiftiMetadata, str]] = {}
        for modality in ("DWI", "ADC", "FLAIR"):
            staged_path = _stage_upload(uploads[modality], staging_dir, modality)
            validate_source_nifti(staged_path)
            staged_path = _normalize_compression(staged_path)
            metadata = validate_source_nifti(staged_path)
            staged[modality] = (
                staged_path,
                metadata,
                sha256_file(staged_path),
            )

        storage.source_dir(case_id)
        for modality, (staged_path, _metadata, _digest) in staged.items():
            os.replace(staged_path, storage.source_path(case_id, modality))
        moved_to_final = True

        artifacts = [
            _source_artifact(
                case_id=case_id,
                modality=modality,
                original_filename=uploads[modality].filename
                or f"{modality.lower()}.nii.gz",
                relative_path=storage.relative(storage.source_path(case_id, modality)),
                metadata=metadata,
                sha256=digest,
            )
            for modality, (_path, metadata, digest) in staged.items()
        ]
        case = Case(id=case_id, name=name)
        return CaseRepository(session).add_imported_case(case, artifacts)
    except Exception:
        session.rollback()
        if moved_to_final or final_case_dir.exists():
            shutil.rmtree(final_case_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


def require_case(repo: CaseRepository, case_id: str) -> Case:
    case = repo.get(case_id)
    if not case:
        raise ApiError(404, "case_not_found", "Case not found")
    return case
