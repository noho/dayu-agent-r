"""财报文档共享语义解析真源。

本模块承载 Fins domain 层的窄业务值解析：SEC form、财期、四位 fiscal/partial
year、canonical Gregorian full-date、文档质量和财务数据质量。calendar/year
合法性由本模块统一拥有；pipeline、processor、storage decode 与 read runtime
只能消费这里的解析结果，避免各自维护业务规则后产生语义漂移。
"""

from __future__ import annotations

import datetime
import re
from typing import Final, Literal, Optional, TypeAlias, cast

from dayu.contracts.json_value import JsonValue


SecFormType: TypeAlias = Literal[
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "20-F/A",
    "6-K",
    "6-K/A",
    "8-K",
    "8-K/A",
    "DEF 14A",
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
]
"""SEC 单一 filing form 的封闭业务值。"""

FiscalPeriod: TypeAlias = Literal["FY", "H1", "Q1", "Q2", "Q3", "Q4"]
"""Fins 通用财期封闭业务值。"""

DocumentQuality: TypeAlias = Literal["full", "partial", "fallback"]
"""processed 文档质量封闭业务值。"""

FinancialDataQuality: TypeAlias = Literal["xbrl", "partial", "extracted"]
"""财务数据载荷质量封闭业务值。"""

_MIN_CALENDAR_YEAR: Final[int] = 1000
"""Fins 财年与 partial calendar year 的最小合法值。"""

_MAX_CALENDAR_YEAR: Final[int] = 9999
"""Fins 财年与 partial calendar year 的最大合法值。"""

_CALENDAR_YEAR_RANGE_TEXT: Final[str] = f"{_MIN_CALENDAR_YEAR}..{_MAX_CALENDAR_YEAR}"
"""由年份边界派生、供 owner 错误文案共用的闭区间文本。"""

_STRICT_ISO_CALENDAR_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})",
    flags=re.ASCII,
)
"""精确 ASCII ``YYYY-MM-DD`` 日期文本格式。"""

SEC_FORM_GROUP_SC13D_G: Final[str] = "SC 13D/G"
"""SEC 下载筛选使用的 SC 13D/G 组合别名；该值不得作为单一 filing form 持久化。"""

SEC_SC13_FORMS: Final[frozenset[SecFormType]] = frozenset(
    cast(
        tuple[SecFormType, ...],
        ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"),
    )
)
"""SC 13D/G 家族展开后的单一 SEC filing form。"""

SEC_FORM_TYPES: Final[frozenset[SecFormType]] = frozenset(
    cast(
        tuple[SecFormType, ...],
        (
            "10-K",
            "10-K/A",
            "10-Q",
            "10-Q/A",
            "20-F",
            "20-F/A",
            "6-K",
            "6-K/A",
            "8-K",
            "8-K/A",
            "DEF 14A",
            "SC 13D",
            "SC 13D/A",
            "SC 13G",
            "SC 13G/A",
        ),
    )
)
"""Fins 当前支持解析的 SEC 单一 filing form 集合。"""

FISCAL_PERIODS: Final[frozenset[FiscalPeriod]] = frozenset(
    cast(tuple[FiscalPeriod, ...], ("FY", "H1", "Q1", "Q2", "Q3", "Q4"))
)
"""Fins 通用财期集合。"""

_FISCAL_PERIOD_FILTER_ALIASES: Final[dict[str, FiscalPeriod]] = {
    "FY": "FY",
    "ANNUAL": "FY",
    "年报": "FY",
    "年度报告": "FY",
    "H1": "H1",
    "1H": "H1",
    "半年报": "H1",
    "中报": "H1",
    "Q1": "Q1",
    "1Q": "Q1",
    "一季报": "Q1",
    "一季度报告": "Q1",
    "Q2": "Q2",
    "2Q": "Q2",
    "二季报": "Q2",
    "二季度报告": "Q2",
    "Q3": "Q3",
    "3Q": "Q3",
    "三季报": "Q3",
    "三季度报告": "Q3",
    "Q4": "Q4",
    "4Q": "Q4",
    "四季报": "Q4",
    "四季度报告": "Q4",
}
"""CN/HK 下载筛选 token 到 canonical 财期的唯一映射。"""

_FISCAL_PERIOD_RECENCY_ORDER: Final[tuple[str, ...]] = ("", "Q1", "Q2", "H1", "Q3", "Q4", "FY")
"""财期在同一财年内的固定业务顺序；空字符串占据未知值的 rank 0。"""

DOCUMENT_QUALITIES: Final[frozenset[DocumentQuality]] = frozenset(
    cast(tuple[DocumentQuality, ...], ("full", "partial", "fallback"))
)
"""processed 文档质量集合。"""

FINANCIAL_DATA_QUALITIES: Final[frozenset[FinancialDataQuality]] = frozenset(
    cast(tuple[FinancialDataQuality, ...], ("xbrl", "partial", "extracted"))
)
"""财务数据载荷质量集合。"""

_SEC_FORM_ALIASES: Final[dict[str, str]] = {
    "10K": "10-K",
    "10K/A": "10-K/A",
    "10KA": "10-K/A",
    "10Q": "10-Q",
    "10Q/A": "10-Q/A",
    "10QA": "10-Q/A",
    "20F": "20-F",
    "20F/A": "20-F/A",
    "20FA": "20-F/A",
    "6K": "6-K",
    "6K/A": "6-K/A",
    "6KA": "6-K/A",
    "8K": "8-K",
    "8K/A": "8-K/A",
    "8KA": "8-K/A",
    "DEF14A": "DEF 14A",
    "SC13D/G": SEC_FORM_GROUP_SC13D_G,
    "SC13DG": SEC_FORM_GROUP_SC13D_G,
    "SCHEDULE13D/G": SEC_FORM_GROUP_SC13D_G,
    "SCHEDULE13DG": SEC_FORM_GROUP_SC13D_G,
    "SC13D": "SC 13D",
    "SC13D/A": "SC 13D/A",
    "SC13DA": "SC 13D/A",
    "SCHEDULE13D": "SC 13D",
    "SCHEDULE13D/A": "SC 13D/A",
    "SCHEDULE13DA": "SC 13D/A",
    "SC13G": "SC 13G",
    "SC13G/A": "SC 13G/A",
    "SC13GA": "SC 13G/A",
    "SCHEDULE13G": "SC 13G",
    "SCHEDULE13G/A": "SC 13G/A",
    "SCHEDULE13GA": "SC 13G/A",
}


def _sec_form_alias_key(value: str) -> str:
    """构造 SEC form 别名查找键。

    Args:
        value: 原始 SEC form 文本。

    Returns:
        去除空白和横线后的大写查找键，保留斜线以区分修正案。

    Raises:
        无。
    """

    return re.sub(r"[\s-]+", "", value.strip().upper())


def normalize_sec_form_type_for_matching(value: Optional[str]) -> Optional[str]:
    """标准化用于匹配的 SEC form 文本。

    该函数用于 processor 支持判断、read runtime 过滤和远端候选收集等消费路径。
    已知别名会投影为 canonical SEC form 或 `SC 13D/G` 组合筛选别名；未知非空
    值只做大写保留，由调用方自己的支持集合决定是否接收。

    Args:
        value: 原始 SEC form 文本。

    Returns:
        标准化 form 文本；输入为空时返回 `None`。

    Raises:
        无。
    """

    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    alias_key = _sec_form_alias_key(stripped)
    return _SEC_FORM_ALIASES.get(alias_key, stripped.upper())


def parse_sec_form_type(value: str, *, field_name: str = "form_type") -> SecFormType:
    """解析单一 SEC filing form。

    Args:
        value: 原始 SEC form 文本。
        field_name: 报错使用的字段名。

    Returns:
        canonical SEC filing form。

    Raises:
        ValueError: 输入为空、为组合别名或不是支持的单一 SEC form 时抛出。
    """

    normalized = normalize_sec_form_type_for_matching(value)
    if normalized is None:
        raise ValueError(f"{field_name} 不能为空")
    if normalized == SEC_FORM_GROUP_SC13D_G:
        raise ValueError(f"{field_name} 必须是单一 SEC form，不能是组合别名: {value}")
    if normalized not in SEC_FORM_TYPES:
        raise ValueError(f"{field_name} 不支持: {value}")
    return cast(SecFormType, normalized)


def parse_sec_form_filter_value(value: str, *, field_name: str = "form_type") -> str:
    """解析 SEC 下载筛选 form。

    下载筛选允许 `SC 13D/G` 组合别名，其它值必须是单一 canonical SEC form。

    Args:
        value: 原始 SEC form 筛选文本。
        field_name: 报错使用的字段名。

    Returns:
        canonical 单一 SEC form 或 `SC 13D/G` 组合别名。

    Raises:
        ValueError: 输入为空或不是支持的筛选 form 时抛出。
    """

    normalized = normalize_sec_form_type_for_matching(value)
    if normalized is None:
        raise ValueError(f"{field_name} 不能为空")
    if normalized == SEC_FORM_GROUP_SC13D_G:
        return normalized
    if normalized not in SEC_FORM_TYPES:
        raise ValueError(f"{field_name} 不支持: {value}")
    return normalized


def expand_sec_form_aliases(form_types: list[str]) -> list[str]:
    """展开 SEC form 筛选别名。

    Args:
        form_types: 原始或 canonical SEC form 筛选值。

    Returns:
        去重并排序后的 canonical 单一 SEC form 列表。

    Raises:
        ValueError: 任一输入为空、组合别名以外的未知 form 或不支持 form 时抛出。
    """

    expanded: list[str] = []
    for form_type in form_types:
        normalized = parse_sec_form_filter_value(form_type)
        if normalized == SEC_FORM_GROUP_SC13D_G:
            expanded.extend(SEC_SC13_FORMS)
            continue
        expanded.append(normalized)
    return sorted(set(expanded))


def normalize_fiscal_period(value: Optional[str], *, field_name: str = "fiscal_period") -> Optional[FiscalPeriod]:
    """解析可选财期字段。

    Args:
        value: 原始财期文本。
        field_name: 报错使用的字段名。

    Returns:
        canonical 财期；输入为空时返回 `None`。

    Raises:
        ValueError: 非空输入不是 `FY/H1/Q1/Q2/Q3/Q4` 时抛出。
    """

    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in FISCAL_PERIODS:
        raise ValueError(f"{field_name} 非法: {value}")
    return cast(FiscalPeriod, normalized)


def parse_fiscal_period_filter_value(
    value: str,
    *,
    field_name: str = "form_type",
) -> FiscalPeriod:
    """解析 CN/HK 下载筛选使用的财期别名。

    Args:
        value: 原始财期筛选文本。
        field_name: 错误信息使用的字段名。

    Returns:
        canonical 财期。

    Raises:
        ValueError: 输入为空或不属于支持的财期别名时抛出。
    """

    normalized = value.strip().upper()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    period = _FISCAL_PERIOD_FILTER_ALIASES.get(normalized)
    if period is None:
        raise ValueError(f"{field_name} 不支持: {value}")
    return period


def parse_calendar_year(value: int, *, field_name: str = "year") -> int:
    """解析 Fins 财年或 partial calendar year。

    Args:
        value: 待解析的整数年份。
        field_name: 报错使用的字段名。

    Returns:
        位于 ``1000..9999`` 闭区间内的原始整数年份。

    Raises:
        ValueError: 输入为 bool、非整数或超出 ``1000..9999`` 时抛出。
    """

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < _MIN_CALENDAR_YEAR
        or value > _MAX_CALENDAR_YEAR
    ):
        raise ValueError(f"{field_name} 必须是 {_CALENDAR_YEAR_RANGE_TEXT} 的整数")
    return value


def parse_iso_calendar_date(value: str, *, field_name: str = "date") -> datetime.date:
    """解析精确且实际存在的 ISO 公历日期。

    Args:
        value: 待解析的日期文本，必须精确符合 ASCII ``YYYY-MM-DD``。
        field_name: 报错使用的字段名。

    Returns:
        与输入文本完全一致的公历日期值。

    Raises:
        ValueError: 输入不是字符串、格式不精确或日期在公历中不存在时抛出。
    """

    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是实际存在的 YYYY-MM-DD 日期")
    matched = _STRICT_ISO_CALENDAR_DATE_PATTERN.fullmatch(value)
    if matched is None:
        raise ValueError(f"{field_name} 必须是实际存在的 YYYY-MM-DD 日期")
    try:
        parsed = datetime.date(
            int(matched.group("year")),
            int(matched.group("month")),
            int(matched.group("day")),
        )
    except ValueError:
        raise ValueError(f"{field_name} 必须是实际存在的 YYYY-MM-DD 日期") from None
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} 必须是实际存在的 YYYY-MM-DD 日期")
    return parsed


def normalize_fiscal_year(value: JsonValue | None, *, field_name: str = "fiscal_year") -> int | None:
    """解析可选财年字段。

    财年只能来自 producer 或仓储中的直接四位整数事实。本函数不会从报告日期、
    申报日期或财期推断年份，也不会接受 bool、数字文本或浮点数；非空整数的
    年份范围统一委托 :func:`parse_calendar_year` 校验。

    Args:
        value: 原始财年 JSON 值；字段缺失或显式为空时传入 ``None``。
        field_name: 报错使用的字段名。

    Returns:
        位于 ``1000..9999`` 闭区间内的财年；输入缺失时返回 ``None``。

    Raises:
        ValueError: 非空输入为 bool、非整数或超出 ``1000..9999`` 时抛出。
    """

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 必须是 {_CALENDAR_YEAR_RANGE_TEXT} 的整数")
    return parse_calendar_year(value, field_name=field_name)


def fiscal_period_recency_rank(period: str | None) -> int:
    """返回财期在同一财年内的固定排序权重。

    Args:
        period: canonical 财期；``None`` 或未知文本表示没有可用财期事实。

    Returns:
        ``None``/未知值为 0，其余依次为 Q1=1、Q2=2、H1=3、Q3=4、Q4=5、FY=6。

    Raises:
        无。
    """

    if period is None or period not in _FISCAL_PERIOD_RECENCY_ORDER:
        return 0
    return _FISCAL_PERIOD_RECENCY_ORDER.index(period)


def sanitize_fiscal_period_by_sec_form(
    form_type: Optional[str],
    fiscal_period: Optional[str],
) -> Optional[FiscalPeriod]:
    """按 SEC form 约束财期合法值。

    Args:
        form_type: 原始或 canonical SEC form。
        fiscal_period: 原始或 canonical 财期。

    Returns:
        通过 form 约束的 canonical 财期；为空或不匹配时返回 `None`。

    Raises:
        ValueError: 非空财期不是 Fins 支持的财期枚举时抛出。
    """

    normalized_period = normalize_fiscal_period(fiscal_period)
    if normalized_period is None:
        return None
    normalized_form = normalize_sec_form_type_for_matching(form_type)
    if normalized_form in {"10-K", "10-K/A", "20-F", "20-F/A"}:
        return "FY" if normalized_period == "FY" else None
    if normalized_form in {"10-Q", "10-Q/A"}:
        return normalized_period if normalized_period in {"Q1", "Q2", "Q3", "Q4"} else None
    return normalized_period


def normalize_document_quality(
    value: Optional[str],
    *,
    field_name: str = "quality",
) -> DocumentQuality:
    """解析 processed 文档质量。

    Args:
        value: 原始质量文本；为空时使用默认 `full`。
        field_name: 报错使用的字段名。

    Returns:
        canonical 文档质量。

    Raises:
        ValueError: 非空输入不是 `full/partial/fallback` 时抛出。
    """

    normalized = "full" if value is None or not value.strip() else value.strip().lower()
    if normalized not in DOCUMENT_QUALITIES:
        raise ValueError(f"{field_name} 非法: {value}")
    return cast(DocumentQuality, normalized)


def normalize_financial_data_quality(
    value: str,
    *,
    field_name: str = "data_quality",
) -> FinancialDataQuality:
    """解析财务数据质量。

    Args:
        value: 原始财务数据质量文本。
        field_name: 报错使用的字段名。

    Returns:
        canonical 财务数据质量。

    Raises:
        ValueError: 输入为空或不是 `xbrl/partial/extracted` 时抛出。
    """

    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    if normalized not in FINANCIAL_DATA_QUALITIES:
        raise ValueError(f"{field_name} 非法: {value}")
    return cast(FinancialDataQuality, normalized)
