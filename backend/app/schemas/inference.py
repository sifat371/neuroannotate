from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InferenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = "demo"


class InferenceJobRead(BaseModel):
    id: str
    case_id: str
    provider: str
    model_name: str
    model_version: str
    service_version: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failure_category: str | None
    error_message: str | None
    segmentation_id: str | None
    provenance: dict[str, object]


class ProviderInfoRead(BaseModel):
    name: str
    model_name: str
    model_version: str
    service_version: str
    available: bool


class InferenceRead(BaseModel):
    id: str
    case_id: str
    provider: str
    status: str
    metadata: dict[str, str | int | float | bool]
    created_at: datetime
