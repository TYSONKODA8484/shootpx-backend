from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email import send_email
from app.core.firebase import generate_email_sign_in_link
from app.core.permissions import compute_permissions, get_membership
from app.models.invite import TeamInvite
from app.models.team import Team, TeamMembership, TeamRole, new_id
from app.models.user import User
from app.schemas.teams import MemberAdd, TeamCreate


def send_team_invite_email(email: str, team_name: str, continue_url: str) -> None:
    """The invite IS a sign-in link — clicking it both creates their account
    (if they didn't have one) and, via accept_pending_invites() running
    right after login, drops them straight into the team."""
    link = generate_email_sign_in_link(email, continue_url)
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2>You've been invited to "{team_name}" on {settings.APP_NAME}</h2>
      <p>Click below to sign in and join the team.</p>
      <p style="margin: 24px 0;">
        <a href="{link}"
           style="background:#111;color:#fff;padding:12px 20px;border-radius:6px;text-decoration:none;">
          Join {team_name}
        </a>
      </p>
      <p>If you weren't expecting this, you can safely ignore this email.</p>
    </div>
    """
    send_email(email, f"You've been invited to {team_name} on {settings.APP_NAME}", html)


def create_team(db: Session, current_user: User, payload: TeamCreate) -> tuple[Team, TeamRole]:
    team = Team(name=payload.name)
    db.add(team)
    db.flush()  # get team.id (app-generated) before creating the membership row

    membership = TeamMembership(team_id=team.id, user_id=current_user.id, role=TeamRole.owner.value)
    db.add(membership)
    db.commit()
    db.refresh(team)
    return team, TeamRole.owner


def list_my_teams(db: Session, current_user: User) -> list[tuple[Team, str]]:
    return (
        db.query(Team, TeamMembership.role)
        .join(TeamMembership, TeamMembership.team_id == Team.id)
        .filter(TeamMembership.user_id == current_user.id)
        .all()
    )


def list_members(db: Session, team_id: str, current_user: User) -> list[tuple[User, str]]:
    get_membership(db, team_id, current_user.id)  # any member can see the roster
    return (
        db.query(User, TeamMembership.role)
        .join(TeamMembership, TeamMembership.user_id == User.id)
        .filter(TeamMembership.team_id == team_id)
        .all()
    )


def list_pending_invites(db: Session, team_id: str, current_user: User) -> list[TeamInvite]:
    get_membership(db, team_id, current_user.id)
    return (
        db.query(TeamInvite)
        .filter(TeamInvite.team_id == team_id, TeamInvite.accepted_at.is_(None))
        .all()
    )


def add_member(db: Session, team_id: str, current_user: User, payload: MemberAdd):
    """Returns ("added", User) if the person already had an account and is
    now a member, or ("invited", TeamInvite) if they don't exist yet and
    we've parked a pending invite for when they first sign in."""
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team owner can add members")

    email = payload.email.lower()
    target = db.query(User).filter(User.email == email).first()

    if target:
        existing = (
            db.query(TeamMembership)
            .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == target.id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member of this team")

        new_membership = TeamMembership(team_id=team_id, user_id=target.id, role=payload.role.value)
        db.add(new_membership)
        db.commit()
        return "added", target

    existing_invite = (
        db.query(TeamInvite)
        .filter(TeamInvite.team_id == team_id, TeamInvite.email == email, TeamInvite.accepted_at.is_(None))
        .first()
    )
    if existing_invite:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already invited to this team")

    invite = TeamInvite(
        id=new_id(),
        team_id=team_id,
        email=email,
        role=payload.role.value,
        invited_by=current_user.id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return "invited", invite


def accept_pending_invites(db: Session, user: User) -> None:
    """Call this right after any successful login. Turns every un-accepted
    invite for this user's email into a real team membership — this is what
    makes "invite someone with no account" work regardless of whether they
    end up signing in with Google or an email link."""
    pending = (
        db.query(TeamInvite)
        .filter(TeamInvite.email == user.email, TeamInvite.accepted_at.is_(None))
        .all()
    )
    if not pending:
        return

    for invite in pending:
        already_member = (
            db.query(TeamMembership)
            .filter(TeamMembership.team_id == invite.team_id, TeamMembership.user_id == user.id)
            .first()
        )
        if not already_member:
            db.add(TeamMembership(team_id=invite.team_id, user_id=user.id, role=invite.role))
        invite.accepted_at = datetime.utcnow()

    db.commit()
