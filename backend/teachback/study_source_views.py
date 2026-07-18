"""Bounded authoring-time upload endpoint for study materials.

The endpoint validates one uploaded asset, computes its checksum, and (for
PDFs) extracts page-located text candidates. Candidates are never treated as
approved evidence and raw uploads are not persisted by this MVP.
"""

from __future__ import annotations

import uuid
import hashlib
from urllib.parse import urlparse

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .ingestion import IngestionError, extract_pdf_candidates_from_bytes, inspect_uploaded_asset
from .models import StudySource


def _error(message: str, code: str = "invalid_upload", status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
    return Response({"error": {"code": code, "message": message, "details": []}}, status=status_code)


def _asset_kind(mime_type: str) -> str:
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    return "video"


@method_decorator(csrf_exempt, name="dispatch")
class StudySourceIngestView(APIView):
    """Accept one PDF/image/video and return a reviewable candidate manifest."""

    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        uploaded_file = request.FILES.get("file") or request.FILES.get("asset")
        if uploaded_file is None:
            url = str(request.data.get("url") or "").strip()
            parsed = urlparse(url)
            if not url or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return _error("provide a PDF/image/audio/video file or an http(s) source URL", "missing_file")
            title = str(request.data.get("title") or parsed.netloc).strip()[:240]
            subject_id = str(request.data.get("subjectId") or "").strip()[:100]
            module_id = str(request.data.get("moduleId") or "").strip()[:120]
            source_kind = str(request.data.get("sourceKind") or "website").strip()[:32]
            source_id = f"url_{hashlib.sha256(url.encode('utf-8')).hexdigest()[:32]}"
            pipeline = {"state": "awaiting_approval", "steps": [{"name": "validate", "state": "complete"}, {"name": "fetch", "state": "pending"}, {"name": "extract", "state": "pending"}, {"name": "approve", "state": "pending"}]}
            source, _ = StudySource.objects.update_or_create(source_id=source_id, defaults={"title": title or url, "subject_id": subject_id, "module_id": module_id, "source_kind": source_kind, "source_url": url, "status": "awaiting_approval", "approval_status": "instructor_review_required", "extraction": {"status": "deferred", "method": "url_fetch_pending"}, "candidates": [], "pipeline": pipeline})
            return Response({"sourceId": source.source_id, "title": source.title, "sourceKind": source_kind, "sourceUrl": url, "status": source.status, "approvalStatus": source.approval_status, "autoApproved": False, "publishable": False, "extraction": source.extraction, "pipeline": pipeline, "candidates": []}, status=status.HTTP_201_CREATED)

        try:
            metadata, payload = inspect_uploaded_asset(uploaded_file)
        except IngestionError as exc:
            return _error(str(exc))

        candidates = []
        extraction = {"status": "deferred", "method": None}
        if metadata.mime_type == "application/pdf":
            try:
                raw_candidates = extract_pdf_candidates_from_bytes(payload, sha256=metadata.sha256)
            except IngestionError as exc:
                return _error(str(exc), "pdf_extraction_failed")
            candidates = [
                {
                    "candidateId": f"candidate_{metadata.sha256[:12]}_{item.locator.get('page', index + 1):03d}_{index + 1:02d}",
                    "text": item.text,
                    "locator": item.locator,
                    "status": item.status,
                }
                for index, item in enumerate(raw_candidates)
            ]
            extraction = {"status": "complete", "method": "pypdf", "pageCandidateCount": len(raw_candidates), "sectionCandidateCount": sum(1 for item in raw_candidates if item.locator.get("kind") == "pdf-section")}
        else:
            extraction["nextStep"] = "Run the approved OCR or transcript pipeline before publishing source spans."

        body = request.data
        title = str(body.get("title") or metadata.filename).strip()[:240]
        subject_id = str(body.get("subjectId") or "").strip()[:100]
        module_id = str(body.get("moduleId") or "").strip()[:120]
        source_id = f"upload_{uuid.uuid4().hex}"
        asset_kind = _asset_kind(metadata.mime_type)
        requested_source_kind = str(body.get("sourceKind") or "").strip()[:32]
        source_kind = requested_source_kind if requested_source_kind in {"notes", "past_questions"} else asset_kind
        pipeline = {
            "state": "awaiting_approval",
            "steps": [
                {"name": "validate", "state": "complete"},
                {"name": "extract", "state": extraction["status"]},
                {"name": "transcribe", "state": "deferred" if asset_kind in {"audio", "video"} else "not_required"},
                {"name": "approve", "state": "pending"},
            ],
        }
        StudySource.objects.create(
            source_id=source_id,
            title=title or metadata.filename,
            subject_id=subject_id,
            module_id=module_id,
            source_kind=source_kind,
            filename=metadata.filename,
            mime_type=metadata.mime_type,
            size_bytes=metadata.size_bytes,
            sha256=metadata.sha256,
            status="awaiting_approval",
            approval_status="instructor_review_required",
            extraction=extraction,
            candidates=candidates,
            pipeline=pipeline,
        )
        return Response(
            {
                "sourceId": source_id,
                "title": title,
                "subjectId": subject_id or None,
                "moduleId": module_id or None,
                "assetKind": asset_kind,
                "sourceKind": source_kind,
                "filename": metadata.filename,
                "mimeType": metadata.mime_type,
                "sizeBytes": metadata.size_bytes,
                "sha256": metadata.sha256,
                "status": "awaiting_approval",
                "approvalStatus": "instructor_review_required",
                "autoApproved": False,
                "publishable": False,
                "extraction": extraction,
                "pipeline": pipeline,
                "candidates": candidates,
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
class StudySourceDetailView(APIView):
    def get(self, request, source_id):
        source = StudySource.objects.filter(source_id=source_id).first()
        if source is None:
            return _error("unknown source", "not_found", status.HTTP_404_NOT_FOUND)
        return Response({
            "sourceId": source.source_id,
            "title": source.title,
            "subjectId": source.subject_id or None,
            "moduleId": source.module_id or None,
            "sourceKind": source.source_kind,
            "filename": source.filename or None,
            "sourceUrl": source.source_url or None,
            "mimeType": source.mime_type or None,
            "sizeBytes": source.size_bytes,
            "sha256": source.sha256 or None,
            "status": source.status,
            "approvalStatus": source.approval_status,
            "extraction": source.extraction,
            "pipeline": source.pipeline,
            "candidates": source.candidates,
        })
