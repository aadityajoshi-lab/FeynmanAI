from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import override_settings

from teachback.learning_os_views import _active_provider_metadata as activity_provider_metadata
from teachback.notebook_media import _active_provider_metadata as notebook_provider_metadata
import pytest

from teachback.providers import OpenAIProvider, ProviderUnavailable, QwenProvider, normalize_model_name, provider_for, qwen_generation_configured


@override_settings(LLM_PROVIDER="qwen", FIREWORKS_API_KEY="test-transport-key", FIREWORKS_MODEL="qwen-test-model")
def test_qwen_is_the_explicit_active_provider_and_keeps_transport_provenance() -> None:
    assert qwen_generation_configured() is True
    assert activity_provider_metadata() == ("qwen", "qwen-test-model")
    assert notebook_provider_metadata() == ("qwen", "qwen-test-model")

    with patch("teachback.providers.QwenProvider", return_value=object()) as provider_class:
        provider_for()
    provider_class.assert_called_once_with()


@override_settings(FIREWORKS_API_KEY="test-transport-key", FIREWORKS_MODEL="qwen-test-model")
def test_qwen_health_identifies_the_model_and_its_non_openai_transport() -> None:
    provider = QwenProvider.__new__(QwenProvider)
    provider.model = "qwen-test-model"
    provider.provider_id = "qwen"

    health = provider.health()

    assert health["provider"] == "qwen"
    assert health["transport"] == "fireworks"
    assert health["providerMode"] == "live_qwen"
    assert health["model"] == "qwen-test-model"


@override_settings(OPENAI_API_KEY="test-omniroute-key", FIREWORKS_API_KEY="test-fireworks-key", FIREWORKS_MODEL="fireworks-fallback-model")
def test_openai_request_fails_over_to_fireworks_and_marks_provenance() -> None:
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Mock()
    provider.client.responses.create.side_effect = RuntimeError("OmniRoute unavailable")
    provider.model = "gpt-5.6-terra-high"
    provider.provider_id = "openai"
    provider.mode = "live_openai"

    fallback_result = {"intendedCapability": "Understand transformers"}
    with patch("teachback.providers.FireworksProvider") as fallback_class:
        fallback = fallback_class.return_value
        fallback.model = "fireworks-fallback-model"
        fallback._chat_json.return_value = fallback_result

        result = provider._chat_json("draft", "learning_contract_v1", {"type": "object"})

    assert result is fallback_result
    assert provider.mode == "live_fireworks_fallback"
    assert provider.fallback_model == "fireworks-fallback-model"
    fallback_class.assert_called_once_with()
    fallback._chat_json.assert_called_once_with("draft", "learning_contract_v1", {"type": "object"}, attachment=None)


@override_settings(OPENAI_API_KEY="", FIREWORKS_API_KEY="test-fireworks-key")
def test_openai_provider_selection_uses_fireworks_when_openai_is_unavailable() -> None:
    fallback = object()
    with patch("teachback.providers.OpenAIProvider", side_effect=ProviderUnavailable("OmniRoute is unavailable")), patch(
        "teachback.providers.FireworksProvider", return_value=fallback
    ) as fireworks_class:
        assert provider_for("openai") is fallback

    fireworks_class.assert_called_once_with()


@override_settings(OPENAI_API_KEY="test-omniroute-key", FIREWORKS_API_KEY="")
def test_openai_provider_error_is_preserved_without_fireworks_credentials() -> None:
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = Mock()
    provider.client.responses.create.side_effect = RuntimeError("OmniRoute unavailable")
    provider.model = "gpt-5.6-terra-high"
    provider.provider_id = "openai"
    provider.mode = "live_openai"

    with pytest.raises(ProviderUnavailable, match="OpenAI request failed: OmniRoute unavailable"):
        provider._chat_json("draft", "learning_contract_v1", {"type": "object"})


def test_omniroute_namespace_is_removed_from_model_ids() -> None:
    assert normalize_model_name("cx/gpt-5.6-terra-high") == "gpt-5.6-terra-high"
    assert normalize_model_name("gpt-5.6-terra-high") == "gpt-5.6-terra-high"
