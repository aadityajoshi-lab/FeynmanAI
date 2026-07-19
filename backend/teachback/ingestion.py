"""Safe authoring-time source ingestion helpers.

This module deliberately produces *candidate* spans. Nothing returned here is
published evidence until an instructor approves it and assigns a stable
sourceSpanId in a versioned SourcePack.
"""
from __future__ import annotations

import hashlib
import mimetypes
import re
import unicodedata
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path


MAX_SOURCE_BYTES = 50 * 1024 * 1024
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/webm",
}

_MIME_SIGNATURES = {
    "application/pdf": lambda payload: payload.startswith(b"%PDF-"),
    "text/plain": lambda payload: True,
    "text/markdown": lambda payload: True,
    "text/csv": lambda payload: True,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": lambda payload: payload.startswith(b"PK"),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": lambda payload: payload.startswith(b"PK"),
    "image/png": lambda payload: payload.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda payload: payload.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda payload: len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP",
    "video/mp4": lambda payload: len(payload) >= 12 and payload[4:8] == b"ftyp",
    "video/webm": lambda payload: payload.startswith(b"\x1a\x45\xdf\xa3"),
    "audio/mpeg": lambda payload: payload.startswith(b"ID3") or payload.startswith(b"\xff\xfb"),
    "audio/wav": lambda payload: len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WAVE",
    "audio/x-wav": lambda payload: len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WAVE",
    "audio/ogg": lambda payload: payload.startswith(b"OggS"),
    "audio/webm": lambda payload: payload.startswith(b"\x1a\x45\xdf\xa3"),
}

NOTEBOOK_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES | {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_NUMBERED_SECTION_MARKER = re.compile(r"(?<![\w.])(\d+(?:\.\d+)+)(?=\s|[.)\-:])")


class IngestionError(ValueError):
    """Raised when an authoring asset cannot be safely inspected."""


@dataclass(frozen=True)
class AssetMetadata:
    path: str
    mime_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class UploadedAssetMetadata:
    """Metadata for a multipart upload; no raw upload is persisted here."""

    filename: str
    mime_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class CandidateSpan:
    text: str
    locator: dict
    status: str = "candidate"


def normalize_extracted_text(text: str) -> str:
    """Clean common PDF text-layer artifacts before a model sees the source.

    Some lecture PDFs contain every glyph twice in the text layer even though
    the page looks normal. Passing that artifact through produces titles such
    as ``AAnnaalloogg`` and makes the generated lesson unusable. We only apply
    duplicate-glyph collapsing when the whole extracted page shows a strong
    duplicate signal, so ordinary words such as ``book`` are left alone.
    """

    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\u00ad", "")
    normalized = re.sub(r"(?<=\w)-\s+(?=\w)", "", normalized)
    normalized = " ".join(normalized.split())
    letters = [char for char in normalized if char.isalpha()]
    duplicate_pairs = sum(
        1
        for left, right in zip(normalized, normalized[1:])
        if left.isalpha() and left.casefold() == right.casefold()
    )
    duplicate_ratio = duplicate_pairs / max(len(letters), 1)
    if duplicate_ratio >= 0.18:
        normalized = re.sub(r"([A-Za-z])\1", r"\1", normalized)
        normalized = re.sub(r"([.!?,;:])\1+", r"\1", normalized)
    return " ".join(normalized.split()).strip()


def inspect_asset(path: str | Path, *, max_bytes: int = MAX_SOURCE_BYTES) -> AssetMetadata:
    """Validate a local authoring asset and return its stable metadata."""
    asset = Path(path)
    if not asset.is_file():
        raise IngestionError("asset does not exist")
    size = asset.stat().st_size
    if size <= 0 or size > max_bytes:
        raise IngestionError("asset size is outside the allowed range")
    mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES:
        raise IngestionError(f"unsupported media type: {mime}")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    return AssetMetadata(str(asset), mime, size, digest)


def inspect_uploaded_asset(uploaded_file, *, max_bytes: int = MAX_SOURCE_BYTES, allowed_mime_types: set[str] | None = None) -> tuple[UploadedAssetMetadata, bytes]:
    """Read and validate a Django UploadedFile for the authoring pipeline.

    MIME declarations and file suffixes are checked against a small signature
    table. This is deliberately an authoring-time helper: the returned bytes
    are used only for candidate extraction and are not published as evidence.
    """

    filename = Path(str(getattr(uploaded_file, "name", ""))).name
    if not filename:
        raise IngestionError("uploaded file must have a filename")

    declared_mime = str(getattr(uploaded_file, "content_type", "") or "").lower().strip()
    guessed_mime = mimetypes.guess_type(filename)[0]
    if declared_mime in {"", "application/octet-stream"}:
        mime = guessed_mime or declared_mime
    else:
        mime = declared_mime
    if mime not in (allowed_mime_types or ALLOWED_MIME_TYPES):
        raise IngestionError(f"unsupported media type: {mime or 'unknown'}")
    if guessed_mime and guessed_mime != mime:
        raise IngestionError("file extension does not match the declared media type")

    declared_size = getattr(uploaded_file, "size", None)
    if declared_size is not None and (declared_size <= 0 or declared_size > max_bytes):
        raise IngestionError("asset size is outside the allowed range")

    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass
    chunks: list[bytes] = []
    total = 0
    for chunk in uploaded_file.chunks():
        total += len(chunk)
        if total > max_bytes:
            raise IngestionError("asset size is outside the allowed range")
        chunks.append(chunk)
    payload = b"".join(chunks)
    if total <= 0:
        raise IngestionError("asset size is outside the allowed range")
    signature_check = _MIME_SIGNATURES[mime]
    if not signature_check(payload):
        raise IngestionError("file signature does not match the declared media type")

    return UploadedAssetMetadata(filename=filename, mime_type=mime, size_bytes=total, sha256=hashlib.sha256(payload).hexdigest()), payload


def extract_pdf_candidates(path: str | Path) -> list[CandidateSpan]:
    """Extract page-located text candidates; never marks them approved."""
    metadata = inspect_asset(path)
    if metadata.mime_type != "application/pdf":
        raise IngestionError("extract_pdf_candidates requires a PDF")
    return extract_pdf_candidates_from_bytes(Path(metadata.path).read_bytes(), sha256=metadata.sha256)


def extract_pdf_candidates_from_bytes(payload: bytes, *, sha256: str) -> list[CandidateSpan]:
    """Extract page-located text from validated PDF bytes."""

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise IngestionError("pypdf is required for PDF authoring ingestion") from exc

    try:
        reader = PdfReader(BytesIO(payload))
        spans: list[CandidateSpan] = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                extracted = page.extract_text(extraction_mode="layout") or ""
            except TypeError:  # pragma: no cover - older pypdf compatibility
                extracted = page.extract_text() or ""
            text = normalize_extracted_text(extracted)
            if text:
                sections = split_numbered_sections(text, page_number=page_number, sha256=sha256)
                spans.extend(sections or [CandidateSpan(text=text, locator={"kind": "pdf-page", "page": page_number, "sha256": sha256})])
        return spans
    except Exception as exc:
        raise IngestionError("unable to extract PDF text") from exc


def split_numbered_sections(text: str, *, page_number: int, sha256: str) -> list[CandidateSpan]:
    """Keep numbered textbook sections separate when a page contains many of them."""
    matches = list(_NUMBERED_SECTION_MARKER.finditer(text))
    if len(matches) < 2:
        return []
    sections: list[CandidateSpan] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = " ".join(text[start:end].split()).strip()
        # Ignore incidental numeric references; a real section candidate has
        # enough explanatory text to support a learner-facing topic.
        if len(section_text) < 70:
            continue
        sections.append(CandidateSpan(
            text=section_text,
            locator={"kind": "pdf-section", "page": page_number, "section": match.group(1), "sha256": sha256},
        ))
    return sections


def media_pipeline_states() -> tuple[str, ...]:
    return ("pending", "validating", "extracting", "transcribing", "awaiting_approval", "approved", "published", "rejected")
