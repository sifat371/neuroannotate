from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.errors import ApiError


@dataclass(frozen=True)
class NiftiMetadata:
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    affine: list[list[float]]
    datatype: str
    file_size: int


def inspect_nifti(path: Path) -> NiftiMetadata:
    """Validate a 3D numeric NIfTI file and return persistence metadata."""
    try:
        from app.services.nifti_codec import load_volume

        source_path = Path(path)
        image = load_volume(source_path)
        shape = tuple(int(value) for value in image.data.shape)
        if len(shape) != 3 or any(dimension <= 0 for dimension in shape):
            raise ValueError("expected a non-empty 3D NIfTI volume")

        affine = np.asarray(image.affine, dtype=float)
        if affine.shape != (4, 4) or not np.isfinite(affine).all():
            raise ValueError("affine contains non-finite values")
        spacing = tuple(float(value) for value in image.spacing)
        if len(spacing) != 3 or not np.isfinite(spacing).all():
            raise ValueError("voxel spacing contains non-finite values")

        datatype = np.dtype(image.datatype)
        if not np.issubdtype(datatype, np.number):
            raise ValueError("NIfTI datatype must be numeric")

        return NiftiMetadata(
            shape=shape,
            spacing=spacing,
            affine=affine.tolist(),
            datatype=str(datatype),
            file_size=source_path.stat().st_size,
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
    same_affine = np.allclose(
        reference.affine,
        candidate.affine,
        atol=1e-5,
        rtol=0,
    )
    if not (same_shape and same_affine):
        raise ApiError(
            422,
            "incompatible_geometry",
            "NIfTI geometry does not match the case reference",
        )
