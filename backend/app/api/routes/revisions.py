import json

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import AnnotationRevision
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.services.cases import require_case
from app.services.revisions import save_revision_from_labelmap
from app.services.storage import Storage

router = APIRouter(prefix="/api/cases", tags=["revisions"])


def _read(revision: AnnotationRevision) -> dict:
    return {
        "id": revision.id,
        "case_id": revision.case_id,
        "source_inference_id": revision.source_inference_id,
        "note": revision.note,
        "created_at": revision.created_at,
    }


@router.get("/{case_id}/revisions")
def list_revisions(case_id: str, session: Session = Depends(get_session)):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    return [_read(revision) for revision in repo.list_revisions(case_id)]


@router.post("/{case_id}/revisions", status_code=status.HTTP_201_CREATED)
async def create_revision(
    case_id: str,
    voxels: UploadFile = File(...),
    shape: str = Form(...),
    source_inference_id: str = Form(...),
    note: str | None = Form(None),
    session: Session = Depends(get_session),
):
    repo = CaseRepository(session)
    require_case(repo, case_id)

    source = repo.get_inference(source_inference_id)
    if not source or source.case_id != case_id:
        raise ApiError(
            422,
            "invalid_source_inference",
            "Source inference does not belong to this case",
        )

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

    dwi = repo.get_modality(case_id, "DWI")
    if dwi is None:
        raise ApiError(409, "case_not_ready", "DWI is required before saving a revision")

    storage = Storage(settings.data_dir)
    out = storage.revision_path(case_id)
    save_revision_from_labelmap(
        await voxels.read(),
        dims,
        storage.resolve(dwi.relative_path),
        out,
    )
    revision = repo.add_revision(
        AnnotationRevision(
            case_id=case_id,
            source_inference_id=source_inference_id,
            relative_path=storage.relative(out),
            note=note,
        )
    )
    return _read(revision)


@router.get("/{case_id}/revisions/{revision_id}")
def get_revision(
    case_id: str,
    revision_id: str,
    session: Session = Depends(get_session),
):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    revision = repo.get_revision(revision_id)
    if not revision or revision.case_id != case_id:
        raise ApiError(404, "revision_not_found", "Revision not found")
    return _read(revision)


@router.get("/{case_id}/revisions/{revision_id}/file")
@router.get("/{case_id}/revisions/{revision_id}/file.nii.gz")
def revision_file(
    case_id: str,
    revision_id: str,
    session: Session = Depends(get_session),
):
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
