"""creative_photoshoot_controller — the one pre-step endpoint ahead of the
existing /generate pipeline: assembling product images, running the
safety check, and building the single final creative prompt (case
branching + adult-floor guardrail). Always exactly one prompt/output — no
batch setting anywhere; a second variation means calling this (and then
/generate) again.

Reuses catalog_photoshoot's assemble_product_images/run_safety_check/
build_image_size directly (not copies) and its config for the generation
model + safety-check model/prompt — only the prompt_writer model and the
creative system prompt come from this tool's own config. See
app/tools/creative_photoshoot.py's docstring.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.models.asset import Asset
from app.models.user import User
from app.schemas.creative_photoshoot import CreativePromptRequest, CreativePromptResponse
from app.tools import catalog_photoshoot as catalog_tool
from app.tools import creative_photoshoot as tool


def build_prompt(
    db: Session, team_id: str, current_user: User, payload: CreativePromptRequest,
) -> CreativePromptResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    creative_config = tool.get_config(db)
    catalog_config = catalog_tool.get_config(db)  # generation + safety-check model/prompt
    # live off catalog_photoshoot's own config, never copied — see
    # app/tools/creative_photoshoot.py's docstring.

    product_urls = []
    for asset_id in payload.product_asset_ids:
        asset = db.get(Asset, asset_id)
        if not asset or asset.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"asset_id {asset_id!r} does not belong to this team")
        product_urls.append(asset.url)

    try:
        image_urls, labels = catalog_tool.assemble_product_images(product_urls)
        passed, reason = catalog_tool.run_safety_check(catalog_config, image_urls, payload.user_prompt)
        if not passed:
            raise ValueError(f"Blocked at safety check: {reason}")
        final_prompt = tool.build_creative_prompt(creative_config, image_urls, labels, payload.idea_tags, payload.user_prompt)
        final_prompt = tool.apply_adult_floor(final_prompt)
        image_size = catalog_tool.build_image_size(payload.resolution_mode, payload.aspect_ratio, payload.custom_width, payload.custom_height)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CreativePromptResponse(final_prompt=final_prompt, image_urls=image_urls, labels=labels, image_size=image_size)
