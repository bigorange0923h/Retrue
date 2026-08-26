"""customers：客户序列化器。

提供客户列表（脱敏）、详情与编辑（完整手机号）两种输出，确保手机号脱敏。
"""

from __future__ import annotations

from rest_framework import serializers

from apps.customers.models import Customer, CustomerStatus


class CustomerListSerializer(serializers.ModelSerializer):
    """客户列表输出（脱敏）。

    列表场景不返回完整手机号，仅返回 phone_masked。
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    gender_display = serializers.CharField(source="get_gender_display", read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone_masked",
            "gender",
            "gender_display",
            "main_issue",
            "status",
            "status_display",
            "first_visit_date",
            "created_at",
            "updated_at",
        ]


class CustomerDetailSerializer(serializers.ModelSerializer):
    """客户详情输出。

    详情场景返回完整手机号，供资料编辑使用。
    """

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    gender_display = serializers.CharField(source="get_gender_display", read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "phone_masked",
            "gender",
            "gender_display",
            "birth_date",
            "occupation",
            "sport",
            "main_issue",
            "injury_date",
            "surgery_date",
            "status",
            "status_display",
            "first_visit_date",
            "note",
            "created_at",
            "updated_at",
        ]


class CustomerCreateSerializer(serializers.ModelSerializer):
    """客户创建/编辑输入校验。

    手机号为可选；提交时由 service 自动生成脱敏值。
    """

    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "gender",
            "birth_date",
            "occupation",
            "sport",
            "main_issue",
            "injury_date",
            "surgery_date",
            "status",
            "first_visit_date",
            "note",
        ]
        extra_kwargs = {"name": {"required": True}}
