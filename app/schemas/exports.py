from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    presets: list[str] = Field(min_length=1, max_length=5)


class ExportResultItem(BaseModel):
    preset: str
    asset_id: str
    url: str


class ExportResponse(BaseModel):
    exports: list[ExportResultItem]
