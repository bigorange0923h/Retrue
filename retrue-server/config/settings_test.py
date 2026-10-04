"""独立 PostgreSQL 测试配置：忽略真实业务库连接和真实聊天模型配置。"""

import os

from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "retrue_validation",
        "USER": os.getenv("RETRUE_TEST_DB_USER", "retrue_test"),
        "PASSWORD": os.getenv("RETRUE_TEST_DB_PASSWORD", "validation_only"),
        "HOST": os.getenv("RETRUE_TEST_DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("RETRUE_TEST_DB_PORT", "58432"),
        "OPTIONS": {"connect_timeout": 3},
        "TEST": {"NAME": "test_retrue_validation"},
    }
}
AI_PROVIDER = "mock"
AI_CONFIG_FILE = ""
AI_FALLBACK_PROVIDERS = ""
AI_API_KEY = ""
AI_MODEL = ""
AI_BASE_URL = ""
AI_EMBEDDING_API_KEY = ""
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "retrue_cache"}}
