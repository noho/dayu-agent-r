"""XBRL concept 执行与 processor 结果契约真源。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias, TypedDict, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import (
    FinancialDataQuality,
    normalize_financial_data_quality,
)


XbrlQueryReason: TypeAlias = Literal["xbrl_not_available", "query_partially_failed"]
"""XBRL 查询降级原因的封闭业务值。"""

_XBRL_QUERY_REASONS: Final[frozenset[str]] = frozenset(
    {"xbrl_not_available", "query_partially_failed"}
)


class XbrlFactsResult(TypedDict):
    """processor 产生的完整 XBRL facts 结果。"""

    query_params: dict[str, JsonValue]
    facts: list[dict[str, JsonValue]]
    total: int
    data_quality: FinancialDataQuality
    reason: XbrlQueryReason | None


XbrlFactsPayload: TypeAlias = Mapping[str, JsonValue] | XbrlFactsResult
"""校验边界接收的 JSON mapping 或强类型 producer 结果。"""


@dataclass(frozen=True)
class XbrlConceptQuerySummary:
    """一次多 concept XBRL 查询的有界执行汇总。"""

    rows: list[dict[str, JsonValue]]
    attempted_concepts: tuple[str, ...]
    successful_concepts: tuple[str, ...]
    failed_concepts: tuple[str, ...]


class XbrlQueryExecutionError(RuntimeError):
    """所有可执行 XBRL concept 均失败。"""

    def __init__(self, failed_concepts: tuple[str, ...]) -> None:
        """初始化全失败异常。

        Args:
            failed_concepts: 已失败的有界 concept 本地名。

        Returns:
            无。

        Raises:
            ValueError: 失败 concept 集合为空时抛出。
        """

        if not failed_concepts:
            raise ValueError("XBRL 全失败异常必须包含 failed concepts")
        self.failed_concepts = failed_concepts
        super().__init__("XBRL concept 查询执行失败")


@dataclass(frozen=True)
class ValidatedXbrlFactsResult:
    """已通过 producer contract 的 XBRL facts 结果。"""

    query_params: dict[str, JsonValue]
    facts: list[dict[str, JsonValue]]
    total: int
    data_quality: FinancialDataQuality
    reason: XbrlQueryReason | None


def validate_xbrl_facts_result_payload(
    payload: XbrlFactsPayload,
) -> ValidatedXbrlFactsResult:
    """校验并复制 processor XBRL facts 原始结果。

    Args:
        payload: processor ``query_xbrl_facts`` 返回的原始 JSON 对象。

    Returns:
        满足 raw total、质量与原因不变量的强类型结果。

    Raises:
        ValueError: 字段缺失、JSON shape 非法、raw total 不一致、夹带 read-side
            去重字段或质量矩阵冲突时抛出。
    """

    if "deduped_fact_count" in payload:
        raise ValueError("XBRL producer result 不得包含 read-side deduped_fact_count")
    query_params = _required_json_object(payload, "query_params")
    facts = _required_json_object_list(payload, "facts")
    total = _required_non_negative_int(payload, "total")
    if total != len(facts):
        raise ValueError("XBRL facts result total 必须等于 raw facts 数量")
    data_quality = _required_financial_data_quality(payload, "data_quality")
    reason = _required_xbrl_reason(payload, "reason")
    if data_quality == "partial" and reason is None:
        raise ValueError("XBRL partial result 必须提供 reason")
    if data_quality != "partial" and reason is not None:
        raise ValueError("XBRL 完整结果的 reason 必须为 None")
    if data_quality == "extracted":
        raise ValueError("XBRL query result 不得声明 extracted")
    if reason == "xbrl_not_available" and facts:
        raise ValueError("XBRL 不可用结果不得包含 facts")
    return ValidatedXbrlFactsResult(
        query_params=query_params,
        facts=facts,
        total=total,
        data_quality=data_quality,
        reason=reason,
    )


def _require_field(payload: XbrlFactsPayload, field_name: str) -> JsonValue:
    """读取必填字段并区分缺失与显式 ``null``。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        字段值。

    Raises:
        ValueError: 字段缺失时抛出。
    """

    if field_name not in payload:
        raise ValueError(f"XBRL facts result 缺少必填字段: {field_name}")
    return cast(JsonValue, payload[field_name])


def _required_json_object(
    payload: XbrlFactsPayload,
    field_name: str,
) -> dict[str, JsonValue]:
    """读取并复制必填 JSON object 字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        独立复制的 JSON object。

    Raises:
        ValueError: 字段不是合法 JSON object 时抛出。
    """

    value = _require_field(payload, field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"XBRL facts result {field_name} 必须为对象")
    copied = dict(value)
    if any(not isinstance(key, str) or not _is_json_value(item) for key, item in copied.items()):
        raise ValueError(f"XBRL facts result {field_name} 必须为合法 JSON 对象")
    return copied


def _required_json_object_list(
    payload: XbrlFactsPayload,
    field_name: str,
) -> list[dict[str, JsonValue]]:
    """读取并复制必填 JSON object 数组。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        独立复制的对象列表。

    Raises:
        ValueError: 字段不是合法 JSON object 数组时抛出。
    """

    value = _require_field(payload, field_name)
    if not isinstance(value, list):
        raise ValueError(f"XBRL facts result {field_name} 必须为数组")
    result: list[dict[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"XBRL facts result {field_name} 元素必须为对象")
        copied = dict(item)
        if any(not isinstance(key, str) or not _is_json_value(entry) for key, entry in copied.items()):
            raise ValueError(f"XBRL facts result {field_name} 必须为合法 JSON 对象数组")
        result.append(copied)
    return result


def _required_non_negative_int(payload: XbrlFactsPayload, field_name: str) -> int:
    """读取必填非负整数。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        非负整数。

    Raises:
        ValueError: 字段不是非负整数时抛出。
    """

    value = _require_field(payload, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"XBRL facts result {field_name} 必须为非负整数")
    return value


def _required_financial_data_quality(
    payload: XbrlFactsPayload,
    field_name: str,
) -> FinancialDataQuality:
    """读取必填财务质量字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        canonical 财务质量。

    Raises:
        ValueError: 字段不是合法质量值时抛出。
    """

    value = _require_field(payload, field_name)
    if not isinstance(value, str):
        raise ValueError(f"XBRL facts result {field_name} 必须为字符串")
    return normalize_financial_data_quality(value, field_name=f"XBRL facts result {field_name}")


def _required_xbrl_reason(
    payload: XbrlFactsPayload,
    field_name: str,
) -> XbrlQueryReason | None:
    """读取必填可空 XBRL 降级原因。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        canonical 原因或 ``None``。

    Raises:
        ValueError: 字段缺失或原因不在封闭集合时抛出。
    """

    value = _require_field(payload, field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value not in _XBRL_QUERY_REASONS:
        raise ValueError(f"XBRL facts result {field_name} 非法")
    return cast(XbrlQueryReason, value)


def _is_json_value(value: JsonValue) -> bool:
    """递归判断值是否满足有限 JSON 语义。

    Args:
        value: 待检查值。

    Returns:
        值可安全作为 JSON 时返回 ``True``。

    Raises:
        无。
    """

    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


__all__ = [
    "ValidatedXbrlFactsResult",
    "XbrlConceptQuerySummary",
    "XbrlFactsPayload",
    "XbrlFactsResult",
    "XbrlQueryExecutionError",
    "XbrlQueryReason",
    "validate_xbrl_facts_result_payload",
]
