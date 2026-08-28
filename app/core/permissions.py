"""The single place that turns "what role is this person" into "what are
they allowed to do." Routes/controllers ask compute_permissions() rather
than hardcoding role checks — the point is that a route never says
`if role == "owner"`, it says `if not perms.can_x`. Today owner and editor
happen to share almost every capability; when that changes, this is the
only file that needs to.
"""

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.team import Team, TeamMembership, TeamRole


@dataclass(frozen=True)
class Permissions:
    can_upload_assets: bool
    can_generate: bool
    can_manage_team: bool  # invite/remove members, etc — stays owner-only


def compute_permissions(role: str) -> Permissions:
    is_owner = role == TeamRole.owner.value
    return Permissions(
        can_upload_assets=True,  # owner and editor both, for now
        can_generate=True,  # owner and editor both, for now
        can_manage_team=is_owner,  # team management is the one owner-only thing
    )


def get_membership(db: Session, team_id: str, user_id: str) -> TeamMembership:
    """A user only gets team-scoped access through a membership row — no
    membership, no access, regardless of who created the team or the
    resource underneath it (asset, job, ...). Also 404s for a
    SOFT-DELETED team (Team.is_active=False, see team_controller.
    delete_team) — this is the ONE choke point every team-scoped route
    goes through (billing, generation, assets, team management itself),
    so this single check is what makes a deleted team disappear
    everywhere at once, not just from list_my_teams."""
    membership = (
        db.query(TeamMembership)
        .join(Team, Team.id == TeamMembership.team_id)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id, Team.is_active == True)  # noqa: E712
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return membership
