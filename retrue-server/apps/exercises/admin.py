"""exercises：动作库模型的后台管理注册。"""

from django.contrib import admin

from apps.exercises.models import Exercise, ExerciseAlias


class ExerciseAliasInline(admin.TabularInline):
    """动作别名内联管理。"""

    model = ExerciseAlias
    extra = 0


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    """动作库后台管理。"""

    list_display = ("name", "body_part", "is_official", "therapist")
    list_filter = ("is_official",)
    search_fields = ("name",)
    inlines = [ExerciseAliasInline]
