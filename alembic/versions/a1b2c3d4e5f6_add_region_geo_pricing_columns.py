"""add region/plan_group columns for geo-pricing

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-08-28 12:00:00.000000

Schema-only groundwork for geo-pricing (see app/core/geo_pricing.py and
Plan/CreditPack's updated docstrings) — no non-INR rows are inserted here.
Razorpay's International Payments has to be enabled/approved on the
account before a USD Plan/Order would even be payable; creating those rows
ahead of that would just be dead data that fails at checkout. This
migration only:

1. Adds `region` + `plan_group` to plans, `region` + `pack_group` to
   credit_packs.
2. Backfills every EXISTING paid plan/pack as region='IN' (matching where
   they were actually created — see f1a2b3c4d5e6's docstring) with a
   plan_group/pack_group derived from name+billing_cycle, so region
   filtering (list_plans/list_credit_packs with ?region=) keeps working
   for what already exists. The Free plan is intentionally left
   region=NULL, plan_group=NULL — it's region-less by design (Plan's
   docstring).

Adding the actual US-priced rows is a follow-up migration once
International Payments is confirmed enabled AND real USD prices are
decided — not a code change, just new INSERTs (same shape as
f1a2b3c4d5e6), same as how real Plan pricing tiers were always meant to be
business data rather than baked into a schema migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (plan name, billing_cycle) -> plan_group
PLAN_GROUPS = {
    ("Starter", "monthly"): "starter-monthly",
    ("Pro", "monthly"): "pro-monthly",
    ("Pro", "yearly"): "pro-yearly",
}

# credit_pack name -> pack_group
PACK_GROUPS = {
    "Small top-up": "small-topup",
    "Large top-up": "large-topup",
}


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column("plans", sa.Column("region", sa.String(), nullable=True))
    op.add_column("plans", sa.Column("plan_group", sa.String(), nullable=True))
    op.add_column("credit_packs", sa.Column("region", sa.String(), nullable=True))
    op.add_column("credit_packs", sa.Column("pack_group", sa.String(), nullable=True))

    for (name, cycle), group in PLAN_GROUPS.items():
        conn.execute(sa.text("""
            UPDATE plans SET region = 'IN', plan_group = :group
            WHERE name = :name AND billing_cycle = :cycle AND provider = 'razorpay'
        """), {"group": group, "name": name, "cycle": cycle})

    for name, group in PACK_GROUPS.items():
        conn.execute(sa.text("""
            UPDATE credit_packs SET region = 'IN', pack_group = :group
            WHERE name = :name
        """), {"group": group, "name": name})


def downgrade() -> None:
    op.drop_column("credit_packs", "pack_group")
    op.drop_column("credit_packs", "region")
    op.drop_column("plans", "plan_group")
    op.drop_column("plans", "region")
