"""replace plans/credit packs with real pricing-page catalog

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-28 18:00:00.000000

Data-only. Supersedes the earlier Starter/Pro/Pro-yearly placeholder plans
(f1a2b3c4d5e6) and placeholder credit packs with the actual catalog the
frontend pricing page was built against: weekly/monthly/yearly
subscriptions, and 4 one-time credit packs. Adds `badge` + `features`
columns to both tables so the pricing page's ribbon label and bullet list
are DB-owned data, not hardcoded in the frontend (see Plan/CreditPack's
docstrings), and adds 'weekly' as a valid billing_cycle.

provider_plan_id values ARE real Razorpay plan ids (Plans API, test mode,
key rzp_test_TV6dBSLVyrkkOy) — visible in Razorpay Dashboard > Subscriptions
> Plans. India-only pricing: this account is a personal Razorpay account,
which cannot enable International Payments, so there is no non-INR option
right now (see Plan's region/plan_group docstring for the geo-pricing
groundwork that stays unused until a business account changes that).

Old plans (Starter/Pro monthly/Pro yearly from f1a2b3c4d5e6) are
DEACTIVATED (is_active=false), not deleted — a team that already
subscribed to one of them must keep resolving to a real row (FK from
team_subscriptions.plan_id), just no longer offered to new signups. Old
credit packs (Small/Large top-up) are deleted outright since nothing
FKs to a credit_pack row (CreditTransaction only stores a snapshot amount).
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, billing_cycle, price_paise, credit_allowance, max_team_members,
#  provider_plan_id, badge, features, plan_group)
PLANS = [
    (
        "Weekly", "weekly", 24900, 80, 3, "plan_TV7ysoXQP4bni2", None,
        ["80 credits per week", "Standard resolution", "Commercial licence", "Full template library"],
        "shootpx-weekly",
    ),
    (
        "Monthly", "monthly", 79900, 350, 10, "plan_TV7yt1KFO6RPrr", "BEST VALUE",
        ["350 credits per month", "2K export", "Commercial licence", "Priority generation queue"],
        "shootpx-monthly",
    ),
    (
        "Yearly", "yearly", 7999900, 4500, 10, "plan_TV7ytBRKox7Rl0", None,
        ["4,500 credits per year (~2 months free)", "4K export", "Commercial licence", "Priority generation queue"],
        "shootpx-yearly",
    ),
]

# (name, credit_amount, price_paise, badge, features, pack_group)
CREDIT_PACKS = [
    (
        "Starter", 60, 19900, None,
        ["60 image credits", "Standard resolution", "Commercial licence", "Full template library"],
        "shootpx-starter-pack",
    ),
    (
        "Popular", 175, 44900, "MOST POPULAR",
        ["175 image credits", "2K export", "Commercial licence", "Priority generation queue"],
        "shootpx-popular-pack",
    ),
    (
        "Pro", 450, 99900, None,
        ["450 image credits", "4K export", "Commercial licence", "Priority generation queue"],
        "shootpx-pro-pack",
    ),
    (
        "Bulk", 1000, 189900, None,
        ["1,000 image credits", "4K export", "Commercial licence", "Priority generation queue"],
        "shootpx-bulk-pack",
    ),
]

OLD_PROVIDER_PLAN_IDS = ("plan_TV6uz8xD64BCHw", "plan_TV6uzIVBWeQgN5", "plan_TV6uzSYR8Pp4Rx")
OLD_PACK_NAMES = ("Small top-up", "Large top-up")
NEW_PROVIDER_PLAN_IDS = ("plan_TV7ysoXQP4bni2", "plan_TV7yt1KFO6RPrr", "plan_TV7ytBRKox7Rl0")
NEW_PACK_GROUPS = ("shootpx-starter-pack", "shootpx-popular-pack", "shootpx-pro-pack", "shootpx-bulk-pack")


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column("plans", sa.Column("badge", sa.String(), nullable=True))
    op.add_column("plans", sa.Column("features", sa.JSON(), nullable=True))
    op.add_column("credit_packs", sa.Column("badge", sa.String(), nullable=True))
    op.add_column("credit_packs", sa.Column("features", sa.JSON(), nullable=True))

    conn.execute(sa.text("""
        UPDATE plans SET is_active = false
        WHERE provider_plan_id IN :old_ids
    """).bindparams(sa.bindparam("old_ids", expanding=True)), {"old_ids": list(OLD_PROVIDER_PLAN_IDS)})

    conn.execute(sa.text("""
        DELETE FROM credit_packs WHERE name IN :old_names
    """).bindparams(sa.bindparam("old_names", expanding=True)), {"old_names": list(OLD_PACK_NAMES)})

    for name, cycle, price, credits, members, provider_plan_id, badge, features, group in PLANS:
        conn.execute(sa.text("""
            INSERT INTO plans (id, name, billing_cycle, price, currency, region, plan_group,
                                credit_allowance, max_team_members, provider, provider_plan_id,
                                is_active, badge, features, created_at)
            VALUES (:id, :name, :cycle, :price, 'INR', 'IN', :group, :credits, :members,
                    'razorpay', :provider_plan_id, true, :badge, :features, now())
        """), {
            "id": str(uuid.uuid4()), "name": name, "cycle": cycle, "price": price,
            "credits": credits, "members": members, "provider_plan_id": provider_plan_id,
            "badge": badge, "features": __import__("json").dumps(features), "group": group,
        })

    for name, credit_amount, price, badge, features, group in CREDIT_PACKS:
        conn.execute(sa.text("""
            INSERT INTO credit_packs (id, name, credit_amount, price, currency, region, pack_group,
                                       is_active, badge, features)
            VALUES (:id, :name, :credit_amount, :price, 'INR', 'IN', :group, true, :badge, :features)
        """), {
            "id": str(uuid.uuid4()), "name": name, "credit_amount": credit_amount, "price": price,
            "badge": badge, "features": __import__("json").dumps(features), "group": group,
        })


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        DELETE FROM plans WHERE provider_plan_id IN :new_ids
    """).bindparams(sa.bindparam("new_ids", expanding=True)), {"new_ids": list(NEW_PROVIDER_PLAN_IDS)})

    conn.execute(sa.text("""
        DELETE FROM credit_packs WHERE pack_group IN :new_groups
    """).bindparams(sa.bindparam("new_groups", expanding=True)), {"new_groups": list(NEW_PACK_GROUPS)})

    conn.execute(sa.text("""
        UPDATE plans SET is_active = true
        WHERE provider_plan_id IN :old_ids
    """).bindparams(sa.bindparam("old_ids", expanding=True)), {"old_ids": list(OLD_PROVIDER_PLAN_IDS)})

    op.drop_column("credit_packs", "features")
    op.drop_column("credit_packs", "badge")
    op.drop_column("plans", "features")
    op.drop_column("plans", "badge")
