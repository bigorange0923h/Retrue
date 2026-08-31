"""rehab：康复计划与阶段接口路由。"""

from django.urls import path

from apps.rehab import views
from apps.schedules import views as schedule_views

urlpatterns = [
    path(
        "plan-templates/",
        views.RehabPlanTemplateListView.as_view(),
        name="rehab-plan-template-list",
    ),
    path(
        "plan-templates/<int:template_id>/",
        views.RehabPlanTemplateDetailView.as_view(),
        name="rehab-plan-template-detail",
    ),
    path("plans/", views.RehabPlanListView.as_view(), name="rehab-plan-list"),
    path("plans/<int:plan_id>/", views.RehabPlanDetailView.as_view(), name="rehab-plan-detail"),
    path("plan-courses/", views.RehabPlanCourseListView.as_view(), name="rehab-plan-course-list"),
    path(
        "plan-courses/<int:course_id>/",
        views.RehabPlanCourseDetailView.as_view(),
        name="rehab-plan-course-detail",
    ),
    path(
        "plan-courses/<int:course_id>/adjust/",
        views.RehabPlanCourseAdjustView.as_view(),
        name="rehab-plan-course-adjust",
    ),
    path(
        "plan-courses/<int:plan_course_id>/schedule/preview/",
        schedule_views.BatchSchedulePreviewView.as_view(),
        name="rehab-plan-course-schedule-preview",
    ),
    path(
        "plan-courses/<int:plan_course_id>/schedule/confirm/",
        schedule_views.BatchScheduleConfirmView.as_view(),
        name="rehab-plan-course-schedule-confirm",
    ),
    path("stages/", views.RehabStageView.as_view(), name="rehab-stage"),
]
