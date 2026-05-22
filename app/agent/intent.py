"""
用户意图分类工具

在进入问数链路前，模型会把用户原始问题分类成数据查询、普通对话或危险意图
本文件只保留结构化结果和业务校验，不负责解析模型文本
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class IntentCategory(StrEnum):
    """入口意图分类"""

    DATA_QUERY = "data_query" 
    GENERAL_CHAT = "general_chat"
    UNSAFE = "unsafe"


@dataclass(frozen=True)
class IntentDecision:
    """一次意图判断的结构化结果"""

    category: IntentCategory # 意图分类
    reason: str # 意图分类原因
    matched_terms: list[str] = field(default_factory=list) # 命中线索


def parse_intent_payload(payload: object) -> IntentDecision:
    """将 JSON 对象转换成意图分类结果"""

    if not isinstance(payload, Mapping):
        raise ValueError("意图分类结果必须是 JSON 对象")
    # 读取分类
    category = _category_from_value(payload.get("category"))
    # 读取原因
    reason = str(payload.get("reason") or "模型完成意图分类。")
    # 命中线索
    matched_terms = payload.get("matched_terms") or []
    if not isinstance(matched_terms, list):
        matched_terms = []

    return IntentDecision(
        category=category,
        reason=reason,
        matched_terms=[str(term) for term in matched_terms],
    )


def _category_from_value(value: object) -> IntentCategory:
    """从字符串值创建意图分类"""
    try:
        return IntentCategory(str(value))
    except ValueError:
        raise ValueError(f"未知意图分类：{value}") from None
