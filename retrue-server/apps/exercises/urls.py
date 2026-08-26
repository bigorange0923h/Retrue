"""exercises：动作库接口路由。"""

from django.urls import path

from apps.exercises import views

urlpatterns = [
    path("", views.ExerciseListView.as_view(), name="exercise-list"),
    path("<int:exercise_id>/", views.ExerciseDetailView.as_view(), name="exercise-detail"),
]
