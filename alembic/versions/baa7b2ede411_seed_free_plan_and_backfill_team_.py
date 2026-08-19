"""seed free plan and backfill team subscriptions

Revision ID: baa7b2ede411
Revises: 1fa978c93dc2
Create Date: 2026-08-19 17:10:05.512634

Data-only migration, same philosophy as e3d3552b463c (the personal-teams
backfill): raw SQL, not the ORM, so this stays correct even as the models
drift later. Two things:

1. Seeds exactly one placeholder Free plan — real pricing tiers are
   business data, populated whenever they're decided (see BOOK.md Chapter
   17's non-goals). Values below (5 starter credits, 1 team member) are
   deliberately small/conservative placeholders, not tuned numbers.
2. Backfills every team with no team_subscriptions row yet onto that Free
   plan, granting its credit_allowance synchronously — this migration runs
   AFTER team_subscriptions exists, so literally every team created before
   this moment (which is all of them, this table is brand new) needs this.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'baa7b2ede411'
down_revision: Union[str, Sequence[str], None] = '1fa978c93dc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FREE_PLAN_CREDIT_ALLOWANCE = 5
FREE_PLAN_MAX_TEAM_MEMBERS = 1


def upgrade() -> None:
    conn = op.get_bind()

    free_plan_id = str(uuid.uuid4())
    conn.execute(sa.text("""
        INSERT INTO plans (id, name, billing_cycle, price, currency, credit_allowance,
                            max_team_members, provider, provider_plan_id, is_active, created_at)
        VALUES (:id, 'Free', 'free', NULL, 'INR', :credits, :members, NULL, NULL, true, now())
    """), {"id": free_plan_id, "credits": FREE_PLAN_CREDIT_ALLOWANCE, "members": FREE_PLAN_MAX_TEAM_MEMBERS})

    teams_without_subscription = conn.execute(sa.text("""
        SELECT t.id FROM teams t
        LEFT JOIN team_subscriptions ts ON ts.team_id = t.id
        WHERE ts.id IS NULL
    """)).fetchall()

    for (team_id,) in teams_without_subscription:
        conn.execute(sa.text("""
            INSERT INTO team_subscriptions (id, team_id, plan_id, provider, provider_subscription_id,
                                             status, current_period_end, next_credit_refill_at,
                                             created_at, updated_at)
            VALUES (:id, :team_id, :plan_id, NULL, NULL, 'free', NULL,
                    now() + interval '1 month', now(), now())
        """), {"id": str(uuid.uuid4()), "team_id": team_id, "plan_id": free_plan_id})

        conn.execute(sa.text("""
            INSERT INTO team_credit_balances (team_id, balance, updated_at)
            VALUES (:team_id, :credits, now())
            ON CONFLICT (team_id) DO UPDATE SET balance = team_credit_balances.balance + :credits, updated_at = now()
        """), {"team_id": team_id, "credits": FREE_PLAN_CREDIT_ALLOWANCE})

        conn.execute(sa.text("""
            INSERT INTO credit_transactions (id, team_id, amount, reason, reference_id, balance_after, created_at)
            VALUES (:id, :team_id, :credits, 'plan_grant', NULL, :credits, now())
        """), {"id": str(uuid.uuid4()), "team_id": team_id, "credits": FREE_PLAN_CREDIT_ALLOWANCE})


def downgrade() -> None:
    # Documented no-op — same reasoning as e3d3552b463c's downgrade: nothing
    # distinguishes a backfilled row from one that would exist naturally,
    # so there's nothing to reliably reverse.
    pass
