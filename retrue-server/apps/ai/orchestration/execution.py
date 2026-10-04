"""以持久执行记录隔离旧尝试；模型等待期间不持有数据库事务。"""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.assistant_tasks.models import AssistantRun, AssistantRunStatus, AssistantTask
from apps.assistant_tasks.services import TaskVersionConflict

_run_id = ContextVar("assistant_execution_run", default=None)


def current_run_id():
    """返回本图执行的 run 引用，供只读 Tool 复用，避免另建竞争尝试。"""
    return _run_id.get()


def execution_timeout():
    """执行恢复时间至少覆盖 SSE 时限及单次模型调用，避免仍正常处理时提前重试。"""
    return max(210, int(getattr(settings, "AI_TIMEOUT", 60)) + 30)


def assert_execution_current():
    """节点和外部调用返回后验证所属尝试；失效执行不能继续生成可确认结果。"""
    run_id = _run_id.get()
    if run_id is None:
        return
    run = AssistantRun.objects.select_related("task").filter(pk=run_id).first()
    if (
        run is None or run.status != AssistantRunStatus.RUNNING
        or run.task.status in {"cancelled", "expired", "completed"}
        or run.task.runs.order_by("-attempt", "-id").values_list("id", flat=True).first() != run_id
        or run.started_at < timezone.now() - timedelta(seconds=execution_timeout())
    ):
        raise TaskVersionConflict("本次执行已失效，请查看任务当前结果后再操作")
    AssistantTask.objects.filter(pk=run.task_id).update(last_activity_at=timezone.now())


@contextmanager
def execution_scope(run):
    """将 run 归属带入图的线程上下文，退出时恢复，避免不同请求串用。"""
    token = _run_id.set(run.id)
    try:
        assert_execution_current()
        yield
        assert_execution_current()
    finally:
        _run_id.reset(token)


@contextmanager
def execution_write():
    """短事务内锁定所属任务与执行，再校验并写结果，堵住校验后的竞态。"""
    run_id = _run_id.get()
    if run_id is None:
        yield
        return
    with transaction.atomic():
        task_id = AssistantRun.objects.values_list("task_id", flat=True).get(pk=run_id)
        AssistantTask.objects.select_for_update().get(pk=task_id)
        AssistantRun.objects.select_for_update().get(pk=run_id)
        assert_execution_current()
        yield


class GuardedProvider:
    """为当前尝试的所有 provider 方法添加返回后校验，不改变供应商实现。"""

    def __init__(self, provider):
        self.provider = provider

    def __getattr__(self, name):
        value = getattr(self.provider, name)
        if not callable(value):
            return value

        def call(*args, **kwargs):
            assert_execution_current()
            result = value(*args, **kwargs)
            assert_execution_current()
            return result
        return call


def guard_provider(provider):
    """仅当前编排执行需要包装；独立工具与普通 provider 测试保持原对象。"""
    return GuardedProvider(provider) if _run_id.get() is not None else provider
