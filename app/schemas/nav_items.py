from pydantic import BaseModel, ConfigDict


class NavItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    is_active: bool

