"""tests/test_brand_kit.py — get-or-create, update, and marks logic for
the Brand Kit."""

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.controllers import brand_kit_controller
from app.models.brand_kit import BrandKit, BrandMark
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User
from app.schemas.brand_kit import BrandKitUpdate


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _upload_file(filename="logo.png", content_type="image/png"):
    return UploadFile(file=io.BytesIO(b"fake-bytes"), filename=filename, headers=Headers({"content-type": content_type}))


def test_get_or_create_creates_an_empty_kit_on_first_call(db_session):
    team, user = _make_team_and_user(db_session)

    kit = brand_kit_controller.get_or_create_brand_kit(db_session, team.id, user)

    assert kit.team_id == team.id
    assert kit.palette == []
    assert kit.marks == []
    assert db_session.query(BrandKit).filter(BrandKit.team_id == team.id).count() == 1


def test_get_or_create_returns_the_same_kit_on_second_call(db_session):
    team, user = _make_team_and_user(db_session)

    first = brand_kit_controller.get_or_create_brand_kit(db_session, team.id, user)
    second = brand_kit_controller.get_or_create_brand_kit(db_session, team.id, user)

    assert first.id == second.id
    assert db_session.query(BrandKit).filter(BrandKit.team_id == team.id).count() == 1


def test_get_or_create_404s_for_a_non_member(db_session):
    team, _owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        brand_kit_controller.get_or_create_brand_kit(db_session, team.id, outsider)
    assert exc_info.value.status_code == 404


def test_update_brand_kit_replaces_palette_and_fonts(db_session):
    team, user = _make_team_and_user(db_session)
    brand_kit_controller.get_or_create_brand_kit(db_session, team.id, user)

    updated = brand_kit_controller.update_brand_kit(
        db_session, team.id, user, BrandKitUpdate(palette=["#123f2e", "#3f9c73"], heading_font="Inter", body_font="Georgia"),
    )

    assert updated.palette == ["#123f2e", "#3f9c73"]
    assert updated.heading_font == "Inter"
    assert updated.body_font == "Georgia"


def test_add_mark_creates_asset_and_links_it(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr("app.controllers.asset_controller.storage.save", lambda key, content: None)

    mark = asyncio.run(
        brand_kit_controller.add_mark(db_session, team.id, user, _upload_file(), variant="dark")
    )

    assert mark.variant == "dark"
    kit = brand_kit_controller.get_or_create_brand_kit(db_session, team.id, user)
    assert len(kit.marks) == 1
    assert kit.marks[0].id == mark.id


def test_delete_mark_removes_link_not_asset(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    monkeypatch.setattr("app.controllers.asset_controller.storage.save", lambda key, content: None)
    mark = asyncio.run(brand_kit_controller.add_mark(db_session, team.id, user, _upload_file(), variant="light"))
    from app.models.asset import Asset
    asset_id = mark.asset_id

    brand_kit_controller.delete_mark(db_session, mark.id, user)

    assert db_session.query(BrandMark).filter(BrandMark.id == mark.id).first() is None
    assert db_session.get(Asset, asset_id) is not None  # underlying asset untouched


def test_delete_mark_404s_for_missing_mark(db_session):
    _team, user = _make_team_and_user(db_session)
    with pytest.raises(HTTPException) as exc_info:
        brand_kit_controller.delete_mark(db_session, "does-not-exist", user)
    assert exc_info.value.status_code == 404
