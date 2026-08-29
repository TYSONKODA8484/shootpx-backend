"""swap product listing to the real fal pipeline

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-08-30 00:00:00.000000

c7d8e9f0a1b2 marked product_photoshoot 'live' for the frontend's "Product
Listing" tool. That was wrong: product_photoshoot is still wired to
MockAIProvider (fake output), while catalog_photoshoot -- a different
feature_type -- already has the real fal.ai pipeline (see the on-model-
shots/catalog-photoshoot work) and was marked coming_soon.

Someone could have paid credits for "Product Listing" and gotten a fake
image. This flips which of the two is live:
  - catalog_photoshoot  -> live         (real fal.ai pipeline; this is what
                                          the frontend's "Product Listing"
                                          should actually call)
  - product_photoshoot  -> coming_soon  (mock-only; not customer-safe yet)

feature_type strings are NOT renamed -- that's a primary key already
referenced by existing GenerationJob rows, the tool_config table, and the
CMS registry, and the frontend already joins on feature_type rather than
display_name. Only the label a human sees changes, and only for the two
tools whose backend name didn't match the frontend's customer-facing copy:
  - catalog_photoshoot display_name:  "Catalog Photoshoot"  -> "Product Listing"
  - creative_photoshoot display_name: "Creative Photoshoot" -> "Product Staging"
(app/tools/catalog_photoshoot.py and app/tools/creative_photoshoot.py's
ToolSpec.display_name were updated to match -- sync_tools_to_db overwrites
display_name from code on every boot, so this migration's UPDATE is just to
make GET /tools correct immediately, without waiting for the next deploy.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE tools SET status = 'live' WHERE feature_type = 'catalog_photoshoot'"))
    conn.execute(sa.text("UPDATE tools SET status = 'coming_soon' WHERE feature_type = 'product_photoshoot'"))
    conn.execute(sa.text("UPDATE tools SET display_name = 'Product Listing' WHERE feature_type = 'catalog_photoshoot'"))
    conn.execute(sa.text("UPDATE tools SET display_name = 'Product Staging' WHERE feature_type = 'creative_photoshoot'"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE tools SET status = 'coming_soon' WHERE feature_type = 'catalog_photoshoot'"))
    conn.execute(sa.text("UPDATE tools SET status = 'live' WHERE feature_type = 'product_photoshoot'"))
    conn.execute(sa.text("UPDATE tools SET display_name = 'Catalog Photoshoot' WHERE feature_type = 'catalog_photoshoot'"))
    conn.execute(sa.text("UPDATE tools SET display_name = 'Creative Photoshoot' WHERE feature_type = 'creative_photoshoot'"))
