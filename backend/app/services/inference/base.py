from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CaseInput:
    case_id: str
    modality_paths: dict[str, Path]


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    model_name: str
    model_version: str
    service_version: str
    available: bool


@dataclass(frozen=True)
class ProviderResult:
    mask_path: Path
    provider: str
    model_name: str
    model_version: str
    service_version: str
    configuration: dict[str, object]
    runtime: dict[str, object]


class ProviderOutputPersistenceError(Exception):
    """Raised when a provider cannot write its output artifact."""


class ProviderUnavailableError(Exception):
    """Raised when the configured provider cannot be reached."""


class ProviderRuntimeError(Exception):
    """Raised when a provider returns an invalid or failed result."""


class SegmentationProvider(Protocol):
    name: str
    def info(self) -> ProviderInfo: ...
    def segment(self, case: CaseInput, output_path: Path) -> ProviderResult: ...
