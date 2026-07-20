"""Source-grounded universal curriculum compiler.

The compiler accepts only server-owned, selected, ready notebook sources. A
provider may propose a richer graph, but the proposal is rejected unless every
concept and activity cites an allowed source anchor. The deterministic
fallback is intentionally useful for local development and provider outages.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from django.db import transaction

from .curriculum_adapters import GENERIC_ADAPTER, get_domain_adapter
from .models import (
    ActivityDefinition,
    ConceptNode,
    CurriculumPack,
    CurriculumVersion,
    EvaluationRubric,
    GoalCurriculumRoute,
    LearningActivity,
    LearningGoal,
    NotebookSource,
    PrerequisiteEdge,
)
from .providers import ProviderOutputError, ProviderUnavailable, provider_for


class CurriculumCompileError(ValueError):
    """A safe, user-facing curriculum compilation failure."""

    def __init__(self, message: str, code: str = "curriculum_compile_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceSpan:
    source_id: str
    anchor_id: str
    text: str
    page: int | None = None
    block_index: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "sourceAnchorId": self.anchor_id,
            "text": self.text[:1800],
            "page": self.page,
            "blockIndex": self.block_index,
        }


def _source_blocks(source: NotebookSource) -> list[dict[str, Any]]:
    blocks = source.blocks if isinstance(source.blocks, list) else []
    return [block for block in blocks if isinstance(block, dict)]


def source_spans(selected_sources: Iterable[NotebookSource]) -> list[SourceSpan]:
    spans: list[SourceSpan] = []
    for source in selected_sources:
        for index, block in enumerate(_source_blocks(source)):
            anchor = str(block.get("sourceAnchor") or block.get("sourceAnchorId") or block.get("anchorId") or "").strip()
            text = str(block.get("text") or block.get("content") or block.get("value") or block.get("markdown") or "").strip()
            if not anchor or not text:
                continue
            raw_page = block.get("page") or block.get("pageNumber")
            try:
                page = int(raw_page) if raw_page is not None else None
            except (TypeError, ValueError):
                page = None
            spans.append(SourceSpan(str(source.source_id), anchor, text, page, index))
    return spans


def source_fingerprint(selected_sources: Iterable[NotebookSource]) -> str:
    rows = []
    for source in sorted(selected_sources, key=lambda item: str(item.source_id)):
        rows.append({
            "sourceId": str(source.source_id),
            "status": source.status,
            "groundingEnabled": bool(source.grounding_enabled),
            "sha256": source.sha256,
            "updatedAt": source.updated_at.isoformat() if source.updated_at else None,
            "anchors": [span.anchor_id for span in source_spans([source])],
        })
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _ready_selected_sources(goal: LearningGoal, selected_sources: Iterable[NotebookSource] | None) -> list[NotebookSource]:
    requested = list(selected_sources or [])
    if not requested:
        return []
    source_ids = {str(source.source_id) for source in requested}
    attached = NotebookSource.objects.filter(
        source_id__in=source_ids,
        notebook__goal=goal,
        notebook__owner_profile=goal.profile,
        status="ready",
        grounding_enabled=True,
    ).select_related("notebook")
    by_id = {str(source.source_id): source for source in attached}
    if set(by_id) != source_ids:
        raise CurriculumCompileError("Select only ready, grounding-enabled sources attached to this goal.", "invalid_source_scope")
    return [by_id[source_id] for source_id in sorted(source_ids)]


def _short_title(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" .:-")
    if not cleaned:
        return fallback
    return cleaned[:160]


def _candidate_concepts(goal: LearningGoal, spans: list[SourceSpan]) -> list[dict[str, Any]]:
    """Extract bounded concept candidates without inventing unsupported facts."""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for span in spans:
        paragraphs = [part.strip() for part in re.split(r"\n{2,}|(?<=[.!?])\s+", span.text) if part.strip()]
        for paragraph in paragraphs[:2]:
            title = _short_title(paragraph.split(".", 1)[0], f"Source idea {len(candidates) + 1}")
            key = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:140] or f"concept-{len(candidates) + 1}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "key": key,
                "title": title,
                "description": paragraph[:900],
                "sourceIds": [span.source_id],
                "sourceAnchorIds": [span.anchor_id],
                "uncertainty": {"level": "provisional", "reason": "Inferred from a bounded source span."},
            })
            if len(candidates) >= 8:
                return candidates
    if candidates:
        return candidates
    raise CurriculumCompileError("The selected sources contain no ready text blocks to ground a curriculum.", "source_text_unavailable")


def _fallback_proposal(goal: LearningGoal, learner_level: str, spans: list[SourceSpan]) -> dict[str, Any]:
    concepts = _candidate_concepts(goal, spans)
    adapter = get_domain_adapter(goal.title, goal.domain)
    allowed_source_ids = sorted({span.source_id for span in spans})
    allowed_anchor_ids = [span.anchor_id for span in spans]
    edges = [
        {"prerequisite": concepts[index - 1]["key"], "dependent": concepts[index]["key"], "sourceAnchorIds": concepts[index]["sourceAnchorIds"]}
        for index in range(1, len(concepts))
    ]
    activity_types = adapter.curriculum_sequence or adapter.activity_sequence
    activities: list[dict[str, Any]] = []
    for index, activity_type in enumerate(activity_types):
        concept = concepts[min(index, len(concepts) - 1)]
        activities.append({
            "activityType": activity_type,
            "conceptKey": concept["key"],
            "title": f"{activity_type.replace('_', ' ').title()}: {concept['title']}",
            "prompt": (
                f"Using the selected source anchor, {activity_type.replace('_', ' ')} {concept['title']}. "
                "Record a prediction or observation, explain the relationship, and name one uncertainty."
            ),
            "difficulty": min(5, 1 + index // 2),
            "expectedObservations": list(adapter.expected_observations if adapter is not GENERIC_ADAPTER else GENERIC_ADAPTER.expected_observations),
            "evaluatorRubric": list(adapter.rubric if adapter is not GENERIC_ADAPTER else GENERIC_ADAPTER.rubric),
            "sourceIds": concept["sourceIds"],
            "sourceAnchorIds": concept["sourceAnchorIds"],
            "remediationTarget": adapter.remediation(concept["title"]),
            "transferTarget": adapter.transfer(concept["title"]),
        })
    return {
        "schemaVersion": "curriculum-proposal.v1",
        "domain": goal.domain or "general",
        "learnerLevel": learner_level,
        "concepts": concepts,
        "prerequisites": edges,
        "activities": activities,
        "uncertainty": {"level": "provisional", "reason": "Provider unavailable; concepts and activities were inferred only from selected ready source spans."},
    }


def _proposal_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schemaVersion", "domain", "learnerLevel", "concepts", "prerequisites", "activities", "uncertainty"],
        "properties": {
            "schemaVersion": {"type": "string"},
            "domain": {"type": "string", "minLength": 1, "maxLength": 120},
            "learnerLevel": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
            "concepts": {"type": "array", "minItems": 2, "maxItems": 12, "items": {"type": "object"}},
            "prerequisites": {"type": "array", "maxItems": 30, "items": {"type": "object"}},
            "activities": {"type": "array", "minItems": 4, "maxItems": 20, "items": {"type": "object"}},
            "uncertainty": {"type": "object"},
        },
    }


def _validate_proposal(raw: Any, *, allowed_source_ids: set[str], allowed_anchor_ids: set[str], goal: LearningGoal, learner_level: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProviderOutputError("Curriculum provider returned a non-object proposal.")
    required = {"concepts", "prerequisites", "activities", "uncertainty"}
    if not required.issubset(raw):
        raise ProviderOutputError("Curriculum provider omitted required proposal fields.")
    concepts = raw.get("concepts")
    activities = raw.get("activities")
    if not isinstance(concepts, list) or not 2 <= len(concepts) <= 12:
        raise ProviderOutputError("Curriculum proposal must contain two to twelve concepts.")
    if not isinstance(activities, list) or not 4 <= len(activities) <= 20:
        raise ProviderOutputError("Curriculum proposal must contain four to twenty observable activities.")

    concept_keys: set[str] = set()
    normalized_concepts: list[dict[str, Any]] = []
    for index, concept in enumerate(concepts):
        if not isinstance(concept, dict):
            raise ProviderOutputError("Every curriculum concept must be an object.")
        key = re.sub(r"[^a-z0-9]+", "-", str(concept.get("key") or concept.get("id") or "").casefold()).strip("-")[:140]
        title = str(concept.get("title") or "").strip()[:240]
        anchors = [str(item).strip() for item in concept.get("sourceAnchorIds", [])] if isinstance(concept.get("sourceAnchorIds"), list) else []
        source_ids = [str(item).strip() for item in concept.get("sourceIds", [])] if isinstance(concept.get("sourceIds"), list) else []
        if not key or not title or not anchors or not set(anchors).issubset(allowed_anchor_ids) or not set(source_ids).issubset(allowed_source_ids):
            raise ProviderOutputError("Every curriculum concept must cite selected source anchors.")
        if key in concept_keys:
            raise ProviderOutputError("Curriculum concept keys must be unique.")
        concept_keys.add(key)
        normalized_concepts.append({
            "key": key,
            "title": title,
            "description": str(concept.get("description") or concept.get("explanation") or "").strip()[:4000],
            "sourceIds": list(dict.fromkeys(source_ids)),
            "sourceAnchorIds": list(dict.fromkeys(anchors)),
            "uncertainty": concept.get("uncertainty") if isinstance(concept.get("uncertainty"), dict) else {},
            "position": index,
        })

    normalized_edges: list[dict[str, Any]] = []
    for edge in raw.get("prerequisites", []):
        if not isinstance(edge, dict):
            continue
        prerequisite = str(edge.get("prerequisite") or edge.get("from") or "").strip()
        dependent = str(edge.get("dependent") or edge.get("to") or "").strip()
        anchors = [str(item).strip() for item in edge.get("sourceAnchorIds", [])] if isinstance(edge.get("sourceAnchorIds"), list) else []
        if prerequisite not in concept_keys or dependent not in concept_keys or prerequisite == dependent or not set(anchors).issubset(allowed_anchor_ids):
            raise ProviderOutputError("Curriculum prerequisite edges must reference cited concepts and allowed anchors.")
        normalized_edges.append({"prerequisite": prerequisite, "dependent": dependent, "sourceAnchorIds": list(dict.fromkeys(anchors))})

    normalized_activities: list[dict[str, Any]] = []
    allowed_types = {"predict", "explain", "compare", "derive", "debug", "analyze", "simulate", "apply", "build", "transfer", "remediate"}
    for index, activity in enumerate(activities):
        if not isinstance(activity, dict):
            raise ProviderOutputError("Every curriculum activity must be an object.")
        activity_type = str(activity.get("activityType") or activity.get("type") or "").strip().casefold()
        concept_key = str(activity.get("conceptKey") or activity.get("concept") or "").strip()
        title = str(activity.get("title") or "").strip()[:240]
        prompt = str(activity.get("prompt") or "").strip()[:4000]
        anchors = [str(item).strip() for item in activity.get("sourceAnchorIds", [])] if isinstance(activity.get("sourceAnchorIds"), list) else []
        source_ids = [str(item).strip() for item in activity.get("sourceIds", [])] if isinstance(activity.get("sourceIds"), list) else []
        if activity_type not in allowed_types or concept_key not in concept_keys or not title or not prompt or not anchors:
            raise ProviderOutputError("Curriculum activities need an allowed type, concept, prompt, and citation.")
        if not set(anchors).issubset(allowed_anchor_ids) or not set(source_ids).issubset(allowed_source_ids):
            raise ProviderOutputError("Curriculum activity cites an unselected source anchor.")
        normalized_activities.append({
            "activityType": activity_type,
            "conceptKey": concept_key,
            "title": title,
            "prompt": prompt,
            "difficulty": max(1, min(int(activity.get("difficulty") or 1), 5)),
            "expectedObservations": activity.get("expectedObservations") if isinstance(activity.get("expectedObservations"), list) else ["prediction", "explanation", "uncertainty"],
            "evaluatorRubric": activity.get("evaluatorRubric") if isinstance(activity.get("evaluatorRubric"), list) else ["Uses the selected source", "Explains a relationship", "Names uncertainty"],
            "sourceIds": list(dict.fromkeys(source_ids)),
            "sourceAnchorIds": list(dict.fromkeys(anchors)),
            "remediationTarget": str(activity.get("remediationTarget") or "Return to the cited concept and explain one bounded relationship.")[:1000],
            "transferTarget": str(activity.get("transferTarget") or "Apply the cited relationship to a changed condition.")[:1000],
        })
    return {
        "schemaVersion": "curriculum-proposal.v1",
        "domain": str(raw.get("domain") or goal.domain or "general")[:120],
        "learnerLevel": learner_level,
        "concepts": normalized_concepts,
        "prerequisites": normalized_edges,
        "activities": normalized_activities,
        "uncertainty": raw.get("uncertainty") if isinstance(raw.get("uncertainty"), dict) else {"level": "provisional"},
    }


def _provider_proposal(goal: LearningGoal, learner_level: str, spans: list[SourceSpan]) -> tuple[dict[str, Any], dict[str, Any]]:
    provider = provider_for("fireworks")
    request = {
        "goal": {"title": goal.title, "description": goal.description, "outcome": goal.outcome, "domain": goal.domain},
        "learnerLevel": learner_level,
        "sourceSpans": [span.as_dict() for span in spans],
        "schema": _proposal_schema(),
    }
    raw = provider.compile_curriculum(request)
    proposal = _validate_proposal(raw, allowed_source_ids={span.source_id for span in spans}, allowed_anchor_ids={span.anchor_id for span in spans}, goal=goal, learner_level=learner_level)
    return proposal, {"provider": "fireworks", "providerMode": getattr(provider, "mode", "live_fireworks"), "model": getattr(provider, "model", ""), "status": "completed"}


def _materialize_payload(pack: CurriculumPack, version: CurriculumVersion, route: GoalCurriculumRoute) -> dict[str, Any]:
    concepts = list(version.concepts.all())
    activities = list(version.activity_definitions.select_related("concept").all())
    cited_concepts = sum(1 for concept in concepts if concept.source_anchor_ids)
    cited_activities = sum(1 for activity in activities if activity.source_anchor_ids)
    total_claims = len(concepts) + len(activities)
    cited_claims = cited_concepts + cited_activities
    quality = {
        "conceptCount": len(concepts),
        "citedConceptCount": cited_concepts,
        "activityCount": len(activities),
        "citedActivityCount": cited_activities,
        "coveragePercent": round((cited_claims / total_claims) * 100) if total_claims else 0,
        "unsupportedClaims": max(0, total_claims - cited_claims),
        "warnings": [
            "Provider-generated curriculum remains provisional until learner evidence is observed.",
            "Every claim in this route must remain inside the selected source anchors.",
            *( ["One or more curriculum claims lack a validated source anchor."] if total_claims > cited_claims else [] ),
        ],
    }
    safety_boundary = (
        "Academic, source-cited learning only. No personal diagnosis, treatment, prescription, or patient-specific advice."
        if pack.safety_mode == "academic_source_bound"
        else "Bounded learning activity. Generated feedback cannot override deterministic evidence or source boundaries."
    )
    compiler_stages = [
        {"id": "read_sources", "label": "Reading sources", "status": "completed"},
        {"id": "extract_concepts", "label": "Extracting concepts", "status": "completed"},
        {"id": "detect_prerequisites", "label": "Detecting prerequisites", "status": "completed"},
        {"id": "build_activities", "label": "Building activities", "status": "completed"},
        {"id": "validate_citations", "label": "Validating citations", "status": "completed"},
        {"id": "prepare_route", "label": "Preparing route", "status": "completed"},
    ]
    return {
        "packId": str(pack.pack_id),
        "curriculumVersionId": version.id,
        "version": version.version,
        "status": pack.status,
        "domain": pack.domain,
        "learnerLevel": pack.learner_level,
        "safetyMode": pack.safety_mode,
        "sourceIds": pack.source_ids,
        "sourceAnchorIds": pack.source_anchor_ids,
        "sourceFingerprint": pack.source_fingerprint,
        "uncertainty": pack.uncertainty,
        "provenance": pack.provenance,
        "quality": quality,
        "safetyBoundary": safety_boundary,
        "difficultyExplanation": f"{pack.learner_level.title()} route with observable tasks increasing from bounded prediction to transfer.",
        "compilerStages": compiler_stages,
        "preview": {
            "editable": True,
            "approvalRequired": bool(pack.goal.course_id),
            "approvalState": "pending" if pack.goal.course_id else "not_required",
            "routeEdited": bool((route.route or {}).get("routeEdited")),
        },
        "concepts": [
            {"conceptId": concept.id, "key": concept.node_key, "title": concept.title, "description": concept.explanation, "position": concept.position, "sourceIds": concept.source_ids, "sourceAnchorIds": concept.source_anchor_ids, "uncertainty": concept.uncertainty}
            for concept in concepts
        ],
        "prerequisites": [
            {"prerequisite": edge.prerequisite.node_key, "dependent": edge.dependent.node_key, "relation": edge.relation, "sourceAnchorIds": edge.source_anchor_ids}
            for edge in version.prerequisite_edges.select_related("prerequisite", "dependent")
        ],
        "activities": [
            {"activityDefinitionId": definition.id, "conceptKey": definition.concept.node_key if definition.concept else None, "type": definition.activity_type, "title": definition.title, "prompt": definition.prompt, "position": definition.position, "difficulty": definition.difficulty, "configuration": definition.configuration, "expectedObservations": definition.expected_observations, "sourceIds": definition.source_ids, "sourceAnchorIds": definition.source_anchor_ids, "remediationTarget": definition.remediation_target, "transferTarget": definition.transfer_target, "rubric": {"criteria": definition.rubric.criteria, "requiredFields": definition.rubric.required_fields, "sourceRequirements": definition.rubric.source_requirements} if hasattr(definition, "rubric") else {}}
            for definition in activities
        ],
        "route": route.route,
    }


@transaction.atomic
def _persist_compilation(goal: LearningGoal, proposal: dict[str, Any], *, sources: list[NotebookSource], fingerprint: str, provenance: dict[str, Any]) -> dict[str, Any]:
    previous = CurriculumPack.objects.filter(goal=goal, status__in=["ready", "needs_review"]).order_by("-version").first()
    next_version = (previous.version + 1) if previous else 1
    if previous:
        previous.status = "stale"
        previous.save(update_fields=["status", "updated_at"])
        previous.versions.filter(status="active").update(status="stale")
    adapter = get_domain_adapter(goal.title, goal.domain)
    source_ids = sorted({str(source.source_id) for source in sources})
    anchor_ids = [span.anchor_id for span in source_spans(sources)]
    pack = CurriculumPack.objects.create(
        goal=goal,
        domain=str(proposal.get("domain") or goal.domain or "general"),
        learner_level=goal.current_level,
        safety_mode=goal.safety_mode,
        status="ready",
        version=next_version,
        source_ids=source_ids,
        source_anchor_ids=anchor_ids,
        source_fingerprint=fingerprint,
        uncertainty=proposal.get("uncertainty") or {"level": "provisional"},
        provenance=provenance,
        compiler_mode=str(provenance.get("providerMode") or "deterministic_fallback"),
    )
    version = CurriculumVersion.objects.create(curriculum=pack, version=next_version, source_ids=source_ids, source_anchor_ids=anchor_ids, source_fingerprint=fingerprint, provenance=provenance, uncertainty=pack.uncertainty)
    node_by_key: dict[str, ConceptNode] = {}
    for index, concept in enumerate(proposal["concepts"]):
        node_by_key[concept["key"]] = ConceptNode.objects.create(
            curriculum=version,
            node_key=concept["key"],
            title=concept["title"],
            explanation=concept.get("description", ""),
            position=index,
            source_ids=concept.get("sourceIds", []),
            source_anchor_ids=concept.get("sourceAnchorIds", []),
            uncertainty=concept.get("uncertainty", {}),
        )
    for edge in proposal.get("prerequisites", []):
        PrerequisiteEdge.objects.create(curriculum=version, prerequisite=node_by_key[edge["prerequisite"]], dependent=node_by_key[edge["dependent"]], source_anchor_ids=edge.get("sourceAnchorIds", []))
    for position, item in enumerate(proposal["activities"], start=1):
        concept = node_by_key[item["conceptKey"]]
        contract = adapter.build_activity(
            activity_type=item["activityType"], concept=concept.title, prompt=item["prompt"], difficulty=item["difficulty"],
            source_ids=item["sourceIds"], source_anchor_ids=item["sourceAnchorIds"], prerequisites=[],
            requires_source=goal.source_mode == "required" or goal.safety_mode == "academic_source_bound",
        )
        contract["configuration"].update({"expectedLearnerObservations": item["expectedObservations"], "evaluatorRubric": item["evaluatorRubric"], "curriculumVersionId": version.id, "conceptKey": concept.node_key})
        definition = ActivityDefinition.objects.create(
            curriculum=version, concept=concept, activity_type=item["activityType"], title=item["title"], prompt=item["prompt"], position=position,
            difficulty=item["difficulty"], configuration=contract["configuration"], expected_observations=item["expectedObservations"], source_ids=item["sourceIds"], source_anchor_ids=item["sourceAnchorIds"], remediation_target=item["remediationTarget"], transfer_target=item["transferTarget"], safety_mode=goal.safety_mode,
        )
        EvaluationRubric.objects.create(activity=definition, criteria=item["evaluatorRubric"], required_fields=["writtenExplanation", "learnerConclusion", "interactionState"], source_requirements=contract["configuration"]["sourceRequirements"], uncertainty=proposal.get("uncertainty") or {})
    LearningActivity.objects.filter(goal=goal, status__in=["ready", "needs_source"]).update(status="stale")
    materialized: list[LearningActivity] = []
    for definition in version.activity_definitions.select_related("concept").all():
        materialized.append(LearningActivity.objects.create(
            goal=goal,
            activity_type=definition.activity_type,
            title=definition.title,
            prompt=definition.prompt,
            position=definition.position,
            status="needs_source" if definition.configuration.get("sourceRequirements", {}).get("mode") == "required" else "ready",
            configuration=definition.configuration,
            difficulty=definition.difficulty,
            remediation_target=definition.remediation_target,
            transfer_target=definition.transfer_target,
            prerequisites=[definition.concept.title] if definition.concept else [],
            source_ids=definition.source_ids,
            evaluator={"mode": "source_backed" if definition.configuration.get("sourceRequirements", {}).get("mode") == "required" else "guided_observation", "requiresSource": definition.configuration.get("sourceRequirements", {}).get("mode") == "required", "minimumResponseCharacters": 24, "curriculumVersionId": version.id, "conceptKey": definition.concept.node_key if definition.concept else None, "citations": definition.source_anchor_ids},
        ))
    active = materialized[0]
    route_payload = {"schemaVersion": "adaptive-route.v2", "curriculumVersionId": version.id, "curriculumPackId": str(pack.pack_id), "state": "active", "currentPosition": 1, "activeActivityId": str(active.activity_id), "nextAction": "start_activity", "sourceFingerprint": fingerprint, "uncertainty": pack.uncertainty, "previewAvailable": True, "approvalRequired": bool(goal.course_id), "approvalState": "pending" if goal.course_id else "not_required", "routeEdited": False}
    route, _ = GoalCurriculumRoute.objects.update_or_create(goal=goal, defaults={"curriculum": version, "state": "active", "active_activity": version.activity_definitions.order_by("position", "id").first(), "current_position": 1, "route": route_payload, "next_action": "start_activity", "invalid_reason": ""})
    goal.route = route_payload
    goal.next_action = "start_activity"
    goal.status = "active" if goal.status != "draft" else goal.status
    goal.save(update_fields=["route", "next_action", "status", "updated_at"])
    return _materialize_payload(pack, version, route)


def compile_curriculum(goal: LearningGoal, learner_level: str, selected_sources: Iterable[NotebookSource]) -> dict[str, Any]:
    """Compile and persist a source-grounded curriculum for ``goal``."""
    if learner_level not in {"beginner", "intermediate", "advanced"}:
        raise CurriculumCompileError("learner_level must be beginner, intermediate, or advanced.", "invalid_learner_level")
    sources = _ready_selected_sources(goal, selected_sources)
    if not sources:
        raise CurriculumCompileError("Attach and select at least one ready source before compiling a curriculum.", "source_required")
    spans = source_spans(sources)
    if not spans:
        raise CurriculumCompileError("Selected sources have no grounded text blocks.", "source_text_unavailable")
    fingerprint = source_fingerprint(sources)
    provider_error: str | None = None
    try:
        proposal, provenance = _provider_proposal(goal, learner_level, spans)
    except (ProviderUnavailable, ProviderOutputError, NotImplementedError) as exc:
        provider_error = type(exc).__name__
        proposal = _fallback_proposal(goal, learner_level, spans)
        provenance = {"provider": "fireworks", "providerMode": "deterministic_fallback", "status": "fallback", "errorCategory": provider_error}
    result = _persist_compilation(goal, proposal, sources=sources, fingerprint=fingerprint, provenance=provenance)
    result["compiler"] = {"mode": provenance.get("providerMode", "deterministic_fallback"), "providerErrorCategory": provider_error, "schemaVersion": "curriculum-proposal.v1"}
    return result


def curriculum_is_stale(pack: CurriculumPack, selected_sources: Iterable[NotebookSource]) -> bool:
    sources = list(selected_sources)
    current_ids = sorted({str(source.source_id) for source in sources})
    return pack.status == "stale" or current_ids != sorted(pack.source_ids) or source_fingerprint(sources) != pack.source_fingerprint
