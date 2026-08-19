"""register product_import as a discoverable tool row

Revision ID: 3adad199e5b6
Revises: 53d441e69de6
Create Date: 2026-08-19 18:00:17.617625

Data-only. product_import isn't in the app/tools/ registry (it has no
AIProvider, doesn't go through GenerationJob — see BOOK.md Chapter 14) so
it can't self-register a Tool row via ToolSpec the way on_model_shots/ugc
do at boot. Inserted directly, once, here — this is what makes it show up
in GET /tools and gives it a DB-editable credit_cost/is_active instead of
the hardcoded settings constant it used to have (see Chapter 17's fix).
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3adad199e5b6'
down_revision: Union[str, Sequence[str], None] = '53d441e69de6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FEATURE_TYPE = "product_import"
CREDIT_COST = 5


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT 1 FROM tools WHERE feature_type = :ft"), {"ft": FEATURE_TYPE}
    ).first()
    if existing:
        return
    conn.execute(sa.text("""
        INSERT INTO tools (feature_type, display_name, output_media_type, credit_cost, is_active, created_at, updated_at)
        VALUES (:ft, 'Product Import (URL Pull)', 'product_data', :cost, true, now(), now())
    """), {"ft": FEATURE_TYPE, "cost": CREDIT_COST})


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM tools WHERE feature_type = 'product_import'"))
