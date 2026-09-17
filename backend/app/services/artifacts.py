from __future__ import annotations

from pathlib import Path

from app.services.nifti import NiftiMetadata, inspect_nifti


def validate_source_nifti(path: Path) -> NiftiMetadata:
    """Validate a source image and return its persistence metadata."""
    return inspect_nifti(path)
