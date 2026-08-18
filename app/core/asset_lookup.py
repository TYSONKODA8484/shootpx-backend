"""Cached Asset row lookups (the "media" cache namespace) — used wherever
a response needs to resolve a set of asset ids into full rows, e.g.
GenerationJobSummary's source/output asset refs. GET /jobs and GET
/batches/{id} get polled repeatedly while a job is running, re-resolving
the same asset ids on every poll; assets are effectively immutable once
created (no update/delete endpoint exists anywhere in this app), so
there's no write path that needs to invalidate this — MEDIA_CACHE_TTL_SECONDS
is the only thing bounding staleness, and nothing can actually go stale
in a way that matters.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import settings
from app.models.asset import Asset

NAMESPACE = "media"


def _to_cache(asset: Asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "team_id": asset.team_id,
        "created_by": asset.created_by,
        "kind": asset.kind,
        "media_type": asset.media_type,
        "storage_key": asset.storage_key,
        "url": asset.url,
        "product_import_id": asset.product_import_id,
        "created_at": asset.created_at.isoformat(),
    }


def _from_cache(data: dict[str, Any]) -> Asset:
    # Transient instance, same caveat as middleware/auth.py's User cache:
    # fine for reading columns (every caller here only reads .url and
    # .media_type), not safe if anything ever reads a relationship off it.
    return Asset(
        id=data["id"],
        team_id=data["team_id"],
        created_by=data["created_by"],
        kind=data["kind"],
        media_type=data["media_type"],
        storage_key=data["storage_key"],
        url=data["url"],
        product_import_id=data["product_import_id"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def get_assets_cached(db: Session, asset_ids: set[str]) -> dict[str, Asset]:
    """Bulk lookup by id: check the cache for each id, then one batched
    DB query (IN (...)) for whatever's missing — never N individual
    queries. Populates the cache for anything freshly fetched."""
    if not asset_ids:
        return {}

    result: dict[str, Asset] = {}
    missing: list[str] = []
    for asset_id in asset_ids:
        cached = cache.get(NAMESPACE, asset_id)
        if cached is not None:
            result[asset_id] = _from_cache(cached)
        else:
            missing.append(asset_id)

    if missing:
        rows = db.query(Asset).filter(Asset.id.in_(missing)).all()
        for asset in rows:
            result[asset.id] = asset
            cache.set(NAMESPACE, asset.id, _to_cache(asset), ttl_seconds=settings.MEDIA_CACHE_TTL_SECONDS)

    return result
