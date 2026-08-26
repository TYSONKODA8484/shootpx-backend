from pydantic import BaseModel


class BrandMarkOut(BaseModel):
    id: str
    asset_id: str
    variant: str
    url: str


class BrandKitOut(BaseModel):
    id: str
    team_id: str
    palette: list[str]
    heading_font: str | None
    body_font: str | None
    marks: list[BrandMarkOut]


class BrandKitUpdate(BaseModel):
    palette: list[str]
    heading_font: str | None = None
    body_font: str | None = None


class AssetSavedProductUpdate(BaseModel):
    is_saved_product: bool
