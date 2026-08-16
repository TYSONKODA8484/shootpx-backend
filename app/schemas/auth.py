from pydantic import BaseModel, EmailStr


class SessionCreate(BaseModel):
    id_token: str  # the Firebase ID token the frontend got from Firebase Auth


class EmailLinkRequest(BaseModel):
    email: EmailStr
    continue_url: str  # where the link should land — the page that finishes sign-in


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None

    class Config:
        from_attributes = True
