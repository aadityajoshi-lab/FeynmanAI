from unittest.mock import patch

from django.test import override_settings

from teachback.learning_os_views import _active_provider_metadata as activity_provider_metadata
from teachback.notebook_media import _active_provider_metadata as notebook_provider_metadata
from teachback.providers import OpenAIProvider, normalize_model_name, openai_generation_configured, provider_for


@override_settings(LLM_PROVIDER="openai", OPENAI_API_KEY="test-key", OPENAI_MODEL="gpt-5.6-terra-high")
def test_openai_is_the_active_provider() -> None:
    assert openai_generation_configured() is True
    assert activity_provider_metadata() == ("openai", "gpt-5.6-terra-high")
    assert notebook_provider_metadata() == ("openai", "gpt-5.6-terra-high")
    with patch("teachback.providers.OpenAIProvider", return_value=object()) as provider_class:
        provider_for()
    provider_class.assert_called_once_with()


@override_settings(OPENAI_API_KEY="test-key", OPENAI_MODEL="gpt-5.6-terra-high")
def test_openai_health_reports_safe_metadata() -> None:
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.model = "gpt-5.6-terra-high"
    provider.provider_id = "openai"
    health = provider.health()
    assert health["providerMode"] == "live_openai"
    assert health["model"] == "gpt-5.6-terra-high"


def test_model_namespace_is_normalized() -> None:
    assert normalize_model_name("cx/gpt-5.6-terra-high") == "gpt-5.6-terra-high"
