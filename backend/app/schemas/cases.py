from datetime import datetime

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
