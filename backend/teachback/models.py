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
