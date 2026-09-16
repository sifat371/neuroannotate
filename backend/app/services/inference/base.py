from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CaseInput:
    case_id: str
    modality_paths: dict[str, Path]


@dataclass(frozen=True)
class SegmentationResult:
    mask_path: Path
    provider: str
    metadata: dict[str, str | int | float | bool]


class SegmentationProvider(Protocol):
    name: str
    def segment(self, case: CaseInput, output_path: Path) -> SegmentationResult: ...
