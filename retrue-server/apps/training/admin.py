"""training：训练记录模型的后台管理注册。"""

from django.contrib import admin

from apps.training.models import (
    HomeTrainingExercise,
    HomeTrainingPlan,
    TrainingExercise,
    TrainingRecord,
)


class TrainingExerciseInline(admin.TabularInline):
    """训练动作内联管理。"""

    model = TrainingExercise
    extra = 0


class HomeTrainingExerciseInline(admin.TabularInline):
    """家庭训练动作内联管理。"""

    model = HomeTrainingExercise
    extra = 0


@admin.register(TrainingRecord)
class TrainingRecordAdmin(admin.ModelAdmin):
    """训练记录后台管理。"""

    list_display = ("training_date", "customer", "therapist", "created_at")
    list_filter = ("training_date",)
    search_fields = ("customer__name", "customer_feedback")
    inlines = [TrainingExerciseInline]


@admin.register(HomeTrainingPlan)
class HomeTrainingPlanAdmin(admin.ModelAdmin):
    """家庭训练计划后台管理。"""

    list_display = ("title", "customer", "therapist", "created_at")
    search_fields = ("customer__name", "title")
    inlines = [HomeTrainingExerciseInline]
