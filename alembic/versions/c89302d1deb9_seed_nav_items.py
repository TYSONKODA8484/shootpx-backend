"""seed nav items

Revision ID: c89302d1deb9
Revises: 47a66511d405
Create Date: 2026-08-26 16:11:00.000000

Data-only. Seeds the 12 known Studio sidebar pages, confirmed against the
actual UI (screenshots) rather than guessed from route names alone.
"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c89302d1deb9'
down_revision: Union[str, Sequence[str], None] = '47a66511d405'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAV_ITEMS = [
    ("home", "Home"),
    ("upload", "Upload"),
    ("photoshoot", "Photoshoot"),
    ("refine", "Refine"),
    ("video", "Video"),
    ("batch", "Batch"),
    ("tools", "Tools"),
    ("templates", "Templates"),
    ("library", "Library"),
    ("brand", "Brand Kit"),
    ("activity", "Activity"),
    ("prefs", "Preferences"),
]

nav_items_table = sa.table(
    "nav_items",
    sa.column("key", sa.String),
    sa.column("label", sa.String),
    sa.column("is_active", sa.Boolean),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()
    for key, label in NAV_ITEMS:
        existing = conn.execute(sa.text("SELECT 1 FROM nav_items WHERE key = :key"), {"key": key}).first()
        if existing:
            continue
        conn.execute(nav_items_table.insert().values(
            key=key, label=label, is_active=True, created_at=now, updated_at=now,
        ))


def downgrade() -> None:
    conn = op.get_bind()
    for key, _label in NAV_ITEMS:
        conn.execute(sa.text("DELETE FROM nav_items WHERE key = :key"), {"key": key})
