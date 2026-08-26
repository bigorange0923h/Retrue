"""audit：审计日志接口路由。"""

from django.urls import path

from apps.audit import views

urlpatterns = [
    path("", views.AuditLogListView.as_view(), name="audit-list"),
    path("object/", views.AuditLogObjectListView.as_view(), name="audit-object"),
]
