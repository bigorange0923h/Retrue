"""课程写入的康复师维度事务锁。

同一康复师的排课、取消、训练确认及计划调整共用锁，避免不同计划之间的
空区间冲突检查同时通过。顺序固定为康复师事务锁，再锁业务行；锁只保护
数据库写入，不包住模型请求或其他网络操作。
"""

from __future__ import annotations

from contextlib import contextmanager
from functools import wraps
from functools import wraps

from django.db import OperationalError, connection, transaction
from rest_framework.exceptions import APIException


class CourseWriteBusyError(APIException):
    """课程写入锁超时或死锁，可在刷新后重试整个请求。"""

    status_code = 409
    default_detail = "课程正在由另一请求更新，请刷新后稍后重试"
    default_code = "course_write_busy"


def course_write_locked(function):
    """为第一个参数为康复师的领域写服务统一包裹事务锁。"""
    @wraps(function)
    def locked(therapist, *args, **kwargs):
        """先取得康复师锁，再执行服务内的行锁和最新状态检查。"""
        with course_write_transaction(therapist):
            return function(therapist, *args, **kwargs)

    return locked


def course_write_locked(function):
    """为第一个参数为康复师的领域写服务统一包裹事务锁。"""
    @wraps(function)
    def locked(therapist, *args, **kwargs):
        """先取得康复师锁，再执行服务内的行锁和最新状态检查。"""
        with course_write_transaction(therapist):
            return function(therapist, *args, **kwargs)

    return locked


@contextmanager
def course_write_transaction(therapist):
    """原子执行课程写入；PostgreSQL 锁等待最多五秒。

    事务锁按账号稳定命名，提交或回滚时释放，嵌套调用可以重入。SQLite
    仅支持本地功能回归，不提供并发验收保证。未知数据库错误继续抛出。
    """
    try:
        with transaction.atomic():
            previous_timeout = None
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_setting('lock_timeout')")
                    previous_timeout = cursor.fetchone()[0]
                    cursor.execute("SELECT set_config('lock_timeout', '5000ms', true)")
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        [f"retrue:courses:therapist:{therapist.pk}"],
                    )
            yield
            # 仅成功时恢复；SQL 错误会令 PostgreSQL 事务中止，此时继续查询会
            # 覆盖原始锁超时。失败直接交给 atomic 回滚，SET LOCAL 随之恢复。
            if previous_timeout is not None and not connection.needs_rollback:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('lock_timeout', %s, true)",
                        [previous_timeout],
                    )
    except OperationalError as exc:
        cause = exc.__cause__
        sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
        if sqlstate in {"55P03", "40P01"}:
            raise CourseWriteBusyError() from exc
        raise
