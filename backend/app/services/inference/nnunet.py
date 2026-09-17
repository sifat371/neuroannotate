from pathlib import Path

from app.core.errors import ApiError
from app.services.inference.base import CaseInput, ProviderInfo, ProviderResult


class NNUNetProvider:
    name = "nnunet"

    def __init__(self, model_dir: Path | None = None):
        self.model_dir = model_dir

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, "nnunet", "unconfigured", "0.1.0", False)

    def segment(self, case: CaseInput, output_path: Path) -> ProviderResult:
        if self.model_dir is None or not self.model_dir.exists():
            raise ApiError(
                503,
                "nnunet_unavailable",
                "nnU-Net provider is configured but no model package is available",
            )
        raise ApiError(
            503,
            "nnunet_unavailable",
            "nnU-Net adapter is scaffolded but inference is not enabled in v1",
        )
