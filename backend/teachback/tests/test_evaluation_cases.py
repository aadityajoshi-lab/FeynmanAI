"""Executable coverage for every frozen contracts/v1 evaluation case."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from teachback.models import Claim, LearningSession


EVALUATION_CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "v1" / "evaluation-cases.json").read_text(encoding="utf-8")
)["cases"]


def case(case_id: str) -> dict:
    return next(item for item in EVALUATION_CASES if item["caseId"] == case_id)


def _create_session(client: APIClient, text: str, request_id: str) -> str:
    response = client.post(
        "/api/v1/sessions",
        {"lessonId": "photosynthesis", "learnerText": text, "clientRequestId": request_id},
        format="json",
    )
    assert response.status_code == 201
    return response.json()["sessionId"]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
@pytest.mark.parametrize("case_id", [f"eval-{number:02d}" for number in range(1, 7)])
def test_frozen_audit_cases(client: APIClient, case_id: str) -> None:
    # Case IDs have a descriptive suffix; select the first frozen case whose
    # numeric prefix matches the parameter.
    item = next(c for c in EVALUATION_CASES if c["caseId"].startswith(case_id))
    session_id = _create_session(client, item["input"]["learnerText"], f"frozen-{case_id}-001")
    response = client.post(f"/api/v1/sessions/{session_id}/audit", {"recordVersion": 1}, format="json")
    expected = item["expected"]
    assert response.status_code == expected["httpStatus"]
    record = response.json()
    assert record["state"] == expected["state"]
    if "containsVerdicts" in expected:
        assert any(claim["verdict"] in expected["containsVerdicts"] for claim in record["claims"])
    if "verdict" in expected:
        claim = next(claim for claim in record["claims"] if claim["verdict"] == expected["verdict"])
        assert claim.get("misconceptionType") == expected.get("misconceptionType")
        assert expected["requiresAnchor"] in claim["sourceAnchorIds"]
    assert all(anchor.startswith("photosynthesis-v1-span-") for claim in record["claims"] for anchor in claim["sourceAnchorIds"])


@pytest.mark.django_db
def test_eval_07_empty_teachback_is_rejected(client: APIClient) -> None:
    item = case("eval-07-empty-teachback")
    response = client.post(
        "/api/v1/sessions",
        {"lessonId": "photosynthesis", "learnerText": item["input"]["learnerText"], "clientRequestId": "frozen-eval-07"},
        format="json",
    )
    assert response.status_code == item["expected"]["httpStatus"]
    assert response.json()["error"]["code"] == item["expected"]["errorCode"]


@pytest.mark.django_db
def test_eval_08_oversized_teachback_is_rejected(client: APIClient) -> None:
    item = case("eval-08-oversized-teachback")
    response = client.post(
        "/api/v1/sessions",
        {"lessonId": "photosynthesis", "learnerText": "x" * item["input"]["learnerTextLength"], "clientRequestId": "frozen-eval-08"},
        format="json",
    )
    assert response.status_code == item["expected"]["httpStatus"]
    assert response.json()["error"]["code"] == item["expected"]["errorCode"]


@pytest.mark.django_db
def test_eval_09_unknown_anchor_fails_closed(client: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from teachback import providers, views

    class BadFixture(providers.FixtureProvider):
        def audit(self, request):
            return {
                "claims": [{
                    "claimId": "claim-01", "learnerText": "bad evidence", "verdict": "supported",
                    "probe": "why?", "sourceAnchorIds": ["photosynthesis-v1-span-99"],
                }]
            }

    monkeypatch.setattr(views, "provider_for", lambda mode=None: BadFixture())
    session_id = _create_session(client, "Bad evidence", "frozen-eval-09")
    response = client.post(f"/api/v1/sessions/{session_id}/audit", {"recordVersion": 1}, format="json")
    assert response.status_code == case("eval-09-unknown-anchor")["expected"]["httpStatus"]
    assert response.json()["state"] == "needs_human_review"
    assert "invalid_source_anchor" in response.json()["warnings"]


@pytest.mark.django_db
def test_eval_10_malformed_provider_output_fails_closed(client: APIClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from teachback import providers, views

    class MalformedFixture(providers.FixtureProvider):
        def audit(self, request):
            return {"claims": "not-an-array"}

    monkeypatch.setattr(views, "provider_for", lambda mode=None: MalformedFixture())
    session_id = _create_session(client, "Malformed response", "frozen-eval-10")
    response = client.post(f"/api/v1/sessions/{session_id}/audit", {"recordVersion": 1}, format="json")
    assert response.status_code == case("eval-10-malformed-provider-output")["expected"]["httpStatus"]
    assert response.json()["state"] == "needs_human_review"
    assert "invalid_output" in response.json()["warnings"]


def _seed_record(*, record_version: int = 1, include_light_claim: bool = False) -> LearningSession:
    session = LearningSession.objects.create(
        lesson_id="photosynthesis", learner_text="Seeded teach-back", client_request_id=None,
        record_version=record_version, provider_mode="codex_fixture", status="ready",
    )
    Claim.objects.create(
        session=session, position=0, claim_id="claim-soil-mass", learner_text="Soil provides most of the mass.",
        verdict="misconception", misconception_type="source_of_matter", probe="Where does carbon come from?",
        source_anchor_ids=["photosynthesis-v1-span-06"],
    )
    if include_light_claim:
        Claim.objects.create(
            session=session, position=1, claim_id="claim-light-mass", learner_text="Sunlight becomes the mass.",
            verdict="misconception", misconception_type="source_of_matter", probe="What does light supply?",
            source_anchor_ids=["photosynthesis-v1-span-04"],
        )
    return session


@pytest.mark.django_db
def test_eval_11_and_12_clarification_are_read_only(client: APIClient) -> None:
    session = _seed_record()
    session_id = f"sess_{session.pk:08x}"
    before = client.get(f"/api/v1/sessions/{session_id}/record").json()
    answered = client.post(
        f"/api/v1/sessions/{session_id}/claims/claim-soil-mass/clarifications",
        {"question": case("eval-11-clarification-answered")["input"]["question"], "recordVersion": 1}, format="json",
    )
    assert answered.status_code == 200
    assert answered.json()["state"] == "answered"
    assert "photosynthesis-v1-span-06" in answered.json()["sourceAnchorIds"]
    assert answered.json()["recordVersion"] == before["recordVersion"]
    abstained = client.post(
        f"/api/v1/sessions/{session_id}/claims/claim-soil-mass/clarifications",
        {"question": case("eval-12-clarification-abstains")["input"]["question"], "recordVersion": 1}, format="json",
    )
    assert abstained.status_code == 200
    assert abstained.json()["state"] == "abstained"
    assert abstained.json()["reasonCode"] == "outside_source_pack"
    assert client.get(f"/api/v1/sessions/{session_id}/record").json()["recordVersion"] == before["recordVersion"]


@pytest.mark.django_db
def test_eval_13_selected_claim_revision_preserves_neighbors(client: APIClient) -> None:
    session = _seed_record(include_light_claim=True)
    session_id = f"sess_{session.pk:08x}"
    before = client.get(f"/api/v1/sessions/{session_id}/record").json()
    repair = case("eval-13-selected-claim-revision")["input"]["learnerRepair"]
    response = client.post(
        f"/api/v1/sessions/{session_id}/claims/claim-soil-mass/revisions",
        {"learnerRepair": repair, "expectedVersion": 1}, format="json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "updated"
    assert payload["recordVersion"] == 2
    assert payload["crossClaimRecheck"] is False
    light_before = next(c for c in before["claims"] if c["claimId"] == "claim-light-mass")
    light_after = next(c for c in payload["record"]["claims"] if c["claimId"] == "claim-light-mass")
    assert light_after["learnerText"] == light_before["learnerText"]


@pytest.mark.django_db
def test_eval_14_cross_claim_warning_is_visible(client: APIClient) -> None:
    session = _seed_record(include_light_claim=True)
    session_id = f"sess_{session.pk:08x}"
    repair = case("eval-14-cross-claim-warning")["input"]["learnerRepair"]
    response = client.post(
        f"/api/v1/sessions/{session_id}/claims/claim-light-mass/revisions",
        {"learnerRepair": repair, "expectedVersion": 1}, format="json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["crossClaimRecheck"] is True
    assert "cross_claim_recheck" in payload["warnings"]


@pytest.mark.django_db
def test_eval_15_stale_revision_uses_contract_error_code(client: APIClient) -> None:
    session = _seed_record(record_version=2)
    session_id = f"sess_{session.pk:08x}"
    response = client.post(
        f"/api/v1/sessions/{session_id}/claims/claim-soil-mass/revisions",
        {"learnerRepair": case("eval-15-stale-revision")["input"]["learnerRepair"], "expectedVersion": 1}, format="json",
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_record_version"


@pytest.mark.django_db
def test_eval_16_duplicate_session_request_is_idempotent(client: APIClient) -> None:
    body = {
        "lessonId": "photosynthesis", "learnerText": "Carbon dioxide and water make sugars using light energy.",
        "clientRequestId": case("eval-16-duplicate-session-request")["input"]["clientRequestId"],
    }
    first = client.post("/api/v1/sessions", body, format="json")
    repeat = client.post("/api/v1/sessions", body, format="json")
    assert first.status_code == 201
    assert repeat.status_code == 200
    assert repeat.json()["sessionId"] == first.json()["sessionId"]
