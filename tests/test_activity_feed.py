"""tests/test_activity_feed.py — GET /teams/{team_id}/activity's merge
logic: which rows from generation_jobs/product_imports/credit_transactions
show up, in what order, with what cursor.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.controllers import activity_controller
from app.models.credit import CreditReason, CreditTransaction
from app.models.generation_job import GenerationJob, JobStatus
from app.models.product_import import ProductImport, ProductImportStatus
from app.models.team import Team, TeamMembership, new_id
from app.models.tool import Tool
from app.models.user import User

T0 = datetime(2026, 1, 1, 12, 0, 0)


def _make_team_and_user(db):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role="owner"))
    db.commit()
    return team, user


def _job(db, team, user, *, status, created_at, feature_type="on_model_shots", error=None):
    job = GenerationJob(
        team_id=team.id, created_by=user.id, feature_type=feature_type,
        status=status, error=error, created_at=created_at,
    )
    db.add(job)
    db.commit()
    return job


def _import(db, team, user, *, status, created_at, product_name=None, source_url="https://x.example/p"):
    imp = ProductImport(
        team_id=team.id, created_by=user.id, source_url=source_url,
        status=status, product_name=product_name, created_at=created_at,
    )
    db.add(imp)
    db.commit()
    return imp


def _credit_tx(db, team, *, reason, amount, created_at):
    tx = CreditTransaction(
        team_id=team.id, amount=amount, reason=reason, balance_after=amount, created_at=created_at,
    )
    db.add(tx)
    db.commit()
    return tx


def test_feed_includes_jobs_imports_and_curated_credits_only(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0)
    _import(db_session, team, user, status=ProductImportStatus.done.value, created_at=T0)
    _credit_tx(db_session, team, reason=CreditReason.plan_grant.value, amount=100, created_at=T0)
    _credit_tx(db_session, team, reason=CreditReason.generation_spend.value, amount=-1, created_at=T0)

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    kinds = sorted(e.kind for e in feed.events)
    assert kinds == ["credit", "import", "job"]  # generation_spend excluded


def test_feed_orders_newest_first(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0 + timedelta(minutes=5))

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    assert feed.events[0].created_at > feed.events[1].created_at


def test_feed_job_title_uses_tool_display_name(db_session):
    team, user = _make_team_and_user(db_session)
    db_session.add(Tool(feature_type="on_model_shots", display_name="On-Model Shots", output_media_type="image"))
    db_session.commit()
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0, feature_type="on_model_shots")

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    assert feed.events[0].title == "On-Model Shots"


def test_feed_failed_job_detail_includes_error(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.failed.value, created_at=T0, error="provider timeout")

    feed = activity_controller.get_activity_feed(db_session, team.id, user)

    assert "provider timeout" in feed.events[0].detail


def test_feed_404s_for_a_non_member(db_session):
    team, _owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        activity_controller.get_activity_feed(db_session, team.id, outsider)
    assert exc_info.value.status_code == 404


def test_feed_pagination_cursor_walks_backwards(db_session):
    team, user = _make_team_and_user(db_session)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0)
    _job(db_session, team, user, status=JobStatus.done.value, created_at=T0 + timedelta(minutes=5))

    page1 = activity_controller.get_activity_feed(db_session, team.id, user, limit=1)
    assert len(page1.events) == 1
    assert page1.next_cursor == page1.events[0].created_at

    page2 = activity_controller.get_activity_feed(db_session, team.id, user, limit=1, before=page1.next_cursor)
    assert len(page2.events) == 1
    assert page2.events[0].created_at < page1.events[0].created_at
