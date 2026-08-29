"""app/worker.py's lock key — per-user, not per-team, so different members
of the same team can generate concurrently while one user's own second
generation still queues behind their first. See
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md's
addendum."""

from app.worker import _user_lock_key


def test_user_lock_key_is_scoped_by_user_not_team():
    assert _user_lock_key("user-1") == "lock:user:user-1"
    assert _user_lock_key("user-1") != _user_lock_key("user-2")
