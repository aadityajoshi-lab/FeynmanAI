from __future__ import annotations

import hashlib

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from teachback.models import StudySource


def _pdf_bytes(text: str = "Sampling evidence") -> bytes:
    stream = f"BT /F1 24 Tf 72 200 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        b"4 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    payload = b"%PDF-1.4\n"
    offsets = [0]
    for item in objects:
        offsets.append(len(payload))
        payload += item
    xref = len(payload)
    payload += b"xref\n0 6\n0000000000 65535 f \n"
    payload += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    payload += b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return payload


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_pdf_ingest_returns_candidates_checksum_and_review_gate(client: APIClient) -> None:
    payload = _pdf_bytes()
    response = client.post(
        "/api/v1/study-sources/ingest",
        {
            "file": SimpleUploadedFile("sampling.pdf", payload, content_type="application/pdf"),
            "title": "Sampling chapter",
            "subjectId": "dsap",
            "moduleId": "sampling-aliasing",
        },
        format="multipart",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assetKind"] == "pdf"
    assert body["mimeType"] == "application/pdf"
    assert body["sizeBytes"] == len(payload)
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["status"] == "awaiting_approval"
    assert body["approvalStatus"] == "instructor_review_required"
    assert body["autoApproved"] is False
    assert body["publishable"] is False
    assert body["extraction"]["method"] == "pypdf"
    assert body["candidates"][0]["status"] == "candidate"
    assert "Sampling evidence" in body["candidates"][0]["text"]
    assert body["candidates"][0]["locator"]["page"] == 1
    assert StudySource.objects.filter(source_id=body["sourceId"], sha256=body["sha256"]).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filename", "content_type", "payload", "asset_kind"),
    [
        ("diagram.png", "image/png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00", "image"),
        ("lecture.mp4", "video/mp4", b"\x00\x00\x00\x18ftypisom\x00\x00", "video"),
    ],
)
def test_image_and_video_ingest_defer_extraction_without_auto_approval(
    client: APIClient, filename: str, content_type: str, payload: bytes, asset_kind: str
) -> None:
    response = client.post(
        "/api/v1/study-sources/ingest/",
        {"file": SimpleUploadedFile(filename, payload, content_type=content_type)},
        format="multipart",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["assetKind"] == asset_kind
    assert body["candidates"] == []
    assert body["extraction"]["status"] == "deferred"
    assert body["approvalStatus"] == "instructor_review_required"
    assert body["autoApproved"] is False


@pytest.mark.django_db
def test_ingest_rejects_missing_file_and_mismatched_or_unsupported_assets(client: APIClient) -> None:
    missing = client.post("/api/v1/study-sources/ingest", {}, format="multipart")
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "missing_file"

    unsupported = client.post(
        "/api/v1/study-sources/ingest",
        {"file": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
        format="multipart",
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["error"]["code"] == "invalid_upload"

    mismatch = client.post(
        "/api/v1/study-sources/ingest",
        {"file": SimpleUploadedFile("notes.png", _pdf_bytes(), content_type="application/pdf")},
        format="multipart",
    )
    assert mismatch.status_code == 422
    assert "extension" in mismatch.json()["error"]["message"]


@pytest.mark.django_db
def test_malformed_pdf_fails_closed(client: APIClient) -> None:
    response = client.post(
        "/api/v1/study-sources/ingest",
        {"file": SimpleUploadedFile("broken.pdf", b"%PDF-1.7\nnot a pdf", content_type="application/pdf")},
        format="multipart",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_extraction_failed"


@pytest.mark.django_db
def test_url_sources_enter_the_review_pipeline_without_becoming_evidence(client: APIClient) -> None:
    response = client.post(
        "/api/v1/study-sources/ingest",
        {"url": "https://example.edu/dsap/chapter-7", "sourceKind": "research_paper", "title": "DSP paper"},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["sourceKind"] == "research_paper"
    assert body["status"] == "awaiting_approval"
    assert body["extraction"]["status"] == "deferred"
    assert body["candidates"] == []
