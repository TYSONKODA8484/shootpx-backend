from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.controllers import team_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.team import TeamRole
from app.models.user import User
from app.schemas.teams import AddMemberResult, InviteOut, MemberAdd, MemberOut, TeamCreate, TeamOut

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    team, role = team_controller.create_team(db, current_user, payload)
    return TeamOut(id=team.id, name=team.name, role=role)


@router.get("", response_model=list[TeamOut])
def list_my_teams(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = team_controller.list_my_teams(db, current_user)
    return [TeamOut(id=team.id, name=team.name, role=TeamRole(role)) for team, role in rows]


@router.get("/{team_id}/members", response_model=list[MemberOut])
def list_members(team_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = team_controller.list_members(db, team_id, current_user)
    return [
        MemberOut(user_id=u.id, email=u.email, name=u.name, avatar_url=u.avatar_url, role=TeamRole(role))
        for u, role in rows
    ]


@router.get("/{team_id}/invites", response_model=list[InviteOut])
def list_pending_invites(team_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invites = team_controller.list_pending_invites(db, team_id, current_user)
    return [
        InviteOut(id=i.id, email=i.email, role=TeamRole(i.role), created_at=i.created_at.isoformat())
        for i in invites
    ]


@router.post("/{team_id}/members", response_model=AddMemberResult, status_code=status.HTTP_201_CREATED)
def add_member(
    team_id: str,
    payload: MemberAdd,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    outcome, result = team_controller.add_member(db, team_id, current_user, payload)

    if outcome == "added":
        return AddMemberResult(
            status="added",
            member=MemberOut(
                user_id=result.id, email=result.email, name=result.name, avatar_url=result.avatar_url,
                role=payload.role,
            ),
        )

    background_tasks.add_task(
        team_controller.send_team_invite_email, result.email, result.team.name, payload.continue_url
    )
    return AddMemberResult(
        status="invited",
        invite=InviteOut(id=result.id, email=result.email, role=TeamRole(result.role), created_at=result.created_at.isoformat()),
    )
