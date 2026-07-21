from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from teachback.adaptive_runtime import deterministic_evaluation
from teachback.models import CurriculumPack


def register(client: APIClient, email: str) -> None:
    response = client.post("/api/v1/auth/register", {"email": email, "password": "safe-password-123", "displayName": "Curriculum learner"}, format="json")
    assert response.status_code == 201, response.content


def create_history_goal(client: APIClient) -> dict:
    response = client.post(
        "/api/v1/goals",
        {
            "title": "Learn the causes and consequences of the French Revolution from the uploaded source pack",
            "description": "Build a source-grounded explanation of causes, sequence, and consequences.",
            "outcome": "Explain and transfer the historical relationships",
            "currentLevel": "beginner",
            "timeBudget": "Three focused sessions",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
def test_unknown_domain_compiles_from_selected_source_with_citations_and_generic_route() -> None:
    client = APIClient()
    register(client, "history-compiler@example.com")
    goal = create_history_goal(client)
    notebook = client.post("/api/v1/notebooks", {"title": "French Revolution source pack", "goalId": goal["goalId"]}, format="json")
    assert notebook.status_code == 201, notebook.content
    source = client.post(
        f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text",
        {
            "title": "French Revolution notes",
            "text": "The Ancien Régime concentrated privilege in estates while fiscal crisis and unequal taxation increased political pressure. The Estates-General and popular mobilization changed representation and authority. Revolutionary institutions then produced conflict, the Terror, and a durable argument about citizenship and sovereignty.",
            "useForGrounding": True,
        },
        format="json",
    )
    assert source.status_code == 201, source.content
    source_row = source.json()["sources"][0]
    compiled = client.post(f"/api/v1/goals/{goal['goalId']}/curriculum", {"sourceIds": [source_row["sourceId"]]}, format="json")
    assert compiled.status_code == 201, compiled.content
    curriculum = compiled.json()["curriculum"]
    assert curriculum["status"] == "ready"
    assert curriculum["provenance"]["providerMode"] == "deterministic_fallback"
    assert len(curriculum["concepts"]) >= 2
    assert len(curriculum["activities"]) >= 7
    allowed_anchors = set(source_row["anchorIds"])
    assert set(curriculum["sourceAnchorIds"]).issubset(allowed_anchors)
    assert all(set(activity["sourceAnchorIds"]).issubset(allowed_anchors) for activity in curriculum["activities"])
    assert all(activity["configuration"]["adapterKind"] == "source_grounded_reasoning" for activity in curriculum["activities"])
    route = compiled.json()["goal"]["route"]
    assert route["curriculumVersionId"] == curriculum["curriculumVersionId"]
    assert route["activeActivityId"]


@pytest.mark.django_db
def test_malformed_provider_proposal_falls_back_without_unselected_citations() -> None:
    client = APIClient()
    register(client, "history-provider-fallback@example.com")
    goal = create_history_goal(client)
    notebook = client.post("/api/v1/notebooks", {"title": "History sources", "goalId": goal["goalId"]}, format="json")
    source = client.post(f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text", {"title": "Selected history", "text": "Fiscal crisis changed representation and institutions.", "useForGrounding": True}, format="json")
    source_row = source.json()["sources"][0]

    class MalformedProvider:
        mode = "live_openai"

        def compile_curriculum(self, request):
            return {"concepts": [{"key": "unsupported", "title": "Unsupported claim", "description": "", "sourceIds": ["other-source"], "sourceAnchorIds": ["other-anchor"], "uncertainty": {}}], "prerequisites": [], "activities": [], "uncertainty": {}}

    with patch("teachback.curriculum_compiler.provider_for", return_value=MalformedProvider()):
        compiled = client.post(f"/api/v1/goals/{goal['goalId']}/curriculum", {"sourceIds": [source_row["sourceId"]]}, format="json")
    assert compiled.status_code == 201, compiled.content
    assert compiled.json()["curriculum"]["provenance"]["providerMode"] == "deterministic_fallback"
    assert compiled.json()["curriculum"]["compiler"]["providerErrorCategory"] == "ProviderOutputError"
    assert CurriculumPack.objects.filter(goal__goal_id=goal["goalId"], status="ready").exists()


@pytest.mark.django_db
def test_unknown_domain_attempts_retry_then_advance_and_route_survives_refresh() -> None:
    client = APIClient()
    register(client, "history-evidence@example.com")
    goal = create_history_goal(client)
    notebook = client.post("/api/v1/notebooks", {"title": "Evidence history", "goalId": goal["goalId"]}, format="json")
    source = client.post(f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text", {"title": "History source", "text": "Fiscal crisis and unequal taxation increased pressure; mobilization changed representation and authority.", "useForGrounding": True}, format="json")
    source_row = source.json()["sources"][0]
    compiled = client.post(f"/api/v1/goals/{goal['goalId']}/curriculum", {"sourceIds": [source_row["sourceId"]]}, format="json").json()
    activity = compiled["goal"]["activities"][0]
    weak = client.post(f"/api/v1/goals/{goal['goalId']}/attempts", {"activityId": activity["activityId"], "response": "I predict a change but need to inspect the source."}, format="json")
    assert weak.status_code == 200, weak.content
    assert weak.json()["adaptiveRoute"]["nextAction"] == "retry"
    strong = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": activity["activityId"],
            "response": "I predict fiscal crisis and unequal taxation increased pressure on representation. The source anchor connects that pressure to mobilization and institutional change, so I would compare the Estates-General with later revolutionary authority and state the uncertainty around which cause was most decisive.",
            "learnerConclusion": "The relationship is a sequence, not a single cause; the changed condition is a different distribution of privilege.",
            "confidence": 4,
            "prediction": {"mobilization": "increases"},
            "interactionState": {"case": "estates", "changedCondition": "privilege redistributed", "checked": True},
            "sourceIds": [source_row["sourceId"]],
            "sourceAnchorIds": [source_row["anchorIds"][0]],
        },
        format="json",
    )
    assert strong.status_code == 200, strong.content
    assert strong.json()["adaptiveRoute"]["nextAction"] in {"advance", "increase_difficulty"}
    reopened = client.get(f"/api/v1/goals/{goal['goalId']}/curriculum")
    assert reopened.status_code == 200
    assert reopened.json()["curriculum"]["status"] == "ready"
    assert reopened.json()["goal"]["route"]["activeActivityId"]


@pytest.mark.django_db
def test_deleting_selected_source_marks_curriculum_stale() -> None:
    client = APIClient()
    register(client, "history-stale@example.com")
    goal = create_history_goal(client)
    notebook = client.post("/api/v1/notebooks", {"title": "Stale history", "goalId": goal["goalId"]}, format="json")
    source = client.post(f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text", {"title": "Replaceable history", "text": "Institutions and representation changed after fiscal crisis.", "useForGrounding": True}, format="json")
    source_row = source.json()["sources"][0]
    compiled = client.post(f"/api/v1/goals/{goal['goalId']}/curriculum", {"sourceIds": [source_row["sourceId"]]}, format="json")
    assert compiled.status_code == 201
    removed = client.delete(f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/{source_row['sourceId']}")
    assert removed.status_code == 200, removed.content
    stale = client.get(f"/api/v1/goals/{goal['goalId']}/curriculum")
    assert stale.status_code == 200
    assert stale.json()["curriculum"]["status"] == "stale"


@pytest.mark.django_db
def test_curriculum_quality_preview_and_route_correction_are_persisted() -> None:
    client = APIClient()
    register(client, "quality-preview@example.com")
    goal = create_history_goal(client)
    notebook = client.post("/api/v1/notebooks", {"title": "Quality history", "goalId": goal["goalId"]}, format="json")
    source = client.post(f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text", {"title": "Quality source", "text": "Fiscal crisis weakened the monarchy.\n\nBread prices intensified unrest.\n\nRights language reframed citizenship.", "useForGrounding": True}, format="json")
    source_row = source.json()["sources"][0]
    compiled = client.post(f"/api/v1/goals/{goal['goalId']}/curriculum", {"sourceIds": [source_row["sourceId"]]}, format="json")
    assert compiled.status_code == 201, compiled.content
    curriculum = compiled.json()["curriculum"]
    assert curriculum["quality"]["coveragePercent"] == 100
    assert len(curriculum["compilerStages"]) == 6
    assert curriculum["preview"]["editable"] is True
    activity_order = [activity["activityId"] for activity in compiled.json()["goal"]["activities"]]
    edited = client.patch(f"/api/v1/goals/{goal['goalId']}/curriculum", {"activityOrder": list(reversed(activity_order)), "learnerNote": "Start with the fiscal mechanism."}, format="json")
    assert edited.status_code == 200, edited.content
    assert edited.json()["curriculum"]["preview"]["routeEdited"] is True
    assert edited.json()["goal"]["route"]["routeEdited"] is True


def test_semantic_evaluator_detects_contradiction_and_reports_quality_signals() -> None:
    result = deterministic_evaluation(
        configuration={
            "concept": "classification threshold",
            "prerequisites": ["Inspect a confusion matrix"],
            "expectedLearnerObservations": ["prediction", "confusion_matrix_or_metric"],
            "evaluatorRubric": ["Names precision/recall trade-off"],
            "interactiveControls": [{"id": "threshold"}],
            "sourceRequirements": {"mode": "optional"},
        },
        attempt={
            "writtenExplanation": "The threshold increases the positive predictions and changes the precision recall trade-off.",
            "learnerConclusion": "The result is lower and fewer positive predictions occur.",
            "prediction": {"expected": "increase"},
            "interactionState": {"threshold": 0.7},
            "confidence": 5,
            "structuredSubmitted": True,
        },
        source_ids=[],
        anchor_ids=[],
        provider_failed=False,
    )
    assert result["action"] == "retry"
    assert result["reason"] == "prediction_conclusion_contradiction"
    assert result["qualitySignals"]["predictionConclusionContradiction"] is True
    assert "conceptCoverage" in result["qualitySignals"]
