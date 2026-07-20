"""Hermetic defaults for the backend test suite.

Developers may keep real provider credentials in a local ``.env`` for manual
browser/API validation.  Unit and API tests must never inherit those settings
and accidentally make billable network calls; focused provider tests can still
opt in with ``override_settings`` plus a mocked transport.
"""

import pytest


@pytest.fixture(autouse=True)
def disable_live_provider_credentials(settings):
    settings.LLM_PROVIDER = "fixture"
    settings.FIREWORKS_API_KEY = ""
    settings.OPENAI_API_KEY = ""
    settings.MISTRAL_API_KEY = ""

