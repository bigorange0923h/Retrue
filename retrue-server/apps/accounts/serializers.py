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
        is_superuser: 是否超级用户（前端据此决定是否展示账号管理入口）。
        is_active: 账号是否可用。
        is_staff: 是否可登录后台管理。
    """

    display_name = serializers.SerializerMethodField()
    therapist_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "therapist_id",
            "is_superuser",
            "is_active",
            "is_staff",
        ]

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


class UserListSerializer(serializers.ModelSerializer):
    """账号管理列表输出（仅超级用户可见）。

    字段：id、username、display_name、is_active、is_staff、is_superuser、last_login、date_joined。
    """

    display_name = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(format="%Y-%m-%d %H:%M", required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "display_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "date_joined",
        ]

    def get_display_name(self, obj: User) -> str:
        """获取展示名。"""
        profile = getattr(obj, "therapist_profile", None)
        if profile is not None and profile.name:
            return profile.name
        return obj.get_username()


class UserCreateSerializer(serializers.ModelSerializer):
    """账号创建输入校验。

    字段：
        username: 登录名，唯一。
        password: 初始密码，至少 8 位。
        is_active: 是否启用。
        is_staff: 是否可登录后台。
        is_superuser: 是否为超级用户。
    """

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="至少 8 位",
    )

    class Meta:
        model = User
        fields = ["username", "password", "is_active", "is_staff", "is_superuser"]
        extra_kwargs = {
            "username": {"required": True},
            "is_active": {"required": False, "default": True},
            "is_staff": {"required": False, "default": False},
            "is_superuser": {"required": False, "default": False},
        }

    def validate_username(self, value: str) -> str:
        """校验用户名唯一。"""
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("该用户名已存在")
        return value

    def create(self, validated_data: dict) -> User:
        """创建用户并设置密码。"""
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """账号更新输入校验。

    字段：
        is_active: 是否启用。
        is_staff: 是否可登录后台。
        is_superuser: 是否为超级用户。
        password: 可选，重置密码，至少 8 位。

    校验：
        不得停用/降级最后一个超级用户，避免系统失去管理入口。
    """

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        min_length=8,
        max_length=128,
        style={"input_type": "password"},
        help_text="留空则不修改密码",
    )

    class Meta:
        model = User
        fields = ["is_active", "is_staff", "is_superuser", "password"]

    def validate(self, attrs: dict) -> dict:
        """跨字段校验：保护最后一个超级用户。"""
        instance: User | None = self.instance
        if instance is None:
            return attrs

        new_active = attrs.get("is_active", instance.is_active)
        new_super = attrs.get("is_superuser", instance.is_superuser)
        # 若要把该用户改为「停用」或「不再是超管」时，需确认它不是唯一可用超管
        losing_super = instance.is_superuser and (not new_active or not new_super)
        if losing_super:
            other_super_count = User.objects.filter(is_superuser=True, is_active=True).exclude(pk=instance.pk).count()
            if other_super_count == 0:
                raise serializers.ValidationError("不能停用或降级最后一个可用的超级用户")
        return attrs

    def update(self, instance: User, validated_data: dict) -> User:
        """更新账号，若含 password 则重置密码。"""
        password = validated_data.pop("password", "")
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
