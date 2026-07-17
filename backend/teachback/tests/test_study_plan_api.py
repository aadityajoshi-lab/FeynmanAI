import json

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


def test_provider_status_does_not_expose_keys(client):
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["providers"]} == {"fireworks", "openai", "fixture"}
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

    assert scenes["minItems"] == 4
    assert scenes["maxItems"] == 4
    assert scene["properties"]["actions"]["maxItems"] == 2
    assert scene["properties"]["config"]["additionalProperties"] is False
    assert scene["properties"]["explanation"]["maxLength"] == 1200


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
