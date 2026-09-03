"""tests/test_storage.py — LocalStorage.delete() behavior, and
SupabaseStorage's request shape (httpx itself is monkeypatched, so these
verify what gets sent, not a real Supabase project)."""

import os

import httpx
import pytest

from app.core.storage import LocalStorage, SupabaseStorage


def test_delete_removes_the_file(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path), base_url="http://x/files")
    storage.save("team-1/thing.png", b"hello")
    full_path = tmp_path / "team-1" / "thing.png"
    assert full_path.exists()

    storage.delete("team-1/thing.png")

    assert not full_path.exists()


def test_delete_is_a_noop_for_a_missing_file(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path), base_url="http://x/files")
    storage.delete("team-1/does-not-exist.png")  # must not raise


def test_read_returns_saved_bytes(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path), base_url="http://x/files")
    storage.save("team-1/thing.png", b"hello world")

    assert storage.read("team-1/thing.png") == b"hello world"


# --- SupabaseStorage ---------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def _supabase_storage():
    return SupabaseStorage(
        project_url="https://xxxx.supabase.co",
        service_role_key="service-role-secret",
        bucket="shootpx-assets",
    )


def test_save_posts_to_object_endpoint_with_upsert_and_guessed_content_type(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, content=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["content"] = content
        return _FakeResponse(200)

    monkeypatch.setattr(httpx, "post", fake_post)
    storage = _supabase_storage()

    storage.save("team-1/thing.png", b"hello world")

    assert captured["url"] == "https://xxxx.supabase.co/storage/v1/object/shootpx-assets/team-1/thing.png"
    assert captured["content"] == b"hello world"
    assert captured["headers"]["Content-Type"] == "image/png"
    assert captured["headers"]["x-upsert"] == "true"
    assert captured["headers"]["Authorization"] == "Bearer service-role-secret"


def test_save_raises_on_a_failed_upload(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(500))
    storage = _supabase_storage()

    with pytest.raises(httpx.HTTPStatusError):
        storage.save("team-1/thing.png", b"hello world")


def test_url_for_builds_the_public_object_url():
    storage = _supabase_storage()

    assert (
        storage.url_for("team-1/thing.png")
        == "https://xxxx.supabase.co/storage/v1/object/public/shootpx-assets/team-1/thing.png"
    )


def test_delete_sends_the_key_as_a_prefix_to_the_bucket_endpoint(monkeypatch):
    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        captured.update(method=method, url=url, json=json)
        return _FakeResponse(200)

    monkeypatch.setattr(httpx, "request", fake_request)
    storage = _supabase_storage()

    storage.delete("team-1/thing.png")

    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://xxxx.supabase.co/storage/v1/object/shootpx-assets"
    assert captured["json"] == {"prefixes": ["team-1/thing.png"]}


def test_delete_is_a_noop_for_a_missing_supabase_object(monkeypatch):
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _FakeResponse(404))
    storage = _supabase_storage()

    storage.delete("team-1/does-not-exist.png")  # must not raise


def test_supabase_read_returns_the_response_body(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(200, content=b"hello world"))
    storage = _supabase_storage()

    assert storage.read("team-1/thing.png") == b"hello world"
