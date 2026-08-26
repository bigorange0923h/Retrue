"""customers：客户接口单元测试。

覆盖数据隔离、手机号脱敏、创建/更新/搜索与状态筛选。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.customers.models import Customer, CustomerStatus

User = get_user_model()


class CustomerApiTests(APITestCase):
    """客户接口测试。"""

    def setUp(self) -> None:
        """准备两个康复师账号与客户数据。"""
        self.therapist1 = User.objects.create_user(username="t1", password="test12345")
        self.therapist2 = User.objects.create_user(username="t2", password="test12345")

        self.client.force_login(self.therapist1)

        self.customer = Customer.objects.create(
            therapist=self.therapist1,
            name="张三",
            phone="13800138000",
            main_issue="左膝疼痛",
        )
        # 另一康复师的客户，用于隔离测试
        self.other_customer = Customer.objects.create(
            therapist=self.therapist2,
            name="李四",
            phone="13900139000",
        )

    def test_create_customer_and_masks_phone(self) -> None:
        """创建客户后自动生成脱敏手机号。"""
        resp = self.client.post(
            reverse("customer-list"),
            {"name": "王五", "phone": "13700137000", "gender": "male"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["data"]
        self.assertEqual(data["phone"], "13700137000")
        self.assertEqual(data["phone_masked"], "137****7000")

    def test_list_returns_masked_phone_only(self) -> None:
        """列表返回脱敏手机号，不暴露完整号码。"""
        resp = self.client.get(reverse("customer-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["total"], 1)
        item = resp.data["data"]["items"][0]
        self.assertEqual(item["name"], "张三")
        self.assertEqual(item["phone_masked"], "138****8000")
        self.assertNotIn("phone", item)  # 列表不返回完整手机号字段

    def test_list_isolates_therapist_data(self) -> None:
        """只能看到本人客户，不能看到其他康复师的客户。"""
        resp = self.client.get(reverse("customer-list"))
        names = [item["name"] for item in resp.data["data"]["items"]]
        self.assertIn("张三", names)
        self.assertNotIn("李四", names)

    def test_search_and_status_filter(self) -> None:
        """支持姓名搜索与状态筛选。"""
        Customer.objects.create(
            therapist=self.therapist1, name="张三丰", status=CustomerStatus.PAUSED
        )
        resp = self.client.get(reverse("customer-list"), {"keyword": "张三"})
        self.assertEqual(resp.data["data"]["total"], 2)

        resp = self.client.get(reverse("customer-list"), {"status": "paused"})
        self.assertEqual(resp.data["data"]["total"], 1)
        self.assertEqual(resp.data["data"]["items"][0]["name"], "张三丰")

    def test_detail_returns_full_phone(self) -> None:
        """详情场景返回完整手机号供资料编辑。"""
        resp = self.client.get(reverse("customer-detail", args=[self.customer.id]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["phone"], "13800138000")

    def test_cannot_access_other_therapist_customer(self) -> None:
        """不能读取其他康复师的客户详情。"""
        resp = self.client.get(reverse("customer-detail", args=[self.other_customer.id]))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(resp.data["code"], 404)

    def test_update_customer(self) -> None:
        """更新客户资料。"""
        resp = self.client.put(
            reverse("customer-detail", args=[self.customer.id]),
            {"name": "张三（更新）", "status": "paused"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["name"], "张三（更新）")
        self.assertEqual(resp.data["data"]["status"], "paused")
        # 更新后手机号脱敏值仍保留
        self.assertEqual(resp.data["data"]["phone_masked"], "138****8000")

    def test_mask_phone_helper(self) -> None:
        """脱敏函数对 11 位号码与空值处理正确。"""
        from apps.customers.models import mask_phone

        self.assertEqual(mask_phone("13800138000"), "138****8000")
        self.assertEqual(mask_phone("12345"), "")
        self.assertEqual(mask_phone(""), "")
