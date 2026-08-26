"""ai：AI 草稿接口路由。"""

from django.urls import path

from apps.ai import views

urlpatterns = [
    path("parse/", views.ParseDraftView.as_view(), name="ai-parse"),
    path("confirm/<int:draft_id>/", views.ConfirmDraftView.as_view(), name="ai-confirm"),
    path("cancel/<int:draft_id>/", views.CancelDraftView.as_view(), name="ai-cancel"),
    path("drafts/", views.DraftListView.as_view(), name="ai-drafts"),
    path("customer-candidates/", views.CustomerCandidateView.as_view(), name="ai-candidates"),
]
