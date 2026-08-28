import enum
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.core.time import utc_now


class TeamRole(str, enum.Enum):
    owner = "owner"
    editor = "editor"


def new_id() -> str:
    return str(uuid.uuid4())


class Team(Base):
    """The `teams` table — a workspace. Its id is app-generated (nothing
    external hands us one).

    is_active/deleted_at implement a SOFT delete — same is_active
    convention as Tool/NavItem/Plan elsewhere in this codebase, chosen
    deliberately over a hard DELETE because 7+ tables FK to teams.id
    (assets, generation_jobs, payments, credit_transactions, brand_kits,
    product_imports, team_subscriptions) with no cascade rules defined on
    most of them — a real DELETE would either crash on FK constraints or
    require adding destructive cascades that permanently erase generation/
    payment history. Soft delete keeps all of that data intact and
    reversible; team_controller.delete_team is what actually sets these
    two columns (see its docstring for the full contract: what gets
    blocked, what still works)."""

    __tablename__ = "teams"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime, nullable=True)  # set once, alongside is_active=False; never cleared back

    memberships = relationship("TeamMembership", back_populates="team", cascade="all, delete-orphan")
    invites = relationship("TeamInvite", back_populates="team", cascade="all, delete-orphan")


class TeamMembership(Base):
    """The `team_members` join table: which users belong to which teams,
    and with what role in that team. This is what makes "one person, many
    teams" work — a user shows up once per team they're actually on."""

    __tablename__ = "team_members"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, default=TeamRole.editor.value, nullable=False)  # 'owner' | 'editor'
    joined_at = Column(DateTime, default=utc_now, nullable=False)

    team = relationship("Team", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
