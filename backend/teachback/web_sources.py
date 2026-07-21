"""Bounded fetching and normalization for learner-supplied source URLs.

This module is deliberately small and defensive. A URL source is fetched only
when the learner explicitly adds it to a notebook; it is never used as a
general web-search proxy. Raw response bytes are returned to the caller for
immediate extraction and are not persisted.
"""
from __future__ import annotations

import base64
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from django.conf import settings


class WebSourceError(ValueError):
    pass


@dataclass(frozen=True)
class FetchedReference:
    payload: bytes
    extraction_mime: str
    original_mime: str
    final_url: str
    title: str
    source_kind: str
    fetched_bytes: int
    metadata: dict[str, str] = field(default_factory=dict)
    assets: tuple[dict[str, str], ...] = ()


def _host_is_public(hostname: str) -> bool:
    host = (hostname or "").strip(".").casefold()
    if not host or host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except OSError as exc:
        raise WebSourceError("The source host could not be resolved.") from exc
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise WebSourceError("The source host returned an invalid address.") from exc
        if parsed.is_private or parsed.is_loopback or parsed.is_link_local or parsed.is_reserved or parsed.is_multicast or parsed.is_unspecified:
            return False
    return True


def validate_reference_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise WebSourceError("Reference URLs must be public http(s) URLs.")
    if not _host_is_public(parsed.hostname):
        raise WebSourceError("Private, local, and internal source hosts are not allowed.")
    return parsed.geturl()


def _arxiv_pdf_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if host not in {"arxiv.org", "export.arxiv.org"}:
        return None
    match = re.fullmatch(r"/(?:abs|pdf)/([^/?#]+?)(?:\.pdf)?/?", parsed.path or "")
    if not match:
        return None
    return f"https://export.arxiv.org/pdf/{match.group(1)}.pdf"


class _ReadablePageParser(HTMLParser):
    """Keep readable teaching content plus a small, bounded visual index.

    It intentionally does not preserve HTML.  The caller persists normalized
    Markdown and accepted image data only, so third-party scripts, trackers,
    and raw page markup never become notebook memory.
    """

    _ignored = {"script", "style", "noscript", "template", "svg", "canvas", "nav", "footer", "header", "form", "aside"}
    _block_tags = {"p", "div", "article", "section", "main", "h1", "h2", "h3", "h4", "li", "pre", "blockquote", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.metadata: dict[str, str] = {}
        self.images: list[dict[str, str]] = []
        self._ignored_depth = 0
        self._in_title = False
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._figure_image_indexes: list[int] | None = None
        self._caption_parts: list[str] | None = None

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(key).casefold(): str(value or "").strip() for key, value in attrs}

    def _append_break(self) -> None:
        if self._ignored_depth == 0:
            self.parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        values = self._attrs(attrs)
        if tag in self._ignored:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (values.get("name") or values.get("property") or "").casefold()
            content = values.get("content") or ""
            if key in {"description", "og:description"} and content and "description" not in self.metadata:
                self.metadata["description"] = content[:600]
            elif key == "og:title" and content and "ogTitle" not in self.metadata:
                self.metadata["ogTitle"] = content[:300]
        elif tag == "link" and "canonical" in values.get("rel", "").casefold() and values.get("href"):
            self.metadata.setdefault("canonicalUrl", values["href"][:2000])
        elif tag == "img" and (values.get("src") or values.get("data-src") or values.get("data-original")):
            source = values.get("src") or values.get("data-src") or values.get("data-original")
            if source:
                self.images.append({"url": source, "alt": values.get("alt") or "Webpage visual"})
                if self._figure_image_indexes is not None:
                    self._figure_image_indexes.append(len(self.images) - 1)
        elif tag == "figure":
            self._figure_image_indexes = []
        elif tag == "figcaption":
            self._caption_parts = []
        elif tag == "table":
            self._table_rows = []
        elif tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
        if tag in self._block_tags:
            self._append_break()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "title":
            self._in_title = False
        if tag in self._ignored:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            self._current_row.append(" ".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if any(self._current_row):
                self._table_rows.append(self._current_row)
            self._current_row = None
        elif tag == "table":
            self._append_table()
            self._table_rows = []
        elif tag == "figcaption" and self._caption_parts is not None:
            caption = " ".join(self._caption_parts).strip()
            if caption and self._figure_image_indexes is not None:
                for index in self._figure_image_indexes:
                    self.images[index]["caption"] = caption[:600]
            self._caption_parts = None
        elif tag == "figure":
            self._figure_image_indexes = None
        if tag in self._block_tags:
            self._append_break()

    def _append_table(self) -> None:
        rows = [row for row in self._table_rows if row]
        if not rows:
            return
        width = max(len(row) for row in rows)
        normalized = [(row + [""] * width)[:width] for row in rows]
        header = [cell.replace("|", "\\|") for cell in normalized[0]]
        self.parts.extend(["\n", "| " + " | ".join(header) + " |", "\n", "| " + " | ".join(["---"] * width) + " |", "\n"])
        for row in normalized[1:]:
            self.parts.extend(["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |", "\n"])
        self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not data.strip() or self._ignored_depth:
            return
        clean = re.sub(r"\s+", " ", data).strip()
        if self._in_title:
            self.title_parts.append(clean)
        if self._current_cell is not None:
            self._current_cell.append(clean)
        elif self._caption_parts is not None:
            self._caption_parts.append(clean)
        else:
            self.parts.append(clean)


def _html_payload(payload: bytes, url: str) -> tuple[bytes, str, dict[str, str], list[dict[str, str]]]:
    parser = _ReadablePageParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    parser.close()
    text = re.sub(r"[ \t]+", " ", " ".join(parser.parts))
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 80:
        raise WebSourceError("The webpage did not contain enough readable text to ground a notebook.")
    title = " ".join(parser.title_parts).strip() or parser.metadata.get("ogTitle") or urlparse(url).netloc
    metadata = {"title": title, **parser.metadata}
    return f"# {title}\n\n{text}".encode("utf-8"), title, metadata, parser.images


def _read_bounded_response(url: str, max_bytes: int, *, accept: str) -> tuple[bytes, str, str]:
    """Fetch one already-public resource and reject oversized responses.

    Every requested image goes through the same host check as the main page.
    Redirect destinations are checked before anything is retained.  A failed
    optional visual never makes a usable text source fail.
    """
    requested_url = validate_reference_url(url)
    request = Request(
        requested_url,
        headers={"User-Agent": "FeynmanLearningOS/1.0 source-fetch", "Accept": accept},
        method="GET",
    )
    timeout = float(getattr(settings, "WEB_SOURCE_TIMEOUT_SECONDS", 30))
    try:
        with urlopen(request, timeout=timeout) as response:
            final_url = validate_reference_url(response.geturl())
            content_type = (response.headers.get_content_type() or "application/octet-stream").casefold()
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(min(1024 * 1024, max_bytes - total + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise WebSourceError("The source exceeds the configured fetch limit.")
    except WebSourceError:
        raise
    except (OSError, ValueError) as exc:
        raise WebSourceError("The source could not be fetched right now.") from exc
    payload = b"".join(chunks)
    if not payload:
        raise WebSourceError("The source returned an empty response.")
    return payload, content_type, final_url


def _page_visual_assets(candidates: list[dict[str, str]], page_url: str) -> tuple[dict[str, str], ...]:
    """Return a small set of safe, durable visual assets for an HTML source."""
    max_images = max(0, min(int(getattr(settings, "WEB_SOURCE_MAX_IMAGES", 6)), 12))
    max_image_bytes = max(16 * 1024, int(getattr(settings, "WEB_SOURCE_MAX_IMAGE_BYTES", 2 * 1024 * 1024)))
    assets: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for candidate in candidates:
        if len(assets) >= max_images:
            break
        raw_url = str(candidate.get("url") or "").strip()
        if not raw_url or raw_url.startswith("data:"):
            continue
        try:
            image_url = validate_reference_url(urljoin(page_url, raw_url))
        except WebSourceError:
            continue
        if image_url in seen_urls:
            continue
        seen_urls.add(image_url)
        try:
            image_bytes, mime_type, _ = _read_bounded_response(image_url, max_image_bytes, accept="image/*")
        except WebSourceError:
            continue
        if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
            continue
        alt = str(candidate.get("caption") or candidate.get("alt") or "Webpage visual").strip()[:600]
        assets.append({
            "type": "image",
            "mimeType": mime_type,
            "alt": alt or "Webpage visual",
            "dataUrl": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
        })
    return tuple(assets)


def fetch_reference(url: str) -> FetchedReference:
    requested_url = validate_reference_url(url)
    arxiv_url = _arxiv_pdf_url(requested_url)
    fetch_url = arxiv_url or requested_url
    max_bytes = int(getattr(settings, "WEB_SOURCE_MAX_BYTES", 25 * 1024 * 1024))
    payload, content_type, final_url = _read_bounded_response(fetch_url, max_bytes, accept="text/html,application/pdf;q=0.9,*/*;q=0.1")
    if arxiv_url or content_type == "application/pdf" or final_url.casefold().split("?", 1)[0].endswith(".pdf"):
        title = PurePosixPath(urlparse(final_url).path).name or "arXiv paper"
        return FetchedReference(payload, "application/pdf", content_type, final_url, title, "arxiv_pdf" if arxiv_url else "web_pdf", len(payload))
    if content_type in {"text/html", "application/xhtml+xml"} or final_url.casefold().split("?", 1)[0].endswith(('.html', '.htm')):
        cleaned, title, metadata, candidates = _html_payload(payload, final_url)
        return FetchedReference(
            cleaned,
            "text/markdown",
            content_type,
            final_url,
            title,
            "web_page",
            len(payload),
            metadata=metadata,
            assets=_page_visual_assets(candidates, final_url),
        )
    raise WebSourceError("This URL is not an HTML page or PDF.")
