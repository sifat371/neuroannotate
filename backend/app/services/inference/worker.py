"""Sequential local worker for persisted inference jobs."""

import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock
from time import perf_counter

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import InferenceJob, SegmentationArtifact, SourceArtifact
from app.db.session import new_session
from app.services.artifacts import validate_source_nifti
from app.services.checksums import sha256_file
from app.services.inference.base import (
    CaseInput,
    ProviderOutputPersistenceError,
    ProviderRuntimeError,
    ProviderUnavailableError,
)
from app.services.inference.jobs import transition_job
from app.services.inference.registry import get_provider
from app.services.nifti import assert_compatible_geometry, inspect_nifti
from app.services.nifti_codec import load_volume

_execution_lock = Lock()
logger = logging.getLogger(__name__)


def _cleanup_output(destination: Path) -> None:
    """Remove any mask that was not committed as a completed artifact."""
    try:
        destination.unlink(missing_ok=True)
        if destination.parent.exists():
            destination.parent.rmdir()
    except OSError:
        logger.exception("Could not clean failed inference output %s", destination)


def _serialize_failure_provenance(provenance: dict[str, object]) -> str:
    """Serialize failure provenance, dropping invalid provider metadata if needed."""
    try:
        return json.dumps(provenance, allow_nan=False)
    except (TypeError, ValueError):
        runtime = provenance.get("runtime")
        duration = runtime.get("duration_seconds") if isinstance(runtime, dict) else None
        return json.dumps(
            {
                "sources": provenance.get("sources", []),
                "configuration": {},
                "runtime": {"duration_seconds": duration},
            },
            allow_nan=False,
        )


def recover_interrupted_jobs(session: Session) -> int:
    """Fail jobs left running when the previous application process stopped."""
    jobs = session.scalars(
        select(InferenceJob).where(InferenceJob.status == "running")
    ).all()
    if not jobs:
        return 0
    for job in jobs:
        _cleanup_output(
            settings.data_dir / "inference" / job.id / "segmentation.nii.gz"
        )
        transition_job(job, "failed")
        job.failure_category = "application_interrupted"
        job.error_message = "Interrupted by application restart"
    session.commit()
    return len(jobs)


class InferenceWorker:
    """Process at most one queued job per invocation."""

    def run_once(self) -> bool:
        with _execution_lock, new_session() as session:
            job = session.scalar(
                select(InferenceJob)
                .where(InferenceJob.status == "queued")
                .order_by(InferenceJob.created_at, InferenceJob.id)
                .limit(1)
            )
            if job is None:
                return False
            transition_job(job, "running")
            session.commit()
            destination = settings.data_dir / "inference" / job.id / "segmentation.nii.gz"
            provenance: dict[str, object] = {}
            started = perf_counter()
            category = "input_validation_failure"
            try:
                loaded_provenance = json.loads(job.provenance_json)
                if not isinstance(loaded_provenance, dict):
                    raise ValueError("Inference provenance must be a JSON object")
                provenance = loaded_provenance
                paths: dict[str, Path] = {}
                for reference in provenance["sources"]:
                    source = session.get(SourceArtifact, reference["id"])
                    if source is None or source.case_id != job.case_id:
                        raise ValueError("Source artifact is missing or belongs to another case")
                    if source.modality != reference["modality"]:
                        raise ValueError("Source modality has changed")
                    path = settings.data_dir / source.relative_path
                    if not reference["sha256"] or sha256_file(path) != reference["sha256"]:
                        raise ValueError("Source checksum does not match the queued input")
                    validate_source_nifti(path)
                    paths[source.modality] = path
                if set(paths) != {"DWI", "ADC", "FLAIR"}:
                    raise ValueError("Inference requires the complete source triad")
                reference_metadata = inspect_nifti(paths["DWI"])

                category = "provider_unavailable"
                provider = get_provider(job.provider)
                if not provider.info().available:
                    raise ValueError(f"Provider {job.provider} is unavailable")

                category = "artifact_persistence_failure"
                destination.parent.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=destination.parent) as temporary:
                    category = "provider_runtime_failure"
                    try:
                        result = provider.segment(
                            CaseInput(job.case_id, paths),
                            Path(temporary) / "segmentation.nii.gz",
                        )
                    except ProviderUnavailableError:
                        category = "provider_unavailable"
                        raise
                    except ProviderRuntimeError:
                        category = "provider_runtime_failure"
                        raise
                    except ProviderOutputPersistenceError:
                        category = "artifact_persistence_failure"
                        raise
                    provenance.update(
                        configuration=result.configuration, runtime=result.runtime
                    )
                    category = "invalid_model_output"
                    metadata = inspect_nifti(result.mask_path)
                    assert_compatible_geometry(reference_metadata, metadata)
                    volume = load_volume(result.mask_path)
                    if metadata.datatype != "uint8" or not np.isfinite(volume.data).all():
                        raise ValueError("Model mask must contain finite uint8 data")
                    if not np.isin(volume.data, (0, 1)).all():
                        raise ValueError("Model mask must be binary")
                    category = "artifact_persistence_failure"
                    os.replace(result.mask_path, destination)
                digest = sha256_file(destination)
                job.provider = result.provider
                job.model_name = result.model_name
                job.model_version = result.model_version
                job.service_version = result.service_version
                provenance["result"] = {"sha256": digest}
                job.provenance_json = json.dumps(provenance, allow_nan=False)
                job.segmentation = SegmentationArtifact(
                    case_id=job.case_id,
                    relative_path=str(destination.relative_to(settings.data_dir)),
                    sha256=digest,
                    shape_x=metadata.shape[0], shape_y=metadata.shape[1], shape_z=metadata.shape[2],
                    spacing_x=metadata.spacing[0],
                    spacing_y=metadata.spacing[1],
                    spacing_z=metadata.spacing[2],
                    affine_json=json.dumps(metadata.affine),
                    datatype=metadata.datatype,
                )
                transition_job(job, "completed")
                session.commit()
            except Exception as exc:
                # This is the worker boundary: provider exceptions must not kill the loop.
                session.rollback()
                _cleanup_output(destination)
                transition_job(job, "failed")
                job.failure_category = category
                job.error_message = f"{type(exc).__name__}: {exc}"
                runtime = provenance.get("runtime")
                if not isinstance(runtime, dict):
                    runtime = {}
                runtime["duration_seconds"] = perf_counter() - started
                provenance["runtime"] = runtime
                job.provenance_json = _serialize_failure_provenance(provenance)
                session.commit()
            return True


def run_worker_loop(stop_event: Event, poll_interval_seconds: float = 0.1) -> None:
    """Continuously process queued jobs until application shutdown."""
    worker = InferenceWorker()
    while not stop_event.is_set():
        try:
            processed = worker.run_once()
        except Exception:
            logger.exception("Inference worker could not inspect the queue")
            processed = False
        if not processed:
            stop_event.wait(poll_interval_seconds)
