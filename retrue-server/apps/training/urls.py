"""training：训练记录接口路由。"""

from django.urls import path

from apps.training import views

urlpatterns = [
    path("", views.TrainingRecordListView.as_view(), name="training-list"),
    path("timeline/", views.CustomerTimelineView.as_view(), name="customer-timeline"),
    path("<int:record_id>/", views.TrainingRecordDetailView.as_view(), name="training-detail"),
]
