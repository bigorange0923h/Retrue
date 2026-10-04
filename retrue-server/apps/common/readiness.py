"""独立短超时就绪检查；只读数据库和模型配置，不调用真实模型。"""

from __future__ import annotations

from time import monotonic

import psycopg
from psycopg import sql
from django.conf import settings
from django.db.migrations.loader import MigrationLoader
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def _expected_migrations() -> set[tuple[str, str]]:
    """从当前发布代码构建必需迁移集合，不使用业务数据库连接。"""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return {
        migration
        for leaf in loader.graph.leaf_nodes()
        for migration in loader.graph.forwards_plan(leaf)
    }


def _database_readiness() -> dict[str, str]:
    """新建只读连接，限制连接/语句/锁等待；不复用业务事务或建表。"""
    checks = {name: "unavailable" for name in ("database", "migrations", "cache", "vector")}
    config = settings.DATABASES["default"]
    if config["ENGINE"] != "django.db.backends.postgresql":
        checks["database"] = "unsupported"
        return checks
    try:
        expected = _expected_migrations()
        options = dict(config.get("OPTIONS", {}))
        options.pop("options", None)
        options.pop("connect_timeout", None)
        # 使用服务端只读会话和短超时，避免探针因业务事务等待而耗尽工作线程。
        with psycopg.connect(
            dbname=config["NAME"], user=config["USER"], password=config.get("PASSWORD", ""),
            host=config.get("HOST", ""), port=config.get("PORT", "5432"),
            connect_timeout=2, autocommit=True,
            options="-c statement_timeout=1000 -c lock_timeout=1000 -c default_transaction_read_only=on",
            **options,
        ) as probe:
            with probe.cursor() as cursor:
                cursor.execute("SELECT 1")
                checks["database"] = "ok"
                cursor.execute("SELECT app, name FROM django_migrations")
                applied = set(cursor.fetchall())
                checks["migrations"] = "ok" if expected <= applied else "pending"
                cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                checks["vector"] = "ok" if cursor.fetchone()[0] else "missing"
                cache = settings.CACHES["default"]
                if cache["BACKEND"] == "django.core.cache.backends.db.DatabaseCache":
                    cursor.execute(sql.SQL("SELECT cache_key FROM {} LIMIT 1").format(
                        sql.Identifier(*str(cache["LOCATION"]).split(".")),
                    ))
                    checks["cache"] = "ok"
                else:
                    checks["cache"] = "unsupported"
    except Exception:
        # 探针只返回稳定状态，不把连接信息、SQL、密钥或内部异常暴露给公网。
        return checks
    return checks


def _model_configuration() -> dict[str, str]:
    """只构建 provider 校验配置；运行时连通/质量需要另行授权验证。"""
    try:
        from apps.ai.providers.factory import get_provider
        get_provider()
    except Exception:
        return {"model_configuration": "invalid", "model_runtime": "not_checked"}
    return {"model_configuration": "ok", "model_runtime": "not_checked"}


@require_GET
def readiness_check(request):
    """返回独立就绪状态；200 表示依赖/配置可就绪，503 表示尚不能接业务。"""
    started = monotonic()
    checks = _database_readiness()
    checks.update(_model_configuration())
    ready = all(value == "ok" for name, value in checks.items() if name != "model_runtime")
    code = 200 if ready else 503
    response = JsonResponse({
        "code": code,
        "message": "业务依赖已就绪；真实模型尚未验证" if ready else "业务依赖尚未就绪",
        "data": {
            "status": "ready" if ready else "not_ready", "checks": checks,
            "live_model_checked": False, "elapsed_ms": round((monotonic() - started) * 1000),
        },
    }, status=code)
    response["Cache-Control"] = "no-store"
    return response
