import numpy as np
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import SegmentationArtifact
from app.db.session import get_session
from app.schemas.inference import InferenceCreate, InferenceJobRead, ProviderInfoRead
from app.services.inference.jobs import (
    create_job,
    job_to_dict,
    list_jobs,
    require_job,
    retry_job,
)
from app.services.inference.registry import list_providers
from app.services.nifti_codec import load_volume

router = APIRouter(prefix="/api", tags=["inference-jobs"])


@router.post("/cases/{case_id}/inference-jobs", response_model=InferenceJobRead, status_code=202)
def enqueue_job(
    case_id: str, payload: InferenceCreate, session: Session = Depends(get_session)
) -> dict[str, object]:
    return job_to_dict(create_job(session, case_id, payload.provider))


@router.get("/cases/{case_id}/inference-jobs", response_model=list[InferenceJobRead])
def get_case_jobs(
    case_id: str, session: Session = Depends(get_session)
) -> list[dict[str, object]]:
    return [job_to_dict(job) for job in list_jobs(session, case_id)]


@router.get("/inference-jobs/{job_id}", response_model=InferenceJobRead)
def get_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return job_to_dict(require_job(session, job_id))


@router.post("/inference-jobs/{job_id}/retry", response_model=InferenceJobRead, status_code=202)
def retry(job_id: str, session: Session = Depends(get_session)) -> dict[str, object]:
    return job_to_dict(retry_job(session, job_id))


@router.get("/inference/providers", response_model=list[ProviderInfoRead])
def provider_status() -> list[dict[str, object]]:
    return [vars(provider.info()) for provider in list_providers()]


@router.get("/segmentations/{segmentation_id}/metrics")
def segmentation_metrics(
    segmentation_id: str, session: Session = Depends(get_session)
) -> dict[str, int | float]:
    """Return deterministic lesion burden measurements for an AI candidate mask."""
    artifact = session.get(SegmentationArtifact, segmentation_id)
    if artifact is None:
        raise ApiError(404, "segmentation_not_found", "Segmentation not found")
    volume = load_volume(settings.data_dir / artifact.relative_path)
    unit_scale = {"mm": 1.0, "meter": 1000.0, "micron": 0.001}.get(
        volume.spatial_units
    )
    if unit_scale is None:
        raise ApiError(
            422,
            "unsupported_spatial_units",
            "Segmentation spatial units must be mm, meter, or micron to report volume",
        )
    lesion_voxels = int(np.count_nonzero(np.asarray(volume.data) > 0))
    voxel_volume_mm3 = (
        artifact.spacing_x * artifact.spacing_y * artifact.spacing_z * unit_scale**3
    )
    return {
        "lesion_voxels": lesion_voxels,
        "lesion_volume_ml": lesion_voxels * voxel_volume_mm3 / 1000.0,
    }


@router.get("/segmentations/{segmentation_id}/file.nii.gz")
def segmentation_file(
    segmentation_id: str, session: Session = Depends(get_session)
) -> FileResponse:
    artifact = session.get(SegmentationArtifact, segmentation_id)
    if artifact is None:
        raise ApiError(404, "segmentation_not_found", "Segmentation not found")
    return FileResponse(
        settings.data_dir / artifact.relative_path,
        media_type="application/octet-stream",
        filename="segmentation.nii.gz",
    )
