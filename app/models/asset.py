import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.core.db import Base
from app.models.team import new_id


class AssetKind(str, enum.Enum):
    upload = "upload"
    generated = "generated"
    imported = "imported"  # came from a ProductImport (product_imports.py),
    # not uploaded by a user or produced by a GenerationJob — a distinct
    # provenance worth keeping separate even though the row shape is the same.


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
    kind = Column(String, nullable=False)  # 'upload' | 'generated' | 'imported'
    media_type = Column(String, nullable=False)  # 'image' | 'video'
    storage_key = Column(String, nullable=False)
    url = Column(String, nullable=False)
    product_import_id = Column(String, ForeignKey("product_imports.id"), nullable=True)  # set
    # only for kind='imported' — which ProductImport's scrape produced this
    # image. Nullable FK on the "many" side (one import can produce several
    # images), same shape as GenerationJob.output_asset_id being the FK on
    # the "one" side for its single-output case.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
