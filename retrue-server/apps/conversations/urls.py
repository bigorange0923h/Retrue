"""统一 AI 会话路由。"""

from django.urls import path

from apps.conversations import views

urlpatterns = [
    path("", views.ConversationListCreateView.as_view(), name="conversation-list-create"),
    path("<int:conversation_id>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("<int:conversation_id>/messages/", views.ConversationMessageView.as_view(), name="conversation-message"),
    path("<int:conversation_id>/episodes/extract/", views.ConversationEpisodeExtractView.as_view(), name="conversation-episode-extract"),
]
