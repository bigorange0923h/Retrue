"""Mock AI provider。

真实服务商尚未确定，先用确定性规则解析训练自然语言文本，
返回符合 TrainingDraft schema 的结构化草稿。接入真实模型后替换。
"""

from __future__ import annotations

import json
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

        text = self._normalize_count_tokens(text.strip())
        exercises = self._extract_exercises(text)

        # 感受只保留「感觉/感受」之后的内容，避免把姓名和训练项目一并
        # 填进反馈字段。
        feedback = self._extract_feedback(text)
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
        # 每个分号/句号分隔段可包含多个动作。逗号后的「每组 X 次」等
        # 修饰语需要与前一动作合并，而下一个独立动作仍应单独保留。
        for sentence in re.split(r"[;；。\n]+", text):
            clauses = [clause.strip() for clause in re.split(r"[，,]+", sentence) if clause.strip()]
            current = ""
            for clause in clauses:
                if current and re.match(r"^(?:每\s*组|有\s*\d+\s*组|共\s*\d+\s*组)", clause):
                    current = f"{current}，{clause}"
                    continue
                if current:
                    exercise = self._parse_single_segment(current)
                    if exercise:
                        results.append(exercise)
                current = clause
            if current:
                exercise = self._parse_single_segment(current)
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
        # 动作紧跟在"做了/练了"等动词后；姓名、日期等前缀不会进入动作名。
        # "做完感觉……"是反馈，不是新的训练动作；末尾的单字"做"仅匹配
        # 不跟"完"的情形，以兼容"做 臀桥 3 组"。
        action_match = re.search(r"(?:做了|练了|训练了|进行了|完成了|做(?!完))\s*(?P<body>[^，,；;。\n]+)", segment)
        if action_match:
            body = action_match.group("body").strip()
        else:
            # 后续独立动作常省略动词，如"靠墙静蹲 30 秒"。没有任何训练
            # 数量时则不把反馈性文字误判为动作。
            if not re.search(r"\d+\s*(?:组|次|秒|kg)", segment):
                return None
            body = segment.strip()
        # 支持「三组臀桥」和「臀桥三组」两种常见口述。
        leading_sets = re.match(r"(?:有\s*)?(?P<sets>\d+)\s*组\s*(?P<name>[\u4e00-\u9fffA-Za-z]+)", body)
        if leading_sets:
            name = leading_sets.group("name")
        else:
            name_match = re.match(r"(?P<name>[\u4e00-\u9fffA-Za-z]+)", body)
            name = name_match.group("name") if name_match else ""
        if not name:
            return None

        # 组数和每组次数可出现在后续逗号分隔的修饰片段中，因此从整句提取。
        sets_match = re.search(r"(?:有|共)?\s*(\d+)\s*组", segment)
        reps_match = re.search(r"每\s*组\s*(\d+)\s*次", segment)
        if reps_match is None:
            paired_reps = re.search(r"\d+\s*组\s*(\d+)\s*次", segment)
            reps_match = paired_reps
        # 时长（秒）
        seconds_match = re.search(r"(\d+)\s*秒", segment)
        # 重量
        weight_match = re.search(r"(\d+(?:\.\d+)?)\s*kg", segment)

        return {
            "exercise_name": name,
            "activity_type": "exercise",
            "sets": int(sets_match.group(1)) if sets_match else None,
            "reps": int(reps_match.group(1)) if reps_match else None,
            "duration_seconds": int(seconds_match.group(1)) if seconds_match else None,
            "weight": f"{weight_match.group(1)}kg" if weight_match else "",
            "note": "",
        }

    @staticmethod
    def _normalize_count_tokens(text: str) -> str:
        """将紧邻单位的中文数字归一为阿拉伯数字，例如"三组""十次"。"""
        digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

        def to_number(value: str) -> int:
            if value == "十":
                return 10
            if "十" in value:
                head, tail = value.split("十", 1)
                return (digits.get(head, 1) if head else 1) * 10 + (digits.get(tail, 0) if tail else 0)
            return digits.get(value, 0)

        return re.sub(
            r"([零一二三四五六七八九十两]+)\s*(组|次|秒)",
            lambda match: f"{to_number(match.group(1))}{match.group(2)}",
            text,
        )

    @staticmethod
    def _extract_feedback(text: str) -> str:
        """提取客户感受，去除训练动作和口语前缀。"""
        match = re.search(r"(?:做完(?:之后)?|自己做完)?\s*(?:感觉|感受)\s*(.+?)(?:[。\n]|$)", text)
        return match.group(1).strip(" ，,。") if match else ""

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

    def parse_assessment_text(self, text: str) -> dict:
        """规则式解析评估草稿（离线可用）。"""
        return {
            "assessment_type": "reassessment" if any(k in text for k in ("复评", "复查", "进展")) else "initial",
            "assessment_date": date.today().isoformat(),
            "chief_complaint": self._extract_section(text, ["主诉", "问题", "疼", "痛"]) or text[:120],
            "medical_history": self._extract_section(text, ["病史", "既往", "手术"]) or "",
            "rehab_goal": self._extract_section(text, ["目标", "希望", "想"]) or "",
            "current_status": self._extract_section(text, ["目前", "现在", "近期"]) or "",
            "note": "",
        }

    def parse_followup_text(self, text: str) -> dict:
        """规则式解析随访草稿（离线可用）。"""
        followup_type = "review" if any(k in text for k in ("复查", "复诊")) else "visit"
        return {
            "followup_type": followup_type,
            "due_date": date.today().isoformat(),
            "content": text[:200],
        }

    def parse_training_revision_text(self, text: str) -> dict:
        """规则式解析训练修订草稿（离线可用）。"""
        return {
            "training_date": date.today().isoformat(),
            "customer_feedback": self._extract_section(text, ["感觉", "感受"]) or "",
            "therapist_observation": self._extract_section(text, ["观察", "评估"]) or "",
            "next_plan": self._extract_section(text, ["下次", "下一步", "接下来"]) or "",
            "note": "",
        }

    def parse_multi_customer_text(self, text: str) -> dict:
        """规则式解析多客户训练补记拆分（离线可用）。

        复用共享分段器 split_training_segments 按"客户训练起点"切段（与意图层
        多客户判定的分段一致，保证单/多客户判定与实际拆分不脱节）；每个子项内
        再按逗号/顿号拆分活动，并做简单的组数/次数/数量识别。仅用于离线测试与
        兜底，真实模型应覆盖为结构化调用。
        """
        from apps.ai.segmentation import split_training_segments

        chunks = split_training_segments(text)
        items: list[dict] = []
        for index, (name, content) in enumerate(chunks, start=1):
            activities = self._split_activities(content)
            items.append(
                {
                    "sequence": index,
                    "customer_name_hint": name,
                    "activities": activities,
                }
            )
        return {"intent": "multi_customer_training_record", "confidence": 0.9, "items": items}

    def _split_activities(self, content: str) -> list[dict]:
        """把一段内容按逗号/顿号/分号拆成活动项，并把"每组X次/共Y组"合并到前一个动作。"""
        segments = re.split(r"[，,、;；]", content)
        activities: list[dict] = []
        for segment in segments:
            segment = segment.strip().strip("。.")
            if not segment:
                continue
            # 组数/次数修饰片段合并到上一个活动。
            if re.fullmatch(r"(共\s*\d+\s*组|每[组次]\s*\d+\s*次)", segment):
                if activities:
                    self._merge_modifier(activities[-1], segment)
                continue
            activities.append(self._parse_activity(segment))
        return activities

    def _merge_modifier(self, activity: dict, segment: str) -> None:
        """把"共X组/每组X次"合并进活动。"""
        group_match = re.search(r"共\s*(\d+)\s*组", segment)
        if group_match:
            activity["sets"] = int(group_match.group(1))
            activity["unit"] = "次/组" if activity.get("reps") is not None else "组"
        per_match = re.search(r"每[组次]\s*(\d+)\s*次", segment)
        if per_match:
            activity["reps"] = int(per_match.group(1))
            activity["unit"] = "次/组"

    def _parse_activity(self, segment: str) -> dict:
        """解析单个活动：名称 + 可能的组数/次数/数量。"""
        for _ in range(3):
            new_segment = re.sub(r"^(今天|昨天|做了|做|进行了|完成|刚刚|刚)", "", segment).strip()
            if new_segment == segment:
                break
            segment = new_segment
        activity_type = "therapy" if ("按摩" in segment or "治疗" in segment or "理疗" in segment) else "exercise"
        sets = None
        reps = None
        quantity = None
        unit = ""
        group_match = re.search(r"共\s*(\d+)\s*组", segment)
        if group_match:
            sets = int(group_match.group(1))
        per_match = re.search(r"每[组次]\s*(\d+)\s*次", segment)
        if per_match:
            reps = int(per_match.group(1))
        count_match = re.search(r"(\d+)\s*([次组个下])", segment)
        if count_match:
            value = int(count_match.group(1))
            unit = count_match.group(2)
            if activity_type in {"therapy", "massage"}:
                quantity = value
            elif sets is None and reps is None:
                reps = value
        name = re.sub(r"共\s*\d+\s*组|每[组次]\s*\d+\s*次|\d+\s*[次组个下]", "", segment)
        name = name.strip("，,。.；;：: ")
        return {
            "name": name or segment,
            "activity_type": activity_type,
            "sets": sets,
            "reps": reps,
            "quantity": quantity,
            "unit": unit,
            "duration": None,
        }

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
        if system and "长期记忆评估器" in system:
            return self._evaluate_memory_candidate(prompt)
        if system and "对话摘要器" in system:
            return self._summarize_conversation(prompt)
        if system and "历史讨论事件提取器" in system:
            return self._extract_episode(prompt)
        return "（Mock 回答）我已阅读检索到的知识库信息，请问还需了解什么？"

    def _summarize_conversation(self, prompt: str) -> str:
        """用截断文本模拟滚动摘要，供本地环境验证长对话闭环。"""
        existing = prompt.split("已有摘要：", 1)[-1].split("本次需要压缩", 1)[0].strip()
        new_messages = prompt.split("本次需要压缩进摘要的旧消息：", 1)[-1].split("请输出", 1)[0].strip()
        parts = [] if existing == "暂无摘要" else [existing]
        parts.append(f"新增历史消息：{new_messages[:500]}")
        return "\n".join(parts)[:800]

    def _extract_episode(self, prompt: str) -> str:
        """模拟从包含明确讨论决定的长对话中提取 Episode。"""
        if not any(keyword in prompt for keyword in ["决定", "下一步", "讨论", "调整"]):
            return json.dumps({"episodes": []}, ensure_ascii=False)
        episode = {
            "episode_key": "mock_discussion_event",
            "title": "重要康复讨论",
            "summary": "康复师与 AI 对客户情况进行了讨论并形成后续安排。",
            "key_points": ["对话中出现了需要长期回顾的客户信息"],
            "decisions": ["按讨论结果调整后续安排"],
            "next_actions": ["后续训练中继续观察"],
            "importance_score": 3,
            "confidence": 0.85,
        }
        return json.dumps({"episodes": [episode]}, ensure_ascii=False)

    def _evaluate_memory_candidate(self, prompt: str) -> str:
        """用确定性规则模拟偏好类记忆提取，便于本地打通确认闭环。"""
        marker = "需要分析的康复师消息："
        content = prompt.split(marker, 1)[-1].split("请输出：", 1)[0].strip()
        match = re.search(r"(?:客户|用户|他|她)?(?:现在|目前|已经)*\s*(不喜欢|喜欢)([\u4e00-\u9fa5A-Za-z0-9]{1,16})", content)
        if not match:
            return json.dumps({"candidates": []}, ensure_ascii=False)
        stance, topic = match.groups()
        topic = re.sub(r"(?:了|啦|这项训练|这个动作)$", "", topic).strip()
        if not topic:
            return json.dumps({"candidates": []}, ensure_ascii=False)
        memory_key = f"exercise_preference.{topic}"
        existing_section = prompt.split("现有有效记忆：", 1)[-1].split(marker, 1)[0]
        relation = "conflict" if memory_key in existing_section else "new"
        memory_type = "dislike" if stance == "不喜欢" else "preference"
        candidate = {
            "classification": "customer_memory",
            "memory_type": memory_type,
            "memory_key": memory_key,
            "content": f"客户目前{stance}{topic}",
            "normalized_value": f"{stance}{topic}",
            "confidence": 0.9,
            "importance_score": 3,
            "evidence": content[:200],
            "relation": relation,
        }
        return json.dumps({"candidates": [candidate]}, ensure_ascii=False)

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
