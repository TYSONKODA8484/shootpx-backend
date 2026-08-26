"""seed category a tool costs

Revision ID: 4e95a697f741
Revises: 3adad199e5b6
Create Date: 2026-08-26 12:48:50.813662

Data-only, same pattern as 3adad199e5b6_register_product_import_as_a_.
The app/tools/ registry (app/tools/product_photoshoot.py etc.) will
auto-insert these rows too via sync_tools_to_db() — and that can genuinely
happen BEFORE this migration ever runs, since app/main.py calls
sync_tools_to_db() against the real DATABASE_URL at import time, and that
same import path is also hit by pytest importing app.main (its get_db
override only swaps the request-scoped session, not this module-level
call). Whichever runs first inserts these rows with credit_cost defaulted
to 1 (the Tool model's column default). Because of that, this migration
UPSERTs (ON CONFLICT DO UPDATE) rather than skip-if-exists — a plain
existence guard would silently leave product_motion at 1 forever if
sync_tools_to_db happened to run first, which is exactly the bug this
migration hit during development.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e95a697f741'
down_revision: Union[str, Sequence[str], None] = '3adad199e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TOOLS = [
    # (feature_type, display_name, output_media_type, credit_cost)
    ("product_photoshoot", "Product Photoshoot", "image", 1),
    ("background_swap", "Background Swap", "image", 1),
    ("mockup_studio", "Mockup Studio", "image", 1),
    ("flat_lay_angles", "Flat Lay / Angles", "image", 1),
    ("magic_erase", "Magic Erase", "image", 1),
    ("inpaint", "Inpaint", "image", 1),
    ("relight_shadows", "Relight & Shadows", "image", 1),
    ("upscale_4k", "Upscale 4K", "image", 1),
    ("resize_outpaint", "Resize & Outpaint", "image", 1),
    ("product_motion", "Product Motion", "video", 4),
]


def upgrade() -> None:
    conn = op.get_bind()
    for feature_type, display_name, media_type, cost in TOOLS:
        conn.execute(sa.text("""
            INSERT INTO tools (feature_type, display_name, output_media_type, credit_cost, is_active, created_at, updated_at)
            VALUES (:ft, :name, :media_type, :cost, true, now(), now())
            ON CONFLICT (feature_type) DO UPDATE
            SET credit_cost = EXCLUDED.credit_cost,
                display_name = EXCLUDED.display_name,
                output_media_type = EXCLUDED.output_media_type,
                updated_at = now()
        """), {"ft": feature_type, "name": display_name, "media_type": media_type, "cost": cost})


def downgrade() -> None:
    conn = op.get_bind()
    for feature_type, _, _, _ in TOOLS:
        conn.execute(sa.text("DELETE FROM tools WHERE feature_type = :ft"), {"ft": feature_type})
