"""AssistantTask 统一任务路由。"""

from django.urls import path

from apps.assistant_tasks import views


urlpatterns = [
    path(
        "customers/by-name/",
        views.AssistantCustomerNameLookupView.as_view(),
        name="assistant-customer-name-lookup",
    ),
    # 统一回合编排入口。
    path("turns/", views.AssistantTurnView.as_view(), name="assistant-turn"),
    # 保留 list 别名，便于训练接入按既有列表命名规范反向解析。
    path("tasks/", views.AssistantTaskListCreateView.as_view(), name="assistant-task-list"),
    path("tasks/", views.AssistantTaskListCreateView.as_view(), name="assistant-task-list-create"),
    path("tasks/<int:task_id>/", views.AssistantTaskDetailView.as_view(), name="assistant-task-detail"),
    path("tasks/<int:task_id>/cancel/", views.AssistantTaskCancelView.as_view(), name="assistant-task-cancel"),
    path(
        "tasks/<int:task_id>/resume/",
        views.AssistantTurnResumeView.as_view(),
        name="assistant-task-resume",
    ),
    path(
        "tasks/<int:task_id>/customer-selection/",
        views.AssistantCustomerSelectionView.as_view(),
        name="assistant-task-customer-selection",
    ),
    path(
        "tasks/<int:task_id>/tools/",
        views.AssistantTaskToolExecuteView.as_view(),
        name="assistant-task-tool-execute",
    ),
]
