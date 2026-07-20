"""财务报表结果、倍率与质量语义的领域真源。

processor 负责产生本模块定义的完整报表事实；read runtime 只能调用校验器并
逐字段投影，不得补写期间、倍率、质量或原因。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal, NotRequired, TypeAlias, TypedDict, cast

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import (
    FinancialDataQuality,
    FiscalPeriod,
    normalize_financial_data_quality,
    normalize_fiscal_period,
)


FinancialScale: TypeAlias = Literal["units", "thousands", "millions", "billions"]
"""财务数值倍率的封闭业务值。"""

FinancialStatementReason: TypeAlias = Literal[
    "unsupported_statement_type",
    "xbrl_not_available",
    "statement_not_found",
    "low_confidence_extraction",
    "scale_unavailable",
    "period_semantics_unavailable",
    "scale_and_period_semantics_unavailable",
]
"""财务报表缺失或降级原因的封闭业务值。"""

_FINANCIAL_SCALES: Final[frozenset[str]] = frozenset(
    {"units", "thousands", "millions", "billions"}
)
_FINANCIAL_STATEMENT_REASONS: Final[frozenset[str]] = frozenset(
    {
        "unsupported_statement_type",
        "xbrl_not_available",
        "statement_not_found",
        "low_confidence_extraction",
        "scale_unavailable",
        "period_semantics_unavailable",
        "scale_and_period_semantics_unavailable",
    }
)
_FINANCIAL_RESULT_REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
    }
)
_FINANCIAL_RESULT_OPTIONAL_KEYS: Final[frozenset[str]] = frozenset({"reason"})
_FINANCIAL_PERIOD_KEYS: Final[frozenset[str]] = frozenset(
    {"period_end", "fiscal_year", "fiscal_period"}
)
_DIRECT_EVIDENCE_REASONS: Final[frozenset[FinancialStatementReason]] = frozenset(
    {
        "scale_unavailable",
        "period_semantics_unavailable",
        "scale_and_period_semantics_unavailable",
    }
)
_ISO_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}")


class FinancialPeriod(TypedDict):
    """财务报表单一期间。"""

    period_end: str
    fiscal_year: int | None
    fiscal_period: FiscalPeriod | None


class FinancialStatementResult(TypedDict):
    """processor 产生的完整财务报表领域结果。"""

    statement_type: str
    periods: list[FinancialPeriod]
    rows: list[dict[str, JsonValue]]
    currency: str | None
    units: str | None
    scale: FinancialScale | None
    data_quality: FinancialDataQuality
    reason: NotRequired[FinancialStatementReason]


FinancialStatementPayload: TypeAlias = Mapping[str, JsonValue] | FinancialStatementResult
"""校验边界接收的 JSON mapping 或强类型 producer 结果。"""


@dataclass(frozen=True)
class FinancialQualityOutcome:
    """由直接倍率和期间证据判定的财务报表质量。"""

    data_quality: FinancialDataQuality
    reason: FinancialStatementReason | None


@dataclass(frozen=True)
class FinancialScaleOutcome:
    """XBRL 倍率探测结果及其执行状态。"""

    scale: FinancialScale | None
    query_failed: bool


def infer_financial_scale_from_decimals(decimals: JsonValue) -> FinancialScale | None:
    """从 XBRL ``decimals`` 直接证据解析财务数值倍率。

    Args:
        decimals: XBRL fact 的 decimals 字段。

    Returns:
        可确认的倍率；无直接或合法证据时返回 ``None``。

    Raises:
        无。
    """

    if isinstance(decimals, bool) or decimals is None:
        return None
    if isinstance(decimals, str):
        normalized = decimals.strip().upper()
        if normalized == "INF":
            return "units"
        try:
            decimal_value = int(normalized)
        except ValueError:
            return None
    elif isinstance(decimals, int):
        decimal_value = decimals
    elif isinstance(decimals, float) and math.isfinite(decimals) and decimals.is_integer():
        decimal_value = int(decimals)
    else:
        return None
    if decimal_value == -9:
        return "billions"
    if decimal_value == -6:
        return "millions"
    if decimal_value == -3:
        return "thousands"
    if decimal_value >= 0:
        return "units"
    return None


def determine_financial_statement_quality(
    *,
    rows: list[dict[str, JsonValue]],
    periods: list[FinancialPeriod],
    scale: FinancialScale | None,
    complete_quality: Literal["xbrl", "extracted"],
) -> FinancialQualityOutcome:
    """依据 producer 的直接证据统一判定报表质量与原因。

    Args:
        rows: 已抽取的财务报表行。
        periods: 已抽取并携带直接 fiscal 证据的期间。
        scale: 从 XBRL decimals、HTML caption 或 OCR heading 获得的倍率。
        complete_quality: 证据完整时使用的质量来源。

    Returns:
        唯一满足质量/原因矩阵的结果。

    Raises:
        ValueError: ``rows`` 为空时抛出；空报表原因必须由 producer 调用路径拥有。
    """

    if not rows:
        raise ValueError("完整性质量判定要求至少一行财务数据")
    scale_missing = scale is None
    period_semantics_missing = not periods or any(
        period["fiscal_year"] is None or period["fiscal_period"] is None
        for period in periods
    )
    if scale_missing and period_semantics_missing:
        return FinancialQualityOutcome("partial", "scale_and_period_semantics_unavailable")
    if scale_missing:
        return FinancialQualityOutcome("partial", "scale_unavailable")
    if period_semantics_missing:
        return FinancialQualityOutcome("partial", "period_semantics_unavailable")
    return FinancialQualityOutcome(complete_quality, None)


def validate_financial_statement_result_payload(
    payload: FinancialStatementPayload,
) -> FinancialStatementResult:
    """校验并复制 processor 财务报表结果。

    Args:
        payload: processor 返回的原始 JSON 对象。

    Returns:
        逐字段复制、满足领域不变量的强类型结果。

    Raises:
        ValueError: 必填字段缺失、字段类型非法、JSON shape 非法或质量矩阵冲突时抛出。
    """

    _validate_exact_keys(
        payload,
        required_keys=_FINANCIAL_RESULT_REQUIRED_KEYS,
        optional_keys=_FINANCIAL_RESULT_OPTIONAL_KEYS,
        context="FinancialStatementResult",
    )
    statement_type = _required_non_empty_string(payload, "statement_type")
    periods = _required_periods(payload)
    rows = _required_json_rows(payload)
    currency = _required_optional_string(payload, "currency")
    units = _required_optional_string(payload, "units")
    scale = _required_financial_scale(payload)
    data_quality = _required_data_quality(payload)
    reason = _optional_financial_reason(payload)
    if data_quality == "partial" and reason is None:
        raise ValueError("FinancialStatementResult partial 必须提供 reason")
    if data_quality != "partial" and reason is not None:
        raise ValueError("FinancialStatementResult 完整结果必须省略 reason")
    if not rows and data_quality != "partial":
        raise ValueError("FinancialStatementResult 空 rows 不得声明完整质量")
    if units is not None and (
        units.lower() in _FINANCIAL_SCALES
        or re.search(r"\bin\s+(?:thousands|millions|billions)\b", units, re.IGNORECASE)
    ):
        raise ValueError("FinancialStatementResult units 不得承载 scale")
    if rows and (data_quality != "partial" or reason in _DIRECT_EVIDENCE_REASONS):
        expected_quality = determine_financial_statement_quality(
            rows=rows,
            periods=periods,
            scale=scale,
            complete_quality="xbrl" if data_quality == "partial" else data_quality,
        )
        if data_quality != expected_quality.data_quality or reason != expected_quality.reason:
            raise ValueError("FinancialStatementResult quality/reason 与直接证据不一致")
    result = FinancialStatementResult(
        statement_type=statement_type,
        periods=periods,
        rows=rows,
        currency=currency,
        units=units,
        scale=scale,
        data_quality=data_quality,
    )
    if reason is not None:
        result["reason"] = reason
    return result


def _validate_exact_keys(
    payload: Mapping[str, JsonValue] | FinancialStatementResult,
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


def _require_field(payload: FinancialStatementPayload, field_name: str) -> JsonValue:
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
        raise ValueError(f"FinancialStatementResult 缺少必填字段: {field_name}")
    return cast(JsonValue, payload[field_name])


def _required_non_empty_string(payload: FinancialStatementPayload, field_name: str) -> str:
    """读取必填非空字符串字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        去除首尾空白的字符串。

    Raises:
        ValueError: 字段缺失、不是字符串或为空时抛出。
    """

    value = _require_field(payload, field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"FinancialStatementResult {field_name} 必须为非空字符串")
    return value.strip()


def _required_optional_string(payload: FinancialStatementPayload, field_name: str) -> str | None:
    """读取必填可空字符串字段。

    Args:
        payload: 原始 JSON 对象。
        field_name: 字段名。

    Returns:
        规范化字符串或 ``None``。

    Raises:
        ValueError: 字段缺失、不是字符串/null 或字符串为空时抛出。
    """

    value = _require_field(payload, field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"FinancialStatementResult {field_name} 必须为非空字符串或 null")
    return value.strip()


def _required_periods(payload: FinancialStatementPayload) -> list[FinancialPeriod]:
    """校验并复制期间列表。

    Args:
        payload: 原始 JSON 对象。

    Returns:
        强类型期间列表。

    Raises:
        ValueError: periods 不是数组或任一期间字段非法时抛出。
    """

    raw_periods = _require_field(payload, "periods")
    if not isinstance(raw_periods, list):
        raise ValueError("FinancialStatementResult periods 必须为数组")
    periods: list[FinancialPeriod] = []
    for raw_period in raw_periods:
        if not isinstance(raw_period, Mapping):
            raise ValueError("FinancialStatementResult periods 元素必须为对象")
        _validate_exact_keys(
            raw_period,
            required_keys=_FINANCIAL_PERIOD_KEYS,
            optional_keys=frozenset(),
            context="FinancialStatementResult period",
        )
        period_end = _required_non_empty_string(raw_period, "period_end")
        if _ISO_DATE_PATTERN.fullmatch(period_end) is None:
            raise ValueError("FinancialStatementResult period_end 必须为 YYYY-MM-DD")
        try:
            date.fromisoformat(period_end)
        except ValueError as exc:
            raise ValueError("FinancialStatementResult period_end 必须为有效 ISO 日期") from exc
        raw_year = _require_field(raw_period, "fiscal_year")
        if raw_year is not None and (
            not isinstance(raw_year, int) or isinstance(raw_year, bool) or raw_year <= 0
        ):
            raise ValueError("FinancialStatementResult fiscal_year 必须为正整数或 null")
        raw_period_value = _require_field(raw_period, "fiscal_period")
        if raw_period_value is not None and not isinstance(raw_period_value, str):
            raise ValueError("FinancialStatementResult fiscal_period 必须为字符串或 null")
        fiscal_period = normalize_fiscal_period(
            raw_period_value,
            field_name="FinancialStatementResult fiscal_period",
        )
        periods.append(
            FinancialPeriod(
                period_end=period_end,
                fiscal_year=raw_year,
                fiscal_period=fiscal_period,
            )
        )
    return periods


def _required_json_rows(payload: FinancialStatementPayload) -> list[dict[str, JsonValue]]:
    """校验并复制财务行 JSON 对象。

    Args:
        payload: 原始 JSON 对象。

    Returns:
        独立复制的行列表。

    Raises:
        ValueError: rows 不是对象数组或包含非法 JSON 值时抛出。
    """

    raw_rows = _require_field(payload, "rows")
    if not isinstance(raw_rows, list):
        raise ValueError("FinancialStatementResult rows 必须为数组")
    rows: list[dict[str, JsonValue]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            raise ValueError("FinancialStatementResult rows 元素必须为对象")
        copied_row = dict(raw_row)
        for key, value in copied_row.items():
            if not isinstance(key, str) or not _is_json_value(value):
                raise ValueError("FinancialStatementResult rows 必须是合法 JSON 对象")
        rows.append(copied_row)
    return rows


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


def _required_financial_scale(payload: FinancialStatementPayload) -> FinancialScale | None:
    """读取必填倍率字段。

    Args:
        payload: 原始 JSON 对象。

    Returns:
        canonical 倍率或 ``None``。

    Raises:
        ValueError: 字段缺失或值不在封闭集合时抛出。
    """

    value = _require_field(payload, "scale")
    if value is None:
        return None
    if not isinstance(value, str) or value not in _FINANCIAL_SCALES:
        raise ValueError("FinancialStatementResult scale 非法")
    return cast(FinancialScale, value)


def _required_data_quality(payload: FinancialStatementPayload) -> FinancialDataQuality:
    """读取必填财务质量字段。

    Args:
        payload: 原始 JSON 对象。

    Returns:
        canonical 财务质量。

    Raises:
        ValueError: 字段缺失或值非法时抛出。
    """

    value = _require_field(payload, "data_quality")
    if not isinstance(value, str):
        raise ValueError("FinancialStatementResult data_quality 必须为字符串")
    return normalize_financial_data_quality(value, field_name="FinancialStatementResult data_quality")


def _optional_financial_reason(
    payload: FinancialStatementPayload,
) -> FinancialStatementReason | None:
    """读取可选降级原因字段。

    Args:
        payload: 原始 JSON 对象。

    Returns:
        canonical 原因或 ``None``。

    Raises:
        ValueError: 原因为 ``null`` 或不在封闭集合时抛出。
    """

    if "reason" not in payload:
        return None
    value = _require_field(payload, "reason")
    if value is None:
        raise ValueError("FinancialStatementResult reason 为可选字段，不得使用 null")
    if not isinstance(value, str) or value not in _FINANCIAL_STATEMENT_REASONS:
        raise ValueError("FinancialStatementResult reason 非法")
    return cast(FinancialStatementReason, value)


__all__ = [
    "FinancialPeriod",
    "FinancialQualityOutcome",
    "FinancialScale",
    "FinancialScaleOutcome",
    "FinancialStatementReason",
    "FinancialStatementResult",
    "FinancialStatementPayload",
    "determine_financial_statement_quality",
    "infer_financial_scale_from_decimals",
    "validate_financial_statement_result_payload",
]
