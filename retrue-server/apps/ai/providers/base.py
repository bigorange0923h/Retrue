"""AI provider 抽象基类。

定义所有 AI 供应商必须实现的接口，使业务层与具体模型解耦。
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """AI 供应商抽象基类。

    业务层仅依赖本接口，不感知具体模型 SDK。
    子类需实现 parse_training_text 方法。
    """

    @abstractmethod
    def parse_training_text(self, text: str) -> dict:
        """将自然语言训练描述解析为结构化草稿。

        参数：
            text: 康复师输入的自然语言训练描述。
        返回：
            结构化草稿字典，含 exercises、customer_feedback、
            therapist_observation、next_plan 等字段。
        异常：
            raise AIProviderError: 解析失败时抛出。
        """
        raise NotImplementedError


class AIProviderError(Exception):
    """AI 供应商调用异常。

    解析失败或调用异常时抛出，用于上层转换为用户可读的错误。
    """

    def __init__(self, message: str):
        """初始化异常。

        参数：
            message: 面向用户的中文错误消息。
        """
        super().__init__(message)
        self.message = message
