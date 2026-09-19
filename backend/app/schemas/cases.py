from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CaseRead(BaseModel):
    id: str
    name: str
    created_at: datetime
    modalities: list[str]
    ready_for_inference: bool
    model_config = ConfigDict(from_attributes=True)


class SourceArtifactRead(BaseModel):
    id: str
    modality: Literal["DWI", "ADC", "FLAIR"]
    original_filename: str
    relative_path: str
    sha256: str | None
    file_size: int | None
    shape: tuple[int, int, int]
    spacing: tuple[float, float, float]
    affine: list[list[float]]
    datatype: str | None
    created_at: datetime


class CaseDetail(CaseRead):
    annotation_space: Literal["DWI"] = "DWI"
    sources: list[SourceArtifactRead]
