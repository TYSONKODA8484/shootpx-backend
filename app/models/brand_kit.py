from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.core.db import Base
from app.models.team import new_id


class BrandKit(Base):
    """One per team (UNIQUE team_id) — the Brand page's palette/type. Marks
    (logo variants) are a separate table (BrandMark, below) since a kit has
    many of them."""

    __tablename__ = "brand_kits"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False, unique=True)
    palette = Column(JSON, nullable=False, default=list)  # list[str] of hex colors
    heading_font = Column(String, nullable=True)
    body_font = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    marks = relationship("BrandMark", back_populates="brand_kit", cascade="all, delete-orphan")


class BrandMark(Base):
    """Links a BrandKit to an Asset (kind='upload') that IS the mark — this
    table just carries the link + a free-label variant ("light"/"dark"/...).
    Deleting a BrandMark row does not delete the underlying Asset — that's
    a separate, explicit DELETE /assets/{id} if the file itself should go
    too (see B1)."""

    __tablename__ = "brand_marks"

    id = Column(String, primary_key=True, default=new_id)
    brand_kit_id = Column(String, ForeignKey("brand_kits.id"), nullable=False)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=False)
    variant = Column(String, nullable=False, default="default")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    brand_kit = relationship("BrandKit", back_populates="marks")
    asset = relationship("Asset")
