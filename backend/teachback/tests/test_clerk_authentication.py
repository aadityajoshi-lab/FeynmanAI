from types import SimpleNamespace
from django.db import OperationalError

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


@pytest.mark.django_db
def test_clerk_authentication_passes_the_optional_local_public_key(monkeypatch):
    settings.CLERK_SECRET_KEY = "test-clerk-secret"
    settings.CLERK_JWT_KEY = "public-test-key"
    state = SimpleNamespace(is_signed_in=True, message=None, payload={"sub": "user_local_key", "email": "local-key@example.com"})
    captured = {}

    def authenticate(_request, options):
        captured["options"] = options
        return state

    monkeypatch.setattr(authentication, "authenticate_request", authenticate)

    response = APIClient().get("/api/v1/me", HTTP_AUTHORIZATION="Bearer test-session")

    assert response.status_code == 200
    assert captured["options"].jwt_key == "public-test-key"


def test_clerk_provision_retries_only_transient_sqlite_locks(monkeypatch):
    attempts = []

    def provision(_payload, _request):
        attempts.append(True)
        if len(attempts) < 3:
            raise OperationalError("database is locked")
        return "provisioned-user"

    monkeypatch.setattr(authentication, "_provision_user_for_clerk_payload", provision)
    monkeypatch.setattr(authentication.time, "sleep", lambda _seconds: None)

    assert authentication._user_for_clerk_payload({"sub": "user_retry"}, object()) == "provisioned-user"
    assert len(attempts) == 3
