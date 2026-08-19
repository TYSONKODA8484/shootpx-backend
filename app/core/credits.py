"""The one place a team's credit balance is ever written. Both grants
(positive amount) and spends (negative amount) go through the same atomic
SQL UPDATE — never read-then-write in Python. A webhook-driven grant and a
worker-driven deduction can land at the same moment; only deductions are
protected by app/worker.py's per-team generation lock, so the balance
update itself has to be atomic regardless of caller.
"""

import calendar
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.credit import CreditTransaction


def add_one_month(dt: datetime) -> datetime:
    """dt + 1 calendar month, clamping day-of-month for overflow (Jan 31 ->
    Feb 28/29, not a crash). Used everywhere a subscription's
    next_credit_refill_at advances — stdlib-only rather than pulling in
    python-dateutil for one function, matching this codebase's otherwise
    lean dependency list."""
    month = dt.month + 1
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def apply_credit_delta(db: Session, team_id: str, amount: int, reason: str, reference_id: str | None = None) -> int:
    """Atomically adjusts a team's balance by `amount` (positive to grant,
    negative to spend) and writes the matching ledger row. Returns the new
    balance. Caller is responsible for checking sufficient balance BEFORE
    calling this for a spend (see generation_controller.py) — this function
    just applies the delta, it doesn't gate it."""
    db.execute(sa.text("""
        INSERT INTO team_credit_balances (team_id, balance, updated_at)
        VALUES (:team_id, :amount, now())
        ON CONFLICT (team_id) DO UPDATE
        SET balance = team_credit_balances.balance + :amount, updated_at = now()
    """), {"team_id": team_id, "amount": amount})

    new_balance = db.execute(
        sa.text("SELECT balance FROM team_credit_balances WHERE team_id = :t"),
        {"t": team_id},
    ).scalar_one()

    db.add(CreditTransaction(
        team_id=team_id, amount=amount, reason=reason,
        reference_id=reference_id, balance_after=new_balance,
    ))
    return new_balance


def get_balance(db: Session, team_id: str) -> int:
    row = db.execute(
        sa.text("SELECT balance FROM team_credit_balances WHERE team_id = :t"),
        {"t": team_id},
    ).first()
    return row[0] if row else 0
