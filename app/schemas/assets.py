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


class AssetListOut(BaseModel):
    total: int
    assets: list[AssetOut]


class AssetUpdate(BaseModel):
    is_saved_product: bool
