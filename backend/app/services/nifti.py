from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.errors import ApiError


@dataclass(frozen=True)
class NiftiMetadata:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    affine: np.ndarray


def inspect_nifti(path: Path) -> NiftiMetadata:
    try:
        from app.services.nifti_codec import load_volume

        image = load_volume(path)
        affine = np.asarray(image.affine, dtype=float)
        if not np.isfinite(affine).all():
            raise ValueError("affine contains non-finite values")
        return NiftiMetadata(
            tuple(int(v) for v in image.data.shape),
            image.spacing,
            affine,
        )
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(422, "invalid_nifti", f"Invalid NIfTI file: {exc}") from exc


def assert_compatible_geometry(
    reference: NiftiMetadata,
    candidate: NiftiMetadata,
) -> None:
    same_shape = reference.shape == candidate.shape
    same_affine = np.allclose(reference.affine, candidate.affine, atol=1e-4)
    if not (same_shape and same_affine):
        raise ApiError(
            422,
            "incompatible_geometry",
            "NIfTI geometry does not match the case reference",
        )
