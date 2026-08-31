"""assessments：评估接口路由。"""

from django.urls import path

from apps.assessments import views

urlpatterns = [
    path("metric-definitions/", views.MetricDefinitionsView.as_view(), name="assessment-metric-definitions"),
    path("initial/", views.InitialAssessmentView.as_view(), name="assessment-initial"),
    path("", views.AssessmentListView.as_view(), name="assessment-list"),
    path("<int:assessment_id>/", views.AssessmentDetailView.as_view(), name="assessment-detail"),
    path("<int:assessment_id>/complete/", views.AssessmentCompleteView.as_view(), name="assessment-complete"),
]
