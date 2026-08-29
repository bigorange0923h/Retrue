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

    name = "mock"

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

    def chat(self, prompt: str, system: str | None = None) -> str:
        """通用对话能力（Mock 实现）。

        返回基于 prompt 的确定性回复，用于在真实 LLM 接入前打通 RAG 流程。
        若 prompt 中包含"知识库"片段则复述其第一条作为模拟回答。

        参数：
            prompt: 用户侧消息。
            system: 可选的系统提示。
        返回：
            模拟文本回答。
        """
        return "（Mock 回答）我已阅读检索到的知识库信息，请问还需了解什么？"

    def prepare_lesson(self, summary: dict) -> dict:
        """基于客户历史汇总生成备课建议（规则启发式）。

        参数：
            summary: 客户历史数据汇总，含 pain、last_record、next_plan、
                     current_stage、note 等。
        返回：
            备课建议字典。
        """
        suggestions = []
        risk_reminders = []
        # 疼痛描述来自客户反馈（含 NRS 评分）
        pain = summary.get("customer_feedback") or summary.get("pain") or ""
        stage = summary.get("current_stage") or ""

        # 基于疼痛生成建议与风险
        if "NRS" in pain or any(kw in pain for kw in ["疼", "痛"]):
            suggestions.append("重点检查疼痛部位，评估当前疼痛等级变化")
            if "NRS" in pain:
                try:
                    score = int(pain.split("NRS")[-1].strip().split(" ")[0])
                    if score >= 6:
                        risk_reminders.append(f"⚠️ 当前疼痛 NRS {score} 较高，建议谨慎增加负荷")
                except (ValueError, IndexError):
                    pass

        # 基于阶段给出训练思路
        if stage:
            stage_plan = {
                "急性期/疼痛控制": "以疼痛控制与保护性训练为主，避免诱发疼痛",
                "恢复期/活动度恢复": "注重活动度恢复与轻度力量训练",
                "力量重建期": "逐步增加力量训练强度",
                "功能回归期": "聚焦功能性动作与专项回归",
            }
            for key, advice in stage_plan.items():
                if key in stage:
                    suggestions.append(advice)
                    break

        # 基于上次计划生成延续建议
        next_plan = summary.get("next_plan") or ""
        if next_plan:
            suggestions.append(f"延续上次计划方向：{next_plan}")

        if not suggestions:
            suggestions.append("回顾客户上次训练记录与当前情况后制定本次方案")

        return {
            "suggested_checks": suggestions,
            "recommended_tests": [],
            "recommended_parts": [],
            "training_approach": suggestions[0] if suggestions else "",
            "risk_reminders": risk_reminders,
        }
