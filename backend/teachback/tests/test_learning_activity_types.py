import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_general_goal_includes_a_distinct_apply_task_before_transfer() -> None:
    client = APIClient()
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "activity-types@example.com", "password": "safe-password-123", "displayName": "Activity learner"},
        format="json",
    )
    assert registration.status_code == 201
    goal = client.post(
        "/api/v1/goals",
        {
            "title": "Understand a new language concept",
            "description": "Practice it in a concrete case.",
            "outcome": "Use the concept clearly",
            "currentLevel": "beginner",
            "timeBudget": "Flexible",
        },
        format="json",
    )
    assert goal.status_code == 201
    activity_types = [activity["type"] for activity in goal.json()["activities"]]
    assert activity_types == ["predict", "explain", "apply", "transfer"]


@pytest.mark.django_db
def test_engineering_goal_exposes_every_active_practice_mode() -> None:
    client = APIClient()
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "engineering-activity-types@example.com", "password": "safe-password-123", "displayName": "Engineering learner"},
        format="json",
    )
    assert registration.status_code == 201
    goal = client.post(
        "/api/v1/goals",
        {
            "title": "Trace an operating-system scheduler",
            "description": "Simulate and compare a scheduler policy.",
            "outcome": "Trace and debug a scheduler",
            "currentLevel": "beginner",
            "timeBudget": "Flexible",
        },
        format="json",
    )
    assert goal.status_code == 201
    assert [activity["type"] for activity in goal.json()["activities"]] == ["predict", "explain", "derive", "simulate", "debug", "apply", "build", "transfer"]
