from django.urls import path
from .dynamic_views import (
    AnonymousLearnerView, AttemptClarificationView, AttemptInspectionView, AttemptLearningModeView, AttemptRecordView,
    AttemptRevisionView, CheckpointView, LearnerMemoryExportView, LearnerMemoryView, LearnerPreferencesView,
    LearnerProfileView, ModuleAttemptsView, ModuleDetailView, ModuleManifestView, RecommendationView,
    SkillEvidenceView, SubjectDetailView, SubjectListView, SubjectModulesView,
)
from .study_source_views import StudySourceDetailView, StudySourceIngestView
from .study_plan_views import ProviderStatusView, StudyPlanChatView, StudyPlanInteractionView, StudyPlanView

urlpatterns = [
    path("study-sources/ingest", StudySourceIngestView.as_view()),
    path("study-sources/ingest/", StudySourceIngestView.as_view()),
    path("study-sources/<str:source_id>", StudySourceDetailView.as_view()),
    path("study-plans", StudyPlanView.as_view()),
    path("study-plans/", StudyPlanView.as_view()),
    path("study-plans/interactions", StudyPlanInteractionView.as_view()),
    path("study-plans/interactions/", StudyPlanInteractionView.as_view()),
    path("study-plans/chat", StudyPlanChatView.as_view()),
    path("study-plans/chat/", StudyPlanChatView.as_view()),
    path("providers", ProviderStatusView.as_view()),
    path("subjects", SubjectListView.as_view()),
    path("subjects/<slug:subject_id>", SubjectDetailView.as_view()),
    path("subjects/<slug:subject_id>/modules", SubjectModulesView.as_view()),
    path("subjects/<slug:subject_id>/modules/<slug:module_id>", ModuleDetailView.as_view()),
    path("modules/<slug:module_id>/manifest", ModuleManifestView.as_view()),
    path("modules/<slug:module_id>/attempts", ModuleAttemptsView.as_view()),
    path("modules/<slug:module_id>/attempts/", ModuleAttemptsView.as_view()),
    path("learners/anonymous", AnonymousLearnerView.as_view()),
    path("learners/<str:learner_id>/profile", LearnerProfileView.as_view()),
    path("learners/<str:learner_id>/preferences", LearnerPreferencesView.as_view()),
    path("learners/<str:learner_id>/memory", LearnerMemoryView.as_view()),
    path("learners/<str:learner_id>/memory/export", LearnerMemoryExportView.as_view()),
    path("learners/<str:learner_id>/recommendation", RecommendationView.as_view()),
    path("learners/<str:learner_id>/skills", SkillEvidenceView.as_view()),
    path("attempts/<uuid:attempt_id>/checkpoints/<slug:checkpoint_id>/predict", CheckpointView.as_view(), {"kind": "predict"}),
    path("attempts/<uuid:attempt_id>/checkpoints/<slug:checkpoint_id>/explain", CheckpointView.as_view(), {"kind": "explain"}),
    path("attempts/<uuid:attempt_id>/learning-mode", AttemptLearningModeView.as_view()),
    path("attempts/<uuid:attempt_id>/clarifications", AttemptClarificationView.as_view()),
    path("attempts/<uuid:attempt_id>/revisions", AttemptRevisionView.as_view()),
    path("attempts/<uuid:attempt_id>/record", AttemptRecordView.as_view()),
    path("attempts/<uuid:attempt_id>/inspection", AttemptInspectionView.as_view()),
]
