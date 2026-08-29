from pydantic import BaseModel


class RecolorPromptRequest(BaseModel):
    image_asset_ids: list[str]  # first is the photo being edited, rest are optional references, max 4
    color: str
    description: str = ""  # blank means "let the model name the subject"
    resolution_mode: str = "match_input"  # 'match_input' | 'standard' | 'custom'
    aspect_ratio: str = "1:1"
    custom_width: int | None = None
    custom_height: int | None = None


class RecolorPromptResponse(BaseModel):
    prompt: str
    description: str  # resolved — echoes back what was actually used, even if auto-suggested
    image_urls: list[str]
    labels: list[str]
    image_size: dict | str
