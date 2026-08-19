from pydantic import BaseModel


class ToolOut(BaseModel):
    feature_type: str
    display_name: str
    output_media_type: str
    credit_cost: int

    class Config:
        from_attributes = True
