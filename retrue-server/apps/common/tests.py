"""common：统一响应与全局异常处理测试。

覆盖信封结构、业务码与异常映射。
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
)
from rest_framework.test import APITestCase

from apps.common.exceptions import _extract_message, _map_exception_to_code
from apps.common.response import ApiResponse


class ApiResponseTests(APITestCase):
    """统一响应工具测试。"""

    def test_ok_returns_unified_envelope(self) -> None:
        """成功响应包含 code/message/data。"""
        resp = ApiResponse.ok({"id": 1}, message="成功")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["code"], 200)
        self.assertEqual(resp.data["message"], "成功")
        self.assertEqual(resp.data["data"], {"id": 1})

    def test_error_returns_code_and_message(self) -> None:
        """失败响应返回指定业务码与消息。"""
        resp = ApiResponse.error("参数错误", code=400)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["code"], 400)
        self.assertEqual(resp.data["data"], None)

    def test_ok_page_returns_page_shape(self) -> None:
        """分页响应包含 items/page/page_size/total。"""
        resp = ApiResponse.ok_page([1, 2], page=1, page_size=20, total=2)
        self.assertEqual(resp.data["data"]["items"], [1, 2])
        self.assertEqual(resp.data["data"]["total"], 2)
        self.assertEqual(resp.data["data"]["page_size"], 20)


class ExceptionMappingTests(APITestCase):
    """异常到业务码映射测试。"""

    def test_map_validation_error_to_400(self) -> None:
        """参数校验异常映射为 400。"""
        self.assertEqual(_map_exception_to_code(ValidationError("bad")), 400)

    def test_map_unauthorized_to_401(self) -> None:
        """未登录/认证失败映射为 401。"""
        self.assertEqual(_map_exception_to_code(NotAuthenticated()), 401)
        self.assertEqual(_map_exception_to_code(AuthenticationFailed("fail")), 401)

    def test_map_forbidden_to_403(self) -> None:
        """无权限异常映射为 403。"""
        self.assertEqual(_map_exception_to_code(PermissionDenied()), 403)

    def test_extract_validation_message(self) -> None:
        """从字段校验错误中提取第一条中文消息。"""
        exc = ValidationError({"username": ["用户名或密码错误"]})
        self.assertEqual(_extract_message(exc, None), "用户名或密码错误")
