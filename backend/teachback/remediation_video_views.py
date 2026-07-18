"""Server-side remediation lesson generation."""
from __future__ import annotations

import base64
import json
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .providers import ProviderOutputError, ProviderUnavailable, provider_for
from .study_plan_views import _error, _source_context


def _bounded_text(body: dict, name: str, limit: int, required: bool = True) -> str:
    value = body.get(name, "")
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{name} is required")
    if len(value) > limit:
        raise ValueError(f"{name} must be no longer than {limit} characters")
    return value


def _approved_source_context(spans: list[dict], anchor_ids: list[str]) -> str:
    wanted = set(anchor_ids)
    selected = [span for span in spans if str(span.get("spanId") or span.get("candidateId")) in wanted]
    if not selected:
        selected = spans[:4]
    lines = []
    for span in selected[:8]:
        anchor = str(span.get("spanId") or span.get("candidateId") or "source-span")
        text = str(span.get("text") or span.get("content") or "").strip()
        if text:
            lines.append(f"[{anchor}] {text[:1800]}")
    return "\n\n".join(lines)[:12000]


def _validate_slide_manifest(manifest: dict, allowed_anchors: set[str], fallback_anchors: list[str] | None = None) -> list[dict]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("slides"), list):
        raise ProviderOutputError("Fireworks returned no slide lesson")
    slides = manifest["slides"]
    if not 1 <= len(slides) <= 8:
        raise ProviderOutputError("Fireworks slide lesson must contain at least one slide and no more than 8 slides")
    cleaned: list[dict] = []
    for index, slide in enumerate(slides):
        if not isinstance(slide, dict):
            raise ProviderOutputError("Fireworks returned an invalid remediation slide")
        anchors = slide.get("sourceAnchorIds") if isinstance(slide.get("sourceAnchorIds"), list) else []
        # The model can describe the lesson, but it does not own provenance.
        # Rebind every slide to the already-validated topic anchors. This keeps
        # a malformed/hallucinated model anchor from aborting an otherwise safe
        # remediation lesson and prevents it from becoming runtime evidence.
        topic_anchors = sorted({str(anchor) for anchor in (fallback_anchors or []) if str(anchor) in allowed_anchors})
        valid_anchors = sorted({str(anchor) for anchor in anchors if str(anchor) in allowed_anchors and (not topic_anchors or str(anchor) in topic_anchors)})
        if not valid_anchors:
            valid_anchors = topic_anchors or sorted(allowed_anchors)[:3]
        if not valid_anchors:
            raise ProviderOutputError("remediation slide has no approved source anchor available")
        title = str(slide.get("title") or "").strip()
        body = str(slide.get("body") or "").strip()
        narration = str(slide.get("narration") or "").strip()
        bullets = slide.get("bullets")
        diagram = slide.get("diagram") if isinstance(slide.get("diagram"), dict) else {"nodes": [], "edges": []}
        if not title or not body or not narration or not isinstance(bullets, list) or not bullets:
            raise ProviderOutputError("remediation slide is missing learner-facing content")
        nodes = diagram.get("nodes") if isinstance(diagram.get("nodes"), list) else []
        edges = diagram.get("edges") if isinstance(diagram.get("edges"), list) else []
        node_ids = {str(node.get("id")) for node in nodes if isinstance(node, dict) and node.get("id")}
        safe_edges = [edge for edge in edges if isinstance(edge, dict) and str(edge.get("from")) in node_ids and str(edge.get("to")) in node_ids]
        cleaned.append({
            "index": index,
            "title": title[:160],
            "body": body[:900],
            "bullets": [str(item).strip()[:220] for item in bullets[:5] if str(item).strip()],
            "narration": narration[:1400],
            "sourceAnchorIds": valid_anchors,
            "diagram": {
                "nodes": [{"id": str(node.get("id"))[:40], "label": str(node.get("label") or node.get("id"))[:100]} for node in nodes[:8] if isinstance(node, dict) and node.get("id")],
                "edges": safe_edges[:12],
            },
        })
    return cleaned


def _complete_slide_lesson(slides: list[dict], *, topic_title: str, correct_answer: str, correction: str, remediation: str, scene_anchors: list[str]) -> list[dict]:
    """Fill missing teaching beats without inventing new source evidence."""
    templates = [
        (
            "Definition to remember",
            f"The source-grounded idea for {topic_title} is: {correct_answer}",
            ["Start with the definition before applying the idea.", "Use the supplied correction to check the meaning."],
            f"The definition to remember is this: {correct_answer} {correction}",
        ),
        (
            "How to apply it",
            f"Apply the idea by following this repair method: {correction}",
            ["Name the relevant quantity or block.", "Follow the operation in the correct order."],
            f"To apply the idea, follow this repair method: {correction}",
        ),
        (
            "Transfer check",
            f"Before moving on, explain {topic_title} in your own words and identify the step that prevents the original mistake.",
            ["Locate the step that was misunderstood.", "Try the same reasoning on a similar example."],
            f"For transfer, explain {topic_title} in your own words and identify the step that prevents the original mistake. {remediation}",
        ),
    ]
    completed = list(slides)
    for title, body, bullets, narration in templates:
        if len(completed) >= 4:
            break
        completed.append({
            "index": len(completed),
            "title": title,
            "body": body[:900],
            "bullets": [item[:220] for item in bullets],
            "narration": narration[:1400],
            "sourceAnchorIds": sorted(set(scene_anchors)),
            "diagram": {"nodes": [], "edges": []},
        })
    return completed


def _voice_multipart(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----FeynmanVoice" + uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _generate_voice(text: str) -> dict | None:
    base_url = str(getattr(settings, "TTS_VOXCPM_BASE_URL", "") or "").rstrip("/")
    if not base_url:
        return None
    prompt = str(getattr(settings, "TTS_VOXCPM_PROMPT", "") or "").strip()
    body, content_type = _voice_multipart({
        "text": f"({prompt}){text}" if prompt else text,
        "cfg_value": "2.0",
        "inference_timesteps": "10",
        "normalize": "false",
        "denoise": "false",
    })
    headers = {"Content-Type": content_type}
    api_key = str(getattr(settings, "TTS_VOXCPM_API_KEY", "") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with urlopen(Request(f"{base_url}/tts/upload", data=body, headers=headers, method="POST"), timeout=settings.TTS_VOXCPM_TIMEOUT_SECONDS) as response:
            audio = response.read()
            mime = response.headers.get_content_type() or "audio/wav"
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailable(f"VoxCPM Python voice service failed: {exc}") from exc
    if not audio:
        raise ProviderUnavailable("VoxCPM Python voice service returned empty audio")
    format_name = "mp3" if "mpeg" in mime or "mp3" in mime else "wav"
    return {"dataUrl": f"data:{mime};base64,{base64.b64encode(audio).decode('ascii')}", "format": format_name, "providerId": "voxcpm-python"}


def _fireworks_slide_lesson(*, topic_title: str, stage_kind: str, mistake: str, correct_answer: str, correction: str, remediation: str, source_context: str, allowed_anchors: set[str], scene_anchors: list[str], requested_duration: int) -> dict:
    provider = provider_for("fireworks")
    manifest = provider.generate_remediation_slides({
        "topicTitle": topic_title,
        "stageKind": stage_kind,
        "mistake": mistake,
        "correctAnswer": correct_answer,
        "correction": correction,
        "remediation": remediation,
        "sourceContext": source_context,
        "approvedAnchorIds": sorted(allowed_anchors),
    })
    slides = _validate_slide_manifest(manifest, allowed_anchors, scene_anchors)
    slides = _complete_slide_lesson(
        slides,
        topic_title=topic_title,
        correct_answer=correct_answer,
        correction=correction,
        remediation=remediation,
        scene_anchors=scene_anchors,
    )
    per_slide = max(8, requested_duration // len(slides))
    for slide in slides:
        slide["durationSeconds"] = per_slide
        try:
            voice = _generate_voice(slide["narration"])
        except ProviderUnavailable:
            # Narration is an enhancement. A voice-service outage must not
            # prevent the learner from receiving the visual correction.
            voice = None
        if voice:
            slide["audio"] = {**voice, "text": slide["narration"]}
    return {
        "mode": "fireworks_slides",
        "title": str(manifest.get("title") or f"{topic_title} — guided correction")[:240],
        "requestedDurationSeconds": requested_duration,
        "actualDurationSeconds": per_slide * len(slides),
        "providerId": "fireworks-qwen3p7-plus",
        "voiceProviderId": "voxcpm-python" if any("audio" in slide for slide in slides) else None,
        "slides": slides,
    }


@method_decorator(csrf_exempt, name="dispatch")
class StudyRemediationVideoConfigView(APIView):
    """Expose safe video capability metadata; never expose provider secrets."""

    def get(self, request):
        mode = settings.REMEDIATION_VIDEO_PROVIDER
        rendered = mode != "fireworks-slides"
        return Response({
            "mode": "sequenced_clips" if rendered else "fireworks_slides",
            "provider": "configured video provider" if rendered else "fireworks-qwen3p7-plus",
            "label": "Rendered video clips" if rendered else "Fireworks narrated slides",
            "configured": bool(settings.FIREWORKS_API_KEY) if not rendered else bool(settings.VIDEO_SERVICE_BASE_URL and settings.VIDEO_SERVICE_KEY),
            "voiceConfigured": bool(settings.TTS_VOXCPM_BASE_URL),
            "minDurationSeconds": 60,
            "maxDurationSeconds": 300,
        })


@method_decorator(csrf_exempt, name="dispatch")
class StudyRemediationVideoView(APIView):
    """Create a source-bounded remediation lesson."""

    def post(self, request):
        if settings.REMEDIATION_VIDEO_PROVIDER != "fireworks-slides" and (not settings.VIDEO_SERVICE_BASE_URL or not settings.VIDEO_SERVICE_KEY):
            return _error("The self-contained remediation video service is not configured", "video_provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)

        body = request.data if isinstance(request.data, dict) else {}
        source_ids = body.get("sourceIds")
        scene = body.get("scene")
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 20 or any(not isinstance(item, str) or not item.strip() for item in source_ids):
            return _error("sourceIds must be a non-empty list of IDs")
        if not isinstance(scene, dict):
            return _error("scene is required")
        scene_anchors = scene.get("sourceAnchorIds")
        if not isinstance(scene_anchors, list) or not scene_anchors or any(not isinstance(item, str) or not item.strip() for item in scene_anchors):
            return _error("scene.sourceAnchorIds must be a non-empty list")
        scene_anchors = [item.strip() for item in scene_anchors]

        try:
            mistake = _bounded_text(body, "mistake", 2400)
            correct_answer = _bounded_text(body, "correctAnswer", 4000)
            correction = _bounded_text(body, "correction", 2400)
            remediation = _bounded_text(body, "remediation", 2400, required=False)
            topic_title = _bounded_text(scene, "title", 240, required=False) or "This topic"
            stage_kind = _bounded_text(scene, "stageKind", 80, required=False) or "assessment"
            requested_duration = int(body.get("requestedDurationSeconds") or 60)
        except (TypeError, ValueError) as exc:
            return _error(str(exc))
        if requested_duration < 60 or requested_duration > 300:
            return _error("requestedDurationSeconds must be between 60 and 300")

        try:
            spans, allowed_anchors, source_pack_version, review_required = _source_context([item.strip() for item in source_ids])
            if not set(scene_anchors).issubset(allowed_anchors):
                return _error("scene contains an unapproved source anchor", "source_boundary_violation")
            source_context = _approved_source_context(spans, scene_anchors)
            if not source_context:
                return _error("approved source context is unavailable", "source_extraction_pending")

            if settings.REMEDIATION_VIDEO_PROVIDER == "fireworks-slides":
                try:
                    lesson = _fireworks_slide_lesson(
                        topic_title=topic_title,
                        stage_kind=stage_kind,
                        mistake=mistake,
                        correct_answer=correct_answer,
                        correction=correction,
                        remediation=remediation,
                        source_context=source_context,
                        allowed_anchors=allowed_anchors,
                        scene_anchors=[str(anchor) for anchor in scene_anchors],
                        requested_duration=requested_duration,
                    )
                except (ProviderUnavailable, ProviderOutputError) as exc:
                    return _error(str(exc), "video_generation_failed", status.HTTP_502_BAD_GATEWAY)
                return Response({
                    "success": True,
                    "remediationVideo": lesson,
                    "sourcePackVersion": source_pack_version,
                    "reviewRequired": review_required,
                    "sourceAnchorIds": sorted(set(scene_anchors)),
                }, status=status.HTTP_200_OK)

            payload = json.dumps({
                "topicTitle": topic_title,
                "stageKind": stage_kind,
                "mistake": mistake,
                "correctAnswer": correct_answer,
                "correction": correction,
                "remediation": remediation,
                "sourceContext": source_context,
                "requestedDurationSeconds": requested_duration,
            }, ensure_ascii=False).encode("utf-8")
            endpoint = settings.VIDEO_SERVICE_BASE_URL.rstrip("/") + "/api/remediation-video"
            upstream = Request(endpoint, data=payload, headers={
                "Content-Type": "application/json",
                "X-Feynman-Video-Key": settings.VIDEO_SERVICE_KEY,
            }, method="POST")
            with urlopen(upstream, timeout=settings.VIDEO_SERVICE_TIMEOUT_SECONDS) as response:
                upstream_body = json.loads(response.read().decode("utf-8"))
            if not isinstance(upstream_body, dict) or not upstream_body.get("success"):
                return _error("The remediation video provider returned an invalid response", "video_provider_unavailable", status.HTTP_502_BAD_GATEWAY)
            upstream_body.update({
                "sourcePackVersion": source_pack_version,
                "reviewRequired": review_required,
                "sourceAnchorIds": sorted(set(scene_anchors)),
            })
            return Response(upstream_body, status=status.HTTP_200_OK)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            return _error(f"Video generation failed: {detail}", "video_generation_failed", status.HTTP_502_BAD_GATEWAY)
        except (URLError, TimeoutError) as exc:
            return _error(f"Video service is unavailable: {exc}", "video_provider_unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
        except (json.JSONDecodeError, OSError) as exc:
            return _error(f"Video provider returned an unreadable response: {exc}", "video_generation_failed", status.HTTP_502_BAD_GATEWAY)
