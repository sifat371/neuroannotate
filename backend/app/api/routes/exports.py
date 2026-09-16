from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.services.cases import require_case
from app.services.storage import Storage

router = APIRouter(prefix="/api/cases", tags=["exports"])


@router.get("/{case_id}/export")
def export_revision(
    case_id: str,
    revision_id: str = Query(...),
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
        media_type="application/gzip",
        filename=f"neuroannotate_{case_id}_{revision_id}.nii.gz",
    )
