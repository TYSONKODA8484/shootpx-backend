from pydantic import BaseModel, ConfigDict


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature_type: str
    display_name: str
    output_media_type: str
    status: str  # 'live' | 'coming_soon' — see Tool's docstring; a
    # 'coming_soon' tool is still listed here (frontend shows a SOON
    # badge) but rejected at /generate, same as an inactive tool
    credit_cost: int

