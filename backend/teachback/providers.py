"""Model boundary: live providers for learner modules, fixtures only for tests."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any
from django.conf import settings

SOURCE_IDS = [f"photosynthesis-v1-span-{i:02d}" for i in range(1, 9)]
LEARNING_MODE_IDS = {
    "worked_example", "predict_reveal", "self_explain", "retrieval", "spaced_review",
    "interleaved_contrast", "concrete_example", "representation_switch", "exam_bridge",
}


class ProviderUnavailable(RuntimeError):
    pass


class ProviderOutputError(ValueError):
    pass


MAX_PROVIDER_INTEGER_DIGITS = 256


def _bounded_provider_int(raw: str) -> int | str:
    """Keep absurd provider numbers as text instead of converting them."""
    digits = raw.lstrip("-").lstrip("0") or "0"
    if len(digits) > MAX_PROVIDER_INTEGER_DIGITS:
        return raw
    return int(raw)


def load_provider_json(raw: str) -> dict:
    """Parse provider JSON without allowing unbounded integer conversion."""
    return json.loads(raw, strict=False, parse_int=_bounded_provider_int)


@dataclass
class AuditRequest:
    learner_text: str
    source_spans: list[dict]
    session_id: str


@dataclass
class ClarificationRequest:
    claim: dict
    question: str
    source_spans: list[dict]
    session_id: str


@dataclass
class StudyPlanRequest:
    """A bounded request for a source-backed study manifest."""

    subject_id: str
    module_id: str | None
    source_ids: list[str]
    chapter_selection: str
    approved_source_ids: list[str]
    source_spans: list[dict] = field(default_factory=list)
    subject_title: str = ""
    past_question_source_ids: list[str] = field(default_factory=list)


@dataclass
class ModuleChatRequest:
    """A contextual command/question about an already-built module.

    The browser sends scene metadata and source IDs, never source text or
    executable content. The provider can answer from the server-owned spans
    and return a small, typed action for the learner surface to apply.
    """

    subject_id: str
    module_id: str | None
    subject_title: str
    source_ids: list[str]
    approved_source_ids: list[str]
    source_spans: list[dict]
    message: str
    history: list[dict]
    active_scene_id: str | None
    active_scene_index: int
    scenes: list[dict]
    learning_mode: str


CHAT_ACTION_TYPES = [
    "none",
    "next_scene",
    "previous_scene",
    "open_scene",
    "focus_checkpoint",
    "show_visualization",
    "repeat_explanation",
    "set_learning_mode",
]


SCENE_TYPES = ["topic", "whiteboard", "two_d", "three_d", "predict_checkpoint", "retrieval", "teach_back", "exam_bridge", "question_bank"]
ACTION_TYPES = ["reveal", "spotlight", "draw", "write", "equation", "pause"]
ASSESSMENT_STAGE_KINDS = ["definition", "mcq", "formula", "diagram", "numerical", "teach_back"]


def assessment_stage_schema(anchors: list[str], *, max_prompt_length: int = 700) -> dict:
    """Schema for the learner's topic-by-topic assessment ladder."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["stageId", "kind", "title", "prompt", "responseType", "options", "sourceAnchorIds"],
        "properties": {
            "stageId": {"type": "string", "minLength": 1, "maxLength": 100},
            "kind": {"type": "string", "enum": ASSESSMENT_STAGE_KINDS},
            "title": {"type": "string", "minLength": 1, "maxLength": 160},
            "prompt": {"type": "string", "minLength": 1, "maxLength": max_prompt_length},
            "responseType": {"type": "string", "enum": ["none", "single_choice", "short_text", "long_text", "file"]},
            "options": {"type": ["array", "null"], "minItems": 2, "maxItems": 4, "items": {"type": "string", "maxLength": 220}},
            "sourceAnchorIds": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "enum": anchors}},
        },
    }


def normalize_answer_options(options: Any) -> list[str] | None:
    """Keep learner-facing MCQ options textual and never expose answer flags."""
    if isinstance(options, dict):
        options = options.get("items") or options.get("choices") or options.get("values")
    if not isinstance(options, list):
        return None
    normalized: list[str] = []
    for option in options:
        if isinstance(option, dict):
            text = option.get("text") or option.get("label") or option.get("value") or option.get("stem") or option.get("option")
        else:
            text = option
        if text is not None and str(text).strip():
            normalized.append(str(text).strip())
    if not normalized:
        return None
    schema_labels = {"id", "stageid", "kind", "type", "title", "stem", "prompt", "question", "responsetype", "options", "choices", "sourceanchors", "sourceanchorids"}
    if len(normalized) >= 3 and all(value.casefold() in schema_labels for value in normalized):
        return None
    return normalized


def normalize_retry_result(result: dict, manifest: dict) -> dict:
    """Keep optional similar-question data safe and aligned to the stage."""
    if result.get("correct") is not False:
        result["retryPrompt"] = None
        result["retryOptions"] = None
        result["retryResponseType"] = None
        result["retrySourceAnchorIds"] = []
        return result
    stage = manifest.get("stage") if isinstance(manifest.get("stage"), dict) else {}
    kind = str(manifest.get("stageKind") or stage.get("kind") or "teach_back")
    prompt = result.get("retryPrompt") or result.get("similarPrompt")
    result["retryPrompt"] = str(prompt).strip() if isinstance(prompt, str) and prompt.strip() else None
    options = normalize_answer_options(result.get("retryOptions") or result.get("similarOptions"))
    if kind == "mcq" and (not options or len(options) < 3):
        options = None
    if kind != "mcq":
        options = None
    result["retryOptions"] = options
    response_type = str(result.get("retryResponseType") or stage.get("responseType") or "long_text")
    result["retryResponseType"] = response_type if response_type in {"single_choice", "short_text", "long_text", "file"} else "long_text"
    allowed = list(manifest.get("sourceAnchorIds") or [])
    returned = result.get("retrySourceAnchorIds")
    result["retrySourceAnchorIds"] = [anchor for anchor in returned if anchor in allowed] if isinstance(returned, list) else []
    if not result["retryPrompt"]:
        result["retryOptions"] = None
        result["retrySourceAnchorIds"] = []
    return result


def study_plan_schema(request: StudyPlanRequest) -> dict:
    """Rich scene schema used when repairing incomplete live manifests.

    The initial provider call stays shallow for Qwen reliability; a targeted
    repair must still require instructional content and renderable scene data.
    """
    allowed_anchor_ids = list(request.approved_source_ids)
    checkpoint_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "prompt", "responseType", "sourceAnchorIds"],
        "properties": {
            "kind": {"type": "string", "enum": ["predict", "retrieval", "teach_back", "exam_bridge"]},
            "prompt": {"type": "string", "minLength": 1},
            "responseType": {"type": "string", "enum": ["single_choice", "short_text", "long_text"]},
            "options": {"type": ["array", "null"], "maxItems": 8, "items": {"type": "string"}},
            "sourceAnchorIds": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": allowed_anchor_ids}},
        },
    }

    # Rich scene contract used for targeted repair fragments. The initial
    # top-level request intentionally uses the shallower Qwen schema below,
    # while repairs must require actual instructional and visual fields.
    action_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["actionId", "kind", "label", "payload", "durationMs"],
        "properties": {
            "actionId": {"type": "string"},
            "kind": {"type": "string", "enum": ACTION_TYPES},
            "label": {"type": "string", "minLength": 1},
            "payload": {"type": "object"},
            "durationMs": {"type": ["integer", "null"], "minimum": 0},
        },
    }
    stage_schema = assessment_stage_schema(allowed_anchor_ids)
    scene_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["sceneId", "conceptId", "type", "title", "explanation", "keyPoints", "workedExample", "commonMistakes", "sourceAnchorIds", "actions", "config", "checkpoint", "stages"],
        "properties": {
            "sceneId": {"type": "string"},
            "conceptId": {"type": "string"},
            "type": {"type": "string", "enum": SCENE_TYPES},
            "title": {"type": "string"},
            "explanation": {"type": "string", "minLength": 1},
            "keyPoints": {"type": "array", "minItems": 2, "maxItems": 6, "items": {"type": "string", "minLength": 1}},
            "workedExample": {"type": ["string", "null"], "maxLength": 1800},
            "commonMistakes": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string", "minLength": 1}},
            "sourceAnchorIds": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": allowed_anchor_ids}},
            "actions": {"type": "array", "minItems": 1, "maxItems": 12, "items": action_schema},
            "config": {"type": "object", "maxProperties": 12},
            "checkpoint": {"type": ["object", "null"], "properties": checkpoint_schema["properties"], "required": checkpoint_schema["required"], "additionalProperties": False},
            "stages": {"type": "array", "minItems": 1, "maxItems": 6, "items": stage_schema},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["studyPlanId", "sourceIds", "chapterSelection", "sourcePackVersion", "recordVersion", "outline", "scenes", "pastQuestionAnalysis"],
        "properties": {
            "studyPlanId": {"type": "string", "minLength": 8},
            "sourceIds": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string", "enum": list(request.source_ids)}},
            "chapterSelection": {"type": "string", "enum": ["chapter_1", "all"]},
            "sourcePackVersion": {"type": "string"},
            "recordVersion": {"type": "integer", "minimum": 1},
            "outline": {"type": "array", "minItems": 1, "maxItems": 12, "items": {"type": "object", "additionalProperties": False, "required": ["conceptId", "title", "objective", "sourceAnchorIds"], "properties": {
                "conceptId": {"type": "string"},
                "title": {"type": "string"},
                "objective": {"type": "string"},
                "sourceAnchorIds": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": allowed_anchor_ids}},
            }}},
            "scenes": {"type": "array", "minItems": 1, "maxItems": 40, "items": scene_schema},
            "pastQuestionAnalysis": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 500}},
        },
    }


def compact_study_plan_schema(request: StudyPlanRequest) -> dict:
    """Small, complete first-manifest contract for live Qwen generation.

    The initial authoring request deliberately has a much smaller completion
    surface than a full course export.  A large PDF plus unbounded scenes,
    actions, and chart data made Qwen stream a partial JSON object before the
    server could validate it.  The learner still receives a real, model-authored
    four-step learning loop; optional visuals and exam practice are callable
    extensions after the module opens.
    """
    anchors = list(request.approved_source_ids)
    checkpoint_schema = {
        "type": ["object", "null"],
        "additionalProperties": False,
        "required": ["kind", "prompt", "responseType", "options", "sourceAnchorIds"],
        "properties": {
            "kind": {"type": "string", "enum": ["predict", "retrieval", "teach_back", "exam_bridge"]},
            "prompt": {"type": "string", "minLength": 1, "maxLength": 700},
            "responseType": {"type": "string", "enum": ["single_choice", "short_text", "long_text"]},
            "options": {
                "type": ["array", "null"],
                "maxItems": 4,
                "items": {"type": "string", "maxLength": 220},
            },
            "sourceAnchorIds": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "string", "enum": anchors},
            },
        },
    }
    action_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["actionId", "kind", "label", "payload", "durationMs"],
        "properties": {
            "actionId": {"type": "string", "maxLength": 80},
            "kind": {"type": "string", "enum": ACTION_TYPES},
            "label": {"type": "string", "minLength": 1, "maxLength": 180},
            # The first manifest uses a compact text whiteboard action. More
            # complex media payloads are requested only after the lesson opens.
            "payload": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 900}},
            },
            "durationMs": {"type": ["integer", "null"], "minimum": 0, "maximum": 30000},
        },
    }
    outline_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["conceptId", "title", "objective", "sourceAnchorIds"],
        "properties": {
            "conceptId": {"type": "string", "minLength": 1, "maxLength": 80},
            "title": {"type": "string", "minLength": 1, "maxLength": 160},
            "objective": {"type": "string", "minLength": 1, "maxLength": 420},
            "sourceAnchorIds": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "string", "enum": anchors},
            },
        },
    }
    stage_schema = assessment_stage_schema(anchors, max_prompt_length=520)
    scene_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["sceneId", "conceptId", "type", "title", "explanation", "keyPoints", "workedExample", "commonMistakes", "sourceAnchorIds", "actions", "config", "checkpoint", "stages"],
        "properties": {
            "sceneId": {"type": "string", "minLength": 1, "maxLength": 80},
            "conceptId": {"type": "string", "minLength": 1, "maxLength": 80},
            "type": {"type": "string", "enum": ["topic", "whiteboard", "two_d", "three_d", "predict_checkpoint", "retrieval", "teach_back", "exam_bridge", "question_bank"]},
            "title": {"type": "string", "minLength": 1, "maxLength": 160},
            "explanation": {"type": "string", "minLength": 80, "maxLength": 2400},
            "keyPoints": {"type": "array", "minItems": 3, "maxItems": 6, "items": {"type": "string", "minLength": 1, "maxLength": 360}},
            "workedExample": {"type": ["string", "null"], "maxLength": 1800},
            "commonMistakes": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string", "minLength": 1, "maxLength": 360}},
            "sourceAnchorIds": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {"type": "string", "enum": anchors},
            },
            "actions": {"type": "array", "minItems": 4, "maxItems": 6, "items": action_schema},
            "config": {"type": "object", "maxProperties": 12},
            "checkpoint": checkpoint_schema,
            "stages": {"type": "array", "minItems": 4, "maxItems": 4, "items": stage_schema},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["studyPlanId", "sourceIds", "chapterSelection", "sourcePackVersion", "recordVersion", "outline", "scenes", "pastQuestionAnalysis"],
        "properties": {
            "studyPlanId": {"type": "string", "minLength": 1, "maxLength": 100},
            "sourceIds": {"type": "array", "minItems": 1, "maxItems": 20, "items": {"type": "string", "enum": list(request.source_ids)}},
            "chapterSelection": {"type": "string", "enum": ["chapter_1", "all"]},
            "sourcePackVersion": {"type": "string", "minLength": 1, "maxLength": 160},
            "recordVersion": {"type": "integer", "minimum": 1},
            "outline": {"type": "array", "minItems": 1, "maxItems": 12, "items": outline_schema},
            "scenes": {"type": "array", "minItems": 1, "maxItems": 12, "items": scene_schema},
            "pastQuestionAnalysis": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 500}},
        },
    }


def normalize_live_study_plan(plan: dict, request: StudyPlanRequest) -> dict:
    """Normalize provider-shaped instructional metadata without adding lesson facts."""
    if not isinstance(plan.get("recordVersion"), int) or plan.get("recordVersion", 0) < 1:
        plan["recordVersion"] = 1
    plan["pastQuestionAnalysis"] = [str(item).strip() for item in (plan.get("pastQuestionAnalysis") or []) if str(item).strip()][:6]
    interactive_types = {"predict_checkpoint": "predict", "retrieval": "retrieval", "teach_back": "teach_back", "exam_bridge": "exam_bridge"}
    for outline in plan.get("outline", []):
        if not isinstance(outline, dict):
            continue
        title = str(outline.get("title") or outline.get("objective") or outline.get("conceptId") or "Generated concept").strip()
        outline["title"] = title
        outline["objective"] = str(outline.get("objective") or title).strip()
        outline["sourceAnchorIds"] = list(outline.get("sourceAnchorIds") or [])
    for scene in plan.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        config = scene.get("config") if isinstance(scene.get("config"), dict) else {}
        explanation = scene.get("explanation") or config.get("description") or scene.get("title") or ""
        scene["explanation"] = str(explanation).strip()
        scene["title"] = str(scene.get("title") or scene["explanation"][:96] or "Generated learning scene").strip()
        scene["keyPoints"] = [str(item).strip() for item in (scene.get("keyPoints") or []) if str(item).strip()][:6]
        scene["workedExample"] = str(scene.get("workedExample") or "").strip() or None
        scene["commonMistakes"] = [str(item).strip() for item in (scene.get("commonMistakes") or []) if str(item).strip()][:4]
        normalized_actions = []
        for index, action in enumerate(scene.get("actions") or []):
            if not isinstance(action, dict):
                continue
            payload = action.get("payload")
            if isinstance(payload, dict):
                normalized_payload = payload
            elif payload is None:
                normalized_payload = {"text": str(action.get("label") or "")}
            else:
                normalized_payload = {"text": str(payload)}
            normalized_actions.append({
                "actionId": str(action.get("actionId") or f"{scene.get('sceneId', 'scene')}-action-{index + 1}"),
                "kind": str(action.get("kind") or "write"),
                "label": str(action.get("label") or "Model-authored step"),
                "payload": normalized_payload,
                "durationMs": action.get("durationMs") if isinstance(action.get("durationMs"), int) and action.get("durationMs") >= 0 else None,
            })
        if not normalized_actions and scene["explanation"]:
            normalized_actions.append({
                "actionId": f"{scene.get('sceneId', 'scene')}-explanation",
                "kind": "write",
                "label": "Model-authored explanation",
                "payload": {"text": scene["explanation"]},
                "durationMs": None,
            })
        scene["actions"] = normalized_actions
        normalized_stages = []
        for index, stage in enumerate(scene.get("stages") or []):
            if not isinstance(stage, dict):
                continue
            options = normalize_answer_options(stage.get("options") or stage.get("choices"))
            raw_kind = stage.get("kind") or stage.get("stageKind") or stage.get("type")
            raw_prompt = stage.get("prompt") or stage.get("stem") or stage.get("question")
            raw_source_anchors = stage.get("sourceAnchorIds") or stage.get("sourceAnchors")
            normalized_stages.append({
                "stageId": str(stage.get("stageId") or stage.get("id") or f"{scene.get('sceneId', 'topic')}-stage-{index + 1}"),
                "kind": str(raw_kind or "teach_back"),
                "title": str(stage.get("title") or stage.get("kind") or "Check your understanding"),
                "prompt": str(raw_prompt or scene["explanation"] or scene["title"]),
                "responseType": str(stage.get("responseType") or ("single_choice" if options else "long_text")),
                "options": options,
                "sourceAnchorIds": list(raw_source_anchors or scene.get("sourceAnchorIds") or []),
            })
        if not normalized_stages and isinstance(scene.get("checkpoint"), dict):
            checkpoint = scene["checkpoint"]
            normalized_stages.append({
                "stageId": f"{scene.get('sceneId', 'scene')}-stage-1",
                "kind": str(checkpoint.get("kind") or "teach_back"),
                "title": str(checkpoint.get("kind") or "Check your understanding"),
                "prompt": str(checkpoint.get("prompt") or scene["explanation"]),
                "responseType": str(checkpoint.get("responseType") or "long_text"),
                "options": normalize_answer_options(checkpoint.get("options")),
                "sourceAnchorIds": list(checkpoint.get("sourceAnchorIds") or scene.get("sourceAnchorIds") or []),
            })
        stage_order = {"definition": 0, "mcq": 1, "formula": 2, "diagram": 2, "numerical": 2, "teach_back": 3}
        ordered_stages = sorted(normalized_stages, key=lambda stage: stage_order.get(stage.get("kind"), 4))
        # Providers occasionally return a duplicate application stage or an
        # extra learner check. Once all required kinds exist, keep the first
        # model-authored instance of each ladder position and expose the
        # canonical four-stage flow to the validator and learner.
        required_kinds = {"definition", "mcq", "teach_back"}
        application_kinds = {"formula", "diagram", "numerical"}
        if (
            required_kinds.issubset({stage.get("kind") for stage in ordered_stages})
            and any(stage.get("kind") in application_kinds for stage in ordered_stages)
        ):
            selected_definition = next(stage for stage in ordered_stages if stage.get("kind") == "definition")
            selected_mcq = next(stage for stage in ordered_stages if stage.get("kind") == "mcq")
            selected_application = next(stage for stage in ordered_stages if stage.get("kind") in application_kinds)
            selected_teach_back = next(stage for stage in ordered_stages if stage.get("kind") == "teach_back")
            scene["stages"] = [selected_definition, selected_mcq, selected_application, selected_teach_back]
        else:
            scene["stages"] = ordered_stages
        scene_type = str(scene.get("type") or "")
        checkpoint = scene.get("checkpoint") if isinstance(scene.get("checkpoint"), dict) else None
        # Some OpenAI-compatible models honor the checkpoint schema but flatten
        # the scene type to a presentation type. Recover the intended interaction
        # from the model-authored checkpoint kind before applying structural
        # fallbacks; this never creates a prompt or source anchor.
        checkpoint_kind = str((checkpoint or {}).get("kind") or "")
        checkpoint_scene_type = next((candidate for candidate, kind in interactive_types.items() if kind == checkpoint_kind), None)
        if scene_type not in interactive_types and checkpoint_scene_type:
            scene_type = checkpoint_scene_type
            scene["type"] = checkpoint_scene_type
        if scene_type in interactive_types:
            checkpoint = checkpoint or {}
            options = normalize_answer_options(checkpoint.get("options"))
            checkpoint = {
                "kind": str(checkpoint.get("kind") or interactive_types[scene_type]),
                "prompt": str(checkpoint.get("prompt") or scene["explanation"] or scene.get("title") or "Respond to this scene."),
                "responseType": str(checkpoint.get("responseType") or ("single_choice" if options else "long_text")),
                "options": options,
                "sourceAnchorIds": list(checkpoint.get("sourceAnchorIds") or scene.get("sourceAnchorIds") or []),
            }
        scene["checkpoint"] = checkpoint
    scenes = [scene for scene in plan.get("scenes", []) if isinstance(scene, dict)]
    scene_types = {str(scene.get("type")) for scene in scenes}
    # If the model supplied several checkpoint-bearing scenes but flattened
    # their labels, distribute those existing scenes across the requested
    # learning interactions. This is metadata repair only; all explanatory
    # content remains model-authored.
    occupied = {str(scene.get("type")) for scene in scenes}
    for target_type in ("predict_checkpoint", "retrieval", "teach_back", "exam_bridge"):
        if target_type in occupied:
            continue
        candidate = next(
            (
                scene
                for scene in scenes
                if scene.get("type") not in interactive_types
                and isinstance(scene.get("checkpoint"), dict)
                and scene.get("type") != "whiteboard"
                and not (
                    scene.get("type") in {"two_d", "three_d"}
                    and sum(1 for item in scenes if item.get("type") in {"two_d", "three_d"}) <= 1
                )
            ),
            None,
        )
        if candidate is not None:
            candidate["type"] = target_type
            normalize_live_study_plan({"scenes": [candidate]}, request)
            occupied.add(target_type)
    scene_types = {str(scene.get("type")) for scene in scenes}
    if "whiteboard" not in scene_types:
        whiteboard_candidate = next((scene for scene in scenes if scene.get("type") not in interactive_types and any(str(action.get("kind")) in {"write", "draw", "equation", "spotlight"} for action in scene.get("actions", []))), None)
        if whiteboard_candidate is not None:
            whiteboard_candidate["type"] = "whiteboard"
    scene_types = {str(scene.get("type")) for scene in scenes}
    if not {"two_d", "three_d"}.intersection(scene_types):
        visual_candidate = next((scene for scene in scenes if scene.get("type") not in interactive_types and scene.get("type") != "whiteboard" and isinstance(scene.get("config"), dict) and scene.get("config")), None)
        visual_candidate = visual_candidate or next((scene for scene in scenes if scene.get("type") not in interactive_types and scene.get("type") != "whiteboard" and any(term in json.dumps(scene.get("config", {}), ensure_ascii=False).lower() for term in ("2d", "3d", "plot", "graph", "diagram", "visual"))), None)
        if visual_candidate is not None:
            visual_candidate["type"] = "three_d" if "3d" in json.dumps(visual_candidate.get("config", {}), ensure_ascii=False).lower() else "two_d"
    def section_order(item: dict, index: int) -> tuple:
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)+)", str(item.get("title") or item.get("sceneId") or ""))
        return (0, tuple(int(part) for part in match.group(1).split(".")), index) if match else (1, (), index)
    plan["scenes"] = [item for index, item in sorted(enumerate(scenes), key=lambda pair: section_order(pair[1], pair[0]))]
    return plan


def missing_required_scene_types(plan: dict) -> list[str]:
    scenes = [scene for scene in plan.get("scenes", []) if isinstance(scene, dict)]
    staged_topics = [scene for scene in scenes if scene.get("stages")]
    if staged_topics:
        missing: list[str] = []
        # Once any topic uses the staged learning loop, every returned scene
        # belongs to that loop. Treat an un-staged scene as missing the full
        # ladder so the provider repair pass can fill it instead of allowing a
        # mixed legacy/staged manifest through to the API validator.
        topics_to_check = staged_topics + [scene for scene in scenes if not scene.get("stages")]
        for scene in topics_to_check:
            scene_stages = [stage for stage in scene.get("stages", []) if isinstance(stage, dict)]
            stage_kinds = {str(stage.get("kind")) for stage in scene_stages}
            for required_kind in ("definition", "mcq", "teach_back"):
                if required_kind not in stage_kinds and required_kind not in missing:
                    missing.append(required_kind)
            mcq_stage = next((stage for stage in scene_stages if stage.get("kind") == "mcq"), None)
            if mcq_stage is not None and (
                mcq_stage.get("responseType") != "single_choice"
                or len(mcq_stage.get("options") or []) < 3
            ) and "mcq" not in missing:
                missing.append("mcq")
            if not {"formula", "diagram", "numerical"}.intersection(stage_kinds) and "formula_or_diagram_or_numerical" not in missing:
                missing.append("formula_or_diagram_or_numerical")
        return missing
    present = {str(scene.get("type")) for scene in plan.get("scenes", []) if isinstance(scene, dict)}
    # Exam practice is an optional extension, not a publication gate. This
    # prevents a valid learning loop from being discarded because a provider
    # omitted one exam-style scene.
    required = ["whiteboard", "predict_checkpoint", "retrieval", "teach_back"]
    return [item for item in required if item not in present]


def module_chat_schema(request: ModuleChatRequest) -> dict:
    """Structured output contract for the contextual module copilot."""
    scene_ids = sorted({str(scene.get("sceneId")) for scene in request.scenes if scene.get("sceneId")})
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["state", "reply", "reasonCode", "sourceAnchorIds", "action"],
        "properties": {
            "state": {"type": "string", "enum": ["answered", "abstained", "needs_human_review", "action_only"]},
            "reply": {"type": "string"},
            "reasonCode": {"type": ["string", "null"]},
            "sourceAnchorIds": {"type": "array", "items": {"type": "string", "enum": list(request.approved_source_ids)}},
            "action": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "sceneId", "modeId", "reason"],
                "properties": {
                    "kind": {"type": "string", "enum": CHAT_ACTION_TYPES},
                    # Fireworks/Qwen accepts nullable types but rejects an enum
                    # containing JSON null. Django validates scene and mode IDs
                    # against the request after parsing.
                    "sceneId": {"type": ["string", "null"]},
                    "modeId": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
            },
        },
    }


class LLMProvider:
    mode = "human_review"

    def audit(self, request: AuditRequest) -> dict:
        raise NotImplementedError

    def clarify(self, request: ClarificationRequest) -> dict:
        raise NotImplementedError

    def health(self) -> dict:
        return {"providerMode": self.mode, "available": False, "schemaVersion": "contracts/v1"}

    def classify_claim(self, text: str, claim_id: str) -> dict:
        raise NotImplementedError

    def evaluate_checkpoint(self, request: dict) -> dict:
        """Evaluate a bounded checkpoint without accepting browser-supplied anchors."""
        raise NotImplementedError

    def recommend_learning_mode(self, context: dict) -> dict:
        raise NotImplementedError

    def chat(self, request: ModuleChatRequest) -> dict:
        raise NotImplementedError

    def generate_study_plan(self, request: StudyPlanRequest) -> dict:
        raise NotImplementedError


def _contains(text: str, *terms: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


class FixtureProvider(LLMProvider):
    mode = "codex_fixture"

    def health(self) -> dict:
        return {"providerMode": self.mode, "available": True, "model": "fixture-v1", "schemaVersion": "contracts/v1", "message": "Deterministic local fixture; not live GPT output."}

    def classify_claim(self, text: str, claim_id: str) -> dict:
        clean = " ".join(text.split())[:2000]
        lower = clean.lower()
        # Keep these rules deliberately explicit: the fixture is the deterministic
        # local substitute for a model, so each frozen misconception must map to a
        # source-bound verdict rather than falling through to "supported".
        if _contains(
            lower,
            "light makes",
            "sunlight becomes",
            "sun makes",
            "energy becomes mass",
            "sunlight directly into",
            "sunlight ... atoms",
            "sunlight into the atoms",
            "sunlight provides mass",
            "sunlight is the mass",
            "light is the mass",
        ) or ("sunlight" in lower and ("dry mass" in lower or "plant mass" in lower or "atoms" in lower)):
            return {"claimId": claim_id, "learnerText": clean, "verdict": "misconception", "misconceptionType": "source_of_matter", "probe": "Which input supplies atoms, and which input supplies energy?", "sourceAnchorIds": ["photosynthesis-v1-span-04"]}
        if _contains(lower, "soil is the main", "soil provides most", "from the soil", "soil nutrients make up most"):
            return {"claimId": claim_id, "learnerText": clean, "verdict": "misconception", "misconceptionType": "source_of_matter", "probe": "Where does the carbon in plant sugars come from?", "sourceAnchorIds": ["photosynthesis-v1-span-05", "photosynthesis-v1-span-06"]}
        if (
            _contains(lower, "water is not", "water isn't", "water is irrelevant", "water does not", "water doesn't")
            and _contains(lower, "carbon dioxide", "co2", "only carbon")
        ):
            return {"claimId": claim_id, "learnerText": clean, "verdict": "misconception", "misconceptionType": "source_of_matter", "probe": "What material atoms does water contribute to sugars?", "sourceAnchorIds": ["photosynthesis-v1-span-03"]}
        if _contains(lower, "carbon dioxide is the energy", "carbon dioxide is energy", "co2 is the energy", "co2 provides energy", "carbon dioxide provides energy"):
            return {"claimId": claim_id, "learnerText": clean, "verdict": "misconception", "misconceptionType": "causal_mechanism", "probe": "Which input supplies energy, and which inputs supply matter?", "sourceAnchorIds": ["photosynthesis-v1-span-08"]}
        if _contains(lower, "only water", "water alone", "water makes all"):
            return {"claimId": claim_id, "learnerText": clean, "verdict": "misconception", "misconceptionType": "causal_mechanism", "probe": "What other material input supplies carbon?", "sourceAnchorIds": ["photosynthesis-v1-span-02", "photosynthesis-v1-span-03"]}
        if not clean:
            return {"claimId": claim_id, "learnerText": "(empty)", "verdict": "needs_human_review", "probe": "What is the main matter input?", "sourceAnchorIds": []}
        if _contains(
            lower,
            "get what they need from the ground",
            "from the ground and the sun",
            "from ground and sun",
            "from the ground",
        ) and _contains(lower, "sun"):
            return {"claimId": claim_id, "learnerText": clean, "verdict": "needs_precision", "probe": "Can you name the matter inputs and the role of light?", "sourceAnchorIds": ["photosynthesis-v1-span-08"]}
        if len(clean) < 30:
            return {"claimId": claim_id, "learnerText": clean, "verdict": "needs_precision", "probe": "Can you name the matter inputs and the role of light?", "sourceAnchorIds": ["photosynthesis-v1-span-08"]}
        anchors = ["photosynthesis-v1-span-01", "photosynthesis-v1-span-07"]
        if _contains(lower, "carbon dioxide", "co2"):
            anchors.insert(0, "photosynthesis-v1-span-02")
        return {"claimId": claim_id, "learnerText": clean, "verdict": "supported", "probe": "Can you distinguish matter inputs from the energy input?", "sourceAnchorIds": anchors[:3]}

    def audit(self, request: AuditRequest) -> dict:
        text = " ".join(request.learner_text.split())
        if not text:
            raise ProviderOutputError("learnerText must not be empty")
        pieces = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text) if p.strip()]
        pieces = pieces[:12] or [text]
        claims = [self.classify_claim(piece, f"claim-{i + 1:02d}") for i, piece in enumerate(pieces)]
        # Guarantee a useful three-claim demo when the learner submits a paragraph.
        if len(claims) == 1:
            claims.extend([
                self.classify_claim("Light supplies energy rather than plant mass.", "claim-02"),
                self.classify_claim("Water and carbon dioxide are matter inputs.", "claim-03"),
            ])
        return {"claims": claims[:12], "schemaVersion": "audit.v1"}

    def clarify(self, request: ClarificationRequest) -> dict:
        q = request.question.strip()
        if len(q) < 3 or not _contains(q, "why", "where", "how", "what", "source", "mass", "carbon", "soil", "light", "water"):
            return {"state": "abstained", "reasonCode": "outside_source_pack", "sourceAnchorIds": []}
        allowed = [span.get("spanId") for span in request.source_spans if span.get("spanId")]
        def anchors(*preferred: str) -> list[str]:
            selected = [item for item in preferred if item in allowed]
            return selected or allowed[:2]
        claim = request.claim
        misconception = claim.get("misconceptionType")
        if misconception == "source_of_matter":
            answer = "Carbon dioxide supplies carbon atoms that become part of sugars; light supplies energy, not plant dry mass."
            source_anchor_ids = anchors("photosynthesis-v1-span-02", "photosynthesis-v1-span-04", "photosynthesis-v1-span-06")
        else:
            answer = "Photosynthesis uses light energy to combine carbon dioxide and water into sugars."
            source_anchor_ids = anchors("photosynthesis-v1-span-03", "photosynthesis-v1-span-07")
        return {"state": "answered", "answer": answer, "sourceAnchorIds": source_anchor_ids}

    def evaluate_checkpoint(self, request: dict) -> dict:
        manifest = request.get("manifest") or {}
        prediction = str(request.get("prediction") or request.get("explanation") or "").strip()
        confidence = max(1, min(5, int(request.get("confidence") or 3)))
        correct = len(prediction) >= 20
        if request.get("kind") == "explain":
            correct = len(prediction) >= 30
        result = {
            "state": "complete",
            "prediction": prediction,
            "prompt": manifest.get("prompt", "What evidence would change your mind?"),
            "responseType": manifest.get("responseType", "text"),
            "sourceAnchorIds": list(manifest.get("sourceAnchorIds", [])),
            "correct": correct,
            "understandingScore": 80 if correct else 35,
            "confidenceScore": confidence,
            "overconfidence": confidence >= 4 and not correct,
            "feedback": "Good enough to continue." if correct else "Add the key idea and the reason it is true, then try again.",
            "remediation": "Review the topic definition and the revealed whiteboard action before retrying." if not correct else "",
            "mistake": "" if correct else "The response does not yet demonstrate the requested idea.",
            "correctAnswer": "" if correct else "Use the topic definition and worked example to state the requested idea.",
            "correction": "" if correct else "Include the relevant concept, relationship, and reason in the next attempt.",
            "nextAction": "advance" if correct else "retry",
            "providerMode": self.mode,
        }
        if not correct:
            stage = manifest.get("stage") if isinstance(manifest.get("stage"), dict) else {}
            result["retryPrompt"] = f"Try a similar check: explain or apply the same idea from {stage.get('title') or 'this topic'}."
            result["retryOptions"] = stage.get("options") if request.get("kind") == "mcq" else None
            result["retryResponseType"] = stage.get("responseType") or "long_text"
            result["retrySourceAnchorIds"] = list(manifest.get("sourceAnchorIds", []))
        return normalize_retry_result(result, manifest)

    def recommend_learning_mode(self, context: dict) -> dict:
        return {"modeId": context.get("modeId", "self_explain"), "reason": context.get("reason", "fixture_rule"), "providerMode": self.mode}

    def chat(self, request: ModuleChatRequest) -> dict:
        """Small deterministic stand-in used only by backend tests."""
        message = request.message.strip().lower()
        scene_ids = [str(scene.get("sceneId")) for scene in request.scenes if scene.get("sceneId")]
        active_index = max(0, min(request.active_scene_index, max(len(scene_ids) - 1, 0)))
        action = {"kind": "none", "sceneId": None, "modeId": None, "reason": "question_answered"}
        if any(term in message for term in ("next", "continue", "forward")) and active_index < len(scene_ids) - 1:
            action = {"kind": "next_scene", "sceneId": scene_ids[active_index + 1], "modeId": None, "reason": "learner_requested_next_scene"}
        elif any(term in message for term in ("previous", "back", "again")) and active_index > 0:
            action = {"kind": "previous_scene", "sceneId": scene_ids[active_index - 1], "modeId": None, "reason": "learner_requested_previous_scene"}
        elif any(term in message for term in ("visual", "graph", "plot", "diagram")):
            visual = next((scene for scene in request.scenes if scene.get("hasVisualization")), None)
            if visual:
                action = {"kind": "show_visualization", "sceneId": str(visual.get("sceneId")), "modeId": None, "reason": "learner_requested_visualization"}
        elif any(term in message for term in ("worked example", "example", "show me")):
            action = {"kind": "set_learning_mode", "sceneId": request.active_scene_id, "modeId": "worked_example", "reason": "learner_requested_example"}
        elif any(term in message for term in ("predict", "prediction")):
            action = {"kind": "set_learning_mode", "sceneId": request.active_scene_id, "modeId": "predict_reveal", "reason": "learner_requested_prediction"}
        elif any(term in message for term in ("simpler", "repeat", "again", "explain")):
            action = {"kind": "repeat_explanation", "sceneId": request.active_scene_id, "modeId": None, "reason": "learner_requested_explanation"}
        anchors = list(request.approved_source_ids[:2])
        reply = "I can explain the current scene from the approved source material. Ask for a simpler explanation, a worked example, the next scene, or a visualization when one is available."
        if action["kind"] == "show_visualization":
            reply = "Opening the model-authored visualization for this concept."
        elif action["kind"] == "next_scene":
            reply = "Moving to the next learning scene."
        elif action["kind"] == "previous_scene":
            reply = "Moving back to the previous learning scene."
        return {"state": "action_only" if action["kind"] != "none" else "answered", "reply": reply, "reasonCode": None, "sourceAnchorIds": anchors, "action": action, "providerMode": self.mode}

    def generate_study_plan(self, request: StudyPlanRequest) -> dict:
        # The fixture is intentionally loaded from the versioned contract rather
        # than duplicated in a view. This keeps the browser from becoming the
        # authority for scenes, source IDs, or chapter scope.
        if request.subject_id != "dsap":
            return {
                "state": "needs_human_review",
                "reasonCode": "subject_pack_not_available_in_fixture_provider",
                "providerMode": "human_review",
            }
        if request.chapter_selection == "all":
            return {
                "state": "needs_human_review",
                "reasonCode": "full_syllabus_manifest_pending",
                "providerMode": "human_review",
                "sourceIds": request.source_ids or ["dsap-sampling-v1"],
                "chapterSelection": "all",
            }
        if request.source_ids and any(source_id != "dsap-sampling-v1" for source_id in request.source_ids):
            return {
                "state": "needs_human_review",
                "reasonCode": "uploaded_source_requires_instructor_approval",
                "providerMode": "human_review",
                "sourceIds": request.source_ids,
                "chapterSelection": request.chapter_selection,
            }
        path = settings.BASE_DIR.parent / "contracts" / "v3" / "dsap-study-fixture.json"
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ProviderOutputError("study fixture is unavailable") from exc
        plan["chapterSelection"] = request.chapter_selection
        plan["providerMode"] = self.mode
        plan["recordVersion"] = 1
        if request.module_id:
            plan["moduleId"] = request.module_id
        return plan


class OpenAIProvider(LLMProvider):
    mode = "live_openai"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ProviderUnavailable("OPENAI_API_KEY is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ProviderUnavailable("openai package is not installed") from exc
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def health(self) -> dict:
        return {"providerMode": self.mode, "available": True, "model": settings.OPENAI_MODEL, "schemaVersion": "contracts/v1"}

    def _call(self, instruction: str, schema_name: str, schema: dict) -> dict:
        try:
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                input=instruction,
                text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
            )
            raw = getattr(response, "output_text", "")
            if not raw:
                raise ProviderOutputError("OpenAI returned no structured output")
            return load_provider_json(raw)
        except ProviderOutputError:
            raise
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def audit(self, request: AuditRequest) -> dict:
        schema = {
            "type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "maxItems": 12, "items": {
                "type": "object", "additionalProperties": False,
                "required": ["claimId", "learnerText", "verdict", "probe", "sourceAnchorIds"],
                "properties": {
                    "claimId": {"type": "string"}, "learnerText": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["supported", "misconception", "needs_precision", "needs_human_review"]},
                    "misconceptionType": {"type": ["string", "null"]}, "probe": {"type": "string"},
                    "sourceAnchorIds": {"type": "array", "items": {"type": "string"}},
                },
            }}},
        }
        return self._call(f"Audit learner teach-back against only these source spans:\n{request.source_spans}\nLearner text:\n{request.learner_text}", "audit_v1", schema)

    def clarify(self, request: ClarificationRequest) -> dict:
        schema = {"type": "object", "additionalProperties": False, "required": ["state", "sourceAnchorIds"], "properties": {"state": {"type": "string", "enum": ["answered", "abstained", "needs_human_review"]}, "answer": {"type": "string"}, "reasonCode": {"type": "string"}, "sourceAnchorIds": {"type": "array", "items": {"type": "string"}}}}
        return self._call(f"Answer only from source spans. Claim: {request.claim}\nQuestion: {request.question}\nSources: {request.source_spans}", "clarification_v1", schema)

    def evaluate_checkpoint(self, request: dict) -> dict:
        manifest = request.get("manifest") or {}
        allowed_anchor_ids = list(manifest.get("sourceAnchorIds", []))
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["state", "correct", "understandingScore", "overconfidence", "feedback", "remediation", "mistake", "correctAnswer", "correction", "nextAction", "sourceAnchorIds", "retryPrompt", "retryOptions", "retryResponseType", "retrySourceAnchorIds"],
            "properties": {
                "state": {"type": "string", "enum": ["complete", "abstained", "needs_human_review"]},
                "correct": {"type": "boolean"},
                "understandingScore": {"type": "integer", "minimum": 0, "maximum": 100},
                "overconfidence": {"type": "boolean"},
                "feedback": {"type": "string"},
                "remediation": {"type": "string"},
                "mistake": {"type": "string"},
                "correctAnswer": {"type": "string"},
                "correction": {"type": "string"},
                "nextAction": {"type": "string", "enum": ["advance", "retry", "review"]},
                "prediction": {"type": "string"},
                "explanation": {"type": "string"},
                "prompt": {"type": "string"},
                "responseType": {"type": "string"},
                "reasonCode": {"type": "string"},
                "sourceAnchorIds": {"type": "array", "items": {"type": "string"}},
                "retryPrompt": {"type": ["string", "null"]},
                "retryOptions": {"type": ["array", "null"], "maxItems": 4, "items": {"type": "string", "maxLength": 300}},
                "retryResponseType": {"type": ["string", "null"]},
                "retrySourceAnchorIds": {"type": "array", "items": {"type": "string"}},
            },
        }
        instruction = (
            "Evaluate one bounded learning checkpoint using only the supplied manifest and approved source IDs. "
            "Do not invent quotes or source IDs. If the explanation cannot be supported, abstain. "
            f"Manifest: {manifest}\nAllowed source IDs: {allowed_anchor_ids}\n"
            f"Stage: {manifest.get('stage', {})}\nLearner confidence (1=guessing, 5=very confident): {request.get('confidence', 3)}\n"
            f"Learner prediction: {request.get('prediction', '')}\nLearner explanation: {request.get('explanation', '')}\n"
            "Return correct=true only when the answer demonstrates the requested concept. Score understanding from 0 to 100. "
            "Set overconfidence=true when confidence is 4 or 5 but the answer is incorrect or materially incomplete. "
            "Use nextAction advance only for a correct answer; use retry for a fixable mistake and review when the evidence is insufficient. "
            "When not correct, mistake must identify the exact incorrect or missing part, correctAnswer must state the source-grounded answer, correction must explain how to fix it, and remediation must name the exact source-grounded idea or step the learner should review before retrying. "
            "When not correct, also return retryPrompt with one similar but not identical check for the same concept. For an MCQ, return 3 or 4 new plausible text retryOptions with no answer key or correctness flags. For formula, numerical, diagram, or teach-back, return retryOptions as null and keep retryResponseType appropriate to the stage. When correct, set retryPrompt to null, retryOptions to null, and retrySourceAnchorIds to an empty list. "
        )
        result = self._call(instruction, "checkpoint_v1", schema)
        result = normalize_retry_result(result, manifest)
        returned_ids = result.get("sourceAnchorIds", [])
        if any(anchor_id not in allowed_anchor_ids for anchor_id in returned_ids):
            raise ProviderOutputError("provider returned an unapproved source anchor")
        return result

    def recommend_learning_mode(self, context: dict) -> dict:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["modeId", "reason"],
            "properties": {
                "modeId": {"type": "string", "enum": sorted(LEARNING_MODE_IDS)},
                "reason": {"type": "string"},
            },
        }
        result = self._call(f"Choose one learning mode from {sorted(LEARNING_MODE_IDS)} for this evidence context: {context}", "learning_mode_v1", schema)
        result["providerMode"] = self.mode
        return result

    def chat(self, request: ModuleChatRequest) -> dict:
        schema = module_chat_schema(request)
        scene_context = [
            {"sceneId": scene.get("sceneId"), "title": scene.get("title"), "type": scene.get("type"), "hasVisualization": bool(scene.get("hasVisualization")), "hasCheckpoint": bool(scene.get("hasCheckpoint"))}
            for scene in request.scenes
        ]
        instruction = (
            "You are the contextual copilot inside a source-bounded learning module. "
            "Answer the learner's question only from the approved source spans. "
            "You may return one typed navigation or learning action, but never HTML, JavaScript, arbitrary URLs, source quotes, or invented facts. "
            "A visualization may be opened only when a scene is marked hasVisualization. "
            f"Subject: {request.subject_title}; module: {request.module_id}; active scene: {request.active_scene_id}; "
            f"learning mode: {request.learning_mode}; scenes: {scene_context}; history: {request.history[-8:]}; "
            f"approved source spans: {request.source_spans}; learner message: {request.message}"
        )
        result = self._call(instruction, "module_chat_v1", schema)
        allowed = set(request.approved_source_ids)
        if not set(result.get("sourceAnchorIds", [])).issubset(allowed):
            raise ProviderOutputError("provider returned an unapproved chat source anchor")
        result["providerMode"] = self.mode
        return result

    def generate_study_plan(self, request: StudyPlanRequest) -> dict:
        # Only the manifest is model-generated. The server still validates every
        # scene type and source anchor before it reaches a learner.
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["studyPlanId", "sourceIds", "chapterSelection", "sourcePackVersion", "recordVersion", "outline", "scenes"],
            "properties": {
                "studyPlanId": {"type": "string"},
                "sourceIds": {"type": "array", "items": {"type": "string"}},
                "chapterSelection": {"type": "string", "enum": ["chapter_1", "all"]},
                "sourcePackVersion": {"type": "string"},
                "recordVersion": {"type": "integer", "minimum": 1},
                "outline": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["conceptId", "title", "objective", "sourceAnchorIds"], "properties": {"conceptId": {"type": "string"}, "title": {"type": "string"}, "objective": {"type": "string"}, "sourceAnchorIds": {"type": "array", "items": {"type": "string"}}}}},
                "scenes": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["sceneId", "conceptId", "type", "title", "sourceAnchorIds"], "properties": {"sceneId": {"type": "string"}, "conceptId": {"type": "string"}, "type": {"type": "string", "enum": ["whiteboard", "two_d", "three_d", "predict_checkpoint", "retrieval", "teach_back", "exam_bridge", "question_bank"]}, "title": {"type": "string"}, "sourceAnchorIds": {"type": "array", "items": {"type": "string"}}, "actions": {"type": "array", "items": {"type": "object"}}, "config": {"type": "object"}}}},
            },
        }
        schema = compact_study_plan_schema(request)
        instruction = (
            "Create a complete learner-ready study module, not a short outline. Every scene must include a substantial explanation and learner-facing interaction content. "
            "Use only those IDs; never write source quotes; use only the listed scene and action types. "
            f"Subject: {request.subject_id}; module: {request.module_id}; chapter: {request.chapter_selection}; "
            f"source IDs: {request.source_ids}; approved anchor IDs: {request.approved_source_ids}."
        )
        result = normalize_live_study_plan(self._call(instruction, "study_manifest_v1", schema), request)
        returned_ids = set(result.get("sourceIds", []))
        returned_anchors = {anchor for item in (result.get("outline", []) + result.get("scenes", [])) for anchor in item.get("sourceAnchorIds", [])}
        allowed = set(request.approved_source_ids)
        if not returned_ids.issubset(set(request.source_ids or ["dsap-sampling-v1"])) or not returned_anchors.issubset(allowed):
            raise ProviderOutputError("provider returned an unapproved study source")
        result["providerMode"] = self.mode
        return result


class FireworksProvider(LLMProvider):
    """OpenAI-compatible Fireworks provider for real module generation."""

    mode = "live_fireworks"

    def __init__(self) -> None:
        if not settings.FIREWORKS_API_KEY:
            raise ProviderUnavailable("FIREWORKS_API_KEY is not configured")
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise ProviderUnavailable("openai package is not installed") from exc
        self.client = OpenAI(
            api_key=settings.FIREWORKS_API_KEY,
            base_url=settings.FIREWORKS_BASE_URL,
            timeout=settings.FIREWORKS_TIMEOUT_SECONDS,
            # The API view owns the retry/abstention boundary. Disable the SDK
            # retry multiplier so a transient provider stall cannot block the
            # Django worker for several timeout windows.
            max_retries=0,
        )

    def health(self) -> dict:
        return {
            "providerMode": self.mode,
            "available": bool(settings.FIREWORKS_API_KEY),
            "model": settings.FIREWORKS_MODEL,
            "baseUrl": settings.FIREWORKS_BASE_URL,
            "schemaVersion": "contracts/v3",
        }

    def audit(self, request: AuditRequest) -> dict:
        schema = {
            "type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "maxItems": 12, "items": {"type": "object", "additionalProperties": False, "required": ["claimId", "learnerText", "verdict", "probe", "sourceAnchorIds"], "properties": {
                "claimId": {"type": "string"}, "learnerText": {"type": "string"}, "verdict": {"type": "string", "enum": ["supported", "misconception", "needs_precision", "needs_human_review"]}, "misconceptionType": {"type": ["string", "null"]}, "probe": {"type": "string"}, "sourceAnchorIds": {"type": "array", "items": {"type": "string"}},
            }}}},
        }
        result = self._chat_json(f"Audit this learner explanation only against these approved source spans: {request.source_spans}. Learner explanation: {request.learner_text}. Return atomic claims, a verdict, one probe, and source anchor IDs.", "audit_v3", schema)
        result["providerMode"] = self.mode
        return result

    def clarify(self, request: ClarificationRequest) -> dict:
        schema = {"type": "object", "additionalProperties": False, "required": ["state", "sourceAnchorIds"], "properties": {"state": {"type": "string", "enum": ["answered", "abstained", "needs_human_review"]}, "answer": {"type": "string"}, "reasonCode": {"type": "string"}, "sourceAnchorIds": {"type": "array", "items": {"type": "string"}}}}
        allowed = [span.get("spanId") for span in request.source_spans if span.get("spanId")]
        result = self._chat_json(f"Answer this learner question only from the supplied source spans. Claim: {request.claim}. Question: {request.question}. Allowed anchors: {allowed}.", "clarification_v3", schema)
        if not set(result.get("sourceAnchorIds", [])).issubset(set(allowed)):
            raise ProviderOutputError("Fireworks returned an unapproved clarification anchor")
        result["providerMode"] = self.mode
        return result

    def evaluate_checkpoint(self, request: dict) -> dict:
        manifest = request.get("manifest") or {}
        allowed = list(manifest.get("sourceAnchorIds", []))
        schema = {"type": "object", "additionalProperties": False, "required": ["state", "correct", "understandingScore", "overconfidence", "feedback", "remediation", "mistake", "correctAnswer", "correction", "nextAction", "sourceAnchorIds", "retryPrompt", "retryOptions", "retryResponseType", "retrySourceAnchorIds"], "properties": {"state": {"type": "string", "enum": ["complete", "abstained", "needs_human_review"]}, "correct": {"type": "boolean"}, "understandingScore": {"type": "integer", "minimum": 0, "maximum": 100}, "overconfidence": {"type": "boolean"}, "feedback": {"type": "string"}, "remediation": {"type": "string"}, "mistake": {"type": "string"}, "correctAnswer": {"type": "string"}, "correction": {"type": "string"}, "nextAction": {"type": "string", "enum": ["advance", "retry", "review"]}, "prediction": {"type": "string"}, "explanation": {"type": "string"}, "prompt": {"type": "string"}, "responseType": {"type": "string"}, "reasonCode": {"type": "string"}, "sourceAnchorIds": {"type": "array", "items": {"type": "string"}}, "retryPrompt": {"type": ["string", "null"]}, "retryOptions": {"type": ["array", "null"], "maxItems": 4, "items": {"type": "string", "maxLength": 300}}, "retryResponseType": {"type": ["string", "null"]}, "retrySourceAnchorIds": {"type": "array", "items": {"type": "string"}}}}
        evaluation_instruction = (
            f"Evaluate a bounded checkpoint using only this manifest and its approved source spans. "
            f"Manifest: {manifest}. Approved source spans: {manifest.get('sourceSpans', [])}. "
            f"Stage: {manifest.get('stage', {})}. Learner confidence (1=guessing, 5=very confident): {request.get('confidence', 3)}. "
            f"Learner prediction: {request.get('prediction', '')}. Learner explanation: {request.get('explanation', '')}. "
        )
        if str(manifest.get("stageKind") or "").lower() == "mcq" or str(request.get("kind") or "").lower() == "mcq":
            evaluation_instruction += (
                "This is a multiple-choice stage. Treat the learner explanation as the exact selected option. Compare it against the exact options in Stage, determine the correct option from the approved source spans, and never evaluate against a different or generic question. If incorrect, correctAnswer must identify the correct option text or state the source-grounded answer for this exact stem. "
            )
        evaluation_instruction += (
            "Return correct=true only when the answer demonstrates the requested concept. Score understanding from 0 to 100. "
            "Set overconfidence=true when confidence is 4 or 5 but the answer is incorrect or materially incomplete. "
            "Use nextAction advance only for a correct answer; use retry for a fixable mistake and review when evidence is insufficient. When not correct, mistake must identify the exact incorrect or missing part, correctAnswer must state the source-grounded answer, correction must explain how to fix it, and remediation must name the exact source-grounded idea to review before retrying. "
            "When not correct, also return retryPrompt with one similar but not identical check for the same concept. For an MCQ, return 3 or 4 new plausible text retryOptions with no answer key or correctness flags. For formula, numerical, diagram, or teach-back, return retryOptions as null and keep retryResponseType appropriate to the stage. When correct, set retryPrompt to null, retryOptions to null, and retrySourceAnchorIds to an empty list."
        )
        result = self._chat_json(
            evaluation_instruction,
            "checkpoint_v4",
            schema,
            attachment=request.get("attachment"),
        )
        # The evaluator may echo a candidate locator rather than the exact
        # server-owned anchor ID. Never expose that untrusted locator, and do
        # not turn an otherwise valid learner evaluation into a 422. The
        # request manifest has already been checked against approved anchors.
        returned_anchors = result.get("sourceAnchorIds")
        if not isinstance(returned_anchors, list):
            returned_anchors = []
        result["sourceAnchorIds"] = [anchor for anchor in returned_anchors if anchor in allowed] or allowed
        result = normalize_retry_result(result, manifest)
        result["providerMode"] = self.mode
        return result

    def recommend_learning_mode(self, context: dict) -> dict:
        schema = {"type": "object", "additionalProperties": False, "required": ["modeId", "reason"], "properties": {"modeId": {"type": "string", "enum": sorted(LEARNING_MODE_IDS)}, "reason": {"type": "string"}}}
        result = self._chat_json(f"Choose the best learning mode from {sorted(LEARNING_MODE_IDS)} for this observed evidence: {context}.", "learning_mode_v3", schema)
        result["providerMode"] = self.mode
        return result

    def chat(self, request: ModuleChatRequest) -> dict:
        schema = module_chat_schema(request)
        scene_context = [
            {"sceneId": scene.get("sceneId"), "title": scene.get("title"), "type": scene.get("type"), "hasVisualization": bool(scene.get("hasVisualization")), "hasCheckpoint": bool(scene.get("hasCheckpoint"))}
            for scene in request.scenes
        ]
        instruction = (
            "You are the contextual copilot inside a source-bounded learning module. "
            "Answer the learner's question only from the approved source spans. "
            "Return one typed action only when it helps the learner control this module. "
            "Never return HTML, JavaScript, arbitrary URLs, source quotes, or invented facts. "
            "A visualization may be opened only for a scene marked hasVisualization. "
            f"Subject: {request.subject_title}; module: {request.module_id}; active scene: {request.active_scene_id}; "
            f"learning mode: {request.learning_mode}; scenes: {scene_context}; history: {request.history[-8:]}; "
            f"approved source spans: {request.source_spans}; learner message: {request.message}"
        )
        result = self._chat_json(instruction, "module_chat_v3", schema)
        allowed = set(request.approved_source_ids)
        if not set(result.get("sourceAnchorIds", [])).issubset(allowed):
            raise ProviderOutputError("Fireworks returned an unapproved chat source anchor")
        action = result.get("action") if isinstance(result.get("action"), dict) else {}
        action_kind = str(action.get("kind") or "none")
        if action_kind == "show_visualization":
            target = next((scene for scene in request.scenes if str(scene.get("sceneId")) == str(action.get("sceneId"))), None)
            if not target or not target.get("hasVisualization"):
                raise ProviderOutputError("chat requested an unavailable visualization")
        result["providerMode"] = self.mode
        return result

    def _chat_json(self, instruction: str, schema_name: str, schema: dict, *, attachment: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                user_content: str | list[dict] = instruction
                if isinstance(attachment, dict) and isinstance(attachment.get("dataUrl"), str):
                    user_content = [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": attachment["dataUrl"]}},
                    ]
                response = self.client.chat.completions.create(
                    model=settings.FIREWORKS_MODEL,
                    temperature=0.0,
                    # A full module contains learner-facing explanations,
                    # whiteboard actions, visualization config, and four
                    # checkpoints. Keep enough completion budget for the
                    # manifest instead of silently truncating it mid-object.
                    max_tokens=20000,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a rigorous curriculum architect. Return only JSON matching the supplied schema. Use only the supplied source candidates. Never invent citations, quotes, facts, or source IDs. Draft content may require human review.",
                        },
                        {"role": "user", "content": user_content},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                    },
                )
                message = response.choices[0].message.content if response.choices else ""
                if isinstance(message, list):
                    message = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in message)
                if not message:
                    raise ProviderOutputError("Fireworks returned no structured output")
                # Qwen occasionally emits literal newlines inside long string
                # fields despite JSON-schema mode. Permit control characters;
                # the typed manifest and source validators remain authoritative.
                return load_provider_json(message)
            except ProviderOutputError:
                raise
            except json.JSONDecodeError as exc:
                try:
                    from json_repair import repair_json
                    repaired = repair_json(message, return_objects=True)
                    is_manifest = schema_name.startswith("study_manifest")
                    if isinstance(repaired, dict) and repaired and (not is_manifest or isinstance(repaired.get("scenes"), list)):
                        return repaired
                except Exception:
                    pass
                last_error = exc
                if attempt == 0:
                    continue
            except Exception as exc:
                raise ProviderUnavailable(str(exc)) from exc
        raise ProviderUnavailable(f"Fireworks returned malformed structured output after retry: {last_error}") from last_error

    def generate_study_plan(self, request: StudyPlanRequest) -> dict:
        allowed_anchor_ids = list(request.approved_source_ids)
        schema = compact_study_plan_schema(request)
        # Keep the authoring prompt compact even when a PDF has many pages. The
        # full candidate set stays server-side for validation; the model receives
        # locator-rich candidates rather than an unbounded document dump.
        compact_spans = [
            {
                "sourceId": span.get("sourceId"),
                "sourceKind": span.get("sourceKind"),
                "candidateId": span.get("candidateId"),
                "text": str(span.get("text") or "")[:500],
                "page": span.get("page"),
                "locator": span.get("locator"),
            }
            for span in request.source_spans
            if isinstance(span, dict) and span.get("candidateId")
        ]
        source_context = json.dumps(compact_spans[:40], ensure_ascii=False)[:20000]
        instruction = (
            f"Build a complete first learning module for subject '{request.subject_title or request.subject_id}'. "
            f"Chapter selection: {request.chapter_selection}. Source pack IDs: {request.source_ids}. "
            f"Only these source anchor IDs may be used: {allowed_anchor_ids}. "
            "Return one topic scene per numbered section or subsection found in the source, preserving ascending source order. If the source has sections such as 1.1, 1.2, and 1.3, return those as separate topics and begin each title with the exact section label. Do not merge 1.1, 1.2, and 1.3 into one broad concept and do not invent extra topics. "
            "Do not make the scenes generic lesson headings: each topic must teach and test one concrete idea from its own section. "
            "Every topic scene must have exactly four stages in this order: definition, mcq, one application stage whose kind is formula, diagram, or numerical, and teach_back. "
            "The definition stage explains the topic and uses responseType none. The mcq stage must test a specific idea from that section, use exactly 3 or 4 plausible text options, use responseType single_choice, and include distractors based on realistic misconceptions rather than vague or trivially wrong choices. Never include answer keys or isCorrect fields. "
            "The application stage must ask the learner to write a formula, solve a numerical problem, or upload/draw a block diagram; use responseType long_text for formula/numerical and file for diagram. "
            "The teach_back stage asks the learner to explain the idea in their own words with responseType long_text. "
            "Each topic must also include a substantial explanation, 3-6 keyPoints, a workedExample when the source supports one, 2-4 commonMistakes, and 4-6 whiteboard actions. "
            "Whiteboard actions must build the idea step by step: identify terms, show the mechanism or derivation, connect the representation, apply it, and call out a likely mistake. "
            "Use a model-authored config visual when the source supports a figure, block diagram, graph, process, or relationship; use points for graphs or nodes/edges for diagrams, never external image URLs. "
            "Keep all explanations and prompts concrete, source-grounded, and free of repeated individual characters or words. Never include isCorrect, answer keys, or correctness flags in learner-facing options. "
            "Each topic needs one approved source anchor and a null top-level checkpoint because stages contain the assessments. "
            "Use type topic for every scene and keep all stage/source IDs server-owned. "
            f"Past-question source IDs: {request.past_question_source_ids or []}. If past-question sources are present, return up to six concise patterns in pastQuestionAnalysis and make application stages reflect those patterns; otherwise return an empty list. "
            f"Source candidates (candidate text is not automatically approved evidence): {source_context}"
        )
        raw_result = self._chat_json(instruction, "study_manifest_v3", schema)
        # A truncated structured response can be syntactically repairable while
        # still losing the top-level manifest. Give the model one focused retry
        # before entering per-scene repair; never let a malformed object become a
        # server exception or an empty learner module.
        if not isinstance(raw_result, dict) or not isinstance(raw_result.get("scenes"), list):
            raw_result = self._chat_json(
                instruction + " Return the complete top-level object with studyPlanId, sourceIds, chapterSelection, sourcePackVersion, recordVersion, outline, and scenes. Do not return a single scene or a partial object.",
                "study_manifest_v3_retry",
                schema,
            )
        if not isinstance(raw_result, dict) or not isinstance(raw_result.get("scenes"), list):
            raise ProviderOutputError("Fireworks returned an incomplete study manifest")
        result = normalize_live_study_plan(raw_result, request)
        result.setdefault("scenes", [])
        missing = missing_required_scene_types(result)
        if missing and any(scene.get("stages") for scene in result.get("scenes", []) if isinstance(scene, dict)):
            # Qwen can satisfy the top-level manifest schema while dropping one
            # or more stages from a topic. Repair those small omissions with
            # stage-only requests instead of discarding an otherwise usable
            # module.
            if "formula_or_diagram_or_numerical" in missing:
                application_schema = assessment_stage_schema(allowed_anchor_ids, max_prompt_length=520)
                application_schema["properties"]["kind"] = {
                    "type": "string",
                    "enum": ["formula", "diagram", "numerical"],
                }
                application_kinds = {"formula", "diagram", "numerical"}
                for scene in result.get("scenes", []):
                    if not isinstance(scene, dict):
                        continue
                    stages = [stage for stage in scene.get("stages", []) if isinstance(stage, dict)]
                    if any(stage.get("kind") in application_kinds for stage in stages):
                        continue
                    repair_instruction = (
                        f"Return exactly one practical application assessment stage for the topic '{scene.get('title')}'. "
                        "The kind MUST be exactly one of formula, numerical, or diagram. "
                        "Choose formula when the learner should write or apply an equation, numerical when they should solve a short calculation, "
                        "and diagram when they should submit a block diagram. Use responseType long_text for formula or numerical and file for diagram. "
                        "The prompt must test application of this topic, not ask the learner to repeat its definition. "
                        f"Use only approved source anchor IDs {allowed_anchor_ids}. "
                        f"Source candidates: {source_context[:12000]}"
                    )
                    for repair_attempt in range(2):
                        repaired_stage = self._chat_json(
                            repair_instruction + (" Return a single plain stage object with prompt, responseType, and sourceAnchorIds." if repair_attempt else ""),
                            f"study_application_stage_v{repair_attempt + 1}",
                            application_schema,
                        )
                        if not isinstance(repaired_stage, dict):
                            continue
                        raw_kind = repaired_stage.get("kind") or repaired_stage.get("stageKind") or repaired_stage.get("type")
                        raw_prompt = repaired_stage.get("prompt") or repaired_stage.get("stem") or repaired_stage.get("question")
                        candidate_kind = str(raw_kind or "formula")
                        if candidate_kind not in application_kinds:
                            candidate_kind = "diagram" if str(repaired_stage.get("responseType") or "").lower() == "file" else "formula"
                        if not str(raw_prompt or "").strip():
                            continue
                        repaired_stage["kind"] = candidate_kind
                        repaired_stage["prompt"] = str(raw_prompt).strip()
                        repaired_stage["responseType"] = "file" if candidate_kind == "diagram" else "long_text"
                        repaired_stage["options"] = None
                        repaired_stage["stageId"] = f"{scene.get('sceneId', 'topic')}-application"
                        repaired_stage["title"] = str(repaired_stage.get("title") or "Apply the idea").strip()
                        repaired_stage["sourceAnchorIds"] = list(
                            repaired_stage.get("sourceAnchorIds")
                            or repaired_stage.get("sourceAnchors")
                            or scene.get("sourceAnchorIds")
                            or allowed_anchor_ids[:1]
                        )[:3]
                        stages.append(repaired_stage)
                        scene["stages"] = stages
                        break
                result = normalize_live_study_plan(result, request)
                missing = missing_required_scene_types(result)
            stage_repairs = {
                "definition": {
                    "responseType": "none",
                    "instruction": "Explain the topic clearly in learner-friendly language and identify the central idea.",
                },
                "mcq": {
                    "responseType": "single_choice",
                    "instruction": "Write one source-grounded multiple-choice question with exactly 3 or 4 plausible text options. Do not include option IDs, isCorrect, answer keys, or correctness flags.",
                },
                "teach_back": {
                    "responseType": "long_text",
                    "instruction": "Ask the learner to explain the topic in their own words and connect it to the source-grounded idea.",
                },
            }
            for missing_kind, repair_spec in stage_repairs.items():
                if missing_kind not in missing:
                    continue
                stage_schema = assessment_stage_schema(allowed_anchor_ids, max_prompt_length=520)
                stage_schema["properties"]["kind"] = {"type": "string", "enum": [missing_kind]}
                stage_schema["properties"]["responseType"] = {"type": "string", "enum": [repair_spec["responseType"]]}
                if missing_kind == "mcq":
                    stage_schema["properties"]["options"]["minItems"] = 3
                    stage_schema["properties"]["options"]["maxItems"] = 4
                else:
                    stage_schema["properties"]["options"] = {"type": ["array", "null"], "maxItems": 0, "items": {"type": "string"}}
                for scene in result.get("scenes", []):
                    if not isinstance(scene, dict):
                        continue
                    stages = [stage for stage in scene.get("stages", []) if isinstance(stage, dict)]
                    if any(stage.get("kind") == missing_kind for stage in stages):
                        continue
                    repair_instruction = (
                        f"Return exactly one {missing_kind} assessment stage for the topic '{scene.get('title')}'. "
                        f"{repair_spec['instruction']} "
                        f"Use responseType {repair_spec['responseType']} and only approved source anchor IDs {allowed_anchor_ids}. "
                        f"Source candidates: {source_context[:12000]}"
                    )
                    repair_attempts = 2
                    for repair_attempt in range(repair_attempts):
                        retry_note = (
                            " The previous response was not usable. Return a normal learner-facing MCQ with a prompt and 3 or 4 plain-text options; never return option objects, option IDs, isCorrect, or an answer key."
                            if repair_attempt
                            else ""
                        )
                        repaired_stage = self._chat_json(
                            repair_instruction + retry_note,
                            f"study_{missing_kind}_stage_v{repair_attempt + 1}",
                            stage_schema,
                        )
                        if not isinstance(repaired_stage, dict):
                            continue
                        options = normalize_answer_options(repaired_stage.get("options") or repaired_stage.get("choices"))
                        raw_prompt = repaired_stage.get("prompt") or repaired_stage.get("stem") or repaired_stage.get("question")
                        if missing_kind == "mcq":
                            # Qwen sometimes returns option records even when
                            # the schema asks for strings, and may omit the
                            # structural enum fields. The option text is still
                            # usable, so normalize it and repair only metadata
                            # that is owned by the server/assessment ladder.
                            if not str(raw_prompt or "").strip() or not options or len(options) < 3:
                                continue
                            repaired_stage["kind"] = "mcq"
                            repaired_stage["responseType"] = "single_choice"
                        elif not str(raw_prompt or "").strip():
                            continue
                        else:
                            repaired_stage["kind"] = missing_kind
                            repaired_stage["responseType"] = repair_spec["responseType"]
                        repaired_stage["prompt"] = str(raw_prompt).strip()
                        repaired_stage["options"] = options
                        repaired_stage["stageId"] = f"{scene.get('sceneId', 'topic')}-{missing_kind}"
                        if not str(repaired_stage.get("title") or "").strip():
                            repaired_stage["title"] = f"{scene.get('title') or 'Topic'} assessment"
                        if not isinstance(repaired_stage.get("sourceAnchorIds"), list) or not repaired_stage.get("sourceAnchorIds"):
                            scene_anchors = scene.get("sourceAnchorIds") if isinstance(scene.get("sourceAnchorIds"), list) else []
                            repaired_stage["sourceAnchorIds"] = list(repaired_stage.get("sourceAnchors") or scene_anchors[:3] or allowed_anchor_ids[:1])
                        stages.append(repaired_stage)
                        scene["stages"] = stages
                        break
            if stage_repairs and any(item in missing for item in stage_repairs):
                result = normalize_live_study_plan(result, request)
                missing = missing_required_scene_types(result)
            if missing:
                raise ProviderOutputError(f"live study module is missing assessment stages: {', '.join(missing)}")
        if missing:
            # Repair fragments use the rich scene contract rather than the
            # intentionally shallow top-level Qwen schema. This keeps a
            # missing visualization from being silently returned as a title
            # with no renderable model-authored configuration.
            scene_schema = study_plan_schema(request)["properties"]["scenes"]["items"]
            for missing_type in missing:
                target_type = "two_d" if missing_type == "two_d_or_three_d" else missing_type
                repair_attempts = 1
                for repair_attempt in range(repair_attempts):
                    visual_requirements = ""
                    if target_type in {"two_d", "three_d"}:
                        visual_requirements = (
                            f" This is a real {target_type} visualization, not a prose card. Its config MUST contain model-authored render data: "
                            "a dimension/title plus either at least two numeric points, or nodes/edges, or another concrete chart/diagram payload. "
                            "Do not leave config empty."
                        )
                    retry_note = " The previous visual repair lacked renderable config; make the visualization payload explicit." if repair_attempt else ""
                    repair_instruction = (
                        f"Return exactly one learner-ready scene object for subject '{request.subject_title or request.subject_id}'. "
                        f"Its type field MUST be exactly '{target_type}'. Do not use exam_bridge as a substitute. "
                        "Include a clear explanation, 3 key points, a worked example or null, 2 common mistakes, at least one action with a payload, and a checkpoint when the scene type is interactive. "
                        f"Use only approved anchor IDs {allowed_anchor_ids}.{visual_requirements}{retry_note} "
                        f"Source candidates: {source_context[:50000]}"
                    )
                    fragment = self._chat_json(repair_instruction, f"study_scene_{target_type}_v{repair_attempt + 1}", scene_schema)
                    fragment_plan = normalize_live_study_plan({"scenes": [fragment]}, request)
                    if not fragment_plan["scenes"]:
                        continue
                    fragment_scene = fragment_plan["scenes"][0]
                    # A model may put chart/diagram data on an action payload
                    # while returning a presentation type. Reuse that
                    # model-authored payload; never invent coordinates or facts.
                    if target_type in {"two_d", "three_d"} and not fragment_scene.get("config"):
                        for action in fragment_scene.get("actions", []):
                            payload = action.get("payload") if isinstance(action, dict) else None
                            if isinstance(payload, dict) and any(key in payload for key in ("points", "nodes", "edges", "chartType", "dimension")):
                                fragment_scene["config"] = payload
                                break
                    if fragment_scene.get("type") != target_type:
                        if target_type in {"two_d", "three_d"} and fragment_scene.get("config"):
                            fragment_scene["type"] = target_type
                        elif target_type == "whiteboard" and fragment_scene.get("actions"):
                            fragment_scene["type"] = target_type
                        elif target_type in {"predict_checkpoint", "retrieval", "teach_back", "exam_bridge"} and (
                            fragment_scene.get("actions") or fragment_scene.get("explanation") or fragment_scene.get("checkpoint")
                        ):
                            # Qwen can occasionally ignore the enum in a repair
                            # fragment even though it returned all of the fields
                            # needed for an interactive scene. The requested type
                            # is structural metadata; coercing it here lets the
                            # normalizer create the checkpoint from the model's
                            # own prompt rather than inventing lesson content.
                            fragment_scene["type"] = target_type
                            fragment_scene = normalize_live_study_plan({"scenes": [fragment_scene]}, request)["scenes"][0]
                    if fragment_scene.get("type") == target_type and (
                        target_type not in {"two_d", "three_d"} or fragment_scene.get("config")
                    ):
                        result["scenes"].append(fragment_scene)
                        break
        returned_ids = set(result.get("sourceIds", []))
        returned_anchors = {
            anchor
            for item in (result.get("outline", []) + result.get("scenes", []))
            for anchor in item.get("sourceAnchorIds", [])
        }
        if not returned_ids.issubset(set(request.source_ids)):
            raise ProviderOutputError("Fireworks returned an unrequested source ID")
        if not returned_anchors.issubset(set(allowed_anchor_ids)):
            raise ProviderOutputError("Fireworks returned an unapproved source anchor")
        result["providerMode"] = self.mode
        return result


    def generate_remediation_slides(self, request: dict) -> dict:
        """Create a source-grounded slide storyboard with the Qwen Fireworks key."""
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "slides"],
            "properties": {
                "title": {"type": "string", "minLength": 8, "maxLength": 240},
                "slides": {
                    "type": "array", "minItems": 4, "maxItems": 8,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["slideId", "title", "body", "bullets", "narration", "sourceAnchorIds", "diagram"],
                        "properties": {
                            "slideId": {"type": "string", "maxLength": 80},
                            "title": {"type": "string", "minLength": 3, "maxLength": 160},
                            "body": {"type": "string", "minLength": 20, "maxLength": 900},
                            "bullets": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string", "maxLength": 220}},
                            "narration": {"type": "string", "minLength": 40, "maxLength": 1400},
                            "sourceAnchorIds": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                            "diagram": {
                                "type": "object", "additionalProperties": False, "required": ["nodes", "edges"],
                                "properties": {
                                    "nodes": {"type": "array", "maxItems": 8, "items": {"type": "object", "additionalProperties": False, "required": ["id", "label"], "properties": {"id": {"type": "string", "maxLength": 40}, "label": {"type": "string", "maxLength": 100}}}},
                                    "edges": {"type": "array", "maxItems": 12, "items": {"type": "object", "additionalProperties": False, "required": ["from", "to"], "properties": {"from": {"type": "string", "maxLength": 40}, "to": {"type": "string", "maxLength": 40}}}},
                                },
                            },
                        },
                    },
                },
            },
        }
        instruction = (
            "Create a complete source-grounded remediation slide lesson. This is not an MP4 request: "
            "make 4 to 8 readable teaching slides that can be shown one at a time with narration. "
            "Repair the learner's exact mistake, then teach the definition, visual model, worked application, correction, and transfer check. "
            "Use only the approved source context and anchor IDs. Do not invent facts, values, citations, or answer keys. "
            f"Topic: {request.get('topicTitle')}; stage: {request.get('stageKind')}; "
            f"Learner mistake: {request.get('mistake')}; correct answer: {request.get('correctAnswer')}; "
            f"Correction: {request.get('correction')}; review focus: {request.get('remediation')}; "
            f"Approved anchor IDs (use these only if you include sourceAnchorIds): {request.get('approvedAnchorIds')}; "
            f"Approved source context: {request.get('sourceContext')}"
        )
        result = self._chat_json(instruction, "remediation_slides_v1", schema)
        result["providerMode"] = self.mode
        return result


def provider_for(mode: str | None = None) -> LLMProvider:
    configured = (mode or settings.LLM_PROVIDER or "fixture").lower()
    if configured in {"fireworks", "live_fireworks", "qwen"}:
        return FireworksProvider()
    if configured in {"openai", "live_openai"}:
        return OpenAIProvider()
    return FixtureProvider()
