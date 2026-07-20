"""Acceptance coverage for the role-aware Feynman Learning OS surface."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

from teachback.models import Course, Enrollment, LearnerProfile, Membership, Organization, ShareGrant, SourcePack
from teachback.providers import ProviderUnavailable


def _register(client: APIClient, email: str, name: str = "Learner") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        {"email": email, "password": "safe-password-123", "displayName": name},
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


def _goal(client: APIClient, title: str, **extra: str) -> dict:
    response = client.post(
        "/api/v1/goals",
        {
            "title": title,
            "description": "I want a durable mental model, a concrete application, and an explanation I can defend.",
            "outcome": "Explain and apply the idea",
            "currentLevel": "beginner",
            "timeBudget": "A few focused sessions each week",
            **extra,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()


@pytest.mark.django_db
def test_goal_without_optional_description_keeps_contract_brief_non_empty() -> None:
    client = APIClient()
    _register(client, "brief-fallback@example.com")

    response = client.post(
        "/api/v1/goals",
        {"title": "Learn digital signal processing", "currentLevel": "beginner"},
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["contract"]["brief"] == "Learn digital signal processing"


@pytest.mark.django_db
def test_goal_contract_records_observed_and_source_backed_verified_evidence() -> None:
    client = APIClient()
    _register(client, "learner@example.com")

    goal = _goal(client, "Learn operating-system scheduling")
    assert goal["status"] == "contract_ready"
    assert goal["contract"]["firstTask"]
    assert [activity["type"] for activity in goal["activities"]] == ["predict", "explain", "derive", "simulate", "debug", "apply", "build", "transfer"]

    confirmed = client.patch(f"/api/v1/goals/{goal['goalId']}", {"confirmContract": True}, format="json")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "active"

    observed = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {"activityId": goal["activities"][0]["activityId"], "response": "I predict an interactive process should receive service quickly because response time affects what a person experiences. I would compare the queue trace and state the uncertainty around fairness."},
        format="json",
    )
    assert observed.status_code == 200
    assert observed.json()["evidence"]["status"] == "observed"
    assert observed.json()["goal"]["evidenceCount"] == 1

    academic = _goal(client, "Study medical anatomy from academic references")
    assert academic["sourceMode"] == "required"
    notebook = client.post(
        "/api/v1/notebooks",
        {"title": "Academic anatomy references", "goalId": academic["goalId"]},
        format="json",
    )
    assert notebook.status_code == 201
    uploaded = client.post(
        f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources",
        {
            "file": SimpleUploadedFile(
                "anatomy.md",
                b"# Anatomy\n\nAcademic anatomy explains structures, their relationships, and observable functions.",
                content_type="text/markdown",
            )
        },
        format="multipart",
    )
    assert uploaded.status_code == 201
    source_id = uploaded.json()["sources"][0]["sourceId"]
    source_dock = client.get(f"/api/v1/goals/{academic['goalId']}/sources")
    assert source_dock.status_code == 200
    source_summary = source_dock.json()["notebooks"][0]["sources"][0]
    assert source_summary["sourceId"] == source_id
    anchor_id = source_summary["anchorIds"][0]
    invalid_anchor = client.post(
        f"/api/v1/goals/{academic['goalId']}/attempts",
        {
            "activityId": academic["activities"][0]["activityId"],
            "response": "The anatomy mechanism can be explained from the supplied academic material by naming the relevant structure, its relationship to nearby structures, the observable function, and the limitation of applying this educational explanation to an individual patient.",
            "sourceAnchorIds": ["notes:p4"],
        },
        format="json",
    )
    assert invalid_anchor.status_code == 422
    assert invalid_anchor.json()["error"]["code"] == "invalid_source_anchor"
    verified = client.post(
        f"/api/v1/goals/{academic['goalId']}/attempts",
        {"activityId": academic["activities"][0]["activityId"], "response": "The anatomy mechanism can be explained from the supplied academic material by naming the relevant structure, its relationship to nearby structures, the observable function, and the limitation of applying this educational explanation to an individual patient.", "sourceIds": [source_id], "sourceAnchorIds": [anchor_id]},
        format="json",
    )
    assert verified.status_code == 200
    assert verified.json()["evidence"]["status"] == "verified"
    assert verified.json()["evidence"]["sourceAnchorIds"] == [anchor_id]
    assert verified.json()["evidence"]["sourceIds"] == [source_id]


@pytest.mark.django_db
def test_configured_fireworks_activity_feedback_is_source_scoped_and_persists_provenance() -> None:
    client = APIClient()
    _register(client, "fireworks-activity@example.com")
    goal = _goal(client, "Explain source-bounded signal sampling")
    notebook = client.post("/api/v1/notebooks", {"title": "Signal notes", "goalId": goal["goalId"]}, format="json")
    assert notebook.status_code == 201
    notebook_id = notebook.json()["notebookId"]
    selected = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Selected sampling source", "text": "Sampling at a rate above twice the highest frequency avoids aliasing in the bounded signal.", "useForGrounding": True},
        format="json",
    )
    assert selected.status_code == 201
    selected_source = selected.json()["sources"][0]
    unselected = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Unselected source", "text": "This unrelated ready source must not be included in the evaluator request.", "useForGrounding": True},
        format="json",
    )
    assert unselected.status_code == 201

    captured: dict = {}

    class FakeFireworks:
        mode = "live_fireworks"

        def evaluate_checkpoint(self, request):
            captured.update(request)
            return {
                "state": "complete",
                "correct": True,
                "understandingScore": 87,
                "overconfidence": False,
                "feedback": "Your explanation correctly connects the sampling boundary to aliasing.",
                "remediation": "",
                "mistake": "",
                "correctAnswer": "Sampling above twice the highest frequency avoids aliasing for the bounded signal.",
                "correction": "",
                "nextAction": "advance",
                "sourceAnchorIds": [selected_source["anchorIds"][0]],
                "retryPrompt": None,
                "retryOptions": None,
                "retryResponseType": None,
                "retrySourceAnchorIds": [],
                "providerMode": "live_fireworks",
            }

    with override_settings(FIREWORKS_API_KEY="configured-for-test"):
        with patch("teachback.learning_os_views.provider_for", return_value=FakeFireworks()):
            response = client.post(
                f"/api/v1/goals/{goal['goalId']}/attempts",
                {
                    "activityId": goal["activities"][0]["activityId"],
                    "response": "I predict that a component above the sampling boundary can be represented as a lower frequency after sampling. The selected source says that sampling at more than twice the highest frequency avoids that ambiguity, so I would compare the original and sampled signals before claiming reconstruction is reliable.",
                    "sourceIds": [selected_source["sourceId"]],
                    "sourceAnchorIds": [selected_source["anchorIds"][0]],
                    "confidence": 3,
                },
                format="json",
            )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["evidence"]["status"] == "verified"
    assert body["feedback"]["providerAttempt"] == "completed"
    assert body["feedback"]["model"]
    assert body["feedback"]["evaluation"]["sourceAnchorIds"] == [selected_source["anchorIds"][0]]
    assert body["evidence"]["rubric"]["providerAttempt"] == "completed"
    assert body["evidence"]["rubric"]["providerFeedback"]["understandingScore"] == 87
    spans = captured["manifest"]["sourceSpans"]
    assert spans
    assert {span["sourceId"] for span in spans} == {selected_source["sourceId"]}
    assert {span["sourceAnchorId"] for span in spans} == {selected_source["anchorIds"][0]}
    assert all("unrelated ready source" not in span["text"] for span in spans)


@pytest.mark.django_db
def test_configured_fireworks_failure_records_attempt_but_never_verifies_evidence() -> None:
    client = APIClient()
    _register(client, "fireworks-failure@example.com")
    goal = _goal(client, "Explain a source-bounded scheduler")
    notebook = client.post("/api/v1/notebooks", {"title": "Scheduler notes", "goalId": goal["goalId"]}, format="json")
    source = client.post(
        f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text",
        {"title": "Scheduler source", "text": "A scheduler selects runnable processes using a bounded policy and trades response time against fairness.", "useForGrounding": True},
        format="json",
    )
    assert source.status_code == 201
    source_row = source.json()["sources"][0]

    with override_settings(FIREWORKS_API_KEY="configured-for-test"):
        with patch("teachback.learning_os_views.provider_for", side_effect=ProviderUnavailable("request timed out")):
            response = client.post(
                f"/api/v1/goals/{goal['goalId']}/attempts",
                {
                    "activityId": goal["activities"][0]["activityId"],
                    "response": "The scheduler source explains that the policy chooses runnable processes and must balance response time with fairness. I would trace a queue, compare which process waits, state the trade-off, and test whether a changed policy improves one goal while harming the other.",
                    "sourceIds": [source_row["sourceId"]],
                    "sourceAnchorIds": [source_row["anchorIds"][0]],
                },
                format="json",
            )
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["status"] != "verified"
    assert body["evidence"]["rubric"]["providerAttempt"] == "failed"
    assert body["evidence"]["rubric"]["providerErrorCategory"] == "timeout"
    assert body["feedback"]["retryAvailable"] is True
    assert body["feedback"]["retryAction"] == "resubmit_attempt"
    assert "not verified" in body["evidence"]["summary"].lower()


@pytest.mark.django_db
def test_contract_overrides_drive_the_first_task_and_runtime_source_requirement() -> None:
    client = APIClient()
    _register(client, "contract-editor@example.com")
    created = client.post(
        "/api/v1/goals",
        {
            "title": "Understand sampling",
            "description": "I want to reason about signal reconstruction.",
            "outcome": "Explain aliasing",
            "currentLevel": "beginner",
            "timeBudget": "Flexible",
            "contract": {
                "intendedCapability": "Predict and explain aliasing in a bounded signal case",
                "learnerStartingPoint": "intermediate",
                "timeBudget": "Three focused sessions",
                "prerequisites": ["Read a waveform", "Explain sampling rate"],
                "confidence": "uncertain",
                "sourceRequirements": "Use a lecture reference before claiming verification.",
                "safetyMode": "guided",
                "verificationMode": "source_backed",
                "firstTask": "Predict what folds into the baseband when the sampling rate is too low.",
                "learnerCorrection": "Keep the route focused on a signal example.",
                "brief": "Use one source-grounded case.",
            },
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    goal = created.json()
    assert goal["outcome"] == "Predict and explain aliasing in a bounded signal case"
    assert goal["currentLevel"] == "intermediate"
    assert goal["sourceMode"] == "required"
    assert goal["contract"]["sourceRequirements"] == "A selected ready source and durable anchor are required before an attempt can be verified."
    assert goal["contract"]["prerequisites"] == ["Read a waveform", "Explain sampling rate"]
    assert goal["activities"][0]["prompt"] == goal["contract"]["firstTask"]
    assert goal["activities"][0]["prerequisites"] == goal["contract"]["prerequisites"]
    assert goal["activities"][0]["evaluator"]["requiresSource"] is True

    bypass = client.patch(f"/api/v1/goals/{goal['goalId']}", {"sourceMode": "optional"}, format="json")
    assert bypass.status_code == 422
    assert bypass.json()["error"]["code"] == "source_mode_required"

    corrected = client.patch(
        f"/api/v1/goals/{goal['goalId']}",
        {
            "contract": {
                "safetyMode": "academic_source_bound",
                "firstTask": "Use a cited source to predict aliasing in a sampled waveform.",
            }
        },
        format="json",
    )
    assert corrected.status_code == 200
    assert corrected.json()["sourceMode"] == "required"
    assert corrected.json()["activities"][0]["evaluator"]["requiresSource"] is True
    assert corrected.json()["activities"][0]["prompt"] == "Use a cited source to predict aliasing in a sampled waveform."

    medical = _goal(client, "Study medical anatomy from academic references")
    unsafe_relaxation = client.patch(
        f"/api/v1/goals/{medical['goalId']}",
        {"contract": {"safetyMode": "guided"}},
        format="json",
    )
    assert unsafe_relaxation.status_code == 422
    assert unsafe_relaxation.json()["error"]["code"] == "safety_mode_required"


@pytest.mark.django_db
def test_ready_anchored_source_verifies_a_general_goal_and_personal_advice_is_not_evidence() -> None:
    client = APIClient()
    _register(client, "anchored-general@example.com")
    goal = _goal(client, "Understand sampling and aliasing")
    notebook = client.post("/api/v1/notebooks", {"title": "Sampling notes", "goalId": goal["goalId"]}, format="json")
    assert notebook.status_code == 201
    source = client.post(
        f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/text",
        {"title": "Sampling reference", "sourceKind": "pasted_notes", "text": "Sampling records a continuous signal at intervals. Frequencies above half the sampling rate can alias into lower frequencies.", "useForGrounding": True},
        format="json",
    )
    assert source.status_code == 201
    dock = client.get(f"/api/v1/goals/{goal['goalId']}/sources")
    source_summary = dock.json()["notebooks"][0]["sources"][0]
    verified = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": goal["activities"][0]["activityId"],
            "response": "If the sampling rate is too low, a high frequency can be represented as a lower frequency after sampling. I would compare the original waveform and the sampled trace, name the Nyquist boundary, explain the ambiguity, and use the cited note before asserting that the reconstruction is correct.",
            "sourceIds": [source_summary["sourceId"]],
            "sourceAnchorIds": [source_summary["anchorIds"][0]],
        },
        format="json",
    )
    assert verified.status_code == 200
    assert verified.json()["evidence"]["status"] == "verified"

    medical = _goal(client, "Study medical anatomy from academic references")
    medical_notebook = client.post("/api/v1/notebooks", {"title": "Anatomy notes", "goalId": medical["goalId"]}, format="json")
    medical_source = client.post(
        f"/api/v1/notebooks/{medical_notebook.json()['notebookId']}/sources/text",
        {"title": "Anatomy reference", "sourceKind": "pasted_notes", "text": "Academic anatomy describes structures and observable functions.", "useForGrounding": True},
        format="json",
    )
    assert medical_source.status_code == 201
    medical_dock = client.get(f"/api/v1/goals/{medical['goalId']}/sources")
    medical_summary = medical_dock.json()["notebooks"][0]["sources"][0]
    blocked = client.post(
        f"/api/v1/goals/{medical['goalId']}/attempts",
        {
            "activityId": medical["activities"][0]["activityId"],
            "response": "I would diagnose my rash from this anatomy source and tell myself what treatment to take. The source contains academic facts, but I would turn those facts into a personal clinical decision for my own symptoms, which is what I need this task to decide.",
            "sourceIds": [medical_summary["sourceId"]],
            "sourceAnchorIds": [medical_summary["anchorIds"][0]],
        },
        format="json",
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "educational_boundary"
    assert client.get(f"/api/v1/evidence?goalId={medical['goalId']}").json()["evidence"] == []


@pytest.mark.django_db
def test_course_sharing_is_explicit_and_revoke_removes_instructor_access() -> None:
    instructor = APIClient()
    _register(instructor, "teacher@example.com", "Teacher")
    workspace = instructor.post("/api/v1/workspaces", {"name": "Systems Institute", "kind": "institution"}, format="json")
    assert workspace.status_code == 201
    course = instructor.post(
        "/api/v1/courses",
        {"workspaceId": workspace.json()["workspaceId"], "title": "Systems studio", "description": "Trace mechanisms", "status": "published"},
        format="json",
    )
    assert course.status_code == 201, course.content
    course_payload = course.json()

    learner = APIClient()
    _register(learner, "student@example.com", "Student")
    joined = learner.post("/api/v1/courses/join", {"joinCode": course_payload["joinCode"]}, format="json")
    assert joined.status_code == 201, joined.content

    goal = _goal(learner, "Understand OS process states", courseId=course_payload["courseId"])
    attempt = learner.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {"activityId": goal["activities"][0]["activityId"], "response": "A process state tells us what can happen next. I would trace ready, running, and blocked transitions in a concrete scheduler case, then compare the impact on response time and CPU utilization."},
        format="json",
    )
    assert attempt.status_code == 200
    evidence_id = attempt.json()["evidence"]["evidenceId"]

    before_share = instructor.get(f"/api/v1/courses/{course_payload['courseId']}/cohort")
    assert before_share.status_code == 200
    assert before_share.json()["learners"][0]["sharedEvidence"] == []

    share = learner.post("/api/v1/shares", {"courseId": course_payload["courseId"], "evidenceIds": [evidence_id]}, format="json")
    assert share.status_code == 201, share.content

    after_share = instructor.get(f"/api/v1/courses/{course_payload['courseId']}/cohort")
    assert after_share.status_code == 200
    assert "learnerId" not in after_share.json()["learners"][0]
    assert after_share.json()["learners"][0]["sharedEvidence"][0]["evidenceId"] == evidence_id

    revoked = learner.delete(f"/api/v1/shares/{share.json()['shareId']}")
    assert revoked.status_code == 200
    after_revoke = instructor.get(f"/api/v1/courses/{course_payload['courseId']}/cohort")
    assert after_revoke.json()["learners"][0]["sharedEvidence"] == []


@pytest.mark.django_db
def test_workspace_invitation_assigns_a_role_only_to_the_invited_account() -> None:
    owner = APIClient()
    _register(owner, "invite-owner@example.com", "Workspace owner")
    workspace = owner.post("/api/v1/workspaces", {"name": "Invitation Institute", "kind": "institution"}, format="json")
    assert workspace.status_code == 201
    invited = owner.post(
        f"/api/v1/organizations/{workspace.json()['workspaceId']}/members",
        {"email": "invite-instructor@example.com", "role": "instructor"},
        format="json",
    )
    assert invited.status_code == 201
    token = invited.json()["token"]
    invitation = APIClient().get(f"/api/v1/invites/{token}")
    assert invitation.status_code == 200
    assert invitation.json()["role"] == "instructor"

    intruder = APIClient()
    _register(intruder, "invite-intruder@example.com", "Wrong account")
    assert intruder.post(f"/api/v1/invites/{token}", format="json").status_code == 403

    instructor = APIClient()
    _register(instructor, "invite-instructor@example.com", "Invited instructor")
    accepted = instructor.post(f"/api/v1/invites/{token}", format="json")
    assert accepted.status_code == 200
    assert accepted.json()["workspace"]["role"] == "instructor"
    course = instructor.post(
        "/api/v1/courses",
        {"workspaceId": workspace.json()["workspaceId"], "title": "Invited instructor course", "status": "draft"},
        format="json",
    )
    assert course.status_code == 201
    assert course.json()["canManage"] is True
    assert course.json()["canReviewCohort"] is True


@pytest.mark.django_db
def test_course_context_requires_membership_and_course_lists_do_not_leak_other_courses() -> None:
    instructor = APIClient()
    _register(instructor, "course-context-teacher@example.com", "Course teacher")
    workspace = instructor.post("/api/v1/workspaces", {"name": "Context Institute", "kind": "institution"}, format="json")
    assert workspace.status_code == 201
    joined_course = instructor.post(
        "/api/v1/courses",
        {"workspaceId": workspace.json()["workspaceId"], "title": "Context studio", "status": "published"},
        format="json",
    )
    hidden_course = instructor.post(
        "/api/v1/courses",
        {"workspaceId": workspace.json()["workspaceId"], "title": "Instructor draft", "status": "draft"},
        format="json",
    )
    assert joined_course.status_code == 201
    assert hidden_course.status_code == 201

    learner = APIClient()
    _register(learner, "course-context-learner@example.com", "Course learner")
    joined = learner.post("/api/v1/courses/join", {"joinCode": joined_course.json()["joinCode"]}, format="json")
    assert joined.status_code == 201

    attached = learner.post(
        "/api/v1/notebooks",
        {"title": "Course-local sources", "courseId": joined_course.json()["courseId"]},
        format="json",
    )
    assert attached.status_code == 201, attached.content
    assert attached.json()["courseId"] == joined_course.json()["courseId"]
    assert attached.json()["workspaceId"] == workspace.json()["workspaceId"]

    listed = learner.get("/api/v1/courses")
    assert listed.status_code == 200
    assert [course["courseId"] for course in listed.json()["courses"]] == [joined_course.json()["courseId"]]
    assert listed.json()["courses"][0]["canManage"] is False
    assert listed.json()["courses"][0]["canReviewCohort"] is False

    personal_goal = _goal(learner, "Trace a private scheduler")
    mismatch = learner.post(
        "/api/v1/notebooks",
        {"title": "Invalid mixed context", "goalId": personal_goal["goalId"], "courseId": joined_course.json()["courseId"]},
        format="json",
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "course_goal_mismatch"
    mismatch_attach = learner.post(
        f"/api/v1/goals/{personal_goal['goalId']}/sources",
        {"notebookId": attached.json()["notebookId"]},
        format="json",
    )
    assert mismatch_attach.status_code == 422
    assert mismatch_attach.json()["error"]["code"] == "course_goal_mismatch"

    outsider = APIClient()
    _register(outsider, "course-context-outsider@example.com", "Outside learner")
    forbidden = outsider.post(
        "/api/v1/notebooks",
        {"title": "Unjoined course source", "courseId": joined_course.json()["courseId"]},
        format="json",
    )
    assert forbidden.status_code == 403

    course_model = Course.objects.get(course_id=joined_course.json()["courseId"])
    outsider_profile = LearnerProfile.objects.get(account__username="course-context-outsider@example.com")
    Membership.objects.create(organization=course_model.organization, user=outsider_profile.account, role="instructor")
    cross_course_instructor = outsider.post(
        "/api/v1/notebooks",
        {"title": "Other instructor source", "courseId": joined_course.json()["courseId"]},
        format="json",
    )
    assert cross_course_instructor.status_code == 403
    assert outsider.get(f"/api/v1/courses/{joined_course.json()['courseId']}/cohort").status_code == 403
    assert outsider.get("/api/v1/courses").json()["courses"] == []

    administrator = APIClient()
    _register(administrator, "course-context-admin@example.com", "Institution admin")
    admin_profile = LearnerProfile.objects.get(account__username="course-context-admin@example.com")
    Membership.objects.create(organization=course_model.organization, user=admin_profile.account, role="institution_admin")
    assert administrator.get(f"/api/v1/courses/{joined_course.json()['courseId']}/cohort").status_code == 403
    admin_course = administrator.get(f"/api/v1/courses/{joined_course.json()['courseId']}")
    assert admin_course.status_code == 200
    assert admin_course.json()["canManage"] is True
    assert admin_course.json()["canReviewCohort"] is False

    managed = instructor.post(
        "/api/v1/notebooks",
        {"title": "Instructor course source", "courseId": joined_course.json()["courseId"]},
        format="json",
    )
    assert managed.status_code == 201
    assert managed.json()["courseId"] == joined_course.json()["courseId"]
    instructor_course = instructor.get(f"/api/v1/courses/{joined_course.json()['courseId']}")
    assert instructor_course.status_code == 200
    assert instructor_course.json()["canManage"] is True
    assert instructor_course.json()["canReviewCohort"] is True


@pytest.mark.django_db
def test_teach_dashboard_only_counts_shared_evidence_and_own_course_source_governance() -> None:
    instructor = APIClient()
    _register(instructor, "dashboard-teacher@example.com", "Dashboard teacher")
    workspace = instructor.post("/api/v1/workspaces", {"name": "Dashboard Institute", "kind": "institution"}, format="json")
    course = instructor.post(
        "/api/v1/courses",
        {"workspaceId": workspace.json()["workspaceId"], "title": "Dashboard studio", "status": "published"},
        format="json",
    )
    assert course.status_code == 201

    learner = APIClient()
    _register(learner, "dashboard-learner@example.com", "Dashboard learner")
    assert learner.post("/api/v1/courses/join", {"joinCode": course.json()["joinCode"]}, format="json").status_code == 201
    goal = _goal(learner, "Trace process states", courseId=course.json()["courseId"])
    attempt = learner.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": goal["activities"][0]["activityId"],
            "response": "I would trace the state transition and explain why it changes.",
        },
        format="json",
    )
    assert attempt.status_code == 200
    assert attempt.json()["evidence"]["status"] == "needs_review"
    evidence_id = attempt.json()["evidence"]["evidenceId"]

    course_model = Course.objects.get(course_id=course.json()["courseId"])
    own_unapproved = SourcePack.objects.create(lesson_id="dashboard-own-unapproved", title="Own pending pack", approved=False)
    course_model.source_packs.add(own_unapproved)
    foreign_workspace = Organization.objects.create(name="Foreign Institute", kind="institution")
    foreign_course = Course.objects.create(organization=foreign_workspace, title="Foreign studio")
    foreign_unapproved = SourcePack.objects.create(lesson_id="dashboard-foreign-unapproved", title="Foreign pending pack", approved=False)
    foreign_course.source_packs.add(foreign_unapproved)

    before_share = instructor.get("/api/v1/teach/dashboard")
    assert before_share.status_code == 200
    assert before_share.json()["pendingReviews"] == 0
    assert before_share.json()["sourceApprovalNeeded"] == 1

    share = learner.post(
        "/api/v1/shares",
        {"courseId": course.json()["courseId"], "evidenceIds": [evidence_id]},
        format="json",
    )
    assert share.status_code == 201
    after_share = instructor.get("/api/v1/teach/dashboard")
    assert after_share.json()["pendingReviews"] == 1

    assert learner.delete(f"/api/v1/shares/{share.json()['shareId']}").status_code == 200
    after_revoke = instructor.get("/api/v1/teach/dashboard")
    assert after_revoke.json()["pendingReviews"] == 0


@pytest.mark.django_db
def test_owned_notebook_is_private_but_legacy_uuid_notebooks_stay_compatible() -> None:
    owner = APIClient()
    _register(owner, "owner@example.com", "Owner")
    created = owner.post("/api/v1/notebooks", {"title": "Private DSP notes"}, format="json")
    assert created.status_code == 201
    notebook_id = created.json()["notebookId"]
    assert owner.get(f"/api/v1/notebooks/{notebook_id}").status_code == 200

    other = APIClient()
    _register(other, "other@example.com", "Other")
    assert other.get(f"/api/v1/notebooks/{notebook_id}").status_code == 404

    legacy = APIClient().post("/api/v1/notebooks", {"title": "Legacy source desk"}, format="json")
    assert legacy.status_code == 201
    assert APIClient().get(f"/api/v1/notebooks/{legacy.json()['notebookId']}").status_code == 200


def test_local_cors_allows_the_frontend_origin_and_rejects_unknown_origins() -> None:
    client = APIClient()

    allowed = client.options(
        "/api/v1/goals",
        HTTP_ORIGIN="http://127.0.0.1:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken",
    )
    assert allowed.status_code == 204
    assert allowed["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
    assert "X-CSRFToken" in allowed["Access-Control-Allow-Headers"]

    denied = client.options(
        "/api/v1/goals",
        HTTP_ORIGIN="https://untrusted.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
    )
    assert denied.status_code == 204
    assert "Access-Control-Allow-Origin" not in denied


@pytest.mark.django_db
def test_session_csrf_bootstrap_protects_authenticated_mutations_without_blocking_auth() -> None:
    client = APIClient(enforce_csrf_checks=True)
    _register(client, "csrf@example.com", "CSRF learner")

    payload = {
        "title": "Trace a scheduler",
        "description": "I want to trace a concrete scheduler case and explain why its behavior changes.",
        "outcome": "Trace and compare a scheduler",
        "currentLevel": "beginner",
        "timeBudget": "Two focused sessions",
    }
    denied = client.post("/api/v1/goals", payload, format="json")
    assert denied.status_code == 403

    bootstrap = client.get("/api/v1/auth/csrf")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["csrfToken"]
    assert client.cookies.get("csrftoken")

    allowed = client.post(
        "/api/v1/goals",
        payload,
        format="json",
        HTTP_X_CSRFTOKEN=bootstrap.json()["csrfToken"],
    )
    assert allowed.status_code == 201, allowed.content

    logout_without_token = client.post("/api/v1/auth/logout", format="json")
    assert logout_without_token.status_code == 403
    logout = client.post(
        "/api/v1/auth/logout",
        format="json",
        HTTP_X_CSRFTOKEN=bootstrap.json()["csrfToken"],
    )
    assert logout.status_code == 200

    # Login begins unauthenticated, so it remains usable before a CSRF token is
    # available; authenticated mutations above still require the token.
    login = client.post(
        "/api/v1/auth/login",
        {"email": "csrf@example.com", "password": "safe-password-123"},
        format="json",
    )
    assert login.status_code == 200


@pytest.mark.django_db
def test_source_deletion_invalidates_linked_evidence_and_activity_scope() -> None:
    client = APIClient()
    _register(client, "source-owner@example.com", "Source owner")
    goal = _goal(client, "Study medical anatomy from academic references")
    notebook = client.post(
        "/api/v1/notebooks",
        {"title": "Anatomy source desk", "goalId": goal["goalId"]},
        format="json",
    )
    assert notebook.status_code == 201
    uploaded = client.post(
        f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources",
        {
            "file": SimpleUploadedFile(
                "anatomy.md",
                b"# Anatomy\n\nA structure has a location, relationship, and observable function in the academic source.",
                content_type="text/markdown",
            )
        },
        format="multipart",
    )
    assert uploaded.status_code == 201
    source_id = uploaded.json()["sources"][0]["sourceId"]
    source_dock = client.get(f"/api/v1/goals/{goal['goalId']}/sources")
    assert source_dock.status_code == 200
    anchor_id = source_dock.json()["notebooks"][0]["sources"][0]["anchorIds"][0]

    evidence = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": goal["activities"][0]["activityId"],
            "response": "The source identifies a structure, its relationship to nearby structures, and its observable function. I would use that relationship to explain a bounded academic case, state what I am uncertain about, and avoid turning the source into advice for an individual patient.",
            "sourceIds": [source_id],
            "sourceAnchorIds": [anchor_id],
        },
        format="json",
    )
    assert evidence.status_code == 200
    assert evidence.json()["evidence"]["status"] == "verified"

    removed = client.delete(f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources/{source_id}")
    assert removed.status_code == 200
    timeline = client.get(f"/api/v1/evidence?goalId={goal['goalId']}")
    assert timeline.status_code == 200
    invalidated = timeline.json()["evidence"][0]
    assert invalidated["status"] == "needs_review"
    assert invalidated["sourceAnchorIds"] == []
    assert invalidated["sourceIds"] == []
    assert invalidated["rubric"]["sourceVerificationState"] == "invalidated"

    route = client.get(f"/api/v1/goals/{goal['goalId']}/route")
    assert route.status_code == 200
    activity = route.json()["activities"][0]
    assert activity["sourceIds"] == []
    assert activity["status"] == "needs_source"


@pytest.mark.django_db
def test_goal_source_dock_excludes_other_learners_notebooks() -> None:
    owner = APIClient()
    _register(owner, "dock-owner@example.com", "Owner")
    goal = _goal(owner, "Trace an operating-system scheduler")
    notebook = owner.post(
        "/api/v1/notebooks",
        {"title": "Owned source desk"},
        format="json",
    )
    assert notebook.status_code == 201
    uploaded = owner.post(
        f"/api/v1/notebooks/{notebook.json()['notebookId']}/sources",
        {
            "file": SimpleUploadedFile(
                "scheduler.md",
                b"# Scheduler\n\nA scheduler selects a runnable process according to a bounded policy.",
                content_type="text/markdown",
            )
        },
        format="multipart",
    )
    assert uploaded.status_code == 201
    attached = owner.post(
        f"/api/v1/goals/{goal['goalId']}/sources",
        {"notebookId": notebook.json()["notebookId"]},
        format="json",
    )
    assert attached.status_code == 200
    assert attached.json()["notebooks"][0]["notebookId"] == notebook.json()["notebookId"]
    assert attached.json()["notebooks"][0]["sources"][0]["anchorIds"]

    other = APIClient()
    _register(other, "dock-other@example.com", "Other")
    assert other.get(f"/api/v1/goals/{goal['goalId']}/sources").status_code == 404


@pytest.mark.django_db
def test_goal_source_dock_shows_owned_source_states_and_safe_artifact_metadata() -> None:
    client = APIClient()
    _register(client, "dock-state-owner@example.com", "Dock owner")
    goal = _goal(client, "Understand DSP sampling")
    notebook = client.post("/api/v1/notebooks", {"title": "Sampling context", "goalId": goal["goalId"]}, format="json")
    assert notebook.status_code == 201
    notebook_id = notebook.json()["notebookId"]

    ready = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Grounding source", "sourceKind": "pasted_notes", "text": "Sampling at a sufficiently high rate preserves a bounded signal representation.", "useForGrounding": True},
        format="json",
    )
    view_only = client.post(
        f"/api/v1/notebooks/{notebook_id}/sources/text",
        {"title": "Personal view-only note", "sourceKind": "typed_text", "text": "This note should remain visible but excluded from grounded answers.", "useForGrounding": False},
        format="json",
    )
    assert ready.status_code == 201
    assert view_only.status_code == 201
    ready_source_id = next(item["sourceId"] for item in view_only.json()["sources"] if item["groundingEnabled"])
    artifact = client.post(
        f"/api/v1/notebooks/{notebook_id}/artifacts",
        {"type": "summary", "sourceIds": [ready_source_id]},
        format="json",
    )
    assert artifact.status_code == 201

    dock = client.get(f"/api/v1/goals/{goal['goalId']}/sources")
    assert dock.status_code == 200
    source_rows = dock.json()["notebooks"][0]["sources"]
    assert {row["title"] for row in source_rows} == {"Grounding source", "Personal view-only note"}
    assert next(row for row in source_rows if row["title"] == "Personal view-only note")["groundingEnabled"] is False
    artifact_row = dock.json()["notebooks"][0]["artifacts"][0]
    assert artifact_row["artifactId"] == artifact.json()["artifactId"]
    assert artifact_row["sourceIds"] == [ready_source_id]
    assert "payload" not in artifact_row

    invalid_scope = client.post(
        f"/api/v1/goals/{goal['goalId']}/attempts",
        {
            "activityId": goal["activities"][0]["activityId"],
            "response": "This response tries to claim grounding from a view-only note even though that note was intentionally excluded from verification and the selected source scope.",
            "sourceIds": [next(row["sourceId"] for row in source_rows if row["title"] == "Personal view-only note")],
        },
        format="json",
    )
    assert invalid_scope.status_code == 422
    assert invalid_scope.json()["error"]["code"] == "invalid_source_scope"


@pytest.mark.django_db
def test_privacy_patch_can_revoke_all_course_shares() -> None:
    client = APIClient()
    _register(client, "privacy@example.com", "Private learner")
    profile = LearnerProfile.objects.get(account__username="privacy@example.com")
    workspace = Organization.objects.create(name="Privacy institution", kind="institution")
    course = Course.objects.create(organization=workspace, title="Privacy course")
    Enrollment.objects.create(course=course, profile=profile)
    grant = ShareGrant.objects.create(profile=profile, course=course, evidence_ids=["evidence-placeholder"])

    response = client.patch("/api/v1/privacy", {"courseSharingEnabled": False}, format="json")
    assert response.status_code == 200
    assert response.json()["courseSharingEnabled"] is False
    assert response.json()["activeShares"] == 0
    grant.refresh_from_db()
    assert grant.active is False

    blocked = client.post(
        "/api/v1/shares",
        {"courseId": str(course.course_id), "evidenceIds": ["evidence-placeholder"]},
        format="json",
    )
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "course_sharing_disabled"
