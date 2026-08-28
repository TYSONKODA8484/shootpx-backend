import pytest
from fastapi import HTTPException

from app.controllers import cms_controller
from app.core.cms_registry import ENTITIES
from app.core.time import utc_now

PLANS = ENTITIES["plans"]


def _plan_payload(**overrides):
    payload = {
        "name": "Starter", "billing_cycle": "monthly", "price": 99900,
        "currency": "INR", "credit_allowance": 100, "max_team_members": 5,
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def test_create_list_get_update_delete_roundtrip(db_session):
    created = cms_controller.create_row(db_session, PLANS, _plan_payload())
    plan_id = created["id"]
    assert created["name"] == "Starter"

    listed = cms_controller.list_rows(db_session, PLANS, page=1, search=None)
    assert listed["total"] == 1

    fetched = cms_controller.get_row(db_session, PLANS, plan_id)
    assert fetched["credit_allowance"] == 100

    updated = cms_controller.update_row(db_session, PLANS, plan_id, {"credit_allowance": 200})
    assert updated["credit_allowance"] == 200

    cms_controller.delete_row(db_session, PLANS, plan_id)
    with pytest.raises(HTTPException) as exc_info:
        cms_controller.get_row(db_session, PLANS, plan_id)
    assert exc_info.value.status_code == 404


def test_update_rejects_non_editable_field(db_session):
    created = cms_controller.create_row(db_session, PLANS, _plan_payload())
    with pytest.raises(HTTPException) as exc_info:
        cms_controller.update_row(db_session, PLANS, created["id"], {"id": "hacked"})
    assert exc_info.value.status_code == 400


def test_delete_blocked_by_foreign_key(db_session):
    from app.models.subscription import TeamSubscription
    from app.models.team import Team

    created = cms_controller.create_row(db_session, PLANS, _plan_payload())
    db_session.add(Team(id="team-1", name="Test Team"))
    db_session.commit()
    db_session.add(TeamSubscription(
        id="sub-1", team_id="team-1", plan_id=created["id"],
        status="active", next_credit_refill_at=utc_now(),
    ))
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        cms_controller.delete_row(db_session, PLANS, created["id"])
    assert exc_info.value.status_code == 400


def test_credit_transactions_reject_update_and_delete(db_session):
    from app.models.team import Team

    ledger = ENTITIES["credit-transactions"]
    db_session.add(Team(id="team-1", name="Test Team"))
    db_session.commit()

    created = cms_controller.create_row(db_session, ledger, {
        "team_id": "team-1", "amount": 10, "reason": "manual_adjustment", "balance_after": 10,
    })

    with pytest.raises(HTTPException) as exc_info:
        cms_controller.update_row(db_session, ledger, created["id"], {"amount": 20})
    assert exc_info.value.status_code == 405

    with pytest.raises(HTTPException) as exc_info:
        cms_controller.delete_row(db_session, ledger, created["id"])
    assert exc_info.value.status_code == 405


def test_stats(db_session):
    from app.models.team import Team
    from app.models.user import User

    db_session.add_all([
        User(id="u1", email="a@example.com"),
        Team(id="t1", name="Team 1"),
    ])
    db_session.commit()

    stats = cms_controller.get_stats(db_session)
    assert stats["total_users"] == 1
    assert stats["total_teams"] == 1
    assert stats["total_credit_balance"] == 0
