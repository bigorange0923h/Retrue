"""schedules：课程接口路由。"""

from django.urls import path

from apps.schedules import views

urlpatterns = [
    path("today/", views.TodayCoursesView.as_view(), name="today-courses"),
    path("calendar/", views.CourseCalendarView.as_view(), name="course-calendar"),
    path("batch/preview/", views.BatchSchedulePreviewView.as_view(), name="course-batch-preview"),
    path("batch/confirm/", views.BatchScheduleConfirmView.as_view(), name="course-batch-confirm"),
    path(
        "plan-courses/<int:plan_course_id>/schedule/preview/",
        views.BatchSchedulePreviewView.as_view(),
        name="plan-course-schedule-preview",
    ),
    path(
        "plan-courses/<int:plan_course_id>/schedule/confirm/",
        views.BatchScheduleConfirmView.as_view(),
        name="plan-course-schedule-confirm",
    ),
    path("course-types/", views.CourseTypeListView.as_view(), name="course-type-list"),
    path("course-types/<int:type_id>/", views.CourseTypeDetailView.as_view(), name="course-type-detail"),
    path("<int:course_id>/", views.CourseDetailView.as_view(), name="course-detail"),
    path("", views.CourseCreateView.as_view(), name="course-create"),
]
