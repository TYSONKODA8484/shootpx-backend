from pydantic import BaseModel


class CatalogShotsRequest(BaseModel):
    product_asset_ids: list[str]
    num_outputs: int = 6
    resolution_mode: str = "standard"
    aspect_ratio: str = "1:1"
    custom_width: int | None = None
    custom_height: int | None = None
    user_prompt: str | None = None


class CatalogShotsResponse(BaseModel):
    prompts: list[str]
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
