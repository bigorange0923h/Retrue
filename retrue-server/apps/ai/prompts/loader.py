"""提示词模板加载与渲染工具。

模板以独立文件存放于 apps/ai/prompts/ 目录（*.txt），与业务代码解耦。
支持两类使用方式：
    - load_prompt(name)          读取原始模板字符串。
    - render_prompt(name, **kw)  读取模板并用 str.format 注入动态内容。

说明：
    - 模板内的占位符使用 {var} 语法，与 str.format 一致。
    - 若模板中包含字面量花括号（如 JSON 示例），请用 {{ }} 转义。
    - 提供模块级缓存，避免每次调用重复读盘；文件内容变更需重启进程生效。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

#: 提示词模板根目录
PROMPT_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """按文件名读取提示词模板（自动补充 .txt 后缀）。

    参数：
        name: 模板名，如 "rag_system"；可带或不带 .txt 后缀。
    返回：
        模板原始字符串。
    异常：
        FileNotFoundError: 模板文件不存在。
    """
    filename = name if name.endswith(".txt") else f"{name}.txt"
    path = PROMPT_DIR / filename
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **kwargs) -> str:
    """读取模板并渲染动态内容。

    参数：
        name: 模板名。
        **kwargs: 注入到 {var} 占位符的内容。
    返回：
        渲染后的字符串。
    异常：
        KeyError: 模板包含未提供的占位符。
    """
    template = load_prompt(name)
    return template.format(**kwargs)
