"""单次对话 SSE 传输，兼容开发用 WSGI 与部署用 ASGI，不提供自动重放。"""

import asyncio
from queue import Empty, Full, Queue
from threading import BoundedSemaphore, Event, Thread
from time import monotonic
from typing import Any, Callable

from django.core.handlers.asgi import ASGIRequest
from django.db import connections
from django.http import StreamingHttpResponse
from rest_framework.renderers import JSONRenderer

from apps.ai.orchestration.progress import report_progress
from apps.common.response import ApiResponse

# 本地试用版限制每个进程的执行数量；连接断开后，已开始的同步调用可能继续。
_slots = BoundedSemaphore(4)
HEARTBEAT_SECONDS = 10
STREAM_SECONDS = 180


def _encode(event: str, envelope: dict, sequence: int) -> str:
    """按 SSE 格式编码统一信封，JSON 转义保证正文不能注入额外事件。"""
    data = JSONRenderer().render(envelope).decode("utf-8")
    return f"id: {sequence}\nevent: {event}\ndata: {data}\n\n"


def turn_stream_response(request: Any, execute: Callable[[], dict], error_response: Callable):
    """为已认证且输入通过校验的一次执行建立流；同步业务只运行一次。"""
    if not _slots.acquire(blocking=False):
        return ApiResponse.error("助理正在处理较多请求，请稍后再试", 503)

    queue: Queue = Queue(maxsize=128)
    disconnected = Event()

    def publish(event: str, envelope: dict) -> None:
        if disconnected.is_set():
            return
        try:
            queue.put_nowait((event, envelope))
        except Full:
            # 慢客户端只丢过期进度，终态必须可投递；队列禁止无界增长。
            if event in {"result", "error"}:
                while True:
                    try:
                        queue.get_nowait()
                    except Empty:
                        break
                queue.put_nowait((event, envelope))

    def work() -> None:
        try:
            with report_progress(lambda progress: publish("progress", ApiResponse.ok(progress).data)):
                result = execute()
            publish("result", ApiResponse.ok(result, "对话处理完成").data)
        except Exception as exc:
            publish("error", error_response(exc).data)
        finally:
            try:
                connections.close_all()
            finally:
                _slots.release()

    def take():
        try:
            return queue.get(timeout=HEARTBEAT_SECONDS)
        except Empty:
            return None

    def frame(item, sequence):
        if item is None:
            return ": heartbeat\n\n"
        return _encode(item[0], item[1], sequence)

    def timeout_frame(sequence):
        return _encode("error", ApiResponse.error(
            "等待时间较长，处理可能仍在继续，请查看当前会话或任务后再操作", 504,
        ).data, sequence)

    def sync_events():
        deadline = monotonic() + STREAM_SECONDS
        sequence = 0
        try:
            yield ": connected\n\n"
            while monotonic() < deadline:
                item = take()
                sequence += 1
                yield frame(item, sequence)
                if item and item[0] in {"result", "error"}:
                    return
            yield timeout_frame(sequence + 1)
        finally:
            disconnected.set()

    async def async_events():
        deadline = monotonic() + STREAM_SECONDS
        sequence = 0
        try:
            yield ": connected\n\n"
            while monotonic() < deadline:
                item = await asyncio.to_thread(take)
                sequence += 1
                yield frame(item, sequence)
                if item and item[0] in {"result", "error"}:
                    return
            yield timeout_frame(sequence + 1)
        finally:
            disconnected.set()

    # DRF 的 request 包装了原始请求；必须匹配迭代器类型，避免 ASGI 缓冲整个流。
    native_request = getattr(request, "_request", request)
    events = async_events() if isinstance(native_request, ASGIRequest) else sync_events()
    response = StreamingHttpResponse(events, content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache, no-store, no-transform"
    response["X-Accel-Buffering"] = "no"
    try:
        Thread(target=work, name="assistant-turn-stream", daemon=True).start()
    except Exception:
        _slots.release()
        raise
    return response
