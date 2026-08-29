"""Verifies POST /generate (via generation_controller.run_generation and
run_generation_bulk) threads the acting user's id through to
enqueue_generation_job — the plumbing the per-user lock in worker.py
depends on. Does not exercise the real Redis lock itself — no Redis
integration test infra exists in this project yet (same gap noted in
docs/BOOK.md for the rest of generation)."""

import asyncio

from app.controllers import generation_controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.generation import BulkGenerateRequest, GenerateRequest


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def test_run_generation_enqueues_with_the_acting_users_id(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr(generation_controller, "_resolve_and_check_credits", lambda *a, **k: 1)

    captured = {}

    async def fake_enqueue(job_id, team_id, created_by):
        captured["job_id"] = job_id
        captured["team_id"] = team_id
        captured["created_by"] = created_by

    monkeypatch.setattr(generation_controller, "enqueue_generation_job", fake_enqueue)

    payload = GenerateRequest(team_id=team.id, feature_type="on_model_shots", input_payload={})
    job = asyncio.run(generation_controller.run_generation(db_session, user, payload))

    assert captured["created_by"] == user.id
    assert captured["team_id"] == team.id
    assert captured["job_id"] == job.id


def test_run_generation_bulk_enqueues_every_job_with_the_acting_users_id(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    assets = []
    for _ in range(2):
        asset = Asset(
            team_id=team.id, created_by=user.id, kind=AssetKind.upload.value,
            media_type=MediaType.image.value, storage_key=f"{team.id}/{new_id()}.png",
            url="http://x/1.png",
        )
        db_session.add(asset)
        assets.append(asset)
    db_session.commit()

    monkeypatch.setattr(generation_controller, "_resolve_and_check_credits", lambda *a, **k: 1)

    captured_created_by = []

    async def fake_enqueue(job_id, team_id, created_by):
        captured_created_by.append(created_by)

    monkeypatch.setattr(generation_controller, "enqueue_generation_job", fake_enqueue)

    payload = BulkGenerateRequest(
        team_id=team.id, feature_type="on_model_shots",
        asset_ids=[a.id for a in assets], input_payload={},
    )
    asyncio.run(generation_controller.run_generation_bulk(db_session, user, payload))

    assert captured_created_by == [user.id, user.id]
