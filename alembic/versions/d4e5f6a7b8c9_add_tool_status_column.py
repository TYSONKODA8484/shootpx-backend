"""add status column to tools, seed coming_soon set

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-28 22:00:00.000000

Adds Tool.status (see Tool's docstring for the is_active-vs-status split)
and sets it to match exactly what the frontend's SHOW_COMING_SOON flag
already shows today — moving that decision server-side, per-tool, instead
of one global frontend boolean. Every row defaults to 'live'; only the
tools the frontend currently badges SOON are flipped to 'coming_soon' here.

Note: the frontend's list also mentions "Batch Studio" as coming soon —
there is no tools row for it (nothing in app/tools/*.py registers that
feature_type), so it's left alone here; it's a frontend-only concept for
now, not a gap in this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMING_SOON_FEATURE_TYPES = (
    "magic_erase",
    "inpaint",
    "relight_shadows",
    "upscale_4k",
    "resize_outpaint",
    "flat_lay_angles",
    "product_motion",
    "ugc",
)


def upgrade() -> None:
    op.add_column("tools", sa.Column("status", sa.String(), nullable=False, server_default="live"))

    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE tools SET status = 'coming_soon' WHERE feature_type IN :feature_types
    """).bindparams(sa.bindparam("feature_types", expanding=True)), {"feature_types": list(COMING_SOON_FEATURE_TYPES)})


def downgrade() -> None:
    op.drop_column("tools", "status")
