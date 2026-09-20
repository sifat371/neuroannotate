"""Create immutable export snapshots from saved annotation revisions."""

from __future__ import annotations

import ctypes
import errno
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.release import RELEASE_VERSION
from app.db.models import (
    AnnotationRevision,
    Case,
    ExportArtifact,
    InferenceJob,
    SegmentationArtifact,
    SourceArtifact,
    new_uuid,
)
from app.services.checksums import sha256_file
from app.services.provenance import build_provenance, serialize_provenance, validate_provenance
from app.services.storage import Storage

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


def _publish_without_overwrite(source: Path, destination: Path) -> None:
    """Atomically publish a directory only when no destination already exists."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as exc:
        raise ApiError(
            503, "atomic_publish_unsupported", "Atomic no-replace export publication is unavailable"
        ) from exc
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    ) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise ApiError(409, "export_path_exists", "Export artifact already exists")
    raise OSError(error_number, os.strerror(error_number), destination)


def _software_identity() -> dict[str, object]:
    """Return portable software identity, omitting an unavailable git revision."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[3],
        )
        commit: str | None = completed.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"name": settings.app_name, "version": RELEASE_VERSION, "git_commit": commit}


def _require_digest_matches(path: Path, expected: str | None, field: str) -> None:
    """Reject absent or mismatched checksums before an export is published."""
    if expected is None:
        raise ApiError(409, "incomplete_provenance", f"Missing {field} checksum")
    if not path.is_file() or sha256_file(path) != expected:
        raise ApiError(409, "incomplete_provenance", f"Invalid {field} checksum")


def _lineage(session: Session, revision: AnnotationRevision) -> list[str]:
    """Follow immediate-parent pointers from the selected revision to its root."""
    result: list[str] = []
    current: AnnotationRevision | None = revision
    seen: set[str] = set()
    while current is not None:
        if current.id in seen or current.case_id != revision.case_id:
            raise ApiError(409, "invalid_revision_lineage", "Revision lineage is invalid")
        seen.add(current.id)
        result.append(current.id)
        if current.parent_revision_id is None:
            current = None
            continue
        current = session.get(AnnotationRevision, current.parent_revision_id)
        if current is None:
            raise ApiError(409, "invalid_revision_lineage", "Revision lineage is invalid")
    result.reverse()
    return result


def _load_dependencies(
    session: Session, case_id: str, revision_id: str
) -> tuple[Case, AnnotationRevision, list[SourceArtifact], SegmentationArtifact, InferenceJob]:
    """Load the complete immutable dependency graph for one export."""
    case = session.get(Case, case_id)
    if case is None:
        raise ApiError(404, "case_not_found", "Case not found")
    revision = session.get(AnnotationRevision, revision_id)
    if revision is None or revision.case_id != case_id:
        raise ApiError(404, "revision_not_found", "Revision not found")
    sources = list(
        session.scalars(select(SourceArtifact).where(SourceArtifact.case_id == case_id))
    )
    segmentation = session.get(SegmentationArtifact, revision.source_segmentation_id)
    if segmentation is None or segmentation.case_id != case_id:
        raise ApiError(409, "incomplete_provenance", "Source segmentation is unavailable")
    job = session.get(InferenceJob, segmentation.inference_job_id)
    if job is None or job.case_id != case_id or job.status != "completed":
        raise ApiError(409, "incomplete_provenance", "Completed inference metadata is unavailable")
    return case, revision, sources, segmentation, job


def create_export(
    session: Session,
    storage: Storage,
    case_id: str,
    revision_id: str,
) -> ExportArtifact:
    """Persist an atomic two-file snapshot of one saved case revision."""
    case, revision, sources, segmentation, job = _load_dependencies(session, case_id, revision_id)
    source_by_modality = {source.modality: source for source in sources}
    if set(source_by_modality) != {"DWI", "ADC", "FLAIR"}:
        raise ApiError(409, "incomplete_provenance", "The complete source triad is required")
    for source in source_by_modality.values():
        _require_digest_matches(
            storage.resolve(source.relative_path), source.sha256, source.modality
        )
    _require_digest_matches(
        storage.resolve(segmentation.relative_path), segmentation.sha256, "segmentation"
    )
    revision_path = storage.resolve(revision.relative_path)
    _require_digest_matches(revision_path, revision.sha256, "revision")

    export_id = new_uuid()
    export_root = storage.root / "exports"
    export_root.mkdir(parents=True, exist_ok=True)
    output_dir = export_root / export_id
    if output_dir.exists():
        raise ApiError(409, "export_path_exists", "Export artifact already exists")
    export = ExportArtifact(
        id=export_id,
        case_id=case_id,
        revision_id=revision_id,
        mask_path=storage.relative(output_dir / "lesion-mask.nii.gz"),
        provenance_path=storage.relative(output_dir / "provenance.json"),
        mask_sha256="",
        created_at=datetime.now(UTC),
    )
    published = False
    try:
        with TemporaryDirectory(dir=export_root) as temporary_name:
            temporary_dir = Path(temporary_name)
            temporary_mask = temporary_dir / "lesion-mask.nii.gz"
            shutil.copyfile(revision_path, temporary_mask)
            export.mask_sha256 = sha256_file(temporary_mask)
            if export.mask_sha256 != revision.sha256:
                raise ApiError(
                    409, "incomplete_provenance", "Revision checksum changed during export"
                )
            document = build_provenance(
                case=case,
                sources=sources,
                job=job,
                segmentation=segmentation,
                revision=revision,
                export=export,
                software=_software_identity(),
                lineage=_lineage(session, revision),
            )
            validate_provenance(document)
            temporary_provenance = temporary_dir / "provenance.json.tmp"
            temporary_provenance.write_bytes(serialize_provenance(document))
            os.replace(temporary_provenance, temporary_dir / "provenance.json")
            _publish_without_overwrite(temporary_dir, output_dir)
            published = True
        session.add(export)
        session.commit()
        return export
    except Exception:
        session.rollback()
        if published:
            shutil.rmtree(output_dir, ignore_errors=True)
        raise
