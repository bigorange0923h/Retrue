"""rehab：康复计划与阶段接口路由。"""

from django.urls import path

from apps.rehab import views

urlpatterns = [
    path("plans/", views.RehabPlanListView.as_view(), name="rehab-plan-list"),
    path("stages/", views.RehabStageView.as_view(), name="rehab-stage"),
]
