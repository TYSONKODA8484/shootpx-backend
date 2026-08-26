from pydantic import BaseModel


class NavItemOut(BaseModel):
    key: str
    label: str
    is_active: bool

    class Config:
        from_attributes = True
