"""The one place a team's credit balance is ever written. Both grants
(positive amount) and spends (negative amount) go through the same atomic
SQL UPDATE — never read-then-write in Python. A webhook-driven grant and a
worker-driven deduction can land at the same moment; only deductions are
protected by app/worker.py's per-team generation lock, so the balance
update itself has to be atomic regardless of caller.
"""

import calendar
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.credit import CreditTransaction


def add_one_month(dt: datetime) -> datetime:
    """dt + 1 calendar month, clamping day-of-month for overflow (Jan 31 ->
    Feb 28/29, not a crash). stdlib-only rather than pulling in
    python-dateutil for one function, matching this codebase's otherwise
    lean dependency list. Kept as its own function (rather than folded into
    add_refill_interval below) since add_one_year also builds on it."""
    month = dt.month + 1
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def add_one_year(dt: datetime) -> datetime:
    """dt + 12 calendar months — same day-of-month clamping as
    add_one_month (Feb 29 on a non-leap target year -> Feb 28), just
    applied twelve times so the two never drift out of sync on how they
    handle month-end overflow."""
    result = dt
    for _ in range(12):
        result = add_one_month(result)
    return result


def add_refill_interval(dt: datetime, billing_cycle: str) -> datetime:
    """Advances `dt` by however often THIS billing_cycle actually refills
    credits — every plan used to refill monthly regardless of
    billing_cycle (a real mismatch once a Weekly plan existed: "80
    credits/week" was only ever being granted once a month). 'free'
    refills monthly, same as 'monthly' — the Free plan has no cycle of its
    own to speak of, monthly has always been its cadence."""
    if billing_cycle == "weekly":
        return dt + timedelta(weeks=1)
    if billing_cycle == "yearly":
        return add_one_year(dt)
    return add_one_month(dt)  # 'monthly' and 'free'


def period_length(billing_cycle: str) -> timedelta:
    """How long ONE billing period lasts, for setting
    TeamSubscription.current_period_end — used instead of a
    hardcoded 30 days so a weekly/yearly subscriber's period-end (and
    therefore how long they keep paid-tier access after cancelling) isn't
    silently wrong for anything but a monthly plan. Approximates a
    calendar year/month as 365/30 days rather than add_one_year/
    add_one_month here since this produces a timedelta to ADD to "now",
    not a calendar-aware advance of an existing date — good enough for a
    period-end display, not used for actual refill scheduling (that's
    add_refill_interval, which IS calendar-aware)."""
    if billing_cycle == "weekly":
        return timedelta(weeks=1)
    if billing_cycle == "yearly":
        return timedelta(days=365)
    return timedelta(days=30)  # 'monthly' and 'free'


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
