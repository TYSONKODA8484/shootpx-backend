"""tests/test_asset_versions.py — get_asset_versions' backward-chain walk
through generation_jobs.output_asset_id -> source_asset_id."""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from app.controllers import asset_controller
from app.models.asset import Asset, AssetKind
from app.models.generation_job import GenerationJob, JobStatus
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


def _make_asset(db, team, user):
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=AssetKind.upload.value, media_type="image",
        storage_key=f"{team.id}/{new_id()}.png", url=f"http://x/files/{team.id}/{new_id()}.png",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _make_job(db, team, user, *, source_asset_id, output_asset_id, feature_type, completed_at):
    job = GenerationJob(
        team_id=team.id, created_by=user.id, feature_type=feature_type, status=JobStatus.done.value,
        source_asset_id=source_asset_id, output_asset_id=output_asset_id, completed_at=completed_at,
    )
    db.add(job)
    db.commit()
    return job


def _make_tool(db, feature_type, display_name):
    db.add(Tool(feature_type=feature_type, display_name=display_name, output_media_type="image"))
    db.commit()


def test_versions_of_an_untouched_asset_is_just_itself_labeled_original(db_session):
    team, user = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, user)

    result = asset_controller.get_asset_versions(db_session, asset.id, user)

    assert len(result.versions) == 1
    assert result.versions[0].asset_id == asset.id
    assert result.versions[0].label == "Original"


def test_versions_walks_the_chain_backwards_newest_first(db_session):
    team, user = _make_team_and_user(db_session)
    _make_tool(db_session, "on_model_shots", "On-Model Shots")
    _make_tool(db_session, "upscale_4k", "Upscale 4K")

    original = _make_asset(db_session, team, user)
    v2 = _make_asset(db_session, team, user)
    v3 = _make_asset(db_session, team, user)
    _make_job(db_session, team, user, source_asset_id=original.id, output_asset_id=v2.id, feature_type="on_model_shots", completed_at=T0)
    _make_job(db_session, team, user, source_asset_id=v2.id, output_asset_id=v3.id, feature_type="upscale_4k", completed_at=T0 + timedelta(minutes=5))

    result = asset_controller.get_asset_versions(db_session, v3.id, user)

    labels = [v.label for v in result.versions]
    asset_ids = [v.asset_id for v in result.versions]
    assert labels == ["Upscale 4K", "On-Model Shots", "Original"]
    assert asset_ids == [v3.id, v2.id, original.id]


def test_versions_404s_for_a_missing_asset(db_session):
    _team, user = _make_team_and_user(db_session)
    with pytest.raises(HTTPException) as exc_info:
        asset_controller.get_asset_versions(db_session, "does-not-exist", user)
    assert exc_info.value.status_code == 404


def test_versions_404s_for_a_non_member(db_session):
    team, owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, owner)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.get_asset_versions(db_session, asset.id, outsider)
    assert exc_info.value.status_code == 404
