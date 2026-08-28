from pydantic import BaseModel, ConfigDict

from app.models.asset import AssetKind, MediaType


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    created_by: str
    kind: AssetKind
    media_type: MediaType
    storage_key: str
    url: str
    is_saved_product: bool

class AssetListOut(BaseModel):
    total: int
    assets: list[AssetOut]


class AssetUpdate(BaseModel):
    is_saved_product: bool


class AssetVersionEntry(BaseModel):
    asset_id: str
    url: str
    label: str
    created_at: str  # isoformat


class AssetVersionsOut(BaseModel):
    versions: list[AssetVersionEntry]  # ordered newest-first
