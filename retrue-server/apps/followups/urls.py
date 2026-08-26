"""followups：回访/复查接口路由。"""

from django.urls import path

from apps.followups import views

urlpatterns = [
    path("", views.FollowUpListView.as_view(), name="followup-list"),
    path("<int:task_id>/", views.FollowUpDetailView.as_view(), name="followup-detail"),
]
