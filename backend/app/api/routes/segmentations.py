import json

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import InferenceRun
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.services.cases import REQUIRED_MODALITIES, require_case
from app.services.inference.base import CaseInput
from app.services.inference.registry import get_provider
from app.services.storage import Storage

router = APIRouter(prefix="/api/cases", tags=["segmentations"])


def _read(run: InferenceRun) -> dict:
    return {
        "id": run.id,
        "case_id": run.case_id,
        "provider": run.provider,
        "status": run.status,
        "metadata": json.loads(run.metadata_json or "{}"),
        "created_at": run.created_at,
    }


@router.post("/{case_id}/segment", status_code=status.HTTP_201_CREATED)
def segment(case_id: str, session: Session = Depends(get_session)):
    repo = CaseRepository(session)
    case = require_case(repo, case_id)
    available = {modality.modality for modality in case.modalities}
    if available != REQUIRED_MODALITIES:
        raise ApiError(
            409,
            "case_not_ready",
            "DWI, ADC, and FLAIR are required before segmentation",
        )

    storage = Storage(settings.data_dir)
    paths = {
        modality.modality: storage.resolve(modality.relative_path)
        for modality in case.modalities
    }
    output = storage.inference_path(case_id)
    result = get_provider().segment(CaseInput(case_id, paths), output)
    run = repo.add_inference(
        InferenceRun(
            case_id=case_id,
            provider=result.provider,
            relative_path=storage.relative(result.mask_path),
            status="completed",
            metadata_json=json.dumps(result.metadata),
        )
    )
    return _read(run)


@router.get("/{case_id}/segmentations/latest")
def latest(case_id: str, session: Session = Depends(get_session)):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    run = repo.latest_inference(case_id)
    if not run:
        raise ApiError(404, "segmentation_not_found", "No segmentation is available")
    return _read(run)


@router.get("/{case_id}/segmentations/latest/file")
def latest_file(case_id: str, session: Session = Depends(get_session)):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    run = repo.latest_inference(case_id)
    if not run:
        raise ApiError(404, "segmentation_not_found", "No segmentation is available")
    path = Storage(settings.data_dir).resolve(run.relative_path)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename="segmentation.nii.gz",
    )
