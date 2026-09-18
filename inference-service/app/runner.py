"""Lazy bridge to the pinned DeepISLES installation inside the GPU image."""

from __future__ import annotations

from pathlib import Path


class DeepISLESRunnerError(RuntimeError):
    """The pinned model did not produce one unambiguous final mask."""


def locate_final_ensemble_mask(output_dir: Path) -> Path:
    """Locate the sole native final mask copied by pinned DeepISLES output cleanup."""
    candidates = sorted(Path(output_dir).rglob("lesion_msk.nii.gz"))
    if len(candidates) != 1:
        raise DeepISLESRunnerError("Expected exactly one final DeepISLES lesion mask")
    return candidates[0]


def run_deepisles(dwi: Path, adc: Path, flair: Path, output_dir: Path) -> Path:
    """Run the pinned ensemble with the v1 native-DWI output flags."""
    from src.isles22_ensemble import IslesEnsemble

    model = IslesEnsemble()
    model.predict_ensemble(
        ensemble_path="/opt/deepisles",
        input_dwi_path=str(dwi),
        input_adc_path=str(adc),
        input_flair_path=str(flair),
        output_path=str(output_dir),
        skull_strip=False,
        fast=False,
        save_team_outputs=False,
        results_mni=False,
        parallelize=True,
    )
    return locate_final_ensemble_mask(output_dir)
