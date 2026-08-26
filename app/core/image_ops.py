"""Resize + reformat an asset into a named marketplace preset. A genuinely
separate concern from the AI generation pipeline (core/ai_provider.py) —
this never touches AIProvider. Amazon's white-background requirement is a
plain letterbox/pad, not real background removal — that's background_swap
(a Category-A tool), not this module's job.
"""

from io import BytesIO

from PIL import Image, ImageOps

# (target_width, target_height, output_format, mode)
#   mode "fit"     — crop-to-fill: exact target dimensions, cropping any excess
#   mode "pad"     — contain within target, pad remaining space with white
#   mode "contain" — preserve aspect, cap the max dimension, never upscale
EXPORT_PRESETS = {
    "shopify_product": (2048, 2048, "JPEG", "fit"),
    "amazon_main": (3000, 3000, "JPEG", "pad"),
    "etsy_listing": (2700, 2025, "JPEG", "fit"),
    "instagram_post": (1080, 1350, "JPEG", "fit"),
    "master_png": (4096, 4096, "PNG", "contain"),
}

_EXTENSION_FOR_FORMAT = {"JPEG": "jpg", "PNG": "png"}


def export_variant(source_bytes: bytes, preset_key: str) -> tuple[bytes, str]:
    if preset_key not in EXPORT_PRESETS:
        raise ValueError(f"unknown export preset {preset_key!r} — known: {', '.join(EXPORT_PRESETS)}")

    target_w, target_h, output_format, mode = EXPORT_PRESETS[preset_key]
    image = ImageOps.exif_transpose(Image.open(BytesIO(source_bytes)))
    if output_format == "JPEG":
        image = image.convert("RGB")  # JPEG has no alpha channel

    if mode == "fit":
        result = ImageOps.fit(image, (target_w, target_h), Image.LANCZOS)
    elif mode == "pad":
        fitted = ImageOps.contain(image, (target_w, target_h), Image.LANCZOS)
        result = Image.new("RGB", (target_w, target_h), "white")
        offset = ((target_w - fitted.width) // 2, (target_h - fitted.height) // 2)
        result.paste(fitted, offset)
    else:  # "contain" — preserve aspect, no crop, no pad, never upscale
        result = image.copy()
        result.thumbnail((target_w, target_h), Image.LANCZOS)

    buffer = BytesIO()
    result.save(buffer, format=output_format)
    return buffer.getvalue(), _EXTENSION_FOR_FORMAT[output_format]
