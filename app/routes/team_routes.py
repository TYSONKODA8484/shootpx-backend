from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app.controllers import team_controller
from app.core.db import get_db
from app.middleware.auth import get_current_user
from app.models.team import Team, TeamRole
from app.models.user import User
from app.schemas.teams import AddMemberResult, InviteOut, MemberAdd, MemberOut, TeamCreate, TeamOut, TeamUpdate

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    team, role = team_controller.create_team(db, current_user, payload)
    return TeamOut(id=team.id, name=team.name, role=role)


@router.get("", response_model=list[TeamOut])
def list_my_teams(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = team_controller.list_my_teams(db, current_user)
    return [TeamOut(id=team.id, name=team.name, role=TeamRole(role)) for team, role in rows]


@router.patch("/{team_id}", response_model=TeamOut)
def rename_team(
    team_id: str,
    payload: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    team = team_controller.rename_team(db, team_id, current_user, payload)
    membership = team_controller.get_membership(db, team_id, current_user.id)
    return TeamOut(id=team.id, name=team.name, role=TeamRole(membership.role))


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
        InviteOut(
            id=i.id, email=i.email, role=TeamRole(i.role),
            created_at=i.created_at.isoformat(), expires_at=i.expires_at.isoformat(),
        )
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
    """ALWAYS creates a pending invite and emails it — see
    team_controller.add_member's docstring. The invited person is not a
    team member until they click the emailed link (which lands on
    continue_url with ?invite_id=... appended) and it's accepted via
    POST /auth/session."""
    invite = team_controller.add_member(db, team_id, current_user, payload)

    team = db.get(Team, team_id)
    background_tasks.add_task(
        team_controller.send_team_invite_email, invite.email, team.name, payload.continue_url, invite.id
    )
    return AddMemberResult(
        invite=InviteOut(
            id=invite.id, email=invite.email, role=TeamRole(invite.role),
            created_at=invite.created_at.isoformat(), expires_at=invite.expires_at.isoformat(),
        ),
    )


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    team_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-only. 400 if user_id is yourself (use DELETE /teams/{team_id}
    instead) or the team's last remaining owner — see
    team_controller.remove_member's docstring."""
    team_controller.remove_member(db, team_id, current_user, user_id)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Owner-only SOFT delete — see Team's and team_controller.delete_team's
    docstrings. 400 if there's a currently-active paid subscription;
    cancel it first via POST /billing/cancel."""
    team_controller.delete_team(db, team_id, current_user)
