"""knowledge：客户知识库接口路由。"""

from django.urls import path

from apps.knowledge import views

urlpatterns = [
    path("items/", views.KnowledgeItemListView.as_view(), name="knowledge-item-list"),
    path("items/<int:item_id>/", views.KnowledgeItemDetailView.as_view(), name="knowledge-item-detail"),
    path("candidates/", views.KnowledgeCandidateListView.as_view(), name="knowledge-candidate-list"),
    path(
        "candidates/<int:candidate_id>/decide/",
        views.KnowledgeCandidateConfirmView.as_view(),
        name="knowledge-candidate-decide",
    ),
    path("rag/", views.RagAnswerView.as_view(), name="knowledge-rag"),
    path("index/", views.KnowledgeIndexBuildView.as_view(), name="knowledge-index-build"),
]
