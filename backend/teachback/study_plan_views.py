"""Source-bounded study-plan generation for the live study desk.

Uploaded material remains a reviewable candidate source. Live providers may
draft a module from those candidates, but the response is labeled as a draft
until an instructor approves the source pack.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .providers import CHAT_ACTION_TYPES, LEARNING_MODE_IDS, ModuleChatRequest, ProviderOutputError, ProviderUnavailable, StudyPlanRequest, provider_for
from .models import StudySource


def _error(message: str, code: str = "invalid_request", http_status: int = 422):
    return Response({"error": {"code": code, "message": message}}, status=http_status)


def _dsap_source_pack() -> dict:
    path = settings.BASE_DIR.parent / "contracts" / "v2" / "source-pack.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sourcePackId": "dsap-sampling-v1", "version": "unknown", "spans": []}


def _source_context(source_ids: list[str]) -> tuple[list[dict], set[str], str, bool]:
    """Resolve browser IDs to server-owned source candidates and anchors."""
    if source_ids == ["dsap-sampling-v1"]:
        pack = _dsap_source_pack()
        spans = [{"sourceId": "dsap-sampling-v1", **span} for span in pack.get("spans", [])]
        anchors = {str(span.get("spanId")) for span in spans if span.get("spanId")}
        return spans, anchors, str(pack.get("sourcePackId", "dsap-sampling-v1")), pack.get("approvalStatus") != "approved"
    records = list(StudySource.objects.filter(source_id__in=source_ids))
    by_id = {record.source_id: record for record in records}
    if len(by_id) != len(set(source_ids)):
        missing = [source_id for source_id in source_ids if source_id not in by_id]
        raise ProviderOutputError(f"unknown source IDs: {', '.join(missing)}")
    spans: list[dict] = []
    review_required = False
    versions: list[str] = []
    for source_id in source_ids:
        record = by_id[source_id]
        review_required = review_required or record.approval_status != "approved"
        versions.append(record.sha256[:12] or record.source_id[:12])
        spans.extend({"sourceId": source_id, **candidate} for candidate in (record.candidates or []))
    anchors = {str(span.get("candidateId")) for span in spans if span.get("candidateId")}
    return spans, anchors, "uploaded-draft-" + "-".join(versions[:4]), review_required


def _validate_manifest(plan: dict, allowed_anchors: set[str]) -> None:
    """Reject the dangerous part of a model result before it reaches a UI."""
    if not isinstance(plan, dict):
        raise ProviderOutputError("study plan must be an object")
    required = {"studyPlanId", "sourceIds", "chapterSelection", "providerMode", "sourcePackVersion", "recordVersion", "outline", "scenes"}
    if not required.issubset(plan):
        raise ProviderOutputError("study plan is missing required fields")
    if plan["chapterSelection"] not in {"chapter_1", "all"}:
        raise ProviderOutputError("unsupported chapter selection")
    if plan["providerMode"] not in {"codex_fixture", "live_openai", "live_fireworks", "human_review"}:
        raise ProviderOutputError("unsupported provider mode")
    if not isinstance(plan["outline"], list) or not isinstance(plan["scenes"], list):
        raise ProviderOutputError("outline and scenes must be arrays")
    for item in [*plan["outline"], *plan["scenes"]]:
        for anchor_id in item.get("sourceAnchorIds", []):
            if anchor_id not in allowed_anchors:
                raise ProviderOutputError("study plan contains an unapproved source anchor")
        for action in item.get("actions", []):
            if action.get("kind") not in {"reveal", "spotlight", "draw", "write", "equation", "pause"}:
                raise ProviderOutputError("study plan contains an unsupported action")
    if plan["providerMode"] in {"live_openai", "live_fireworks"}:
        scene_types = {str(scene.get("type")) for scene in plan["scenes"]}
        # A module needs an explain-and-respond loop to be useful. Exam practice
        # is intentionally optional: it can be requested later from the module
        # copilot instead of causing an otherwise complete live module to fail.
        required_types = {"whiteboard", "predict_checkpoint", "retrieval", "teach_back"}
        missing_types = sorted(required_types - scene_types)
        if missing_types:
            raise ProviderOutputError(f"live study module is missing required learning scenes: {', '.join(missing_types)}")
        for scene in plan["scenes"]:
            if not isinstance(scene.get("sourceAnchorIds"), list) or not scene.get("sourceAnchorIds"):
                raise ProviderOutputError("live study scene is missing approved source evidence")
            if not isinstance(scene.get("explanation"), str) or len(scene["explanation"].strip()) < 20:
                raise ProviderOutputError("live study scene is missing a learner-facing explanation")
            if not isinstance(scene.get("actions"), list) or len(scene["actions"]) < 1:
                raise ProviderOutputError("live study scene is missing whiteboard actions")
            if scene.get("type") in {"predict_checkpoint", "retrieval", "teach_back", "exam_bridge"} and not isinstance(scene.get("checkpoint"), dict):
                raise ProviderOutputError("live interactive scene is missing its checkpoint")
        for outline in plan["outline"]:
            if not isinstance(outline.get("sourceAnchorIds"), list) or not outline.get("sourceAnchorIds"):
                raise ProviderOutputError("live study concept is missing approved source evidence")


@method_decorator(csrf_exempt, name="dispatch")
class StudyPlanView(APIView):
    """POST a bounded plan request; browser text/source quotes are not accepted."""

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        forbidden = {"sourceText", "source_text", "prompt", "systemPrompt", "html", "rawDocument"}
        if forbidden.intersection(body):
            return _error("send source IDs only; source text and generated HTML are not accepted", "source_boundary_violation")
        subject_id = str(body.get("subjectId") or "dsap").strip()
        module_id = str(body.get("moduleId") or "sampling-aliasing").strip() or None
        chapter_selection = str(body.get("chapterSelection") or "chapter_1").strip()
        if chapter_selection not in {"chapter_1", "all"}:
            return _error("chapterSelection must be chapter_1 or all")
        source_ids = body.get("sourceIds") or ["dsap-sampling-v1"]
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 20 or any(not isinstance(item, str) or not item.strip() for item in source_ids):
            return _error("sourceIds must be a non-empty list of IDs")
        source_ids = [item.strip() for item in source_ids]
        provider_mode = str(body.get("provider") or body.get("providerMode") or settings.LLM_PROVIDER).strip().lower()
        provider_aliases = {"fireworks": "fireworks", "live_fireworks": "fireworks", "qwen": "fireworks", "openai": "openai", "live_openai": "openai", "fixture": "fixture", "codex_fixture": "fixture"}
        if provider_mode not in provider_aliases:
            return _error("provider must be fireworks, openai, or fixture")
        try:
            source_spans, allowed_anchors, source_pack_version, review_required = _source_context(source_ids)
            if not source_spans:
                return Response({"state": "needs_human_review", "reasonCode": "source_extraction_pending", "providerMode": "human_review", "sourceIds": source_ids, "chapterSelection": chapter_selection, "sourcePackVersion": source_pack_version, "recordVersion": 1, "reviewRequired": True}, status=status.HTTP_200_OK)
            provider = provider_for(provider_aliases[provider_mode])
            plan = provider.generate_study_plan(StudyPlanRequest(subject_id, module_id, source_ids, chapter_selection, sorted(allowed_anchors), source_spans=source_spans, subject_title=str(body.get("subjectTitle") or subject_id)))
            # Human-review plans are a safe terminal state for unapproved uploads.
            if plan.get("state") == "needs_human_review":
                return Response({**plan, "sourcePackVersion": source_pack_version, "recordVersion": 1, "reviewRequired": True}, status=status.HTTP_200_OK)
            _validate_manifest(plan, allowed_anchors)
            if not set(plan.get("sourceIds", [])).issubset(set(source_ids)):
                raise ProviderOutputError("study plan returned an unrequested source ID")
            plan["sourcePackVersion"] = source_pack_version
            plan["reviewRequired"] = review_required
            return Response(plan, status=status.HTTP_200_OK)
        except ProviderUnavailable as exc:
            return _error(str(exc), "provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        except ProviderOutputError as exc:
            return _error(str(exc), "needs_human_review")


@method_decorator(csrf_exempt, name="dispatch")
class StudyPlanInteractionView(APIView):
    """Evaluate one generated scene without accepting browser-owned evidence."""

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        source_ids = body.get("sourceIds")
        scene = body.get("scene")
        response_text = body.get("response", "")
        kind = str(body.get("kind") or "teach_back").strip()
        if kind not in {"predict", "retrieval", "teach_back", "exam_bridge"}:
            return _error("kind must be predict, retrieval, teach_back, or exam_bridge")
        if not isinstance(source_ids, list) or not source_ids or any(not isinstance(item, str) or not item.strip() for item in source_ids):
            return _error("sourceIds must be a non-empty list of IDs")
        if not isinstance(scene, dict):
            return _error("scene is required")
        if not isinstance(response_text, str) or not response_text.strip() or len(response_text) > 12000:
            return _error("response must be a non-empty string up to 12000 characters")
        scene_anchors = scene.get("sourceAnchorIds")
        if not isinstance(scene_anchors, list) or not scene_anchors or any(not isinstance(item, str) for item in scene_anchors):
            return _error("scene.sourceAnchorIds must be a non-empty list")
        provider_mode = str(body.get("provider") or settings.LLM_PROVIDER).strip().lower()
        provider_aliases = {"fireworks": "fireworks", "live_fireworks": "fireworks", "qwen": "fireworks", "openai": "openai", "live_openai": "openai", "fixture": "fixture", "codex_fixture": "fixture"}
        if provider_mode not in provider_aliases:
            return _error("provider must be fireworks, openai, or fixture")
        try:
            source_spans, allowed_anchors, source_pack_version, review_required = _source_context([item.strip() for item in source_ids])
            if not set(scene_anchors).issubset(allowed_anchors):
                return _error("scene contains an unapproved source anchor", "source_boundary_violation")
            provider = provider_for(provider_aliases[provider_mode])
            manifest = {
                "sceneId": str(scene.get("sceneId") or "generated-scene"),
                "prompt": str(scene.get("prompt") or scene.get("explanation") or "Explain your reasoning."),
                "responseType": str(scene.get("responseType") or "long_text"),
                "sourceAnchorIds": sorted(set(scene_anchors)),
                "sourceSpans": source_spans,
            }
            provider_request = {
                "kind": kind,
                "manifest": manifest,
                "prediction": response_text if kind == "predict" else "",
                "explanation": response_text if kind != "predict" else "",
            }
            result = provider.evaluate_checkpoint(provider_request)
            result.update({
                "sourcePackVersion": source_pack_version,
                "recordVersion": 1,
                "reviewRequired": review_required,
                "providerMode": getattr(provider, "mode", "human_review"),
            })
            return Response(result)
        except ProviderUnavailable as exc:
            return _error(str(exc), "provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        except ProviderOutputError as exc:
            return _error(str(exc), "needs_human_review")


@method_decorator(csrf_exempt, name="dispatch")
class StudyPlanChatView(APIView):
    """Contextual module copilot: answers from source spans and returns typed UI actions."""

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        forbidden = {"sourceText", "source_text", "sourceQuotes", "rawDocument", "systemPrompt", "html", "script"}
        if forbidden.intersection(body):
            return _error("send source IDs and module metadata only; source text and executable content are not accepted", "source_boundary_violation")
        message = body.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            return _error("message must be a non-empty string up to 4000 characters")
        source_ids = body.get("sourceIds")
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 20 or any(not isinstance(item, str) or not item.strip() for item in source_ids):
            return _error("sourceIds must be a non-empty list of IDs")
        provider_mode = str(body.get("provider") or settings.LLM_PROVIDER).strip().lower()
        provider_aliases = {"fireworks": "fireworks", "live_fireworks": "fireworks", "qwen": "fireworks", "openai": "openai", "live_openai": "openai", "fixture": "fixture", "codex_fixture": "fixture"}
        if provider_mode not in provider_aliases:
            return _error("provider must be fireworks, openai, or fixture")
        raw_scenes = body.get("scenes")
        if not isinstance(raw_scenes, list) or not raw_scenes or len(raw_scenes) > 40:
            return _error("scenes must be a non-empty list")
        scenes = []
        for raw_scene in raw_scenes:
            if not isinstance(raw_scene, dict) or not isinstance(raw_scene.get("sceneId"), str) or not raw_scene.get("sceneId"):
                return _error("each scene must include a sceneId")
            scenes.append({
                "sceneId": raw_scene["sceneId"][:120],
                "title": str(raw_scene.get("title") or "Learning scene")[:240],
                "type": str(raw_scene.get("type") or "whiteboard")[:40],
                "hasVisualization": bool(raw_scene.get("hasVisualization")),
                "hasCheckpoint": bool(raw_scene.get("hasCheckpoint")),
            })
        scene_ids = {scene["sceneId"] for scene in scenes}
        active_scene_id = body.get("activeSceneId")
        if active_scene_id is not None and (not isinstance(active_scene_id, str) or active_scene_id not in scene_ids):
            return _error("activeSceneId must belong to the supplied module scenes")
        try:
            active_scene_index = int(body.get("activeSceneIndex") or 0)
        except (TypeError, ValueError):
            return _error("activeSceneIndex must be an integer")
        if active_scene_index < 0 or active_scene_index >= len(scenes):
            return _error("activeSceneIndex is outside the module scene range")
        history = body.get("history") or []
        if not isinstance(history, list) or len(history) > 12:
            return _error("history must contain at most 12 messages")
        bounded_history = []
        for item in history:
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"} or not isinstance(item.get("content"), str):
                return _error("history messages must contain role and content")
            bounded_history.append({"role": item["role"], "content": item["content"][:2000]})
        learning_mode = str(body.get("learningMode") or "self_explain")
        if learning_mode not in LEARNING_MODE_IDS:
            return _error("learningMode is not a supported learning mode")
        try:
            source_spans, allowed_anchors, source_pack_version, review_required = _source_context([item.strip() for item in source_ids])
            if not source_spans:
                return Response({"state": "needs_human_review", "reply": "The source extraction is not ready yet.", "reasonCode": "source_extraction_pending", "sourceAnchorIds": [], "action": {"kind": "none", "sceneId": None, "modeId": None, "reason": "source_extraction_pending"}, "providerMode": "human_review", "sourcePackVersion": source_pack_version, "recordVersion": 1, "reviewRequired": True})
            provider = provider_for(provider_aliases[provider_mode])
            result = provider.chat(ModuleChatRequest(
                subject_id=str(body.get("subjectId") or "study"),
                module_id=str(body.get("moduleId") or "") or None,
                subject_title=str(body.get("subjectTitle") or body.get("subjectId") or "Study module")[:240],
                source_ids=[item.strip() for item in source_ids],
                approved_source_ids=sorted(allowed_anchors),
                source_spans=source_spans,
                message=message.strip(),
                history=bounded_history,
                active_scene_id=active_scene_id,
                active_scene_index=active_scene_index,
                scenes=scenes,
                learning_mode=learning_mode,
            ))
            if not isinstance(result, dict) or result.get("state") not in {"answered", "abstained", "needs_human_review", "action_only"}:
                raise ProviderOutputError("chat returned an invalid state")
            if not isinstance(result.get("reply"), str):
                raise ProviderOutputError("chat returned no learner-facing reply")
            if result.get("state") in {"answered", "action_only"} and len(result["reply"].strip()) < 8:
                raise ProviderOutputError("chat returned an incomplete learner-facing reply")
            if result.get("state") == "needs_human_review" and len(result["reply"].strip()) < 8:
                result["reply"] = "The live provider did not return a complete answer. Try again or request instructor review."
            anchors = result.get("sourceAnchorIds") or []
            if not isinstance(anchors, list) or not set(anchors).issubset(allowed_anchors):
                raise ProviderOutputError("chat returned an unapproved source anchor")
            action = result.get("action") if isinstance(result.get("action"), dict) else {}
            action_kind = str(action.get("kind") or "none")
            if action_kind not in CHAT_ACTION_TYPES:
                raise ProviderOutputError("chat returned an unsupported module action")
            action_scene_id = action.get("sceneId")
            if action_scene_id is not None and action_scene_id not in scene_ids:
                raise ProviderOutputError("chat action targeted an unknown scene")
            action_mode_id = action.get("modeId")
            if action_mode_id is not None and action_mode_id not in LEARNING_MODE_IDS:
                raise ProviderOutputError("chat action targeted an unsupported learning mode")
            if action_kind == "set_learning_mode" and action_mode_id is None:
                raise ProviderOutputError("chat learning-mode action is missing modeId")
            if action_kind == "none":
                action_scene_id = None
                action_mode_id = None
                if result.get("state") == "action_only":
                    result["state"] = "answered"
            if action_kind == "show_visualization":
                target = next((scene for scene in scenes if scene["sceneId"] == action_scene_id), None)
                if not target or not target["hasVisualization"]:
                    raise ProviderOutputError("chat requested an unavailable visualization")
            if result.get("state") == "answered" and not anchors:
                raise ProviderOutputError("answered chat response is missing approved source evidence")
            result.update({"providerMode": getattr(provider, "mode", "human_review"), "sourcePackVersion": source_pack_version, "recordVersion": 1, "reviewRequired": review_required, "sourceAnchorIds": sorted(set(anchors)), "action": {"kind": action_kind, "sceneId": action_scene_id, "modeId": action_mode_id, "reason": str(action.get("reason") or "")[:240]}})
            return Response(result)
        except ProviderUnavailable as exc:
            return _error(str(exc), "provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        except ProviderOutputError as exc:
            return _error(str(exc), "needs_human_review")


@method_decorator(csrf_exempt, name="dispatch")
class ProviderStatusView(APIView):
    """Expose provider availability without exposing credentials."""

    def get(self, request):
        return Response({
            "providers": [
                {"id": "fireworks", "label": "Qwen3 P7 Plus / Fireworks", "available": bool(settings.FIREWORKS_API_KEY), "model": settings.FIREWORKS_MODEL},
                {"id": "openai", "label": "OpenAI", "available": bool(settings.OPENAI_API_KEY), "model": settings.OPENAI_MODEL},
                {"id": "fixture", "label": "Local fixture", "available": True, "model": "fixture-v1"},
            ],
            "defaultProvider": settings.LLM_PROVIDER,
        })
