from app.core.config import settings
from app.core.errors import ApiError
from app.services.inference.base import SegmentationProvider
from app.services.inference.demo import DemoSegmentationProvider
from app.services.inference.nnunet import NNUNetProvider

PROVIDER_NAMES = ("demo", "nnunet")


def get_provider(name: str | None = None) -> SegmentationProvider:
    name = name or settings.inference_provider
    if name == "demo":
        return DemoSegmentationProvider()
    if name == "nnunet":
        return NNUNetProvider()
    raise ApiError(500, "unknown_provider", "Configured segmentation provider is unknown")


def list_providers() -> list[SegmentationProvider]:
    """Return each configured provider in stable display order."""
    return [get_provider(name) for name in PROVIDER_NAMES]
