"""服务器专用配置：显式选择此模块，不改变本地 config.settings 默认行为。"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


def required_env(name: str) -> str:
    """读取必填部署变量；缺失时阻止启动，不回退到开发密码。"""
    value = os.getenv(name, "")
    if not value.strip():
        raise ImproperlyConfigured(f"生产环境必须设置 {name}")
    return value


def env_list(name: str, default: str = "") -> list[str]:
    """将逗号分隔的域名或来源转成去空白列表。"""
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


DEBUG = False
SECRET_KEY = required_env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith(("unsafe-", "replace-", "django-insecure-")):
    raise ImproperlyConfigured("生产 DJANGO_SECRET_KEY 必须是至少 50 字符的随机密钥")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("生产 DJANGO_ALLOWED_HOSTS 必须显式指定域名，不能使用 *")
if "127.0.0.1" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("127.0.0.1")  # 容器内部健康探针。

ASGI_APPLICATION = "config.asgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required_env("POSTGRES_DB"),
        "USER": required_env("POSTGRES_USER"),
        "PASSWORD": required_env("POSTGRES_PASSWORD"),
        "HOST": required_env("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        # ASGI 不使用持久连接；连接池应在明确评估容量后引入。
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")),
            "sslmode": os.getenv("POSTGRES_SSLMODE", "prefer"),
        },
    }
}

# 前后端同源不需要 CORS 放行；跨域部署须显式提供完整来源。
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_ALL_ORIGINS = False
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "true").lower() == "true"
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
# 本拓扑中 Nginx 必须覆盖客户端提供的协议头。
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

STATIC_URL = os.getenv("DJANGO_STATIC_URL", "/retrue/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"  # noqa: F405
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Shanghai")

# 生产日志统一交给 Docker 收集，不在容器内轮转文件。
LOGGING["handlers"].pop("app_file", None)  # noqa: F405
for logger_config in [LOGGING["root"], *LOGGING["loggers"].values()]:  # noqa: F405
    logger_config["handlers"] = ["console"]
