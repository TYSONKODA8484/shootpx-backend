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


class AddMemberResult(BaseModel):
    status: str  # "added" | "invited"
    member: MemberOut | None = None
    invite: InviteOut | None = None
