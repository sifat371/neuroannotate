import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import InferenceJob, SegmentationArtifact, new_uuid
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.services.cases import REQUIRED_MODALITIES, require_case
from app.services.inference.base import CaseInput
from app.services.inference.registry import get_provider
from app.services.nifti import inspect_nifti
from app.services.storage import Storage

router = APIRouter(prefix="/api/cases", tags=["segmentations"])


def _read(run: InferenceJob) -> dict:
    return {
        "id": run.id,
        "case_id": run.case_id,
        "provider": run.provider,
        "status": run.status,
        "metadata": json.loads(run.provenance_json or "{}"),
        "created_at": run.created_at,
    }


@router.post("/{case_id}/segment", status_code=status.HTTP_201_CREATED)
def segment(case_id: str, session: Session = Depends(get_session)):
    repo = CaseRepository(session)
    case = require_case(repo, case_id)
    available = {artifact.modality for artifact in case.source_artifacts}
    if available != REQUIRED_MODALITIES:
        raise ApiError(
            409,
            "case_not_ready",
            "DWI, ADC, and FLAIR are required before segmentation",
        )

    storage = Storage(settings.data_dir)
    paths = {
        artifact.modality: storage.resolve(artifact.relative_path)
        for artifact in case.source_artifacts
    }
    output = storage.inference_path(case_id)
    result = get_provider().segment(CaseInput(case_id, paths), output)
    metadata = inspect_nifti(result.mask_path)
    with result.mask_path.open("rb") as file_handle:
        sha256 = hashlib.file_digest(file_handle, "sha256").hexdigest()
    job_id = new_uuid()
    completed_at = datetime.now(UTC)
    run = repo.add_inference(
        InferenceJob(
            id=job_id,
            case_id=case_id,
            provider=result.provider,
            model_name=result.provider,
            model_version="1",
            service_version="0.1.0",
            status="completed",
            started_at=completed_at,
            completed_at=completed_at,
            provenance_json=json.dumps(result.metadata),
        ),
        SegmentationArtifact(
            id=job_id,
            case_id=case_id,
            inference_job_id=job_id,
            relative_path=storage.relative(result.mask_path),
            sha256=sha256,
            shape_x=metadata.shape[0],
            shape_y=metadata.shape[1],
            shape_z=metadata.shape[2],
            spacing_x=metadata.spacing[0],
            spacing_y=metadata.spacing[1],
            spacing_z=metadata.spacing[2],
            affine_json=json.dumps(metadata.affine.tolist()),
            datatype=metadata.datatype,
        ),
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
@router.get("/{case_id}/segmentations/latest/file.nii.gz")
def latest_file(case_id: str, session: Session = Depends(get_session)):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    run = repo.latest_inference(case_id)
    if not run:
        raise ApiError(404, "segmentation_not_found", "No segmentation is available")
    if run.segmentation is None:
        raise ApiError(404, "segmentation_not_found", "No segmentation is available")
    path = Storage(settings.data_dir).resolve(run.segmentation.relative_path)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename="segmentation.nii.gz",
    )
