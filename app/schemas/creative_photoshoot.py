from pydantic import BaseModel


class CreativePromptRequest(BaseModel):
    product_asset_ids: list[str]
    idea_tags: list[str] = []
    user_prompt: str | None = None
    resolution_mode: str = "standard"
    aspect_ratio: str = "3:4"
    custom_width: int | None = None
    custom_height: int | None = None


class CreativePromptResponse(BaseModel):
    final_prompt: str
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
