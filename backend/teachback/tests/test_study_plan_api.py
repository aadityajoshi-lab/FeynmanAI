import json

import pytest
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_provider_status_does_not_expose_keys(client):
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["providers"]} == {"mistral", "fireworks", "openai", "fixture"}
    fireworks = next(item for item in body["providers"] if item["id"] == "fireworks")
    assert {"id", "label", "available", "model", "configured", "reachable", "status", "lastErrorCategory", "lastSuccessAt"}.issubset(fireworks)
    assert {"ready", "extracting", "failed", "localFallbackActive"}.issubset(body["sourceStatus"])
    assert all("key" not in json.dumps(item).lower() for item in body["providers"])


def test_rich_scene_schema_is_available_for_provider_repairs():
    from teachback.providers import StudyPlanRequest, study_plan_schema

    schema = study_plan_schema(StudyPlanRequest("demo", "module", ["source-1"], "chapter_1", ["anchor-1"]))
    scene = schema["properties"]["scenes"]["items"]
    assert "config" in scene["required"]
    assert "checkpoint" in scene["required"]


def test_compact_live_manifest_schema_is_bounded_to_the_first_learning_loop():
    from teachback.providers import StudyPlanRequest, compact_study_plan_schema

    schema = compact_study_plan_schema(StudyPlanRequest("demo", "module", ["source-1"], "chapter_1", ["anchor-1"]))
    scenes = schema["properties"]["scenes"]
    scene = scenes["items"]

    assert scenes["minItems"] == 1
    assert scenes["maxItems"] == 12
    assert scene["properties"]["actions"]["maxItems"] == 6
    assert scene["properties"]["config"]["maxProperties"] == 12
    assert scene["properties"]["explanation"]["maxLength"] == 2400
    assert scene["properties"]["stages"]["minItems"] == 4
    assert scene["properties"]["stages"]["maxItems"] == 4


def test_mcq_options_strip_answer_keys_before_they_reach_the_learner():
    from teachback.providers import normalize_answer_options

    options = normalize_answer_options([
        {"optionId": "opt_1_a", "text": "Wrong answer", "isCorrect": False},
        {"optionId": "opt_1_b", "text": "Correct answer", "isCorrect": True},
    ])

    assert options == ["Wrong answer", "Correct answer"]
    assert all("isCorrect" not in option for option in options or [])


def test_schema_field_names_are_not_treated_as_mcq_options():
    from teachback.providers import normalize_answer_options

    assert normalize_answer_options(["id", "stem", "responseType", "options", "sourceAnchors"]) is None


def test_incorrect_checkpoint_can_return_a_safe_similar_mcq():
    from teachback.providers import normalize_retry_result

    result = normalize_retry_result(
        {
            "correct": False,
            "retryPrompt": "Which statement best applies this idea?",
            "retryOptions": [
                {"text": "A plausible distractor", "isCorrect": False},
                {"text": "The source-grounded application", "isCorrect": True},
                {"text": "Another misconception", "isCorrect": False},
            ],
            "retryResponseType": "single_choice",
            "retrySourceAnchorIds": ["candidate_1", "not-approved"],
        },
        {"stageKind": "mcq", "sourceAnchorIds": ["candidate_1"], "stage": {"kind": "mcq"}},
    )

    assert result["retryOptions"] == ["A plausible distractor", "The source-grounded application", "Another misconception"]
    assert result["retrySourceAnchorIds"] == ["candidate_1"]
    assert all("isCorrect" not in option for option in result["retryOptions"])


def test_degraded_checkpoint_feedback_is_repaired_for_the_learner():
    from teachback.providers import normalize_checkpoint_feedback

    result = normalize_checkpoint_feedback(
        {"correct": False, "feedback": "T", "mistake": "T", "correctAnswer": "T", "correction": "T", "remediation": "R"},
        {
            "stageKind": "mcq",
            "prompt": "What is the purpose of the secondary element?",
            "stage": {
                "kind": "mcq",
                "prompt": "What is the purpose of the secondary element?",
                "options": [
                    "To display the final readable result.",
                    "To amplify or filter a weak electrical signal.",
                    "To compare the unknown quantity with a standard.",
                ],
            },
            "sourceSpans": [{"text": "The secondary element amplifies or filters the weak signal from the primary element."}],
        },
        "To display the final readable result.",
    )

    assert len(result["mistake"]) > 18
    assert result["correctAnswer"] == "To amplify or filter a weak electrical signal."
    assert len(result["correction"]) > 18
    assert len(result["remediation"]) > 18


def test_provider_json_preserves_absurd_integer_tokens_as_text():
    from teachback.providers import load_provider_json

    parsed = load_provider_json('{"value": ' + ("9" * 5000) + "}")

    assert isinstance(parsed["value"], str)
    assert len(parsed["value"]) == 5000


def test_numbered_source_sections_are_kept_in_learning_order():
    from teachback.providers import StudyPlanRequest, normalize_live_study_plan

    result = normalize_live_study_plan(
        {
            "recordVersion": 1,
            "scenes": [
                {"sceneId": "s13", "title": "1.3 Digital instrumentation", "explanation": "Digital section explanation."},
                {"sceneId": "s11", "title": "1.1 Introduction", "explanation": "Introduction section explanation."},
                {"sceneId": "s12", "title": "1.2 Analog instrumentation", "explanation": "Analog section explanation."},
            ],
        },
        StudyPlanRequest("instrumentation", "chapter-1", ["source"], "chapter_1", ["anchor"]),
    )

    assert [scene["title"] for scene in result["scenes"]] == ["1.1 Introduction", "1.2 Analog instrumentation", "1.3 Digital instrumentation"]


def test_normalizer_keeps_one_canonical_four_stage_ladder():
    from teachback.providers import StudyPlanRequest, normalize_live_study_plan

    result = normalize_live_study_plan(
        {
            "recordVersion": 1,
            "scenes": [{
                "sceneId": "topic-1",
                "title": "1.1 Introduction",
                "explanation": "A source-grounded introduction to the topic.",
                "stages": [
                    {"kind": "definition", "prompt": "Read the definition."},
                    {"kind": "mcq", "prompt": "Choose the correct statement.", "options": ["A", "B", "C"]},
                    {"kind": "formula", "prompt": "Write the formula."},
                    {"kind": "numerical", "prompt": "Solve the numerical example."},
                    {"kind": "teach_back", "prompt": "Explain the idea in your own words."},
                ],
            }],
        },
        StudyPlanRequest("instrumentation", "chapter-1", ["source"], "chapter_1", ["anchor"]),
    )

    assert [stage["kind"] for stage in result["scenes"][0]["stages"]] == ["definition", "mcq", "formula", "teach_back"]


def test_normalizer_repairs_short_placeholder_stage_prompts():
    from teachback.providers import StudyPlanRequest, normalize_live_study_plan

    result = normalize_live_study_plan(
        {
            "recordVersion": 1,
            "scenes": [{
                "sceneId": "topic-1",
                "title": "1.1 Introduction to instrumentation",
                "explanation": "An instrumentation system measures a physical quantity and produces a usable signal.",
                "stages": [
                    {"kind": "definition", "prompt": "T"},
                    {"kind": "mcq", "prompt": "", "options": ["A", "B", "C"]},
                    {"kind": "formula", "prompt": "Apply"},
                    {"kind": "teach_back", "prompt": None},
                ],
            }],
        },
        StudyPlanRequest("instrumentation", "chapter-1", ["source"], "chapter_1", ["anchor"]),
    )

    prompts = [stage["prompt"] for stage in result["scenes"][0]["stages"]]
    assert all(len(prompt.strip()) >= 5 for prompt in prompts)
    assert "define" in prompts[0].lower()
    assert "best explains" in prompts[1].lower()
    assert "teach" in prompts[3].lower()


def test_staged_manifest_marks_unstaged_topics_for_repair():
    from teachback.providers import missing_required_scene_types

    plan = {
        "scenes": [
            {"stages": [{"kind": "definition"}, {"kind": "mcq", "responseType": "single_choice", "options": ["A", "B", "C"]}, {"kind": "formula"}, {"kind": "teach_back"}]},
            {"title": "1.2 Analog instrumentation"},
        ]
    }

    assert missing_required_scene_types(plan) == ["definition", "mcq", "teach_back", "formula_or_diagram_or_numerical"]


@pytest.mark.django_db
def test_fixture_study_plan_is_source_bounded(client):
    response = client.post(
        "/api/v1/study-plans",
        {"subjectId": "dsap", "moduleId": "sampling-aliasing", "chapterSelection": "chapter_1", "sourceIds": ["dsap-sampling-v1"]},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["providerMode"] == "codex_fixture"
    assert body["chapterSelection"] == "chapter_1"
    assert body["scenes"]
    allowed = {f"dsap-sampling-v1-span-{index:02d}" for index in range(1, 7)}
    assert all(anchor in allowed for scene in body["scenes"] for anchor in scene["sourceAnchorIds"])


@pytest.mark.django_db
def test_unknown_source_cannot_become_runtime_evidence(client):
    response = client.post(
        "/api/v1/study-plans",
        {"subjectId": "dsap", "sourceIds": ["upload_unapproved"], "chapterSelection": "all"},
        format="json",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "needs_human_review"


@pytest.mark.django_db
def test_plan_rejects_browser_supplied_source_text(client):
    response = client.post(
        "/api/v1/study-plans",
        {"subjectId": "dsap", "sourceText": "pretend evidence"},
        format="json",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "source_boundary_violation"


def test_live_fireworks_mode_is_accepted_by_manifest_validator():
    from teachback.study_plan_views import _validate_manifest

    _validate_manifest(
        {
            "studyPlanId": "plan_qwen3p7",
            "sourceIds": ["upload_source"],
            "chapterSelection": "chapter_1",
            "providerMode": "live_fireworks",
            "sourcePackVersion": "uploaded-draft-test",
            "recordVersion": 1,
            "outline": [{"sourceAnchorIds": ["candidate_1"]}],
            "scenes": [{"type": scene_type, "explanation": "A complete generated explanation for this concept.", "sourceAnchorIds": ["candidate_1"], "actions": [{"kind": "write"}], "checkpoint": {"kind": "teach_back", "prompt": "Explain it.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]}} for scene_type in ["whiteboard", "two_d", "predict_checkpoint", "retrieval", "teach_back", "exam_bridge"]],
        },
        {"candidate_1"},
    )


def test_live_manifest_allows_optional_visualization_and_exam_bridge():
    from teachback.study_plan_views import _validate_manifest

    _validate_manifest(
        {
            "studyPlanId": "plan_without_visual",
            "sourceIds": ["upload_source"],
            "chapterSelection": "chapter_1",
            "providerMode": "live_fireworks",
            "sourcePackVersion": "uploaded-draft-test",
            "recordVersion": 1,
            "outline": [{"sourceAnchorIds": ["candidate_1"]}],
            "scenes": [{"type": scene_type, "explanation": "A complete generated explanation for this concept.", "sourceAnchorIds": ["candidate_1"], "actions": [{"kind": "write"}], "checkpoint": {"kind": "teach_back", "prompt": "Explain it.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]}} for scene_type in ["whiteboard", "predict_checkpoint", "retrieval", "teach_back"]],
        },
        {"candidate_1"},
    )


def test_live_manifest_requires_a_topic_assessment_ladder():
    from teachback.study_plan_views import _validate_manifest

    stages = [
        {"kind": "definition", "prompt": "Read the definition.", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "mcq", "prompt": "Which statement is correct?", "responseType": "single_choice", "options": ["A", "B", "C"], "sourceAnchorIds": ["candidate_1"]},
        {"kind": "numerical", "prompt": "Solve the numerical example.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "teach_back", "prompt": "Explain the idea in your own words.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
    ]
    _validate_manifest(
        {
            "studyPlanId": "plan_topic_ladder",
            "sourceIds": ["upload_source"],
            "chapterSelection": "chapter_1",
            "providerMode": "live_fireworks",
            "sourcePackVersion": "uploaded-draft-test",
            "recordVersion": 1,
            "outline": [{"sourceAnchorIds": ["candidate_1"]}],
            "scenes": [{"type": "topic", "explanation": "A complete generated explanation for this topic.", "sourceAnchorIds": ["candidate_1"], "actions": [{"kind": "write"}], "stages": stages}],
        },
        {"candidate_1"},
    )


def test_live_manifest_requires_the_ladder_on_every_topic():
    from teachback.providers import ProviderOutputError
    from teachback.study_plan_views import _validate_manifest

    complete_stages = [
        {"kind": "definition", "prompt": "Read the definition.", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "mcq", "prompt": "Which statement is correct?", "responseType": "single_choice", "options": ["A", "B", "C"], "sourceAnchorIds": ["candidate_1"]},
        {"kind": "formula", "prompt": "Write the formula.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "teach_back", "prompt": "Explain the idea in your own words.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
    ]
    incomplete_stages = [stage for stage in complete_stages if stage["kind"] != "formula"]

    with pytest.raises(ProviderOutputError, match="each topic must progress"):
        _validate_manifest(
            {
                "studyPlanId": "plan_two_topics",
                "sourceIds": ["upload_source"],
                "chapterSelection": "chapter_1",
                "providerMode": "live_fireworks",
                "sourcePackVersion": "uploaded-draft-test",
                "recordVersion": 1,
                "outline": [{"sourceAnchorIds": ["candidate_1"]}],
                "scenes": [
                    {"type": "topic", "explanation": "A complete generated explanation for this topic.", "sourceAnchorIds": ["candidate_1"], "actions": [{"kind": "write"}], "stages": complete_stages},
                    {"type": "topic", "explanation": "Another complete generated explanation for this topic.", "sourceAnchorIds": ["candidate_1"], "actions": [{"kind": "write"}], "stages": incomplete_stages},
                ],
            },
            {"candidate_1"},
        )


def test_live_manifest_requires_exactly_one_application_stage_in_the_ladder():
    from teachback.providers import ProviderOutputError
    from teachback.study_plan_views import _validate_manifest

    stages = [
        {"kind": "definition", "prompt": "Read the definition.", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "mcq", "prompt": "Which statement is correct?", "responseType": "single_choice", "options": ["A", "B", "C"], "sourceAnchorIds": ["candidate_1"]},
        {"kind": "formula", "prompt": "Write the formula.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "numerical", "prompt": "Solve the numerical example.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
        {"kind": "teach_back", "prompt": "Explain the idea in your own words.", "responseType": "long_text", "sourceAnchorIds": ["candidate_1"]},
    ]

    with pytest.raises(ProviderOutputError, match="each topic must progress"):
        _validate_manifest(
            {
                "studyPlanId": "plan_extra_application",
                "sourceIds": ["upload_source"],
                "chapterSelection": "chapter_1",
                "providerMode": "live_fireworks",
                "sourcePackVersion": "uploaded-draft-test",
                "recordVersion": 1,
                "outline": [{"sourceAnchorIds": ["candidate_1"]}],
                "scenes": [{"type": "topic", "explanation": "A complete generated explanation for this topic.", "sourceAnchorIds": ["candidate_1"], "actions": [{"kind": "write"}], "stages": stages}],
            },
            {"candidate_1"},
        )


@pytest.mark.django_db
def test_generated_scene_interaction_is_source_bounded(client):
    response = client.post(
        "/api/v1/study-plans/interactions",
        {
            "sourceIds": ["dsap-sampling-v1"],
            "kind": "predict",
            "response": "The sample rate is high enough for this signal.",
            "provider": "fixture",
            "scene": {"sceneId": "generated-predict", "prompt": "Predict what changes.", "responseType": "long_text", "sourceAnchorIds": ["dsap-sampling-v1-span-01"]},
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["providerMode"] == "codex_fixture"
    assert "understandingScore" in response.json()
    assert "overconfidence" in response.json()


@pytest.mark.django_db
def test_generated_scene_rejects_unapproved_anchor(client):
    response = client.post(
        "/api/v1/study-plans/interactions",
        {
            "sourceIds": ["dsap-sampling-v1"],
            "kind": "teach_back",
            "response": "An explanation.",
            "scene": {"sceneId": "generated-teach", "sourceAnchorIds": ["not-approved"]},
        },
        format="json",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "source_boundary_violation"


def test_remediation_slides_rebind_model_anchors_to_topic_anchors():
    from teachback.remediation_video_views import _complete_slide_lesson, _validate_slide_manifest

    slides = _validate_slide_manifest(
        {
            "slides": [
                {
                    "title": "Definition",
                    "body": "A source-grounded explanation.",
                    "narration": "Read the definition before applying the idea.",
                    "bullets": ["Use the approved topic evidence."],
                    "sourceAnchorIds": ["model-invented-anchor"],
                    "diagram": {"nodes": [], "edges": []},
                }
            ] * 4,
        },
        {"topic-anchor", "other-approved-anchor"},
        ["topic-anchor"],
    )

    assert all(slide["sourceAnchorIds"] == ["topic-anchor"] for slide in slides)
    completed = _complete_slide_lesson(
        slides,
        topic_title="Digital instrumentation",
        correct_answer="The ADC comes before the display.",
        correction="Follow the signal path.",
        remediation="Review the block order.",
        scene_anchors=["topic-anchor"],
    )
    assert len(completed) == 4
    assert all(slide["sourceAnchorIds"] == ["topic-anchor"] for slide in completed)


@pytest.mark.django_db
@override_settings(VIDEO_SERVICE_KEY="", REMEDIATION_VIDEO_PROVIDER="seedance")
def test_remediation_video_stays_optional_when_video_service_is_not_configured(client):
    response = client.post(
        "/api/v1/study-plans/remediation-video",
        {"sourceIds": ["dsap-sampling-v1"], "scene": {"sourceAnchorIds": ["dsap-sampling-v1-span-01"]}},
        format="json",
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "video_provider_unavailable"


@pytest.mark.django_db
def test_module_chat_returns_a_typed_navigation_action(client):
    response = client.post(
        "/api/v1/study-plans/chat",
        {
            "subjectId": "dsap",
            "moduleId": "sampling-aliasing",
            "sourceIds": ["dsap-sampling-v1"],
            "provider": "fixture",
            "message": "Take me to the next scene",
            "history": [],
            "activeSceneId": "scene-1",
            "activeSceneIndex": 0,
            "learningMode": "predict_reveal",
            "scenes": [
                {"sceneId": "scene-1", "title": "First", "type": "whiteboard", "hasVisualization": False, "hasCheckpoint": False},
                {"sceneId": "scene-2", "title": "Second", "type": "teach_back", "hasVisualization": False, "hasCheckpoint": True},
            ],
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "action_only"
    assert body["action"] == {"kind": "next_scene", "sceneId": "scene-2", "modeId": None, "reason": "learner_requested_next_scene"}
    assert body["providerMode"] == "codex_fixture"
    assert body["sourceAnchorIds"]


@pytest.mark.django_db
def test_module_chat_rejects_browser_source_text(client):
    response = client.post(
        "/api/v1/study-plans/chat",
        {"sourceIds": ["dsap-sampling-v1"], "message": "Explain", "sourceText": "not allowed"},
        format="json",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "source_boundary_violation"


@pytest.mark.django_db
def test_module_chat_does_not_open_unavailable_visualization(client):
    response = client.post(
        "/api/v1/study-plans/chat",
        {
            "subjectId": "dsap",
            "sourceIds": ["dsap-sampling-v1"],
            "provider": "fixture",
            "message": "Show the visualization",
            "history": [],
            "activeSceneId": "scene-1",
            "activeSceneIndex": 0,
            "learningMode": "predict_reveal",
            "scenes": [{"sceneId": "scene-1", "title": "First", "type": "whiteboard", "hasVisualization": False, "hasCheckpoint": False}],
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["action"]["kind"] == "none"
