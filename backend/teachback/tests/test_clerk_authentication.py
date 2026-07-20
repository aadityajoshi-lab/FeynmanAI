from types import SimpleNamespace

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from teachback import authentication
from teachback.models import LearnerProfile


@pytest.mark.django_db
def test_clerk_bearer_creates_django_identity_and_personal_workspace(monkeypatch):
    settings.CLERK_SECRET_KEY = "test-clerk-secret"
    state = SimpleNamespace(
        is_signed_in=True,
        message=None,
        payload={
            "sub": "user_clerk_alpha",
            "email": "clerk-alpha@example.com",
            "first_name": "Alpha",
            "last_name": "Learner",
        },
    )
    monkeypatch.setattr(authentication, "authenticate_request", lambda request, options: state)

    response = APIClient().get("/api/v1/me", HTTP_AUTHORIZATION="Bearer test-session")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "clerk-alpha@example.com"
    profile = LearnerProfile.objects.get(clerk_user_id="user_clerk_alpha")
    assert profile.account is not None
    assert profile.workspace_id is not None


@pytest.mark.django_db
def test_clerk_bearer_claims_anonymous_profile_before_workspace_creation(monkeypatch):
    settings.CLERK_SECRET_KEY = "test-clerk-secret"
    anonymous = LearnerProfile.objects.create(anonymous_key="anonymous-to-claim", display_name="Old learner")
    state = SimpleNamespace(
        is_signed_in=True,
        message=None,
        payload={"sub": "user_clerk_claim", "email": "claim@example.com", "name": "Claimed learner"},
    )
    monkeypatch.setattr(authentication, "authenticate_request", lambda request, options: state)

    response = APIClient().get(
        "/api/v1/me",
        HTTP_AUTHORIZATION="Bearer test-session",
        HTTP_X_FEYNMAN_ANONYMOUS_LEARNER="anonymous-to-claim",
    )

    assert response.status_code == 200
    anonymous.refresh_from_db()
    assert anonymous.account_id is not None
    assert anonymous.clerk_user_id == "user_clerk_claim"


@pytest.mark.django_db
def test_invalid_clerk_bearer_is_rejected(monkeypatch):
    settings.CLERK_SECRET_KEY = "test-clerk-secret"
    state = SimpleNamespace(is_signed_in=False, message="Invalid session", payload=None)
    monkeypatch.setattr(authentication, "authenticate_request", lambda request, options: state)

    response = APIClient().get("/api/v1/me", HTTP_AUTHORIZATION="Bearer invalid")

    assert response.status_code == 401
