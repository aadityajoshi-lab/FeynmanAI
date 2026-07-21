from __future__ import annotations

from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from teachback.web_sources import WebSourceError, fetch_reference


class _Response:
    def __init__(self, payload: bytes, content_type: str, url: str):
        self._payload = payload
        self._offset = 0
        self._url = url
        self.headers = Message()
        self.headers.set_type(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self._url

    def read(self, size=-1):
        if self._offset >= len(self._payload):
            return b""
        if size < 0:
            size = len(self._payload)
        chunk = self._payload[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_arxiv_abs_reference_resolves_to_pdf() -> None:
    with patch("teachback.web_sources.socket.getaddrinfo", return_value=[(None, None, None, None, ("151.101.3.42", 0))]):
        with patch("teachback.web_sources.urlopen", return_value=_Response(b"%PDF-1.7", "application/pdf", "https://export.arxiv.org/pdf/1706.03762")) as fetch:
            result = fetch_reference("https://arxiv.org/abs/1706.03762")
    assert result.source_kind == "arxiv_pdf"
    assert result.extraction_mime == "application/pdf"
    assert result.final_url.endswith("/pdf/1706.03762")
    assert fetch.call_args.args[0].full_url.endswith("/pdf/1706.03762.pdf")


def test_html_reference_is_reduced_to_readable_source_text() -> None:
    html = b"<html><head><title>Signal notes</title><script>ignore()</script></head><body><nav>Menu</nav><article><h1>Sampling</h1><p>Sampling maps a continuous signal to discrete observations.</p><p>Reconstruction requires a sufficient sampling rate.</p></article></body></html>"
    with patch("teachback.web_sources.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
        with patch("teachback.web_sources.urlopen", return_value=_Response(html, "text/html", "https://example.com/notes")):
            result = fetch_reference("https://example.com/notes")
    text = result.payload.decode("utf-8")
    assert result.source_kind == "web_page"
    assert result.title == "Signal notes"
    assert "Sampling maps" in text
    assert "ignore()" not in text
    assert "Menu" not in text


def test_html_reference_preserves_a_bounded_public_visual_and_table() -> None:
    html = b"""<html><head><title>Sampling guide</title><meta name='description' content='A concise sampling guide.'></head>
    <body><article><p>Sampling maps a continuous signal to evenly spaced observations so the original waveform can be reasoned about.</p>
    <table><tr><th>Rate</th><th>Effect</th></tr><tr><td>Low</td><td>Aliases</td></tr></table>
    <figure><img src='/images/wave.png' alt='Waveform'><figcaption>Aliased waveform</figcaption></figure></article></body></html>"""

    def response_for(request, **_kwargs):
        if request.full_url.endswith("/images/wave.png"):
            return _Response(b"\x89PNG\r\n\x1a\nimage", "image/png", request.full_url)
        return _Response(html, "text/html", "https://example.com/notes")

    with patch("teachback.web_sources.socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 0))]):
        with patch("teachback.web_sources.urlopen", side_effect=response_for):
            result = fetch_reference("https://example.com/notes")
    text = result.payload.decode("utf-8")
    assert "| Rate | Effect |" in text
    assert result.metadata["description"] == "A concise sampling guide."
    assert len(result.assets) == 1
    assert result.assets[0]["alt"] == "Aliased waveform"
    assert result.assets[0]["dataUrl"].startswith("data:image/png;base64,")


def test_private_source_hosts_are_rejected() -> None:
    with pytest.raises(WebSourceError, match="Private"):
        fetch_reference("http://127.0.0.1:8000/internal")
