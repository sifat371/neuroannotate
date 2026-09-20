from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import ExportArtifact
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.schemas.exports import ExportCreate, ExportRead
from app.services.cases import require_case
from app.services.exports import create_export
from app.services.storage import Storage

router = APIRouter(prefix="/api", tags=["exports"])


def _read(export: ExportArtifact) -> dict[str, object]:
    """Serialize an export without exposing managed filesystem paths."""
    return {
        "id": export.id,
        "case_id": export.case_id,
        "revision_id": export.revision_id,
        "mask_sha256": export.mask_sha256,
        "created_at": export.created_at,
        "mask_url": f"/api/exports/{export.id}/mask",
        "provenance_url": f"/api/exports/{export.id}/provenance",
        "bundle_url": f"/api/exports/{export.id}/bundle",
    }


def _require_export(session: Session, export_id: str) -> ExportArtifact:
    """Return a completed export record or a stable API error."""
    export = session.get(ExportArtifact, export_id)
    if export is None:
        raise ApiError(404, "export_not_found", "Export not found")
    return export


@router.post(
    "/cases/{case_id}/exports",
    response_model=ExportRead,
    status_code=status.HTTP_201_CREATED,
)
def create_case_export(
    case_id: str,
    payload: ExportCreate,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    export = create_export(session, Storage(settings.data_dir), case_id, payload.revision_id)
    return _read(export)


@router.get("/exports/{export_id}/mask")
def export_mask(export_id: str, session: Session = Depends(get_session)) -> FileResponse:
    export = _require_export(session, export_id)
    return FileResponse(
        Storage(settings.data_dir).resolve(export.mask_path),
        media_type="application/gzip",
        filename="lesion-mask.nii.gz",
    )


@router.get("/exports/{export_id}/provenance")
def export_provenance(export_id: str, session: Session = Depends(get_session)) -> FileResponse:
    export = _require_export(session, export_id)
    return FileResponse(
        Storage(settings.data_dir).resolve(export.provenance_path),
        media_type="application/json",
        filename="provenance.json",
    )


@router.get("/exports/{export_id}/bundle")
def export_bundle(export_id: str, session: Session = Depends(get_session)) -> Response:
    export = _require_export(session, export_id)
    storage = Storage(settings.data_dir)
    bundle = BytesIO()
    with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("lesion-mask.nii.gz", storage.resolve(export.mask_path).read_bytes())
        archive.writestr("provenance.json", storage.resolve(export.provenance_path).read_bytes())
    return Response(
        bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="neuroannotate-export.zip"'},
    )


@router.get("/cases/{case_id}/export")
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
