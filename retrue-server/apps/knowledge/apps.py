"""knowledge：客户私有康复知识库与 RAG。"""

from __future__ import annotations

from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    """知识库应用配置。"""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
    verbose_name = "客户知识库"
