"""assessments：评估接口路由。"""

from django.urls import path

from apps.assessments import views

urlpatterns = [
    path("", views.AssessmentListView.as_view(), name="assessment-list"),
    path("<int:assessment_id>/", views.AssessmentDetailView.as_view(), name="assessment-detail"),
]
