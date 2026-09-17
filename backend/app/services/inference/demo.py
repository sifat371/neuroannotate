from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import ndimage

from app.services.inference.base import (
    CaseInput,
    ProviderInfo,
    ProviderOutputPersistenceError,
    ProviderResult,
)
from app.services.nifti_codec import load_volume, save_volume


class DemoSegmentationProvider:
    name = "demo"

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, "deterministic_demo_threshold", "2", "0.1.0", True)

    def segment(self, case: CaseInput, output_path: Path) -> ProviderResult:
        started = perf_counter()
        dwi_img = load_volume(case.modality_paths["DWI"])
        dwi = np.asarray(dwi_img.data, dtype=np.float32)
        finite = np.isfinite(dwi)
        if not finite.any():
            mask = np.zeros(dwi.shape, dtype=np.uint8)
        else:
            dwi_threshold = float(np.percentile(dwi[finite], 92))
            mask = (dwi >= dwi_threshold) & finite
            labels, count = ndimage.label(mask)
            if count:
                sizes = np.bincount(labels.ravel())
                keep = sizes >= 8
                keep[0] = False
                mask = keep[labels]
            mask = mask.astype(np.uint8)
        try:
            save_volume(output_path, mask, dwi_img.affine, dtype=np.uint8)
        except OSError as exc:
            raise ProviderOutputPersistenceError(
                "Could not write demo segmentation output"
            ) from exc
        info = self.info()
        return ProviderResult(
            mask_path=output_path,
            provider=self.name,
            model_name=info.model_name,
            model_version=info.model_version,
            service_version=info.service_version,
            configuration={
                "dwi_percentile": 92,
                "input_modalities": ["DWI"],
                "minimum_component_voxels": 8,
                "clinical_use": False,
            },
            runtime={"duration_seconds": perf_counter() - started, "device": "cpu"},
        )
