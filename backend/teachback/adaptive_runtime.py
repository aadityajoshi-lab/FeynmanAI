"""Deterministic, source-bounded adaptive learning runtime.

Provider feedback may enrich the learner-facing explanation, but every route
transition in this module is decided from explicit, persisted learner evidence.
The contract is deliberately JSON-native so each domain adapter can use the
same Activity Canvas and submit the same structured attempt envelope.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .curriculum_adapters import get_domain_adapter


INTERACTION_CONTRACTS: dict[str, dict[str, Any]] = {
    "dsp": {
        "kind": "sampling_spectrum_lab",
        "controls": [
            {"id": "signal_frequency", "kind": "range", "min": 1, "max": 18, "step": 1, "default": 7},
            {"id": "sample_rate", "kind": "range", "min": 2, "max": 36, "step": 1, "default": 8},
            {"id": "window", "kind": "select", "options": ["rectangular", "hann", "hamming"]},
        ],
        "expected": ["prediction", "nyquist_or_bin_observation", "spectral_leakage_explanation"],
        "rubric": ["Relates sample rate to Nyquist", "Explains a spectrum observation", "Names a windowing trade-off"],
        "remediation": "Return to the sampled waveform and identify the Nyquist limit and bin spacing.",
        "transfer": "Apply the idea to a changed sample rate or window and explain what remains reliable.",
    },
    "operating_systems": {
        "kind": "scheduler_trace",
        "controls": [
            {"id": "topic", "kind": "select", "options": ["scheduling", "virtual_memory", "deadlock", "system_call"]},
            {"id": "policy", "kind": "select", "options": ["fcfs", "round_robin", "priority"]},
            {"id": "quantum", "kind": "range", "min": 1, "max": 6, "step": 1, "default": 2},
            {"id": "frame_capacity", "kind": "range", "min": 2, "max": 5, "step": 1, "default": 3},
            {"id": "processes", "kind": "process_table", "required": True},
        ],
        "expected": ["prediction", "trace", "waiting_or_turnaround_tradeoff"],
        "rubric": ["Uses a concrete schedule", "Names a metric trade-off", "Explains a state transition"],
        "remediation": "Trace process ready, running, and waiting states before changing policy.",
        "transfer": "Compare a policy change for an interactive and a batch workload.",
    },
    "computer_graphics": {
        "kind": "transform_camera",
        "controls": [
            {"id": "translate", "kind": "vector2", "default": [0, 0]},
            {"id": "rotation", "kind": "range", "min": -180, "max": 180, "step": 5, "default": 0},
            {"id": "scale", "kind": "range", "min": 0.25, "max": 3, "step": 0.25, "default": 1},
            {"id": "camera", "kind": "select", "options": ["world", "view", "projection"]},
            {"id": "light", "kind": "vector3", "default": [1, 1, 1]},
            {"id": "depth_test", "kind": "toggle", "default": True},
            {"id": "sample_count", "kind": "range", "min": 1, "max": 8, "step": 1, "default": 2},
        ],
        "expected": ["prediction", "coordinate_or_visual_observation", "transform_explanation"],
        "rubric": ["Distinguishes coordinate spaces", "Predicts a visible change", "Explains matrix order or camera effect"],
        "remediation": "Apply one transform at a time and label the coordinate space after each step.",
        "transfer": "Explain how the same transform changes after moving from world to view space.",
    },
    "ai_ml": {
        "kind": "classification_evaluation",
        "controls": [
            {"id": "threshold", "kind": "range", "min": 0.1, "max": 0.9, "step": 0.05, "default": 0.5},
            {"id": "split", "kind": "select", "options": ["stratified", "random", "leaky"]},
            {"id": "slice", "kind": "select", "options": ["all", "minority", "recent_shift"]},
            {"id": "regularization", "kind": "range", "min": 0, "max": 1, "step": 0.1, "default": 0.2},
        ],
        "expected": ["prediction", "confusion_matrix_or_metric", "error_or_leakage_explanation"],
        "rubric": ["Uses a bounded evaluation slice", "Names precision/recall trade-off", "Detects leakage or distribution shift"],
        "remediation": "Inspect the train/test split and a confusion-matrix row before changing the threshold.",
        "transfer": "Design a follow-up evaluation for a shifted deployment slice.",
    },
    "history": {
        "kind": "historical_evidence_map",
        "controls": [
            {"id": "timeline", "kind": "timeline", "required": True},
            {"id": "actors", "kind": "relation_table", "required": True},
            {"id": "source_stance", "kind": "select", "options": ["primary", "secondary", "uncertain"]},
        ],
        "expected": ["chronology", "source_provenance", "causal_mechanism", "uncertainty_limit"],
        "rubric": ["Separates chronology from causation", "Uses a bounded source claim", "Names uncertainty or disagreement"],
        "remediation": "Return to the selected source anchor and separate actors, evidence, and interpretation.",
        "transfer": "Apply the same evidence test to a nearby historical case without assuming the pattern transfers.",
    },
    "medical": {
        "kind": "source_grounded_mechanism",
        "controls": [
            {"id": "structure", "kind": "select_source_anchor", "required": True},
            {"id": "mechanism_map", "kind": "relation_table", "required": True},
        ],
        "expected": ["selected_source_anchor", "mechanism_explanation", "uncertainty_limit"],
        "rubric": ["Cites selected academic material", "Explains a bounded mechanism", "States uncertainty and educational limit"],
        "remediation": "Return to the selected academic anchor and map structure, relationship, and observable function.",
        "transfer": "Compare the mechanism with a nearby academic case without making a patient-specific recommendation.",
    },
    "general": {
        "kind": "bounded_reasoning",
        "controls": [{"id": "case", "kind": "text_or_table", "required": True}],
        "expected": ["prediction_or_explanation", "concrete_case", "uncertainty"],
        "rubric": ["Uses a concrete case", "Explains a relationship", "Names uncertainty"],
        "remediation": "Use one bounded example and name the relationship before generalising.",
        "transfer": "Apply the same relationship to a nearby but different case.",
    },
}


def _domain_contract(domain: str) -> dict[str, Any]:
    adapter = get_domain_adapter(domain=domain)
    return {
        "kind": adapter.interaction_kind,
        "controls": [dict(control) for control in adapter.controls],
        "expected": list(adapter.expected_observations),
        "rubric": list(adapter.rubric),
        "remediation": adapter.remediation_target,
        "transfer": adapter.transfer_target,
    }


def activity_contracts_for_goal(
    *, title: str, domain: str, prerequisites: list[str], requires_source: bool, first_prompt: str
) -> list[dict[str, Any]]:
    """Return a deterministic route whose activities all share one schema."""
    adapter = get_domain_adapter(title, domain)
    domain_contract = _domain_contract(adapter.key)
    sequence = [(activity_type, f"{activity_type.replace('_', ' ').title()} the concept") for activity_type in adapter.activity_sequence]

    items: list[dict[str, Any]] = []
    for position, (activity_type, label) in enumerate(sequence, start=1):
        prompt = first_prompt if position == 1 else (
            f"{label} for {title}. Manipulate the bounded controls, record your observation, "
            "then explain the consequence and one uncertainty."
        )
        configuration = {
            "schemaVersion": "activity.v1",
            "activityType": activity_type,
            "domain": adapter.key,
            "adapterKind": domain_contract["kind"],
            "concept": title,
            "difficulty": min(position, 3),
            "prerequisites": prerequisites if position == 1 else [],
            "taskPrompt": prompt,
            "interactiveControls": domain_contract["controls"],
            "expectedLearnerObservations": domain_contract["expected"],
            "evaluatorRubric": domain_contract["rubric"],
            "sourceRequirements": {
                "mode": "required" if (requires_source or domain == "medical") else "optional",
                "requireSelectedAnchors": bool(requires_source or domain == "medical"),
            },
            "allowedResponseTypes": ["written_explanation", "prediction", "interaction_state", "trace", "learner_conclusion"],
            "remediationTarget": domain_contract["remediation"],
            "transferTarget": domain_contract["transfer"],
        }
        items.append({
            "type": activity_type,
            "title": label,
            "prompt": prompt,
            "difficulty": min(position, 3),
            "prerequisites": prerequisites if position == 1 else [],
            "configuration": configuration,
            "remediationTarget": domain_contract["remediation"],
            "transferTarget": domain_contract["transfer"],
        })
    return items


def normalize_structured_attempt(body: dict[str, Any]) -> dict[str, Any]:
    """Validate the shared activity envelope without discarding useful evidence."""
    response = str(body.get("response") or body.get("writtenExplanation") or "").strip()
    conclusion = str(body.get("learnerConclusion") or "").strip()
    confidence = body.get("confidence")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, int) or confidence < 1 or confidence > 5):
        raise ValueError("confidence must be an integer from 1 to 5.")

    def object_field(name: str) -> dict[str, Any]:
        value = body.get(name, {})
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be an object.")
        return value

    def list_field(name: str) -> list[Any]:
        value = body.get(name, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{name} must be an array.")
        return value[:100]

    return {
        "writtenExplanation": response[:12000],
        "learnerConclusion": conclusion[:4000],
        "confidence": confidence,
        "prediction": object_field("prediction"),
        "interactionState": object_field("interactionState"),
        "simulationParameters": object_field("simulationParameters"),
        "selectedOptions": list_field("selectedOptions"),
        "calculations": object_field("calculations"),
        "trace": list_field("trace"),
        "structuredSubmitted": any(name in body for name in ("prediction", "interactionState", "simulationParameters", "selectedOptions", "calculations", "trace", "learnerConclusion")),
    }


def _semantic_tokens(value: object) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{4,}", str(value or "").casefold()) if token not in {"with", "from", "that", "this", "then", "into", "before", "after", "what", "your"}}


def _semantic_item_hit(item: str, lower_text: str, tokens: set[str]) -> bool:
    """Match rubric language to observable evidence without requiring exact prose."""
    item_lower = item.casefold()
    if _semantic_tokens(item) & tokens:
        return True
    aliases = {
        "prediction": ("predict", "expect", "would", "if", "when"),
        "source_citation": ("source", "cited", "note", "reference", "anchor"),
        "relationship_explanation": ("because", "causes", "leads", "represented", "compare", "connect"),
        "changed_condition": ("changed", "if ", "when ", "too low", "different", "rate"),
        "trace": ("trace", "queue", "state", "schedule"),
        "waiting_or_turnaround_tradeoff": ("waiting", "turnaround", "response", "fairness", "trade-off"),
        "coordinate_or_visual_observation": ("coordinate", "rotate", "scale", "camera", "visible", "render"),
        "uncertainty": ("uncertain", "ambiguity", "limit", "assumption", "reliable", "cannot conclude"),
        "uncertainty_limit": ("uncertain", "ambiguity", "limit", "assumption", "educational"),
        "mechanism_explanation": ("mechanism", "structure", "function", "relationship"),
        "confusion_matrix_or_metric": ("precision", "recall", "metric", "confusion", "threshold"),
        "error_or_leakage_explanation": ("error", "leakage", "shift", "distribution", "split"),
    }
    for phrase, terms in aliases.items():
        if phrase in item_lower and any(term in lower_text for term in terms):
            return True
    return False


def _semantic_quality(configuration: dict[str, Any], attempt: dict[str, Any], source_ids: list[str], anchor_ids: list[str]) -> dict[str, Any]:
    """Score observable meaning, not prose volume.

    These checks are deliberately explainable and persisted with the decision.
    Fireworks may critique the response, but it cannot bypass these signals.
    """
    written = str(attempt.get("writtenExplanation") or "")
    conclusion = str(attempt.get("learnerConclusion") or "")
    combined = f"{written} {conclusion}".strip()
    lower = combined.casefold()
    concept = str(configuration.get("concept") or "")
    expected = [str(item) for item in configuration.get("expectedLearnerObservations", []) if item]
    rubric = [str(item) for item in configuration.get("evaluatorRubric", []) if item]
    prerequisites = [str(item) for item in configuration.get("prerequisites", []) if item]
    concept_terms = _semantic_tokens(concept)
    prediction_text = json.dumps(attempt.get("prediction") or {}, sort_keys=True).casefold()
    interaction = attempt.get("interactionState") or {}
    observable_material = f"{combined} {prediction_text} {json.dumps(interaction, sort_keys=True)} {json.dumps(attempt.get('trace') or [], sort_keys=True)} {json.dumps(attempt.get('calculations') or {}, sort_keys=True)}"
    concept_coverage = 1.0 if concept and concept.casefold() in lower else (len(concept_terms & _semantic_tokens(observable_material)) / max(1, len(concept_terms)))
    causal_markers = ("because", "therefore", "leads to", "causes", "results in", "trade-off", "relationship", "depends", "so that", "represented as", "compare", "if ", "when ")
    has_causal_relationship = any(marker in lower for marker in causal_markers) and len(_semantic_tokens(observable_material)) >= 8
    uncertainty_markers = ("uncertain", "uncertainty", "limit", "limitation", "depends", "might", "could", "not enough", "cannot conclude", "assumption", "ambiguity", "reliable", "assert")
    has_uncertainty = any(marker in lower for marker in uncertainty_markers)
    positive = {"increase", "increases", "higher", "more", "improve", "faster", "true", "yes", "earlier"}
    negative = {"decrease", "decreases", "lower", "less", "worse", "slower", "false", "no", "later"}
    prediction_polarity = (bool(positive & _semantic_tokens(prediction_text)), bool(negative & _semantic_tokens(prediction_text)))
    conclusion_polarity = (bool(positive & _semantic_tokens(conclusion)), bool(negative & _semantic_tokens(conclusion)))
    contradiction = bool(prediction_text and conclusion and ((prediction_polarity[0] and conclusion_polarity[1]) or (prediction_polarity[1] and conclusion_polarity[0])))
    has_interaction = bool(interaction or attempt.get("simulationParameters") or attempt.get("trace"))
    has_calculation_or_trace = bool(attempt.get("calculations") or attempt.get("trace"))
    prerequisite_hits = sum(1 for item in prerequisites if _semantic_tokens(item) & _semantic_tokens(observable_material))
    prerequisite_coverage = prerequisite_hits / len(prerequisites) if prerequisites else (1.0 if concept_coverage >= 0.5 else 0.0)
    observable_tokens = _semantic_tokens(observable_material)
    expected_hits = sum(1 for item in expected if _semantic_item_hit(item, lower, observable_tokens))
    rubric_hits = sum(1 for item in rubric if _semantic_item_hit(item, lower, observable_tokens))
    return {
        "conceptCoverage": round(concept_coverage, 2),
        "expectedObservationHits": expected_hits,
        "expectedObservationCount": len(expected),
        "rubricHits": rubric_hits,
        "rubricCount": len(rubric),
        "causalRelationship": has_causal_relationship,
        "uncertaintyStatement": has_uncertainty,
        "predictionConclusionContradiction": contradiction,
        "interactionObserved": has_interaction,
        "calculationOrTraceObserved": has_calculation_or_trace,
        "prerequisiteCoverage": round(prerequisite_coverage, 2),
        "sourceAnchored": bool(source_ids and anchor_ids),
        "confidence": attempt.get("confidence"),
    }


def deterministic_evaluation(
    *, configuration: dict[str, Any], attempt: dict[str, Any], source_ids: list[str], anchor_ids: list[str], provider_failed: bool
) -> dict[str, Any]:
    """Return a route transition based only on stored observable evidence."""
    written = str(attempt.get("writtenExplanation") or "")
    conclusion = str(attempt.get("learnerConclusion") or "")
    interaction = attempt.get("interactionState") or {}
    simulation = attempt.get("simulationParameters") or {}
    trace = attempt.get("trace") or []
    prediction = attempt.get("prediction") or {}
    requirements = configuration.get("sourceRequirements") if isinstance(configuration, dict) else {}
    requires_source = isinstance(requirements, dict) and requirements.get("mode") == "required"
    controls = configuration.get("interactiveControls") if isinstance(configuration, dict) else []
    requires_interaction = bool(controls)
    text_length = len(written) + len(conclusion)
    quality = _semantic_quality(configuration, attempt, source_ids, anchor_ids)
    has_interaction = bool(quality["interactionObserved"])
    score = 0.08
    score += min(text_length, 500) / 3300
    score += 0.18 * quality["conceptCoverage"]
    score += 0.15 if quality["causalRelationship"] else 0
    score += 0.08 if quality["uncertaintyStatement"] else 0
    score += 0.22 if has_interaction else 0
    score += 0.14 if quality["calculationOrTraceObserved"] else 0
    score += 0.08 if conclusion else 0
    score += 0.08 * quality["prerequisiteCoverage"]
    score += 0.15 if quality["sourceAnchored"] else 0
    score += 0.10 * (quality["expectedObservationHits"] / max(1, quality["expectedObservationCount"]))
    score += 0.08 * (quality["rubricHits"] / max(1, quality["rubricCount"]))
    score += 0.08 if prediction else 0
    if attempt.get("confidence") == 5 and score < 0.72:
        score -= 0.08
        quality["confidenceCalibration"] = "overconfident"
    else:
        quality["confidenceCalibration"] = "calibrated_or_unknown"
    score = min(round(max(score, 0.05), 2), 0.95)

    def decision(action: str, reason: str, evidence_status: str = "observed") -> dict[str, Any]:
        return {"action": action, "reason": reason, "score": score, "evidenceStatus": evidence_status, "qualitySignals": quality}

    if provider_failed:
        return decision("retry", "provider_unavailable")
    if text_length < 24:
        return decision("retry", "observable_explanation_too_short", "needs_review")
    if len(written.split()) < 12 and not has_interaction:
        return decision("retry", "observable_explanation_needs_detail", "needs_review")
    # A short or underspecified attempt should receive a retry prompt before
    # a source-verification request. Source anchoring is still mandatory for
    # a sufficiently detailed academic attempt, but the first response to a
    # weak learner signal is actionable remediation rather than a dead end.
    if requires_source and (not source_ids or not anchor_ids):
        return decision("request_source_backed_verification", "source_anchors_required", "needs_review")
    if requires_interaction and attempt.get("structuredSubmitted") and not has_interaction:
        return decision("retry", "interaction_state_required", "needs_review")
    if quality["predictionConclusionContradiction"]:
        return decision("retry", "prediction_conclusion_contradiction", "needs_review")
    if attempt.get("confidence") == 1 and score < 0.62:
        return decision("simplify_task", "low_confidence_with_incomplete_evidence")
    if score < 0.45:
        return decision("remediate_prerequisite", "missing_prerequisite_observation")
    if score < 0.65:
        return decision("add_worked_example", "partial_observable_evidence")
    if attempt.get("interactionState", {}).get("requiresHumanReview"):
        return decision("require_human_review", "learner_or_activity_flagged_review", "needs_review")
    if score >= 0.84:
        return decision("increase_difficulty", "strong_structured_evidence", "verified" if requires_source else "observed")
    return decision("advance", "sufficient_structured_evidence", "verified" if requires_source else "observed")


def next_route_state(*, current_position: int, activity_id: str, decision: dict[str, Any], next_activity_id: str | None, fallback_action: str) -> dict[str, Any]:
    action = str(decision["action"])
    active_id = activity_id if action in {"retry", "simplify_task", "request_source_backed_verification", "require_human_review"} else (next_activity_id or activity_id)
    return {
        "schemaVersion": "adaptive-route.v1",
        "state": "active",
        "currentPosition": current_position,
        "activeActivityId": active_id,
        "nextAction": action if next_activity_id or action != "advance" else fallback_action,
        "transitionReason": decision["reason"],
        "lastDecision": decision,
    }
