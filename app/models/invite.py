from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.team import new_id


class TeamInvite(Base):
    """A pending invite for someone who doesn't have an account yet (or just
    hasn't been matched up) — keyed by email since that's all we have until
    they actually sign in. The moment ANY login succeeds (Google or email
    link — doesn't matter, both land in `users` the same way), we check this
    table for that email and turn matching rows into real TeamMembership
    rows. `accepted_at` stays NULL until that happens."""

    __tablename__ = "team_invites"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # 'owner' | 'editor'
    invited_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = Column(DateTime, nullable=True)

    team = relationship("Team", back_populates="invites")
