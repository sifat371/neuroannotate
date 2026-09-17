from __future__ import annotations

import numpy as np

from app.services.nifti import NiftiMetadata


def same_geometry(
    a: NiftiMetadata,
    b: NiftiMetadata,
    *,
    atol: float = 1e-5,
) -> bool:
    """Return whether two volumes share a shape and affine geometry."""
    return a.shape == b.shape and bool(
        np.allclose(a.affine, b.affine, atol=atol, rtol=0)
    )
