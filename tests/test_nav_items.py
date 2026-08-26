"""tests/test_nav_items.py — list_nav_items only returns active rows,
in a stable order."""

from app.controllers import nav_item_controller
from app.models.nav_item import NavItem


def test_list_nav_items_excludes_inactive(db_session):
    db_session.add_all([
        NavItem(key="home", label="Home", is_active=True),
        NavItem(key="brand", label="Brand Kit", is_active=False),
    ])
    db_session.commit()

    result = nav_item_controller.list_nav_items(db_session)

    keys = [n.key for n in result]
    assert "home" in keys
    assert "brand" not in keys
