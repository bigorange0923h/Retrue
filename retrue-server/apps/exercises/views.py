"""exercises：动作库接口视图。"""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.response import ApiResponse
from apps.exercises.models import Exercise
from apps.exercises.serializers import ExerciseSerializer


class ExerciseListView(APIView):
    """动作库列表与创建接口。"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """查询动作库（官方 + 本人个人动作）。"""
        queryset = Exercise.objects.filter(is_official=True) | Exercise.objects.filter(therapist=request.user)
        keyword = request.query_params.get("keyword", "").strip()
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)
        return ApiResponse.ok(ExerciseSerializer(queryset.distinct(), many=True).data, message="查询动作库成功")

    def post(self, request):
        """创建个人动作。"""
        serializer = ExerciseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data["therapist"] = request.user
        serializer.validated_data["is_official"] = False
        exercise = Exercise.objects.create(**serializer.validated_data)
        return ApiResponse.ok(ExerciseSerializer(exercise).data, message="动作创建成功")


class ExerciseDetailView(APIView):
    """动作详情与更新接口。"""

    permission_classes = [IsAuthenticated]

    def _get_or_404(self, request, exercise_id: int):
        """获取动作（官方或本人个人动作）。"""
        exercise = Exercise.objects.filter(id=exercise_id).first()
        if exercise is None:
            return ApiResponse.error("动作不存在", 404)
        # 官方动作所有人可看；个人动作仅本人
        if not exercise.is_official and exercise.therapist_id != request.user.id:
            return ApiResponse.error("无权访问该动作", 404)
        return exercise

    def get(self, request, exercise_id: int):
        """返回动作详情。"""
        exercise = self._get_or_404(request, exercise_id)
        if isinstance(exercise, Response):
            return exercise
        return ApiResponse.ok(ExerciseSerializer(exercise).data, message="获取动作成功")

    def put(self, request, exercise_id: int):
        """更新动作（仅个人动作可改）。"""
        exercise = self._get_or_404(request, exercise_id)
        if isinstance(exercise, Response):
            return exercise
        if exercise.is_official:
            return ApiResponse.error("官方动作不可修改", 403)
        serializer = ExerciseSerializer(exercise, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.validated_data.pop("is_official", None)
        updated = serializer.save()
        return ApiResponse.ok(ExerciseSerializer(updated).data, message="动作已更新")
