"""tests/test_storage.py — LocalStorage.delete() behavior."""

import os

from app.core.storage import LocalStorage


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
