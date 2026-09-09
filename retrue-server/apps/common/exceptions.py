"""全局异常处理。

将 DRF 与 Django 抛出的异常统一转换为 {code, message, data} 信封结构，
避免在每个 View 中分别处理，也避免向客户端泄露堆栈、SQL 或敏感信息。
"""

from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from rest_framework import exceptions  # noqa: F401  # 供异常类型判断时引用
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.common.response import (
    CODE_BAD_REQUEST,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_SERVER_ERROR,
    CODE_TOO_MANY_REQUESTS,
    CODE_UNAUTHORIZED,
)

logger = logging.getLogger(__name__)


def custom_exception_handler(exc: Exception, context: dict) -> object:
    """DRF 统一异常入口。

    参数：
        exc: 捕获到的异常对象。
        context: DRF 提供的上下文，含 request、view 等信息。
    返回：
        统一信封结构的 Response；无法识别的异常记录日志后返回 500。
    """
    response = exception_handler(exc, context)

    if response is not None:
        code = _map_exception_to_code(exc)
        message = _extract_message(exc, response)
        response.data = {"code": code, "message": message, "data": None}
        response.status_code = code
        return response

    logger.exception("未处理的服务器异常: %s", exc)
    return Response(
        {"code": CODE_SERVER_ERROR, "message": "服务器内部错误", "data": None},
        status=CODE_SERVER_ERROR,
    )


def _map_exception_to_code(exc: Exception) -> int:
    """将 DRF 异常映射为统一业务状态码。

    参数：
        exc: DRF 异常实例。
    返回：
        对应的业务状态码。
    """
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return CODE_UNAUTHORIZED
    if isinstance(exc, PermissionDenied):
        return CODE_FORBIDDEN
    if isinstance(exc, Throttled):
        return CODE_TOO_MANY_REQUESTS
    if isinstance(exc, ValidationError):
        return CODE_BAD_REQUEST
    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return CODE_NOT_FOUND
    return CODE_BAD_REQUEST


def _extract_message(exc: Exception, response: object) -> str:
    """从异常或 DRF 响应中提取面向用户的简短中文消息。

    参数：
        exc: 原始异常。
        response: DRF 生成的响应。
    返回：
        可直接展示给用户的中文消息字符串。
    """
    if isinstance(exc, ValidationError):
        detail = exc.detail
        if isinstance(detail, dict) and detail:
            first = next(iter(detail.values()))
            if isinstance(first, list) and first:
                return str(first[0])
            return str(first)
        if isinstance(detail, list) and detail:
            return str(detail[0])
        return "参数校验失败"

    detail = getattr(exc, "detail", None)
    if detail is not None:
        return str(detail)
    return str(getattr(response, "data", "请求失败")) if response is not None else "请求失败"
