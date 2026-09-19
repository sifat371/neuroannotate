import gzip
import shutil
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, label

from app.services.nifti_codec import save_volume


def _save_deterministic_volume(
    path: Path,
    data: np.ndarray,
    affine: np.ndarray,
    *,
    dtype: type[np.generic],
) -> Path:
    """Write a NIfTI gzip stream without timestamps or host-specific names."""
    uncompressed_path = path.with_suffix("")
    try:
        save_volume(uncompressed_path, data, affine, dtype=dtype)
        with (
            uncompressed_path.open("rb") as source,
            path.open("wb") as destination,
            gzip.GzipFile(filename="", fileobj=destination, mode="wb", mtime=0) as target,
        ):
            shutil.copyfileobj(source, target)
    finally:
        uncompressed_path.unlink(missing_ok=True)
    return path


def _expected_demo_mask(dwi: np.ndarray) -> np.ndarray:
    """Return the deterministic mask produced by the built-in demo provider."""
    dwi = np.asarray(dwi, dtype=np.float32)
    finite = np.isfinite(dwi)
    if not finite.any():
        return np.zeros(dwi.shape, dtype=np.uint8)

    threshold = float(np.percentile(dwi[finite], 92))
    components, count = label((dwi >= threshold) & finite)
    if not count:
        return np.zeros(dwi.shape, dtype=np.uint8)
    sizes = np.bincount(components.ravel())
    keep = sizes >= 8
    keep[0] = False
    return keep[components].astype(np.uint8)


def generate_demo_case(output_dir: Path) -> dict[str, Path]:
    """Generate a reproducible, non-patient source triad and expected mask."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(2026)
    shape = (64, 64, 48)
    x, y, z = np.indices(shape)

    brain = (
        ((x - 31.5) / 27) ** 2
        + ((y - 31.5) / 25) ** 2
        + ((z - 23.5) / 20) ** 2
        <= 1
    )
    base = 0.25 + 0.5 * np.exp(
        -(
            ((x - 31.5) / 24) ** 2
            + ((y - 31.5) / 22) ** 2
            + ((z - 23.5) / 18) ** 2
        )
    )
    base *= brain

    lesion1 = (
        ((x - 23) / 6) ** 2 + ((y - 38) / 5) ** 2 + ((z - 24) / 5) ** 2 <= 1
    )
    lesion2 = (
        ((x - 42) / 4) ** 2 + ((y - 25) / 4) ** 2 + ((z - 30) / 4) ** 2 <= 1
    )
    lesions = lesion1 | lesion2
    noise = gaussian_filter(rng.normal(0, 0.025, shape), 0.7)

    dwi = (base + noise + 0.65 * lesions) * brain
    adc = (0.75 * base + noise - 0.32 * lesions) * brain
    flair = (0.9 * base + noise + 0.32 * lesions) * brain
    affine = np.array(
        [
            [1.5, 0, 0, -48],
            [0, 1.5, 0, -48],
            [0, 0, 2.0, -48],
            [0, 0, 0, 1],
        ],
        dtype=float,
    )

    dwi = dwi.astype(np.float32)
    adc = adc.astype(np.float32)
    flair = flair.astype(np.float32)
    outputs: dict[str, Path] = {}
    for name, array in {"DWI": dwi, "ADC": adc, "FLAIR": flair}.items():
        path = output_dir / f"demo_{name.lower()}.nii.gz"
        outputs[name] = _save_deterministic_volume(
            path,
            array,
            affine,
            dtype=np.float32,
        )
    outputs["MASK"] = _save_deterministic_volume(
        output_dir / "demo_mask.nii.gz",
        _expected_demo_mask(dwi),
        affine,
        dtype=np.uint8,
    )
    return outputs


if __name__ == "__main__":
    generate_demo_case(Path(__file__).resolve().parents[3] / "sample_data")
