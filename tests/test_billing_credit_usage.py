"""billing_controller.get_credit_usage_by_member — per-member credit spend
breakdown for a team, derived by joining CreditTransaction (generation_spend
only) to GenerationJob.created_by. Owner-only."""

import pytest
from fastapi import HTTPException

from app.controllers import billing_controller
from app.models.credit import CreditReason, CreditTransaction
from app.models.generation_job import GenerationJob, JobStatus
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User


def _make_team(db):
    team = Team(id=new_id(), name="Test Team")
    db.add(team)
    db.commit()
    return team


def _make_user(db, team, role="editor"):
    user = User(id=new_id(), email=f"{new_id()}@example.com", name="Test User")
    db.add(user)
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return user


def _make_generation_spend(db, team, user, amount):
    job = GenerationJob(
        team_id=team.id, created_by=user.id, feature_type="on_model_shots",
        status=JobStatus.done.value, input_payload={}, credit_cost=amount,
    )
    db.add(job)
    db.commit()
    db.add(CreditTransaction(
        team_id=team.id, amount=-amount, reason=CreditReason.generation_spend.value,
        reference_id=job.id, balance_after=1000 - amount,
    ))
    db.commit()
    return job


def test_get_credit_usage_by_member_groups_spend_per_user(db_session):
    team = _make_team(db_session)
    owner = _make_user(db_session, team, role="owner")
    editor = _make_user(db_session, team, role="editor")

    _make_generation_spend(db_session, team, owner, 30)
    _make_generation_spend(db_session, team, editor, 100)
    _make_generation_spend(db_session, team, editor, 50)

    result = billing_controller.get_credit_usage_by_member(db_session, owner, team.id)

    assert result["team_id"] == team.id
    assert result["total_credits_spent"] == 180
    by_user = {m["user_id"]: m["credits_spent"] for m in result["by_member"]}
    assert by_user[owner.id] == 30
    assert by_user[editor.id] == 150
    assert result["by_member"][0]["user_id"] == editor.id  # sorted highest-spend first


def test_get_credit_usage_by_member_ignores_non_generation_reasons(db_session):
    team = _make_team(db_session)
    owner = _make_user(db_session, team, role="owner")
    db_session.add(CreditTransaction(
        team_id=team.id, amount=1000, reason=CreditReason.plan_grant.value,
        reference_id=None, balance_after=1000,
    ))
    db_session.commit()

    result = billing_controller.get_credit_usage_by_member(db_session, owner, team.id)
    assert result["total_credits_spent"] == 0
    assert result["by_member"] == []


def test_get_credit_usage_by_member_rejects_non_owner(db_session):
    team = _make_team(db_session)
    owner = _make_user(db_session, team, role="owner")
    editor = _make_user(db_session, team, role="editor")
    _make_generation_spend(db_session, team, owner, 30)

    with pytest.raises(HTTPException) as exc_info:
        billing_controller.get_credit_usage_by_member(db_session, editor, team.id)
    assert exc_info.value.status_code == 403
