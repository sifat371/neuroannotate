from datetime import datetime

from pydantic import BaseModel


class RevisionRead(BaseModel):
    id: str
    case_id: str
    source_inference_id: str
    source_segmentation_id: str
    parent_revision_id: str | None
    sha256: str | None
    edit_stats: dict[str, int | float]
    note: str | None
    created_at: datetime
