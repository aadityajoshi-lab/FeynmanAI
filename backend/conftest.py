"""Keep the test suite offline and deterministic even when local runtime envs use OpenAI."""

import pytest


@pytest.fixture(autouse=True)
def force_fixture_provider(settings):
    settings.LLM_PROVIDER = "fixture"
