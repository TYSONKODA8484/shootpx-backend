"""backfill personal teams for existing teamless users

Revision ID: e3d3552b463c
Revises: b55cfad6e50d
Create Date: 2026-08-19 16:39:58.022353

Data-only migration: any user who signed up before personal-team
auto-creation existed (auth_controller.upsert_user_from_firebase /
team_controller.create_personal_team) has zero rows in team_members. This
gives each of them the same "<name>'s Workspace" team, owned by them, that a
new signup gets automatically today.

Written against raw SQL (op.execute), not the ORM models — a data migration
should stay correct even as the models themselves drift later; the exact
shape of `teams`/`team_members` as of THIS migration is what matters, not
whatever app/models/ looks like when this eventually runs.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3d3552b463c'
down_revision: Union[str, Sequence[str], None] = 'b55cfad6e50d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("""
        SELECT u.id, u.name, u.email FROM users u
        LEFT JOIN team_members tm ON tm.user_id = u.id
        WHERE tm.id IS NULL
    """)).fetchall()

    for user_id, name, email in rows:
        team_id = str(uuid.uuid4())
        team_name = f"{name or email.split('@')[0]}'s Workspace"
        conn.execute(sa.text(
            "INSERT INTO teams (id, name, created_at) VALUES (:id, :name, now())"
        ), {"id": team_id, "name": team_name})
        conn.execute(sa.text(
            "INSERT INTO team_members (id, team_id, user_id, role, joined_at) "
            "VALUES (:id, :team_id, :user_id, 'owner', now())"
        ), {"id": str(uuid.uuid4()), "team_id": team_id, "user_id": user_id})


def downgrade() -> None:
    # Documented no-op — nothing marks these teams as "backfilled" rather
    # than genuinely user-created (a deliberate choice, see the design spec),
    # so there is nothing to reliably reverse.
    pass
