"""家庭训练交付回归：父子原子性、审计快照及编辑重读一致。"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.customers.models import Customer
from apps.training.models import HomeTrainingExercise, HomeTrainingPlan
from apps.training.serializers import HomeTrainingPlanCreateSerializer


class HomeTrainingDeliveryTests(APITestCase):
    """失败保持原计划，成功可以重读全部训练量和注意事项。"""

    def setUp(self) -> None:
        """使用明确模拟的客户和训练动作。"""
        self.user = get_user_model().objects.create_user(username="home-delivery", password="test12345")
        self.customer = Customer.objects.create(therapist=self.user, name="测试家庭训练客户")
        self.client.force_login(self.user)
        self.plan = HomeTrainingPlan.objects.create(therapist=self.user, customer=self.customer, title="原计划")
        HomeTrainingExercise.objects.create(plan=self.plan, exercise_name="测试原动作", sets=2, reps=8)

    def test_edit_reread_and_audit_include_complete_dose(self) -> None:
        """编辑后重新读取和审计记录中都是最新动作明细。"""
        payload = {"title": "更新计划", "frequency": "每周三次", "note": "测试注意事项",
                   "exercises": [{"exercise_name": "测试静蹲", "sets": 3, "duration_seconds": 30,
                                  "frequency": "隔天一次", "note": "测试控制幅度"}]}
        url = reverse("home-training-detail", args=[self.plan.id])
        resp = self.client.put(url, payload, format="json")
        self.assertEqual(resp.status_code, 200)
        reread = self.client.get(url).data["data"]
        self.assertEqual(reread["exercises"][0]["duration_seconds"], 30)
        self.assertEqual(reread["exercises"][0]["frequency"], "隔天一次")
        log = AuditLog.objects.get(actor=self.user, object_id=str(self.plan.id), action="update")
        self.assertEqual(log.before_data["exercises"][0]["exercise_name"], "测试原动作")
        self.assertEqual(log.after_data["exercises"][0]["exercise_name"], "测试静蹲")

    def test_child_failure_keeps_parent_and_original_children(self) -> None:
        """子动作写入失败后，父计划更改和旧动作删除一并回滚。"""
        serializer = HomeTrainingPlanCreateSerializer(self.plan,
            data={"title": "不应保留的标题", "exercises": [{"exercise_name": "测试新动作"}]}, partial=True)
        serializer.is_valid(raise_exception=True)
        with patch.object(HomeTrainingPlanCreateSerializer, "_create_exercises", side_effect=RuntimeError("模拟子项失败")):
            with self.assertRaises(RuntimeError):
                serializer.save()
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.title, "原计划")
        self.assertEqual(self.plan.exercises.get().exercise_name, "测试原动作")

    def test_audit_failure_rolls_back_create_and_nested_rows(self) -> None:
        """审计失败不能留下新计划或孤立明细。"""
        with patch("apps.training.home_services.write_audit_log", side_effect=RuntimeError("模拟审计失败")):
            resp = self.client.post(reverse("home-training-list"),
                {"customer": self.customer.id, "title": "不应保留", "exercises": [{"exercise_name": "测试动作"}]},
                format="json")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(HomeTrainingPlan.objects.count(), 1)
        self.assertEqual(HomeTrainingExercise.objects.count(), 1)
