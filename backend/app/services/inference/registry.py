from app.core.config import settings
from app.core.errors import ApiError
from app.services.inference.demo import DemoSegmentationProvider
from app.services.inference.nnunet import NNUNetProvider


def get_provider():
    if settings.inference_provider == "demo":
        return DemoSegmentationProvider()
    if settings.inference_provider == "nnunet":
        return NNUNetProvider()
    raise ApiError(500, "unknown_provider", "Configured segmentation provider is unknown")
