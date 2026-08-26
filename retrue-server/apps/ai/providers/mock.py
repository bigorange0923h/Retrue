"""Mock AI provider。

真实服务商尚未确定，先用确定性规则解析训练自然语言文本，
返回符合 TrainingDraft schema 的结构化草稿。接入真实模型后替换。
"""

from __future__ import annotations

import re
from datetime import date

from apps.ai.providers.base import AIProviderError, BaseProvider


class MockProvider(BaseProvider):
    """基于规则的 Mock provider。

    从自然语言中提取动作（名称 + 组数/次数/负荷）与客户反馈等。
    用于在真实 LLM 接入前打通草稿确认闭环。
    """

    def parse_training_text(self, text: str) -> dict:
        """解析训练文本为结构化草稿。

        参数：
            text: 自然语言训练描述。
        返回：
            TrainingDraft 兼容的字典。
        """
        if not text or not text.strip():
            raise AIProviderError("训练描述为空")

        text = text.strip()
        exercises = self._extract_exercises(text)

        # 简单提取客户感受与计划（规则启发式）
        feedback = self._extract_section(text, ["感觉", "感受", "有点", "疼痛"])
        next_plan = self._extract_section(text, ["下次", "下一步", "接下来"])

        return {
            "training_date": date.today().isoformat(),
            "customer_hint": None,
            "exercises": exercises,
            "customer_feedback": feedback,
            "therapist_observation": "",
            "next_plan": next_plan,
        }

    def _extract_exercises(self, text: str) -> list:
        """提取动作列表。

        对每个片段查找数量单位（组/次/秒/kg）之前的连续中文作为动作名。

        参数：
            text: 训练描述文本。
        返回：
            动作草稿字典列表。
        """
        results = []
        # 按分号/句号/换行/中文逗号拆分，支持多个动作
        segments = re.split(r"[;；。\n，,]+", text)
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            exercise = self._parse_single_segment(segment)
            if exercise:
                results.append(exercise)
        return results

    def _parse_single_segment(self, segment: str) -> dict | None:
        """解析单个片段为一个动作。

        匹配模式如「臀桥 3 组 12 次」「做了靠墙静蹲 30 秒」。

        参数：
            segment: 单个训练片段文本。
        返回：
            动作草稿字典；无法识别时返回 None。
        """
        # 组数
        sets_match = re.search(r"(\d+)\s*组", segment)
        # 次数
        reps_match = re.search(r"(\d+)\s*次", segment)
        # 时长（秒）
        seconds_match = re.search(r"(\d+)\s*秒", segment)
        # 重量
        weight_match = re.search(r"(\d+(?:\.\d+)?)\s*kg", segment)

        # 动作名 = 数量单位之前的连续中文/字母片段
        name = ""
        for match in (sets_match, reps_match, seconds_match, weight_match):
            if match and match.start() > 0:
                candidate = segment[: match.start()]
                # 循环去掉常见动词/时间前缀（做了/做/今天等）
                prefix = re.compile(r"^(今天|昨天|做了|做|然后|再加|进行|开始|训练)")
                prev = None
                while candidate != prev:
                    prev = candidate
                    candidate = prefix.sub("", candidate).strip()
                if candidate:
                    name = candidate
                    break

        if not name:
            return None

        return {
            "exercise_name": name,
            "sets": int(sets_match.group(1)) if sets_match else None,
            "reps": int(reps_match.group(1)) if reps_match else None,
            "duration_seconds": int(seconds_match.group(1)) if seconds_match else None,
            "weight": f"{weight_match.group(1)}kg" if weight_match else "",
            "note": "",
        }

    def _extract_section(self, text: str, keywords: list[str]) -> str:
        """从文本中提取含某类关键词的句子。

        参数：
            text: 训练描述文本。
            keywords: 关键词列表。
        返回：
            匹配的句子片段，无则空字符串。
        """
        sentences = re.split(r"[。\n]+", text)
        for sentence in sentences:
            if any(kw in sentence for kw in keywords) and len(sentence) < 60:
                return sentence.strip()
        return ""
