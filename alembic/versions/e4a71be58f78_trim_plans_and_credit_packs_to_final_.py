"""trim plans and credit packs to final catalog, reprice subscriptions

Revision ID: e4a71be58f78
Revises: f6a7b8c9d0e1
Create Date: 2026-08-29 12:00:00.000000

Data-only. Product decision: exactly 3 subscription plans (Weekly, Monthly,
Yearly at plan_group shootpx-weekly/monthly/yearly, priced INR 100 / 500 /
10,000) and exactly 4 credit packs (Starter/Popular/Pro/Bulk, unchanged).

Unlike b2c3d4e5f6a7 (which deactivated superseded plans instead of deleting
them, precisely because team_subscriptions.plan_id FKs to plans.id with no
cascade), this migration actually DELETES the leftover rows: Free,
"Monthly 100", and the duplicate "Starter monthly" plans (all plan_group
IS NULL or outside the shootpx-* set). Before deleting, every team
currently on one of those plans (Free: 21, Monthly 100: 5, Starter
monthly dup: 3 as of authoring) is reassigned to the Monthly plan so the
FK never breaks. That reassignment is a deliberate, explicit product
decision (not a technical default) and is NOT undone by downgrade() —
there is no record of which team was on which plan before this ran, so
downgrade only restores the deleted catalog rows and original prices, not
the per-team assignments.

Credit packs: the 4 real packs (Starter/Popular/Pro/Bulk, pack_group set)
are untouched. The junk rows (pack_group IS NULL: two "100 credits", one
"10 credits", one "1000 credits") are deleted outright — same as
b2c3d4e5f6a7 did for the old Small/Large top-up packs, since nothing FKs
to a credit_pack row (CreditTransaction only stores a snapshot amount).
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a71be58f78'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KEPT_PLAN_GROUPS = ("shootpx-weekly", "shootpx-monthly", "shootpx-yearly")
NEW_PRICES = {
    "shootpx-weekly": 10000,      # INR 100
    "shootpx-monthly": 50000,     # INR 500
    "shootpx-yearly": 1000000,    # INR 10,000
}
OLD_PRICES = {
    "shootpx-weekly": 24900,
    "shootpx-monthly": 79900,
    "shootpx-yearly": 7999900,
}

# Full snapshot of the rows being deleted, so downgrade() can restore them.
DELETED_PLANS = [
    # (id, name, billing_cycle, price, currency, region, plan_group,
    #  credit_allowance, max_team_members, provider, provider_plan_id, is_active)
    ("30256491-0589-4490-b871-e52fdd379d8e", "Starter", "monthly", 49900, "INR", "IN", "starter-monthly", 50, 3, "razorpay", "plan_TV6uz8xD64BCHw", False),
    ("3832535d-183e-42cb-86b6-3eed30cbdcda", "Pro", "monthly", 149900, "INR", "IN", "pro-monthly", 200, 10, "razorpay", "plan_TV6uzIVBWeQgN5", False),
    ("978bba9c-50cf-4a4e-847f-dc694710850a", "Pro", "yearly", 1499900, "INR", "IN", "pro-yearly", 200, 10, "razorpay", "plan_TV6uzSYR8Pp4Rx", False),
    ("b182a7d5-7829-4588-97cf-a23f6121787e", "Starter", "monthly", 49900, "INR", "IN", "starter-monthly", 100, 5, "razorpay", "plan_TRcDOvGM7A84FG", False),
    ("b696ec38-5f45-46a8-b55b-d12bd3059dbc", "Monthly 100", "monthly", 10000, "INR", None, None, 100, 5, "razorpay", "plan_TRcbYPaxL2zYxy", True),
    ("d4e47bfc-3323-4496-91d3-81a6474602d0", "Free", "free", None, "INR", None, None, 5, 1, None, None, True),
]

DELETED_CREDIT_PACKS = [
    # (id, name, credit_amount, price, currency, region, pack_group, is_active)
    ("048e8363-78a7-4e9d-a11d-9e0ed728be82", "1000 credits", 1000, 100000, "INR", None, None, True),
    ("9f60e9e1-beab-4fb9-8cab-bbac8c02c567", "10 credits", 10, 1000, "INR", None, None, True),
    ("b89a464f-21ea-45ce-aa79-7b59534e4438", "100 credits", 100, 10000, "INR", None, None, True),
    ("d6749092-fa56-4a3e-824b-34a58f05c6f9", "100 credits", 100, 19900, "INR", None, None, False),
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Move every team off the plans we're about to delete, onto Monthly,
    #    so the team_subscriptions.plan_id FK never breaks.
    conn.execute(sa.text("""
        UPDATE team_subscriptions
        SET plan_id = (SELECT id FROM plans WHERE plan_group = 'shootpx-monthly')
        WHERE plan_id IN (
            SELECT id FROM plans
            WHERE plan_group IS NULL OR plan_group NOT IN :kept
        )
    """).bindparams(sa.bindparam("kept", expanding=True)), {"kept": list(KEPT_PLAN_GROUPS)})

    # 2. Delete every plan except Weekly/Monthly/Yearly.
    conn.execute(sa.text("""
        DELETE FROM plans WHERE plan_group IS NULL OR plan_group NOT IN :kept
    """).bindparams(sa.bindparam("kept", expanding=True)), {"kept": list(KEPT_PLAN_GROUPS)})

    # 3. Reprice the 3 keepers.
    for group, price in NEW_PRICES.items():
        conn.execute(
            sa.text("UPDATE plans SET price = :price WHERE plan_group = :group"),
            {"price": price, "group": group},
        )

    # 4. Delete the junk credit packs; the 4 real ones (pack_group set) are untouched.
    conn.execute(sa.text("DELETE FROM credit_packs WHERE pack_group IS NULL"))


def downgrade() -> None:
    conn = op.get_bind()

    # Restore original prices on the 3 kept plans.
    for group, price in OLD_PRICES.items():
        conn.execute(
            sa.text("UPDATE plans SET price = :price WHERE plan_group = :group"),
            {"price": price, "group": group},
        )

    # Recreate the deleted plan rows (NOTE: team_subscriptions reassigned in
    # upgrade() are NOT moved back — there is no record of the prior mapping).
    for (plan_id, name, cycle, price, currency, region, group, credits, members,
         provider, provider_plan_id, is_active) in DELETED_PLANS:
        conn.execute(sa.text("""
            INSERT INTO plans (id, name, billing_cycle, price, currency, region, plan_group,
                                credit_allowance, max_team_members, provider, provider_plan_id,
                                is_active, created_at)
            VALUES (:id, :name, :cycle, :price, :currency, :region, :group, :credits, :members,
                    :provider, :provider_plan_id, :is_active, now())
        """), {
            "id": plan_id, "name": name, "cycle": cycle, "price": price, "currency": currency,
            "region": region, "group": group, "credits": credits, "members": members,
            "provider": provider, "provider_plan_id": provider_plan_id, "is_active": is_active,
        })

    # Recreate the deleted junk credit packs.
    for (pack_id, name, credit_amount, price, currency, region, group, is_active) in DELETED_CREDIT_PACKS:
        conn.execute(sa.text("""
            INSERT INTO credit_packs (id, name, credit_amount, price, currency, region, pack_group, is_active)
            VALUES (:id, :name, :credit_amount, :price, :currency, :region, :group, :is_active)
        """), {
            "id": pack_id, "name": name, "credit_amount": credit_amount, "price": price,
            "currency": currency, "region": region, "group": group, "is_active": is_active,
        })
