from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from teachback.adaptive_runtime import activity_contracts_for_goal, deterministic_evaluation
from teachback.models import ActivityAttempt


def _register(client: APIClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        {"email": email, "password": "safe-password-123", "displayName": "Adaptive learner"},
        format="json",
    )
    assert response.status_code == 201, response.content


def _goal(client: APIClient, title: str) -> dict:
    response = client.post(
        "/api/v1/goals",
        {
            "title": title,
            "description": "I will manipulate a bounded case, make a prediction, and explain the observable trade-off.",
            "outcome": title,
            "currentLevel": "beginner",
            "timeBudget": "Two focused sessions",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
def test_every_supported_domain_receives_one_shared_structured_activity_contract() -> None:
    client = APIClient()
    _register(client, "adaptive-contracts@example.com")

    for title, domain, control in [
        ("Trace operating-system scheduling", "operating_systems", "policy"),
        ("Explain computer graphics camera projection", "computer_graphics", "camera"),
        ("Evaluate machine learning classification thresholds", "ai_ml", "threshold"),
        ("Study medical anatomy from academic references", "medical", "structure"),
    ]:
        goal = _goal(client, title)
        configuration = goal["activities"][0]["configuration"]
        assert configuration["schemaVersion"] == "activity.v1"
        assert configuration["domain"] == domain
        assert any(item["id"] == control for item in configuration["interactiveControls"])
        assert configuration["allowedResponseTypes"]
        if domain == "medical":
            assert configuration["sourceRequirements"]["mode"] == "required"


@pytest.mark.django_db
def test_structured_observable_attempt_persists_and_advances_with_deterministic_reason() -> None:
    client = APIClient()
    _register(client, "structured-attempt@example.com")
    goal = _goal(client, "Trace operating-system scheduling")
    activity = goal["activities"][0]

    response = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": activity["activityId"],
            "response": "With round robin, reducing the quantum improves response time for a newly runnable process, but it adds context switches. I predict the ready queue rotates more often and waiting-time fairness can improve for short jobs.",
            "learnerConclusion": "The useful trade-off is responsiveness versus switching overhead, so I would choose the quantum from the workload rather than treat one value as universally best.",
            "confidence": 4,
            "prediction": {"short_jobs_respond_sooner": True},
            "interactionState": {"policy": "round_robin", "quantum": 2, "processes": [{"id": "P1", "burst": 5}, {"id": "P2", "burst": 3}]},
            "simulationParameters": {"quantum": 2},
            "calculations": {"contextSwitches": 4},
            "trace": [{"process": "P1", "start": 0, "end": 2}, {"process": "P2", "start": 2, "end": 4}],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["adaptiveRoute"]["transitionReason"] == "strong_structured_evidence"
    assert body["adaptiveRoute"]["nextAction"] == "increase_difficulty"
    assert body["evidence"]["rubric"]["structuredAttempt"]["interactionState"]["policy"] == "round_robin"
    stored = ActivityAttempt.objects.get(attempt_id=body["evidence"]["rubric"]["structuredAttemptId"])
    assert stored.trace[0]["process"] == "P1"
    assert stored.interaction_state["simulationParameters"]["quantum"] == 2


@pytest.mark.django_db
def test_incomplete_structured_interaction_retries_and_medical_requires_sources() -> None:
    client = APIClient()
    _register(client, "adaptive-boundaries@example.com")
    os_goal = _goal(client, "Trace operating-system scheduling")
    weak = client.post(
        f"/api/v1/goals/{os_goal['goalId']}/attempts",
        {
            "activityId": os_goal["activities"][0]["activityId"],
            "response": "I think scheduling has a trade-off, but I have not yet run the bounded trace or checked the queue state.",
            "interactionState": {},
        },
        format="json",
    )
    assert weak.status_code == 200
    assert weak.json()["adaptiveRoute"]["nextAction"] == "retry"
    assert weak.json()["evidence"]["status"] == "needs_review"

    medical = _goal(client, "Study medical anatomy from academic references")
    missing_source = client.post(
        f"/api/v1/goals/{medical['goalId']}/attempts",
        {
            "activityId": medical["activities"][0]["activityId"],
            "response": "This academic mechanism description names a structure and its relationship, but it intentionally has no selected academic anchor and makes no patient-specific recommendation.",
            "interactionState": {"mechanism_map": [{"structure": "example", "function": "bounded academic explanation"}]},
        },
        format="json",
    )
    assert missing_source.status_code == 200
    assert missing_source.json()["adaptiveRoute"]["nextAction"] == "request_source_backed_verification"
    assert missing_source.json()["evidence"]["status"] == "needs_review"


def test_deterministic_runtime_has_explicit_remediation_and_transfer_outcomes() -> None:
    config = activity_contracts_for_goal(
        title="Bounded systems practice",
        domain="operating_systems",
        prerequisites=["Trace a process state"],
        requires_source=False,
        first_prompt="Predict the trace.",
    )[0]["configuration"]
    remediation = deterministic_evaluation(
        configuration={**config, "interactiveControls": []},
        attempt={"writtenExplanation": "I can name the process state and queue transition but not yet calculate the metric.", "structuredSubmitted": False},
        source_ids=[],
        anchor_ids=[],
        provider_failed=False,
    )
    assert remediation["action"] == "remediate_prerequisite"

    transfer = deterministic_evaluation(
        configuration=config,
        attempt={
            "writtenExplanation": "The trace predicts a fair rotation and the measured waiting time exposes the trade-off between response and switching overhead.",
            "learnerConclusion": "I would change policy for an interactive workload.",
            "interactionState": {"policy": "round_robin", "quantum": 2},
            "trace": [{"process": "P1", "start": 0, "end": 2}],
            "calculations": {"waiting": 5},
            "structuredSubmitted": True,
        },
        source_ids=[],
        anchor_ids=[],
        provider_failed=False,
    )
    assert transfer["action"] in {"advance", "increase_difficulty"}


@pytest.mark.django_db
def test_completing_the_last_activity_assigns_a_persisted_transfer_task() -> None:
    client = APIClient()
    _register(client, "adaptive-transfer@example.com")
    goal = _goal(client, "Trace operating-system scheduling")
    final_activity = goal["activities"][-1]
    result = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": final_activity["activityId"],
            "response": "The schedule trace makes the policy trade-off observable: a smaller quantum gives a newly runnable process an earlier response, while it increases context switches and can add overhead. I would calculate waiting time and turnaround time from completion and arrival, then compare the trace against a batch workload before choosing the policy.",
            "learnerConclusion": "The transfer is to change the workload and explain which metric should drive the policy choice.",
            "confidence": 4,
            "prediction": {"short_job_response": "earlier"},
            "interactionState": {"policy": "round_robin", "quantum": 2},
            "calculations": {"waiting": 5, "turnaround": 8},
            "trace": [{"process": "P1", "start": 0, "end": 2}, {"process": "P2", "start": 2, "end": 4}],
        },
        format="json",
    )
    assert result.status_code == 200, result.content
    payload = result.json()
    assert payload["adaptiveRoute"]["nextAction"] == "assign_transfer_task"
    assert any(activity["type"] == "transfer" and activity["status"] == "ready" for activity in payload["goal"]["activities"])
