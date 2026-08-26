"""Generic CRUD against whatever's registered in app/core/cms_registry.py —
list/get/create/update/delete/stats, all driven by EntityConfig instead of
one hand-written set of endpoints per table. app/routes/cms_routes.py is a
thin HTTP wrapper around these functions; auth (get_current_admin) lives at
the route layer, not here — these functions assume the caller already
checked that.
"""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import cache
from app.core.cms_registry import ENTITIES, EntityConfig, FieldConfig
from app.core.config import settings
from app.models.credit import TeamCreditBalance
from app.models.plan import Plan
from app.models.subscription import TeamSubscription
from app.models.team import Team
from app.models.user import User

PAGE_SIZE = 50


def verify_admin_password(password: str) -> bool:
    return bool(settings.CMS_ADMIN_PASSWORD) and password == settings.CMS_ADMIN_PASSWORD


def get_entity_config(entity: str) -> EntityConfig:
    config = ENTITIES.get(entity)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown entity: {entity!r}")
    return config


def describe_entities() -> list[dict[str, Any]]:
    return [
        {
            "name": c.name,
            "label": c.label,
            "pk_field": c.pk_field,
            "pk_provided_on_create": c.pk_provided_on_create,
            "allow_create": c.allow_create,
            "allow_update": c.allow_update,
            "allow_delete": c.allow_delete,
            "search_fields": c.search_fields,
            "fields": [
                {
                    "name": f.name,
                    "kind": f.kind,
                    "editable": f.editable,
                    "enum_values": f.enum_values,
                    "fk_entity": f.fk_entity,
                    "help_text": f.help_text,
                }
                for f in c.fields
            ],
        }
        for c in ENTITIES.values()
    ]


def serialize_row(config: EntityConfig, row: Any) -> dict[str, Any]:
    result = {}
    for f in config.fields:
        value = getattr(row, f.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        result[f.name] = value
    return result


def _coerce(f: FieldConfig | None, value: Any) -> Any:
    if f is not None and value is not None and f.kind == "datetime" and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


def _invalidate_cache(config: EntityConfig, row_id: Any) -> None:
    if config.cache_namespace:
        cache.delete(config.cache_namespace, str(row_id))


def _not_found(config: EntityConfig, row_id: Any) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{config.name} {row_id!r} not found")


def list_rows(db: Session, config: EntityConfig, page: int, search: str | None) -> dict[str, Any]:
    query = db.query(config.model)
    if search and config.search_fields:
        like = f"%{search}%"
        conditions = [getattr(config.model, name).ilike(like) for name in config.search_fields]
        query = query.filter(or_(*conditions))
    total = query.count()
    rows = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()
    return {
        "items": [serialize_row(config, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
    }


def get_row(db: Session, config: EntityConfig, row_id: str) -> dict[str, Any]:
    row = db.get(config.model, row_id)
    if row is None:
        raise _not_found(config, row_id)
    return serialize_row(config, row)


def create_row(db: Session, config: EntityConfig, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.allow_create:
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                             detail=f"{config.name} rows can't be created here")

    field_by_name = {f.name: f for f in config.fields}
    allowed_names = {f.name for f in config.fields if f.editable}
    if config.pk_provided_on_create:
        allowed_names.add(config.pk_field)
        if not payload.get(config.pk_field):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"{config.pk_field!r} is required to create a {config.name}")

    unknown = set(payload) - allowed_names
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not creatable: {sorted(unknown)}")

    kwargs = {key: _coerce(field_by_name.get(key), value) for key, value in payload.items()}
    row = config.model(**kwargs)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig)) from exc
    db.refresh(row)
    _invalidate_cache(config, getattr(row, config.pk_field))
    return serialize_row(config, row)


def update_row(db: Session, config: EntityConfig, row_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not config.allow_update:
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                             detail=f"{config.name} rows can't be edited")
    row = db.get(config.model, row_id)
    if row is None:
        raise _not_found(config, row_id)

    field_by_name = {f.name: f for f in config.fields}
    editable_names = {f.name for f in config.fields if f.editable}
    unknown = set(payload) - editable_names
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Not editable: {sorted(unknown)}")

    for key, value in payload.items():
        setattr(row, key, _coerce(field_by_name[key], value))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig)) from exc
    db.refresh(row)
    _invalidate_cache(config, row_id)
    return serialize_row(config, row)


def delete_row(db: Session, config: EntityConfig, row_id: str) -> dict[str, Any]:
    if not config.allow_delete:
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                             detail=f"{config.name} rows can't be deleted")
    row = db.get(config.model, row_id)
    if row is None:
        raise _not_found(config, row_id)

    db.delete(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc.orig)) from exc
    _invalidate_cache(config, row_id)
    return {"deleted": row_id}


def get_stats(db: Session) -> dict[str, Any]:
    total_users = db.query(User).count()
    total_teams = db.query(Team).count()
    subs_by_plan = (
        db.query(Plan.name, func.count(TeamSubscription.id))
        .join(TeamSubscription, TeamSubscription.plan_id == Plan.id)
        .group_by(Plan.name)
        .all()
    )
    total_credit_balance = db.query(func.coalesce(func.sum(TeamCreditBalance.balance), 0)).scalar()
    return {
        "total_users": total_users,
        "total_teams": total_teams,
        "subscriptions_by_plan": {name: count for name, count in subs_by_plan},
        "total_credit_balance": total_credit_balance,
    }
