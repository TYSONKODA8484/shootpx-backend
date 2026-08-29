"""app/core/fal_provider.py's FalImageEditProvider — generic submit/poll
against fal's queue API. fal_client and httpx are monkeypatched throughout;
no real network call is made. SessionLocal/load_tool_config are also
monkeypatched so this doesn't need a real DB to resolve which model id to
call."""

import pytest

import app.core.fal_provider as fal_provider_module
from app.core.ai_provider import GenerationFailed, GenerationHandle, GenerationPending
from app.core.fal_provider import FalImageEditProvider


class _DummySession:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(fal_provider_module, "SessionLocal", lambda: _DummySession())
    monkeypatch.setattr(
        fal_provider_module, "load_tool_config",
        lambda db, feature_type, path: {"models": {"final_generation": "fal-ai/some/model"}},
    )


def test_submit_calls_fal_with_resolved_model_and_returns_handle(monkeypatch):
    captured = {}

    class _FakeHandle:
        request_id = "req-123"

    def fake_submit(model, arguments):
        captured["model"] = model
        captured["arguments"] = arguments
        return _FakeHandle()

    monkeypatch.setattr(fal_provider_module.fal_client, "submit", fake_submit)

    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = provider.submit(
        "on_model_shots", None,
        {"prompt": "a pose", "image_urls": ["http://x/1.jpg"], "image_size": "portrait_4_3"},
    )

    assert captured["model"] == "fal-ai/some/model"
    assert captured["arguments"]["prompt"] == "a pose"
    assert captured["arguments"]["enable_safety_checker"] is True
    assert handle == GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")


def test_poll_result_pending_when_in_progress(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.InProgress(logs=None),
    )
    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")

    with pytest.raises(GenerationPending):
        provider.poll_result(handle)


def test_poll_result_pending_when_queued(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.Queued(position=2),
    )
    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")

    with pytest.raises(GenerationPending):
        provider.poll_result(handle)


def test_poll_result_failed_when_fal_reports_error(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.Completed(
            logs=None, metrics={}, error="nsfw content detected", error_type="content_policy",
        ),
    )
    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")

    with pytest.raises(GenerationFailed, match="nsfw content detected"):
        provider.poll_result(handle)


def test_poll_result_downloads_bytes_when_completed(monkeypatch):
    monkeypatch.setattr(
        fal_provider_module.fal_client, "status",
        lambda model, request_id, with_logs=False: fal_provider_module.fal_client.Completed(
            logs=None, metrics={}, error=None,
        ),
    )
    monkeypatch.setattr(
        fal_provider_module.fal_client, "result",
        lambda model, request_id: {"images": [{"url": "https://fal.example/out.png"}]},
    )

    class _FakeResponse:
        content = b"fake-png-bytes"
        headers = {"content-type": "image/png"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(fal_provider_module.httpx, "get", lambda url, timeout=60.0: _FakeResponse())

    provider = FalImageEditProvider(feature_type="on_model_shots", model_config_key="final_generation")
    handle = GenerationHandle(external_job_id="fal-ai/some/model::req-123", provider="fal")
    result = provider.poll_result(handle)

    assert result.media_type == "image"
    assert result.content == b"fake-png-bytes"
    assert result.extension == "png"
