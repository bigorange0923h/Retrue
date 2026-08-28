"""schedules：课程接口路由。"""

from django.urls import path

from apps.schedules import views

urlpatterns = [
    path("today/", views.TodayCoursesView.as_view(), name="today-courses"),
    path("calendar/", views.CourseCalendarView.as_view(), name="course-calendar"),
    path("<int:course_id>/", views.CourseDetailView.as_view(), name="course-detail"),
    path("", views.CourseCreateView.as_view(), name="course-create"),
]
