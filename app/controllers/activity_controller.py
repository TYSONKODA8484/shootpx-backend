"""Computed activity feed — Option 1 from the B2 design spec. No new table:
unions recent rows from generation_jobs, product_imports, and a curated
subset of credit_transactions, sorted and paginated in Python. Each source
query is capped at `limit` rows independently before the merge, so this is
an approximation of true cross-stream keyset pagination, not exact — fine
for a feed with no dedicated table backing it (see BACKEND-NEEDS.md's B2
section: "Option 1, no write path to build").
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.asset_lookup import get_assets_cached
from app.core.permissions import get_membership
from app.models.asset import Asset
from app.models.credit import CreditReason, CreditTransaction
from app.models.generation_job import GenerationJob, JobStatus
from app.models.product_import import ProductImport, ProductImportStatus
from app.models.tool import Tool
from app.models.user import User
from app.schemas.activity import ActivityEvent, ActivityFeedOut

# Not every credit_transactions row belongs in a human-readable feed — a
# generation_spend row fires once per job and would drown out everything
# else (BACKEND-NEEDS.md's own example: "not every single generation
# deduction"). Only reasons worth surfacing as their own feed entry:
CURATED_CREDIT_REASONS = {
    CreditReason.plan_grant.value,
    CreditReason.topup_purchase.value,
    CreditReason.subscription_cancelled.value,
}


def get_activity_feed(
    db: Session,
    team_id: str,
    current_user: User,
    limit: int = 20,
    before: str | None = None,
) -> ActivityFeedOut:
    get_membership(db, team_id, current_user.id)
    limit = max(1, min(limit, 100))
    before_dt = datetime.fromisoformat(before) if before else None

    job_query = db.query(GenerationJob).filter(
        GenerationJob.team_id == team_id,
        GenerationJob.status.in_([JobStatus.done.value, JobStatus.failed.value]),
    )
    if before_dt:
        job_query = job_query.filter(GenerationJob.created_at < before_dt)
    jobs = job_query.order_by(GenerationJob.created_at.desc()).limit(limit).all()

    import_query = db.query(ProductImport).filter(
        ProductImport.team_id == team_id,
        ProductImport.status.in_([ProductImportStatus.done.value, ProductImportStatus.failed.value]),
    )
    if before_dt:
        import_query = import_query.filter(ProductImport.created_at < before_dt)
    imports = import_query.order_by(ProductImport.created_at.desc()).limit(limit).all()

    credit_query = db.query(CreditTransaction).filter(
        CreditTransaction.team_id == team_id,
        CreditTransaction.reason.in_(CURATED_CREDIT_REASONS),
    )
    if before_dt:
        credit_query = credit_query.filter(CreditTransaction.created_at < before_dt)
    credits = credit_query.order_by(CreditTransaction.created_at.desc()).limit(limit).all()

    feature_types = {j.feature_type for j in jobs}
    tools_by_type = (
        {t.feature_type: t for t in db.query(Tool).filter(Tool.feature_type.in_(feature_types)).all()}
        if feature_types else {}
    )

    output_asset_ids = {j.output_asset_id for j in jobs if j.output_asset_id}
    assets_by_id = get_assets_cached(db, output_asset_ids) if output_asset_ids else {}

    import_ids = [i.id for i in imports]
    first_image_by_import: dict[str, str] = {}
    if import_ids:
        images = (
            db.query(Asset)
            .filter(Asset.product_import_id.in_(import_ids))
            .order_by(Asset.created_at.asc())
            .all()
        )
        for img in images:
            first_image_by_import.setdefault(img.product_import_id, img.url)

    events: list[ActivityEvent] = []

    for j in jobs:
        tool = tools_by_type.get(j.feature_type)
        title = tool.display_name if tool else j.feature_type
        detail = "Completed" if j.status == JobStatus.done.value else f"Failed: {j.error or 'unknown error'}"
        asset = assets_by_id.get(j.output_asset_id) if j.output_asset_id else None
        events.append(ActivityEvent(
            id=f"job:{j.id}", kind="job", title=title, detail=detail, status=j.status,
            created_at=j.created_at.isoformat(), asset_url=asset.url if asset else None,
        ))

    for i in imports:
        title = i.product_name or i.source_url
        events.append(ActivityEvent(
            id=f"import:{i.id}", kind="import", title=title, detail=i.status.capitalize(), status=i.status,
            created_at=i.created_at.isoformat(), asset_url=first_image_by_import.get(i.id),
        ))

    for c in credits:
        sign = "+" if c.amount > 0 else ""
        events.append(ActivityEvent(
            id=f"credit:{c.id}", kind="credit", title=c.reason.replace("_", " ").title(),
            detail=f"{sign}{c.amount} credits", status=None,
            created_at=c.created_at.isoformat(), asset_url=None,
        ))

    events.sort(key=lambda e: e.created_at, reverse=True)
    page = events[:limit]
    next_cursor = page[-1].created_at if len(page) == limit else None
    return ActivityFeedOut(events=page, next_cursor=next_cursor)
