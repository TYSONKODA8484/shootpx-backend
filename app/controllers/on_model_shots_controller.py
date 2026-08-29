"""on_model_shots_controller — the two synchronous pre-steps ahead of the
existing /generate pipeline: resolving a model image (generate/upload/
default) and writing the N pose prompts. See
docs/superpowers/specs/2026-08-29-on-model-shots-real-provider-design.md.
"""

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import compute_permissions, get_membership
from app.core.storage import storage
from app.models.asset import Asset, AssetKind, MediaType
from app.models.team import new_id
from app.models.user import User
from app.schemas.on_model_shots import (
    ModelImageResolveRequest,
    ModelImageResolveResponse,
    PromptsRequest,
    PromptsResponse,
)
from app.tools import on_model_shots as tool

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _guess_extension(content_type: str) -> str:
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";")[0].strip().lower(), "jpg")


def _save_generated_image(team_id: str, user_id: str, url: str) -> Asset:
    """Downloads a fal-generated image's bytes and saves them through our
    own storage — fal's URL is never stored as the permanent Asset.url
    (see the spec's "only outputs stored" rule)."""
    resp = httpx.get(url, timeout=60.0)
    resp.raise_for_status()
    ext = _guess_extension(resp.headers.get("content-type", ""))
    key = f"{team_id}/generated/{new_id()}.{ext}"
    storage.save(key, resp.content)
    return Asset(
        team_id=team_id, created_by=user_id, kind=AssetKind.generated.value,
        media_type=MediaType.image.value, storage_key=key, url=storage.url_for(key),
    )


def resolve_model_image(
    db: Session, team_id: str, current_user: User, payload: ModelImageResolveRequest,
) -> ModelImageResolveResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    if payload.mode == "generate":
        candidate = tool.generate_model_candidate(
            config, payload.gender, payload.age_bracket, payload.skin_tone, payload.body_type, payload.additional_notes,
        )
        asset = _save_generated_image(team_id, current_user.id, candidate["url"])
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return ModelImageResolveResponse(
            asset_id=asset.id, url=asset.url, clean=candidate["clean"],
            reason=candidate["reason"], description=candidate["description"],
        )

    if payload.mode == "upload":
        if not payload.asset_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_id is required for mode='upload'")
        asset = db.get(Asset, payload.asset_id)
        if not asset or asset.team_id != team_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="asset_id does not belong to this team")
        try:
            url = tool.resolve_model_via_upload(config, asset.url)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        return ModelImageResolveResponse(asset_id=asset.id, url=url, clean=True, reason=None, description=None)

    if payload.mode == "default":
        if not payload.preset_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="preset_id is required for mode='default'")
        if payload.preset_id not in config.get("presets", {}):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown preset_id {payload.preset_id!r}")
        url = tool.resolve_model_via_default(config, payload.preset_id)
        return ModelImageResolveResponse(asset_id=None, url=url, clean=True, reason=None, description=None)

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown mode {payload.mode!r}")


def build_prompts(
    db: Session, team_id: str, current_user: User, payload: PromptsRequest,
) -> PromptsResponse:
    membership = get_membership(db, team_id, current_user.id)
    if not compute_permissions(membership.role).can_generate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to generate on this team")

    config = tool.get_config(db)

    def _resolve_asset_urls(asset_ids: list[str]) -> list[str]:
        urls = []
        for asset_id in asset_ids:
            asset = db.get(Asset, asset_id)
            if not asset or asset.team_id != team_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"asset_id {asset_id!r} does not belong to this team")
            urls.append(asset.url)
        return urls

    garment_urls = _resolve_asset_urls(payload.garment_asset_ids)
    reference_urls = _resolve_asset_urls(payload.reference_asset_ids)

    try:
        image_urls, labels = tool.assemble_inputs(payload.model_image_url, garment_urls, reference_urls)
        prompts = tool.generate_pose_prompts_via_vlm(
            config, image_urls, labels, payload.garment_type, payload.num_poses, payload.user_prompt,
        )
        passed, reason = tool.run_local_safety_check(config, " ".join(prompts), image_urls)
        if not passed:
            raise ValueError(f"Blocked at local safety pre-check: {reason}")
        image_size = tool.build_image_size(payload.resolution_mode, payload.aspect_ratio, payload.custom_width, payload.custom_height)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return PromptsResponse(prompts=prompts, image_urls=image_urls, labels=labels, image_size=image_size)
