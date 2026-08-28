from sqlalchemy import Boolean, Column, DateTime, String

from app.core.db import Base
from app.core.time import utc_now


class BillingMode(Base):
    """A pure show/hide switch for a whole billing MODE (subscriptions vs
    one-time credit top-ups) — same spirit and same shape as NavItem, just
    for the pricing page's two tabs instead of Studio sidebar pages. Two
    rows are fixed (seeded by migration): key="subscriptions" and
    key="credits". An admin toggles is_active via the CMS; nothing creates
    or deletes rows here.

    Checked live by GET /billing/config on every request — unchecking one
    here means the frontend hides that whole tab immediately, no restart,
    no cache to clear, matching Tool.is_active/NavItem.is_active's
    contract. Deliberately NOT a blanket "maintenance mode" flag: the two
    are independent so subscriptions can be sunset while credit top-ups
    stay on, or vice versa, without one dragging the other down.

    This only controls what the PRICING PAGE offers going forward — it
    does not touch teams already on a plan of the disabled mode (an
    existing subscriber isn't force-cancelled by turning subscriptions
    off) and does not gate the underlying /billing/subscribe or
    /billing/topup endpoints themselves; a frontend that ignores this flag
    could still call them. If hard-blocking the endpoints too ever
    matters, that's a deliberate follow-up, not implied by this table.
    """

    __tablename__ = "billing_modes"

    key = Column(String, primary_key=True)  # "subscriptions" | "credits"
    label = Column(String, nullable=False)  # display-only, for the CMS's own list view
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
