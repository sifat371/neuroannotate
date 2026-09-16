from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from app.services.nifti_codec import save_volume


def generate_demo_case(output_dir: Path) -> dict[str, Path]:
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

    outputs: dict[str, Path] = {}
    for name, array in {"DWI": dwi, "ADC": adc, "FLAIR": flair}.items():
        path = output_dir / f"demo_{name.lower()}.nii.gz"
        save_volume(path, array.astype(np.float32), affine, dtype=np.float32)
        outputs[name] = path
    return outputs


if __name__ == "__main__":
    generate_demo_case(Path(__file__).resolve().parents[3] / "sample_data")
