import pytest

from teachback.providers import ProviderOutputError, _require_top_level_fields


def test_openai_structured_output_requires_declared_fields() -> None:
    schema = {"required": ["answer", "sourceAnchorIds"]}
    assert _require_top_level_fields({"answer": "ok", "sourceAnchorIds": []}, schema)["answer"] == "ok"
    with pytest.raises(ProviderOutputError, match="required structured fields"):
        _require_top_level_fields({"answer": "ok"}, schema)
