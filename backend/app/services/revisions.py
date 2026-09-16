from pathlib import Path

import numpy as np

from app.core.errors import ApiError
from app.services.nifti_codec import load_volume, save_volume


def save_revision_from_labelmap(
    voxels: bytes,
    shape: tuple[int, int, int],
    reference_path: Path,
    output_path: Path,
) -> Path:
    ref = load_volume(reference_path)
    ref_shape = tuple(int(v) for v in ref.data.shape)
    if shape != ref_shape:
        raise ApiError(
            422,
            "incompatible_geometry",
            "Labelmap shape does not match the reference volume",
        )

    expected = int(np.prod(shape))
    if len(voxels) != expected:
        raise ApiError(
            422,
            "invalid_labelmap_buffer",
            "Labelmap byte count does not match the supplied shape",
        )

    array = np.frombuffer(voxels, dtype=np.uint8).reshape(shape, order="F")
    array = (array > 0).astype(np.uint8)
    save_volume(output_path, array, ref.affine, dtype=np.uint8)
    return output_path
