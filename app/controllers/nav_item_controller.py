"""Public sidebar-visibility list — no auth, same spirit as GET /tools:
app-shell config, not per-team data."""

from sqlalchemy.orm import Session

from app.models.nav_item import NavItem


def list_nav_items(db: Session) -> list[NavItem]:
    return db.query(NavItem).filter(NavItem.is_active == True).order_by(NavItem.key).all()  # noqa: E712
