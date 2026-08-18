"""Generic namespaced read-through cache on top of Redis — the same Redis
instance already backing the arq queue and per-team lock (REDIS_URL,
core/config.py). A namespace ("login", "media", ...) is just a key prefix,
so clear_namespace() can wipe one concern (e.g. "flush every cached user
during an incident") without touching any other's cached data — that's
the whole reason this isn't just one flat cache. Adding a new namespace
(a future "feed" cache, say) needs nothing here; callers just pass a new
namespace string.

Sync client, not redis.asyncio — every caller today (middleware/auth.py,
core/asset_lookup.py) is sync code, and this codebase's DB layer
(SessionLocal) is sync throughout, so matching that avoids mixing async
Redis calls into sync request-handling code for no benefit.

Values are cached as plain JSON-able dicts, not ORM instances — callers
convert to/from their model on either side (see asset_lookup.py for the
pattern). A cached SQLAlchemy instance would be detached from any Session,
and reconstructing one via Model(**dict) only stays safe as long as
nothing touches a relationship on it — worth the small conversion step to
not have to remember that rule at every call site.
"""

import json
from typing import Any

import redis

from app.core.config import settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _client


def _key(namespace: str, key: str) -> str:
    return f"cache:{namespace}:{key}"


def get(namespace: str, key: str) -> Any | None:
    raw = _get_client().get(_key(namespace, key))
    return json.loads(raw) if raw is not None else None


def set(namespace: str, key: str, value: Any, ttl_seconds: int) -> None:
    _get_client().set(_key(namespace, key), json.dumps(value), ex=ttl_seconds)


def delete(namespace: str, key: str) -> None:
    _get_client().delete(_key(namespace, key))


def clear_namespace(namespace: str) -> int:
    """Deletes every key in one namespace — the manual 'cache cleaning'
    escape hatch (e.g. from a shell: `python -c "from app.core.cache import
    clear_namespace; clear_namespace('media')"`) for whenever TTL expiry
    and the explicit invalidation call sites aren't enough — after a bug
    that cached something wrong, say. Uses SCAN, not KEYS, so clearing a
    large namespace doesn't block Redis while it runs. Returns how many
    keys were deleted."""
    client = _get_client()
    pattern = _key(namespace, "*")
    n = 0
    for k in client.scan_iter(match=pattern, count=500):
        client.delete(k)
        n += 1
    return n
