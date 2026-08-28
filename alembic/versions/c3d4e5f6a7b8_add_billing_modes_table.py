"""add billing_modes table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-28 20:00:00.000000

Adds the billing_modes table (app/models/billing_mode.py) and seeds its 2
fixed rows, both is_active=true — same pattern as 47a66511d405/
c89302d1deb9 (nav_items' table + seed), just split across create+seed here
since it's one small migration rather than two. Lets an admin (via the CMS)
independently hide the pricing page's Subscription or Credits tab without a
deploy — GET /billing/config is what a well-behaved frontend reads before
deciding which tab(s) to render.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MODES = [
    ("subscriptions", "Subscriptions"),
    ("credits", "Credit top-ups"),
]


def upgrade() -> None:
    op.create_table(
        "billing_modes",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    conn = op.get_bind()
    for key, label in MODES:
        conn.execute(sa.text("""
            INSERT INTO billing_modes (key, label, is_active, created_at, updated_at)
            VALUES (:key, :label, true, now(), now())
        """), {"key": key, "label": label})


def downgrade() -> None:
    op.drop_table("billing_modes")
