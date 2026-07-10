"""SEC 表单/日期/文本解析工具集。

此模块包含纯函数工具，无 I/O 副作用。供 SecPipeline 及多个子工作流模块共享。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.filing_semantics import (
    SEC_FORM_GROUP_SC13D_G,
    expand_sec_form_aliases,
    parse_sec_form_filter_value,
)

import datetime as dt
import re
from typing import Optional

# ---------- 常量 ----------

# 美股默认下载表单集合（年报、季报、公告、持股），覆盖国内/外籍发行人两种表单。
DEFAULT_FORMS_US: list[str] = ["10-K", "20-F", "10-Q", "6-K", "8-K", "DEF 14A", SEC_FORM_GROUP_SC13D_G]

LOOKBACK_YEARS_BY_FORM: dict[str, int] = {
    "10-K": 5,
    "20-F": 5,
    "10-Q": 2,
    "6-K": 2,
    "DEF 14A": 3,
    "8-K": 1,
    "8-K/A": 1,
    "SC 13D": 1,
    "SC 13D/A": 1,
    "SC 13G": 1,
    "SC 13G/A": 1,
}

# 回溯窗口宽限天数。SEC 申报时限因公司类型不同有差异（10-K 60~90天、20-F 4个月），
# 连续两年申报间隔可能超过 N 年。加 60 天宽限确保不遗漏边界 filing。
LOOKBACK_GRACE_DAYS = 60

SUPPORTED_FORMS = frozenset(LOOKBACK_YEARS_BY_FORM.keys())


# ---------- 函数 ----------


def parse_sec_pipeline_form(form_type: str) -> str:
    """解析 SEC pipeline 接收的 form 筛选值。

    Args:
        form_type: 原始 form 字符串。

    Returns:
        canonical 单一 SEC form 或 `SC 13D/G` 组合别名。

    Raises:
        ValueError: form 为空或不受支持时抛出。
    """

    return parse_sec_form_filter_value(form_type)


def expand_form_aliases(form_types: list[str]) -> list[str]:
    """展开 form 别名。

    Args:
        form_types: 标准化前后的 form 列表。

    Returns:
        去重后的展开结果。

    Raises:
        ValueError: 展开后存在不支持 form 时抛出。
    """

    expanded: list[str] = []
    for form_type in form_types:
        normalized = parse_sec_pipeline_form(form_type)
        if normalized == SEC_FORM_GROUP_SC13D_G:
            expanded.extend(expand_sec_form_aliases([normalized]))
            continue
        expanded.append(normalized)
    deduplicated = sorted(set(expanded))
    unsupported = [item for item in deduplicated if item not in SUPPORTED_FORMS]
    if unsupported:
        raise ValueError(f"不支持的 form_type: {unsupported}")
    return deduplicated


def split_form_input(raw_form_input: str) -> list[str]:
    """拆分 form 输入字符串。

    Args:
        raw_form_input: 原始 form 输入。

    Returns:
        form 片段列表。

    Raises:
        ValueError: 输入为空时抛出。
    """

    values = [item.strip() for item in re.split(r",\s*", raw_form_input) if item.strip()]
    if not values:
        raise ValueError("form_type 不能为空")
    return values


def parse_date(value: str, is_end: bool = False) -> dt.date:
    """解析日期字符串。

    支持：
    - ``YYYY``
    - ``YYYY-MM``
    - ``YYYY-MM-DD``

    Args:
        value: 原始日期字符串。
        is_end: 是否按结束日期语义解析（用于补月底/年底）。

    Returns:
        日期对象。

    Raises:
        ValueError: 输入格式非法时抛出。
    """

    raw = value.strip()
    if re.fullmatch(r"\d{4}", raw):
        year = int(raw)
        return dt.date(year, 12, 31) if is_end else dt.date(year, 1, 1)
    if re.fullmatch(r"\d{4}-\d{1,2}", raw):
        year_str, month_str = raw.split("-")
        year = int(year_str)
        month = int(month_str)
        if is_end:
            if month == 12:
                next_month = dt.date(year + 1, 1, 1)
            else:
                next_month = dt.date(year, month + 1, 1)
            return next_month - dt.timedelta(days=1)
        return dt.date(year, month, 1)
    return dt.datetime.strptime(raw, "%Y-%m-%d").date()


def subtract_years(anchor_date: dt.date, years: int) -> dt.date:
    """从给定日期回退若干年。

    Args:
        anchor_date: 锚点日期。
        years: 年数。

    Returns:
        回退后的日期。

    Raises:
        ValueError: years 非正数时抛出。
    """

    if years <= 0:
        raise ValueError("years 必须大于 0")
    target_year = anchor_date.year - years
    try:
        return anchor_date.replace(year=target_year)
    except ValueError:
        return anchor_date.replace(year=target_year, day=28)


def increment_document_version(previous_version: str) -> str:
    """递增文档版本号。

    Args:
        previous_version: 旧版本号（如 v1）。

    Returns:
        新版本号。

    Raises:
        无。
    """

    matched = re.fullmatch(r"v(\d+)", previous_version.strip())
    if matched is None:
        return "v2"
    return f"v{int(matched.group(1)) + 1}"


def first_non_empty_text(*values: JsonValue) -> Optional[str]:
    """返回第一个非空白文本值。

    Args:
        *values: 待筛选的候选值。

    Returns:
        第一个非空白字符串；若均为空则返回 ``None``。

    Raises:
        无。
    """

    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized:
            return normalized
    return None
