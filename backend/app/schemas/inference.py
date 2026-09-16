from datetime import datetime

from pydantic import BaseModel


class InferenceRead(BaseModel):
    id: str
    case_id: str
    provider: str
    status: str
    metadata: dict[str, str | int | float | bool]
    created_at: datetime
