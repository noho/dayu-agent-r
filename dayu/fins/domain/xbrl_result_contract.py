"""XBRL processor 结果契约校验。

该模块持有 `query_xbrl_facts` 原始结果的 producer contract：
processor 负责给出完整 raw facts、raw total 与查询参数；read runtime
只能在该契约通过后做投影清洗和去重，不能重算或覆盖 processor-owned 字段。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Optional

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import FinancialDataQuality, normalize_financial_data_quality


@dataclass(frozen=True)
class ValidatedXbrlFactsResult:
    """已通过 raw XBRL facts processor contract 的结果。"""

    query_params: Mapping[str, JsonValue]
    facts: list[JsonValue]
    total: int
    data_quality: Optional[FinancialDataQuality]
    reason: Optional[str]


def validate_xbrl_facts_result_payload(payload: Mapping[str, JsonValue]) -> ValidatedXbrlFactsResult:
    """校验 XBRL facts processor 原始返回契约。

    Args:
        payload: processor `query_xbrl_facts` 返回的原始 JSON 对象。

    Returns:
        已校验的 typed raw result。

    Raises:
        ValueError: 必填字段缺失、字段类型非法、`total` 与 raw `facts` 长度不一致，
            或可选字段语义非法时抛出。
    """

    query_params = _required_json_object(payload, "query_params")
    facts = _required_json_list(payload, "facts")
    total = _required_json_int(payload, "total")
    if total != len(facts):
        raise ValueError("XBRL facts result total 必须等于 raw facts 数量")
    data_quality = _optional_financial_data_quality(payload, "data_quality")
    reason = _optional_non_empty_string(payload, "reason")
    return ValidatedXbrlFactsResult(
        query_params=query_params,
        facts=facts,
        total=total,
        data_quality=data_quality,
        reason=reason,
    )


def _required_json_object(payload: Mapping[str, JsonValue], field_name: str) -> Mapping[str, JsonValue]:
    """读取必填 JSON object 字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        字段对应的 JSON object。

    Raises:
        ValueError: 字段缺失、不是对象或 key 不是字符串时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"XBRL facts result {field_name} 必须为对象")
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"XBRL facts result {field_name} 的 key 必须为字符串")
    return value


def _required_json_list(payload: Mapping[str, JsonValue], field_name: str) -> list[JsonValue]:
    """读取必填 JSON array 字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        字段对应的 JSON array。

    Raises:
        ValueError: 字段缺失或不是数组时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"XBRL facts result {field_name} 必须为数组")
    return value


def _required_json_int(payload: Mapping[str, JsonValue], field_name: str) -> int:
    """读取必填 JSON integer 字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        字段对应的整数。

    Raises:
        ValueError: 字段缺失、不是整数、为布尔值或小于 0 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"XBRL facts result {field_name} 必须为整数")
    if value < 0:
        raise ValueError(f"XBRL facts result {field_name} 不能为负数")
    return value


def _optional_financial_data_quality(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> Optional[FinancialDataQuality]:
    """读取可选财务数据质量字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        字段不存在时返回 `None`，存在时返回 canonical 财务数据质量。

    Raises:
        ValueError: 字段存在但不是字符串或枚举值非法时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"XBRL facts result {field_name} 必须为字符串")
    return normalize_financial_data_quality(value, field_name=f"XBRL facts result {field_name}")


def _optional_non_empty_string(payload: Mapping[str, JsonValue], field_name: str) -> Optional[str]:
    """读取可选非空字符串字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        字段不存在时返回 `None`，存在时返回去除首尾空白后的字符串。

    Raises:
        ValueError: 字段存在但不是字符串或为空时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"XBRL facts result {field_name} 必须为字符串")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"XBRL facts result {field_name} 不能为空")
    return normalized


__all__ = [
    "ValidatedXbrlFactsResult",
    "validate_xbrl_facts_result_payload",
]
