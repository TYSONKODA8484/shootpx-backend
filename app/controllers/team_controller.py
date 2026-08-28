from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.controllers.billing_controller import assign_free_plan
from app.core.config import settings
from app.core.email import send_email
from app.core.firebase import generate_email_sign_in_link
from app.core.permissions import compute_permissions, get_membership
from app.core.time import utc_now
from app.models.invite import INVITE_EXPIRY, TeamInvite
from app.models.plan import Plan
from app.models.subscription import SubscriptionStatus, TeamSubscription
from app.models.team import Team, TeamMembership, TeamRole, new_id
from app.models.user import User
from app.schemas.teams import MemberAdd, TeamCreate, TeamUpdate


def send_team_invite_email(email: str, team_name: str, continue_url: str, invite_id: str) -> None:
    """Sent for EVERY invite, whether the email already has an account or
    not — see add_member's docstring. The link is the same Firebase
    magic-link sign-in mechanism used for ordinary login (Firebase doesn't
    care whether the email is new or existing; it just authenticates it),
    with invite_id appended to continue_url as a query param so
    /auth/session knows exactly WHICH invite to accept once they land back
    on the frontend — never a blanket "accept everything pending for this
    email" sweep. If they're already logged in on that device, clicking
    the link still round-trips them through Firebase (a fresh sign-in),
    which is a deliberate trade-off for "this exact link, this exact
    invite" being unambiguous — see the design discussion this replaced
    (accept_pending_invites' old blanket-sweep behavior)."""
    separator = "&" if "?" in continue_url else "?"
    link = generate_email_sign_in_link(email, f"{continue_url}{separator}invite_id={invite_id}")
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: auto;">
      <h2>You've been invited to "{team_name}" on {settings.APP_NAME}</h2>
      <p>Click below to sign in and join the team. This link expires in 48 hours.</p>
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
        .filter(TeamMembership.user_id == current_user.id, Team.is_active == True)  # noqa: E712
        # Soft-deleted teams (delete_team below) never appear here again —
        # same "gone from the client, data stays in the DB" contract as
        # Tool.is_active/NavItem.is_active elsewhere.
        .order_by(Team.created_at.asc())
        # Oldest first — the personal team (create_personal_team, below) is
        # always created before any other team a user joins, so index 0 of
        # this list is always reliably "theirs". This is what lets a client
        # (the test console, later a real frontend) safely default to it.
        .all()
    )


def create_personal_team(db: Session, user: User) -> Team:
    """Called once, right after a brand-new user's first-ever sign-in
    (auth_routes.py, when upsert_user_from_firebase reports is_new=True).
    Gives every user a team to work in immediately, without ever requiring
    them to manually call POST /teams for solo use — team_id stays a
    required field everywhere else; this just guarantees one always exists."""
    base_name = user.name or user.email.split("@")[0]
    team, _ = create_team(db, user, TeamCreate(name=f"{base_name}'s Workspace"))

    # Assign the Free plan + grant its starter credits SYNCHRONOUSLY — a
    # brand-new signup must never wait on the refill cron for its first
    # credits. See billing_controller.assign_free_plan / BOOK.md Chapter 17.
    assign_free_plan(db, team)

    return team


def rename_team(db: Session, team_id: str, current_user: User, payload: TeamUpdate) -> Team:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team owner can rename this team")

    team = db.get(Team, team_id)
    team.name = payload.name
    db.commit()
    db.refresh(team)
    return team


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


def add_member(db: Session, team_id: str, current_user: User, payload: MemberAdd) -> TeamInvite:
    """ALWAYS creates a pending TeamInvite and emails it — regardless of
    whether the invited email already has an account. Nobody is ever added
    to a team immediately by this call; membership only happens when that
    specific invite is accepted (accept_invite, via the emailed link) —
    see TeamInvite's docstring for why. Callers (team_routes.py) are
    responsible for actually sending the email via
    send_team_invite_email — this function just creates the row."""
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team owner can add members")

    # Hard block at the plan's max_team_members — same "reject, don't
    # silently overage" philosophy as credit enforcement
    # (generation_controller.py). Counts CURRENT members plus pending
    # (unaccepted, unexpired) invites, so a team can't be over-invited past
    # its cap and then have acceptance silently blow past the limit later —
    # the check that actually matters is repeated at accept_invite too,
    # since a plan downgrade between invite and acceptance is possible.
    # Fails open if there's no subscription row yet (shouldn't happen post
    # Spec B, but a team predating it shouldn't be blocked over a missing
    # billing row).
    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub is not None:
        plan = db.get(Plan, sub.plan_id)
        if plan is not None:
            current_member_count = db.query(TeamMembership).filter(TeamMembership.team_id == team_id).count()
            pending_invite_count = (
                db.query(TeamInvite)
                .filter(TeamInvite.team_id == team_id, TeamInvite.accepted_at.is_(None), TeamInvite.expires_at > utc_now())
                .count()
            )
            if current_member_count + pending_invite_count >= plan.max_team_members:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Team member limit ({plan.max_team_members}) reached for the current plan — upgrade to add more",
                )

    email = payload.email.lower()

    already_member = (
        db.query(TeamMembership)
        .join(User, User.id == TeamMembership.user_id)
        .filter(TeamMembership.team_id == team_id, User.email == email)
        .first()
    )
    if already_member:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member of this team")

    existing_invite = (
        db.query(TeamInvite)
        .filter(
            TeamInvite.team_id == team_id, TeamInvite.email == email,
            TeamInvite.accepted_at.is_(None), TeamInvite.expires_at > utc_now(),
        )
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
        expires_at=utc_now() + INVITE_EXPIRY,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def remove_member(db: Session, team_id: str, current_user: User, target_user_id: str) -> None:
    """Owner-only, same gate as add_member. Two things it deliberately
    blocks, both 400s rather than a generic 403/404:
      - removing yourself via this endpoint — an owner "leaving" their own
        team isn't supported today (there's no ownership-transfer flow, so
        it would either leave the team ownerless or silently need to pick
        a new owner); ask them to use delete_team instead if that's really
        the goal.
      - removing the last remaining owner — a team with zero owners can
        never be managed again (rename, subscribe, invite, delete — all
        owner-gated), so this is a dead-end state worth refusing outright
        rather than allowing and discovering later.
    """
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team owner can remove members")

    if target_user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owners cannot remove themselves — delete the team instead")

    target_membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == target_user_id)
        .first()
    )
    if target_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That user is not a member of this team")

    if target_membership.role == TeamRole.owner.value:
        owner_count = (
            db.query(TeamMembership)
            .filter(TeamMembership.team_id == team_id, TeamMembership.role == TeamRole.owner.value)
            .count()
        )
        if owner_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the last owner of a team")

    db.delete(target_membership)
    db.commit()


def delete_team(db: Session, team_id: str, current_user: User) -> None:
    """Owner-only SOFT delete — see Team's docstring for why this isn't a
    real DELETE. Sets is_active=False + deleted_at; the row and everything
    FK'd to it (assets, generation jobs, payments, credit history, ...)
    stays in the DB untouched, just no longer reachable through any
    team-scoped endpoint (get_membership below and list_my_teams above
    both exclude it).

    Blocked (400) while there's a currently-active PAID subscription —
    cancel it first (POST /billing/cancel) so Razorpay's own billing state
    and this team's "deleted" state never disagree; a Free-plan team (or
    one whose subscription is already cancelled/past_due) deletes freely.
    Idempotent-ish: deleting an already-deleted team 404s via
    get_membership (soft-deleted teams aren't found by membership lookups
    that check is_active — see the note below) rather than silently
    no-op'ing twice.
    """
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_manage_team:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the team owner can delete this team")

    sub = db.query(TeamSubscription).filter(TeamSubscription.team_id == team_id).first()
    if sub is not None and sub.status == SubscriptionStatus.active.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cancel the active subscription before deleting this team",
        )

    team = db.get(Team, team_id)
    team.is_active = False
    team.deleted_at = utc_now()
    db.commit()


def accept_invite(db: Session, user: User, invite_id: str) -> TeamInvite | None:
    """Called from /auth/session with the invite_id encoded in the invite
    email's link (see send_team_invite_email) — accepts ONLY that specific
    invite, never a blanket sweep of every pending invite for this email
    (that was the old accept_pending_invites behavior; replaced because it
    meant ANY login, even via an unrelated link, silently joined someone
    to every team they'd ever been invited to with no real per-invite
    consent). Returns None (a no-op, not an error) for:
      - an unknown invite_id (already handled elsewhere, or garbage input)
      - an invite already accepted
      - an EXPIRED invite (created_at + 48h passed — TeamInvite.expires_at)
      - an invite whose email doesn't match this user's email (can't
        accept someone else's invite by guessing/reusing an invite_id)
    Returning None rather than raising lets the caller (auth_routes.py)
    treat "no invite to accept" as a normal login, not a failure — the
    frontend redirected here from an old/expired link shouldn't block
    someone from just logging in."""
    invite = db.get(TeamInvite, invite_id)
    if invite is None or invite.accepted_at is not None or invite.expires_at <= utc_now():
        return None
    if invite.email != user.email:
        return None

    already_member = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == invite.team_id, TeamMembership.user_id == user.id)
        .first()
    )
    if not already_member:
        db.add(TeamMembership(team_id=invite.team_id, user_id=user.id, role=invite.role))
    invite.accepted_at = utc_now()
    db.commit()
    return invite
