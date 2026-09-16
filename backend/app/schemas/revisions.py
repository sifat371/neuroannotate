from datetime import datetime

from pydantic import BaseModel


class RevisionRead(BaseModel):
    id: str
    case_id: str
    source_inference_id: str
    note: str | None
    created_at: datetime
