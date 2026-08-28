"""seed paid plans and credit packs

Revision ID: f1a2b3c4d5e6
Revises: c89302d1deb9
Create Date: 2026-08-28 00:00:00.000000

Data-only migration, same philosophy as baa7b2ede411 (the Free plan seed):
raw SQL, not the ORM. Adds a small set of PAID plans alongside the existing
Free plan, plus a couple of credit top-up packs, so subscription + credit
purchase flows have something real to test against end-to-end (checkout,
webhook crediting, plan-change, cancellation clawback, top-ups).

All values here (prices, credit allowances) are placeholders for testing,
not final business numbers:

- provider_plan_id values ARE real Razorpay plan ids (created via the
  Plans API against this project's test-mode Razorpay account — see
  plan.create calls run against RAZORPAY_KEY_ID rzp_test_TV6dBSLVyrkkOy).
  They will need to be recreated (and this migration's data corrected, or
  the plans table updated directly) if the project ever points at a
  different Razorpay account — a test-mode plan id is not portable across
  accounts, and definitely not to live mode.
- prices are in the smallest currency unit (paise, since currency='INR').
- credit_allowance is granted PER MONTHLY REFILL regardless of
  billing_cycle (see Plan's docstring) — the yearly plan still refills
  monthly, not once a year.

Seeds:
  1. Starter  - monthly - INR 499  (49900 paise) - 50 credits/mo  - 3 members
  2. Pro      - monthly - INR 1499 (149900 paise) - 200 credits/mo - 10 members
  3. Pro      - yearly  - INR 14999 (1499900 paise) - 200 credits/mo - 10 members
  4. Credit pack "Small top-up" - INR 199 (19900 paise) - 25 credits
  5. Credit pack "Large top-up" - INR 699 (69900 paise) - 100 credits
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'c89302d1deb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PAID_PLANS = [
    # (name, billing_cycle, price_paise, credit_allowance, max_team_members, provider_plan_id)
    ("Starter", "monthly", 49900, 50, 3, "plan_TV6uz8xD64BCHw"),
    ("Pro", "monthly", 149900, 200, 10, "plan_TV6uzIVBWeQgN5"),
    ("Pro", "yearly", 1499900, 200, 10, "plan_TV6uzSYR8Pp4Rx"),
]

CREDIT_PACKS = [
    # (name, credit_amount, price_paise)
    ("Small top-up", 25, 19900),
    ("Large top-up", 100, 69900),
]


def upgrade() -> None:
    conn = op.get_bind()

    for name, cycle, price, credits, members, provider_plan_id in PAID_PLANS:
        conn.execute(sa.text("""
            INSERT INTO plans (id, name, billing_cycle, price, currency, credit_allowance,
                                max_team_members, provider, provider_plan_id, is_active, created_at)
            VALUES (:id, :name, :cycle, :price, 'INR', :credits, :members, 'razorpay', :provider_plan_id, true, now())
        """), {
            "id": str(uuid.uuid4()), "name": name, "cycle": cycle, "price": price,
            "credits": credits, "members": members, "provider_plan_id": provider_plan_id,
        })

    for name, credit_amount, price in CREDIT_PACKS:
        conn.execute(sa.text("""
            INSERT INTO credit_packs (id, name, credit_amount, price, currency, is_active)
            VALUES (:id, :name, :credit_amount, :price, 'INR', true)
        """), {
            "id": str(uuid.uuid4()), "name": name, "credit_amount": credit_amount, "price": price,
        })


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM plans WHERE provider_plan_id IN (
            'plan_TV6uz8xD64BCHw', 'plan_TV6uzIVBWeQgN5', 'plan_TV6uzSYR8Pp4Rx'
        )
    """))
    conn.execute(sa.text("""
        DELETE FROM credit_packs WHERE name IN ('Small top-up', 'Large top-up')
    """))
