from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import AnnotationRevision, SegmentationArtifact, SourceArtifact
from app.services.artifacts import validate_source_nifti
from app.services.checksums import sha256_file
from app.services.nifti import NiftiMetadata, assert_compatible_geometry
from app.services.nifti_codec import load_volume, save_volume
from app.services.storage import Storage


@dataclass(frozen=True)
class RevisionStats:
    added_voxels: int
    removed_voxels: int
    changed_voxels: int
    lesion_voxels: int
    lesion_volume_ml: float


def compute_revision_stats(
    parent: np.ndarray,
    current: np.ndarray,
    voxel_volume_mm3: float,
) -> RevisionStats:
    """Describe binary mask changes from the immediate parent to a revision."""
    parent_mask = np.asarray(parent) > 0
    current_mask = np.asarray(current) > 0
    added_voxels = int(np.count_nonzero(current_mask & ~parent_mask))
    removed_voxels = int(np.count_nonzero(parent_mask & ~current_mask))
    lesion_voxels = int(np.count_nonzero(current_mask))
    return RevisionStats(
        added_voxels=added_voxels,
        removed_voxels=removed_voxels,
        changed_voxels=added_voxels + removed_voxels,
        lesion_voxels=lesion_voxels,
        lesion_volume_ml=lesion_voxels * voxel_volume_mm3 / 1000.0,
    )


def _source_metadata(source: SourceArtifact) -> NiftiMetadata:
    return NiftiMetadata(
        shape=(source.shape_x, source.shape_y, source.shape_z),
        spacing=(source.spacing_x, source.spacing_y, source.spacing_z),
        affine=json.loads(source.affine_json),
        datatype=source.datatype or "unknown",
        file_size=source.file_size or 0,
    )


def _publish_without_overwrite(source: Path, destination: Path) -> None:
    """Atomically rename a same-filesystem file without replacing an artifact."""
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        os.replace(source, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def create_revision(
    session: Session,
    storage: Storage,
    *,
    case_id: str,
    voxels: bytes,
    shape: tuple[int, int, int],
    source_segmentation_id: str | None,
    parent_revision_id: str | None,
    note: str | None,
) -> AnnotationRevision:
    """Persist a complete revision mask in the case's canonical DWI geometry."""
    dwi = session.scalar(
        select(SourceArtifact).where(
            SourceArtifact.case_id == case_id,
            SourceArtifact.modality == "DWI",
        )
    )
    if dwi is None:
        raise ApiError(409, "case_not_ready", "DWI is required before saving a revision")
    dwi_metadata = _source_metadata(dwi)
    if shape != dwi_metadata.shape:
        raise ApiError(
            422,
            "incompatible_geometry",
            "Labelmap shape does not match the case DWI",
        )

    expected = int(np.prod(shape))
    if len(voxels) != expected:
        raise ApiError(
            422,
            "invalid_labelmap_buffer",
            "Labelmap byte count does not match the supplied shape",
        )

    parent_revision = (
        session.get(AnnotationRevision, parent_revision_id)
        if parent_revision_id is not None
        else None
    )
    if parent_revision_id is not None and (
        parent_revision is None or parent_revision.case_id != case_id
    ):
        raise ApiError(
            422,
            "invalid_parent_revision",
            "Parent revision does not belong to this case",
        )
    if parent_revision is not None:
        if (
            source_segmentation_id is not None
            and source_segmentation_id != parent_revision.source_segmentation_id
        ):
            raise ApiError(
                422,
                "invalid_revision_lineage",
                "Source segmentation does not match the parent revision lineage",
            )
        source_segmentation_id = parent_revision.source_segmentation_id

    source = (
        session.get(SegmentationArtifact, source_segmentation_id)
        if source_segmentation_id is not None
        else None
    )
    if source is None or source.case_id != case_id:
        raise ApiError(
            422,
            "invalid_source_segmentation",
            "Source segmentation does not belong to this case",
        )

    current = (np.frombuffer(voxels, dtype=np.uint8).reshape(shape, order="F") > 0).astype(
        np.uint8
    )
    base_path = storage.resolve(
        parent_revision.relative_path if parent_revision is not None else source.relative_path
    )
    base_metadata = validate_source_nifti(base_path)
    assert_compatible_geometry(dwi_metadata, base_metadata)
    parent = load_volume(base_path).data
    output_path = storage.revision_path(case_id)
    if output_path.exists():
        raise ApiError(409, "revision_path_exists", "Revision artifact already exists")

    published = False
    try:
        with TemporaryDirectory(dir=output_path.parent) as temporary_dir:
            temporary_path = Path(temporary_dir) / "revision.nii.gz"
            save_volume(
                temporary_path,
                current,
                np.asarray(dwi_metadata.affine),
                dtype=np.uint8,
            )
            saved_metadata = validate_source_nifti(temporary_path)
            assert_compatible_geometry(dwi_metadata, saved_metadata)
            saved = load_volume(temporary_path)
            if saved_metadata.datatype != "uint8" or not np.isin(saved.data, (0, 1)).all():
                raise ApiError(
                    422,
                    "invalid_revision_mask",
                    "Revision mask must be binary uint8",
                )
            stats = compute_revision_stats(
                parent,
                saved.data,
                voxel_volume_mm3=float(np.prod(dwi_metadata.spacing)),
            )
            digest = sha256_file(temporary_path)
            _publish_without_overwrite(temporary_path, output_path)
            published = True

        revision = AnnotationRevision(
            case_id=case_id,
            parent_revision_id=parent_revision_id,
            source_segmentation_id=source.id,
            relative_path=storage.relative(output_path),
            sha256=digest,
            note=note,
            edit_stats_json=json.dumps(asdict(stats), allow_nan=False),
        )
        session.add(revision)
        session.commit()
        return revision
    except Exception:
        session.rollback()
        if published:
            output_path.unlink(missing_ok=True)
        raise
