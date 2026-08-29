"""catalog_photoshoot_controller — the one pre-step endpoint ahead of the
existing /generate pipeline: assembling product images, running the
safety check, and writing the N shot prompts. See
docs/superpowers/specs/2026-08-29-catalog-photoshoot-tool-design.md.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.models.asset import Asset
from app.models.user import User
from app.schemas.catalog_photoshoot import CatalogShotsRequest, CatalogShotsResponse
from app.tools import catalog_photoshoot as tool


def build_shots(
    db: Session, team_id: str, current_user: User, payload: CatalogShotsRequest,
) -> CatalogShotsResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    product_urls = []
    for asset_id in payload.product_asset_ids:
        asset = db.get(Asset, asset_id)
        if not asset or asset.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"asset_id {asset_id!r} does not belong to this team")
        product_urls.append(asset.url)

    try:
        image_urls, labels = tool.assemble_product_images(product_urls)
        passed, reason = tool.run_safety_check(config, image_urls, payload.user_prompt)
        if not passed:
            raise ValueError(f"Blocked at safety check: {reason}")
        prompts = tool.build_shot_prompts(config, image_urls, labels, payload.num_outputs, payload.user_prompt)
        image_size = tool.build_image_size(payload.resolution_mode, payload.aspect_ratio, payload.custom_width, payload.custom_height)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CatalogShotsResponse(prompts=prompts, image_urls=image_urls, labels=labels, image_size=image_size)
