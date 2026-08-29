"""recolor_controller — the one pre-step endpoint ahead of the existing
/generate pipeline: assembling images, running the safety check, filling
in a blank "which part" via one conditional LLM call, composing the
templated prompt, and resolving image_size (including the match_input
default, which needs the photo's real pixel dimensions). Always exactly
one prompt/output — no batch setting anywhere.
"""

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.models.asset import Asset
from app.models.user import User
from app.schemas.recolor import RecolorPromptRequest, RecolorPromptResponse
from app.tools import catalog_photoshoot as catalog_tool
from app.tools import recolor as tool


def build_prompt(
    db: Session, team_id: str, current_user: User, payload: RecolorPromptRequest,
) -> RecolorPromptResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    urls = []
    for asset_id in payload.image_asset_ids:
        asset = db.get(Asset, asset_id)
        if not asset or asset.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"asset_id {asset_id!r} does not belong to this team")
        urls.append(asset.url)

    try:
        image_urls, labels = tool.assemble_recolor_images(urls)
        passed, reason = catalog_tool.run_safety_check(config, image_urls, payload.description or None)
        if not passed:
            raise ValueError(f"Blocked at safety check: {reason}")

        description = payload.description or tool.suggest_recolor_target(config, image_urls)
        prompt = tool.build_recolor_prompt(config, description, payload.color)

        if payload.resolution_mode == "match_input":
            resp = httpx.get(image_urls[0], timeout=30.0)
            resp.raise_for_status()
            image_size = tool.compute_matching_size(resp.content)
        else:
            image_size = tool.build_image_size(payload.resolution_mode, payload.aspect_ratio, payload.custom_width, payload.custom_height)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return RecolorPromptResponse(prompt=prompt, description=description, image_urls=image_urls, labels=labels, image_size=image_size)
