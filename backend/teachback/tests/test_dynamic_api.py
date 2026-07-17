"""HTTP acceptance tests for the dynamic subject/learner API (v2 surface)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient


V2_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "v2" / "evaluation-cases.json").read_text(encoding="utf-8")
)["cases"]
V2_SOURCE = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "v2" / "source-pack.json").read_text(encoding="utf-8")
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _new_learner(client: APIClient, key: str) -> str:
    response = client.post("/api/v1/learners/anonymous", {"learnerId": key}, format="json")
    assert response.status_code == 201
    return response.json()["learnerId"]


@pytest.mark.django_db
def test_dynamic_catalog_and_manifest_are_versioned(client: APIClient) -> None:
    subjects = client.get("/api/v1/subjects")
    assert subjects.status_code == 200
    assert {item["subjectId"] for item in subjects.json()["subjects"]} >= {"dsap", "photosynthesis", "ai-literacy"}

    detail = client.get("/api/v1/subjects/dsap")
    assert detail.status_code == 200
    assert detail.json()["version"] == "dsap-v1"
    modules = client.get("/api/v1/subjects/dsap/modules")
    assert modules.status_code == 200
    assert any(item["moduleId"] == "sampling-aliasing" for item in modules.json()["modules"])

    module = client.get("/api/v1/subjects/dsap/modules/sampling-aliasing")
    assert module.status_code == 200
    assert {concept["conceptId"] for concept in module.json()["concepts"]} >= {"sampling-frequency", "nyquist-condition", "alias-frequency"}
    manifest = client.get("/api/v1/modules/sampling-aliasing/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["manifestVersion"] == 1
    assert manifest.json()["sourceBound"] is False  # v2 pack is still instructor-review-required

    missing = client.get("/api/v1/subjects/not-a-subject")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.django_db
def test_learner_profile_recommendation_memory_isolation_and_export(client: APIClient) -> None:
    learner_a = _new_learner(client, "api-memory-a")
    learner_b = _new_learner(client, "api-memory-b")

    profile = client.patch(f"/api/v1/learners/{learner_a}/profile", {"memoryEnabled": True, "displayName": "A"}, format="json")
    assert profile.status_code == 200
    assert profile.json()["memoryEnabled"] is True
    preference = client.patch(f"/api/v1/learners/{learner_a}/preferences", {"learningMode": "predict_reveal"}, format="json")
    assert preference.status_code == 200
    recommendation = client.get(f"/api/v1/learners/{learner_a}/recommendation?subjectId=dsap")
    assert recommendation.status_code == 200
    assert recommendation.json()["mode"] == "predict_reveal"
    assert recommendation.json()["reason"] == "learner_preference"

    disabled = client.post(f"/api/v1/learners/{learner_b}/memory", {"key": "mode", "content": "guided", "consent": True}, format="json")
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "memory_disabled"
    enabled = client.patch(f"/api/v1/learners/{learner_a}/memory", {"memoryEnabled": True}, format="json")
    assert enabled.status_code == 200
    saved = client.post(f"/api/v1/learners/{learner_a}/memory", {"key": "mode", "kind": "preference", "content": "build", "consent": True}, format="json")
    assert saved.status_code == 201
    assert saved.json()["key"] == "mode"
    assert client.get(f"/api/v1/learners/{learner_b}/memory").json()["items"] == []

    export = client.get(f"/api/v1/learners/{learner_a}/memory/export")
    assert export.status_code == 200
    assert export.json()["profile"]["learnerId"] == learner_a
    assert export.json()["memory"]["items"][0]["key"] == "mode"
    assert all(item.get("learnerId", learner_a) == learner_a for item in export.json().get("attempts", []))

    deleted = client.delete(f"/api/v1/learners/{learner_a}/memory")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/learners/{learner_a}/memory").json()["items"] == []


@pytest.mark.django_db
def test_dynamic_attempt_checkpoint_source_boundary_and_modes(client: APIClient) -> None:
    learner = _new_learner(client, "api-attempt-a")
    created = client.post(
        "/api/v1/modules/sampling-aliasing/attempts",
        {"learnerId": learner, "conceptId": "alias-frequency", "learnerText": "A signal is sampled at regular intervals.", "learningMode": "predict_reveal"},
        format="json",
    )
    assert created.status_code == 201
    attempt_id = created.json()["attemptId"]
    assert created.json()["learningMode"] in {"worked_example", "predict_reveal", "self_explain", "retrieval", "spaced_review", "interleaved_contrast", "concrete_example", "representation_switch", "exam_bridge"}

    prediction = client.post(
        f"/api/v1/attempts/{attempt_id}/checkpoints/sampling-check-03/predict",
        {"prediction": "At 600 samples/s, a 400 Hz tone can alias."},
        format="json",
    )
    assert prediction.status_code == 200
    assert prediction.json()["state"] == "complete"
    explanation = client.post(f"/api/v1/attempts/{attempt_id}/checkpoints/sampling-check-03/explain", {}, format="json")
    assert explanation.status_code == 200
    assert explanation.json()["state"] == "abstained"
    assert explanation.json()["reasonCode"] == "source_pack_not_approved"

    mode = client.post(f"/api/v1/attempts/{attempt_id}/learning-mode", {"learningMode": "build"}, format="json")
    assert mode.status_code == 422
    valid_mode = client.post(f"/api/v1/attempts/{attempt_id}/learning-mode", {"learningMode": "predict_reveal"}, format="json")
    assert valid_mode.status_code == 200
    assert valid_mode.json()["learningMode"] == "predict_reveal"


def test_v2_dsap_cases_have_source_bound_shape() -> None:
    valid_ids = {span["spanId"] for span in V2_SOURCE["spans"]}
    assert len(V2_CASES) == 16
    assert {case["expectedStatus"] for case in V2_CASES} == {"supported", "needs_precision", "misconception", "needs_human_review"}
    for case in V2_CASES:
        assert set(case.get("sourceAnchorIds", [])).issubset(valid_ids)
        if case["kind"] == "ambiguous":
            assert case["sourceAnchorIds"] == []
