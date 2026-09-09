"""统一 API 响应工具与业务状态码。

所有业务接口必须通过本模块构造响应，保证外层结构统一为：
    {"code": 200, "message": "成功的消息", "data": null}
不允许在 View 中手写不同格式的 Response。
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response

# 业务状态码常量
CODE_SUCCESS = 200
CODE_BAD_REQUEST = 400
CODE_UNAUTHORIZED = 401
CODE_FORBIDDEN = 403
CODE_NOT_FOUND = 404
CODE_CONFLICT = 409
CODE_TOO_MANY_REQUESTS = 429
CODE_SERVER_ERROR = 500


class ApiResponse:
    """统一 API 响应构造器。

    职责：将业务码、消息与数据包装成统一信封结构。
    参数：
        code: 业务状态码，默认 200。
        message: 面向前端的中文短消息。
        data: 业务数据，可为对象、数组或 None。
    返回：
        rest_framework.response.Response，状态码与业务码一致。
    """

    @staticmethod
    def ok(data: Any = None, message: str = "操作成功", code: int = CODE_SUCCESS) -> Response:
        """构造成功响应。

        参数：
            data: 业务数据，默认 None。
            message: 成功提示消息。
            code: 业务状态码，默认 200。
        返回：
            统一信封结构的 DRF Response。
        """
        return Response({"code": code, "message": message, "data": data}, status=code)

    @staticmethod
    def error(
        message: str,
        code: int = CODE_BAD_REQUEST,
        data: Any = None,
        http_status: int | None = None,
    ) -> Response:
        """构造失败响应。

        参数：
            message: 面向用户的中文错误消息，不得包含内部堆栈或敏感信息。
            code: 业务状态码。
            data: 可选的错误详情，如字段错误对象。
            http_status: HTTP 状态码，默认与 code 一致；需区分时可单独指定。
        返回：
            统一信封结构的 DRF Response。
        """
        return Response(
            {"code": code, "message": message, "data": data},
            status=http_status if http_status is not None else code,
        )

    @staticmethod
    def ok_page(items: Any, page: int, page_size: int, total: int, message: str = "查询成功") -> Response:
        """构造分页成功响应。

        参数：
            items: 当前页数据列表。
            page: 当前页码，从 1 开始。
            page_size: 每页条数。
            total: 总条数。
            message: 提示消息。
        返回：
            统一信封结构，data 为 {items, page, page_size, total}。
        """
        return ApiResponse.ok(
            {"items": items, "page": page, "page_size": page_size, "total": total},
            message=message,
        )
