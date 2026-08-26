"""training：训练记录与家庭训练接口路由。"""

from django.urls import path

from apps.training import home_views, views

urlpatterns = [
    path("", views.TrainingRecordListView.as_view(), name="training-list"),
    path("timeline/", views.CustomerTimelineView.as_view(), name="customer-timeline"),
    path("<int:record_id>/", views.TrainingRecordDetailView.as_view(), name="training-detail"),
    path("home/plans/", home_views.HomeTrainingPlanListView.as_view(), name="home-training-list"),
    path("home/plans/<int:plan_id>/", home_views.HomeTrainingPlanDetailView.as_view(), name="home-training-detail"),
]
