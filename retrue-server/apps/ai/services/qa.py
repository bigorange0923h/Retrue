"""专业问答服务。

在真实 AI 接入前，提供基于内部知识库（动作库）的轻量问答。
限定在康复专业范围，不回答非康复问题。
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser

from apps.exercises.models import Exercise


def answer_question(therapist: AbstractUser, question: str) -> dict:
    """回答专业问题。

    参数：
        therapist: 当前康复师。
        question: 用户提出的问题。
    返回：
        含 question、answer、sources 的字典。
    """
    question = (question or "").strip()

    # 识别问题中提到的动作名（问题包含动作名），从动作库检索知识
    sources = []
    for exercise in Exercise.objects.filter(is_official=True):
        if exercise.name and exercise.name in question:
            sources.append({
                "name": exercise.name,
                "body_part": exercise.body_part,
                "description": exercise.description,
                "precautions": exercise.precautions,
            })
            if len(sources) >= 5:
                break

    if sources:
        # 基于动作库生成答案
        first = sources[0]
        answer = (
            f"关于「{first['name']}」："
            f"{first['description'] or '该动作用于康复训练。'}"
            + (f"训练部位：{first['body_part']}。" if first['body_part'] else "")
            + (f"注意事项：{first['precautions']}。" if first['precautions'] else "")
        )
        return {"question": question, "answer": answer, "sources": sources}

    # 通用引导
    return {
        "question": question,
        "answer": "请在问题中明确动作名称或部位，我可以在动作库中为你提供相关知识。医学诊断与治疗建议请以专业康复师判断为准。",
        "sources": [],
    }
