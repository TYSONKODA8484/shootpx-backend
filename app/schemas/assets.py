from pydantic import BaseModel

from app.models.asset import AssetKind, MediaType


class AssetOut(BaseModel):
    id: str
    team_id: str
    created_by: str
    kind: AssetKind
    media_type: MediaType
    storage_key: str
    url: str

    class Config:
        from_attributes = True
