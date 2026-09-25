"""Lazy bridge to the modern BrainLesion stroke_segmentor package."""

from __future__ import annotations

from pathlib import Path


def run_deepisles(dwi: Path, adc: Path, flair: Path, output_dir: Path) -> Path:
    """Run the DeepISLES NVAUTO model exposed by stroke_segmentor.

    FLAIR remains part of the NeuroAnnotate case/review workspace, but this
    maintained inference package intentionally uses only DWI and ADC.
    """
    del flair

    # Keep downloaded checkpoints outside the container layer so a hospital
    # installation can initialize once and then run without re-downloading them.
    from stroke_segmentor import zenodo

    zenodo.WEIGHTS_FOLDER = Path("/models/weights")

    from stroke_segmentor.inferer import Inferer

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "lesion_msk.nii.gz"
    Inferer().infer(
        adc_path=adc,
        dwi_path=dwi,
        segmentation_path=output,
    )
    if not output.is_file():
        raise RuntimeError("Stroke segmentor did not create a segmentation mask")
    return output
