"""tests/test_asset_library.py — list_assets/delete_asset controller logic.
Storage and cache are monkeypatched to plain recording stand-ins so these
tests don't need real disk or Redis — they verify the CONTROLLER's
behavior (who can see/delete what, which calls it makes), not the seams
themselves (those are covered by test_storage.py and core/cache.py already
being trusted infra).
"""

import pytest
from fastapi import HTTPException

from app.controllers import asset_controller
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import Team, TeamMembership, new_id
from app.models.user import User


def _make_team_and_user(db, role="owner"):
    team = Team(id=new_id(), name="Test Team")
    user = User(id=new_id(), email=f"{new_id()}@example.com")
    db.add_all([team, user])
    db.commit()
    db.add(TeamMembership(id=new_id(), team_id=team.id, user_id=user.id, role=role))
    db.commit()
    return team, user


def _make_asset(db, team, user, kind=AssetKind.upload.value, media_type=MediaType.image.value, key=None):
    key = key or f"{team.id}/{new_id()}.png"
    asset = Asset(
        team_id=team.id, created_by=user.id, kind=kind, media_type=media_type,
        storage_key=key, url=f"http://x/files/{key}",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def test_list_assets_returns_only_this_teams_assets(db_session):
    team_a, user_a = _make_team_and_user(db_session)
    team_b, user_b = _make_team_and_user(db_session)
    _make_asset(db_session, team_a, user_a)
    _make_asset(db_session, team_b, user_b)

    result = asset_controller.list_assets(db_session, team_a.id, user_a)

    assert result.total == 1
    assert result.assets[0].team_id == team_a.id


def test_list_assets_filters_by_kind_and_media_type(db_session):
    team, user = _make_team_and_user(db_session)
    _make_asset(db_session, team, user, kind=AssetKind.upload.value)
    _make_asset(db_session, team, user, kind=AssetKind.generated.value)

    result = asset_controller.list_assets(db_session, team.id, user, kind="generated")

    assert result.total == 1
    assert result.assets[0].kind == AssetKind.generated.value


def test_list_assets_404s_for_a_non_member(db_session):
    team, _owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.list_assets(db_session, team.id, outsider)
    assert exc_info.value.status_code == 404


def test_delete_asset_removes_row_and_calls_storage_and_cache(db_session, monkeypatch):
    team, user = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, user)
    asset_id, storage_key = asset.id, asset.storage_key

    deleted_keys = []
    cache_deletes = []
    monkeypatch.setattr(asset_controller.storage, "delete", lambda key: deleted_keys.append(key))
    monkeypatch.setattr(asset_controller.cache, "delete", lambda ns, key: cache_deletes.append((ns, key)))

    asset_controller.delete_asset(db_session, asset_id, user)

    assert deleted_keys == [storage_key]
    assert cache_deletes == [("media", asset_id)]
    assert db_session.get(Asset, asset_id) is None


def test_delete_asset_404s_for_missing_asset(db_session):
    _team, user = _make_team_and_user(db_session)
    with pytest.raises(HTTPException) as exc_info:
        asset_controller.delete_asset(db_session, "does-not-exist", user)
    assert exc_info.value.status_code == 404


def test_delete_asset_404s_for_a_non_member(db_session, monkeypatch):
    team, owner = _make_team_and_user(db_session)
    _, outsider = _make_team_and_user(db_session)
    asset = _make_asset(db_session, team, owner)
    monkeypatch.setattr(asset_controller.storage, "delete", lambda key: None)
    monkeypatch.setattr(asset_controller.cache, "delete", lambda ns, key: None)

    with pytest.raises(HTTPException) as exc_info:
        asset_controller.delete_asset(db_session, asset.id, outsider)
    assert exc_info.value.status_code == 404
