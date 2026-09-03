"""ai.segmentation：训练语义分段器单元测试。

覆盖：按客户训练起点切段、不含叙述不误切、单/多客户段数判定、别称/称谓段、
叙述首尾不影响段起点。
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.ai.segmentation import split_training_segments


class SplitTrainingSegmentsTests(SimpleTestCase):
    def test_two_customers_two_segments(self) -> None:
        """两位客户各成一段，内容正确归属。"""
        text = "客户A今天做了深蹲10次，康复按摩1次；客户B做了俯卧撑，每组10次，共5组。"
        segments = split_training_segments(text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0][0], "客户A")
        self.assertIn("深蹲10次", segments[0][1])
        self.assertEqual(segments[1][0], "客户B")
        self.assertIn("俯卧撑", segments[1][1])

    def test_bare_names_segments(self) -> None:
        """无称谓的裸姓名也能切段。"""
        text = "张三今天做了臀桥3组；李四昨天做了深蹲5组。"
        segments = split_training_segments(text)
        self.assertEqual([s[0] for s in segments], ["张三", "李四"])

    def test_single_customer_one_segment(self) -> None:
        """单客户训练叙述只产生一段（非多客户）。"""
        text = "张三今天做了臀桥3组12次"
        self.assertEqual(len(split_training_segments(text)), 1)

    def test_no_training_token_no_segment(self) -> None:
        """普通问答不含训练起点词，不误判为训练段。"""
        text = "张三最近恢复得怎么样"
        self.assertEqual(split_training_segments(text), [])

    def test_narration_before_does_not_break(self) -> None:
        """首部叙述不影响后续客户段的起点。"""
        text = "今天给客户A和客户B补记，客户A做了深蹲10次；客户B做了俯卧撑5组。"
        segments = split_training_segments(text)
        # “给客户A和客户B补记”不是训练起点（后面跟“补记”而非训练叙述触发词），
        # 真正起点是“客户A做了深蹲”“客户B做了俯卧撑”。
        self.assertEqual([s[0] for s in segments], ["客户A", "客户B"])

    def test_alias_prefix_kept(self) -> None:
        """显式「客户」前缀被保留，供目录匹配先去前缀。"""
        segments = split_training_segments("客户阿成今天练了臀桥")
        self.assertEqual(segments[0][0], "客户阿成")
