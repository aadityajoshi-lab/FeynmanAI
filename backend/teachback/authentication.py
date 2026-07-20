from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions

from .models import LearnerProfile


def _claim_value(payload: dict[str, Any], *names: str) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _email_from_claims(payload: dict[str, Any]) -> str:
    email = _claim_value(payload, "email", "email_address")
    if email:
        return email.lower()
    addresses = payload.get("email_addresses")
    if isinstance(addresses, list):
        for item in addresses:
            if isinstance(item, dict):
                value = _claim_value(item, "email_address", "email")
                if value:
                    return value.lower()
    return ""


def _display_name(payload: dict[str, Any], email: str) -> str:
    explicit = _claim_value(payload, "name", "full_name")
    if explicit:
        return explicit[:120]
    first = _claim_value(payload, "first_name", "given_name")
    last = _claim_value(payload, "last_name", "family_name")
    return " ".join(part for part in (first, last) if part)[:120] or email.split("@", 1)[0][:120]


def _username_for_clerk_id(clerk_user_id: str) -> str:
    # Django's default username column is 150 characters; Clerk subjects are
    # normally short, but hashing the tail makes this safe for any tenant.
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", clerk_user_id)
    candidate = f"clerk_{clean}"
    if len(candidate) <= 150:
        return candidate
    return f"clerk_{hashlib.sha256(clerk_user_id.encode()).hexdigest()}"


@transaction.atomic
def _user_for_clerk_payload(payload: dict[str, Any], request) -> Any:
    User = get_user_model()
    clerk_user_id = _claim_value(payload, "sub")
    if not clerk_user_id:
        raise AuthenticationFailed("The Clerk session has no user subject.")
    email = _email_from_claims(payload)
    display_name = _display_name(payload, email)

    profile = LearnerProfile.objects.select_related("account").filter(clerk_user_id=clerk_user_id).first()
    user = profile.account if profile else None
    if user is None and email:
        # Link an existing local account only when the email is an exact match
        # and it has not already been claimed by another Clerk identity.
        user = User.objects.filter(email__iexact=email, feynman_profile__clerk_user_id__isnull=True).first()
    if user is None:
        username = _username_for_clerk_id(clerk_user_id)
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(username=username, email=email, first_name=display_name[:150])
    elif email and not user.email:
        user.email = email
        user.save(update_fields=["email"])

    anonymous_key = request.headers.get("X-Feynman-Anonymous-Learner", "").strip()
    account_was_changed = False
    if profile is None:
        profile = LearnerProfile.objects.filter(account=user).first()
    if profile is None and anonymous_key:
        profile = LearnerProfile.objects.filter(anonymous_key=anonymous_key, account__isnull=True).first()
        if profile:
            profile.account = user
            account_was_changed = True
    if profile is None:
        profile = LearnerProfile.objects.create(
            account=user,
            anonymous_key=f"account_{uuid.uuid4().hex}",
            display_name=display_name,
        )
    # Bearer authentication runs for every API request, often concurrently
    # during a workspace load. Avoid rewriting an unchanged profile on every
    # read; repeated SQLite writes here can otherwise lock parallel requests.
    update_fields: list[str] = []
    if account_was_changed or profile.account_id != user.id:
        profile.account = user
        update_fields.append("account")
    if profile.clerk_user_id != clerk_user_id:
        profile.clerk_user_id = clerk_user_id
        update_fields.append("clerk_user_id")
    if display_name and not profile.display_name:
        profile.display_name = display_name
        update_fields.append("display_name")
    if update_fields:
        update_fields.append("updated_at")
        profile.save(update_fields=update_fields)
    return user


class ClerkAuthentication(BaseAuthentication):
    """Authenticate Clerk session tokens without replacing local sessions."""

    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        authorization = request.headers.get("Authorization", "")
        if not authorization.lower().startswith("bearer "):
            return None
        secret_key = getattr(settings, "CLERK_SECRET_KEY", "")
        if not secret_key:
            raise AuthenticationFailed("Clerk authentication is not configured.")
        try:
            state = authenticate_request(
                request,
                AuthenticateRequestOptions(
                    secret_key=secret_key,
                    authorized_parties=getattr(settings, "CLERK_AUTHORIZED_PARTIES", None) or None,
                    accepts_token=["session_token"],
                ),
            )
        except Exception as exc:
            raise AuthenticationFailed("The Clerk session could not be verified.") from exc
        if not state.is_signed_in or not state.payload:
            raise AuthenticationFailed(state.message or "The Clerk session is not valid.")
        return _user_for_clerk_payload(state.payload, request), state
