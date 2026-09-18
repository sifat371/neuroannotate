from datetime import datetime

from pydantic import BaseModel


class ExportCreate(BaseModel):
    revision_id: str


class ExportRead(BaseModel):
    id: str
    case_id: str
    revision_id: str
    mask_sha256: str
    created_at: datetime
    mask_url: str
    provenance_url: str
    bundle_url: str
