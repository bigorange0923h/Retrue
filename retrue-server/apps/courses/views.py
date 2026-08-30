"""courses：课时管理接口视图。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.courses import services
from apps.courses.models import CoursePackage
from apps.courses.serializers import CoursePackageSerializer


class CoursePackageListView(APIView):
    """课时包列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询某客户课时包。"""
        customer_id = request.query_params.get("customer_id", "")
        if not customer_id:
            return ApiResponse.error("缺少 customer_id 参数", 400)
        packages = CoursePackage.objects.filter(
            therapist=request.user, customer_id=customer_id
        ).prefetch_related("adjustments__therapist", "adjustments__course_session")
        return ApiResponse.ok(CoursePackageSerializer(packages, many=True).data, message="查询课时包成功")

    def post(self, request):
        """创建课时包。"""
        serializer = CoursePackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.validated_data.get("customer")
        if customer is None or customer.therapist_id != request.user.id:
            return ApiResponse.error("无权为该客户创建课时包", 403)
        serializer.validated_data.pop("customer_name", None)
        serializer.validated_data.pop("remaining_sessions", None)
        package = CoursePackage.objects.create(therapist=request.user, **serializer.validated_data)
        return ApiResponse.ok(CoursePackageSerializer(package).data, message="课时包创建成功")


class CoursePackageAdjustView(APIView):
    """课时人工调整接口。"""

    permission_classes = [IsAuthenticated]

    def post(self, request, package_id: int):
        """人工调整课时。"""
        package = CoursePackage.objects.filter(therapist=request.user, id=package_id).first()
        if package is None:
            return ApiResponse.error("课时包不存在或无权访问", 404)
        try:
            delta = Decimal(str(request.data.get("delta", 0)))
            reason = request.data.get("reason", "").strip()
        except (InvalidOperation, TypeError, ValueError):
            return ApiResponse.error("delta 必须是数字", 400)
        try:
            updated = services.adjust_sessions(request.user, package, delta, reason)
        except ValueError as exc:
            return ApiResponse.error(str(exc), 400)
        return ApiResponse.ok(CoursePackageSerializer(updated).data, message="课时已调整")
