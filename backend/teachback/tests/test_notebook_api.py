import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from teachback.notebook_pipeline import NotebookExtractionError, _inline_ocr_heading, build_artifact_payload


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

    answer = client.post(f"/api/v1/notebooks/{notebook_id}/ask", {"question": "What is measurement?"}, format="json")
    assert answer.status_code == 200
    assert "Measurement" in answer.json()["answer"]


@pytest.mark.django_db
def test_notebook_rejects_empty_title(client: APIClient) -> None:
    response = client.post("/api/v1/notebooks", {"title": ""}, format="json")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "missing_title"


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
