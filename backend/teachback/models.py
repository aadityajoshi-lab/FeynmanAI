from django.conf import settings
from django.db import models
import uuid


class SourcePack(models.Model):
    lesson_id = models.CharField(max_length=120, unique=True)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=80, default="1.0.0")
    source_url = models.URLField(blank=True)
    license_text = models.CharField(max_length=240, blank=True)
    approved = models.BooleanField(default=True)
    spans = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class StudySource(models.Model):
    """An uploaded or linked source retained as a reviewable draft asset."""

    source_id = models.CharField(max_length=160, unique=True)
    subject_id = models.SlugField(max_length=100, blank=True)
    module_id = models.SlugField(max_length=120, blank=True)
    title = models.CharField(max_length=240)
    source_kind = models.CharField(max_length=32, default="document")
    filename = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=40, default="awaiting_approval")
    approval_status = models.CharField(max_length=40, default="instructor_review_required")
    extraction = models.JSONField(default=dict, blank=True)
    candidates = models.JSONField(default=list, blank=True)
    pipeline = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Notebook(models.Model):
    """A durable, source-first workspace for a learner's materials."""

    notebook_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=240)
    subject = models.CharField(max_length=240, blank=True)
    description = models.TextField(blank=True)
    learning_goal = models.CharField(max_length=40, default="understand")
    status = models.CharField(max_length=32, default="draft")
    ocr_provider = models.CharField(max_length=80, default="local_fallback")
    # Existing notebooks intentionally remain readable by UUID while they are
    # unclaimed. New notebooks are always owned by a learner/workspace.
    owner_profile = models.ForeignKey("LearnerProfile", on_delete=models.SET_NULL, null=True, blank=True, related_name="notebooks")
    workspace = models.ForeignKey("Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="notebooks")
    goal = models.ForeignKey("LearningGoal", on_delete=models.SET_NULL, null=True, blank=True, related_name="notebooks")
    course = models.ForeignKey("Course", on_delete=models.SET_NULL, null=True, blank=True, related_name="notebooks")
    knowledge_pack = models.JSONField(default=dict, blank=True)
    knowledge_pack_markdown = models.TextField(blank=True)
    stats = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotebookSource(models.Model):
    """One source inside a notebook and the structured extraction from it."""

    source_id = models.CharField(max_length=160, unique=True)
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="notebook_sources")
    title = models.CharField(max_length=240)
    source_kind = models.CharField(max_length=40, default="reference")
    filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=32, default="queued")
    grounding_enabled = models.BooleanField(default=True)
    extraction_method = models.CharField(max_length=80, default="local")
    extraction = models.JSONField(default=dict, blank=True)
    blocks = models.JSONField(default=list, blank=True)
    assets = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class NotebookArtifact(models.Model):
    """A reproducible learner output generated from a notebook knowledge pack."""

    artifact_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="artifacts")
    artifact_type = models.CharField(max_length=40)
    title = models.CharField(max_length=240)
    status = models.CharField(max_length=32, default="ready")
    payload = models.JSONField(default=dict, blank=True)
    source_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotebookChatMessage(models.Model):
    """A durable, notebook-scoped chat transcript with its evidence trail."""

    message_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=16)
    content = models.TextField()
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    grounded_in = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, default="ready")
    # Provider provenance is retained with the assistant turn so a learner can
    # distinguish a source excerpt/recovery state from a real model response.
    provider_name = models.CharField(max_length=80, blank=True)
    provider_model = models.CharField(max_length=200, blank=True)
    provider_error_category = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class NotebookNote(models.Model):
    """A learner-authored note that can retain links to notebook evidence."""

    note_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=240)
    content = models.TextField(max_length=12000)
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]


class SubjectPack(models.Model):
    """Versioned, publishable subject configuration independent of a lesson."""
    subject_id = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Module(models.Model):
    subject_pack = models.ForeignKey(SubjectPack, on_delete=models.CASCADE, related_name="modules")
    module_id = models.SlugField(max_length=120)
    title = models.CharField(max_length=240)
    summary = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["subject_pack", "module_id"], name="unique_subject_module")]
        ordering = ["position", "id"]


class Concept(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="concepts")
    concept_id = models.SlugField(max_length=160)
    title = models.CharField(max_length=240)
    prompt = models.TextField()
    learning_goal = models.TextField(blank=True)
    learning_mode = models.CharField(max_length=40, default="guided")
    skill_ids = models.JSONField(default=list, blank=True)
    source_pack = models.ForeignKey(SourcePack, on_delete=models.SET_NULL, null=True, blank=True, related_name="concepts")
    version = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["module", "concept_id"], name="unique_module_concept")]
        ordering = ["id"]


class LearnerProfile(models.Model):
    profile_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    anonymous_key = models.CharField(max_length=128, unique=True)
    account = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="feynman_profile")
    # Clerk's stable subject is the account identity. Email remains profile
    # data and is never used as the primary external identity.
    clerk_user_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    workspace = models.ForeignKey("Organization", on_delete=models.SET_NULL, null=True, blank=True, related_name="learner_profiles")
    display_name = models.CharField(max_length=120, blank=True)
    preferences = models.JSONField(default=dict, blank=True)
    memory_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SkillEvidence(models.Model):
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="skills")
    subject_id = models.SlugField(max_length=100)
    skill_id = models.SlugField(max_length=160)
    status = models.CharField(max_length=32, default="emerging")
    mastery_score = models.FloatField(default=0.0)
    evidence_count = models.PositiveIntegerField(default=0)
    recent_signal = models.CharField(max_length=80, blank=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "subject_id", "skill_id"], name="unique_profile_skill")]


class LearnerMemory(models.Model):
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="memory_items")
    key = models.SlugField(max_length=160)
    kind = models.CharField(max_length=40, default="preference")
    content = models.TextField(max_length=4000)
    enabled = models.BooleanField(default=True)
    consented = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "key"], name="unique_profile_memory_key")]


class LearningAttempt(models.Model):
    """Anonymous subject attempt; its JSON record is versioned and append-only."""
    attempt_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="attempts")
    goal = models.ForeignKey("LearningGoal", on_delete=models.SET_NULL, null=True, blank=True, related_name="attempts")
    activity = models.ForeignKey("LearningActivity", on_delete=models.SET_NULL, null=True, blank=True, related_name="attempts")
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name="attempts")
    concept = models.ForeignKey(Concept, on_delete=models.PROTECT, null=True, blank=True, related_name="attempts")
    learner_text = models.TextField(max_length=12000, blank=True)
    learning_mode = models.CharField(max_length=40, default="guided")
    state = models.CharField(max_length=40, default="draft")
    record_version = models.PositiveIntegerField(default=1)
    record = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AttemptCheckpoint(models.Model):
    attempt = models.ForeignKey(LearningAttempt, on_delete=models.CASCADE, related_name="checkpoints")
    checkpoint_id = models.SlugField(max_length=120)
    kind = models.CharField(max_length=40, default="teach_back")
    state = models.CharField(max_length=40, default="pending")
    payload = models.JSONField(default=dict, blank=True)
    response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "checkpoint_id"], name="unique_attempt_checkpoint")]



class LearningSession(models.Model):
    STATUS_CHOICES = [(x, x) for x in ("draft", "auditing", "ready", "needs_human_review")]
    lesson_id = models.CharField(max_length=120)
    learner_text = models.TextField(max_length=12000)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    provider_mode = models.CharField(max_length=32, default="codex_fixture")
    record_version = models.PositiveIntegerField(default=0)
    client_request_id = models.CharField(max_length=160, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Claim(models.Model):
    VERDICTS = [(x, x) for x in ("supported", "misconception", "needs_precision", "needs_human_review")]
    MISCONCEPTIONS = [(x, x) for x in ("source_of_matter", "causal_mechanism", "terminology")]
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="claims")
    claim_id = models.CharField(max_length=120)
    learner_text = models.TextField(max_length=6000)
    verdict = models.CharField(max_length=32, choices=VERDICTS)
    misconception_type = models.CharField(max_length=40, choices=MISCONCEPTIONS, blank=True, null=True)
    probe = models.TextField(max_length=2000, blank=True)
    source_anchor_ids = models.JSONField(default=list)
    revision_count = models.PositiveIntegerField(default=0)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["session", "claim_id"], name="unique_session_claim")]
        ordering = ["position", "id"]


class AuditRun(models.Model):
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="audits")
    provider_mode = models.CharField(max_length=32)
    status = models.CharField(max_length=32)
    schema_version = models.CharField(max_length=40, default="audit.v1")
    errors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class Clarification(models.Model):
    STATUS_CHOICES = [(x, x) for x in ("pending", "answered", "abstained", "needs_human_review")]
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="clarifications")
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="clarifications")
    question = models.TextField(max_length=4000)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    answer = models.TextField(blank=True)
    source_anchor_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class Revision(models.Model):
    session = models.ForeignKey(LearningSession, on_delete=models.CASCADE, related_name="revisions")
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name="revisions")
    old_text = models.TextField(max_length=6000)
    new_text = models.TextField(max_length=6000)
    old_verdict = models.CharField(max_length=32)
    new_verdict = models.CharField(max_length=32)
    warning = models.CharField(max_length=240, blank=True)
    record_version = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class Organization(models.Model):
    """A personal or institutional workspace that owns Feynman learning data."""

    organization_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=180)
    kind = models.CharField(max_length=32, default="institution")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="owned_feynman_organizations")
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Membership(models.Model):
    ROLE_CHOICES = [(role, role) for role in ("owner", "institution_admin", "instructor", "learner")]
    STATUS_CHOICES = [(state, state) for state in ("active", "invited", "suspended")]

    membership_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feynman_memberships")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default="learner")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "user"], name="unique_organization_member")]


class OrganizationInvitation(models.Model):
    """An invite is durable so the UI can show pending access without email infrastructure."""

    invitation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=32, choices=Membership.ROLE_CHOICES, default="learner")
    token = models.CharField(max_length=64, unique=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=24, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)


class Course(models.Model):
    """An instructor-owned route inside an organization workspace."""

    course_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="courses")
    instructor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="feynman_courses")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    join_code = models.CharField(max_length=24, unique=True, blank=True)
    status = models.CharField(max_length=32, default="draft")
    route = models.JSONField(default=dict, blank=True)
    source_policy = models.JSONField(default=dict, blank=True)
    source_packs = models.ManyToManyField(SourcePack, blank=True, related_name="courses")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)


class Enrollment(models.Model):
    STATUS_CHOICES = [(state, state) for state in ("active", "invited", "withdrawn")]

    enrollment_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="active")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "profile"], name="unique_course_enrollment")]


class LearningGoal(models.Model):
    """A learner-owned capability target, independent of a fixed subject taxonomy."""

    goal_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="goals")
    workspace = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name="goals")
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name="goals")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    domain = models.CharField(max_length=80, default="general")
    outcome = models.CharField(max_length=500, blank=True)
    current_level = models.CharField(max_length=40, default="beginner")
    time_budget = models.CharField(max_length=80, blank=True)
    source_mode = models.CharField(max_length=40, default="optional")
    safety_mode = models.CharField(max_length=40, default="guided")
    verification_mode = models.CharField(max_length=40, default="guided")
    status = models.CharField(max_length=32, default="draft")
    contract = models.JSONField(default=dict, blank=True)
    route = models.JSONField(default=dict, blank=True)
    next_action = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class LearningActivity(models.Model):
    ACTIVITY_TYPES = [(item, item) for item in ("predict", "explain", "compare", "derive", "debug", "analyze", "simulate", "apply", "build", "transfer", "remediate")]

    activity_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name="activities")
    activity_type = models.CharField(max_length=32, choices=ACTIVITY_TYPES, default="explain")
    title = models.CharField(max_length=240)
    prompt = models.TextField()
    position = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=32, default="ready")
    # A versioned, domain-neutral contract.  The canvas renders this object;
    # it is intentionally richer than a prompt so interaction evidence can be
    # evaluated without letting a provider invent a mastery decision.
    configuration = models.JSONField(default=dict, blank=True)
    difficulty = models.PositiveSmallIntegerField(default=1)
    remediation_target = models.CharField(max_length=240, blank=True)
    transfer_target = models.CharField(max_length=240, blank=True)
    prerequisites = models.JSONField(default=list, blank=True)
    source_ids = models.JSONField(default=list, blank=True)
    evaluator = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "id"]


class EvidenceRecord(models.Model):
    STATUS_CHOICES = [(state, state) for state in ("observed", "verified", "needs_review", "rejected")]

    evidence_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="evidence_records")
    goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name="evidence_records")
    activity = models.ForeignKey(LearningActivity, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidence_records")
    capability = models.CharField(max_length=240)
    evidence_type = models.CharField(max_length=40, default="explanation")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="observed")
    score = models.FloatField(null=True, blank=True)
    summary = models.TextField()
    rubric = models.JSONField(default=dict, blank=True)
    transition_reason = models.CharField(max_length=240, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ActivityAttempt(models.Model):
    """Append-only observable work submitted through the shared activity runtime.

    Raw notebook material never belongs here: this record holds only learner
    inputs, deterministic interaction output, and references to selected
    source identifiers/anchors.
    """

    attempt_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="activity_attempts")
    goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name="activity_attempts")
    activity = models.ForeignKey(LearningActivity, on_delete=models.CASCADE, related_name="activity_attempts")
    written_explanation = models.TextField(max_length=12000, blank=True)
    learner_conclusion = models.TextField(max_length=4000, blank=True)
    confidence = models.PositiveSmallIntegerField(null=True, blank=True)
    prediction = models.JSONField(default=dict, blank=True)
    interaction_state = models.JSONField(default=dict, blank=True)
    selected_options = models.JSONField(default=list, blank=True)
    calculations = models.JSONField(default=dict, blank=True)
    trace = models.JSONField(default=list, blank=True)
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    evaluation = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CapabilityState(models.Model):
    """Learner-owned adaptive state for a capability within one goal."""

    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="capability_states")
    goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name="capability_states")
    capability = models.CharField(max_length=240)
    status = models.CharField(max_length=40, default="emerging")
    confidence = models.PositiveSmallIntegerField(null=True, blank=True)
    misconceptions = models.JSONField(default=list, blank=True)
    completed_attempt_ids = models.JSONField(default=list, blank=True)
    retry_history = models.JSONField(default=list, blank=True)
    current_route_position = models.PositiveIntegerField(default=1)
    next_action = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "goal", "capability"], name="unique_goal_capability_state")]


class CurriculumPack(models.Model):
    """A source-scoped curriculum proposal compiled for one learning goal."""

    STATUS_CHOICES = [(state, state) for state in ("draft", "ready", "stale", "provider_failed", "needs_review")]

    pack_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name="curriculum_packs")
    domain = models.CharField(max_length=120, default="general")
    learner_level = models.CharField(max_length=40, default="beginner")
    safety_mode = models.CharField(max_length=40, default="guided")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="draft")
    version = models.PositiveIntegerField(default=1)
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    source_fingerprint = models.CharField(max_length=128, blank=True)
    uncertainty = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    compiler_mode = models.CharField(max_length=40, default="deterministic_fallback")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-version", "-created_at"]


class CurriculumVersion(models.Model):
    """Immutable compiler output metadata for stale-source detection."""

    STATUS_CHOICES = [(state, state) for state in ("active", "superseded", "stale")]

    curriculum = models.ForeignKey(CurriculumPack, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="active")
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    source_fingerprint = models.CharField(max_length=128, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    uncertainty = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["curriculum", "version"], name="unique_curriculum_version")]


class ConceptNode(models.Model):
    """A cited concept in a compiled curriculum graph."""

    curriculum = models.ForeignKey(CurriculumVersion, on_delete=models.CASCADE, related_name="concepts")
    node_key = models.SlugField(max_length=160)
    title = models.CharField(max_length=240)
    explanation = models.TextField(max_length=4000, blank=True)
    position = models.PositiveIntegerField(default=0)
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    uncertainty = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["curriculum", "node_key"], name="unique_curriculum_concept")]
        ordering = ["position", "id"]


class PrerequisiteEdge(models.Model):
    """Directed prerequisite relationship: prerequisite must precede dependent."""

    curriculum = models.ForeignKey(CurriculumVersion, on_delete=models.CASCADE, related_name="prerequisite_edges")
    prerequisite = models.ForeignKey(ConceptNode, on_delete=models.CASCADE, related_name="outgoing_prerequisites")
    dependent = models.ForeignKey(ConceptNode, on_delete=models.CASCADE, related_name="incoming_prerequisites")
    relation = models.CharField(max_length=80, default="required_before")
    confidence = models.FloatField(default=0.5)
    source_anchor_ids = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["curriculum", "prerequisite", "dependent"], name="unique_prerequisite_edge")]


class ActivityDefinition(models.Model):
    """Compiler-owned activity contract used to materialize the shared canvas."""

    curriculum = models.ForeignKey(CurriculumVersion, on_delete=models.CASCADE, related_name="activity_definitions")
    concept = models.ForeignKey(ConceptNode, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_definitions")
    activity_type = models.CharField(max_length=40, default="explain")
    title = models.CharField(max_length=240)
    prompt = models.TextField(max_length=4000)
    position = models.PositiveIntegerField(default=0)
    difficulty = models.PositiveSmallIntegerField(default=1)
    configuration = models.JSONField(default=dict, blank=True)
    expected_observations = models.JSONField(default=list, blank=True)
    source_ids = models.JSONField(default=list, blank=True)
    source_anchor_ids = models.JSONField(default=list, blank=True)
    remediation_target = models.TextField(max_length=1000, blank=True)
    transfer_target = models.TextField(max_length=1000, blank=True)
    safety_mode = models.CharField(max_length=40, default="guided")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]


class EvaluationRubric(models.Model):
    """Strict evaluator requirements attached to a compiled activity."""

    activity = models.OneToOneField(ActivityDefinition, on_delete=models.CASCADE, related_name="rubric")
    version = models.PositiveIntegerField(default=1)
    criteria = models.JSONField(default=list, blank=True)
    required_fields = models.JSONField(default=list, blank=True)
    source_requirements = models.JSONField(default=dict, blank=True)
    uncertainty = models.JSONField(default=dict, blank=True)


class GoalCurriculumRoute(models.Model):
    """Stable linkage from an existing goal route to a compiled curriculum."""

    goal = models.OneToOneField(LearningGoal, on_delete=models.CASCADE, related_name="curriculum_route")
    curriculum = models.ForeignKey(CurriculumVersion, on_delete=models.SET_NULL, null=True, blank=True, related_name="goal_routes")
    state = models.CharField(max_length=32, default="active")
    active_activity = models.ForeignKey(ActivityDefinition, on_delete=models.SET_NULL, null=True, blank=True, related_name="active_goal_routes")
    current_position = models.PositiveIntegerField(default=1)
    route = models.JSONField(default=dict, blank=True)
    next_action = models.CharField(max_length=120, default="start_activity")
    invalid_reason = models.CharField(max_length=240, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class ShareGrant(models.Model):
    """Explicit, revocable learner consent for a course to inspect evidence."""

    share_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="share_grants")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="share_grants")
    evidence_ids = models.JSONField(default=list, blank=True)
    scope = models.CharField(max_length=80, default="selected_evidence")
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GoalShare(models.Model):
    """A revocable, snapshot-based share of a learning route template.

    The snapshot contains the goal contract, activity configurations, and
    source metadata needed to start fresh. It deliberately excludes attempts,
    evidence, private notebook blocks, and learner memory.
    """

    share_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    goal = models.ForeignKey(LearningGoal, on_delete=models.CASCADE, related_name="goal_shares")
    profile = models.ForeignKey(LearnerProfile, on_delete=models.CASCADE, related_name="goal_shares")
    snapshot = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
