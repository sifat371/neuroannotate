"""Narrow FastAPI boundary around DeepISLES execution."""
# ruff: noqa: UP006, UP035

from __future__ import annotations

import asyncio
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Dict, Iterable

import nibabel as nib
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from starlette.datastructures import UploadFile

from app.metadata import MODEL_NAME, MODEL_VERSION, SERVICE_NAME, SERVICE_VERSION, UPSTREAM_COMMIT, runtime_metadata, service_info
from app.runner import run_deepisles

app = FastAPI(title="NeuroAnnotate DeepISLES Service")
_EXPECTED_FIELDS = frozenset(("dwi", "adc", "flair"))
_INFERENCE_LOCK = Lock()
_CONFIGURATION = {
    "implementation": "BrainLesion stroke_segmentor",
    "modalities": ["ADC", "DWI"],
    "flair_used": False,
}


def _validate_mask(mask_path: Path, dwi_path: Path) -> None:
    """Require a readable finite binary uint8 segmentation in DWI geometry."""
    try:
        mask = nib.load(str(mask_path))
        dwi = nib.load(str(dwi_path))
        data = np.asanyarray(mask.dataobj)
        if data.ndim != 3 or data.dtype != np.dtype("uint8"):
            raise ValueError("mask must be a 3D uint8 NIfTI")
        if not np.isfinite(data).all() or not np.isin(data, (0, 1)).all():
            raise ValueError("mask must contain finite binary values")
        if mask.shape != dwi.shape or not np.allclose(
            mask.affine, dwi.affine, atol=1e-5, rtol=0
        ):
            raise ValueError("mask geometry does not match DWI")
    except Exception as exc:
        raise HTTPException(status_code=422, detail="invalid DWI-space segmentation") from exc


def _metadata(duration_seconds: float) -> Dict[str, Any]:
    """Construct metadata with no input, path, host, or patient identifiers."""
    runtime = runtime_metadata()
    runtime["duration_seconds"] = duration_seconds
    return {
        "provider": "deepisles",
        "service": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "configuration": dict(_CONFIGURATION),
        "runtime": runtime,
    }


def _run_deepisles_serialized(
    dwi: Path, adc: Path, flair: Path, output_dir: Path
) -> Path:
    """Serialize GPU execution without blocking the FastAPI event loop."""
    with _INFERENCE_LOCK:
        return run_deepisles(dwi, adc, flair, output_dir)


def _archive(mask_path: Path, metadata: Dict[str, Any]) -> bytes:
    """Create the exact two-member provider response archive in memory."""
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(str(mask_path), "segmentation.nii.gz")
        archive.writestr("metadata.json", json.dumps(metadata, allow_nan=False))
    return contents.getvalue()


def _upload_fields(form: Any) -> Iterable[UploadFile]:
    """Validate exact multipart fields before any artifact is stored."""
    names = [name for name, _value in form.multi_items()]
    if set(names) != _EXPECTED_FIELDS or len(names) != len(_EXPECTED_FIELDS):
        raise HTTPException(status_code=422, detail="exactly dwi, adc, and flair are required")
    uploads = tuple(form[name] for name in ("dwi", "adc", "flair"))
    if not all(isinstance(upload, UploadFile) for upload in uploads):
        raise HTTPException(status_code=422, detail="all modalities must be uploaded files")
    return uploads


@app.get("/health")
def health() -> Dict[str, str]:
    """Return a cheap liveness response without loading model weights."""
    return {"status": "ok"}


@app.get("/v1/info")
def info() -> Dict[str, Any]:
    """Return static identity and lightweight runtime information."""
    return service_info()


@app.post("/v1/segment")
async def segment(request: Request) -> Response:
    """Run one request-owned modality triad and return a safe result archive."""
    form = await request.form()
    dwi_upload, adc_upload, flair_upload = _upload_fields(form)
    request_dir = Path(tempfile.mkdtemp(prefix="neuroannotate-deepisles-"))
    try:
        uploads = (("dwi.nii.gz", dwi_upload), ("adc.nii.gz", adc_upload), ("flair.nii.gz", flair_upload))
        paths = []
        for filename, upload in uploads:
            path = request_dir / filename
            with path.open("wb") as destination:
                shutil.copyfileobj(upload.file, destination)
            paths.append(path)
        output_dir = request_dir / "output"
        output_dir.mkdir()
        started = perf_counter()
        try:
            loop = asyncio.get_running_loop()
            mask_path = await loop.run_in_executor(
                None,
                _run_deepisles_serialized,
                paths[0],
                paths[1],
                paths[2],
                output_dir,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="DeepISLES execution failed") from exc
        _validate_mask(mask_path, paths[0])
        return Response(
            content=_archive(mask_path, _metadata(perf_counter() - started)),
            media_type="application/zip",
        )
    finally:
        shutil.rmtree(str(request_dir), ignore_errors=True)
