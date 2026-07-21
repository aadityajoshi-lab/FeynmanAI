import pytest
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from rest_framework.test import APIClient
from unittest.mock import patch

from teachback.notebook_media import _artifact_text, _rank_sections, _retrieve_chunks, answer_notebook_question, generate_notebook_artifact
from teachback.notebook_pipeline import NotebookExtractionError, _inline_ocr_heading, build_artifact_payload
from teachback.providers import ProviderOutputError, ProviderUnavailable
from teachback.web_sources import FetchedReference


def test_provider_artifact_text_repairs_duplicate_glyph_output_without_touching_normal_words() -> None:
    assert _artifact_text("RReeccuurrrreennccee aanndd ccoonnvvoolluuttiioonnss", "quiz option") == "Recurrence and convolutions"
    assert _artifact_text("Trraananssffoorrmmeerr", "quiz title") == "Transformer"
    assert _artifact_text("WW hhaatt mmeecchhaanniissmmss ddoeeess tthhee TTrraanassffoorrmmeerr??", "quiz question") == "What mechanisms does the Transformer?"
    assert _artifact_text("Ooverview", "table title") == "Overview"
    assert _artifact_text("A book is a useful source.", "normal text") == "A book is a useful source."


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_notebook_upload_builds_pack_and_artifacts(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Signals notebook", "learningGoal": "exam", "ocrProvider": "local"}, format="json")
    assert created.status_code == 201
    notebook_id = created.json()["notebookId"]

    upload = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("notes.md", b"# Analog instruments\n\nMeasurement = unknown / standard\nAnalog instruments use a pointer or waveform.", content_type="text/markdown"), "sourceKind": "reference", "ocrProvider": "local"},
        format="multipart",
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["status"] == "ready"
    assert body["stats"]["sourceCount"] == 1
    assert body["stats"]["formulaCount"] == 1
    assert body["knowledgePack"]["sections"]
    assert "Measurement = unknown / standard" in body["knowledgePackMarkdown"]

    artifact = client.post(f"/api/v1/notebooks/{notebook_id}/artifacts", {"type": "mcq"}, format="json")
    assert artifact.status_code == 201
    assert artifact.json()["payload"]["kind"] == "mcq"
    assert artifact.json()["payload"]["questions"]

    with patch("teachback.notebook_views.answer_notebook_question", return_value={"answer": "Measurement compares an unknown quantity with a standard.", "sourceIds": [body["sources"][0]["sourceId"]], "sourceAnchorIds": [], "groundedIn": "notebook"}):
        answer = client.post(f"/api/v1/notebooks/{notebook_id}/ask", {"question": "What is measurement?"}, format="json")
    assert answer.status_code == 200
    assert "Measurement" in answer.json()["answer"]
    assert len(client.get(f"/api/v1/notebooks/{notebook_id}").json()["chatMessages"]) == 2


@pytest.mark.django_db
def test_url_source_uses_the_explicit_bounded_fetch_contract(client: APIClient) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        {"email": "web-fetch@example.com", "password": "safe-password-123", "displayName": "Web fetch learner"},
        format="json",
    )
    assert registered.status_code == 201
    created = client.post("/api/v1/notebooks", {"title": "Web source notebook", "learningGoal": "understand", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    fetched = FetchedReference(
        payload=b"# Sampling\n\nSampling maps a continuous signal to discrete observations.",
        extraction_mime="text/markdown",
        original_mime="text/html",
        final_url="https://example.com/sampling",
        title="Sampling notes",
        source_kind="web_page",
        fetched_bytes=128,
        metadata={"description": "A source-backed sampling overview."},
        assets=({"type": "image", "mimeType": "image/png", "alt": "Sampled waveform", "dataUrl": "data:image/png;base64,c2FtcGxl"},),
    )

    with patch("teachback.notebook_views.fetch_reference", return_value=fetched) as fetch:
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/sources/text",
            {"url": "https://example.com/sampling", "sourceKind": "url_reference", "fetchWebsite": True, "ocrProvider": "auto"},
            format="json",
        )

    assert response.status_code == 201
    fetch.assert_called_once_with("https://example.com/sampling")
    source = response.json()["sources"][0]
    assert source["sourceKind"] == "web_page"
    assert source["extraction"]["fetchWebsite"] is True
    assert source["extraction"]["fetchedUrl"] == "https://example.com/sampling"
    assert source["extraction"]["webMetadata"]["description"] == "A source-backed sampling overview."
    assert source["extraction"]["assetCount"] == 1
    assert source["assets"][0]["alt"] == "Sampled waveform"
    assert source["assets"][0]["dataUrl"].startswith("data:image/png;base64,")


@pytest.mark.django_db
def test_url_source_can_decline_fetch_only_when_text_is_supplied(client: APIClient) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        {"email": "url-contract@example.com", "password": "safe-password-123", "displayName": "URL contract learner"},
        format="json",
    )
    assert registered.status_code == 201
    created = client.post("/api/v1/notebooks", {"title": "URL contract notebook", "learningGoal": "understand", "ocrProvider": "local"}, format="json")

    response = client.post(
        f"/api/v1/notebooks/{created.json()['notebookId']}/sources/text",
        {"url": "https://example.com/notes", "sourceKind": "url_reference", "fetchWebsite": False},
        format="json",
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "source_fetch_required"


def test_notebook_provider_fallback_is_explicitly_machine_readable() -> None:
    pack = {
        "sections": [{
            "sectionId": "measurement",
            "title": "Measurement",
            "sourceIds": ["source-1"],
            "blocks": [{"type": "text", "markdown": "Measurement compares an unknown quantity with a known standard.", "sourceAnchor": "source-1:p1"}],
        }],
    }
    with patch("teachback.notebook_media.provider_for", side_effect=ProviderUnavailable("offline for test")):
        result = answer_notebook_question(pack, "What is measurement?", allow_web_search=False)
    assert result["degraded"] is True
    assert result["providerUnavailable"] is True
    assert "source excerpt" in result["providerMessage"].lower()
    assert result["sourceAnchorIds"] == ["source-1:p1"]
    assert result["providerErrorCategory"] == "provider_unavailable"
    assert result["retryAction"] == "ask_again"


def test_notebook_invalid_or_uncited_provider_output_is_not_mislabelled_unavailable() -> None:
    pack = {
        "sections": [{
            "sectionId": "measurement",
            "title": "Measurement",
            "sourceIds": ["source-1"],
            "blocks": [{"type": "text", "markdown": "Measurement compares an unknown quantity with a known standard.", "sourceAnchor": "source-1:p1"}],
        }],
    }
    with patch("teachback.notebook_media.provider_for") as provider:
        provider.return_value.answer_notebook_question.return_value = {
            "answer": "Measurement compares an unknown quantity with a known standard.",
            "groundedIn": "notebook",
            "sourceAnchorIds": [],
        }
        uncited = answer_notebook_question(pack, "What is measurement?", allow_web_search=False)
    assert uncited["degraded"] is True
    assert uncited["providerUnavailable"] is False
    assert uncited["providerOutputInvalid"] is True
    assert uncited["citationValidationFailed"] is True
    assert uncited["providerErrorCategory"] == "citation_validation_failed"
    assert "could not be validated" in uncited["providerMessage"].lower()

    with patch("teachback.notebook_media.provider_for", side_effect=ProviderOutputError("provider returned malformed structured output")):
        malformed = answer_notebook_question(pack, "What is measurement?", allow_web_search=False)
    assert malformed["providerUnavailable"] is False
    assert malformed["providerOutputInvalid"] is True
    assert malformed["citationValidationFailed"] is False
    assert malformed["providerErrorCategory"] == "model_response_invalid"


def test_notebook_provider_citations_are_deduplicated() -> None:
    pack = {
        "sections": [{
            "sectionId": "measurement",
            "title": "Measurement",
            "sourceIds": ["source-1"],
            "blocks": [{"type": "text", "markdown": "Measurement compares an unknown quantity with a known standard.", "sourceAnchor": "source-1:p1"}],
        }],
    }
    with patch("teachback.notebook_media.provider_for") as provider:
        provider.return_value.answer_notebook_question.return_value = {
            "answer": "Measurement compares an unknown quantity with a known standard.",
            "groundedIn": "notebook",
            "sourceAnchorIds": ["source-1:p1", "source-1:p1"],
        }
        result = answer_notebook_question(pack, "What is measurement?", allow_web_search=False)
    assert result["sourceAnchorIds"] == ["source-1:p1"]


@pytest.mark.django_db
def test_notebook_ask_persists_provider_unavailable_state(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Provider-state notebook"}, format="json")
    notebook_id = created.json()["notebookId"]
    upload = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("notes.md", b"# Signal\n\nA signal carries information.", content_type="text/markdown")},
        format="multipart",
    )
    source_id = upload.json()["sources"][0]["sourceId"]
    with patch(
        "teachback.notebook_views.answer_notebook_question",
        return_value={
            "answer": "A signal carries information.",
            "sourceIds": [source_id],
            "sourceAnchorIds": [upload.json()["sources"][0]["anchorIds"][0]],
            "groundedIn": "notebook",
            "degraded": True,
            "providerUnavailable": True,
            "providerMessage": "The teaching model is unavailable. This is a source excerpt, not a generated answer.",
        },
    ):
        response = client.post(f"/api/v1/notebooks/{notebook_id}/ask", {"question": "What is a signal?"}, format="json")
    assert response.status_code == 200
    assert response.json()["providerUnavailable"] is True
    history = client.get(f"/api/v1/notebooks/{notebook_id}/chat").json()["messages"]
    assert history[-1]["status"] == "provider_unavailable"
    assert history[-1]["providerUnavailable"] is True


@pytest.mark.django_db
def test_notebook_chat_history_persists_provider_and_citation_provenance(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Provenance notebook"}, format="json")
    notebook_id = created.json()["notebookId"]
    upload = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("notes.md", b"# Signal\n\nA signal carries information.", content_type="text/markdown")},
        format="multipart",
    )
    source = upload.json()["sources"][0]
    with patch(
        "teachback.notebook_views.answer_notebook_question",
        return_value={
            "answer": "A signal carries information.",
            "sourceIds": [source["sourceId"]],
            "sourceAnchorIds": [source["anchorIds"][0]],
            "groundedIn": "notebook",
            "provider": "fireworks",
            "model": "test-model",
            "providerStatus": "completed",
            "citationValidation": "passed",
        },
    ):
        response = client.post(f"/api/v1/notebooks/{notebook_id}/ask", {"question": "What is a signal?"}, format="json")
    assert response.status_code == 200
    message = client.get(f"/api/v1/notebooks/{notebook_id}/chat").json()["messages"][-1]
    assert message["provider"] == "fireworks"
    assert message["model"] == "test-model"
    assert message["sourceAnchorIds"] == [source["anchorIds"][0]]


@pytest.mark.django_db
def test_typed_selected_source_answers_with_citations_when_query_has_no_exact_token_overlap(client: APIClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "typed-citation@example.com", "password": "safe-password-123", "displayName": "Typed source learner"},
        format="json",
    )
    assert registration.status_code == 201
    notebook = client.post("/api/v1/notebooks", {"title": "Scheduling reference"}, format="json")
    assert notebook.status_code == 201
    notebook_id = notebook.json()["notebookId"]
    source = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {
            "title": "Round-robin scheduling notes",
            "sourceKind": "typed_text",
            "text": "Round-robin scheduling can lower interactive response time, but a smaller time quantum increases context-switch overhead.",
            "useForGrounding": True,
        },
        format="json",
    )
    assert source.status_code == 201
    source_payload = source.json()["sources"][0]

    # "scheduler" and "scheduling" do not share an exact rank token.  The
    # provider is deliberately unavailable here so this asserts the real
    # source-scoped excerpt/citation fallback rather than a mocked view.
    with patch("teachback.notebook_media.provider_for", side_effect=ProviderUnavailable("offline for test")):
        answer = client.post(
            f"/api/v1/notebooks/{notebook_id}/ask",
            {"question": "What trade-off does the scheduler source describe?", "sourceIds": [source_payload["sourceId"]]},
            format="json",
        )
    assert answer.status_code == 200, answer.content
    payload = answer.json()
    assert payload["groundedIn"] == "notebook"
    assert payload["sourceIds"] == [source_payload["sourceId"]]
    assert payload["sourceAnchorIds"] == source_payload["anchorIds"]
    assert payload["providerUnavailable"] is True
    assert "context-switch overhead" in payload["answer"].casefold()


def test_ranker_includes_selected_supplementary_ocr_sections_for_chat() -> None:
    supplementary = {
        "sectionId": "source-ocr-section-001",
        "title": "Selected OCR reference",
        "order": 1,
        "sourceIds": ["nbsrc_selected"],
        "blocks": [
            {
                "blockId": "block_selected_page_two",
                "sourceAnchor": "sourcehash:p2",
                "page": 2,
                "type": "text",
                "markdown": "The page-two acceptance marker is AXIOM-ORBIT-47.",
            }
        ],
    }
    ranked = _rank_sections(
        {"sections": [], "supplementarySections": [supplementary]},
        "What exact acceptance marker is stated on the second page?",
    )
    assert ranked == [supplementary]


def test_chunk_retrieval_sends_relevant_ocr_blocks_without_losing_anchors() -> None:
    sections = [{
        "sectionId": "fourier",
        "title": "Discrete Fourier Transform",
        "sourceIds": ["pdf-1"],
        "blocks": [
            {"blockId": "b1", "sourceAnchor": "pdf-1:p1:b1", "page": 1, "type": "text", "markdown": "A transform maps a signal into frequency components."},
            {"blockId": "b2", "sourceAnchor": "pdf-1:p12:b2", "page": 12, "type": "text", "markdown": "The sampling theorem limits recoverable frequencies to half the sample rate."},
            {"blockId": "b3", "sourceAnchor": "pdf-1:p20:b3", "page": 20, "type": "text", "markdown": "The appendix lists historical references."},
        ],
    }]
    retrieved = _retrieve_chunks(sections, "What is the sampling limit?", max_chunks=1)
    assert retrieved[0]["blocks"][0]["sourceAnchor"] == "pdf-1:p12:b2"


@pytest.mark.django_db
def test_notebook_rejects_empty_title(client: APIClient) -> None:
    response = client.post("/api/v1/notebooks", {"title": ""}, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_title"


@pytest.mark.django_db
def test_universal_text_reference_and_blank_note_use_the_notebook_runtime(client: APIClient) -> None:
    registered = client.post(
        "/api/v1/auth/register",
        {"email": "context@example.com", "password": "safe-password-123", "displayName": "Context learner"},
        format="json",
    )
    assert registered.status_code == 201
    goal = client.post(
        "/api/v1/goals",
        {"title": "Understand sampling", "description": "Use a source and demonstrate the trade-off.", "outcome": "Explain aliasing", "currentLevel": "beginner", "timeBudget": "Flexible"},
        format="json",
    )
    assert goal.status_code == 201
    notebook = client.post(
        "/api/v1/notebooks",
        {"title": "Sampling references", "goalId": goal.json()["goalId"]},
        format="json",
    )
    assert notebook.status_code == 201
    notebook_id = notebook.json()["notebookId"]

    source = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {
            "title": "Lecture excerpt",
            "sourceKind": "pasted_notes",
            "text": "Sampling stores measurements at regular intervals. Frequencies above half the sample rate can alias.",
            "url": "https://example.edu/sampling",
        },
        format="json",
    )
    assert source.status_code == 201, source.content
    source_body = source.json()
    typed_source = source_body["sources"][0]
    assert typed_source["status"] == "ready"
    assert typed_source["extraction"]["referenceUrl"] == "https://example.edu/sampling"
    assert typed_source["extraction"]["rawRetention"] == "discarded_after_extraction"
    assert typed_source["pageCount"] == 1
    assert typed_source["blockCount"] >= 1
    assert typed_source["anchorIds"]

    private_context = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Private scratch", "text": "This is a personal scratch context, not verification material.", "useForGrounding": False},
        format="json",
    )
    assert private_context.status_code == 201
    private_source = next(item for item in private_context.json()["sources"] if item["title"] == "Private scratch")
    assert private_source["groundingEnabled"] is False
    blocked = client.post(
        f"/api/v1/notebooks/{notebook_id}/ask",
        {"question": "What does the private scratch say?", "sourceIds": [private_source["sourceId"]]},
        format="json",
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "invalid_source_scope"

    blank_note = client.post(f"/api/v1/notebooks/{notebook_id}/notes/blank", {"title": "My scratchpad"}, format="json")
    assert blank_note.status_code == 201
    assert blank_note.json()["content"] == ""

    listed = client.get("/api/v1/notebooks")
    assert listed.status_code == 200
    assert listed.json()["notebooks"][0]["notebookId"] == notebook_id
    dock = client.get(f"/api/v1/goals/{goal.json()['goalId']}/sources")
    assert dock.status_code == 200
    assert dock.json()["notebooks"][0]["sources"][0]["sourceId"] == typed_source["sourceId"]
    assert dock.json()["notebooks"][0]["sources"][0]["anchorIds"]


@pytest.mark.django_db
def test_goal_attached_medical_notebook_declines_personal_decision_requests(client: APIClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "medical-context@example.com", "password": "safe-password-123", "displayName": "Medical learner"},
        format="json",
    )
    assert registration.status_code == 201
    goal = client.post(
        "/api/v1/goals",
        {"title": "Study medical anatomy", "description": "Academic reference study", "outcome": "Explain a mechanism", "currentLevel": "beginner", "timeBudget": "Flexible"},
        format="json",
    )
    notebook = client.post("/api/v1/notebooks", {"title": "Anatomy source", "goalId": goal.json()["goalId"]}, format="json")
    notebook_id = notebook.json()["notebookId"]

    with patch("teachback.notebook_views.answer_notebook_question") as answer:
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/ask",
            {"question": "Can you diagnose my symptoms and tell me what treatment to take?"},
            format="json",
        )
    assert response.status_code == 200
    assert response.json()["groundedIn"] == "educational_boundary"
    assert "cannot diagnose" in response.json()["answer"]
    answer.assert_not_called()
    lesson = client.post(
        f"/api/v1/notebooks/{notebook_id}/lessons",
        {"question": "What treatment should I take for my symptoms?"},
        format="json",
    )
    assert lesson.status_code == 422
    assert lesson.json()["error"]["code"] == "educational_boundary"


@pytest.mark.django_db
@override_settings(MISTRAL_API_KEY="configured-for-test")
def test_mistral_socket_block_falls_back_to_local_extraction(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Offline-safe notebook", "learningGoal": "understand", "ocrProvider": "auto"}, format="json")
    notebook_id = created.json()["notebookId"]
    with patch("teachback.notebook_pipeline._mistral_ocr", side_effect=NotebookExtractionError("Mistral OCR failed: <urlopen error [WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions>")):
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/sources",
            {"file": SimpleUploadedFile("notes.md", b"# Measurement\n\nMeasurement compares an unknown quantity with a known standard.", content_type="text/markdown"), "sourceKind": "reference", "ocrProvider": "auto"},
            format="multipart",
        )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["sources"][0]["extractionMethod"] == "local-fallback-after-mistral-network-error"
    assert "Mistral OCR was unreachable" in body["sources"][0]["extraction"]["warning"]
    assert body["sources"][0]["extraction"]["providerStatus"] == "configured_but_unavailable"
    assert body["sources"][0]["retryAvailable"] is True
    assert body["sources"][0]["retryRequiresReupload"] is True


@pytest.mark.django_db
@override_settings(MISTRAL_API_KEY="configured-for-test")
def test_failed_mistral_source_retry_requires_reupload_and_keeps_no_raw_bytes(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Retryable OCR notebook", "ocrProvider": "mistral"}, format="json")
    notebook_id = created.json()["notebookId"]
    with patch(
        "teachback.notebook_pipeline._mistral_ocr",
        side_effect=NotebookExtractionError("Mistral OCR failed: HTTP Error 401: Unauthorized"),
    ):
        failed = client.post(
            f"/api/v1/notebooks/{notebook_id}/sources",
            {
                "file": SimpleUploadedFile("notes.pdf", _pdf_bytes("A source sentence for OCR retry."), content_type="application/pdf"),
                "ocrProvider": "mistral",
            },
            format="multipart",
        )
    assert failed.status_code == 422
    assert failed.json()["error"]["code"] == "extraction_failed"
    assert failed.json()["providerErrorCategory"] == "authentication"
    source_id = failed.json()["sourceId"]

    notebook = client.get(f"/api/v1/notebooks/{notebook_id}").json()
    source = notebook["sources"][0]
    assert source["sourceId"] == source_id
    assert source["status"] == "failed"
    assert source["extraction"]["rawRetention"] == "discarded_after_extraction"
    assert source["retryAvailable"] is True
    assert source["retryRequiresReupload"] is True
    assert source["assets"] == []

    no_file = client.post(f"/api/v1/notebooks/{notebook_id}/sources/{source_id}/retry", {}, format="multipart")
    assert no_file.status_code == 409
    assert no_file.json()["error"]["code"] == "source_reupload_required"

    mistral_result = {
        "pages": [{
            "index": 0,
            "markdown": "Mistral extracted page text.",
            "blocks": [{"type": "text", "markdown": "Mistral extracted page text."}],
            "images": [],
        }],
        "usage_info": {"pages_processed": 1},
    }
    with patch("teachback.notebook_pipeline._mistral_ocr", return_value=mistral_result):
        retried = client.post(
            f"/api/v1/notebooks/{notebook_id}/sources/{source_id}/retry",
            {
                "file": SimpleUploadedFile("notes.pdf", _pdf_bytes("A source sentence for OCR retry."), content_type="application/pdf"),
                "ocrProvider": "mistral",
            },
            format="multipart",
        )
    assert retried.status_code == 201
    refreshed = next(item for item in retried.json()["sources"] if item["sourceId"] == source_id)
    assert refreshed["status"] == "ready"
    assert refreshed["extractionMethod"] == "mistral-ocr-4-0"
    assert refreshed["extraction"]["rawRetention"] == "discarded_after_extraction"
    assert refreshed["anchorIds"]


@pytest.mark.django_db
def test_openmaic_lesson_route_persists_a_narrated_lesson(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Lesson notebook", "learningGoal": "understand", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    upload = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("notes.md", b"# Measurement\n\nMeasurement compares an unknown quantity with a known standard.", content_type="text/markdown"), "sourceKind": "reference", "ocrProvider": "local"},
        format="multipart",
    )
    assert upload.status_code == 201
    payload = {"kind": "openmaic_lesson", "mode": "openmaic_native", "title": "Measurement lesson", "slides": [{"title": "Definition"}] * 4, "sourceIds": []}
    with patch("teachback.notebook_views.generate_openmaic_lesson", return_value=payload):
        response = client.post(f"/api/v1/notebooks/{notebook_id}/lessons", {"question": "Explain measurement", "allowWebSearch": False}, format="json")
    assert response.status_code == 201
    assert response.json()["type"] == "openmaic_lesson"
    assert response.json()["payload"]["mode"] == "openmaic_native"


def test_live_fireworks_normalizes_every_notebook_artifact_with_saved_citations() -> None:
    """All live artifact families must be model-generated and anchor-bound."""
    pack = {
        "title": "Signals",
        "sources": ["source-1"],
        "sections": [{
            "sectionId": "signals-section",
            "title": "Signals",
            "sourceIds": ["source-1"],
            "pages": [4],
            "blocks": [{
                "blockId": "signal-block-4",
                "sourceAnchor": "source-1:p4:b1",
                "page": 4,
                "type": "text",
                "markdown": "A signal carries information through a system. The relation y = x is used in this example.",
            }],
        }],
        "supplementarySections": [],
        "formulas": [{"formulaId": "formula-1", "text": "y = x", "sectionId": "signals-section", "sourceId": "source-1", "page": 4}],
        "assets": [],
    }
    anchor = "source-1:p4:b1"
    responses = {
        "summary": {"title": "Signal guide", "sections": [{"title": "Signal", "summary": "A signal carries information through a system.", "sourceAnchorIds": [anchor]}]},
        "mcq": {"title": "Signal quiz", "questions": [{"topicTitle": "Signal", "question": "What does the selected source say a signal carries?", "options": ["Information", "Only heat", "Only mass"], "answerIndex": 0, "explanation": "The cited source states that a signal carries information.", "sourceAnchorIds": [anchor]}]},
        "slides": {"title": "Signal slides", "slides": [{"title": "Signal", "body": "A signal carries information through a system.", "bullets": ["Signals carry information."], "sourceAnchorIds": [anchor]}]},
        "formula_sheet": {"title": "Signal formulas", "formulas": [{"text": "y = x", "label": "Example relation", "sourceAnchorIds": [anchor]}]},
        "important_questions": {"title": "Signal questions", "questions": [{"kind": "explain", "question": "Explain what the source means by a signal.", "answerFocus": "State that it carries information through a system.", "sourceAnchorIds": [anchor]}]},
        "flashcards": {"title": "Signal cards", "cards": [{"front": "What does a signal carry?", "back": "Information through a system.", "tag": "RECALL", "sourceAnchorIds": [anchor]}]},
        "mind_map": {"title": "Signal map", "rootLabel": "Signals", "nodes": [{"id": "signal", "label": "Signal", "detail": "Carries information through a system.", "sourceAnchorIds": [anchor]}], "edges": []},
        "data_table": {"title": "Signal table", "rows": [{"topic": "Signal", "keyIdea": "A signal carries information through a system.", "formulas": ["y = x"], "sourceAnchorIds": [anchor]}]},
    }

    class FakeFireworks:
        def __init__(self) -> None:
            self.requests: list[dict] = []

        def generate_notebook_artifact(self, request: dict) -> dict:
            self.requests.append(request)
            return responses[request["artifactType"]]

    provider = FakeFireworks()
    with override_settings(LLM_PROVIDER="fireworks", FIREWORKS_API_KEY="test-only-key", FIREWORKS_MODEL="test-fireworks-model"):
        with patch("teachback.notebook_media.provider_for", return_value=provider):
            for artifact_type, response in responses.items():
                title, payload = generate_notebook_artifact(pack, artifact_type)
                assert title == response["title"]
                assert payload["provenance"] == {
                    "provider": "fireworks",
                    "model": "test-fireworks-model",
                    "status": "completed",
                    "citationValidation": "passed",
                }
                rendered = str(payload)
                assert anchor in rendered
                assert "source-1" in rendered
    assert {request["artifactType"] for request in provider.requests} == set(responses)
    assert all("sourceId=source-1" in request["sourceContext"] for request in provider.requests)
    assert all("page=4" in request["sourceContext"] and "blockId=signal-block-4" in request["sourceContext"] for request in provider.requests)
    formula_request = next(request for request in provider.requests if request["artifactType"] == "formula_sheet")
    assert formula_request["approvedFormulaCandidates"] == ["y = x"]


def test_live_formula_sheet_keeps_an_honest_empty_state_for_non_math_source() -> None:
    pack = {
        "title": "Round robin",
        "sources": ["source-1"],
        "sections": [{
            "sectionId": "scheduler-section",
            "title": "Scheduler notes",
            "sourceIds": ["source-1"],
            "pages": [1],
            "blocks": [{
                "blockId": "scheduler-block-1",
                "sourceAnchor": "source-1:p1:b1",
                "sourceId": "source-1",
                "page": 1,
                "type": "text",
                "markdown": "Round Robin scheduling gives each ready process a fixed time quantum.",
            }],
        }],
        "supplementarySections": [],
        "formulas": [],
        "assets": [],
    }
    captured: dict = {}

    class FakeFireworks:
        def generate_notebook_artifact(self, request: dict) -> dict:
            captured.update(request)
            return {
                "title": "Scheduler formulas",
                "formulas": [{
                    "text": "q = 10ms",
                    "label": "Invented relation",
                    "sourceAnchorIds": ["source-1:p1:b1"],
                }],
            }

    with override_settings(LLM_PROVIDER="fireworks", FIREWORKS_API_KEY="test-only-key", FIREWORKS_MODEL="test-fireworks-model"):
        with patch("teachback.notebook_media.provider_for", return_value=FakeFireworks()):
            title, payload = generate_notebook_artifact(pack, "formula_sheet")

    assert title == "Scheduler formulas"
    assert payload["formulas"] == []
    assert payload["provenance"]["citationValidation"] == "passed"
    assert payload["note"].startswith("No literal equations")
    assert captured["approvedFormulaCandidates"] == []


@pytest.mark.django_db
def test_live_fireworks_artifact_endpoint_is_scoped_and_persists_provenance(client: APIClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "fireworks-artifact@example.com", "password": "safe-password-123", "displayName": "Fireworks artifact learner"},
        format="json",
    )
    assert registration.status_code == 201
    created = client.post("/api/v1/notebooks", {"title": "Scoped Fireworks artifacts", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    first = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Selected source", "text": "A selected signal carries information through a system and is measured against a known standard."},
        format="json",
    )
    assert first.status_code == 201
    first_source = first.json()["sources"][0]
    second = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Unselected source", "text": "Calibration compares an instrument with a separate standard and must remain outside this artifact."},
        format="json",
    )
    assert second.status_code == 201
    second_source_id = next(source["sourceId"] for source in second.json()["sources"] if source["sourceId"] != first_source["sourceId"])
    anchor = first_source["anchorIds"][0]
    captured: dict = {}

    class FakeFireworks:
        def generate_notebook_artifact(self, request: dict) -> dict:
            captured.update(request)
            return {"title": "Selected signal guide", "sections": [{"title": "Selected signal", "summary": "The selected source says a signal carries information through a system.", "sourceAnchorIds": [anchor]}]}

    with override_settings(LLM_PROVIDER="fireworks", FIREWORKS_API_KEY="test-only-key", FIREWORKS_MODEL="test-fireworks-model"):
        with patch("teachback.notebook_media.provider_for", return_value=FakeFireworks()):
            artifact = client.post(
                f"/api/v1/notebooks/{notebook_id}/artifacts",
                {"type": "summary", "sourceIds": [first_source["sourceId"]]},
                format="json",
            )
    assert artifact.status_code == 201, artifact.content
    body = artifact.json()
    assert body["sourceIds"] == [first_source["sourceId"]]
    assert body["provider"] == "fireworks"
    assert body["model"] == "test-fireworks-model"
    assert body["citationValidation"] == "passed"
    assert body["payload"]["sections"][0]["sourceAnchors"] == [anchor]
    assert first_source["sourceId"] in captured["sourceContext"]
    assert "document=Selected source" in captured["sourceContext"]
    assert second_source_id not in captured["sourceContext"]


@pytest.mark.django_db
def test_configured_fireworks_lesson_is_source_scoped_and_persists_provenance(client: APIClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "fireworks-live-lesson@example.com", "password": "safe-password-123", "displayName": "Fireworks live lesson learner"},
        format="json",
    )
    assert registration.status_code == 201
    created = client.post("/api/v1/notebooks", {"title": "Fireworks lesson", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    source = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Lesson source", "text": "A signal carries information through a system and a learner can explain the relationship in their own words."},
        format="json",
    )
    assert source.status_code == 201
    source_payload = source.json()["sources"][0]
    anchor = source_payload["anchorIds"][0]
    captured: dict = {}

    class FakeFireworks:
        def generate_openmaic_lesson(self, request: dict) -> dict:
            captured.update(request)
            return {
                "title": "Signal lesson",
                "slides": [{
                    "slideId": f"signal-{index}",
                    "title": "Signal relationship",
                    "slideLabel": "KEY IDEA",
                    "body": "The selected source says that a signal carries information through a system.",
                    "bullets": ["Signals carry information.", "Explain the relationship in your own words."],
                    "teachingNote": "Connect the claim to the cited source anchor.",
                    "visualKind": "text-note",
                    "narration": "The selected source explains that a signal carries information through a system, so first state the relationship and then explain it in your own words.",
                    "sourceAnchorIds": [anchor],
                    "assetIds": [],
                    "diagram": {"nodes": [], "edges": []},
                    "actions": [{"kind": "reveal", "label": "Reveal the cited definition.", "target": "body"}],
                } for index in range(1, 5)],
            }

    with override_settings(LLM_PROVIDER="fireworks", FIREWORKS_API_KEY="test-only-key", FIREWORKS_MODEL="test-fireworks-model"):
        with patch("teachback.notebook_media.provider_for", return_value=FakeFireworks()):
            lesson = client.post(
                f"/api/v1/notebooks/{notebook_id}/lessons",
                {"question": "Explain the selected signal", "requestedDurationSeconds": 120, "sourceIds": [source_payload["sourceId"]]},
                format="json",
            )
    assert lesson.status_code == 201, lesson.content
    payload = lesson.json()["payload"]
    assert payload["providerId"] == "fireworks"
    assert payload["providerModel"] == "test-fireworks-model"
    assert payload["provenance"]["citationValidation"] == "passed"
    assert all(slide["sourceAnchorIds"] == [anchor] for slide in payload["slides"])
    assert source_payload["sourceId"] in captured["sourceContext"]
    assert captured["webContext"] == ""


@pytest.mark.django_db
def test_configured_fireworks_lesson_failure_never_saves_or_labels_a_local_fallback(client: APIClient) -> None:
    registration = client.post(
        "/api/v1/auth/register",
        {"email": "fireworks-lesson@example.com", "password": "safe-password-123", "displayName": "Fireworks lesson learner"},
        format="json",
    )
    assert registration.status_code == 201
    created = client.post("/api/v1/notebooks", {"title": "Fireworks lesson failure", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    source = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Lesson source", "text": "A signal carries information through a system and the learner should explain the relationship."},
        format="json",
    )
    assert source.status_code == 201

    class UnavailableFireworks:
        def generate_openmaic_lesson(self, request: dict) -> dict:
            raise ProviderUnavailable("timeout")

    with override_settings(LLM_PROVIDER="fireworks", FIREWORKS_API_KEY="test-only-key"):
        with patch("teachback.notebook_media.provider_for", return_value=UnavailableFireworks()):
            lesson = client.post(
                f"/api/v1/notebooks/{notebook_id}/lessons",
                {"question": "Explain the signal source", "requestedDurationSeconds": 120},
                format="json",
            )
    assert lesson.status_code == 503
    failure = lesson.json()
    assert failure["error"]["code"] == "provider_unavailable"
    assert failure["retryAvailable"] is True
    assert failure["retryAction"] == "generate_lesson"
    assert client.get(f"/api/v1/notebooks/{notebook_id}/artifacts").json()["artifacts"] == []


def test_mcq_builder_uses_a_concept_claim_not_a_document_heading() -> None:
    _, payload = build_artifact_payload({
        "sections": [
            {"sectionId": "cover", "title": "INSTRUMENTATION (II/II)", "sourceIds": ["source-1"], "pages": [1], "blocks": [{"type": "title", "markdown": "# INSTRUMENTATION (II/II)"}]},
            {"sectionId": "topic-1", "title": "Instrumentation System", "sourceIds": ["source-1"], "pages": [2], "blocks": [{"type": "text", "markdown": "An instrumentation system measures physical quantities and converts them into readable and usable signals.", "sourceAnchor": "source-1:p2"}]},
        ],
        "formulas": [],
    }, "mcq")
    assert len(payload["questions"]) == 1
    question = payload["questions"][0]
    assert question["question"] == "Which statement correctly describes an instrumentation system?"
    assert question["options"][question["answerIndex"]].startswith("An instrumentation system measures")
    assert all("INSTRUMENTATION (II/II)" not in option for option in question["options"])
    assert all("It is unrelated" not in option for option in question["options"])


def test_component_mcq_uses_parallel_source_terms_for_distractors() -> None:
    _, payload = build_artifact_payload({
        "sections": [
            {"sectionId": "components", "title": "Instrumentation System", "sourceIds": ["source-1"], "pages": [1], "blocks": [{"type": "text", "markdown": "Some of the components of Instrumentation Systems: Sensors/Transducers, Signal Conditioning, Data Acquisition System (DAS), Control Units, Communication, and Data Display and Analysis.", "sourceAnchor": "source-1:p1"}]},
            {"sectionId": "related", "title": "Microprocessor", "sourceIds": ["source-1"], "pages": [2], "blocks": [{"type": "text", "markdown": "A microprocessor system includes Microprocessor, I/O devices, Memory, and Control Units.", "sourceAnchor": "source-1:p2"}]},
        ],
        "formulas": [],
    }, "mcq")
    question = payload["questions"][0]
    assert question["questionType"] == "components_list"
    assert question["question"].startswith("Which list matches the source's stated components")
    assert len(question["options"]) == 4
    assert all("used only to store data" not in option for option in question["options"])
    assert all("guessing a result" not in option for option in question["options"])
    assert len(set(question["options"])) == 4


def test_compact_instrumentation_ocr_is_repaired_before_outputs_are_built() -> None:
    sections = [
        {
            "sectionId": "analog", "title": "Analog Instrument", "sourceIds": ["source-1"], "pages": [9],
            "blocks": [{"type": "text", "markdown": "Ananaloginstrumentdisplaysmeasurementresultseitherasa waveform orthroughthemovementofapointer acrossascale.", "sourceAnchor": "source-1:p9"}],
        },
        {
            "sectionId": "benefits", "title": "Microprocessor-Based Instrumentation Benefits", "sourceIds": ["source-1"], "pages": [33],
            "blocks": [{"type": "text", "markdown": "Completeautomationandintelligencetosomeextend. -Redesignflexibilityduetoprogrammability. -Economicandreducedcomplexity. -reducedoperatingcosts. -Higheraccuracyofcontrolenforcement -timelyandaccurateinformationenablesoperatorsforefficient plantrunning.", "sourceAnchor": "source-1:p33"}],
        },
        {
            "sectionId": "design", "title": "Microcomputer on Instrumentation Design", "sourceIds": ["source-1"], "pages": [35],
            "blocks": [{"type": "text", "markdown": "Aprocessorplantmayhavetomeasuremultiplevariables simultaneously: pressure, temperature, velocity, viscosity, flowrateetc. -computerbasedsystemcanprocessallinputsorvariablesin realtimesimultaneously. -computerormicroprocessorisfedwithasequenceof instructionsknownascomputerprogramforprocessingor manipulationofdata. programmedtocarryoutthetasksuchasnoisereduction,gain adjustmentetcautomatically.", "sourceAnchor": "source-1:p35"}],
        },
    ]
    _, slides = build_artifact_payload({"sections": sections, "formulas": []}, "slides")
    benefit_slide = next(slide for slide in slides["slides"] if slide["title"] == "Microprocessor-Based Instrumentation Benefits")
    design_slide = next(slide for slide in slides["slides"] if slide["title"] == "Microcomputer on Instrumentation Design")
    benefit_text = " ".join([benefit_slide["body"], *benefit_slide["bullets"]])
    design_text = " ".join([design_slide["body"], *design_slide["bullets"]])
    assert "Complete automation and intelligence to some extent" in benefit_text
    assert "A process plant may have to measure multiple variables simultaneously" in design_text
    assert "A computer-based system can process all input variables simultaneously in real time" in design_text
    assert all(len(slide["bullets"]) <= 4 for slide in slides["slides"])

    _, mcq = build_artifact_payload({"sections": sections, "formulas": []}, "mcq")
    analog_question = next(question for question in mcq["questions"] if question["sourceAnchors"] == ["source-1:p9"])
    assert analog_question["options"][analog_question["answerIndex"]] == "As a waveform or by a pointer moving across a scale."
    assert all("an digital instrument" not in option.lower() for option in analog_question["options"])
    assert len({option.casefold() for option in analog_question["options"]}) == 4
    assert all(question["questionType"] != "components_list" for question in mcq["questions"] if question["sourceAnchors"] != ["source-1:p9"])


def test_repeated_microcomputer_running_header_starts_a_new_topic() -> None:
    parsed = _inline_ocr_heading(
        "Microcomputer on instrumentation design Microcomputer on Instrumentation System. "
        "A process plant may have to measure multiple variables simultaneously."
    )
    assert parsed == (
        "Microcomputer on Instrumentation Design",
        "A process plant may have to measure multiple variables simultaneously.",
    )


def test_microprocessor_features_and_control_questions_stay_on_topic() -> None:
    sections = [
        {
            "sectionId": "features", "title": "Microprocessor-Based System Features", "sourceIds": ["source-1"], "pages": [27],
            "blocks": [{"type": "text", "markdown": "Microprocessor, I/Odevices, and Memory. Decisionmakingpowerbasedonsetvalue. Datastorage, retrievalandtransmission. Effectivecontrolofmultipleequipmentontimesharingbasis.", "sourceAnchor": "source-1:p27"}],
        },
        {
            "sectionId": "control", "title": "Microprocessor Based Control System", "sourceIds": ["source-1"], "pages": [28],
            "blocks": [{"type": "text", "markdown": "Open Loopcontrolsystem Closed Loopcontrolsystem Open Loop Control System. Dependinguponthecontroloutputfrommicroprocessor, operatormakesthechangestocontrolinput. Closed Loop Control System -continuousmonitoringofprocessvariables -outputsignaltocontrolsystemorunits. Analog(pressure)signalisconvertedtodigitalformandfed tomicroprocessor.", "sourceAnchor": "source-1:p28"}],
        },
    ]
    pack = {"sections": sections, "formulas": []}
    _, flashcards = build_artifact_payload(pack, "flashcards")
    rendered_cards = " ".join(card["back"] for card in flashcards["cards"])
    assert "Decision-making power based on set values." in rendered_cards
    assert "Data storage, retrieval, and transmission." in rendered_cards
    assert "open-loop control system, the operator changes the control input" in rendered_cards

    _, mcq = build_artifact_payload(pack, "mcq")
    questions = mcq["questions"]
    feature_question = next(item for item in questions if item["topicTitle"] == "Microprocessor-Based System Features")
    control_question = next(item for item in questions if item["topicTitle"] == "Microprocessor Based Control System")
    assert feature_question["options"][feature_question["answerIndex"]] in {"Preset or set values.", "Data storage, retrieval, and transmission."}
    assert control_question["options"][control_question["answerIndex"]] in {"The operator.", "Continuous monitoring of process variables with an output signal to the control system.", "It is converted to digital form and fed to the microprocessor."}


def test_retrieval_outputs_keep_coverage_when_topic_prompts_repeat() -> None:
    sections = [
        {
            "sectionId": "processor-control", "title": "Microprocessor-Based Instrumentation", "sourceIds": ["source-1"], "pages": [1],
            "blocks": [{"type": "text", "markdown": "A microprocessor receives sensor data and controls pump speed when the measured pressure exceeds a limit. It improves control accuracy in the instrumentation system.", "sourceAnchor": "source-1:p1"}],
        },
        {
            "sectionId": "processor-cost", "title": "Benefits of Using a Microprocessor", "sourceIds": ["source-1"], "pages": [2],
            "blocks": [{"type": "text", "markdown": "A microprocessor simplifies design and reduces operating cost. It processes measured inputs according to a stored program before issuing a control decision.", "sourceAnchor": "source-1:p2"}],
        },
        {
            "sectionId": "processor-display", "title": "Microcomputer on Instrumentation Design", "sourceIds": ["source-1"], "pages": [3],
            "blocks": [{"type": "text", "markdown": "A microcomputer processes multiple sensor inputs in real time and presents timely information to the operator. It can automatically adjust gain after processing the measurement signal.", "sourceAnchor": "source-1:p3"}],
        },
    ]
    pack = {"sections": sections, "formulas": []}
    _, flashcards = build_artifact_payload(pack, "flashcards")
    cards = flashcards["cards"]
    assert len(cards) >= 6
    assert len({card["front"] for card in cards}) < len(cards)
    assert len({(card["front"], card["back"]) for card in cards}) == len(cards)

    _, mcq = build_artifact_payload(pack, "mcq")
    questions = mcq["questions"]
    assert len(questions) >= 6
    assert any(question["questionType"] == "retrieval_transfer" for question in questions)
    assert all(len(question["options"]) == 4 for question in questions)
    assert all(question["options"][question["answerIndex"]] in question["explanation"] for question in questions)


def test_important_questions_use_a_concrete_application_context() -> None:
    _, payload = build_artifact_payload({
        "sections": [{
            "sectionId": "error-section", "title": "Summary of Error", "sourceIds": ["source-1"], "pages": [12],
            "blocks": [{"type": "text", "markdown": "Random error is caused by unknown variations and is reduced using statistical analysis.", "sourceAnchor": "source-1:p12"}],
        }],
        "formulas": [],
    }, "important_questions")
    apply_question = next(item for item in payload["questions"] if item["kind"] == "apply")
    assert "different readings" in apply_question["question"]
    assert "error type" in apply_question["question"]
    assert "statistical" in apply_question["answerFocus"].lower()
    assert apply_question["sourceAnchors"] == ["source-1:p12"]


def test_slide_payload_carries_teaching_note_and_only_structural_diagram() -> None:
    _, payload = build_artifact_payload({
        "sections": [
            {"sectionId": "definition", "title": "Theory of Measurement", "sourceIds": ["source-1"], "pages": [1], "blocks": [{"type": "text", "markdown": "Measurement compares an unknown quantity with a standard known quantity.", "sourceAnchor": "source-1:p1"}]},
            {"sectionId": "digital", "title": "Digital Instrument", "sourceIds": ["source-1"], "pages": [2], "blocks": [{"type": "text", "markdown": "A digital instrument converts the measured signal into a numerical display through signal processing and an ADC.", "sourceAnchor": "source-1:p2"}]},
        ],
        "formulas": [],
    }, "slides")
    assert payload["slides"][0]["visualKind"] == "text-note"
    assert payload["slides"][0]["teachingNote"]
    assert payload["slides"][1]["visualKind"] == "teaching-diagram"
    assert payload["slides"][1]["diagram"]["nodes"]


def _pdf_bytes(text: str) -> bytes:
    """Create a tiny text PDF without adding a production-only dependency."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=220, height=220)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    resources = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    page[NameObject("/Resources")] = resources
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 120 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.django_db
def test_pdf_context_persists_and_chat_is_scoped_to_selected_source(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Durable PDF notebook", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    first = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("first.pdf", _pdf_bytes("Alpha measurement context. Measurement is a comparison between an unknown quantity and a known standard."), content_type="application/pdf"), "ocrProvider": "local"},
        format="multipart",
    )
    assert first.status_code == 201
    first_source = first.json()["sources"][0]["sourceId"]
    second = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("second.pdf", _pdf_bytes("Beta calibration context. Calibration is the process used to compare an instrument with a standard."), content_type="application/pdf"), "ocrProvider": "local"},
        format="multipart",
    )
    assert second.status_code == 201
    second_source = next(item["sourceId"] for item in second.json()["sources"] if item["sourceId"] != first_source)

    reloaded = client.get(f"/api/v1/notebooks/{notebook_id}")
    assert reloaded.status_code == 200
    assert first_source in reloaded.json()["knowledgePack"]["sources"]
    assert "Alpha measurement context" in reloaded.json()["knowledgePackMarkdown"]

    with patch("teachback.notebook_views.answer_notebook_question", return_value={
        "answer": "Alpha is the selected source.",
        "sourceIds": [first_source, second_source],
        "sourceAnchorIds": [],
        "groundedIn": "notebook",
    }) as answer:
        response = client.post(
            f"/api/v1/notebooks/{notebook_id}/ask",
            {"question": "What does Alpha say?", "sourceIds": [first_source]},
            format="json",
        )
    assert response.status_code == 200
    assert response.json()["sourceIds"] == [first_source]
    scoped_pack = answer.call_args.args[0]
    assert scoped_pack["sources"] == [first_source]
    history = client.get(f"/api/v1/notebooks/{notebook_id}/chat").json()["messages"]
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert history[-1]["sourceIds"] == [first_source]


@pytest.mark.django_db
def test_source_deletion_rebuilds_memory_and_marks_dependent_output_stale(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Source removal", "ocrProvider": "local"}, format="json")
    notebook_id = created.json()["notebookId"]
    uploaded = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources",
        {"file": SimpleUploadedFile("notes.md", b"# Signal\n\nA signal carries information.", content_type="text/markdown"), "ocrProvider": "local"},
        format="multipart",
    )
    source_id = uploaded.json()["sources"][0]["sourceId"]
    artifact = client.post(f"/api/v1/notebooks/{notebook_id}/artifacts", {"type": "summary", "sourceIds": [source_id]}, format="json")
    assert artifact.status_code == 201
    with patch("teachback.notebook_views.answer_notebook_question", return_value={
        "answer": "A signal carries information.",
        "sourceIds": [source_id],
        "sourceAnchorIds": [],
        "groundedIn": "notebook",
    }):
        answer = client.post(f"/api/v1/notebooks/{notebook_id}/ask", {"question": "What is a signal?", "sourceIds": [source_id]}, format="json")
    assert answer.status_code == 200

    removed = client.delete(f"/api/v1/notebooks/{notebook_id}/sources/{source_id}")
    assert removed.status_code == 200
    body = removed.json()
    assert body["knowledgePack"]["sources"] == []
    assert body["status"] == "collecting"
    assert body["artifacts"][0]["status"] == "stale"
    assert body["artifacts"][0]["payload"]["invalidated"] is True
    history = client.get(f"/api/v1/notebooks/{notebook_id}/chat").json()["messages"]
    assert all(message["status"] == "stale" for message in history)
    assert all(message["sourceIds"] == [] for message in history)
    assert all("signal" not in message["content"].casefold() for message in history)


@pytest.mark.django_db
def test_notebook_notes_are_persistent_and_editable(client: APIClient) -> None:
    created = client.post("/api/v1/notebooks", {"title": "Notes notebook"}, format="json")
    notebook_id = created.json()["notebookId"]
    note = client.post(
        f"/api/v1/notebooks/{notebook_id}/notes",
        {"title": "My takeaway", "content": "Explain the source in my own words."},
        format="json",
    )
    assert note.status_code == 201
    note_id = note.json()["noteId"]
    updated = client.patch(f"/api/v1/notebooks/{notebook_id}/notes/{note_id}", {"content": "A better explanation."}, format="json")
    assert updated.status_code == 200
    assert updated.json()["content"] == "A better explanation."
    assert client.get(f"/api/v1/notebooks/{notebook_id}/notes").json()["notes"][0]["noteId"] == note_id
    assert client.delete(f"/api/v1/notebooks/{notebook_id}/notes/{note_id}").status_code == 204


def test_mind_map_and_data_table_keep_source_anchors() -> None:
    pack = {
        "title": "Signals",
        "sections": [{
            "sectionId": "signal", "title": "Signal", "sourceIds": ["source-1"], "pages": [1],
            "blocks": [{"type": "text", "markdown": "A signal carries information through a system.", "sourceAnchor": "source-1:p1"}],
        }],
        "formulas": [{"formulaId": "formula-1", "text": "y = x", "sectionId": "signal", "sourceId": "source-1", "page": 1}],
    }
    _, mind_map = build_artifact_payload(pack, "mind_map")
    _, table = build_artifact_payload(pack, "data_table")
    assert mind_map["kind"] == "mind_map"
    assert mind_map["nodes"][1]["sourceAnchors"] == ["source-1:p1"]
    assert table["kind"] == "data_table"
    assert table["rows"][0]["formulas"] == ["y = x"]
