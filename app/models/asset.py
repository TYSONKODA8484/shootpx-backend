import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.db import Base
from app.models.team import new_id


class AssetKind(str, enum.Enum):
    upload = "upload"
    generated = "generated"


class MediaType(str, enum.Enum):
    image = "image"
    video = "video"


class Asset(Base):
    """One row = one file, always — whether it came in via upload or came
    out of a generation job. Scoped directly to a team (no project layer —
    the flow is "pick a tool, generate," never "create a project first").
    team_id says who can access it; created_by says who actually did it —
    for a generated asset, that's whoever triggered the job, not the AI.
    storage_key is what Storage.save()/url_for() use internally; url is the
    ready-to-use link."""

    __tablename__ = "assets"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    kind = Column(String, nullable=False)  # 'upload' | 'generated'
    media_type = Column(String, nullable=False)  # 'image' | 'video'
    storage_key = Column(String, nullable=False)
    url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
