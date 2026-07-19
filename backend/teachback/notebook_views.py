from __future__ import annotations

import re
import uuid

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .ingestion import IngestionError, NOTEBOOK_ALLOWED_MIME_TYPES, inspect_uploaded_asset
from .models import Notebook, NotebookArtifact, NotebookSource
from .notebook_media import answer_notebook_question, generate_openmaic_lesson
from .notebook_pipeline import NotebookExtractionError, build_artifact_payload, extract_source, notebook_payload, rebuild_knowledge_pack
from .providers import ProviderOutputError, ProviderUnavailable


def _error(message: str, code: str = "invalid_request", status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY):
    return Response({"error": {"code": code, "message": message, "details": []}}, status=status_code)


def _notebook(notebook_id: uuid.UUID):
    return Notebook.objects.filter(notebook_id=notebook_id).first()


def _slug_title(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:240]


@method_decorator(csrf_exempt, name="dispatch")
class NotebookCreateView(APIView):
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        body = request.data
        title = _slug_title(str(body.get("title") or body.get("subject") or ""))
        if not title:
            return _error("Give your notebook a name before adding sources.", "missing_title")
        notebook = Notebook.objects.create(
            title=title,
            subject=_slug_title(str(body.get("subject") or title)),
            description=str(body.get("description") or "").strip()[:2000],
            learning_goal=str(body.get("learningGoal") or "understand").strip()[:40],
            status="collecting",
            ocr_provider=str(body.get("ocrProvider") or "auto").strip()[:80],
        )
        return Response(notebook_payload(notebook), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class NotebookDetailView(APIView):
    def get(self, request, notebook_id):
        notebook = _notebook(notebook_id)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return Response(notebook_payload(notebook))


@method_decorator(csrf_exempt, name="dispatch")
class NotebookSourceUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        uploaded_file = request.FILES.get("file") or request.FILES.get("source")
        if uploaded_file is None:
            return _error("Choose a PDF, image, text, or supported document first.", "missing_file")
        try:
            metadata, payload = inspect_uploaded_asset(uploaded_file, allowed_mime_types=NOTEBOOK_ALLOWED_MIME_TYPES)
        except IngestionError as exc:
            return _error(str(exc), "invalid_source")
        provider = str(request.data.get("ocrProvider") or notebook.ocr_provider or "auto").strip().lower()
        source = NotebookSource.objects.create(
            notebook=notebook,
            source_id=f"nbsrc_{uuid.uuid4().hex}",
            title=_slug_title(str(request.data.get("title") or metadata.filename)),
            source_kind=str(request.data.get("sourceKind") or "reference").strip()[:40],
            filename=metadata.filename,
            mime_type=metadata.mime_type,
            size_bytes=metadata.size_bytes,
            sha256=metadata.sha256,
            status="extracting",
            extraction_method="pending",
        )
        try:
            blocks, assets, stats, method = extract_source(payload, metadata.mime_type, metadata.sha256, provider=provider)
        except NotebookExtractionError as exc:
            source.status = "failed"
            source.extraction_method = "failed"
            source.extraction = {"status": "failed", "message": str(exc)}
            source.save(update_fields=["status", "extraction_method", "extraction", "updated_at"])
            return _error(str(exc), "extraction_failed")
        source.status = "ready"
        source.extraction_method = method
        source.extraction = {"status": "complete", **stats}
        source.blocks = blocks
        source.assets = assets
        source.save(update_fields=["status", "extraction_method", "extraction", "blocks", "assets", "updated_at"])
        notebook.status = "processing"
        notebook.ocr_provider = method
        pack, markdown = rebuild_knowledge_pack(notebook)
        notebook.knowledge_pack = pack
        notebook.knowledge_pack_markdown = markdown
        notebook.stats = {"sourceCount": notebook.notebook_sources.count(), "sectionCount": len(pack.get("sections") or []), "assetCount": len(pack.get("assets") or []), "formulaCount": len(pack.get("formulas") or [])}
        notebook.status = "ready"
        notebook.save(update_fields=["status", "ocr_provider", "knowledge_pack", "knowledge_pack_markdown", "stats", "updated_at"])
        # Existing outputs must never keep presenting a question made from an
        # older, poorly structured pack after a source is reprocessed.
        for artifact in notebook.artifacts.all():
            try:
                artifact.title, artifact.payload = build_artifact_payload(pack, artifact.artifact_type)
                artifact.source_ids = source_ids = pack.get("sources") or []
                artifact.status = "ready"
                artifact.save(update_fields=["title", "payload", "source_ids", "status"])
            except ValueError:
                artifact.status = "stale"
                artifact.save(update_fields=["status"])
        return Response(notebook_payload(notebook), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class NotebookArtifactView(APIView):
    parser_classes = [JSONParser]

    def get(self, request, notebook_id):
        notebook = _notebook(notebook_id)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return Response({"artifacts": notebook_payload(notebook)["artifacts"]})

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        artifact_type = str(request.data.get("type") or "").strip().lower()
        if artifact_type not in {"summary", "mcq", "slides", "formula_sheet", "important_questions", "flashcards"}:
            return _error("Choose a supported notebook output.", "unsupported_artifact")
        if not notebook.knowledge_pack:
            return _error("Add and process at least one source before creating an output.", "empty_notebook")
        try:
            title, payload = build_artifact_payload(notebook.knowledge_pack, artifact_type)
        except ValueError as exc:
            return _error(str(exc), "artifact_failed")
        artifact = NotebookArtifact.objects.create(notebook=notebook, artifact_type=artifact_type, title=title, payload=payload, source_ids=notebook.knowledge_pack.get("sources") or [])
        return Response({"artifactId": str(artifact.artifact_id), "type": artifact.artifact_type, "title": artifact.title, "status": artifact.status, "payload": artifact.payload, "createdAt": artifact.created_at.isoformat()}, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class NotebookAskView(APIView):
    parser_classes = [JSONParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        question = re.sub(r"\s+", " ", str(request.data.get("question") or "").strip())[:800]
        if not question:
            return _error("Ask a question about this notebook.", "missing_question")
        allow_web_search = request.data.get("allowWebSearch", True) is not False
        try:
            return Response(answer_notebook_question(notebook.knowledge_pack or {}, question, allow_web_search=allow_web_search))
        except Exception as exc:
            return _error(f"Notebook copilot failed: {exc}", "copilot_failed", status.HTTP_502_BAD_GATEWAY)


@method_decorator(csrf_exempt, name="dispatch")
class NotebookLessonView(APIView):
    """Create and persist an OpenMAIC-style narrated lesson for a question."""

    parser_classes = [JSONParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        body = request.data if isinstance(request.data, dict) else {}
        question = re.sub(r"\s+", " ", str(body.get("question") or "Create a guided lesson from this notebook.").strip())[:800]
        try:
            duration = int(body.get("requestedDurationSeconds") or 120)
        except (TypeError, ValueError):
            return _error("requestedDurationSeconds must be between 60 and 300.", "invalid_duration")
        allow_web_search = body.get("allowWebSearch", True) is not False
        try:
            payload = generate_openmaic_lesson(notebook.knowledge_pack or {}, question, allow_web_search=allow_web_search, requested_duration=duration)
        except ProviderUnavailable as exc:
            return _error(str(exc), "provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        except ProviderOutputError as exc:
            return _error(str(exc), "lesson_generation_failed", status.HTTP_502_BAD_GATEWAY)
        artifact = NotebookArtifact.objects.create(
            notebook=notebook,
            artifact_type="openmaic_lesson",
            title=str(payload.get("title") or "Narrated study lesson"),
            payload=payload,
            source_ids=payload.get("sourceIds") or [],
        )
        return Response({"artifactId": str(artifact.artifact_id), "type": artifact.artifact_type, "title": artifact.title, "status": artifact.status, "payload": artifact.payload, "createdAt": artifact.created_at.isoformat()}, status=status.HTTP_201_CREATED)


def _section_text(section: dict) -> str:
    return " ".join(str(block.get("markdown") or "") for block in section.get("blocks") or [])
