from pathlib import Path

import pytest

from .ingestion import IngestionError, extract_pdf_candidates, inspect_asset, media_pipeline_states


def test_inspect_asset_rejects_unknown_extension(tmp_path: Path):
    asset = tmp_path / "notes.exe"
    asset.write_bytes(b"not a source")
    with pytest.raises(IngestionError, match="unsupported media type"):
        inspect_asset(asset)


def test_inspect_asset_returns_checksum_for_supported_asset(tmp_path: Path):
    asset = tmp_path / "lesson.pdf"
    asset.write_bytes(b"%PDF-1.4 fixture")
    metadata = inspect_asset(asset)
    assert metadata.mime_type == "application/pdf"
    assert len(metadata.sha256) == 64


def test_pipeline_states_include_review_gate():
    assert "awaiting_approval" in media_pipeline_states()
    assert "published" in media_pipeline_states()


def test_extract_pdf_candidates_reports_parse_failure(tmp_path: Path):
    asset = tmp_path / "broken.pdf"
    asset.write_bytes(b"%PDF-1.4 fixture")
    with pytest.raises(IngestionError, match="unable to extract PDF text"):
        extract_pdf_candidates(asset)


def test_normalize_extracted_text_removes_duplicate_pdf_glyphs():
    from teachback.ingestion import normalize_extracted_text

    text = "AAnnaalloogg vvss.. DDiiggiittaall IInnssttrruummeennttss"

    assert normalize_extracted_text(text) == "Analog vs. Digital Instruments"


def test_normalize_extracted_text_preserves_normal_double_letters():
    from teachback.ingestion import normalize_extracted_text

    assert normalize_extracted_text("A book about analog signals") == "A book about analog signals"
