"""customers：客户目录与文本匹配领域服务。

职责：
    - 仅加载当前康复师的最小客户目录（正式名 + 别称 + 脱敏手机尾号）。
    - 对原文做受控、确定性、可解释的姓名匹配，绝不跨康复师、绝不猜测。
    - 输出结构化匹配结果：唯一命中(exact)/多候选(ambiguous)/无匹配(unmatched)。

约定：
    - 匹配结果只是「预选/候选」，不等同正式业务确认；写类流程仍须康复师确认。
    - 本模块不接收也不返回完整手机号；仅暴露脱敏手机号与后四位可选匹配。
    - 别称表本期仅建表 + 迁移，维护入口后续补；这里读取已存在的别名用于匹配。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from django.contrib.auth.models import AbstractUser

from apps.customers.models import Customer, CustomerAlias

# 称谓词：匹配时从原文与名称键中移除，不作为姓名的一部分。
_HONORIFICS = ("客户", "病人", "患者")

# 匹配结果置信档位。
CONF_EXACT = "exact"
CONF_AMBIGUOUS = "ambiguous"

# 匹配状态。
STATUS_EXACT = "exact"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNMATCHED = "unmatched"

# 手机尾号正则（纯数字后四位）。
_PHONE_TAIL_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


@dataclass(frozen=True)
class CustomerDirectoryEntry:
    """目录最小条目：仅用于匹配展示，不含完整手机号与病史。"""

    id: int
    name: str
    aliases: list[str] = field(default_factory=list)
    phone_masked: str = ""


@dataclass(frozen=True)
class CustomerMatch:
    """原文中的一个命中片段。"""

    customer_id: int
    matched_key: str
    start_offset: int
    end_offset: int
    confidence: str


@dataclass(frozen=True)
class MatchResult:
    """一次文本匹配的结构化结果。

    status: exact / ambiguous / unmatched。
    customer_id: exact 时唯一命中客户主键；其余为 None。
    candidates: ambiguous 时的候选列表（按原文位置排序）。
    matched_key: exact 时命中的目录键（正式名或别称）。
    """

    status: str
    customer_id: int | None = None
    candidates: list[CustomerMatch] = field(default_factory=list)
    matched_key: str = ""

    @property
    def is_exact(self) -> bool:
        return self.status == STATUS_EXACT

    @property
    def is_ambiguous(self) -> bool:
        return self.status == STATUS_AMBIGUOUS

    @property
    def is_unmatched(self) -> bool:
        return self.status == STATUS_UNMATCHED


def normalize_name(text: str) -> str:
    """规范化名称或原文片段为匹配键。

    步骤：去首尾空白 → 移除称谓词（客户/病人/患者）→ NFKC → 统一英文小写 → 去除空白。
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", str(text)).strip()
    for honorific in _HONORIFICS:
        value = value.replace(honorific, "")
    value = re.sub(r"\s+", "", value).lower()
    return value


def load_therapist_customer_directory(therapist: AbstractUser) -> list[CustomerDirectoryEntry]:
    """仅加载当前康复师的最小客户目录。

    返回字段：id、name、aliases、phone_masked（绝不包含完整手机号）。
    """
    entries: list[CustomerDirectoryEntry] = []
    customers = Customer.objects.filter(therapist=therapist)
    alias_rows = CustomerAlias.objects.filter(therapist=therapist).select_related("customer")
    alias_map: dict[int, list[str]] = {}
    for row in alias_rows:
        alias_map.setdefault(row.customer_id, []).append(row.alias)
    for customer in customers:
        entries.append(
            CustomerDirectoryEntry(
                id=customer.id,
                name=customer.name,
                aliases=alias_map.get(customer.id, []),
                phone_masked=customer.phone_masked,
            )
        )
    return entries


def match_customers_in_text(therapist: AbstractUser, text: str, phone_tail: str = "") -> MatchResult:
    """在当前康复师目录中匹配原文中的客户姓名。

    步骤：
        1. 加载最小目录。
        2. 建立目录键（正式名 + 别称归一化）→ 客户 id 映射；记录歧义键。
        3. 在规范化原文中做不重叠、按位置排序、同起始取最长命中的匹配。
        4. 全部命中指向同一客户且无歧义键 → exact；否则 ambiguous。
        5. ambiguous 且给定手机尾号时可进一步唯一化。
    """
    entries = load_therapist_customer_directory(therapist)
    if not entries:
        return MatchResult(status=STATUS_UNMATCHED)

    # 目录键 -> (customer_id, 键原文)。同键指向多个客户则视为歧义键。
    key_map: dict[str, list[tuple[int, str]]] = {}
    for entry in entries:
        keys = [normalize_name(entry.name)] + [normalize_name(a) for a in entry.aliases]
        for key in keys:
            if not key:
                continue
            key_map.setdefault(key, []).append((entry.id, key))
    ambiguous_keys = {key for key, owners in key_map.items() if len({c for c, _ in owners}) > 1}

    normalized_text = normalize_name(text)
    if not normalized_text:
        return MatchResult(status=STATUS_UNMATCHED)

    # 收集所有键命中区间（end offset），用于不重叠贪心取最长。
    occurrences: list[CustomerMatch] = []
    for key, owners in key_map.items():
        start = 0
        while True:
            pos = normalized_text.find(key, start)
            if pos < 0:
                break
            conf = CONF_AMBIGUOUS if key in ambiguous_keys else CONF_EXACT
            # 歧义键只记录一次该位置，代表多个候选。
            occurrences.append(CustomerMatch(customer_id=None, matched_key=key, start_offset=pos, end_offset=pos + len(key), confidence=conf))
            start = pos + 1

    if not occurrences:
        return MatchResult(status=STATUS_UNMATCHED)

    # 按位置排序，同起始优先最长；贪心选不重叠命中。
    occurrences.sort(key=lambda m: (m.start_offset, -m.end_offset))
    selected: list[CustomerMatch] = []
    last_end = -1
    for m in occurrences:
        if m.start_offset >= last_end:
            selected.append(m)
            last_end = m.end_offset

    if not selected:
        return MatchResult(status=STATUS_UNMATCHED)

    # 唯一性判定。
    resolved_ids: list[int] = []
    ambiguous_seen = False
    for m in selected:
        if m.confidence == CONF_AMBIGUOUS:
            ambiguous_seen = True
            owners = key_map[m.matched_key]
            for cid, _ in owners:
                if cid not in resolved_ids:
                    resolved_ids.append(cid)
        else:
            owners = key_map[m.matched_key]
            cid = owners[0][0]
            if cid not in resolved_ids:
                resolved_ids.append(cid)

    # 手机尾号唯一化：仅在同名多候选且已给尾号时启用。
    tail = phone_tail.strip()
    if tail.isdigit() and len(resolved_ids) > 1:
        masked_to_tail = [
            cid
            for cid in resolved_ids
            if any(e.id == cid and e.phone_masked.endswith(tail) for e in entries)
        ]
        if len(masked_to_tail) == 1:
            return MatchResult(status=STATUS_EXACT, customer_id=masked_to_tail[0], matched_key="phone_tail")

    if ambiguous_seen or len(set(resolved_ids)) > 1:
        candidates = _build_candidates(entries, selected, resolved_ids)
        return MatchResult(status=STATUS_AMBIGUOUS, candidates=candidates)

    cid = resolved_ids[0]
    matched_key = selected[0].matched_key
    return MatchResult(status=STATUS_EXACT, customer_id=cid, matched_key=matched_key)


def _build_candidates(
    entries: list[CustomerDirectoryEntry],
    selected: list[CustomerMatch],
    resolved_ids: list[int],
) -> list[CustomerMatch]:
    """把歧义命中的多个客户整理成候选列表（含唯一命中者）。"""
    by_id = {e.id: e for e in entries}
    candidates: list[CustomerMatch] = []
    first = selected[0] if selected else None
    offset = first.start_offset if first else 0
    end = first.end_offset if first else 0
    for cid in resolved_ids:
        entry = by_id.get(cid)
        if entry is None:
            continue
        candidates.append(
            CustomerMatch(customer_id=cid, matched_key=entry.name, start_offset=offset, end_offset=end, confidence=CONF_AMBIGUOUS)
        )
    return candidates


def resolve_customers_from_text(therapist: AbstractUser, text: str, phone_tail: str = "") -> MatchResult:
    """编排层统一入口：加载目录并匹配文本中的客户身份。

    为编排层提供单一调用点；内部先看原文是否含手机尾号片段再匹配。
    """
    text = str(text or "").strip()
    # 若原文含 4 位独立数字段（常见于同名客户补充手机尾号），自动尝试用于唯一化。
    tail = phone_tail
    if not tail:
        m = _PHONE_TAIL_RE.search(text)
        if m:
            tail = m.group(1)
    return match_customers_in_text(therapist, text, phone_tail=tail)
