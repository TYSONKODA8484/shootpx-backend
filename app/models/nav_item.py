from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String

from app.core.db import Base


class NavItem(Base):
    """One row per Studio sidebar page — a pure show/hide switch, same
    spirit as Tool.is_active but for whole pages instead of individual
    tools. The 12 rows are fixed (seeded by migration, matching the
    Studio's own routing); an admin toggles is_active, nothing creates or
    deletes rows here."""

    __tablename__ = "nav_items"

    key = Column(String, primary_key=True)  # matches the Studio's own
    # route segment (/app/<key>) — the contract with the frontend
    label = Column(String, nullable=False)  # display-only, for the CMS's
    # own list view; the frontend keeps its own hardcoded label
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
