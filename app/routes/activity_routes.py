from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.controllers import activity_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.activity import ActivityFeedOut

router = APIRouter(tags=["activity"])


@router.get("/teams/{team_id}/activity", response_model=ActivityFeedOut)
def get_activity_feed(
    team_id: str,
    limit: int = Query(default=20, le=100, gt=0),
    before: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return activity_controller.get_activity_feed(db, team_id, current_user, limit=limit, before=before)
