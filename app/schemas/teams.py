from pydantic import BaseModel, EmailStr, field_validator

from app.models.team import TeamRole


class TeamCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v


class TeamUpdate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v


class TeamOut(BaseModel):
    id: str
    name: str
    role: TeamRole  # the requesting user's role in this team


class MemberAdd(BaseModel):
    email: EmailStr
    role: TeamRole = TeamRole.editor
    continue_url: str  # where the invite email's sign-in link should land, if they don't have an account yet


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str | None = None
    avatar_url: str | None = None
    role: TeamRole


class InviteOut(BaseModel):
    id: str
    email: str
    role: TeamRole
    created_at: str
    expires_at: str


class AddMemberResult(BaseModel):
    """Always "invited" now — add_member never adds someone immediately,
    it always creates a pending invite and emails it (see
    team_controller.add_member's docstring). status is kept as a field
    (rather than dropped) so an older frontend build checking
    result.status === "invited" doesn't need to change to keep working."""
    status: str = "invited"
    invite: InviteOut
