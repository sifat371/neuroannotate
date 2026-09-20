"""Durable inference job creation and serialization."""

import json
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import InferenceJob, utcnow
from app.repositories.cases import CaseRepository
from app.services.cases import REQUIRED_MODALITIES, require_case
from app.services.inference.registry import get_provider

ALLOWED_TRANSITIONS: Final[dict[str, set[str]]] = {
    "queued": {"running", "failed"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


def transition_job(job: InferenceJob, target: str) -> None:
    """Apply a valid inference lifecycle transition and its timestamp."""
    if target not in ALLOWED_TRANSITIONS.get(job.status, set()):
        raise ValueError(f"Invalid inference job transition: {job.status} -> {target}")
    changed_at = utcnow()
    job.status = target
    if target == "running":
        job.started_at = changed_at
    elif target in {"completed", "failed"}:
        job.completed_at = changed_at


def create_job(session: Session, case_id: str, provider: str) -> InferenceJob:
    """Queue a job with an immutable snapshot of its input references."""
    case = require_case(CaseRepository(session), case_id)
    if {source.modality for source in case.source_artifacts} != REQUIRED_MODALITIES:
        raise ApiError(409, "case_not_ready", "DWI, ADC, and FLAIR are required")
    info = get_provider(provider).info()
    job = InferenceJob(
        case_id=case_id,
        provider=info.name,
        model_name=info.model_name,
        model_version=info.model_version,
        service_version=info.service_version,
        status="queued",
        provenance_json=json.dumps({
            "sources": [
                {"id": source.id, "modality": source.modality, "sha256": source.sha256}
                for source in sorted(case.source_artifacts, key=lambda source: source.modality)
            ],
            "configuration": {},
            "runtime": {},
        }),
    )
    session.add(job)
    session.commit()
    return job


def require_job(session: Session, job_id: str) -> InferenceJob:
    job = session.get(InferenceJob, job_id)
    if job is None:
        raise ApiError(404, "inference_job_not_found", "Inference job not found")
    return job


def list_jobs(session: Session, case_id: str) -> list[InferenceJob]:
    """List a case's jobs in submission order."""
    require_case(CaseRepository(session), case_id)
    return list(
        session.scalars(
            select(InferenceJob)
            .where(InferenceJob.case_id == case_id)
            .order_by(InferenceJob.created_at, InferenceJob.id)
        )
    )


def retry_job(session: Session, job_id: str) -> InferenceJob:
    """Queue a new attempt for a terminal failed job."""
    failed_job = require_job(session, job_id)
    if failed_job.status != "failed":
        raise ApiError(409, "job_not_failed", "Only failed inference jobs can be retried")
    return create_job(session, failed_job.case_id, failed_job.provider)


def job_to_dict(job: InferenceJob) -> dict[str, object]:
    return {
        "id": job.id,
        "case_id": job.case_id,
        "provider": job.provider,
        "model_name": job.model_name,
        "model_version": job.model_version,
        "service_version": job.service_version,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "failure_category": job.failure_category,
        "error_message": job.error_message,
        "segmentation_id": job.segmentation.id if job.segmentation else None,
        "provenance": json.loads(job.provenance_json),
    }
