"""accounts：认证相关的序列化器。

提供登录校验与当前用户信息的序列化输出。
"""

from __future__ import annotations

from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import User
from apps.therapists.models import Therapist


class LoginSerializer(serializers.Serializer):
    """登录请求校验。

    字段：
        username: 登录用户名。
        password: 登录密码。
    校验：
        用户名与密码必须匹配，否则抛出参数校验错误。
    """

    username = serializers.CharField(max_length=150, write_only=True)
    password = serializers.CharField(max_length=128, write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict) -> dict:
        """校验用户名密码并写入认证后的用户对象。

        参数：
            attrs: 已校验的请求字段。
        返回：
            含 user 键的字典。
        异常：
            serializers.ValidationError: 用户名或密码错误，或账号被停用。
        """
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("用户名或密码错误")
        if not user.is_active:
            raise serializers.ValidationError("账号已被停用")
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """当前登录用户信息输出。

    字段：
        id: 用户 ID。
        username: 登录名。
        display_name: 展示名（优先康复师姓名，否则取用户名）。
        therapist_id: 关联的康复师 ID，无则 None。
    """

    display_name = serializers.SerializerMethodField()
    therapist_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "display_name", "therapist_id"]

    def get_display_name(self, obj: User) -> str:
        """获取展示名。"""
        profile = getattr(obj, "therapist_profile", None)
        if profile is not None and profile.name:
            return profile.name
        return obj.get_username()

    def get_therapist_id(self, obj: User) -> int | None:
        """获取关联康复师 ID。"""
        profile: Therapist | None = getattr(obj, "therapist_profile", None)
        return profile.id if profile is not None else None
