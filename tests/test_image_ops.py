"""tests/test_image_ops.py — export_variant()'s resize/reformat/pad logic."""

import io

import pytest
from PIL import Image

from app.core.image_ops import EXPORT_PRESETS, export_variant


def _png_bytes(width, height, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def test_shopify_product_produces_exact_square_jpeg():
    result_bytes, ext = export_variant(_png_bytes(800, 400), "shopify_product")

    assert ext == "jpg"
    image = Image.open(io.BytesIO(result_bytes))
    assert image.size == (2048, 2048)
    assert image.format == "JPEG"


def test_amazon_main_pads_a_non_square_source_with_white():
    result_bytes, _ext = export_variant(_png_bytes(1000, 400), "amazon_main")

    image = Image.open(io.BytesIO(result_bytes)).convert("RGB")
    assert image.size == (3000, 3000)
    # A wide source contained within a 3000x3000 square leaves the top
    # strip as padding — must be white, not the source's red fill.
    assert image.getpixel((0, 0)) == (255, 255, 255)


def test_master_png_caps_max_dimension_without_upscaling_a_smaller_source():
    result_bytes, ext = export_variant(_png_bytes(500, 300), "master_png")

    assert ext == "png"
    image = Image.open(io.BytesIO(result_bytes))
    assert image.size == (500, 300)  # untouched — already smaller than the cap


def test_master_png_downscales_a_larger_source_to_the_cap():
    result_bytes, _ext = export_variant(_png_bytes(5000, 2500), "master_png")

    image = Image.open(io.BytesIO(result_bytes))
    assert image.size == (4096, 2048)  # aspect preserved, capped at 4096


def test_export_variant_rejects_an_unknown_preset():
    with pytest.raises(ValueError):
        export_variant(_png_bytes(100, 100), "not_a_real_preset")


def test_all_five_presets_are_defined():
    assert set(EXPORT_PRESETS.keys()) == {
        "shopify_product", "amazon_main", "etsy_listing", "instagram_post", "master_png",
    }
