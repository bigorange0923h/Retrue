"""customers：客户目录与文本匹配算法单元测试。

覆盖客户目录最小化加载、规范化、唯一命中/歧义/无匹配、别称匹配、
短名包含长名、跨康复师隔离与脱敏边界。
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.customers.catalog import (
    load_therapist_customer_directory,
    match_customers_in_text,
    normalize_name,
    resolve_customers_from_text,
)
from apps.customers.models import Customer, CustomerAlias

User = get_user_model()


def _make_customer(therapist, name, phone=""):
    return Customer.objects.create(therapist=therapist, name=name, phone=phone)


class NormalizeNameTests(TestCase):
    """文本规范化。"""

    def test_drops_whitespace_and_honorifics(self) -> None:
        """去空白与「客户/病人/患者」等称谓。"""
        self.assertEqual(normalize_name(" 客户黄伟成 "), "黄伟成")
        self.assertEqual(normalize_name("病人张三"), "张三")
        self.assertEqual(normalize_name("患者李四"), "李四")

    def test_nfkc_and_lowercase(self) -> None:
        """NFKC 归一化 + 英文字母统一小写。"""
        self.assertEqual(normalize_name("ＨＵＡＮＧ"), "huang")
        self.assertEqual(normalize_name(" Alex "), "alex")

    def test_empty_returns_empty(self) -> None:
        """空/纯称谓返回空字符串，不参与匹配。"""
        self.assertEqual(normalize_name(""), "")
        self.assertEqual(normalize_name("客户"), "")


class LoadDirectoryTests(TestCase):
    """目录最小字段加载与隔离。"""

    def setUp(self) -> None:
        self.therapist1 = User.objects.create_user(username="t1", password="test12345")
        self.therapist2 = User.objects.create_user(username="t2", password="test12345")
        self.c1 = _make_customer(self.therapist1, "黄伟成", "13800138000")
        _make_customer(self.therapist2, "黄伟成", "13900139000")

    def test_loads_only_current_therapist_minimal_fields(self) -> None:
        """只返回当前康复师客户，且字段最小（不含完整手机号）。"""
        entries = load_therapist_customer_directory(self.therapist1)
        self.assertEqual([e.id for e in entries], [self.c1.id])
        self.assertEqual(entries[0].name, "黄伟成")
        self.assertEqual(entries[0].phone_masked, "138****8000")
        self.assertNotIn("phone", entries[0].__dict__)

    def test_aliases_included(self) -> None:
        """别名随目录一并返回。"""
        CustomerAlias.objects.create(
            therapist=self.therapist1,
            customer=self.c1,
            alias="阿成",
            normalized_alias=normalize_name("阿成"),
        )
        entries = load_therapist_customer_directory(self.therapist1)
        self.assertIn("阿成", entries[0].aliases)


class MatchCustomersTests(TestCase):
    """原文匹配唯一命中/歧义/无匹配。"""

    def setUp(self) -> None:
        self.therapist1 = User.objects.create_user(username="t1", password="test12345")
        self.therapist2 = User.objects.create_user(username="t2", password="test12345")
        self.huang = _make_customer(self.therapist1, "黄伟成", "13800138000")
        self.zhang = _make_customer(self.therapist1, "张三", "13700137000")

    def test_exact_single_hit(self) -> None:
        """唯一精确命中返回 exact 预选。"""
        result = match_customers_in_text(self.therapist1, "黄伟成今天做了三组臀桥")
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.customer_id, self.huang.id)
        self.assertTrue(result.is_exact)

    def test_honorific_form_hits(self) -> None:
        """带「客户」称谓仍能命中同一客户。"""
        result = match_customers_in_text(self.therapist1, "客户黄伟成最近做了几次训练")
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.customer_id, self.huang.id)

    def test_alias_hits(self) -> None:
        """目录别称命中。"""
        CustomerAlias.objects.create(
            therapist=self.therapist1, customer=self.huang, alias="阿成", normalized_alias=normalize_name("阿成")
        )
        result = match_customers_in_text(self.therapist1, "阿成今天练了臀桥")
        self.assertEqual(result.customer_id, self.huang.id)

    def test_ambiguous_when_same_name_two_customers(self) -> None:
        """同康复师两位同名客户 → ambiguous，不自动绑定。"""
        _make_customer(self.therapist1, "张三", "13900139000")
        result = match_customers_in_text(self.therapist1, "张三做了几次训练")
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.customer_id)
        self.assertEqual(len(result.candidates), 2)

    def test_short_name_contained_in_long_no_auto_bind(self) -> None:
        """短名被长名包含（如「黄伟」命中「黄伟成」）不得自动绑定为他人。"""
        _make_customer(self.therapist1, "黄伟", "13500135000")
        result = match_customers_in_text(self.therapist1, "黄伟成今天做了臀桥")
        # 「黄伟成」优先最长命中；若「黄伟」独立存在则整体歧义或仅命中长者。
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.customer_id, self.huang.id)

    def test_no_match_returns_unmatched(self) -> None:
        """目录无此人 → unmatched，绝不猜别康复师客户。"""
        _make_customer(self.therapist2, "黄伟成", "13600136000")
        result = match_customers_in_text(self.therapist1, "刘小红今天做了臀桥")
        self.assertEqual(result.status, "unmatched")
        self.assertIsNone(result.customer_id)

    def test_alias_colliding_with_other_customer_name_is_ambiguous(self) -> None:
        """别称与他人正式名冲突（阿成→黄伟成，另有客户名「阿成」）→ 歧义。"""
        CustomerAlias.objects.create(
            therapist=self.therapist1, customer=self.huang, alias="阿成", normalized_alias=normalize_name("阿成")
        )
        _make_customer(self.therapist1, "阿成", "13600136000")
        result = match_customers_in_text(self.therapist1, "阿成今天练了臀桥")
        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.customer_id)
        self.assertEqual(len(result.candidates), 2)


class ResolveFromTextTests(TestCase):
    """resolve_customers_from_text 封装：目录匹配 + 手机后四位可选项。"""

    def setUp(self) -> None:
        self.therapist1 = User.objects.create_user(username="t1", password="test12345")
        self.c1 = _make_customer(self.therapist1, "黄伟成", "13800138000")
        self.c2 = _make_customer(self.therapist1, "黄伟成", "13900139000")

    def test_phone_tail_disambiguates(self) -> None:
        """同名客户用手机后四位唯一化。"""
        result = resolve_customers_from_text(self.therapist1, "黄伟成 8000 做了几次训练")
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.customer_id, self.c1.id)

    def test_phone_tail_missing_still_ambiguous(self) -> None:
        """同名且无手机尾号 → 歧义。"""
        result = resolve_customers_from_text(self.therapist1, "黄伟成做了几次训练")
        self.assertEqual(result.status, "ambiguous")
