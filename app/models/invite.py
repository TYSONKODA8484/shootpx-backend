from datetime import timedelta

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.core.time import utc_now
from app.models.team import new_id

INVITE_EXPIRY = timedelta(hours=48)


class TeamInvite(Base):
    """A pending invite — created for EVERY add_member call, regardless of
    whether the invited email already has an account or not. Adding
    someone to a team is never immediate: a TeamMembership row only gets
    created when THIS SPECIFIC invite's link is clicked and accepted
    (team_controller.accept_invite), matched by id, not swept in bulk on
    any login. `accepted_at` stays NULL until that happens.

    expires_at is set at creation (created_at + INVITE_EXPIRY, 48 hours) —
    accept_invite refuses an invite past this point even if the link is
    still technically valid Firebase-side; the person has to be re-invited.
    """

    __tablename__ = "team_invites"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    email = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)  # 'owner' | 'editor'
    invited_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)

    team = relationship("Team", back_populates="invites")
