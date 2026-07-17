import pytest
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_lesson_and_session_flow(client):
    lesson = client.get("/api/v1/lessons/photosynthesis")
    assert lesson.status_code == 200
    assert lesson.json()["sourcePackId"] == "photosynthesis-v1"
    created = client.post("/api/v1/sessions", {"lessonId": "photosynthesis", "learnerText": "The soil provides most of a plant's mass and sunlight becomes mass.", "clientRequestId": "demo-flow-001"}, format="json")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]
    assert session_id.startswith("sess_")
    audited = client.post(f"/api/v1/sessions/{session_id}/audit", {"recordVersion": 1}, format="json")
    assert audited.status_code == 200
    record = audited.json()
    assert record["state"] == "ready"
    assert record["providerMode"] == "codex_fixture"
    assert any(c["verdict"] == "misconception" and c["misconceptionType"] == "source_of_matter" for c in record["claims"])
    claim_id = next(c["claimId"] for c in record["claims"] if c["verdict"] == "misconception")
    clarified = client.post(f"/api/v1/sessions/{session_id}/claims/{claim_id}/clarifications", {"question": "Why isn't soil the main source of carbon?", "recordVersion": record["recordVersion"]}, format="json")
    assert clarified.status_code == 200
    assert clarified.json()["state"] == "answered"
    repaired = client.post(f"/api/v1/sessions/{session_id}/claims/{claim_id}/revisions", {"learnerRepair": "Carbon dioxide supplies carbon atoms and light supplies energy.", "expectedVersion": record["recordVersion"]}, format="json")
    assert repaired.status_code == 200
    assert repaired.json()["state"] == "updated"
    assert repaired.json()["crossClaimRecheck"] is False
    assert repaired.json()["record"]["recordVersion"] == record["recordVersion"] + 1


@pytest.mark.django_db
def test_idempotency_and_stale_revision(client):
    body = {"lessonId": "photosynthesis", "learnerText": "Carbon dioxide and water make sugars using light energy.", "clientRequestId": "demo-idempotent-001"}
    first = client.post("/api/v1/sessions", body, format="json")
    second = client.post("/api/v1/sessions", body, format="json")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["sessionId"] == first.json()["sessionId"]
    sid = first.json()["sessionId"]
    client.post(f"/api/v1/sessions/{sid}/audit", {"recordVersion": 1}, format="json")
    record = client.get(f"/api/v1/sessions/{sid}/record").json()
    claim_id = record["claims"][0]["claimId"]
    first_revision = client.post(f"/api/v1/sessions/{sid}/claims/{claim_id}/revisions", {"learnerRepair": "A repaired claim with carbon dioxide.", "expectedVersion": 1}, format="json")
    assert first_revision.status_code == 200
    stale = client.post(f"/api/v1/sessions/{sid}/claims/{claim_id}/revisions", {"learnerRepair": "A second stale repair.", "expectedVersion": 1}, format="json")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_record_version"


@pytest.mark.django_db
def test_unknown_anchor_is_fail_closed(client, monkeypatch):
    from teachback import providers, views

    class BadFixture(providers.FixtureProvider):
        def audit(self, request):
            return {"claims": [{"claimId": "claim-01", "learnerText": "bad", "verdict": "supported", "probe": "why?", "sourceAnchorIds": ["photosynthesis-v1-span-99"]}]}

    monkeypatch.setattr(views, "provider_for", lambda mode=None: BadFixture())
    body = {"lessonId": "photosynthesis", "learnerText": "Bad evidence", "clientRequestId": "demo-bad-anchor"}
    sid = client.post("/api/v1/sessions", body, format="json").json()["sessionId"]
    result = client.post(f"/api/v1/sessions/{sid}/audit", {"recordVersion": 1}, format="json")
    assert result.status_code == 200
    assert result.json()["state"] == "needs_human_review"
    assert result.json()["providerMode"] == "human_review"
