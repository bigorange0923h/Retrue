"""schedules：课程接口路由。"""

from django.urls import path

from apps.schedules import views

urlpatterns = [
    path("today/", views.TodayCoursesView.as_view(), name="today-courses"),
    path("calendar/", views.CourseCalendarView.as_view(), name="course-calendar"),
    path("course-types/", views.CourseTypeListView.as_view(), name="course-type-list"),
    path("course-types/<int:type_id>/", views.CourseTypeDetailView.as_view(), name="course-type-detail"),
    path("customer-courses/", views.CustomerCourseListView.as_view(), name="customer-course-list"),
    path(
        "customer-courses/<int:course_id>/",
        views.CustomerCourseDetailView.as_view(),
        name="customer-course-detail",
    ),
    path("<int:course_id>/", views.CourseDetailView.as_view(), name="course-detail"),
    path("", views.CourseCreateView.as_view(), name="course-create"),
]
