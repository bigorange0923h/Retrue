"""exercises：动作库接口单元测试。"""

from __future__ import annotations

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.exercises.models import Exercise

User = get_user_model()


class ExerciseApiTests(APITestCase):
    """动作库接口测试。"""

    def setUp(self) -> None:
        """准备康复师与动作。"""
        self.therapist = User.objects.create_user(username="t1", password="test12345")
        self.other = User.objects.create_user(username="t2", password="test12345")
        self.client.force_login(self.therapist)

        self.official = Exercise.objects.create(name="臀桥", body_part="髋", is_official=True)
        self.personal = Exercise.objects.create(name="我的单腿蹲", therapist=self.therapist)
        self.other_personal = Exercise.objects.create(name="别人的动作", therapist=self.other)

    def test_list_shows_official_and_own(self) -> None:
        """列表显示官方动作与本人个人动作，不含他人个人动作。"""
        resp = self.client.get(reverse("exercise-list"))
        names = [item["name"] for item in resp.data["data"]]
        self.assertIn("臀桥", names)
        self.assertIn("我的单腿蹲", names)
        self.assertNotIn("别人的动作", names)

    def test_create_personal_exercise(self) -> None:
        """创建个人动作。"""
        resp = self.client.post(
            reverse("exercise-list"),
            {"name": "靠墙静蹲", "body_part": "膝"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["name"], "靠墙静蹲")
        self.assertEqual(resp.data["data"]["is_official"], False)

    def test_cannot_modify_official_exercise(self) -> None:
        """官方动作不可修改。"""
        resp = self.client.put(
            reverse("exercise-detail", args=[self.official.id]),
            {"name": "改名"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_access_other_personal_exercise(self) -> None:
        """不能访问他人个人动作。"""
        resp = self.client.get(reverse("exercise-detail", args=[self.other_personal.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_search(self) -> None:
        """按名称搜索。"""
        resp = self.client.get(reverse("exercise-list"), {"keyword": "单腿蹲"})
        self.assertEqual(len(resp.data["data"]), 1)
        self.assertEqual(resp.data["data"][0]["name"], "我的单腿蹲")

    def test_personal_aliases_create_replace_and_search(self) -> None:
        """个人动作可维护别名，重读与别名搜索一致。"""
        resp = self.client.post(reverse("exercise-list"),
                               {"name": "测试动作", "aliases": [{"alias": "测试旧称"}]}, format="json")
        self.assertEqual(resp.status_code, 200)
        exercise_id = resp.data["data"]["id"]
        resp = self.client.put(reverse("exercise-detail", args=[exercise_id]),
                               {"aliases": [{"alias": "测试新称"}], "is_official": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["data"]["is_official"])
        reread = self.client.get(reverse("exercise-detail", args=[exercise_id]))
        self.assertEqual(reread.data["data"]["aliases"][0]["alias"], "测试新称")
        self.assertEqual(len(self.client.get(reverse("exercise-list"), {"keyword": "测试旧称"}).data["data"]), 0)
        self.assertEqual(len(self.client.get(reverse("exercise-list"), {"keyword": "测试新称"}).data["data"]), 1)

    def test_official_aliases_readonly_and_duplicate_alias_rejected(self) -> None:
        """别名写入不能绕过官方只读，也不能保存同动作重复别名。"""
        resp = self.client.put(reverse("exercise-detail", args=[self.official.id]),
                               {"aliases": [{"alias": "非法更改"}]}, format="json")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.put(reverse("exercise-detail", args=[self.personal.id]),
                               {"aliases": [{"alias": "same"}, {"alias": "SAME"}]}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_exercise_audit_failure_rolls_back_alias_and_parent(self) -> None:
        """审计失败不能留下个人动作及子别名。"""
        before = Exercise.objects.count()
        with patch("apps.exercises.views.write_audit_log", side_effect=RuntimeError("模拟审计失败")):
            resp = self.client.post(reverse("exercise-list"),
                                   {"name": "不应保留", "aliases": [{"alias": "测试别名"}]}, format="json")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(Exercise.objects.count(), before)
