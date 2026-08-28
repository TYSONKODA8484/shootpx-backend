"""add team_invites expiry column

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-29 03:00:00.000000

Adds TeamInvite.expires_at (see TeamInvite's/team_controller.accept_invite's
docstrings — 48-hour invite expiry, per-invite acceptance replacing the old
"any login accepts everything pending" behavior). Existing rows (from
before this feature existed) are backfilled as created_at + 48h, same rule
new rows get going forward — an old already-accepted invite doesn't care
about this value at all (accept_invite checks accepted_at first), and an
old still-pending invite just inherits the same expiry window rather than
being treated as a special case.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("team_invites", sa.Column("expires_at", sa.DateTime(), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE team_invites SET expires_at = created_at + interval '48 hours' WHERE expires_at IS NULL"))
    op.alter_column("team_invites", "expires_at", nullable=False)


def downgrade() -> None:
    op.drop_column("team_invites", "expires_at")
