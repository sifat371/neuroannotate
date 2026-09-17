import hashlib
import json
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.db.models import SourceArtifact
from app.db.session import get_session
from app.repositories.cases import CaseRepository
from app.services.cases import case_to_dict, require_case
from app.services.nifti import assert_compatible_geometry, inspect_nifti
from app.services.storage import Storage

router = APIRouter(prefix="/api/cases", tags=["modalities"])
ALLOWED = {"DWI", "ADC", "FLAIR"}


async def _save_upload(file: UploadFile, path: Path) -> None:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0
    async with aiofiles.open(path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                await out.close()
                path.unlink(missing_ok=True)
                raise ApiError(
                    413,
                    "file_too_large",
                    "Uploaded file exceeds the configured size limit",
                )
            await out.write(chunk)


@router.post(
    "/{case_id}/modalities/{modality}",
    status_code=status.HTTP_201_CREATED,
)
async def upload_modality(
    case_id: str,
    modality: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    modality = modality.upper()
    if modality not in ALLOWED:
        raise ApiError(422, "invalid_modality", "Modality must be DWI, ADC, or FLAIR")

    filename = (file.filename or "").lower()
    if not (filename.endswith(".nii") or filename.endswith(".nii.gz")):
        raise ApiError(
            422,
            "invalid_extension",
            "Only .nii and .nii.gz files are supported",
        )
    if repo.get_modality(case_id, modality):
        raise ApiError(
            409,
            "duplicate_modality",
            f"{modality} is already attached to this case",
        )

    storage = Storage(settings.data_dir)
    path = storage.modality_path(case_id, modality, filename.endswith(".gz"))
    await _save_upload(file, path)
    try:
        meta = inspect_nifti(path)
        reference = next(
            (
                artifact
                for candidate_modality in ("DWI", "ADC", "FLAIR")
                if (artifact := repo.get_modality(case_id, candidate_modality))
            ),
            None,
        )
        if reference:
            ref_meta = inspect_nifti(storage.resolve(reference.relative_path))
            assert_compatible_geometry(ref_meta, meta)

        with path.open("rb") as file_handle:
            sha256 = hashlib.file_digest(file_handle, "sha256").hexdigest()
        artifact = SourceArtifact(
            case_id=case_id,
            modality=modality,
            original_filename=file.filename or path.name,
            relative_path=storage.relative(path),
            sha256=sha256,
            file_size=path.stat().st_size,
            shape_x=meta.shape[0],
            shape_y=meta.shape[1],
            shape_z=meta.shape[2],
            spacing_x=meta.spacing[0],
            spacing_y=meta.spacing[1],
            spacing_z=meta.spacing[2],
            affine_json=json.dumps(meta.affine.tolist()),
            datatype=meta.datatype,
        )
        repo.add_modality(artifact)
    except Exception:
        path.unlink(missing_ok=True)
        raise

    return case_to_dict(require_case(repo, case_id))


@router.get("/{case_id}/modalities/{modality}/file")
@router.get("/{case_id}/modalities/{modality}/file.nii.gz")
def modality_file(
    case_id: str,
    modality: str,
    session: Session = Depends(get_session),
):
    repo = CaseRepository(session)
    require_case(repo, case_id)
    artifact = repo.get_modality(case_id, modality.upper())
    if not artifact:
        raise ApiError(404, "modality_not_found", "Modality not found")
    path = Storage(settings.data_dir).resolve(artifact.relative_path)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )
