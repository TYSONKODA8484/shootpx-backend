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

from app.models.team import TeamMembership, TeamRole


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
    resource underneath it (asset, job, ...)."""
    membership = (
        db.query(TeamMembership)
        .filter(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return membership
