import os
import pytest
from unittest.mock import MagicMock, patch

from sm_bench.model_clients.openrouter_client import OpenRouterClient
from scripts.sync_openrouter import (
    build_model_metadata,
    prune_openrouter_models,
    refresh_model_metadata,
)


def test_prune_openrouter_models():
    api_models = [
        {"id": "meta-llama/llama-3.3-70b-instruct"},
        {"id": "google/gemma-4-31b-it:free"},
        {"id": "openai/gpt-oss-20b"},
    ]

    existing = [
        # Dead free model whose base model exists in api_models
        {"name": "llama-3.3-70b-instruct", "model": "meta-llama/llama-3.3-70b-instruct:free"},
        # Live free model
        {"name": "gemma-4-31b-it", "model": "google/gemma-4-31b-it:free"},
        # Completely dead model
        {"name": "dead-model", "model": "some/dead-model:free"},
        # Duplicate of live model
        {"name": "gpt-oss-20b", "model": "openai/gpt-oss-20b"},
        {"name": "gpt-oss-20b-dup", "model": "openai/gpt-oss-20b"},
    ]

    kept, pruned, converted = prune_openrouter_models(existing, api_models)

    # 1. llama-3.3-70b-instruct:free should be converted to meta-llama/llama-3.3-70b-instruct
    assert ("meta-llama/llama-3.3-70b-instruct:free", "meta-llama/llama-3.3-70b-instruct") in converted
    # 2. dead-model should be pruned
    assert "some/dead-model:free" in pruned
    # 3. Duplicate should be pruned or skipped
    kept_ids = [m["model"] for m in kept]
    assert "meta-llama/llama-3.3-70b-instruct" in kept_ids
    assert "google/gemma-4-31b-it:free" in kept_ids
    assert "openai/gpt-oss-20b" in kept_ids
    assert kept_ids.count("openai/gpt-oss-20b") == 1
    assert "some/dead-model:free" not in kept_ids


def test_refresh_model_metadata_records_reasoning_capabilities():
    existing = [{"name": "kimi", "model": "moonshotai/kimi-k2.6", "params": {}}]
    api_models = [{
        "id": "moonshotai/kimi-k2.6",
        "context_length": 262144,
        "top_provider": {"max_completion_tokens": 65535},
        "supported_parameters": ["reasoning", "max_tokens", "response_format"],
        "architecture": {
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        "pricing": {"prompt": "0.1", "completion": "0.2"},
        "reasoning": {"mandatory": False, "default_enabled": True},
    }]

    assert refresh_model_metadata(existing, api_models) == 1
    metadata = existing[0]["metadata"]
    assert metadata == build_model_metadata(api_models[0])
    assert metadata["reasoning"]["default_enabled"] is True
    assert metadata["max_completion_tokens"] == 65535
    assert refresh_model_metadata(existing, api_models) == 0


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake_test_key"})
def test_openrouter_client_404_free_fallback():
    client = OpenRouterClient(model="meta-llama/llama-3.3-70b-instruct:free", max_retries=2)

    # Mock completion response
    mock_choice = MagicMock()
    mock_choice.message.content = '{"geometry_type": "concentric_tube"}'
    mock_success_resp = MagicMock()
    mock_success_resp.choices = [mock_choice]
    mock_success_resp.usage = None

    # 1st call raises 404 (unavailable for free), 2nd call succeeds
    error_msg = "NotFoundError: Error code: 404 - This model is unavailable for free. The paid version is available now - use this slug instead: meta-llama/llama-3.3-70b-instruct"
    client._client.chat.completions.create = MagicMock(
        side_effect=[Exception(error_msg), mock_success_resp]
    )

    result = client.generate_design("test prompt")

    assert result == '{"geometry_type": "concentric_tube"}'
    # Model should have fallen back to the non-free slug
    assert client.model == "meta-llama/llama-3.3-70b-instruct"
    assert client._client.chat.completions.create.call_count == 2


@patch.dict(os.environ, {"OPENROUTER_API_KEY": "fake_test_key"})
def test_openrouter_client_429_retry():
    client = OpenRouterClient(model="google/gemma-4-31b-it:free", max_retries=3, backoff_factor=0.01)

    mock_choice = MagicMock()
    mock_choice.message.content = '{"geometry_type": "shell_and_tube"}'
    mock_success_resp = MagicMock()
    mock_success_resp.choices = [mock_choice]
    mock_success_resp.usage = None

    # 1st call raises 429, 2nd call succeeds
    error_msg = "RateLimitError: Error code: 429 - provider returned error"
    client._client.chat.completions.create = MagicMock(
        side_effect=[Exception(error_msg), mock_success_resp]
    )

    result = client.generate_design("test prompt")

    assert result == '{"geometry_type": "shell_and_tube"}'
    assert client._client.chat.completions.create.call_count == 2


# ── extra_body must be merged, never passed twice ────────────────────
#
# The benchmark runner puts reasoning effort and provider routing into
# params["extra_body"], and the client adds usage accounting. Passing both to
# create() raised "got multiple values for keyword argument 'extra_body'" and
# failed every run of a reasoning model. The dummy-client tests could not see
# it, because the collision only happens at the real call signature.

class _RecordingCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        raise RuntimeError("stop before the network")


def _client_with_params(params):
    os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
    client = OpenRouterClient(model="test/model", params=params, max_retries=1)
    completions = _RecordingCompletions()
    fake = MagicMock()
    fake.chat.completions = completions
    client._client = fake
    try:
        client.generate_design("prompt")
    except Exception:
        pass
    return completions.kwargs


def test_caller_extra_body_and_usage_accounting_are_merged():
    kwargs = _client_with_params({
        "max_tokens": 8192,
        "temperature": 0.7,
        "extra_body": {
            "reasoning": {"effort": "low"},
            "provider": {"require_parameters": True},
        },
    })
    assert kwargs is not None, "create() was never reached"
    assert kwargs["extra_body"] == {
        "reasoning": {"effort": "low"},
        "provider": {"require_parameters": True},
        "usage": {"include": True},
    }
    assert kwargs["max_tokens"] == 8192
    assert kwargs["temperature"] == 0.7


def test_usage_accounting_alone_still_reaches_the_request():
    kwargs = _client_with_params({"max_tokens": 4096})
    assert kwargs["extra_body"] == {"usage": {"include": True}}


def test_caller_may_override_usage_accounting():
    kwargs = _client_with_params({"extra_body": {"usage": {"include": False}}})
    assert kwargs["extra_body"] == {"usage": {"include": False}}


def test_client_params_are_not_mutated_between_calls():
    """A popped extra_body must not disappear from the client's own params."""
    os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
    params = {"extra_body": {"reasoning": {"effort": "high"}}}
    client = OpenRouterClient(model="test/model", params=params, max_retries=1)
    completions = _RecordingCompletions()
    fake = MagicMock()
    fake.chat.completions = completions
    client._client = fake
    for _ in range(2):
        try:
            client.generate_design("prompt")
        except Exception:
            pass
    assert completions.kwargs["extra_body"]["reasoning"] == {"effort": "high"}
    assert client.params["extra_body"] == {"reasoning": {"effort": "high"}}
