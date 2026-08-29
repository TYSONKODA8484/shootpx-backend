"""restrict live tools to launch set

Revision ID: c7d8e9f0a1b2
Revises: 5c0e6cbe2b23
Create Date: 2026-08-30 00:00:00.000000

Data-only migration, same pattern as d4e5f6a7b8c9 (which first introduced
Tool.status). That migration only flipped the 8 tools the frontend was
already badging SOON; everything else (including background_swap,
catalog_photoshoot, mockup_studio) defaulted to 'live'.

Product now wants exactly 4 tools live at once, matching the frontend's
current tool grid / nav dropdown:
  - product_photoshoot   ("Product Listing")
  - creative_photoshoot  ("Product Staging")
  - on_model_shots       ("Model Shoot")
  - recolor              ("Recolor")

Every other registered feature_type (including the 3 that were live until
now — background_swap, catalog_photoshoot, mockup_studio) moves to
'coming_soon'. Explicit both ways (sets LIVE_FEATURE_TYPES to 'live' too,
not just the rest to 'coming_soon') so this migration is idempotent and
correct regardless of whatever status each row already has — same reason
4e95a697f741 used an UPSERT instead of an existence guard.

is_active is untouched: every tool stays visible on GET /tools (frontend
renders the non-live ones with a SOON badge), none are hidden outright.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = '5c0e6cbe2b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LIVE_FEATURE_TYPES = (
    "product_photoshoot",
    "creative_photoshoot",
    "on_model_shots",
    "recolor",
)

# Every other feature_type known to the registry as of this migration.
# Kept as an explicit list (not "everything not in LIVE_FEATURE_TYPES")
# so a future new tool defaults to whatever Tool.status's column default
# is ('live') rather than being silently swept into coming_soon here.
COMING_SOON_FEATURE_TYPES = (
    "background_swap",
    "catalog_photoshoot",
    "flat_lay_angles",
    "inpaint",
    "magic_erase",
    "mockup_studio",
    "product_motion",
    "relight_shadows",
    "resize_outpaint",
    "ugc",
    "upscale_4k",
)


def _set_status(conn, feature_types, status):
    conn.execute(
        sa.text("UPDATE tools SET status = :status WHERE feature_type IN :feature_types").bindparams(
            sa.bindparam("feature_types", expanding=True)
        ),
        {"status": status, "feature_types": list(feature_types)},
    )


def upgrade() -> None:
    conn = op.get_bind()
    _set_status(conn, LIVE_FEATURE_TYPES, "live")
    _set_status(conn, COMING_SOON_FEATURE_TYPES, "coming_soon")


def downgrade() -> None:
    conn = op.get_bind()
    # Restores exactly what d4e5f6a7b8c9 had left standing: the 3 tools
    # this migration newly moved to coming_soon go back to live; the 8
    # that were already coming_soon before this migration stay that way.
    _set_status(conn, ("background_swap", "catalog_photoshoot", "mockup_studio"), "live")
