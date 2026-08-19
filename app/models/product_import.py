import enum
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String

from app.core.db import Base
from app.models.team import new_id


class ProductImportStatus(str, enum.Enum):
    processing = "processing"
    done = "done"
    failed = "failed"


PRODUCT_IMPORT_FEATURE_TYPE = "product_import"  # the tools.feature_type this
# domain is registered under (seeded by migration, not the app/tools/
# registry — product imports don't go through AIProvider/GenerationJob, so
# they can't self-register via ToolSpec the way on_model_shots/ugc do; this
# is a plain Tool row inserted directly, existing purely for GET /tools
# discovery and DB-editable credit_cost/is_active. sync_tools_to_db() never
# touches it (it only upserts rows matching the in-memory registry).


class ProductImport(Base):
    """One row per 'scrape this product URL' request — a separate table
    from GenerationJob on purpose: its output doesn't fit that shape
    (several images, not one, plus real structured data: name, price,
    description, theme colors). Scraping goes through the product-scrapper
    service (core/product_scraper_client.py) instead of AIProvider — a
    different external system, with its own submit/poll shape and its own
    settings (PRODUCT_SCRAPER_URL etc., core/config.py), but the same
    submit-then-poll-via-arq-Retry pattern as generation jobs (see
    app/worker.py's run_product_import) for the same reason: a scrape can
    take 2-25s and must never block a worker slot for that long.
    """

    __tablename__ = "product_imports"

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("teams.id"), nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    source_url = Column(String, nullable=False)
    status = Column(String, default=ProductImportStatus.processing.value, nullable=False)
    external_job_id = Column(String, nullable=True)  # the scraper service's
    # own job id (from its POST /extract), null until submitted — same
    # round-trip-through-the-row pattern as GenerationJob.external_job_id.

    # Structured fields pulled out of the scraper's result for easy
    # querying/display. raw_result below keeps everything, including
    # whatever isn't promoted to its own column (description_bullets,
    # source_layers, confidence, ...).
    product_name = Column(String, nullable=True)
    product_description = Column(String, nullable=True)
    brand_name = Column(String, nullable=True)
    price = Column(String, nullable=True)  # kept as the scraper's raw
    # string ("$49.99", "₹1,299") rather than parsed to a number — currency
    # and formatting vary too much across sites to normalize reliably here.
    theme_colors = Column(JSON, nullable=True)  # list[str] of hex colors
    raw_result = Column(JSON, nullable=True)  # the scraper's full
    # ExtractionResult, verbatim, once done — nothing is lost even though
    # only some fields are promoted to their own columns above.

    credit_cost = Column(Integer, nullable=True)  # resolved and locked in at
    # submission time (settings.PRODUCT_IMPORT_CREDIT_COST), same "never
    # recomputed at completion" principle as GenerationJob.credit_cost —
    # see BOOK.md Chapter 17.
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
