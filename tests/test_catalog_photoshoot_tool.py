"""app/tools/catalog_photoshoot.py — pure logic + config-driven VLM calls.
Same monkeypatch-at-the-module-boundary approach as
tests/test_on_model_shots_tool.py — no real fal.ai call is made here."""

import pytest

from app.tools import catalog_photoshoot as tool

_FAKE_CONFIG = {
    "models": {"catalog_generation": "m-catalog", "prompt_writer": "m-writer", "safety_check": "m-safety"},
    "prompts": {"shot_prompt_writer": "sys-shot-writer", "safety_check": "sys-safety"},
}


def test_assemble_product_images_labels_every_image_as_a_product_reference():
    image_urls, labels = tool.assemble_product_images(["https://x/1.jpg", "https://x/2.jpg"])
    assert image_urls == ["https://x/1.jpg", "https://x/2.jpg"]
    assert all("exact product, preserve fidelity" in label for label in labels)


def test_assemble_product_images_rejects_over_ten_images():
    with pytest.raises(ValueError, match="exceeds the 10-image input limit"):
        tool.assemble_product_images([f"https://x/{i}.jpg" for i in range(11)])


def test_build_image_size_standard_uses_aspect_ratio_map():
    assert tool.build_image_size("standard", "1:1") == "square_hd"


def test_build_image_size_auto_3k_is_supported_unlike_on_model_shots():
    assert tool.build_image_size("auto_3K") == "auto_3K"


def test_build_image_size_custom_does_not_validate_range():
    """Different from on_model_shots' build_image_size — fal auto-scales an
    out-of-range custom size for this endpoint rather than rejecting it."""
    assert tool.build_image_size("custom", custom_width=100, custom_height=100) == {"width": 100, "height": 100}


def test_run_safety_check_blocks_on_prompt_keyword_before_calling_vlm(monkeypatch):
    def _should_not_be_called(*a, **k):
        raise AssertionError("_vlm_json_call must not run when the prompt keyword check already failed")

    monkeypatch.setattr(tool, "_vlm_json_call", _should_not_be_called)
    passed, reason = tool.run_safety_check(_FAKE_CONFIG, ["https://x/1.jpg"], user_prompt="a photo of a minor")
    assert passed is False
    assert "blocked term 'minor'" in reason


def test_run_safety_check_calls_vlm_when_prompt_is_clean(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system)
        return {"pass": True, "reason": ""}

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    passed, _ = tool.run_safety_check(_FAKE_CONFIG, ["https://x/1.jpg"], user_prompt="a nice shot")
    assert passed is True
    assert captured["model"] == "m-safety"
    assert captured["system"] == "sys-safety"


def test_build_shot_prompts_returns_prompts_when_valid(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: ["shot1", "shot2"])
    prompts = tool.build_shot_prompts(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], 2)
    assert prompts == ["shot1", "shot2"]


def test_build_shot_prompts_retries_once_on_wrong_count_then_succeeds(monkeypatch):
    responses = iter([["only-one"], ["shot1", "shot2"]])
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: next(responses))
    prompts = tool.build_shot_prompts(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], 2)
    assert prompts == ["shot1", "shot2"]


def test_build_shot_prompts_raises_after_two_failures(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: ["shot1", "shot1"])  # duplicate, both attempts
    with pytest.raises(ValueError, match="Shot-list planning failed twice"):
        tool.build_shot_prompts(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], 2)


def test_catalog_photoshoot_is_registered_with_a_fal_image_edit_provider():
    from app.core.fal_provider import FalImageEditProvider
    from app.tools import get_tool

    spec = get_tool("catalog_photoshoot")
    assert spec is not None
    assert isinstance(spec.provider, FalImageEditProvider)
    assert spec.provider.feature_type == "catalog_photoshoot"
    assert spec.provider.model_config_key == "catalog_generation"
