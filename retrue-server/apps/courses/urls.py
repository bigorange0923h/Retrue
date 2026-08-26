"""courses：课时管理接口路由。"""

from django.urls import path

from apps.courses import views

urlpatterns = [
    path("packages/", views.CoursePackageListView.as_view(), name="course-package-list"),
    path("packages/<int:package_id>/adjust/", views.CoursePackageAdjustView.as_view(), name="course-package-adjust"),
]
