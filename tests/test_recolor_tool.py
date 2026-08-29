"""app/tools/recolor.py — pure logic + config-driven VLM calls.
catalog_photoshoot's _vlm_json_call is monkeypatched at ITS module
boundary (recolor.py calls it via catalog_tool, not its own copy) — no
real fal.ai call is made in this test file."""

import io

import pytest
from PIL import Image

from app.tools import catalog_photoshoot as catalog_tool
from app.tools import recolor as tool

_FAKE_CONFIG = {
    "models": {"recolor_generation": "m-recolor", "prompt_writer": "m-writer", "safety_check": "m-safety"},
    "prompts": {"preservation_instructions": "PRESERVE.", "recolor_target_writer": "sys-target", "safety_check": "sys-safety"},
}


def _make_image_bytes(width, height):
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- assemble_recolor_images ----------------------------------------------

def test_assemble_recolor_images_labels_first_as_the_edited_photo():
    image_urls, labels = tool.assemble_recolor_images(["https://x/photo.jpg", "https://x/swatch.jpg"])
    assert image_urls == ["https://x/photo.jpg", "https://x/swatch.jpg"]
    assert "the photo being edited" in labels[0]
    assert "additional reference" in labels[1]


def test_assemble_recolor_images_rejects_over_four_images():
    urls = [f"https://x/{i}.jpg" for i in range(5)]
    with pytest.raises(ValueError, match="exceeds flux-2/edit's 4-image limit"):
        tool.assemble_recolor_images(urls)


# --- build_image_size -------------------------------------------------------

def test_build_image_size_standard_uses_aspect_ratio_map():
    assert tool.build_image_size("standard", "1:1") == "square_hd"


def test_build_image_size_custom_accepts_in_range():
    assert tool.build_image_size("custom", custom_width=1024, custom_height=1024) == {"width": 1024, "height": 1024}


def test_build_image_size_custom_rejects_out_of_range():
    """Different from catalog's build_image_size — flux-2/edit REJECTS an
    out-of-range custom size, it does not auto-scale."""
    with pytest.raises(ValueError, match="invalid"):
        tool.build_image_size("custom", custom_width=100, custom_height=100)


def test_build_image_size_rejects_unknown_mode():
    with pytest.raises(ValueError, match="Unknown resolution_mode"):
        tool.build_image_size("match_input")  # not handled here — caller resolves it first


# --- compute_matching_size ---------------------------------------------------

def test_compute_matching_size_scales_down_an_oversized_image():
    data = _make_image_bytes(4000, 2000)
    size = tool.compute_matching_size(data)
    assert max(size["width"], size["height"]) == tool.RECOLOR_MAX_DIM
    assert size["width"] > size["height"]


def test_compute_matching_size_scales_up_an_undersized_image():
    data = _make_image_bytes(300, 200)
    size = tool.compute_matching_size(data)
    assert min(size["width"], size["height"]) == tool.RECOLOR_MIN_DIM


def test_compute_matching_size_leaves_an_in_range_image_unchanged():
    data = _make_image_bytes(1024, 768)
    size = tool.compute_matching_size(data)
    assert size == {"width": 1024, "height": 768}


# --- prompt composition ------------------------------------------------------

def test_suggest_recolor_target_uses_configured_model_and_only_the_first_image(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system, image_urls=image_urls)
        return {"target": "the jacket"}

    monkeypatch.setattr(catalog_tool, "_vlm_json_call", fake_call)
    result = tool.suggest_recolor_target(_FAKE_CONFIG, ["https://x/photo.jpg", "https://x/swatch.jpg"])

    assert result == "the jacket"
    assert captured["model"] == "m-writer"
    assert captured["system"] == "sys-target"
    assert captured["image_urls"] == ["https://x/photo.jpg"]  # only Image 1, never the references


def test_build_recolor_prompt_composes_the_template():
    prompt = tool.build_recolor_prompt(_FAKE_CONFIG, "the jacket", "#FF0000")
    assert prompt.startswith("PRESERVE.")
    assert "Change the jacket in #Image_1 to #FF0000" in prompt


# --- tool registration ---------------------------------------------------

def test_recolor_is_registered_with_its_own_provider_and_no_max_images():
    from app.core.fal_provider import FalImageEditProvider
    from app.tools import get_tool

    spec = get_tool("recolor")
    assert spec is not None
    assert isinstance(spec.provider, FalImageEditProvider)
    assert spec.provider.feature_type == "recolor"
    assert spec.provider.model_config_key == "recolor_generation"
    assert spec.provider.include_max_images is False
