import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.db import Base


class TeamRole(str, enum.Enum):
    owner = "owner"
    editor = "editor"


def new_id() -> str:
    return str(uuid.uuid4())


class Team(Base):
    """The `teams` table — a workspace. Its id is app-generated (nothing
    external hands us one)."""

    __tablename__ = "teams"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
