"""XBRL concept 执行与 processor 结果契约真源。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, NotRequired, TypeAlias, TypedDict, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import FISCAL_PERIODS, FiscalPeriod, normalize_fiscal_period


XbrlQueryReason: TypeAlias = Literal["xbrl_not_available", "query_partially_failed"]
"""XBRL 查询降级原因的封闭业务值。"""

XbrlDataQuality: TypeAlias = Literal["xbrl", "partial"]
"""XBRL producer 结果质量的封闭业务值。"""

_XBRL_QUERY_REASONS: Final[frozenset[str]] = frozenset(
    {"xbrl_not_available", "query_partially_failed"}
)
_XBRL_RESULT_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {"query_params", "facts", "data_quality"}
)
_XBRL_RESULT_OPTIONAL_KEYS: Final[frozenset[str]] = frozenset({"reason"})
_XBRL_QUERY_PARAM_REQUIRED_KEYS: Final[frozenset[str]] = frozenset({"concepts"})
_XBRL_QUERY_PARAM_OPTIONAL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "statement_type",
        "period_end",
        "fiscal_year",
        "fiscal_period",
        "min_value",
        "max_value",
    }
)


class XbrlQueryParams(TypedDict):
    """processor 实际执行的 XBRL 查询参数。"""

    concepts: list[str]
    statement_type: NotRequired[str]
    period_end: NotRequired[str]
    fiscal_year: NotRequired[int]
    fiscal_period: NotRequired[FiscalPeriod]
    min_value: NotRequired[int | float]
    max_value: NotRequired[int | float]


class XbrlFactsResult(TypedDict):
    """processor 产生的完整 XBRL facts 结果。"""

    query_params: XbrlQueryParams
    facts: list[dict[str, JsonValue]]
    data_quality: XbrlDataQuality
    reason: NotRequired[XbrlQueryReason]


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

    query_params: XbrlQueryParams
    facts: list[dict[str, JsonValue]]
    data_quality: XbrlDataQuality
    reason: XbrlQueryReason | None


def validate_xbrl_facts_result_payload(
    payload: XbrlFactsPayload,
) -> ValidatedXbrlFactsResult:
    """校验并复制 processor XBRL facts 原始结果。

    Args:
        payload: processor ``query_xbrl_facts`` 返回的原始 JSON 对象。

    Returns:
        满足查询参数、质量与原因不变量的强类型结果。

    Raises:
        ValueError: 字段缺失、未知字段、JSON shape 非法或质量矩阵冲突时抛出。
    """

    _validate_exact_keys(
        payload,
        required_keys=_XBRL_RESULT_REQUIRED_KEYS,
        optional_keys=_XBRL_RESULT_OPTIONAL_KEYS,
        context="XBRL facts result",
    )
    query_params = _required_query_params(payload)
    facts = _required_json_object_list(payload, "facts")
    data_quality = _required_xbrl_data_quality(payload, "data_quality")
    reason = _optional_xbrl_reason(payload, "reason")
    if data_quality == "partial" and reason is None:
        raise ValueError("XBRL partial result 必须提供 reason")
    if data_quality != "partial" and reason is not None:
        raise ValueError("XBRL 完整结果必须省略 reason")
    if reason == "xbrl_not_available" and facts:
        raise ValueError("XBRL 不可用结果不得包含 facts")
    return ValidatedXbrlFactsResult(
        query_params=query_params,
        facts=facts,
        data_quality=data_quality,
        reason=reason,
    )


def _validate_exact_keys(
    payload: Mapping[str, JsonValue] | XbrlFactsResult,
    *,
    required_keys: frozenset[str],
    optional_keys: frozenset[str],
    context: str,
) -> None:
    """校验 JSON 对象的必填键与可选键闭集。

    Args:
        payload: 待校验对象。
        required_keys: 必须存在的键。
        optional_keys: 允许缺席的键。
        context: 错误消息中的契约名称。

    Returns:
        无。

    Raises:
        ValueError: 必填键缺失或出现未知键时抛出。
    """

    actual_keys = frozenset(payload.keys())
    missing_keys = required_keys - actual_keys
    if missing_keys:
        raise ValueError(f"{context} 缺少必填字段: {', '.join(sorted(missing_keys))}")
    unknown_keys = actual_keys - required_keys - optional_keys
    if unknown_keys:
        raise ValueError(f"{context} 包含未知字段: {', '.join(sorted(unknown_keys))}")


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


def _required_query_params(payload: XbrlFactsPayload) -> XbrlQueryParams:
    """校验并复制必填的扁平 XBRL 查询参数。

    Args:
        payload: 原始 XBRL producer 结果。

    Returns:
        强类型、可选字段仅在输入存在时出现的查询参数。

    Raises:
        ValueError: 参数不是对象、键集或任一字段类型非法时抛出。
    """

    value = _require_field(payload, "query_params")
    if not isinstance(value, Mapping):
        raise ValueError("XBRL facts result query_params 必须为对象")
    _validate_exact_keys(
        value,
        required_keys=_XBRL_QUERY_PARAM_REQUIRED_KEYS,
        optional_keys=_XBRL_QUERY_PARAM_OPTIONAL_KEYS,
        context="XBRL query_params",
    )
    query_params = XbrlQueryParams(concepts=_required_concepts(value))

    statement_type = _optional_non_empty_string(value, "statement_type")
    if statement_type is not None:
        query_params["statement_type"] = statement_type
    period_end = _optional_non_empty_string(value, "period_end")
    if period_end is not None:
        query_params["period_end"] = period_end
    fiscal_year = _optional_positive_int(value, "fiscal_year")
    if fiscal_year is not None:
        query_params["fiscal_year"] = fiscal_year
    fiscal_period = _optional_fiscal_period(value)
    if fiscal_period is not None:
        query_params["fiscal_period"] = fiscal_period
    min_value = _optional_number(value, "min_value")
    if min_value is not None:
        query_params["min_value"] = min_value
    max_value = _optional_number(value, "max_value")
    if max_value is not None:
        query_params["max_value"] = max_value
    return query_params


def _required_concepts(payload: Mapping[str, JsonValue]) -> list[str]:
    """校验并复制必填 concept 列表。

    Args:
        payload: 扁平 XBRL 查询参数。

    Returns:
        保持实际执行顺序的非空 concept 列表。

    Raises:
        ValueError: 字段缺失、不是数组或含空白/非字符串元素时抛出。
    """

    if "concepts" not in payload:
        raise ValueError("XBRL query_params 缺少必填字段: concepts")
    value = payload["concepts"]
    if not isinstance(value, list) or not value:
        raise ValueError("XBRL query_params concepts 必须为非空字符串数组")
    concepts: list[str] = []
    for concept in value:
        if not isinstance(concept, str) or not concept.strip() or concept != concept.strip():
            raise ValueError("XBRL query_params concepts 必须为非空字符串数组")
        concepts.append(concept)
    return concepts


def _optional_non_empty_string(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> str | None:
    """读取缺席或非空字符串参数。

    Args:
        payload: 扁平 XBRL 查询参数。
        field_name: 字段名。

    Returns:
        字段缺席时返回 ``None``，否则返回原字符串。

    Raises:
        ValueError: 字段存在但不是规范非空字符串时抛出。
    """

    if field_name not in payload:
        return None
    value = payload[field_name]
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"XBRL query_params {field_name} 必须为非空字符串")
    return value


def _optional_positive_int(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> int | None:
    """读取缺席或正整数参数。

    Args:
        payload: 扁平 XBRL 查询参数。
        field_name: 字段名。

    Returns:
        字段缺席时返回 ``None``，否则返回正整数。

    Raises:
        ValueError: 字段为 bool、非整数或非正数时抛出。
    """

    if field_name not in payload:
        return None
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"XBRL query_params {field_name} 必须为正整数")
    return value


def _optional_fiscal_period(payload: Mapping[str, JsonValue]) -> FiscalPeriod | None:
    """读取缺席或共享闭集内的财期参数。

    Args:
        payload: 扁平 XBRL 查询参数。

    Returns:
        字段缺席时返回 ``None``，否则返回共享 ``FiscalPeriod`` 值。

    Raises:
        ValueError: 字段不是 ``FISCAL_PERIODS`` 中的精确值时抛出。
    """

    field_name = "fiscal_period"
    if field_name not in payload:
        return None
    value = payload[field_name]
    if not isinstance(value, str) or value not in FISCAL_PERIODS:
        raise ValueError("XBRL query_params fiscal_period 非法")
    normalized = normalize_fiscal_period(value, field_name="XBRL query_params fiscal_period")
    if normalized is None:
        raise ValueError("XBRL query_params fiscal_period 非法")
    return normalized


def _optional_number(
    payload: Mapping[str, JsonValue],
    field_name: str,
) -> int | float | None:
    """读取缺席或有限 JSON number 参数。

    Args:
        payload: 扁平 XBRL 查询参数。
        field_name: 字段名。

    Returns:
        字段缺席时返回 ``None``，否则返回整数或有限浮点数。

    Raises:
        ValueError: 字段为 bool、非数值或非有限浮点数时抛出。
    """

    if field_name not in payload:
        return None
    value = payload[field_name]
    if isinstance(value, bool):
        raise ValueError(f"XBRL query_params {field_name} 不得为 bool")
    if not isinstance(value, (int, float)):
        raise ValueError(f"XBRL query_params {field_name} 必须为 number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"XBRL query_params {field_name} 必须为有限 number")
    return value


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


def _required_xbrl_data_quality(
    payload: XbrlFactsPayload,
    field_name: str,
) -> XbrlDataQuality:
    """读取必填 XBRL 质量字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        canonical XBRL 质量。

    Raises:
        ValueError: 字段不是合法质量值时抛出。
    """

    value = _require_field(payload, field_name)
    if value == "xbrl":
        return "xbrl"
    if value == "partial":
        return "partial"
    raise ValueError(f"XBRL facts result {field_name} 非法")


def _optional_xbrl_reason(
    payload: XbrlFactsPayload,
    field_name: str,
) -> XbrlQueryReason | None:
    """读取可选 XBRL 降级原因。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        canonical 原因或 ``None``。

    Raises:
        ValueError: 原因为 ``null`` 或不在封闭集合时抛出。
    """

    if field_name not in payload:
        return None
    value = _require_field(payload, field_name)
    if value is None:
        raise ValueError("XBRL reason 为可选字段，不得使用 null")
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
    "XbrlDataQuality",
    "XbrlFactsPayload",
    "XbrlFactsResult",
    "XbrlQueryParams",
    "XbrlQueryExecutionError",
    "XbrlQueryReason",
    "validate_xbrl_facts_result_payload",
]
