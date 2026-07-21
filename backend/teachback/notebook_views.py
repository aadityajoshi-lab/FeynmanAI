from __future__ import annotations

import hashlib
import re
import uuid
from urllib.parse import urlparse

from django.db import transaction
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .ingestion import IngestionError, NOTEBOOK_ALLOWED_MIME_TYPES, inspect_uploaded_asset
from .learning_safety import personal_decision_boundary
from .models import (
    Course,
    CurriculumPack,
    GoalCurriculumRoute,
    Enrollment,
    EvidenceRecord,
    LearnerProfile,
    LearningActivity,
    LearningGoal,
    Membership,
    Notebook,
    NotebookArtifact,
    NotebookChatMessage,
    NotebookNote,
    NotebookSource,
)
from .notebook_media import (
    answer_notebook_question,
    generate_notebook_artifact,
    generate_openmaic_lesson,
    notebook_provider_error_category,
)
from .notebook_pipeline import (
    NotebookExtractionError,
    _chat_message_payload,
    _note_payload,
    extraction_error_category,
    extract_source,
    notebook_payload,
    rebuild_knowledge_pack,
    scoped_knowledge_pack,
)
from .providers import ProviderOutputError, ProviderUnavailable, record_provider_failure
from .web_sources import WebSourceError, fetch_reference


def _error(
    message: str,
    code: str = "invalid_request",
    status_code: int = status.HTTP_422_UNPROCESSABLE_ENTITY,
    *,
    extra: dict | None = None,
):
    payload = {"error": {"code": code, "message": message, "details": []}}
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def _notebook(notebook_id: uuid.UUID, request=None) -> Notebook | None:
    """Keep legacy UUID notebooks working while protecting newly owned notebooks."""
    notebook = Notebook.objects.filter(notebook_id=notebook_id).first()
    if not notebook or not notebook.owner_profile_id:
        return notebook
    user = getattr(request, "user", None) if request is not None else None
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return notebook if notebook.owner_profile.account_id == user.id else None


def _slug_title(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:240]


def _text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _grounding_enabled(value: object, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return default


def _source_ids(body: object) -> list[str] | None:
    if not isinstance(body, dict) or "sourceIds" not in body:
        return None
    raw = body.get("sourceIds")
    if not isinstance(raw, list):
        raise ValueError("sourceIds must be an array when provided.")
    return list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))


def _failed_extraction_metadata(error: NotebookExtractionError) -> dict:
    """Record a retryable, redacted provider failure without raw file bytes."""
    return {
        "status": "failed",
        "providerErrorCategory": extraction_error_category(error),
        "retryable": True,
        "retryAction": "reupload",
        # NotebookSource stores only extracted blocks/assets and hashes.  This
        # explicit marker makes the recovery contract clear to API consumers.
        "rawRetention": "discarded_after_extraction",
    }


def _scoped_pack(notebook: Notebook, body: object) -> tuple[dict, list[str]]:
    requested = _source_ids(body)
    pack = scoped_knowledge_pack(notebook, requested)
    return pack, list(pack.get("sources") or [])


def _artifact_payload(artifact: NotebookArtifact) -> dict:
    invalidated = artifact.status == "stale"
    payload = artifact.payload if isinstance(artifact.payload, dict) else {}
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    return {
        "artifactId": str(artifact.artifact_id),
        "type": artifact.artifact_type,
        "title": artifact.title,
        "status": artifact.status,
        "payload": {"invalidated": True, "message": "This output is unavailable because a referenced source was removed."} if invalidated else payload,
        "sourceIds": [] if invalidated else artifact.source_ids or [],
        "invalidated": invalidated,
        "provider": None if invalidated else provenance.get("provider"),
        "model": None if invalidated else provenance.get("model"),
        "providerStatus": None if invalidated else provenance.get("status"),
        "citationValidation": None if invalidated else provenance.get("citationValidation"),
        "createdAt": artifact.created_at.isoformat(),
    }


def _refresh_notebook_memory(notebook: Notebook, *, ocr_provider: str | None = None) -> tuple[Notebook, dict]:
    """Persist the canonical, page-aware notebook memory after a source change."""
    pack, markdown = rebuild_knowledge_pack(notebook)
    notebook.status = "ready" if pack.get("sources") else "collecting"
    if ocr_provider:
        notebook.ocr_provider = ocr_provider
    notebook.knowledge_pack = pack
    notebook.knowledge_pack_markdown = markdown
    notebook.stats = {
        "sourceCount": notebook.notebook_sources.count(),
        "sectionCount": len(pack.get("sections") or []),
        "assetCount": len(pack.get("assets") or []),
        "formulaCount": len(pack.get("formulas") or []),
    }
    notebook.save(update_fields=["status", "ocr_provider", "knowledge_pack", "knowledge_pack_markdown", "stats", "updated_at"])
    return notebook, pack


def _source_anchor_ids(source: NotebookSource) -> set[str]:
    blocks = source.blocks if isinstance(source.blocks, list) else []
    return {
        str(block.get("sourceAnchor")).strip()
        for block in blocks
        if isinstance(block, dict) and str(block.get("sourceAnchor") or "").strip()
    }


def _invalidate_removed_source(notebook: Notebook, source: NotebookSource) -> None:
    """Remove a deleted source from every derived object that relied on it.

    Notebook outputs become stale as before. Evidence is stricter: a removed
    anchor can no longer support a learner-state claim, so the record returns
    to ``needs_review`` until the learner supplies a fresh ready-source
    attempt. Activity source scopes are also pruned so a later submission
    cannot silently reuse the deleted source.
    """
    source_id = source.source_id
    for artifact in notebook.artifacts.all():
        if not artifact.source_ids or source_id in (artifact.source_ids or []):
            artifact.status = "stale"
            artifact.save(update_fields=["status"])
    for message in notebook.chat_messages.all():
        if source_id in (message.source_ids or []):
            message.status = "stale"
            message.save(update_fields=["status"])

    if not notebook.goal_id:
        return

    source_anchor_ids = _source_anchor_ids(source)
    source_anchor_prefix = f"{source.sha256[:12]}:" if source.sha256 else ""
    affected = False
    for evidence in EvidenceRecord.objects.filter(goal=notebook.goal).select_related("activity"):
        rubric = dict(evidence.rubric) if isinstance(evidence.rubric, dict) else {}
        selected_source_ids = rubric.get("selectedSourceIds") if isinstance(rubric.get("selectedSourceIds"), list) else []
        evidence_anchor_ids = evidence.source_anchor_ids if isinstance(evidence.source_anchor_ids, list) else []
        source_linked = source_id in selected_source_ids or any(
            anchor in source_anchor_ids or (source_anchor_prefix and anchor.startswith(source_anchor_prefix))
            for anchor in evidence_anchor_ids
            if isinstance(anchor, str)
        )
        if not source_linked:
            continue
        remaining_anchor_ids = [
            anchor
            for anchor in evidence_anchor_ids
            if isinstance(anchor, str)
            and anchor not in source_anchor_ids
            and not (source_anchor_prefix and anchor.startswith(source_anchor_prefix))
        ]
        remaining_source_ids = [item for item in selected_source_ids if item != source_id]
        invalidated_source_ids = rubric.get("invalidatedSourceIds") if isinstance(rubric.get("invalidatedSourceIds"), list) else []
        rubric["selectedSourceIds"] = remaining_source_ids
        rubric["invalidatedSourceIds"] = list(dict.fromkeys([*invalidated_source_ids, source_id]))
        rubric["sourceVerificationState"] = "invalidated"
        evidence.source_anchor_ids = remaining_anchor_ids
        evidence.status = "needs_review"
        evidence.summary = "A source supporting this evidence was removed. Add a ready source and submit a fresh attempt to verify it."
        evidence.rubric = rubric
        evidence.save(update_fields=["source_anchor_ids", "status", "summary", "rubric", "updated_at"])
        affected = True

    for activity in LearningActivity.objects.filter(goal=notebook.goal):
        activity_source_ids = activity.source_ids if isinstance(activity.source_ids, list) else []
        if source_id not in activity_source_ids:
            continue
        remaining_source_ids = [item for item in activity_source_ids if item != source_id]
        activity.source_ids = remaining_source_ids
        evaluator = activity.evaluator if isinstance(activity.evaluator, dict) else {}
        if evaluator.get("requiresSource") and not remaining_source_ids:
            activity.status = "needs_source"
            activity.save(update_fields=["source_ids", "status", "updated_at"])
        else:
            activity.save(update_fields=["source_ids", "updated_at"])
        affected = True

    for pack in CurriculumPack.objects.filter(goal=notebook.goal, status__in=["ready", "needs_review"]):
        if source_id not in (pack.source_ids if isinstance(pack.source_ids, list) else []):
            continue
        pack.status = "stale"
        pack.uncertainty = {**(pack.uncertainty if isinstance(pack.uncertainty, dict) else {}), "level": "stale", "reason": "A selected source was deleted; recompile the curriculum."}
        pack.save(update_fields=["status", "uncertainty", "updated_at"])
        pack.versions.filter(status="active").update(status="stale")
        route = GoalCurriculumRoute.objects.filter(goal=notebook.goal).first()
        if route:
            route.state = "stale"
            route.invalid_reason = "A selected source was deleted; recompile the curriculum."
            route.save(update_fields=["state", "invalid_reason", "updated_at"])
        affected = True

    if affected:
        notebook.goal.next_action = "A source supporting recorded evidence was removed. Add a ready source and submit a fresh observable attempt."
        notebook.goal.save(update_fields=["next_action", "updated_at"])


class NotebookCreateView(APIView):
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        """List only notebooks that belong to the signed-in learner.

        The compact response supports universal "Add context" without
        serializing raw source text or chat history into the goal shell.
        """
        user = getattr(request, "user", None)
        profile = LearnerProfile.objects.filter(account=user).first() if user and getattr(user, "is_authenticated", False) else None
        if profile is None:
            return _error("Sign in to browse your source contexts.", "authentication_required", status.HTTP_401_UNAUTHORIZED)
        notebooks = Notebook.objects.filter(owner_profile=profile).order_by("-updated_at", "-id")
        return Response({"notebooks": [{
            "notebookId": str(notebook.notebook_id),
            "title": notebook.title,
            "status": notebook.status,
            "goalId": str(notebook.goal.goal_id) if notebook.goal_id else None,
            "courseId": str(notebook.course.course_id) if notebook.course_id else None,
            "sourceCount": notebook.notebook_sources.count(),
            "updatedAt": notebook.updated_at.isoformat(),
        } for notebook in notebooks]})

    def post(self, request):
        body = request.data
        title = _slug_title(str(body.get("title") or body.get("subject") or ""))
        if not title:
            return _error("Give your notebook a name before adding sources.", "missing_title")
        user = getattr(request, "user", None)
        owner_profile = LearnerProfile.objects.filter(account=user).first() if user and getattr(user, "is_authenticated", False) else None
        requested_goal_id = body.get("goalId")
        requested_course_id = body.get("courseId")
        if (requested_goal_id or requested_course_id) and owner_profile is None:
            return _error("Sign in before attaching context to a learning goal or course.", "authentication_required", status.HTTP_401_UNAUTHORIZED)

        goal = None
        if requested_goal_id:
            try:
                goal_uuid = uuid.UUID(str(requested_goal_id))
            except (TypeError, ValueError, AttributeError):
                return _error("goalId must identify one of your learning goals.", "invalid_goal")
            goal = LearningGoal.objects.filter(goal_id=goal_uuid, profile=owner_profile).first()
            if goal is None:
                return _error("Learning goal not found.", "not_found", status.HTTP_404_NOT_FOUND)

        course = goal.course if goal else None
        if requested_course_id:
            try:
                course_uuid = uuid.UUID(str(requested_course_id))
            except (TypeError, ValueError, AttributeError):
                return _error("courseId must identify a valid course.", "invalid_course")
            course = Course.objects.select_related("organization").filter(course_id=course_uuid).first()
            if course is None:
                return _error("Course not found.", "not_found", status.HTTP_404_NOT_FOUND)
            if goal is not None and goal.course_id != course.id:
                return _error(
                    "A goal-attached source context must use the same course as its learning goal.",
                    "course_goal_mismatch",
                )
            enrolled = Enrollment.objects.filter(course=course, profile=owner_profile, status="active").exists()
            manager = bool(
                course.instructor_id == getattr(user, "id", None)
                or Membership.objects.filter(
                    organization=course.organization,
                    user=user,
                    status="active",
                    role__in={"owner", "institution_admin"},
                ).exists()
            )
            if not (enrolled or manager):
                return _error("Join this course or use instructor access before attaching a source context.", "forbidden", status.HTTP_403_FORBIDDEN)
        notebook = Notebook.objects.create(
            title=title,
            subject=_slug_title(str(body.get("subject") or title)),
            description=str(body.get("description") or "").strip()[:2000],
            learning_goal=str(body.get("learningGoal") or "understand").strip()[:40],
            status="collecting",
            ocr_provider=str(body.get("ocrProvider") or "auto").strip()[:80],
            owner_profile=owner_profile,
            workspace=course.organization if course else (goal.workspace if goal else (owner_profile.workspace if owner_profile else None)),
            goal=goal,
            course=course,
        )
        return Response(notebook_payload(notebook), status=status.HTTP_201_CREATED)


class NotebookDetailView(APIView):
    def get(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return Response(notebook_payload(notebook))


class NotebookSourceUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
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
            grounding_enabled=_grounding_enabled(request.data.get("useForGrounding", request.data.get("groundingEnabled"))),
            extraction_method="pending",
        )
        try:
            blocks, assets, stats, method = extract_source(payload, metadata.mime_type, metadata.sha256, provider=provider)
        except NotebookExtractionError as exc:
            source.status = "failed"
            source.extraction_method = "failed"
            source.extraction = _failed_extraction_metadata(exc)
            source.save(update_fields=["status", "extraction_method", "extraction", "updated_at"])
            return _error(
                "Source extraction failed. Re-upload the file to retry.",
                "extraction_failed",
                extra={
                    "sourceId": source.source_id,
                    "retryable": True,
                    "retryAction": "reupload",
                    "providerErrorCategory": source.extraction["providerErrorCategory"],
                },
            )
        with transaction.atomic():
            source = NotebookSource.objects.select_for_update().get(pk=source.pk)
            notebook = Notebook.objects.select_for_update().get(pk=notebook.pk)
            source.status = "ready"
            source.extraction_method = method
            source.extraction = {"status": "complete", **stats, "rawRetention": "discarded_after_extraction"}
            source.blocks = blocks
            source.assets = assets
            source.save(update_fields=["status", "extraction_method", "extraction", "blocks", "assets", "updated_at"])
            notebook, _ = _refresh_notebook_memory(notebook, ocr_provider=method)
        return Response(notebook_payload(notebook), status=status.HTTP_201_CREATED)


class NotebookSourceRetryView(APIView):
    """Retry a failed/degraded OCR source with a newly selected file.

    Raw uploads are intentionally never stored on ``NotebookSource``.  A retry
    therefore cannot replay a hidden byte blob; the learner must select the
    source again and this endpoint re-runs extraction from that request only.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, notebook_id, source_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        source = notebook.notebook_sources.filter(source_id=source_id).first()
        if source is None:
            return _error("Source not found in this notebook.", "source_not_found", status.HTTP_404_NOT_FOUND)

        extraction = source.extraction if isinstance(source.extraction, dict) else {}
        degraded_local = source.extraction_method == "local-fallback-after-mistral-network-error"
        if source.status != "failed" and not degraded_local and not extraction.get("retryable"):
            return _error("This source has no failed provider extraction to retry.", "retry_not_available", status.HTTP_409_CONFLICT)

        uploaded_file = request.FILES.get("file") or request.FILES.get("source")
        if uploaded_file is None:
            return _error(
                "Choose the source file again to retry extraction. Raw uploads are not retained.",
                "source_reupload_required",
                status.HTTP_409_CONFLICT,
                extra={"sourceId": source.source_id, "retryable": True, "retryAction": "reupload"},
            )
        try:
            metadata, payload = inspect_uploaded_asset(uploaded_file, allowed_mime_types=NOTEBOOK_ALLOWED_MIME_TYPES)
        except IngestionError as exc:
            return _error(str(exc), "invalid_source")

        provider = str(request.data.get("ocrProvider") or notebook.ocr_provider or "auto").strip().lower()
        title = _slug_title(str(request.data.get("title") or source.title or metadata.filename))
        source_kind = str(request.data.get("sourceKind") or source.source_kind or "reference").strip()[:40]
        grounding_value = request.data.get("useForGrounding", request.data.get("groundingEnabled"))
        grounding_enabled = _grounding_enabled(grounding_value, source.grounding_enabled)

        # A successful re-upload changes the source content/anchors.  Invalidate
        # previous outputs before replacing it so stale evidence cannot be
        # presented as if it were grounded in the new extraction.
        with transaction.atomic():
            source = NotebookSource.objects.select_for_update().get(pk=source.pk)
            notebook = Notebook.objects.select_for_update().get(pk=notebook.pk)
            if source.blocks or source.assets or source.status == "ready":
                _invalidate_removed_source(notebook, source)
            source.title = title
            source.source_kind = source_kind
            source.filename = metadata.filename
            source.mime_type = metadata.mime_type
            source.size_bytes = metadata.size_bytes
            source.sha256 = metadata.sha256
            source.status = "extracting"
            source.grounding_enabled = grounding_enabled
            source.extraction_method = "pending"
            source.extraction = {
                "status": "extracting",
                "retryOf": source.source_id,
                "rawRetention": "discarded_after_extraction",
            }
            source.blocks = []
            source.assets = []
            source.save(update_fields=[
                "title", "source_kind", "filename", "mime_type", "size_bytes", "sha256", "status",
                "grounding_enabled", "extraction_method", "extraction", "blocks", "assets", "updated_at",
            ])
            notebook, _ = _refresh_notebook_memory(notebook)

        try:
            blocks, assets, stats, method = extract_source(payload, metadata.mime_type, metadata.sha256, provider=provider)
        except NotebookExtractionError as exc:
            source = NotebookSource.objects.get(pk=source.pk)
            source.status = "failed"
            source.extraction_method = "failed"
            source.extraction = _failed_extraction_metadata(exc)
            source.save(update_fields=["status", "extraction_method", "extraction", "updated_at"])
            return _error(
                "Source extraction failed. Re-upload the file to retry.",
                "extraction_failed",
                extra={
                    "sourceId": source.source_id,
                    "retryable": True,
                    "retryAction": "reupload",
                    "providerErrorCategory": source.extraction["providerErrorCategory"],
                },
            )

        with transaction.atomic():
            source = NotebookSource.objects.select_for_update().get(pk=source.pk)
            notebook = Notebook.objects.select_for_update().get(pk=notebook.pk)
            source.status = "ready"
            source.extraction_method = method
            source.extraction = {"status": "complete", **stats, "rawRetention": "discarded_after_extraction"}
            source.blocks = blocks
            source.assets = assets
            source.save(update_fields=["status", "extraction_method", "extraction", "blocks", "assets", "updated_at"])
            notebook, _ = _refresh_notebook_memory(notebook, ocr_provider=method)
        return Response(notebook_payload(notebook), status=status.HTTP_201_CREATED)


class NotebookTextSourceView(APIView):
    """Add text, webpages, or arXiv papers to notebook-scoped memory.

    A URL is fetched only for this explicit source-add action. HTML is reduced
    to readable text and arXiv ``/abs`` links are resolved to their PDF. Raw
    response bytes are held only for extraction and are never persisted.
    """

    parser_classes = [JSONParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        if not notebook.owner_profile_id:
            return _error("Sign in before adding universal source context.", "authentication_required", status.HTTP_401_UNAUTHORIZED)

        body = request.data if isinstance(request.data, dict) else {}
        source_kind = _text(body.get("sourceKind") or "pasted_notes", 40).casefold().replace(" ", "_")
        allowed_kinds = {"pasted_notes", "typed_text", "url_reference", "reference"}
        if source_kind not in allowed_kinds:
            return _error("sourceKind must be pasted_notes, typed_text, url_reference, or reference.", "invalid_source_kind")

        title = _slug_title(str(body.get("title") or ""))
        content = str(body.get("text") or body.get("content") or "").strip()[:120000]
        reference_url = _text(body.get("url") or body.get("referenceUrl") or "", 2000)
        raw_fetch_website = body.get("fetchWebsite")
        if raw_fetch_website is not None and not isinstance(raw_fetch_website, bool):
            return _error("fetchWebsite must be true or false.", "invalid_fetch_option")
        # Older trusted clients sent a URL without this new field. Preserve the
        # previous safe behavior for URL-only submissions while new clients make
        # their extraction intent explicit.
        fetch_website = bool(raw_fetch_website) if raw_fetch_website is not None else bool(reference_url and not content)
        if reference_url:
            parsed = urlparse(reference_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return _error("Reference URLs must start with http:// or https://.", "invalid_reference_url")
        if not content and not reference_url:
            return _error("Paste source text or provide a reference URL.", "missing_source_content")

        fetched = None
        if reference_url and fetch_website:
            try:
                fetched = fetch_reference(reference_url)
            except WebSourceError as exc:
                return _error(str(exc), "source_fetch_failed", status.HTTP_422_UNPROCESSABLE_ENTITY)
            title = title or fetched.title
            payload = fetched.payload
            extraction_mime = fetched.extraction_mime
            original_mime = fetched.original_mime
            source_kind = fetched.source_kind
        elif reference_url and content:
            content = f"{content}\n\nReference URL: {reference_url}"
            payload = content.encode("utf-8")
            extraction_mime = "text/markdown"
            original_mime = "text/markdown"
        elif content:
            payload = content.encode("utf-8")
            extraction_mime = "text/markdown"
            original_mime = "text/markdown"
        else:
            return _error("Enable bounded webpage extraction or paste source text with this URL.", "source_fetch_required")
        if not title:
            title = _slug_title(content.splitlines()[0] if content else urlparse(reference_url).netloc) or "Fetched source" if fetched else "Pasted source"
        digest = hashlib.sha256(payload).hexdigest()
        try:
            provider = str(body.get("ocrProvider") or notebook.ocr_provider or "auto").strip().lower() if fetched and extraction_mime == "application/pdf" else "local"
            blocks, assets, stats, method = extract_source(payload, extraction_mime, digest, provider=provider)
        except NotebookExtractionError as exc:
            return _error(str(exc), "extraction_failed")
        # A fetched HTML page is normalized to Markdown before text extraction.
        # Its bounded, public visuals are then attached as notebook assets with
        # the same stable source anchors as uploaded PDF visuals.  We persist
        # neither raw HTML nor a remote image URL, only approved image data.
        if fetched and fetched.assets:
            for index, web_asset in enumerate(fetched.assets, start=1):
                data_url = str(web_asset.get("dataUrl") or "")
                if not data_url.startswith("data:image/"):
                    continue
                asset_id = f"asset_{digest[:12]}_web_{index:02d}"
                anchor = f"{digest[:12]}:web:img{index}"
                assets.append({
                    "assetId": asset_id,
                    "type": "image",
                    "mimeType": str(web_asset.get("mimeType") or "image/png"),
                    "page": 1,
                    "alt": str(web_asset.get("alt") or "Webpage visual"),
                    "dataUrl": data_url,
                })
                blocks.append({
                    "blockId": f"block_{digest[:10]}_web_image_{index:02d}",
                    "type": "image",
                    "markdown": f"[Source visual: {str(web_asset.get('alt') or 'Webpage visual')}]",
                    "page": 1,
                    "assetId": asset_id,
                    "sourceAnchor": anchor,
                })
            stats = {**stats, "assetCount": len(assets), "webVisualCount": len(fetched.assets), "blockCount": len(blocks)}

        with transaction.atomic():
            notebook = Notebook.objects.select_for_update().get(pk=notebook.pk)
            source = NotebookSource.objects.create(
                notebook=notebook,
                source_id=f"nbsrc_{uuid.uuid4().hex}",
                title=title,
                source_kind=source_kind,
                filename=(urlparse(fetched.final_url).path.rsplit("/", 1)[-1] if fetched else ""),
                mime_type=original_mime,
                size_bytes=len(payload),
                sha256=digest,
                status="ready",
                grounding_enabled=_grounding_enabled(body.get("useForGrounding", body.get("groundingEnabled"))),
                extraction_method=f"typed_{method}",
                extraction={
                    "status": "complete",
                    **stats,
                    "referenceUrl": reference_url or None,
                    "fetchedUrl": fetched.final_url if fetched else None,
                    "fetchedContentType": fetched.original_mime if fetched else None,
                    "fetchedBytes": fetched.fetched_bytes if fetched else None,
                    "fetchWebsite": bool(fetched),
                    "webMetadata": fetched.metadata if fetched else {},
                    "rawRetention": "discarded_after_extraction",
                },
                blocks=blocks,
                assets=assets,
            )
            notebook, _ = _refresh_notebook_memory(notebook, ocr_provider=f"fetched_{method}" if fetched else f"typed_{method}")
        del source
        return Response(notebook_payload(notebook), status=status.HTTP_201_CREATED)


class NotebookBlankNoteView(APIView):
    """Create a private blank note without pretending it is source evidence."""

    parser_classes = [JSONParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        if not notebook.owner_profile_id:
            return _error("Sign in before adding a personal note.", "authentication_required", status.HTTP_401_UNAUTHORIZED)
        title = _slug_title(str((request.data or {}).get("title") or "Personal note")) or "Personal note"
        note = NotebookNote.objects.create(notebook=notebook, title=title, content="")
        return Response(_note_payload(note), status=status.HTTP_201_CREATED)


class NotebookSourceDetailView(APIView):
    def delete(self, request, notebook_id, source_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        source = notebook.notebook_sources.filter(source_id=source_id).first()
        if source is None:
            return _error("Source not found in this notebook.", "source_not_found", status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            notebook = Notebook.objects.select_for_update().get(pk=notebook.pk)
            _invalidate_removed_source(notebook, source)
            source.delete()
            notebook, _ = _refresh_notebook_memory(notebook)
        return Response(notebook_payload(notebook))


class NotebookArtifactView(APIView):
    parser_classes = [JSONParser]
    supported_types = {"summary", "mcq", "slides", "formula_sheet", "important_questions", "flashcards", "mind_map", "data_table"}

    def get(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return Response({"artifacts": notebook_payload(notebook)["artifacts"]})

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        artifact_type = str(request.data.get("type") or "").strip().lower()
        if artifact_type not in self.supported_types:
            return _error("Choose a supported notebook output.", "unsupported_artifact")
        try:
            pack, selected_source_ids = _scoped_pack(notebook, request.data)
            title, payload = generate_notebook_artifact(pack, artifact_type)
        except ProviderUnavailable as exc:
            record_provider_failure("fireworks", notebook_provider_error_category(exc))
            return _error(
                "The configured Fireworks provider is unavailable. No local artifact was created; retry when the provider is ready.",
                "provider_unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                extra={
                    "provider": "fireworks",
                    "providerStatus": "unavailable",
                    "providerErrorCategory": notebook_provider_error_category(exc),
                    "retryAvailable": True,
                    "retryAction": "generate_artifact",
                },
            )
        except ProviderOutputError as exc:
            record_provider_failure("fireworks", notebook_provider_error_category(exc))
            return _error(
                "Fireworks returned an invalid source-grounded artifact. No artifact was saved; retry the provider.",
                "artifact_generation_failed",
                status.HTTP_502_BAD_GATEWAY,
                extra={
                    "provider": "fireworks",
                    "providerStatus": "invalid_response",
                    "providerErrorCategory": notebook_provider_error_category(exc),
                    "retryAvailable": True,
                    "retryAction": "generate_artifact",
                },
            )
        except ValueError as exc:
            return _error(str(exc), "artifact_failed")
        artifact = NotebookArtifact.objects.create(
            notebook=notebook,
            artifact_type=artifact_type,
            title=title,
            payload=payload,
            source_ids=selected_source_ids,
        )
        return Response(_artifact_payload(artifact), status=status.HTTP_201_CREATED)


class NotebookChatHistoryView(APIView):
    def get(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return Response({"messages": [_chat_message_payload(message) for message in notebook.chat_messages.all()]})


class NotebookAskView(APIView):
    parser_classes = [JSONParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        question = _text(request.data.get("question"), 800)
        if not question:
            return _error("Ask a question about this notebook.", "missing_question")
        domain = notebook.goal.domain if notebook.goal_id else ""
        boundary = personal_decision_boundary(domain, question)
        if boundary:
            selected_source_ids: list[str] = []
            result = {
                "answer": boundary,
                "sourceIds": [],
                "sourceAnchorIds": [],
                "groundedIn": "educational_boundary",
                "safetyBoundary": True,
            }
        else:
            try:
                pack, selected_source_ids = _scoped_pack(notebook, request.data)
            except ValueError as exc:
                return _error(str(exc), "invalid_source_scope")
            try:
                # Uploaded source memory is the only default context. Web research
                # stays separate and is never silently written into this notebook.
                result = answer_notebook_question(pack, question, allow_web_search=False)
            except Exception as exc:
                return _error(f"Notebook copilot failed: {exc}", "copilot_failed", status.HTTP_502_BAD_GATEWAY)
        answer_source_ids = [item for item in result.get("sourceIds") or selected_source_ids if item in selected_source_ids]
        provider_error_category = str(result.get("providerErrorCategory") or "")[:64]
        if result.get("providerUnavailable"):
            assistant_status = "provider_unavailable"
        elif result.get("citationValidationFailed"):
            assistant_status = "citation_validation_failed"
        elif result.get("providerOutputInvalid"):
            assistant_status = "provider_output_invalid"
        else:
            assistant_status = "ready"
        with transaction.atomic():
            user_message = NotebookChatMessage.objects.create(
                notebook=notebook,
                role="user",
                content=question,
                source_ids=selected_source_ids,
            )
            assistant_message = NotebookChatMessage.objects.create(
                notebook=notebook,
                role="assistant",
                content=str(result.get("answer") or "I could not form a source-grounded answer."),
                source_ids=answer_source_ids,
                source_anchor_ids=result.get("sourceAnchorIds") or [],
                grounded_in=str(result.get("groundedIn") or "notebook"),
                status=assistant_status,
                provider_name=str(result.get("provider") or "")[:80],
                provider_model=str(result.get("model") or "")[:200],
                provider_error_category=provider_error_category,
            )
        return Response({
            **result,
            "sourceIds": answer_source_ids,
            "webSources": [],
            "messages": {"user": _chat_message_payload(user_message), "assistant": _chat_message_payload(assistant_message)},
        })


class NotebookNotesView(APIView):
    parser_classes = [JSONParser]

    def get(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        return Response({"notes": [_note_payload(note) for note in notebook.notes.all()]})

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        content = str(request.data.get("content") or "").strip()[:12000]
        if not content:
            return _error("Write a note before saving it.", "missing_note_content")
        try:
            pack, selected_source_ids = _scoped_pack(notebook, request.data) if "sourceIds" in request.data else ({}, [])
        except ValueError as exc:
            return _error(str(exc), "invalid_source_scope")
        del pack
        anchors = request.data.get("sourceAnchorIds") or []
        if not isinstance(anchors, list):
            return _error("sourceAnchorIds must be an array when provided.", "invalid_note_anchors")
        note = NotebookNote.objects.create(
            notebook=notebook,
            title=_slug_title(str(request.data.get("title") or content.splitlines()[0] or "Untitled note")) or "Untitled note",
            content=content,
            source_ids=selected_source_ids,
            source_anchor_ids=list(dict.fromkeys(str(item).strip() for item in anchors if str(item).strip()))[:40],
        )
        return Response(_note_payload(note), status=status.HTTP_201_CREATED)


class NotebookNoteDetailView(APIView):
    parser_classes = [JSONParser]

    def _note(self, request, notebook_id, note_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return None, _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        note = notebook.notes.filter(note_id=note_id).first()
        if note is None:
            return None, _error("Note not found in this notebook.", "note_not_found", status.HTTP_404_NOT_FOUND)
        return note, None

    def patch(self, request, notebook_id, note_id):
        note, error = self._note(request, notebook_id, note_id)
        if error:
            return error
        changes: list[str] = []
        if "title" in request.data:
            title = _slug_title(str(request.data.get("title") or ""))
            if not title:
                return _error("A note title cannot be blank.", "missing_note_title")
            note.title = title
            changes.append("title")
        if "content" in request.data:
            content = str(request.data.get("content") or "").strip()[:12000]
            if not content:
                return _error("A note cannot be blank.", "missing_note_content")
            note.content = content
            changes.append("content")
        if not changes:
            return _error("Provide a title or note content to update.", "missing_note_update")
        note.save(update_fields=[*changes, "updated_at"])
        return Response(_note_payload(note))

    def delete(self, request, notebook_id, note_id):
        note, error = self._note(request, notebook_id, note_id)
        if error:
            return error
        note.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotebookLessonView(APIView):
    """Create and persist a narrated lesson from selected notebook memory."""

    parser_classes = [JSONParser]

    def post(self, request, notebook_id):
        notebook = _notebook(notebook_id, request)
        if notebook is None:
            return _error("Notebook not found.", "not_found", status.HTTP_404_NOT_FOUND)
        body = request.data if isinstance(request.data, dict) else {}
        question = _text(body.get("question") or "Create a guided lesson from this notebook.", 800)
        boundary = personal_decision_boundary(notebook.goal.domain if notebook.goal_id else "", question)
        if boundary:
            return _error(boundary, "educational_boundary")
        try:
            duration = int(body.get("requestedDurationSeconds") or 120)
        except (TypeError, ValueError):
            return _error("requestedDurationSeconds must be between 60 and 300.", "invalid_duration")
        if not 60 <= duration <= 300:
            return _error("requestedDurationSeconds must be between 60 and 300.", "invalid_duration")
        try:
            pack, selected_source_ids = _scoped_pack(notebook, body)
            payload = generate_openmaic_lesson(pack, question, allow_web_search=False, requested_duration=duration)
        except ProviderUnavailable as exc:
            record_provider_failure("fireworks", notebook_provider_error_category(exc))
            return _error(
                "The configured Fireworks provider is unavailable. No local narrated lesson was created; retry when the provider is ready.",
                "provider_unavailable",
                status.HTTP_503_SERVICE_UNAVAILABLE,
                extra={
                    "provider": "fireworks",
                    "providerStatus": "unavailable",
                    "providerErrorCategory": notebook_provider_error_category(exc),
                    "retryAvailable": True,
                    "retryAction": "generate_lesson",
                },
            )
        except ProviderOutputError as exc:
            record_provider_failure("fireworks", notebook_provider_error_category(exc))
            return _error(
                "Fireworks returned an invalid source-grounded narrated lesson. No lesson was saved; retry the provider.",
                "lesson_generation_failed",
                status.HTTP_502_BAD_GATEWAY,
                extra={
                    "provider": "fireworks",
                    "providerStatus": "invalid_response",
                    "providerErrorCategory": notebook_provider_error_category(exc),
                    "retryAvailable": True,
                    "retryAction": "generate_lesson",
                },
            )
        except ValueError as exc:
            return _error(str(exc), "invalid_source_scope")
        artifact = NotebookArtifact.objects.create(
            notebook=notebook,
            artifact_type="openmaic_lesson",
            title=str(payload.get("title") or "Narrated study lesson"),
            payload=payload,
            source_ids=selected_source_ids,
        )
        return Response(_artifact_payload(artifact), status=status.HTTP_201_CREATED)
