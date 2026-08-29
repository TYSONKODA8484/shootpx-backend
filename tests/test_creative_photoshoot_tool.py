"""app/tools/creative_photoshoot.py — pure logic + config-driven VLM
calls. catalog_photoshoot's _vlm_json_call is monkeypatched at ITS module
boundary (creative_photoshoot.py calls it via catalog_tool, not its own
copy) — no real fal.ai call is made in this test file."""

import pytest

from app.tools import catalog_photoshoot as catalog_tool
from app.tools import creative_photoshoot as tool

_FAKE_CONFIG = {
    "models": {"catalog_generation": "m-catalog", "prompt_writer": "m-writer", "safety_check": "m-safety"},
    "prompts": {"creative_prompt_writer": "sys-creative", "safety_check": "sys-safety"},
}


def test_apply_adult_floor_prepends_the_guardrail():
    result = tool.apply_adult_floor("a scene on a beach")
    assert result.startswith("If this scene includes any person")
    assert result.endswith("a scene on a beach")


def test_build_creative_prompt_raises_when_neither_idea_nor_prompt():
    with pytest.raises(ValueError, match="Provide an idea, a prompt, or both"):
        tool.build_creative_prompt(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"])


def test_build_creative_prompt_case1_prompt_only_is_verbatim_no_llm_call(monkeypatch):
    def _should_not_be_called(*a, **k):
        raise AssertionError("_vlm_json_call must not run for prompt-only (Case 1)")

    monkeypatch.setattr(catalog_tool, "_vlm_json_call", _should_not_be_called)
    result = tool.build_creative_prompt(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], user_prompt="on a beach at sunset")
    assert result == "on a beach at sunset"


def test_build_creative_prompt_case2_idea_only_calls_vlm(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system, prompt=prompt)
        return {"prompt": "a studio hero shot"}

    monkeypatch.setattr(catalog_tool, "_vlm_json_call", fake_call)
    result = tool.build_creative_prompt(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"], idea_tags=["Studio hero shot"])

    assert result == "a studio hero shot"
    assert captured["model"] == "m-writer"
    assert captured["system"] == "sys-creative"
    assert "Studio hero shot" in captured["prompt"]


def test_build_creative_prompt_case3_idea_and_prompt_merges_via_vlm(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured["prompt"] = prompt
        return {"prompt": "merged prompt"}

    monkeypatch.setattr(catalog_tool, "_vlm_json_call", fake_call)
    result = tool.build_creative_prompt(
        _FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = product"],
        idea_tags=["Studio hero shot"], user_prompt="on a marble counter",
    )

    assert result == "merged prompt"
    assert "Studio hero shot" in captured["prompt"]
    assert "on a marble counter" in captured["prompt"]


def test_creative_photoshoot_is_registered_with_its_own_fal_image_edit_provider():
    from app.core.fal_provider import FalImageEditProvider
    from app.tools import get_tool

    spec = get_tool("creative_photoshoot")
    assert spec is not None
    assert isinstance(spec.provider, FalImageEditProvider)
    assert spec.provider is not catalog_tool.provider  # its own instance, own config row
    assert spec.provider.feature_type == "creative_photoshoot"
    assert spec.provider.model_config_key == "catalog_generation"
