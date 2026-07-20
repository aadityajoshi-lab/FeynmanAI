from types import SimpleNamespace

from teachback.providers import FireworksProvider, ProviderOutputError


def _provider_with_response(content: str):
    calls: list[dict] = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")]
        )

    provider = FireworksProvider.__new__(FireworksProvider)
    provider.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return provider, calls


def test_fireworks_uses_json_schema_and_accepts_a_complete_response() -> None:
    provider, calls = _provider_with_response(
        '{"answer":"Smaller quanta increase context switching.","groundedIn":"notebook","sourceAnchorIds":["source-1:p1"]}'
    )
    schema = {
        "type": "object",
        "required": ["answer", "groundedIn", "sourceAnchorIds"],
        "properties": {
            "answer": {"type": "string"},
            "groundedIn": {"type": "string"},
            "sourceAnchorIds": {"type": "array"},
        },
    }

    result = provider._chat_json("Use the source.", "notebook_copilot_v1", schema)

    assert result["answer"].startswith("Smaller")
    assert calls[0]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "notebook_copilot_v1", "schema": schema},
    }


def test_fireworks_rejects_an_empty_json_object_even_when_it_parses() -> None:
    provider, _ = _provider_with_response("{}")
    schema = {
        "type": "object",
        "required": ["answer", "groundedIn", "sourceAnchorIds"],
        "properties": {},
    }

    try:
        provider._chat_json("Use the source.", "notebook_copilot_v1", schema)
    except ProviderOutputError as exc:
        assert "required structured fields" in str(exc)
    else:  # pragma: no cover - documents the fail-closed contract
        raise AssertionError("Empty JSON must not be accepted as a provider response")
