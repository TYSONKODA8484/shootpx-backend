"""app/tools/on_model_shots.py — pure logic + config-driven VLM calls.
_vlm_json_call itself is monkeypatched at the module boundary for every
test that exercises a function built on top of it — no real fal.ai call
is made in this test file."""

import pytest

from app.tools import on_model_shots as tool

_FAKE_CONFIG = {
    "models": {"final_generation": "m-final", "text_to_image": "m-t2i", "prompt_writer": "m-writer", "safety_check": "m-safety"},
    "prompts": {
        "model_prompt_writer": "sys-model-prompt", "description_safety": "sys-desc-safety",
        "image_nsfw": "sys-image-nsfw", "general": "sys-general", "intimate": "sys-intimate",
        "local_safety_check": "sys-local-safety",
    },
    "presets": {"preset_1": "https://cdn.example.com/preset_1.jpg"},
}


# --- description safety (keyword, no VLM) -------------------------------

def test_check_description_safety_raises_on_blocked_term():
    with pytest.raises(ValueError, match="Blocked term 'teen'"):
        tool.check_description_safety("a teen model in a studio")


def test_check_description_safety_passes_clean_text():
    assert tool.check_description_safety("a confident adult model in a studio") is True


# --- VLM-backed functions (mocked _vlm_json_call) ------------------------

def test_generate_model_prompt_via_llm_uses_configured_model_and_prompt(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system, prompt=prompt)
        return {"prompt": "a confident adult model"}

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    result = tool.generate_model_prompt_via_llm(_FAKE_CONFIG, "Female", "Young adult (25-30)", "Fair", "Slim")

    assert result == "a confident adult model"
    assert captured["model"] == "m-writer"
    assert captured["system"] == "sys-model-prompt"


def test_check_description_safety_llm_returns_pass_and_reason(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: {"pass": False, "reason": "age-ambiguous"})
    passed, reason = tool.check_description_safety_llm(_FAKE_CONFIG, "a description")
    assert passed is False
    assert reason == "age-ambiguous"


def test_check_image_nsfw_returns_clean_and_reason(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: {"clean": True, "reason": ""})
    clean, reason = tool.check_image_nsfw(_FAKE_CONFIG, "https://x/candidate.png")
    assert clean is True


def test_generate_model_candidate_stops_before_generation_on_description_safety_fail(monkeypatch):
    """The whole point of the two-layer description check running before
    text-to-image: a blocked description must never reach the paid
    generation call."""
    monkeypatch.setattr(tool, "generate_model_prompt_via_llm", lambda *a, **k: "a description")
    monkeypatch.setattr(tool, "check_description_safety_llm", lambda *a, **k: (False, "looked underage"))

    def _should_not_be_called(*a, **k):
        raise AssertionError("generate_model_via_text2image must not be called after a failed safety check")

    monkeypatch.setattr(tool, "generate_model_via_text2image", _should_not_be_called)

    with pytest.raises(ValueError, match="Blocked at prompt-level safety check"):
        tool.generate_model_candidate(_FAKE_CONFIG, "Female", "Young adult (25-30)", "Fair", "Slim")


def test_generate_model_candidate_returns_full_result_when_clean(monkeypatch):
    monkeypatch.setattr(tool, "generate_model_prompt_via_llm", lambda *a, **k: "a description")
    monkeypatch.setattr(tool, "check_description_safety_llm", lambda *a, **k: (True, ""))
    monkeypatch.setattr(tool, "generate_model_via_text2image", lambda *a, **k: "https://fal.example/candidate.png")
    monkeypatch.setattr(tool, "check_image_nsfw", lambda *a, **k: (True, ""))

    result = tool.generate_model_candidate(_FAKE_CONFIG, "Female", "Young adult (25-30)", "Fair", "Slim")

    assert result == {"url": "https://fal.example/candidate.png", "clean": True, "reason": "", "description": "a description"}


def test_resolve_model_via_upload_raises_on_nsfw(monkeypatch):
    monkeypatch.setattr(tool, "check_image_nsfw", lambda *a, **k: (False, "looked underage"))
    with pytest.raises(ValueError, match="looked underage"):
        tool.resolve_model_via_upload(_FAKE_CONFIG, "https://x/uploaded.jpg")


def test_resolve_model_via_upload_returns_url_when_clean(monkeypatch):
    monkeypatch.setattr(tool, "check_image_nsfw", lambda *a, **k: (True, ""))
    assert tool.resolve_model_via_upload(_FAKE_CONFIG, "https://x/uploaded.jpg") == "https://x/uploaded.jpg"


def test_resolve_model_via_default_looks_up_preset_from_config():
    assert tool.resolve_model_via_default(_FAKE_CONFIG, "preset_1") == "https://cdn.example.com/preset_1.jpg"


# --- assemble_inputs -----------------------------------------------------

def test_assemble_inputs_orders_and_labels_model_garment_reference():
    image_urls, labels = tool.assemble_inputs(
        "https://x/model.jpg", ["https://x/garment1.jpg", "https://x/garment2.jpg"], ["https://x/ref.jpg"],
    )
    assert image_urls == ["https://x/model.jpg", "https://x/garment1.jpg", "https://x/garment2.jpg", "https://x/ref.jpg"]
    assert "model reference" in labels[0]
    assert "exact product, preserve fidelity" in labels[1]
    assert "style/pose reference only" in labels[3]


def test_assemble_inputs_rejects_over_ten_images():
    garments = [f"https://x/g{i}.jpg" for i in range(10)]
    with pytest.raises(ValueError, match="exceeds the 10-image limit"):
        tool.assemble_inputs("https://x/model.jpg", garments)


# --- output settings -------------------------------------------------------

def test_build_image_size_standard_uses_aspect_ratio_map():
    assert tool.build_image_size("standard", "3:4") == "portrait_4_3"


def test_build_image_size_rejects_unknown_aspect_ratio():
    with pytest.raises(ValueError, match="Unknown aspect_ratio"):
        tool.build_image_size("standard", "21:9")


def test_build_image_size_auto_modes_pass_through():
    assert tool.build_image_size("auto_2K") == "auto_2K"
    assert tool.build_image_size("auto_4K") == "auto_4K"


def test_build_image_size_custom_requires_both_dimensions():
    with pytest.raises(ValueError, match="requires custom_width and custom_height"):
        tool.build_image_size("custom", custom_width=2048)


def test_validate_custom_size_accepts_in_range_per_axis():
    tool.validate_custom_size(2048, 2048)  # does not raise


def test_validate_custom_size_rejects_out_of_range():
    with pytest.raises(ValueError, match="isn't a valid size"):
        tool.validate_custom_size(100, 100)


# --- router ------------------------------------------------------------

def test_classify_garment_category_intimate_terms():
    assert tool.classify_garment_category("push-up bra") == "intimate"
    assert tool.classify_garment_category("cotton underwear") == "intimate"


def test_classify_garment_category_general_for_everything_else():
    assert tool.classify_garment_category("t-shirt") == "general"


# --- pose prompts + local safety check -----------------------------------

def test_generate_pose_prompts_via_vlm_picks_intimate_system_for_a_bra(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured.update(model=model, system=system)
        return ["p1", "p2"]

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    tool.generate_pose_prompts_via_vlm(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = model"], "bra", num_poses=2)

    assert captured["system"] == "sys-intimate"
    assert captured["model"] == "m-writer"


def test_generate_pose_prompts_via_vlm_picks_general_system_for_a_tshirt(monkeypatch):
    captured = {}

    def fake_call(model, system, prompt, image_urls=None, max_tokens=1000):
        captured["system"] = system
        return ["p1"]

    monkeypatch.setattr(tool, "_vlm_json_call", fake_call)
    tool.generate_pose_prompts_via_vlm(_FAKE_CONFIG, ["https://x/1.jpg"], ["Image 1 = model"], "t-shirt", num_poses=1)
    assert captured["system"] == "sys-general"


def test_run_local_safety_check_short_circuits_on_blocked_keyword(monkeypatch):
    def _should_not_be_called(*a, **k):
        raise AssertionError("_vlm_json_call must not run when a keyword already failed the check")

    monkeypatch.setattr(tool, "_vlm_json_call", _should_not_be_called)
    passed, reason = tool.run_local_safety_check(_FAKE_CONFIG, "a prompt mentioning a minor", ["https://x/1.jpg"])
    assert passed is False
    assert "blocked term 'minor'" in reason


def test_run_local_safety_check_calls_vlm_when_no_blocked_keyword(monkeypatch):
    monkeypatch.setattr(tool, "_vlm_json_call", lambda *a, **k: {"pass": True, "reason": ""})
    passed, reason = tool.run_local_safety_check(_FAKE_CONFIG, "a clean prompt", ["https://x/1.jpg"])
    assert passed is True


# --- tool registration ---------------------------------------------------

def test_on_model_shots_is_registered_with_a_fal_image_edit_provider():
    from app.core.fal_provider import FalImageEditProvider
    from app.tools import get_tool

    spec = get_tool("on_model_shots")
    assert spec is not None
    assert isinstance(spec.provider, FalImageEditProvider)
    assert spec.provider.feature_type == "on_model_shots"
    assert spec.provider.model_config_key == "final_generation"
