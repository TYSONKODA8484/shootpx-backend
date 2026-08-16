from datetime import datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import relationship

from app.core.db import Base


class User(Base):
    """id is Firebase's `uid` — the same identity whether the person signed
    in with Google or with an email link. One row per person, no matter how
    many teams they're on."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)  # Firebase uid
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    memberships = relationship("TeamMembership", back_populates="user", cascade="all, delete-orphan")
