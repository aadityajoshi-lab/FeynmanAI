from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .dynamic import profile_dict
from .learning_safety import personal_decision_boundary
from .adaptive_runtime import (
    activity_contracts_for_goal,
    deterministic_evaluation,
    next_route_state,
    normalize_structured_attempt,
)
from .curriculum_compiler import CurriculumCompileError, compile_curriculum, curriculum_is_stale
from .providers import ProviderOutputError, ProviderUnavailable, active_generation_configured, normalize_model_name, provider_for
from .models import (
    ActivityAttempt,
    CapabilityState,
    CurriculumPack,
    GoalCurriculumRoute,
    Course,
    Enrollment,
    EvidenceRecord,
    LearningActivity,
    LearningGoal,
    LearnerProfile,
    Membership,
    Notebook,
    NotebookSource,
    Organization,
    OrganizationInvitation,
    GoalShare,
    ShareGrant,
    SourcePack,
)


def _error(message: str, code: str = "invalid_request", http_status: int = 422) -> Response:
    return Response({"error": {"code": code, "message": message}}, status=http_status)


def _body(request) -> dict[str, Any]:
    return request.data if isinstance(request.data, dict) else {}


def _active_provider_metadata() -> tuple[str, str]:
    configured = str(getattr(settings, "LLM_PROVIDER", "fixture") or "fixture").casefold()
    if configured in {"openai", "live_openai"}:
        return "openai", normalize_model_name(getattr(settings, "OPENAI_MODEL", "gpt-5.6-terra-high"), "gpt-5.6-terra-high")
    if configured in {"qwen", "live_qwen"}:
        return "qwen", str(getattr(settings, "FIREWORKS_MODEL", ""))
    if configured in {"fireworks", "live_fireworks"}:
        return "fireworks", str(getattr(settings, "FIREWORKS_MODEL", ""))
    return "local", "deterministic-evidence-v1"


def _current_user(request):
    user = getattr(request, "user", None)
    return user if user and getattr(user, "is_authenticated", False) else None


def _ensure_personal_workspace(profile: LearnerProfile) -> Organization:
    if profile.workspace_id:
        return profile.workspace
    account = profile.account
    workspace = Organization.objects.create(
        name=(profile.display_name or getattr(account, "first_name", "") or "Personal workspace")[:180],
        kind="personal",
        owner=account,
        settings={"personal": True},
    )
    profile.workspace = workspace
    profile.save(update_fields=["workspace", "updated_at"])
    if account:
        Membership.objects.get_or_create(
            organization=workspace,
            user=account,
            defaults={"role": "owner", "status": "active"},
        )
    return workspace


def _profile_for_user(user) -> LearnerProfile:
    profile = LearnerProfile.objects.filter(account=user).first()
    if not profile:
        profile = LearnerProfile.objects.create(
            account=user,
            anonymous_key=f"account_{uuid.uuid4().hex}",
            display_name=(getattr(user, "first_name", "") or getattr(user, "username", ""))[:120],
        )
    _ensure_personal_workspace(profile)
    return profile


def _require_profile(request):
    user = _current_user(request)
    if not user:
        return None, _error("Sign in to use a personal workspace.", "authentication_required", 401)
    return _profile_for_user(user), None


def _membership(user, organization: Organization) -> Membership | None:
    if not user:
        return None
    return Membership.objects.filter(organization=organization, user=user, status="active").first()


def _can_manage_organization(user, organization: Organization) -> bool:
    member = _membership(user, organization)
    return bool(member and member.role in {"owner", "institution_admin"})


def _can_manage_course(user, course: Course) -> bool:
    if course.instructor_id == getattr(user, "id", None):
        return True
    member = _membership(user, course.organization)
    # An organization-level instructor role permits creating a course (which
    # assigns that instructor to it), but does not automatically reveal every
    # other instructor's cohort or course route. Owners and institution admins
    # remain the deliberately broader management roles.
    return bool(member and member.role in {"owner", "institution_admin"})


def _can_review_course_cohort(user, course: Course) -> bool:
    """Only the assigned instructor may inspect learner-level shared evidence.

    Organization owners and administrators can manage course configuration and
    see aggregate institution data, but they must not inherit the learner
    evidence review surface merely from a workspace-level role.
    """
    return bool(course.instructor_id and course.instructor_id == getattr(user, "id", None))


def _manageable_courses(user):
    """Courses a member may build or review without broadening learner access."""
    if not user:
        return Course.objects.none()
    return Course.objects.filter(
        Q(instructor=user)
        | Q(
            organization__memberships__user=user,
            organization__memberships__status="active",
            organization__memberships__role__in={"owner", "institution_admin"},
        )
    ).distinct()


def _course_sharing_enabled(profile: LearnerProfile) -> bool:
    preferences = profile.preferences if isinstance(profile.preferences, dict) else {}
    privacy_preferences = preferences.get("privacy") if isinstance(preferences.get("privacy"), dict) else {}
    return bool(privacy_preferences.get("courseSharingEnabled", True))


def _workspace_payload(workspace: Organization, user=None) -> dict[str, Any]:
    membership = _membership(user, workspace)
    return {
        "workspaceId": str(workspace.organization_id),
        "name": workspace.name,
        "kind": workspace.kind,
        "role": membership.role if membership else None,
        "memberCount": workspace.memberships.filter(status="active").count(),
        "createdAt": workspace.created_at.isoformat(),
    }


def _course_payload(course: Course, profile: LearnerProfile | None = None, user=None) -> dict[str, Any]:
    # The role flags are safe to return to every signed-in caller: they are
    # derived from the caller's own membership and let the frontend avoid
    # rendering instructor controls merely because a learner can open a course
    # they enrolled in.
    user = user or (profile.account if profile and profile.account_id else None)
    enrollment = Enrollment.objects.filter(course=course, profile=profile).first() if profile else None
    return {
        "courseId": str(course.course_id),
        "workspaceId": str(course.organization.organization_id),
        "title": course.title,
        "description": course.description,
        "joinCode": course.join_code,
        "status": course.status,
        "instructor": (course.instructor.first_name or course.instructor.username) if course.instructor else "Unassigned",
        "enrollmentStatus": enrollment.status if enrollment else None,
        "learnerCount": course.enrollments.filter(status="active").count(),
        "sourcePackCount": course.source_packs.count(),
        "route": course.route,
        "sourcePolicy": course.source_policy,
        "canManage": _can_manage_course(user, course),
        "canReviewCohort": _can_review_course_cohort(user, course),
        "createdAt": course.created_at.isoformat(),
    }


def _activity_payload(activity: LearningActivity) -> dict[str, Any]:
    return {
        "activityId": str(activity.activity_id),
        "type": activity.activity_type,
        "title": activity.title,
        "prompt": activity.prompt,
        "position": activity.position,
        "status": activity.status,
        "configuration": activity.configuration if isinstance(activity.configuration, dict) else {},
        "difficulty": activity.difficulty,
        "remediationTarget": activity.remediation_target,
        "transferTarget": activity.transfer_target,
        "prerequisites": activity.prerequisites,
        "sourceIds": activity.source_ids,
        "sourceAnchorIds": activity.configuration.get("sourceAnchorIds", []) if isinstance(activity.configuration, dict) else [],
        "citations": activity.configuration.get("citations", []) if isinstance(activity.configuration, dict) else [],
        "evaluator": activity.evaluator,
    }


def _evidence_payload(evidence: EvidenceRecord) -> dict[str, Any]:
    rubric = evidence.rubric if isinstance(evidence.rubric, dict) else {}
    return {
        "evidenceId": str(evidence.evidence_id),
        "goalId": str(evidence.goal.goal_id),
        "goalTitle": evidence.goal.title,
        "goalCategory": evidence.goal.domain,
        "activityId": str(evidence.activity.activity_id) if evidence.activity else None,
        "capability": evidence.capability,
        "type": evidence.evidence_type,
        "status": evidence.status,
        "score": evidence.score,
        "summary": evidence.summary,
        "rubric": rubric,
        "transitionReason": evidence.transition_reason,
        "sourceAnchorIds": evidence.source_anchor_ids,
        "sourceIds": rubric.get("selectedSourceIds") if isinstance(rubric.get("selectedSourceIds"), list) else [],
        "createdAt": evidence.created_at.isoformat(),
    }


def _source_anchor_ids(source: NotebookSource) -> list[str]:
    """Return the durable anchors that can legitimately support an attempt."""
    blocks = source.blocks if isinstance(source.blocks, list) else []
    anchors = [
        str(block.get("sourceAnchor")).strip()
        for block in blocks
        if isinstance(block, dict) and str(block.get("sourceAnchor") or "").strip()
    ]
    return list(dict.fromkeys(anchors))


def _ready_goal_sources(goal: LearningGoal, profile: LearnerProfile) -> list[NotebookSource]:
    """Only the learner's ready sources attached to this exact goal can be cited."""
    return list(
        NotebookSource.objects.select_related("notebook")
        .filter(notebook__goal=goal, notebook__owner_profile=profile, status="ready", grounding_enabled=True)
        .order_by("notebook__created_at", "notebook_id", "created_at", "id")
    )


def _source_summary(source: NotebookSource) -> dict[str, Any]:
    extraction = source.extraction if isinstance(source.extraction, dict) else {}
    return {
        "sourceId": source.source_id,
        "title": source.title,
        "filename": source.filename or None,
        "sourceKind": source.source_kind,
        "mimeType": source.mime_type or None,
        "status": source.status,
        "groundingEnabled": source.grounding_enabled,
        "extractionMethod": source.extraction_method,
        "pageCount": extraction.get("pageCount"),
        "blockCount": extraction.get("blockCount", len(source.blocks or [])),
        "anchorIds": _source_anchor_ids(source),
    }


def _goal_source_payload(goal: LearningGoal, profile: LearnerProfile) -> dict[str, Any]:
    """Source Dock metadata without exposing private source/chat contents.

    The Dock needs to show extracting, failed, and view-only sources so a
    learner can understand the state of an attached context.  The separate
    scope helper still admits only ready, grounding-enabled sources to chat,
    artifacts, and verified evidence.
    """
    sources_by_notebook: dict[int, list[NotebookSource]] = {}
    attached_sources = (
        NotebookSource.objects.select_related("notebook")
        .filter(notebook__goal=goal, notebook__owner_profile=profile)
        .order_by("notebook__created_at", "notebook_id", "created_at", "id")
    )
    for source in attached_sources:
        sources_by_notebook.setdefault(source.notebook_id, []).append(source)
    notebooks = (
        Notebook.objects.filter(goal=goal, owner_profile=profile)
        .order_by("created_at", "id")
    )
    return {
        "goalId": str(goal.goal_id),
        "notebooks": [
            {
                "notebookId": str(notebook.notebook_id),
                "title": notebook.title,
                "status": notebook.status,
                "sources": [_source_summary(source) for source in sources_by_notebook.get(notebook.id, [])],
                "artifacts": [
                    {
                        "artifactId": str(artifact.artifact_id),
                        "type": artifact.artifact_type,
                        "title": artifact.title,
                        "status": artifact.status,
                        "sourceIds": [] if artifact.status == "stale" else artifact.source_ids or [],
                    }
                    for artifact in notebook.artifacts.order_by("-created_at", "-id")
                ],
            }
            for notebook in notebooks
        ],
    }


def _validated_attempt_source_scope(
    goal: LearningGoal,
    profile: LearnerProfile,
    body: dict[str, Any],
) -> tuple[list[str], list[str], Response | None]:
    """Validate optional source selection and every anchor before evidence changes state.

    Older clients may provide anchors without ``sourceIds``. In that case the
    source selection is inferred *only* from the ready attached source that
    owns each anchor; arbitrary anchor strings can never make evidence
    source-backed.
    """
    raw_anchor_ids = body.get("sourceAnchorIds", [])
    if raw_anchor_ids is None:
        raw_anchor_ids = []
    if not isinstance(raw_anchor_ids, list) or not all(isinstance(item, str) for item in raw_anchor_ids):
        return [], [], _error("sourceAnchorIds must be an array of source anchors.")
    anchor_ids = list(dict.fromkeys(item.strip() for item in raw_anchor_ids if item.strip()))
    if len(anchor_ids) > 50 or any(len(item) > 240 for item in anchor_ids):
        return [], [], _error("Provide at most 50 source anchors, each 240 characters or fewer.")

    raw_source_ids = body.get("sourceIds")
    source_ids_supplied = "sourceIds" in body
    if source_ids_supplied:
        if not isinstance(raw_source_ids, list) or not all(isinstance(item, str) for item in raw_source_ids):
            return [], [], _error("sourceIds must be an array of ready source identifiers.")
        requested_source_ids = list(dict.fromkeys(item.strip() for item in raw_source_ids if item.strip()))
        if not requested_source_ids:
            return [], [], _error("Select at least one ready source when sourceIds is provided.")
    else:
        requested_source_ids = []

    ready_sources = _ready_goal_sources(goal, profile)
    source_by_id = {source.source_id: source for source in ready_sources}
    unknown_source_ids = [source_id for source_id in requested_source_ids if source_id not in source_by_id]
    if unknown_source_ids:
        return [], [], _error(
            "Selected sources must be ready, owned by you, and attached to this learning goal.",
            "invalid_source_scope",
        )

    source_by_anchor: dict[str, str] = {}
    for source in ready_sources:
        for anchor_id in _source_anchor_ids(source):
            source_by_anchor[anchor_id] = source.source_id
    unknown_anchor_ids = [anchor_id for anchor_id in anchor_ids if anchor_id not in source_by_anchor]
    if unknown_anchor_ids:
        return [], [], _error(
            "Every source anchor must belong to a ready source attached to this learning goal.",
            "invalid_source_anchor",
        )

    if source_ids_supplied:
        selected_source_ids = requested_source_ids
        unselected_anchor_ids = [anchor_id for anchor_id in anchor_ids if source_by_anchor[anchor_id] not in selected_source_ids]
        if unselected_anchor_ids:
            return [], [], _error(
                "Source anchors must belong to one of the selected ready sources.",
                "invalid_source_scope",
            )
    else:
        selected_source_ids = list(dict.fromkeys(source_by_anchor[anchor_id] for anchor_id in anchor_ids))
    return selected_source_ids, anchor_ids, None


def _activity_feedback_source_spans(
    goal: LearningGoal,
    profile: LearnerProfile,
    selected_source_ids: list[str],
    anchor_ids: list[str],
) -> list[dict[str, Any]]:
    """Build the one bounded provider context pack for an activity attempt.

    The caller has already validated source IDs and anchors.  Repeat the
    ownership/readiness filter here rather than trusting client identifiers,
    and include only the selected blocks.  This keeps the provider boundary
    separate from learner memory, unrelated notebooks, and view-only sources.
    """
    if not selected_source_ids:
        return []
    selected = set(selected_source_ids)
    requested_anchors = set(anchor_ids)
    spans: list[dict[str, Any]] = []
    text_budget = 24000
    for source in _ready_goal_sources(goal, profile):
        if source.source_id not in selected:
            continue
        for block in source.blocks if isinstance(source.blocks, list) else []:
            if not isinstance(block, dict):
                continue
            anchor = str(block.get("sourceAnchor") or "").strip()
            if not anchor or (requested_anchors and anchor not in requested_anchors):
                continue
            text = str(block.get("markdown") or "").strip()
            if not text:
                continue
            if text_budget <= 0 or len(spans) >= 40:
                return spans
            clipped = text[: min(1800, text_budget)]
            text_budget -= len(clipped)
            spans.append({
                "sourceId": source.source_id,
                "documentTitle": source.title,
                "page": block.get("page"),
                "blockId": str(block.get("blockId") or anchor),
                "sourceAnchorId": anchor,
                "text": clipped,
            })
    return spans


def _provider_error_category(error: Exception) -> str:
    """Return a presentation-safe category instead of upstream error text."""
    message = str(error or "").casefold()
    if any(marker in message for marker in ("timed out", "timeout", "deadline exceeded")):
        return "timeout"
    if any(marker in message for marker in ("401", "403", "unauthorized", "forbidden", "authentication")):
        return "authentication"
    if any(marker in message for marker in ("429", "rate limit", "too many requests")):
        return "rate_limited"
    if any(marker in message for marker in ("invalid", "malformed", "schema", "json", "citation")):
        return "invalid_response"
    return "unavailable"


def _activity_provider_feedback(
    *,
    goal: LearningGoal,
    activity: LearningActivity,
    profile: LearnerProfile,
    response_text: str,
    selected_source_ids: list[str],
    anchor_ids: list[str],
    confidence: object,
    structured_attempt: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Evaluate a real learner response with the configured teaching provider.

    A missing key is a local deployment configuration, not a fabricated model
    result.  A configured provider failure is returned as a recoverable
    attempt state so the caller can save observable evidence but cannot mark
    it verified.
    """
    source_spans = _activity_feedback_source_spans(goal, profile, selected_source_ids, anchor_ids)
    base = {
        "provider": _active_provider_metadata()[0],
        "model": _active_provider_metadata()[1],
        "sourceAnchorIds": list(anchor_ids),
    }
    if not active_generation_configured():
        return {
            **base,
            "state": "not_configured",
            "providerAttempt": "not_configured",
            "retryAvailable": False,
            "uncertainty": "No live teaching provider is configured; source-backed verification used the local evidence threshold.",
        }, None
    if not source_spans:
        return {
            **base,
            "state": "needs_source",
            "providerAttempt": "skipped_no_selected_source",
            "retryAvailable": False,
            "uncertainty": "Select ready source anchors before requesting source-grounded feedback.",
        }, None

    try:
        parsed_confidence = int(confidence or 3)
    except (TypeError, ValueError):
        parsed_confidence = 3
    parsed_confidence = max(1, min(5, parsed_confidence))
    manifest = {
        "sourceAnchorIds": list(anchor_ids),
        "sourceSpans": source_spans,
        "stageKind": activity.activity_type,
        "stage": {
            "activityId": str(activity.activity_id),
            "kind": activity.activity_type,
            "title": activity.title,
            "prompt": activity.prompt,
            "responseType": "long_text",
            "rubric": activity.evaluator if isinstance(activity.evaluator, dict) else {},
        },
        "structuredAttempt": structured_attempt or {},
    }
    try:
        result = provider_for().evaluate_checkpoint({
            "manifest": manifest,
            "kind": activity.activity_type,
            "confidence": parsed_confidence,
            "prediction": "",
            "explanation": response_text,
        })
    except (ProviderUnavailable, ProviderOutputError) as exc:
        return {
            **base,
            "state": "provider_failed",
            "providerAttempt": "failed",
            "providerErrorCategory": _provider_error_category(exc),
            "retryAvailable": True,
            "retryAction": "resubmit_attempt",
            "uncertainty": "The configured teaching model did not return a valid evaluation. Your response was saved, but it was not verified.",
        }, None

    allowed_anchors = set(anchor_ids)
    returned_anchors = result.get("sourceAnchorIds") if isinstance(result.get("sourceAnchorIds"), list) else []
    approved_anchors = [str(anchor) for anchor in returned_anchors if str(anchor) in allowed_anchors]
    evaluation = {
        "state": str(result.get("state") or "needs_human_review"),
        "correct": bool(result.get("correct")),
        "understandingScore": result.get("understandingScore"),
        "overconfidence": bool(result.get("overconfidence")),
        "feedback": str(result.get("feedback") or "").strip()[:2000],
        "remediation": str(result.get("remediation") or "").strip()[:1600],
        "mistake": str(result.get("mistake") or "").strip()[:1200],
        "correctAnswer": str(result.get("correctAnswer") or "").strip()[:1600],
        "correction": str(result.get("correction") or "").strip()[:1600],
        "nextAction": str(result.get("nextAction") or "review").strip()[:80],
        "retryPrompt": str(result.get("retryPrompt") or "").strip()[:1200] or None,
        "retryOptions": result.get("retryOptions") if isinstance(result.get("retryOptions"), list) else None,
        "sourceAnchorIds": approved_anchors,
    }
    return {
        **base,
        "state": evaluation["state"],
        "providerAttempt": "completed",
        "providerMode": str(result.get("providerMode") or "live_qwen"),
        "provider": "fireworks" if result.get("providerMode") == "live_fireworks_fallback" else base["provider"],
        "model": str(getattr(settings, "FIREWORKS_MODEL", "")) if result.get("providerMode") == "live_fireworks_fallback" else base["model"],
        "retryAvailable": evaluation["nextAction"] == "retry",
        "uncertainty": "Provider requested human review." if evaluation["state"] != "complete" else ("The response may be overconfident." if evaluation["overconfidence"] else ""),
        "evaluation": evaluation,
    }, evaluation


def _goal_payload(goal: LearningGoal, include_route: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "goalId": str(goal.goal_id),
        "workspaceId": str(goal.workspace.organization_id) if goal.workspace else None,
        "courseId": str(goal.course.course_id) if goal.course else None,
        "title": goal.title,
        "description": goal.description,
        "domain": goal.domain,
        "category": goal.domain,
        "outcome": goal.outcome,
        "currentLevel": goal.current_level,
        "timeBudget": goal.time_budget,
        "sourceMode": goal.source_mode,
        "safetyMode": goal.safety_mode,
        "verificationMode": goal.verification_mode,
        "status": goal.status,
        "contract": goal.contract,
        "nextAction": goal.next_action,
        "evidenceCount": goal.evidence_records.count(),
        "createdAt": goal.created_at.isoformat(),
        "updatedAt": goal.updated_at.isoformat(),
    }
    if include_route:
        payload["route"] = goal.route
        active_activities = goal.activities.exclude(status="stale").order_by("position", "id")
        payload["activities"] = [_activity_payload(activity) for activity in active_activities]
        payload["evidence"] = [_evidence_payload(item) for item in goal.evidence_records.select_related("goal", "activity").order_by("-created_at")[:20]]
        current_pack = goal.curriculum_packs.order_by("-version").first()
        if current_pack:
            payload["curriculum"] = {
                "packId": str(current_pack.pack_id),
                "version": current_pack.version,
                "status": current_pack.status,
                "domain": current_pack.domain,
                "learnerLevel": current_pack.learner_level,
                "sourceIds": current_pack.source_ids,
                "sourceAnchorIds": current_pack.source_anchor_ids,
                "sourceFingerprint": current_pack.source_fingerprint,
                "uncertainty": current_pack.uncertainty,
                "provenance": current_pack.provenance,
            }
    return payload


def _classify_goal(title: str, description: str) -> tuple[str, str, str, str]:
    text = f"{title} {description}".lower()
    if any(word in text for word in ("medical", "medicine", "clinical", "anatomy", "pharmacology", "diagnosis", "symptom", "rash", "treatment", "health", "patient")):
        return "medical", "academic_source_bound", "guided", "Add academic references before claiming verified medical knowledge."
    if any(word in text for word in ("stock", "finance", "financial", "investing", "investment", "trading", "portfolio", "crypto", "shares", "fund")):
        return "finance", "academic_source_bound", "guided", "Use cited educational material; this workspace does not provide personal trading advice."
    if any(word in text for word in ("machine learning", "artificial intelligence", "neural", "model training", "classification", "model error", "dataset", "ml")):
        return "ai_ml", "guided", "guided", "Explain a model decision, then test it on a bounded example."
    if any(word in text for word in ("computer graphics", "rasterization", "projection", "camera matrix", "lighting", "depth buffer", "texture sampling")):
        return "computer_graphics", "guided", "guided", "Predict the visual consequence before changing a transform, camera, light, or sample."
    if any(word in text for word in ("dsp", "signal processing", "fourier", "dft", "sampling", "aliasing", "reconstruction", "spectral")):
        return "dsp", "guided", "guided", "Predict the sampled waveform or spectrum before changing the signal or sampling controls."
    if any(word in text for word in ("operating system", "operating-system", "kernel", "process", "scheduler", "scheduling", "memory management", "page replacement", "deadlock", "system call")):
        return "operating_systems", "guided", "guided", "Predict the system trace before changing policy or resource state."
    # Keep the history adapter explicit so a generic source-grounded goal
    # about a historical event remains compatible with the generic compiler.
    # Learners can opt into the history workbench with "history", "historical",
    # primary-source, archive, or institution language in the goal itself.
    if any(word in text for word in ("history", "historical", "primary source", "archive", "institution")):
        return "history", "academic_source_bound", "source_backed", "Use selected historical sources to separate chronology, causation, and interpretation."
    if any(word in text for word in ("signal processing", "dsp", "engineering")):
        return "engineering", "guided", "guided", "Predict the system behavior before you inspect the mechanism."
    return "general", "guided", "guided", "Explain the first important idea in your own words, then apply it."


def _classify_requested_category(category: object, title: str, description: str) -> tuple[str, str, str, str] | None:
    """Use the learner's explicit category when supplied, while keeping the
    same safety defaults as automatic classification."""
    if not isinstance(category, str) or not category.strip() or category.strip().lower() == "general":
        return None
    normalized = category.strip().lower().replace("_", " ").replace("/", " ")
    aliases = {
        "operating systems": "operating system",
        "computer graphics": "computer graphics",
        "signal processing dsp": "dsp",
        "machine learning ai": "machine learning",
        "medical education": "medical",
    }
    cue = aliases.get(normalized, normalized)
    classified = _classify_goal(f"{cue} {title}", description)
    return classified if classified[0] != "general" else None


def _build_contract(title: str, description: str, outcome: str, current_level: str, time_budget: str, domain: str, safety_mode: str, verification_mode: str) -> dict[str, Any]:
    prerequisite_map = {
        "operating_systems": ["Identify process and resource states", "Trace a bounded system execution", "Calculate a scheduling or memory metric"],
        "computer_graphics": ["Name the coordinate space", "Apply one transform or camera change", "Predict a bounded visual consequence"],
        "engineering": ["Identify the representation", "Explain the mechanism", "Predict an observable result"],
        "ai_ml": ["Read a dataset or example", "Explain an assumption", "Evaluate a model output"],
        "medical": ["Separate academic facts from personal advice", "Use a cited source", "Explain a mechanism"],
        "finance": ["Separate education from a recommendation", "Use a cited source", "Explain risk and uncertainty"],
        "history": ["Separate chronology from causation", "Track source provenance", "State an uncertainty or disagreement"],
        "general": ["Name the core concept", "Give a concrete example", "Apply it in a new situation"],
    }
    return {
        "intendedCapability": outcome or title,
        "learnerStartingPoint": current_level,
        "timeBudget": time_budget or "Flexible",
        "prerequisites": prerequisite_map.get(domain, prerequisite_map["general"]),
        "confidence": "provisional",
        "sourceRequirements": "Source-backed evidence is required before a claim can be verified." if safety_mode == "academic_source_bound" else "Sources are optional until you want source-backed verification.",
        "safetyMode": safety_mode,
        "verificationMode": verification_mode,
        "firstTask": "Make a prediction or explanation before asking for an answer.",
        "learnerCorrection": "You can edit this contract before starting; Feynman will not silently redefine your goal.",
        # The brief is required by the contract schema. Universal goal entry
        # allows the longer description to be empty, so keep the contract
        # valid by falling back to the learner's capability title.
        "brief": description or title,
    }


def _apply_generated_contract(base: dict[str, Any], generated: object, *, domain: str) -> dict[str, Any]:
    """Accept only the learner-facing fields the model is allowed to draft."""
    if not isinstance(generated, dict):
        raise ProviderOutputError("learning contract generation returned a non-object")
    prerequisites = generated.get("prerequisites")
    if not isinstance(prerequisites, list):
        raise ProviderOutputError("learning contract generation returned invalid prerequisites")
    # Keep the contract bounded even when a model ignores the requested item
    # count. Filter unusable entries, then retain the first twelve useful concepts
    # instead of discarding an otherwise good live draft.
    normalized_prerequisites = [
        item.strip() for item in prerequisites
        if isinstance(item, str) and item.strip() and len(item.strip()) <= 240
    ][:12]
    if not normalized_prerequisites:
        raise ProviderOutputError("learning contract generation returned invalid prerequisites")
    first_task = generated.get("firstTask")
    if not isinstance(first_task, str) or not first_task.strip() or len(first_task.strip()) > 1000:
        raise ProviderOutputError("learning contract generation returned an invalid first task")
    boundary = personal_decision_boundary(domain, first_task.strip())
    if boundary:
        raise ProviderOutputError("learning contract generation crossed the educational boundary")
    updated = dict(base)
    updated["prerequisites"] = list(dict.fromkeys(normalized_prerequisites))
    updated["firstTask"] = first_task.strip()
    for field, limit in (("intendedCapability", 240), ("brief", 2000), ("confidence", 120)):
        value = generated.get(field)
        if isinstance(value, str) and value.strip():
            updated[field] = value.strip()[:limit]
    return updated


def _apply_contract_overrides(
    contract: dict[str, Any],
    raw_contract: object,
    *,
    domain: str,
) -> tuple[dict[str, Any], dict[str, Any], Response | None]:
    """Apply an editable learning-contract draft without weakening boundaries.

    A contract is a durable subdocument of the learning goal.  The small
    derived update map keeps the public contract and the runtime fields used
    by activity/evidence evaluation in sync; otherwise an apparently edited
    source or safety requirement would be only cosmetic.
    """
    if raw_contract is None:
        return contract, {}, None
    if not isinstance(raw_contract, dict):
        return contract, {}, _error("contract must be an object.")

    updated = dict(contract)
    runtime: dict[str, Any] = {}
    text_fields = {
        "intendedCapability": 500,
        "timeBudget": 80,
        "confidence": 120,
        "sourceRequirements": 600,
        "firstTask": 1200,
        "learnerCorrection": 1200,
        "brief": 4000,
    }
    for field, limit in text_fields.items():
        if field not in raw_contract:
            continue
        value = raw_contract[field]
        if not isinstance(value, str) or not value.strip():
            return contract, {}, _error(f"contract.{field} must be a non-empty string.")
        updated[field] = value.strip()[:limit]

    if "learnerStartingPoint" in raw_contract:
        level = raw_contract["learnerStartingPoint"]
        if level not in {"beginner", "intermediate", "advanced"}:
            return contract, {}, _error("contract.learnerStartingPoint must be beginner, intermediate, or advanced.")
        updated["learnerStartingPoint"] = level
        runtime["current_level"] = level

    if "prerequisites" in raw_contract:
        prerequisites = raw_contract["prerequisites"]
        if (
            not isinstance(prerequisites, list)
            or not 1 <= len(prerequisites) <= 12
            or not all(isinstance(item, str) and item.strip() and len(item.strip()) <= 240 for item in prerequisites)
        ):
            return contract, {}, _error("contract.prerequisites must contain one to twelve short prerequisite statements.")
        updated["prerequisites"] = list(dict.fromkeys(item.strip() for item in prerequisites))

    if "safetyMode" in raw_contract:
        safety_mode = raw_contract["safetyMode"]
        if safety_mode not in {"guided", "academic_source_bound"}:
            return contract, {}, _error("contract.safetyMode must be guided or academic_source_bound.")
        if domain in {"medical", "finance"} and safety_mode != "academic_source_bound":
            return contract, {}, _error("Medical and finance goals must keep academic_source_bound safety mode.", "safety_mode_required")
        updated["safetyMode"] = safety_mode
        runtime["safety_mode"] = safety_mode

    if "verificationMode" in raw_contract:
        verification_mode = raw_contract["verificationMode"]
        if verification_mode not in {"guided", "source_backed"}:
            return contract, {}, _error("contract.verificationMode must be guided or source_backed.")
        updated["verificationMode"] = verification_mode
        runtime["verification_mode"] = verification_mode

    if "intendedCapability" in updated:
        runtime["outcome"] = updated["intendedCapability"]
    if "timeBudget" in updated:
        runtime["time_budget"] = updated["timeBudget"]

    # High-stakes goals never permit a cosmetic contract edit to lower the
    # actual source and safety boundary.  Their explanatory copy is also kept
    # accurate after a draft round-trip.
    effective_safety_mode = runtime.get("safety_mode", updated.get("safetyMode"))
    effective_verification_mode = runtime.get("verification_mode", updated.get("verificationMode"))
    if domain in {"medical", "finance"}:
        updated["safetyMode"] = "academic_source_bound"
        updated["sourceRequirements"] = "Academic, source-cited evidence is required before a claim can be verified."
        runtime["safety_mode"] = "academic_source_bound"
        runtime["source_mode"] = "required"
    elif effective_safety_mode == "academic_source_bound" or effective_verification_mode == "source_backed":
        if effective_verification_mode == "source_backed":
            updated["sourceRequirements"] = "A selected ready source and durable anchor are required before an attempt can be verified."
        runtime["source_mode"] = "required"
    else:
        runtime["source_mode"] = "optional"

    boundary = personal_decision_boundary(domain, str(updated.get("firstTask") or ""))
    if boundary:
        return contract, {}, _error(boundary, "educational_boundary")
    return updated, runtime, None


class LearningOsAPIView(APIView):
    """Session-authenticated API base.

    DRF's ``SessionAuthentication`` applies CSRF validation to every
    authenticated unsafe request. Do not add ``csrf_exempt`` here: the browser
    must send the cookie-derived ``X-CSRFToken`` after sign-in.
    """


class CsrfBootstrapView(APIView):
    """Issue the cookie/token pair used by cross-origin browser mutations."""

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class AccountRegisterView(LearningOsAPIView):
    def post(self, request):
        body = _body(request)
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        display_name = str(body.get("displayName", "")).strip()
        if "@" not in email or len(email) > 150:
            return _error("A valid email is required.")
        if len(password) < 8:
            return _error("Use a password with at least 8 characters.")
        User = get_user_model()
        if User.objects.filter(username=email).exists():
            return _error("An account already exists for this email.", "account_exists", 409)
        with transaction.atomic():
            user = User.objects.create_user(username=email, email=email, password=password, first_name=display_name[:150])
            anonymous_key = body.get("anonymousLearnerId")
            profile = LearnerProfile.objects.filter(anonymous_key=anonymous_key, account__isnull=True).first() if isinstance(anonymous_key, str) else None
            if not profile:
                profile = LearnerProfile.objects.create(
                    account=user,
                    anonymous_key=f"account_{uuid.uuid4().hex}",
                    display_name=display_name[:120],
                )
            else:
                profile.account = user
                if display_name:
                    profile.display_name = display_name[:120]
                profile.save(update_fields=["account", "display_name", "updated_at"])
            _ensure_personal_workspace(profile)
            login(request, user)
        return Response(_me_payload(user, profile), status=status.HTTP_201_CREATED)


class AccountLoginView(LearningOsAPIView):
    def post(self, request):
        body = _body(request)
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        user = authenticate(request, username=email, password=password)
        if not user:
            return _error("Email or password is incorrect.", "invalid_credentials", 401)
        login(request, user)
        profile = _profile_for_user(user)
        return Response(_me_payload(user, profile))


class AccountLogoutView(LearningOsAPIView):
    def post(self, request):
        logout(request)
        return Response({"signedOut": True})


def _me_payload(user, profile: LearnerProfile) -> dict[str, Any]:
    workspaces = [_workspace_payload(item.organization, user) for item in Membership.objects.select_related("organization").filter(user=user, status="active").order_by("organization__created_at")]
    return {
        "user": {"id": user.id, "email": user.email, "displayName": profile.display_name or user.first_name or user.username},
        "profile": {**profile_dict(profile), "workspaceId": str(profile.workspace.organization_id) if profile.workspace else None},
        "workspaces": workspaces,
        "roles": sorted({item["role"] for item in workspaces if item.get("role")}),
    }


class MeView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        return error or Response(_me_payload(_current_user(request), profile))


class OrganizationCollectionView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        user = _current_user(request)
        rows = Membership.objects.select_related("organization").filter(user=user, status="active").order_by("organization__name")
        return Response({"workspaces": [_workspace_payload(row.organization, user) for row in rows], "personalWorkspaceId": str(profile.workspace.organization_id)})

    def post(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        body = _body(request)
        name = str(body.get("name", "")).strip()
        if not name or len(name) > 180:
            return _error("Workspace name is required and must be 180 characters or fewer.")
        kind = str(body.get("kind", "institution"))
        if kind not in {"institution", "personal"}:
            return _error("kind must be institution or personal")
        user = _current_user(request)
        workspace = Organization.objects.create(name=name, kind=kind, owner=user)
        Membership.objects.create(organization=workspace, user=user, role="owner", status="active")
        return Response(_workspace_payload(workspace, user), status=status.HTTP_201_CREATED)


class OrganizationMembersView(LearningOsAPIView):
    def get(self, request, workspace_id):
        profile, error = _require_profile(request)
        if error:
            return error
        workspace = Organization.objects.filter(organization_id=workspace_id).first()
        if not workspace:
            return _error("Unknown workspace", "not_found", 404)
        if not _can_manage_organization(_current_user(request), workspace):
            return _error("Only workspace owners and admins can view members.", "forbidden", 403)
        members = []
        for member in workspace.memberships.select_related("user").order_by("role", "user__username"):
            members.append({
                "membershipId": str(member.membership_id),
                "email": member.user.email,
                "name": member.user.first_name or member.user.username,
                "role": member.role,
                "status": member.status,
            })
        invitations = [{"inviteId": str(invitation.invitation_id), "email": invitation.email, "role": invitation.role, "token": str(invitation.token), "status": invitation.status} for invitation in workspace.invitations.filter(status="pending").order_by("-created_at")]
        return Response({"members": members, "invitations": invitations})

    def post(self, request, workspace_id):
        profile, error = _require_profile(request)
        if error:
            return error
        workspace = Organization.objects.filter(organization_id=workspace_id).first()
        if not workspace:
            return _error("Unknown workspace", "not_found", 404)
        if not _can_manage_organization(_current_user(request), workspace):
            return _error("Only workspace owners and admins can invite members.", "forbidden", 403)
        body = _body(request)
        email = str(body.get("email", "")).strip().lower()
        role = str(body.get("role", "learner"))
        if "@" not in email:
            return _error("A valid invite email is required.")
        if role not in dict(Membership.ROLE_CHOICES):
            return _error("Unknown membership role.")
        invitation, _ = OrganizationInvitation.objects.update_or_create(
            organization=workspace,
            email=email,
            status="pending",
            defaults={"role": role},
        )
        return Response({"inviteId": str(invitation.invitation_id), "email": invitation.email, "role": invitation.role, "token": str(invitation.token), "joinPath": f"/join/{invitation.token}"}, status=status.HTTP_201_CREATED)


class InvitationDetailView(LearningOsAPIView):
    def get(self, request, token):
        invitation = OrganizationInvitation.objects.select_related("organization").filter(token=token).first()
        if not invitation:
            return _error("This invitation is invalid or no longer available.", "not_found", 404)
        return Response({"inviteId": str(invitation.invitation_id), "organization": invitation.organization.name, "workspaceId": str(invitation.organization.organization_id), "email": invitation.email, "role": invitation.role, "status": invitation.status})

    def post(self, request, token):
        profile, error = _require_profile(request)
        if error:
            return error
        invitation = OrganizationInvitation.objects.select_related("organization").filter(token=token, status="pending").first()
        if not invitation:
            return _error("This invitation is invalid or already used.", "not_found", 404)
        user = _current_user(request)
        if invitation.email.lower() != user.email.lower():
            return _error("Sign in with the email address that received this invitation.", "forbidden", 403)
        Membership.objects.update_or_create(
            organization=invitation.organization,
            user=user,
            defaults={"role": invitation.role, "status": "active"},
        )
        invitation.status = "accepted"
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["status", "accepted_at"])
        return Response({"accepted": True, "workspace": _workspace_payload(invitation.organization, user)})


class CourseCollectionView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        user = _current_user(request)
        managed_courses = _manageable_courses(user)
        courses = (
            Course.objects.select_related("organization", "instructor")
            .filter(
                Q(pk__in=managed_courses.values("pk"))
                | Q(enrollments__profile=profile, enrollments__status="active")
            )
            .distinct()
            .order_by("title")
        )
        return Response({"courses": [_course_payload(course, profile) for course in courses]})

    def post(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        body = _body(request)
        workspace = Organization.objects.filter(organization_id=body.get("workspaceId")).first()
        if not workspace:
            return _error("Choose a valid workspace for the course.", "not_found", 404)
        user = _current_user(request)
        member = _membership(user, workspace)
        if not member or member.role not in {"owner", "institution_admin", "instructor"}:
            return _error("Instructor access is required to create a course.", "forbidden", 403)
        title = str(body.get("title", "")).strip()
        if not title or len(title) > 240:
            return _error("Course title is required and must be 240 characters or fewer.")
        course = Course.objects.create(
            organization=workspace,
            instructor=user,
            title=title,
            description=str(body.get("description", ""))[:4000],
            status=str(body.get("status", "draft")) if str(body.get("status", "draft")) in {"draft", "published", "archived"} else "draft",
            route=body.get("route") if isinstance(body.get("route"), dict) else {},
            source_policy=body.get("sourcePolicy") if isinstance(body.get("sourcePolicy"), dict) else {"approvedSourcesOnly": True},
        )
        return Response(_course_payload(course, profile), status=status.HTTP_201_CREATED)


class CourseDetailView(LearningOsAPIView):
    def get(self, request, course_id):
        profile, error = _require_profile(request)
        if error:
            return error
        course = Course.objects.select_related("organization", "instructor").filter(course_id=course_id).first()
        if not course:
            return _error("Unknown course", "not_found", 404)
        user = _current_user(request)
        enrolled = Enrollment.objects.filter(course=course, profile=profile, status="active").exists()
        if not (_can_manage_course(user, course) or enrolled):
            return _error("Join this course before opening its workspace.", "forbidden", 403)
        return Response({**_course_payload(course, profile), "sourcePacks": [{"sourcePackId": pack.lesson_id, "title": pack.title, "approved": pack.approved} for pack in course.source_packs.all()]})

    def patch(self, request, course_id):
        profile, error = _require_profile(request)
        if error:
            return error
        course = Course.objects.select_related("organization", "instructor").filter(course_id=course_id).first()
        if not course:
            return _error("Unknown course", "not_found", 404)
        if not _can_manage_course(_current_user(request), course):
            return _error("Instructor access is required to update a course.", "forbidden", 403)
        body = _body(request)
        for source, target, limit in (("title", "title", 240), ("description", "description", 4000), ("status", "status", 32)):
            if source in body and isinstance(body[source], str):
                setattr(course, target, body[source].strip()[:limit])
        if isinstance(body.get("route"), dict):
            course.route = body["route"]
        if isinstance(body.get("sourcePolicy"), dict):
            course.source_policy = body["sourcePolicy"]
        course.save()
        return Response(_course_payload(course, profile))


class CourseJoinView(LearningOsAPIView):
    def post(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        code = str(_body(request).get("joinCode", "")).strip().upper()
        course = Course.objects.select_related("organization", "instructor").filter(join_code=code, status="published").first()
        if not course:
            return _error("This course code is invalid or the course is not open for enrollment.", "not_found", 404)
        user = _current_user(request)
        Membership.objects.get_or_create(organization=course.organization, user=user, defaults={"role": "learner", "status": "active"})
        enrollment, _ = Enrollment.objects.update_or_create(course=course, profile=profile, defaults={"status": "active"})
        return Response({"enrollmentId": str(enrollment.enrollment_id), "course": _course_payload(course, profile)}, status=status.HTTP_201_CREATED)


class CourseSourcePackView(LearningOsAPIView):
    def get(self, request, course_id):
        profile, error = _require_profile(request)
        if error:
            return error
        course = Course.objects.select_related("organization").filter(course_id=course_id).first()
        if not course:
            return _error("Unknown course", "not_found", 404)
        if not _can_manage_course(_current_user(request), course):
            return _error("Instructor access is required to manage course sources.", "forbidden", 403)
        return Response({"sourcePacks": [{"sourcePackId": pack.lesson_id, "title": pack.title, "description": pack.description, "approved": pack.approved} for pack in course.source_packs.all()]})

    def post(self, request, course_id):
        profile, error = _require_profile(request)
        if error:
            return error
        course = Course.objects.select_related("organization").filter(course_id=course_id).first()
        if not course:
            return _error("Unknown course", "not_found", 404)
        if not _can_manage_course(_current_user(request), course):
            return _error("Instructor access is required to manage course sources.", "forbidden", 403)
        source_pack_ids = _body(request).get("sourcePackIds")
        if not isinstance(source_pack_ids, list) or not all(isinstance(item, str) for item in source_pack_ids):
            return _error("sourcePackIds must be a list of source pack identifiers.")
        packs = list(SourcePack.objects.filter(lesson_id__in=source_pack_ids, approved=True))
        if len(packs) != len(set(source_pack_ids)):
            return _error("Every course source must be an approved source pack.", "source_not_approved", 422)
        course.source_packs.set(packs)
        return Response({"sourcePacks": [{"sourcePackId": pack.lesson_id, "title": pack.title, "approved": pack.approved} for pack in packs]})


class GoalContractPreviewView(LearningOsAPIView):
    """Draft a goal-specific contract before the learner confirms it."""

    def post(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        body = _body(request)
        title = str(body.get("title") or "").strip()
        description = str(body.get("description") or "").strip()
        outcome = str(body.get("outcome") or "").strip()
        current_level = str(body.get("currentLevel") or "beginner").strip()
        time_budget = str(body.get("timeBudget") or "Flexible").strip()
        if not title or len(title) > 240:
            return _error("Tell Feynman what you want to learn in 240 characters or fewer.")
        if current_level not in {"beginner", "intermediate", "advanced"}:
            return _error("currentLevel must be beginner, intermediate, or advanced.")
        domain, safety_mode, verification_mode, _ = _classify_goal(title, description)
        requested_category = _classify_requested_category(body.get("category"), title, description)
        if requested_category:
            domain, safety_mode, verification_mode, _ = requested_category
        base = _build_contract(title, description, outcome, current_level, time_budget, domain, safety_mode, verification_mode)
        provider_name, provider_model = _active_provider_metadata()
        try:
            generated = provider_for().generate_learning_contract({
                "title": title,
                "description": description,
                "outcome": outcome,
                "currentLevel": current_level,
                "timeBudget": time_budget,
                "domain": domain,
            })
            contract = _apply_generated_contract(base, generated, domain=domain)
            provider_mode = str(generated.get("providerMode") or "")
            if provider_mode == "live_fireworks_fallback":
                provider_name = "fireworks"
                provider_model = str(getattr(settings, "FIREWORKS_MODEL", ""))
            return Response({"contract": contract, "domain": domain, "provider": provider_name, "model": provider_model, "providerMode": provider_mode or None, "generated": True})
        except (ProviderUnavailable, ProviderOutputError):
            # The contract remains editable and honest if the model is down;
            # this fallback is domain-specific and never presented as GPT output.
            return Response({
                "contract": base,
                "domain": domain,
                "provider": provider_name,
                "model": provider_model,
                "generated": False,
                "providerMessage": "The language model was unavailable, so Feynman prepared a domain-specific starter contract for you to edit.",
            })


class GoalCollectionView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        goals = LearningGoal.objects.filter(profile=profile).order_by("-updated_at")
        return Response({"goals": [_goal_payload(goal) for goal in goals]})

    def post(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        body = _body(request)
        title = str(body.get("title", "")).strip()
        description = str(body.get("description", "")).strip()
        outcome = str(body.get("outcome", "")).strip()
        current_level = str(body.get("currentLevel", "beginner"))
        time_budget = str(body.get("timeBudget", ""))
        if not title or len(title) > 240:
            return _error("Tell Feynman what you want to learn in 240 characters or fewer.")
        if current_level not in {"beginner", "intermediate", "advanced"}:
            return _error("currentLevel must be beginner, intermediate, or advanced.")
        domain, safety_mode, verification_mode, next_action = _classify_goal(title, description)
        requested_category = _classify_requested_category(body.get("category"), title, description)
        if requested_category:
            domain, safety_mode, verification_mode, next_action = requested_category
        workspace = profile.workspace
        course = None
        course_id = body.get("courseId")
        if course_id:
            course = Course.objects.filter(course_id=course_id).first()
            if not course or not Enrollment.objects.filter(course=course, profile=profile, status="active").exists():
                return _error("Join the course before attaching a personal goal to it.", "forbidden", 403)
            workspace = course.organization
        contract = _build_contract(title, description, outcome, current_level, time_budget, domain, safety_mode, verification_mode)
        contract, runtime, contract_error = _apply_contract_overrides(contract, body.get("contract"), domain=domain)
        if contract_error:
            return contract_error
        outcome = str(runtime.get("outcome", outcome))[:500]
        current_level = str(runtime.get("current_level", current_level))
        time_budget = str(runtime.get("time_budget", time_budget))[:80]
        safety_mode = str(runtime.get("safety_mode", safety_mode))
        verification_mode = str(runtime.get("verification_mode", verification_mode))
        source_mode = str(runtime.get("source_mode", "required" if safety_mode == "academic_source_bound" else "optional"))
        if "sourceMode" in body:
            requested_source_mode = body["sourceMode"]
            if requested_source_mode not in {"optional", "required"}:
                return _error("sourceMode must be optional or required.")
            if source_mode == "required" and requested_source_mode != "required":
                return _error("This contract requires source-backed verification.", "source_mode_required")
            source_mode = requested_source_mode
        with transaction.atomic():
            goal = LearningGoal.objects.create(
                profile=profile,
                workspace=workspace,
                course=course,
                title=title,
                description=description[:4000],
                outcome=outcome[:500],
                domain=domain,
                current_level=current_level,
                time_budget=time_budget[:80],
                source_mode=source_mode,
                safety_mode=safety_mode,
                verification_mode=verification_mode,
                status="contract_ready",
                contract=contract,
                route={"schemaVersion": "adaptive-route.v1", "mode": "guided", "state": "contract_ready", "currentPosition": 1},
                next_action=str(contract["firstTask"]),
            )
            activities = []
            for position, item in enumerate(
                activity_contracts_for_goal(
                    title=title,
                    domain=domain,
                    prerequisites=contract["prerequisites"],
                    requires_source=goal.source_mode == "required",
                    first_prompt=str(contract["firstTask"]),
                ),
                start=1,
            ):
                activities.append(LearningActivity.objects.create(
                    goal=goal,
                    activity_type=item["type"],
                    title=item["title"],
                    prompt=item["prompt"],
                    position=position,
                    difficulty=item["difficulty"],
                    prerequisites=item["prerequisites"],
                    configuration=item["configuration"],
                    remediation_target=item["remediationTarget"],
                    transfer_target=item["transferTarget"],
                    evaluator={
                        "mode": "source_backed" if goal.source_mode == "required" else "guided_observation",
                        "requiresSource": goal.source_mode == "required",
                        "minimumResponseCharacters": 160,
                    },
                ))
            goal.route = {
                "schemaVersion": "adaptive-route.v1",
                "mode": "guided",
                "state": "contract_ready",
                "currentPosition": 1,
                "activeActivityId": str(activities[0].activity_id),
                "nextAction": "start_activity",
            }
            goal.save(update_fields=["route", "updated_at"])
        return Response(_goal_payload(goal, include_route=True), status=status.HTTP_201_CREATED)


class GoalDetailView(LearningOsAPIView):
    def get(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        return Response(_goal_payload(goal, include_route=True))

    def patch(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        body = _body(request)
        updated_contract, runtime, contract_error = _apply_contract_overrides(goal.contract, body.get("contract"), domain=goal.domain)
        if contract_error:
            return contract_error
        goal.contract = updated_contract
        for source, target, limit in (("title", "title", 240), ("description", "description", 4000), ("outcome", "outcome", 500), ("timeBudget", "time_budget", 80)):
            if source in body and isinstance(body[source], str):
                setattr(goal, target, body[source].strip()[:limit])
        for target, value in runtime.items():
            setattr(goal, target, value)
        if "sourceMode" in body:
            requested_source_mode = body["sourceMode"]
            if requested_source_mode not in {"optional", "required"}:
                return _error("sourceMode must be optional or required.")
            contract_requires_sources = goal.domain in {"medical", "finance"} or goal.contract.get("verificationMode") == "source_backed" or goal.contract.get("safetyMode") == "academic_source_bound"
            if contract_requires_sources and requested_source_mode != "required":
                return _error("This contract requires source-backed verification.", "source_mode_required")
            goal.source_mode = requested_source_mode
        if "outcome" in body and isinstance(body["outcome"], str):
            goal.contract = {**goal.contract, "intendedCapability": goal.outcome or goal.title}
        if "timeBudget" in body and isinstance(body["timeBudget"], str):
            goal.contract = {**goal.contract, "timeBudget": goal.time_budget or "Flexible"}
        first_activity = goal.activities.order_by("position", "id").first()
        if first_activity:
            first_activity.prompt = str(goal.contract.get("firstTask") or first_activity.prompt)
            first_activity.prerequisites = goal.contract.get("prerequisites") if isinstance(goal.contract.get("prerequisites"), list) else []
            evaluator = dict(first_activity.evaluator) if isinstance(first_activity.evaluator, dict) else {}
            evaluator.update({"mode": "source_backed" if goal.source_mode == "required" else "guided_observation", "requiresSource": goal.source_mode == "required"})
            first_activity.evaluator = evaluator
            first_activity.save(update_fields=["prompt", "prerequisites", "evaluator", "updated_at"])
        for activity in goal.activities.exclude(pk=first_activity.pk if first_activity else None):
            evaluator = dict(activity.evaluator) if isinstance(activity.evaluator, dict) else {}
            evaluator.update({"mode": "source_backed" if goal.source_mode == "required" else "guided_observation", "requiresSource": goal.source_mode == "required"})
            activity.evaluator = evaluator
            activity.save(update_fields=["evaluator", "updated_at"])
        if goal.status == "contract_ready" or (first_activity and first_activity.status != "completed"):
            goal.next_action = str(goal.contract.get("firstTask") or goal.next_action)
        if body.get("confirmContract") is True:
            goal.status = "active"
            goal.route = {**goal.route, "state": "active"}
        goal.save()
        return Response(_goal_payload(goal, include_route=True))


def _goal_share_snapshot(goal: LearningGoal) -> dict[str, Any]:
    sources = []
    for notebook in goal.notebooks.prefetch_related("notebook_sources").all():
        sources.append({
            "title": notebook.title,
            "subject": notebook.subject,
            "description": notebook.description,
            "status": notebook.status,
            "sources": [{
                "sourceId": source.source_id,
                "title": source.title,
                "sourceKind": source.source_kind,
                "filename": source.filename,
                "mimeType": source.mime_type,
                "status": source.status,
                "groundingEnabled": source.grounding_enabled,
                "extractionMethod": source.extraction_method,
                "extraction": source.extraction,
                "blocks": source.blocks,
                "assets": source.assets,
            } for source in notebook.notebook_sources.all()],
        })
    activities = []
    for activity in goal.activities.exclude(status="stale").order_by("position", "id"):
        activities.append({
            "activityType": activity.activity_type,
            "title": activity.title,
            "prompt": activity.prompt,
            "position": activity.position,
            "difficulty": activity.difficulty,
            "prerequisites": activity.prerequisites,
            "configuration": activity.configuration,
            "remediationTarget": activity.remediation_target,
            "transferTarget": activity.transfer_target,
            "sourceIds": activity.source_ids,
            "evaluator": activity.evaluator,
        })
    return {"goal": {"title": goal.title, "description": goal.description, "domain": goal.domain, "outcome": goal.outcome, "currentLevel": goal.current_level, "timeBudget": goal.time_budget, "sourceMode": goal.source_mode, "safetyMode": goal.safety_mode, "verificationMode": goal.verification_mode, "contract": goal.contract}, "activities": activities, "sources": sources}


class GoalShareCreateView(LearningOsAPIView):
    def post(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        share = GoalShare.objects.create(goal=goal, profile=profile, snapshot=_goal_share_snapshot(goal), active=True)
        return Response({"shareId": str(share.share_id), "token": str(share.token), "active": share.active}, status=status.HTTP_201_CREATED)


class SharedGoalDetailView(APIView):
    def get(self, request, token):
        share = GoalShare.objects.filter(token=token, active=True).select_related("goal").first()
        if not share:
            return _error("This shared learning route is no longer available.", "not_found", 404)
        snapshot = share.snapshot if isinstance(share.snapshot, dict) else {}
        goal = snapshot.get("goal") if isinstance(snapshot.get("goal"), dict) else {}
        sources = snapshot.get("sources") if isinstance(snapshot.get("sources"), list) else []
        activities = snapshot.get("activities") if isinstance(snapshot.get("activities"), list) else []
        return Response({"shareId": str(share.share_id), "token": str(share.token), "title": goal.get("title", share.goal.title), "domain": goal.get("domain", share.goal.domain), "outcome": goal.get("outcome", ""), "currentLevel": goal.get("currentLevel", "beginner"), "activityCount": len(activities), "sourceCount": sum(len(item.get("sources", [])) for item in sources if isinstance(item, dict)), "sourceTitles": [item.get("title") for item in sources if isinstance(item, dict) and item.get("title")], "active": share.active})


class SharedGoalCloneView(LearningOsAPIView):
    def post(self, request, token):
        profile, error = _require_profile(request)
        if error:
            return error
        share = GoalShare.objects.filter(token=token, active=True).first()
        if not share:
            return _error("This shared learning route is no longer available.", "not_found", 404)
        snapshot = share.snapshot if isinstance(share.snapshot, dict) else {}
        raw_goal = snapshot.get("goal") if isinstance(snapshot.get("goal"), dict) else {}
        activities = snapshot.get("activities") if isinstance(snapshot.get("activities"), list) else []
        workspace = _ensure_personal_workspace(profile)
        with transaction.atomic():
            goal = LearningGoal.objects.create(profile=profile, workspace=workspace, title=str(raw_goal.get("title") or "Shared learning route")[:240], description=str(raw_goal.get("description") or ""), domain=str(raw_goal.get("domain") or "general"), outcome=str(raw_goal.get("outcome") or "")[:500], current_level=str(raw_goal.get("currentLevel") or "beginner"), time_budget=str(raw_goal.get("timeBudget") or "Flexible")[:80], source_mode=str(raw_goal.get("sourceMode") or "optional"), safety_mode=str(raw_goal.get("safetyMode") or "guided"), verification_mode=str(raw_goal.get("verificationMode") or "guided"), status="active", contract=raw_goal.get("contract") if isinstance(raw_goal.get("contract"), dict) else {}, route={"schemaVersion": "adaptive-route.v1", "mode": "shared_template", "state": "active", "currentPosition": 1}, next_action="Start the first shared activity.")
            created = []
            for index, item in enumerate(activities, start=1):
                if not isinstance(item, dict):
                    continue
                created.append(LearningActivity.objects.create(goal=goal, activity_type=str(item.get("activityType") or "explain"), title=str(item.get("title") or "Shared activity")[:240], prompt=str(item.get("prompt") or "Make an observable attempt.")[:4000], position=int(item.get("position") or index), difficulty=int(item.get("difficulty") or 1), prerequisites=item.get("prerequisites") if isinstance(item.get("prerequisites"), list) else [], configuration=item.get("configuration") if isinstance(item.get("configuration"), dict) else {}, remediation_target=str(item.get("remediationTarget") or ""), transfer_target=str(item.get("transferTarget") or ""), source_ids=item.get("sourceIds") if isinstance(item.get("sourceIds"), list) else [], evaluator=item.get("evaluator") if isinstance(item.get("evaluator"), dict) else {"mode": "guided_observation", "minimumResponseCharacters": 160}))
            if created:
                goal.route = {"schemaVersion": "adaptive-route.v1", "mode": "shared_template", "state": "active", "currentPosition": 1, "activeActivityId": str(created[0].activity_id), "nextAction": "start_activity"}
                goal.save(update_fields=["route", "updated_at"])
            for notebook_data in snapshot.get("sources", []) if isinstance(snapshot.get("sources"), list) else []:
                if not isinstance(notebook_data, dict):
                    continue
                notebook = Notebook.objects.create(title=str(notebook_data.get("title") or "Shared source desk")[:240], subject=str(notebook_data.get("subject") or goal.domain)[:240], description=str(notebook_data.get("description") or ""), learning_goal="understand", status=str(notebook_data.get("status") or "ready"), owner_profile=profile, workspace=workspace, goal=goal)
                for source_data in notebook_data.get("sources", []) if isinstance(notebook_data.get("sources"), list) else []:
                    if not isinstance(source_data, dict):
                        continue
                    source_id = f"shared_{uuid.uuid4().hex}"
                    NotebookSource.objects.create(source_id=source_id, notebook=notebook, title=str(source_data.get("title") or "Shared source")[:240], source_kind=str(source_data.get("sourceKind") or "reference"), filename=str(source_data.get("filename") or ""), mime_type=str(source_data.get("mimeType") or ""), status=str(source_data.get("status") or "ready"), grounding_enabled=bool(source_data.get("groundingEnabled", True)), extraction_method=str(source_data.get("extractionMethod") or "shared_snapshot"), extraction=source_data.get("extraction") if isinstance(source_data.get("extraction"), dict) else {}, blocks=source_data.get("blocks") if isinstance(source_data.get("blocks"), list) else [], assets=source_data.get("assets") if isinstance(source_data.get("assets"), list) else [])
        return Response(_goal_payload(goal, include_route=True), status=status.HTTP_201_CREATED)

class GoalRouteView(LearningOsAPIView):
    def get(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        active_activities = goal.activities.exclude(status="stale").order_by("position", "id")
        return Response({"goalId": str(goal.goal_id), "status": goal.status, "contract": goal.contract, "route": goal.route, "nextAction": goal.next_action, "activities": [_activity_payload(activity) for activity in active_activities]})


class GoalSourceDockView(LearningOsAPIView):
    def get(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        return Response(_goal_source_payload(goal, profile))

    def post(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        notebook_id = _body(request).get("notebookId")
        try:
            notebook_uuid = uuid.UUID(str(notebook_id))
        except (TypeError, ValueError, AttributeError):
            return _error("notebookId must identify one of your notebooks.")
        notebook = Notebook.objects.filter(notebook_id=notebook_uuid, owner_profile=profile).first()
        if not notebook:
            return _error("Notebook not found.", "not_found", 404)
        if notebook.goal_id and notebook.goal_id != goal.id:
            return _error(
                "A notebook can be attached to only one learning goal at a time. Detach it from its current goal before moving it.",
                "notebook_already_attached",
                409,
            )
        if notebook.course_id != goal.course_id and (notebook.course_id or goal.course_id):
            return _error(
                "A course-attached source context can only be linked to a learning goal in that same course.",
                "course_goal_mismatch",
            )
        notebook.goal = goal
        notebook.workspace = goal.workspace
        notebook.course = goal.course
        notebook.save(update_fields=["goal", "workspace", "course", "updated_at"])
        return Response(_goal_source_payload(goal, profile))


class GoalCurriculumView(LearningOsAPIView):
    """Compile or retrieve the source-grounded curriculum for a goal."""

    def _goal(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return None, profile, error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return None, profile, _error("Unknown learning goal", "not_found", 404)
        return goal, profile, None

    def get(self, request, goal_id):
        goal, profile, error = self._goal(request, goal_id)
        if error:
            return error
        pack = CurriculumPack.objects.filter(goal=goal).order_by("-version").first()
        if not pack:
            return _error("This goal has no compiled curriculum yet.", "curriculum_not_compiled", 404)
        ready_sources = _ready_goal_sources(goal, profile)
        if curriculum_is_stale(pack, ready_sources):
            pack.status = "stale"
            pack.save(update_fields=["status", "updated_at"])
            pack.versions.filter(status="active").update(status="stale")
            route = GoalCurriculumRoute.objects.filter(goal=goal).first()
            if route:
                route.state = "stale"
                route.invalid_reason = "Selected source context changed or was deleted; recompile before continuing."
                route.save(update_fields=["state", "invalid_reason", "updated_at"])
            return Response({"curriculum": {"packId": str(pack.pack_id), "status": "stale", "sourceIds": pack.source_ids, "sourceAnchorIds": pack.source_anchor_ids}, "route": goal.route})
        version = pack.versions.filter(status="active").order_by("-version").first() or pack.versions.order_by("-version").first()
        route = GoalCurriculumRoute.objects.filter(goal=goal).first()
        if not version or not route:
            return _error("The curriculum linkage is incomplete; recompile this goal.", "curriculum_linkage_incomplete", 409)
        from .curriculum_compiler import _materialize_payload
        return Response({"curriculum": _materialize_payload(pack, version, route), "goal": _goal_payload(goal, include_route=True)})

    def post(self, request, goal_id):
        goal, profile, error = self._goal(request, goal_id)
        if error:
            return error
        body = _body(request)
        source_ids = body.get("sourceIds")
        if source_ids is not None and (not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids)):
            return _error("sourceIds must be an array of selected ready source identifiers.")
        ready_sources = _ready_goal_sources(goal, profile)
        if source_ids is None:
            selected = ready_sources
        else:
            requested = list(dict.fromkeys(item.strip() for item in source_ids if item.strip()))
            selected = [source for source in ready_sources if source.source_id in requested]
            if len(selected) != len(requested):
                return _error("Every selected source must be ready, grounding-enabled, owned by you, and attached to this goal.", "invalid_source_scope")
        learner_level = str(body.get("learnerLevel") or goal.current_level)
        try:
            curriculum = compile_curriculum(goal, learner_level, selected)
        except CurriculumCompileError as exc:
            return _error(str(exc), exc.code)
        return Response({"curriculum": curriculum, "goal": _goal_payload(goal, include_route=True)}, status=status.HTTP_201_CREATED)

    def patch(self, request, goal_id):
        """Accept a learner-edited route preview without mutating the source graph."""
        goal, profile, error = self._goal(request, goal_id)
        if error:
            return error
        route = GoalCurriculumRoute.objects.filter(goal=goal).select_related("curriculum").first()
        if not route or not route.curriculum:
            return _error("Compile a curriculum before editing its route.", "curriculum_not_compiled", 404)
        body = _body(request)
        active_activities = list(LearningActivity.objects.filter(goal=goal).exclude(status="stale").order_by("position", "id"))
        requested_order = body.get("activityOrder")
        if requested_order is not None:
            if not isinstance(requested_order, list) or not all(isinstance(item, str) for item in requested_order):
                return _error("activityOrder must be an array of activity IDs.", "invalid_route_edit")
            by_id = {str(activity.activity_id): activity for activity in active_activities}
            if set(requested_order) != set(by_id) or len(requested_order) != len(by_id):
                return _error("Route edits must include every active activity exactly once.", "invalid_route_edit")
            for position, activity_id in enumerate(requested_order, start=1):
                activity = by_id[activity_id]
                activity.position = position
                activity.save(update_fields=["position", "updated_at"])
            active_activities = [by_id[activity_id] for activity_id in requested_order]
            route.route = {**(route.route if isinstance(route.route, dict) else {}), "activityOrder": requested_order, "routeEdited": True}
        approval_state = str(body.get("approvalState") or "").strip().lower()
        if approval_state:
            if approval_state not in {"pending", "approved"}:
                return _error("approvalState must be pending or approved.", "invalid_approval_state")
            if approval_state == "approved" and goal.course_id and not _can_manage_course(request.user, goal.course):
                return _error("Only the assigned course instructor or institution admin can approve this curriculum.", "instructor_approval_required", 403)
            route.route = {**(route.route if isinstance(route.route, dict) else {}), "approvalState": approval_state}
        if isinstance(body.get("learnerNote"), str):
            route.route = {**(route.route if isinstance(route.route, dict) else {}), "learnerNote": body["learnerNote"].strip()[:600]}
        route.route = {**(route.route if isinstance(route.route, dict) else {}), "previewAvailable": True}
        route.active_activity = route.curriculum.activity_definitions.filter(position=active_activities[0].position).first() if active_activities else None
        route.next_action = "start_activity"
        route.save(update_fields=["route", "active_activity", "next_action", "updated_at"])
        goal.route = route.route
        goal.save(update_fields=["route", "updated_at"])
        from .curriculum_compiler import _materialize_payload
        pack = route.curriculum.curriculum
        return Response({"curriculum": _materialize_payload(pack, route.curriculum, route), "goal": _goal_payload(goal, include_route=True)})


class GoalActivityAttemptView(LearningOsAPIView):
    def post(self, request, goal_id):
        profile, error = _require_profile(request)
        if error:
            return error
        goal = LearningGoal.objects.filter(goal_id=goal_id, profile=profile).first()
        if not goal:
            return _error("Unknown learning goal", "not_found", 404)
        body = _body(request)
        activity = LearningActivity.objects.filter(activity_id=body.get("activityId"), goal=goal).first()
        if not activity:
            return _error("Choose an activity from this learning goal.", "not_found", 404)
        try:
            structured_attempt = normalize_structured_attempt(body)
        except ValueError as exc:
            return _error(str(exc), "invalid_structured_attempt")
        response_text = structured_attempt["writtenExplanation"]
        observable_text = f"{response_text} {structured_attempt['learnerConclusion']}".strip()
        if len(observable_text) < 24 and not structured_attempt["interactionState"]:
            return _error("Submit a meaningful explanation or a structured observable interaction.")
        boundary = personal_decision_boundary(goal.domain, observable_text)
        if boundary:
            return _error(boundary, "educational_boundary")
        selected_source_ids, anchor_ids, source_error = _validated_attempt_source_scope(goal, profile, body)
        if source_error:
            return source_error
        word_count = len(observable_text.split())
        configuration = activity.configuration if isinstance(activity.configuration, dict) else {}
        if not configuration:
            configuration = {
                "schemaVersion": "activity.v1",
                "activityType": activity.activity_type,
                "domain": goal.domain,
                "concept": goal.outcome or goal.title,
                "interactiveControls": [],
                "sourceRequirements": {"mode": "required" if activity.evaluator.get("requiresSource") else "optional"},
                "remediationTarget": activity.remediation_target or "Return to the prerequisite and use one bounded example.",
                "transferTarget": activity.transfer_target or "Apply the concept to a nearby case.",
            }
        requires_source = bool((configuration.get("sourceRequirements") or {}).get("mode") == "required")
        feedback, evaluation = _activity_provider_feedback(
            goal=goal,
            activity=activity,
            profile=profile,
            response_text=observable_text,
            selected_source_ids=selected_source_ids,
            anchor_ids=anchor_ids,
            confidence=structured_attempt.get("confidence"),
            structured_attempt=structured_attempt,
        )
        provider_attempt = str(feedback.get("providerAttempt") or "not_configured")
        decision = deterministic_evaluation(
            configuration=configuration,
            attempt=structured_attempt,
            source_ids=selected_source_ids,
            anchor_ids=anchor_ids,
            provider_failed=provider_attempt == "failed",
        )
        # A provider may explain its own bounded judgement, but deterministic
        # evidence and source rules own the state transition.  Malformed or
        # incomplete provider output can only lower certainty, never verify.
        if evaluation is not None and evaluation.get("state") != "complete":
            decision["evidenceStatus"] = "needs_review"
        evidence_status = str(decision["evidenceStatus"])
        # Backwards-compatible local source verification remains explicit and
        # deterministic: selected ready sources + validated anchors + a
        # substantive explanation can verify evidence even with no provider.
        if (
            selected_source_ids
            and anchor_ids
            and word_count >= 30
            and decision["score"] >= 0.65
            and provider_attempt != "failed"
            and (evaluation is None or evaluation.get("state") == "complete")
        ):
            evidence_status = "verified"
        if evaluation and evaluation.get("feedback"):
            summary = str(evaluation["feedback"])[:2000]
        elif provider_attempt == "failed":
            summary = "The structured attempt was saved, but provider feedback failed and it is not verified. Retry when the provider is available."
        else:
            summary = {
                "advance": "Structured observable evidence supports the next activity.",
                "increase_difficulty": "Strong structured evidence supports a more difficult next activity.",
                "retry": "Record the missing observable evidence, then retry this activity.",
                "simplify_task": "A simpler bounded task is recommended before advancing.",
                "remediate_prerequisite": "A prerequisite remediation task is recommended before advancing.",
                "add_worked_example": "A worked example is recommended before the next independent attempt.",
                "request_source_backed_verification": "Select a ready source and a durable anchor before this activity can be verified.",
                "require_human_review": "This attempt was saved for human review.",
            }.get(str(decision["action"]), "Observable learner evidence was recorded.")
        attempt_record = ActivityAttempt.objects.create(
            profile=profile,
            goal=goal,
            activity=activity,
            written_explanation=response_text,
            learner_conclusion=structured_attempt["learnerConclusion"],
            confidence=structured_attempt["confidence"],
            prediction=structured_attempt["prediction"],
            interaction_state={**structured_attempt["interactionState"], "simulationParameters": structured_attempt["simulationParameters"]},
            selected_options=structured_attempt["selectedOptions"],
            calculations=structured_attempt["calculations"],
            trace=structured_attempt["trace"],
            source_ids=selected_source_ids,
            source_anchor_ids=anchor_ids,
            evaluation={"decision": decision, "provider": feedback},
        )
        evidence = EvidenceRecord.objects.create(
            profile=profile,
            goal=goal,
            activity=activity,
            capability=activity.title,
            evidence_type=activity.activity_type,
            status=evidence_status,
            score=decision["score"],
            summary=summary,
            rubric={
                "wordCount": word_count,
                "structuredAttemptId": str(attempt_record.attempt_id),
                "structuredAttempt": structured_attempt,
                "sourceAnchored": bool(anchor_ids),
                "requiresSource": requires_source,
                "observedAttempt": True,
                "selectedSourceIds": selected_source_ids,
                "provider": feedback.get("provider"),
                "providerMode": feedback.get("providerMode"),
                "model": feedback.get("model"),
                "providerAttempt": provider_attempt,
                "providerFeedback": feedback.get("evaluation"),
                "providerErrorCategory": feedback.get("providerErrorCategory"),
                "uncertainty": feedback.get("uncertainty"),
                "deterministicDecision": decision,
            },
            transition_reason=str(decision["reason"]),
            source_anchor_ids=anchor_ids,
        )
        action = str(decision["action"])
        activity.status = "completed" if action in {"advance", "increase_difficulty"} else {
            "request_source_backed_verification": "needs_source",
            "require_human_review": "needs_human_review",
        }.get(action, "needs_revision")
        if selected_source_ids:
            activity.source_ids = selected_source_ids
            activity.save(update_fields=["source_ids", "status", "updated_at"])
        else:
            activity.save(update_fields=["status", "updated_at"])
        capability = str(configuration.get("concept") or goal.outcome or goal.title)[:240]
        capability_state, _ = CapabilityState.objects.get_or_create(profile=profile, goal=goal, capability=capability)
        capability_state.status = "demonstrated" if action in {"advance", "increase_difficulty"} else "developing"
        capability_state.confidence = structured_attempt["confidence"]
        capability_state.current_route_position = activity.position
        capability_state.next_action = action
        if evaluation and evaluation.get("mistake"):
            capability_state.misconceptions = [*capability_state.misconceptions[-9:], str(evaluation["mistake"])[:600]]
        if action not in {"advance", "increase_difficulty"}:
            capability_state.retry_history = [*capability_state.retry_history[-9:], {"activityId": str(activity.activity_id), "action": action, "reason": decision["reason"]}]
        else:
            capability_state.completed_attempt_ids = [*capability_state.completed_attempt_ids[-19:], str(attempt_record.attempt_id)]
        capability_state.save()

        next_activity = None
        if action in {"advance", "increase_difficulty"}:
            next_activity = goal.activities.filter(position__gt=activity.position, status="ready").order_by("position", "id").first()
            if not next_activity:
                action = "assign_transfer_task"
                decision["action"] = action
        if action in {"remediate_prerequisite", "add_worked_example", "simplify_task", "assign_transfer_task"}:
            target = activity.transfer_target if action == "assign_transfer_task" else activity.remediation_target
            next_activity = LearningActivity.objects.create(
                goal=goal,
                activity_type="transfer" if action == "assign_transfer_task" else "remediate",
                title="Transfer the demonstrated capability" if action == "assign_transfer_task" else "Rebuild the prerequisite",
                prompt=target or "Use a smaller bounded case and record what changes.",
                position=goal.activities.order_by("-position").first().position + 1,
                status="ready",
                difficulty=max(1, activity.difficulty - 1 if action in {"remediate_prerequisite", "simplify_task"} else activity.difficulty),
                prerequisites=activity.prerequisites,
                configuration={**configuration, "activityType": "transfer" if action == "assign_transfer_task" else "remediate", "adaptiveAction": action},
                remediation_target=activity.remediation_target,
                transfer_target=activity.transfer_target,
                evaluator=activity.evaluator,
            )
        goal.status = "active"
        goal.next_action = next_activity.prompt if next_activity else summary
        goal.route = next_route_state(
            current_position=next_activity.position if next_activity else activity.position,
            activity_id=str(activity.activity_id),
            decision=decision,
            next_activity_id=str(next_activity.activity_id) if next_activity else None,
            fallback_action="assign_transfer_task",
        )
        goal.save(update_fields=["status", "route", "next_action", "updated_at"])
        return Response({
            "evidence": _evidence_payload(evidence),
            "feedback": feedback,
            "adaptiveRoute": goal.route,
            "goal": _goal_payload(goal, include_route=True),
        })


class EvidenceCollectionView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        goal_id = request.query_params.get("goalId")
        queryset = EvidenceRecord.objects.select_related("goal", "activity").filter(profile=profile).order_by("-created_at")
        if goal_id:
            queryset = queryset.filter(goal__goal_id=goal_id)
        return Response({"evidence": [_evidence_payload(item) for item in queryset[:100]]})


class ShareGrantCollectionView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        grants = ShareGrant.objects.select_related("course").filter(profile=profile).order_by("-updated_at")
        return Response({"shares": [{"shareId": str(item.share_id), "courseId": str(item.course.course_id), "courseTitle": item.course.title, "evidenceIds": item.evidence_ids, "scope": item.scope, "active": item.active, "createdAt": item.created_at.isoformat()} for item in grants]})

    def post(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        body = _body(request)
        course = Course.objects.filter(course_id=body.get("courseId")).first()
        if not course or not Enrollment.objects.filter(course=course, profile=profile, status="active").exists():
            return _error("Join the course before sharing evidence with it.", "forbidden", 403)
        if not _course_sharing_enabled(profile):
            return _error("Enable course sharing in Privacy before granting instructor access.", "course_sharing_disabled", 403)
        evidence_ids = body.get("evidenceIds")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            return _error("Choose one or more evidence records to share.")
        owned = list(EvidenceRecord.objects.filter(profile=profile, evidence_id__in=evidence_ids).values_list("evidence_id", flat=True))
        if len(owned) != len(set(str(item) for item in evidence_ids)):
            return _error("Every shared record must belong to you.", "forbidden", 403)
        grant = ShareGrant.objects.create(profile=profile, course=course, evidence_ids=[str(item) for item in owned], scope="selected_evidence", active=True)
        return Response({"shareId": str(grant.share_id), "courseId": str(course.course_id), "evidenceIds": grant.evidence_ids, "active": grant.active}, status=status.HTTP_201_CREATED)


class ShareGrantDetailView(LearningOsAPIView):
    def delete(self, request, share_id):
        profile, error = _require_profile(request)
        if error:
            return error
        grant = ShareGrant.objects.filter(share_id=share_id, profile=profile).first()
        if not grant:
            return _error("Unknown evidence share", "not_found", 404)
        grant.active = False
        grant.save(update_fields=["active", "updated_at"])
        return Response({"shareId": str(grant.share_id), "active": False})


def _privacy_payload(profile: LearnerProfile) -> dict[str, Any]:
    active_grants = ShareGrant.objects.filter(profile=profile, active=True)
    return {
        "learnerMemoryEnabled": profile.memory_enabled,
        "notebookSourceRetention": "Raw uploads are discarded after extraction. Extracted source blocks and assets remain inside each notebook until the learner removes the source.",
        "courseSharingEnabled": _course_sharing_enabled(profile),
        "activeShares": active_grants.count(),
    }


class PrivacyView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        return Response(_privacy_payload(profile))

    def patch(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        body = _body(request)
        update_fields: list[str] = []
        if "learnerMemoryEnabled" in body:
            if not isinstance(body["learnerMemoryEnabled"], bool):
                return _error("learnerMemoryEnabled must be true or false.")
            profile.memory_enabled = body["learnerMemoryEnabled"]
            if not profile.memory_enabled:
                profile.memory_items.update(enabled=False)
            update_fields.append("memory_enabled")
        if "courseSharingEnabled" in body:
            if not isinstance(body["courseSharingEnabled"], bool):
                return _error("courseSharingEnabled must be true or false.")
            preferences = dict(profile.preferences) if isinstance(profile.preferences, dict) else {}
            privacy_preferences = dict(preferences.get("privacy")) if isinstance(preferences.get("privacy"), dict) else {}
            privacy_preferences["courseSharingEnabled"] = body["courseSharingEnabled"]
            preferences["privacy"] = privacy_preferences
            profile.preferences = preferences
            update_fields.append("preferences")
            if not body["courseSharingEnabled"]:
                ShareGrant.objects.filter(profile=profile, active=True).update(active=False, updated_at=timezone.now())
        if update_fields:
            profile.save(update_fields=[*update_fields, "updated_at"])
        return Response(_privacy_payload(profile))


class TeachDashboardView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        user = _current_user(request)
        courses = _manageable_courses(user).select_related("organization", "instructor").order_by("title")
        course_ids = list(courses.values_list("id", flat=True))
        now = timezone.now()
        active_grants = ShareGrant.objects.filter(course_id__in=course_ids, active=True).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        )
        shared_evidence_ids = {
            evidence_id
            for grant in active_grants
            for evidence_id in (grant.evidence_ids if isinstance(grant.evidence_ids, list) else [])
        }
        pending = EvidenceRecord.objects.filter(evidence_id__in=shared_evidence_ids, status="needs_review").count()
        source_approval_needed = SourcePack.objects.filter(courses__id__in=course_ids, approved=False).distinct().count()
        return Response({"courses": [_course_payload(course, profile) for course in courses], "pendingReviews": pending, "sourceApprovalNeeded": source_approval_needed})


class CourseCohortView(LearningOsAPIView):
    def get(self, request, course_id):
        profile, error = _require_profile(request)
        if error:
            return error
        course = Course.objects.select_related("organization").filter(course_id=course_id).first()
        if not course:
            return _error("Unknown course", "not_found", 404)
        if not _can_review_course_cohort(_current_user(request), course):
            return _error("Instructor access is required to view this cohort.", "forbidden", 403)
        learners = []
        now = timezone.now()
        for enrollment in course.enrollments.select_related("profile", "profile__account").filter(status="active"):
            grants = ShareGrant.objects.filter(profile=enrollment.profile, course=course, active=True).filter(expires_at__isnull=True) | ShareGrant.objects.filter(profile=enrollment.profile, course=course, active=True, expires_at__gt=now)
            shared_ids = {item for grant in grants for item in grant.evidence_ids}
            records = EvidenceRecord.objects.filter(profile=enrollment.profile, evidence_id__in=shared_ids).select_related("goal", "activity").order_by("-created_at")
            learners.append({"name": enrollment.profile.display_name or (enrollment.profile.account.first_name if enrollment.profile.account else "Learner"), "sharedEvidence": [_evidence_payload(record) for record in records]})
        return Response({"courseId": str(course.course_id), "learners": learners})


class InstitutionDashboardView(LearningOsAPIView):
    def get(self, request):
        profile, error = _require_profile(request)
        if error:
            return error
        workspace_id = request.query_params.get("workspaceId")
        workspace = Organization.objects.filter(organization_id=workspace_id).first() if workspace_id else profile.workspace
        if not workspace:
            return _error("Choose a workspace.", "not_found", 404)
        # A personal learner workspace is intentionally not an institution
        # governance surface.  Membership ownership of the personal workspace
        # must not grant access to aggregate institution metrics.
        if workspace.kind != "institution":
            return _error("Institution admin access is required.", "forbidden", 403)
        if not _can_manage_organization(_current_user(request), workspace):
            return _error("Institution admin access is required.", "forbidden", 403)
        courses = workspace.courses.all()
        return Response({
            "workspace": _workspace_payload(workspace, _current_user(request)),
            "memberCounts": {role: workspace.memberships.filter(role=role, status="active").count() for role in ("owner", "institution_admin", "instructor", "learner")},
            "courseCount": courses.count(),
            "activeEnrollmentCount": Enrollment.objects.filter(course__organization=workspace, status="active").count(),
            "verifiedEvidenceCount": EvidenceRecord.objects.filter(goal__workspace=workspace, status="verified").count(),
            "sourceGovernance": {"approved": SourcePack.objects.filter(courses__organization=workspace, approved=True).distinct().count(), "needsReview": SourcePack.objects.filter(courses__organization=workspace, approved=False).distinct().count()},
        })
