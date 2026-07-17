from django.urls import path
from .views import AuditView, ClarificationView, InspectionView, LessonView, RecordView, RevisionView, SessionView

urlpatterns = [
    path("lessons/<str:lesson_id>", LessonView.as_view()),
    path("sessions", SessionView.as_view()),
    path("sessions/<str:session_id>/audit", AuditView.as_view()),
    path("sessions/<str:session_id>/record", RecordView.as_view()),
    path("sessions/<str:session_id>/inspection", InspectionView.as_view()),
    path("sessions/<str:session_id>/claims/<str:claim_id>/clarifications", ClarificationView.as_view()),
    path("sessions/<str:session_id>/claims/<str:claim_id>/revisions", RevisionView.as_view()),
]
