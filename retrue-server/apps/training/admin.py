"""training：训练记录模型的后台管理注册。"""

from django.contrib import admin

from apps.training.models import TrainingExercise, TrainingRecord


class TrainingExerciseInline(admin.TabularInline):
    """训练动作内联管理。"""

    model = TrainingExercise
    extra = 0


@admin.register(TrainingRecord)
class TrainingRecordAdmin(admin.ModelAdmin):
    """训练记录后台管理。"""

    list_display = ("training_date", "customer", "therapist", "created_at")
    list_filter = ("training_date",)
    search_fields = ("customer__name", "customer_feedback")
    inlines = [TrainingExerciseInline]
