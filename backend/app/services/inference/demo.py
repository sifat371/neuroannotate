from pathlib import Path

import numpy as np
from scipy import ndimage

from app.services.inference.base import CaseInput, SegmentationResult
from app.services.nifti_codec import load_volume, save_volume


class DemoSegmentationProvider:
    name = "demo"

    def segment(self, case: CaseInput, output_path: Path) -> SegmentationResult:
        dwi_img = load_volume(case.modality_paths["DWI"])
        adc_img = load_volume(case.modality_paths["ADC"])
        dwi = np.asarray(dwi_img.data, dtype=np.float32)
        adc = np.asarray(adc_img.data, dtype=np.float32)
        finite = np.isfinite(dwi) & np.isfinite(adc)
        if not finite.any():
            mask = np.zeros(dwi.shape, dtype=np.uint8)
        else:
            dwi_threshold = float(np.percentile(dwi[finite], 92))
            adc_threshold = float(np.percentile(adc[finite], 45))
            mask = ((dwi >= dwi_threshold) & (adc <= adc_threshold) & finite)
            labels, count = ndimage.label(mask)
            if count:
                sizes = np.bincount(labels.ravel())
                keep = sizes >= 8
                keep[0] = False
                mask = keep[labels]
            mask = mask.astype(np.uint8)
        save_volume(output_path, mask, dwi_img.affine, dtype=np.uint8)
        return SegmentationResult(
            mask_path=output_path,
            provider=self.name,
            metadata={"algorithm": "deterministic_demo_threshold", "clinical_use": False},
        )
