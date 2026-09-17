import json

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import AnnotationRevision
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.schemas.revisions import RevisionRead
from app.services.cases import require_case
from app.services.revisions import create_revision as persist_revision
from app.services.storage import Storage

router = APIRouter(prefix="/api", tags=["revisions"])


def _read(revision: AnnotationRevision) -> dict[str, object]:
    edit_stats = json.loads(revision.edit_stats_json or "{}")
    return {
        "id": revision.id,
        "case_id": revision.case_id,
        "source_inference_id": revision.source_segmentation_id,
        "source_segmentation_id": revision.source_segmentation_id,
        "parent_revision_id": revision.parent_revision_id,
        "sha256": revision.sha256,
        "edit_stats": edit_stats,
        "note": revision.note,
        "created_at": revision.created_at,
    }


@router.get("/cases/{case_id}/revisions", response_model=list[RevisionRead])
def list_revisions(
    case_id: str,
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    repo = CaseRepository(session)
    require_case(repo, case_id)
    return [_read(revision) for revision in repo.list_revisions(case_id)]


@router.post(
    "/cases/{case_id}/revisions",
    response_model=RevisionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_revision(
    case_id: str,
    voxels: UploadFile = File(...),
    shape: str = Form(...),
    source_inference_id: str | None = Form(None),
    source_segmentation_id: str | None = Form(None),
    parent_revision_id: str | None = Form(None),
    note: str | None = Form(None),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repo = CaseRepository(session)
    require_case(repo, case_id)

    if source_segmentation_id is None and parent_revision_id is None:
        source = repo.get_inference(source_inference_id) if source_inference_id else None
        if not source or source.case_id != case_id or source.segmentation is None:
            raise ApiError(
                422,
                "invalid_source_inference",
                "Source inference does not belong to this case",
            )
        source_segmentation_id = source.segmentation.id

    try:
        dims = tuple(int(v) for v in json.loads(shape))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ApiError(
            422,
            "invalid_shape",
            "Shape must be a JSON array of three integers",
        ) from exc
    if len(dims) != 3:
        raise ApiError(422, "invalid_shape", "Shape must contain three dimensions")

    storage = Storage(settings.data_dir)
    revision = persist_revision(
        session,
        storage,
        case_id=case_id,
        voxels=await voxels.read(),
        shape=dims,
        source_segmentation_id=source_segmentation_id,
        parent_revision_id=parent_revision_id,
        note=note,
    )
    return _read(revision)


@router.get("/cases/{case_id}/revisions/{revision_id}", response_model=RevisionRead)
def get_revision(
    case_id: str,
    revision_id: str,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    repo = CaseRepository(session)
    require_case(repo, case_id)
    revision = repo.get_revision(revision_id)
    if not revision or revision.case_id != case_id:
        raise ApiError(404, "revision_not_found", "Revision not found")
    return _read(revision)


@router.get("/cases/{case_id}/revisions/{revision_id}/file")
@router.get("/cases/{case_id}/revisions/{revision_id}/file.nii.gz")
def revision_file(
    case_id: str,
    revision_id: str,
    session: Session = Depends(get_session),
) -> FileResponse:
    repo = CaseRepository(session)
    require_case(repo, case_id)
    revision = repo.get_revision(revision_id)
    if not revision or revision.case_id != case_id:
        raise ApiError(404, "revision_not_found", "Revision not found")
    path = Storage(settings.data_dir).resolve(revision.relative_path)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"revision_{revision.id}.nii.gz",
    )


@router.get("/revisions/{revision_id}/file.nii.gz")
def revision_file_by_id(
    revision_id: str,
    session: Session = Depends(get_session),
) -> FileResponse:
    revision = CaseRepository(session).get_revision(revision_id)
    if revision is None:
        raise ApiError(404, "revision_not_found", "Revision not found")
    path = Storage(settings.data_dir).resolve(revision.relative_path)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"revision_{revision.id}.nii.gz",
    )
