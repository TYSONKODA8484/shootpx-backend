"""add team soft-delete columns

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-29 00:00:00.000000

Adds Team.is_active/deleted_at (see Team's docstring for why deleting a
team is a soft delete, not a real DELETE — 7+ tables FK to teams.id with no
cascade rules defined). Schema-only: every existing team defaults to
is_active=true, deleted_at=NULL, i.e. "not deleted", which is correct for
every row that exists before this feature did.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("teams", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "deleted_at")
    op.drop_column("teams", "is_active")
