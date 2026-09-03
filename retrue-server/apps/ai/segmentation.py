"""AI 训练补记：训练语义分段（纯函数，provider/意图层共用）。

多客户批量补记不应靠"正则数名字片段"来判定，而应依据真实的训练语义分段：
把原文按"客户训练起点"切成若干段，每段对应一位客户；段数 >= 2 才算多客户。
本模块提供纯函数分段器，供：
    - 编排意图层判断是否多客户（_is_multi_customer）。
    - provider 拆分（mock.parse_multi_customer_text 复用同一 pattern，保证
      "判定与实际拆分一致"）。

约定：本模块不做客户目录匹配、不解析动作细节；只负责"按训练起点切段"。
"""

from __future__ import annotations

import re

# 训练叙述触发词：名称/称谓后必须紧跟这些词才算一个"客户训练段"的起点，
# 避免把普通叙述或寒暄误当客户名。
_TRAINING_START_TOKENS = r"(?:今天|昨日|昨天|刚刚|做了|练了|训练了|进行了|完成了)"

# 一个段的起点匹配：显式「客户/病人/患者 + 名称」或「独立出现的姓名」
# 后紧跟训练叙述触发词。保留"客户"前缀，供后续目录匹配（先精确、再去前缀）。
_SEGMENT_PATTERN = re.compile(
    r"(?:(?P<prefix>客户|病人|患者)(?P<explicit_name>[A-Za-z0-9]{1,12}?|[\u4e00-\u9fa5]{1,4}?)"
    r"|(?:^|(?<=[，,；;。\n]))(?P<bare_name>[\u4e00-\u9fa5]{2,4}?))"
    r"(?=%s)" % _TRAINING_START_TOKENS
)


def split_training_segments(text: str) -> list[tuple[str, str]]:
    """把原文按"客户训练起点"切成若干段。

    返回 `[(customer_name_hint, segment_content), ...]`，按原文出现顺序排列。
    段内容为该客户训练叙述片段；若原文不含任何训练段，返回空列表。
    """
    if not text:
        return []
    matches = list(_SEGMENT_PATTERN.finditer(text))
    segments: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        name = f"{match.group('prefix') or ''}{match.group('explicit_name') or match.group('bare_name')}"
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        segments.append((name, text[start:end]))
    return segments


__all__ = ["split_training_segments"]
