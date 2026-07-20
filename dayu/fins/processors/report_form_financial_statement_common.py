"""报告类表单 HTML 财务表语义共享能力。

本模块承载 `10-K`、`10-Q`、`20-F` 这类报告类表单的财务表语义层：
- 报表类型分类规则（caption / headers / context_before）
- 行标签语义回退规则（row-signal fallback）
- 报告类表格候选筛选顺序

边界约束：
- 本模块不负责 HTML 表格结构化，不解析 DataFrame。
- 本模块不持有 `6-K` 专属规则。
- 结构化核心继续由 ``html_financial_statement_common`` 提供。
"""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any, Optional

import pandas as pd

from dayu.documents.processors.text_utils import normalize_whitespace as _normalize_whitespace
from dayu.fins.domain.financial_result_contract import FinancialStatementReason

from .html_financial_statement_common import (
    select_html_statement_tables_by_row_signals as _select_html_statement_tables_by_row_signals,
)

REPORT_FORM_SUPPORTED_STATEMENT_TYPES = frozenset(
    {
        "income",
        "balance_sheet",
        "cash_flow",
        "equity",
        "comprehensive_income",
    }
)

REPORT_FORM_HTML_FALLBACK_REASONS: frozenset[FinancialStatementReason] = frozenset(
    {
        "xbrl_not_available",
        "statement_not_found",
    }
)

_STATEMENT_CLASSIFICATION_CONTEXT_WINDOW = 320
_STATEMENT_CLASSIFICATION_MIN_SCORE = 4
_STATEMENT_CLASSIFICATION_CONTEXT_ONLY_MIN_SCORE = 2
_STATEMENT_CLASSIFICATION_WEIGHTS: dict[str, int] = {
    "caption": 6,
    "headers": 4,
    "context": 1,
}
_STATEMENT_LINE_ITEM_WEIGHT = 2

_NON_STATEMENT_TABLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\btable\s+of\s+contents\b"),
    re.compile(r"(?i)\bexhibit\s+index\b"),
    re.compile(r"(?i)\bindex\s+to\s+exhibits\b"),
    re.compile(r"(?i)\bsignatures?\b"),
    re.compile(r"(?i)\bnotes?\s+to\s+(?:the\s+)?consolidated\s+financial\s+statements?\b"),
    re.compile(r"(?i)\bnotes?\s+to\s+financial\s+statements?\b"),
    re.compile(r"(?i)\bschedule\s+[ivx0-9]+\b"),
    re.compile(r"(?i)\bselected\s+financial\s+data\b"),
    re.compile(r"(?i)\bquarterly\s+(?:financial|results)\b"),
    re.compile(r"(?i)\bsupplementary\s+data\b"),
    re.compile(r"(?i)\bsecurities\s+registered\s+pursuant\s+to\s+section\s+12\b"),
    re.compile(r"(?i)\btrading\s+symbol(?:s)?\b"),
    re.compile(r"(?i)\bname\s+of\s+each\s+exchange\b"),
)

_STATEMENT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "balance_sheet": (
        re.compile(r"(?i)\bbalance\s+sheets?\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+financial\s+position\b"),
        re.compile(r"(?i)\bfinancial\s+position\b"),
        re.compile(r"(?i)\bassets?,\s+liabilities?\s+and\s+(?:stockholders'|shareholders'?)\s+equity\b"),
    ),
    "income": (
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+operations\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+income\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+earnings\b"),
        re.compile(r"(?i)\bresults\s+of\s+operations\b"),
        re.compile(r"(?i)\bprofit\s+and\s+loss\b"),
    ),
    "cash_flow": (
        re.compile(r"(?i)\bcash\s+flows?\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+cash\s+flows?\b"),
    ),
    "equity": (
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+(?:stockholders'|shareholders'?)\s+equity\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+changes\s+in\s+equity\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+stockholders'?\s+investment\b"),
    ),
    "comprehensive_income": (
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+comprehensive\s+income\b"),
        re.compile(r"(?i)\bstatement(?:s)?\s+of\s+comprehensive\s+(?:loss|earnings)\b"),
        re.compile(r"(?i)\bother\s+comprehensive\s+income\b"),
        re.compile(r"(?i)\bcomprehensive\s+income\b"),
    ),
}

_STATEMENT_LINE_ITEM_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "balance_sheet": (
        re.compile(r"(?i)\btotal\s+assets?\b"),
        re.compile(r"(?i)\btotal\s+(?:current\s+)?liabilit(?:y|ies)\b"),
        re.compile(r"(?i)\b(?:non[- ]?current|current)\s+assets?\b"),
        re.compile(r"(?i)\b(?:shareholders'?|stockholders'?)\s+equity\b"),
        re.compile(r"(?i)\btotal\s+equity\b"),
    ),
    "income": (
        re.compile(r"(?i)\btotal\s+revenue\b"),
        re.compile(r"(?i)\brevenues?\b"),
        re.compile(r"(?i)\bcost\s+of\s+(?:sales|revenue)\b"),
        re.compile(r"(?i)\bgross\s+profit\b"),
        re.compile(r"(?i)\boperating\s+(?:income|loss|profit)\b"),
        re.compile(r"(?i)\bnet\s+(?:income|loss|earnings|profit)\b"),
        re.compile(r"(?i)\bearnings\s+per\s+share\b"),
    ),
    "cash_flow": (
        re.compile(r"(?i)\boperating\s+activities\b"),
        re.compile(r"(?i)\binvesting\s+activities\b"),
        re.compile(r"(?i)\bfinancing\s+activities\b"),
        re.compile(r"(?i)\bnet\s+cash\s+(?:provided|used)\b"),
        re.compile(r"(?i)\bcash\s+and\s+cash\s+equivalents\b"),
    ),
    "equity": (
        re.compile(r"(?i)\bcommon\s+stock\b"),
        re.compile(r"(?i)\badditional\s+paid[- ]in\s+capital\b"),
        re.compile(r"(?i)\bretained\s+earnings\b"),
        re.compile(r"(?i)\btreasury\s+stock\b"),
        re.compile(r"(?i)\baccumulated\s+other\s+comprehensive\s+(?:income|loss)\b"),
        re.compile(r"(?i)\bdividends?\b"),
    ),
    "comprehensive_income": (
        re.compile(r"(?i)\bnet\s+income\b"),
        re.compile(r"(?i)\bother\s+comprehensive\s+(?:income|loss)\b"),
        re.compile(r"(?i)\bcomprehensive\s+income\b"),
        re.compile(r"(?i)\bforeign\s+currency\s+translation\b"),
        re.compile(r"(?i)\bunrealized\s+(?:gain|loss)\b"),
    ),
}

_ROW_SIGNAL_MIN_HITS_BY_STATEMENT: dict[str, int] = {
    "income": 2,
    "balance_sheet": 2,
    "cash_flow": 2,
    "equity": 2,
    "comprehensive_income": 2,
}
_RELAXED_ROW_SIGNAL_MIN_HITS_BY_STATEMENT: dict[str, int] = {
    "income": 3,
    "balance_sheet": 3,
    "cash_flow": 3,
    "equity": 3,
    "comprehensive_income": 3,
}
_RELAXED_STATEMENT_LINE_ITEM_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    **_STATEMENT_LINE_ITEM_PATTERNS,
    "balance_sheet": _STATEMENT_LINE_ITEM_PATTERNS["balance_sheet"] + (
        re.compile(r"(?i)\bcash\s+and\s+cash\s+equivalents\b"),
        re.compile(r"(?i)\brestricted\s+cash\b"),
        re.compile(r"(?i)\bborrowings?\b"),
        re.compile(r"(?i)\bnet\s+debt\b"),
    ),
}


def should_apply_report_statement_html_fallback(
    reason: FinancialStatementReason | None,
) -> bool:
    """判断是否应触发报告类 HTML fallback。

    Args:
        reason: 当前 XBRL 路径返回的失败原因。

    Returns:
        命中允许 fallback 的 reason 时返回 ``True``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    return reason in REPORT_FORM_HTML_FALLBACK_REASONS


def classify_report_statement_type_for_table(
    *,
    caption: Optional[str],
    headers: Optional[list[str]],
    context_before: str,
) -> Optional[str]:
    """判定报告类表格属于哪类财务报表。

    Args:
        caption: 表格标题。
        headers: 表头列表。
        context_before: 表格前文。

    Returns:
        标准化报表类型；无法判定时返回 ``None``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    caption_text = _normalize_report_statement_text(str(caption or ""))
    headers_text = _normalize_report_statement_text(" ".join(str(item or "") for item in (headers or [])))
    context_text = _normalize_report_statement_text(
        str(context_before or "")[-_STATEMENT_CLASSIFICATION_CONTEXT_WINDOW:]
    )
    if not caption_text and not headers_text and not context_text:
        return None
    if _looks_like_non_statement_table(
        caption_text=caption_text,
        headers_text=headers_text,
    ):
        return None

    scores = {
        statement_type: _score_statement_type(
            statement_type=statement_type,
            statement_patterns=patterns,
            caption_text=caption_text,
            headers_text=headers_text,
            context_text=context_text,
        )
        for statement_type, patterns in _STATEMENT_PATTERNS.items()
    }
    if not scores:
        return None

    winner, winner_score = max(scores.items(), key=lambda item: item[1])
    if winner_score < _STATEMENT_CLASSIFICATION_MIN_SCORE:
        if winner_score < _STATEMENT_CLASSIFICATION_CONTEXT_ONLY_MIN_SCORE:
            return None
        if _has_caption_or_header_signal(
            statement_patterns=_STATEMENT_PATTERNS[winner],
            caption_text=caption_text,
            headers_text=headers_text,
        ):
            return winner
        return None

    runner_up_score = max(
        (score for statement_type, score in scores.items() if statement_type != winner),
        default=0,
    )
    if winner_score == runner_up_score:
        return None
    return winner


def select_report_statement_tables(
    *,
    statement_type: str,
    tables: list[Any],
    parse_table_dataframe: Callable[[Any], Optional[pd.DataFrame]],
) -> list[Any]:
    """按报告类规则选择财务报表候选表。

    选择顺序：
    1. 先排除 layout 表；
    2. 优先在 `is_financial=True` 的表里做 caption/header/context 分类；
    3. 若一个都没命中，再扩大到全部非 layout 表做 row-signal fallback。

    Args:
        statement_type: 目标报表类型。
        tables: 原始表格列表。
        parse_table_dataframe: 表格对象到 DataFrame 的解析函数。

    Returns:
        候选表格列表。

    Raises:
        RuntimeError: 筛选失败时抛出。
    """

    normalized_statement_type = str(statement_type or "").strip().lower()
    if normalized_statement_type not in REPORT_FORM_SUPPORTED_STATEMENT_TYPES:
        return []

    non_layout_tables = [
        table
        for table in tables
        if str(getattr(table, "table_type", "") or "").strip().lower() != "layout"
    ]
    if not non_layout_tables:
        return []

    financial_tables = [
        table for table in non_layout_tables if bool(getattr(table, "is_financial", False))
    ]
    classified_tables = [
        table
        for table in financial_tables
        if classify_report_statement_type_for_table(
            caption=getattr(table, "caption", None),
            headers=getattr(table, "headers", None),
            context_before=str(getattr(table, "context_before", "") or ""),
        )
        == normalized_statement_type
    ]
    if classified_tables:
        return classified_tables

    row_signal_tables = _select_html_statement_tables_by_row_signals(
        tables=non_layout_tables,
        line_item_patterns=_STATEMENT_LINE_ITEM_PATTERNS.get(normalized_statement_type, ()),
        min_hits=_ROW_SIGNAL_MIN_HITS_BY_STATEMENT.get(normalized_statement_type, 1),
        parse_table_dataframe=parse_table_dataframe,
    )
    if row_signal_tables:
        return row_signal_tables

    return _select_report_statement_tables_by_relaxed_row_signals(
        statement_type=normalized_statement_type,
        tables=non_layout_tables,
        parse_table_dataframe=parse_table_dataframe,
    )


def _select_report_statement_tables_by_relaxed_row_signals(
    *,
    statement_type: str,
    tables: list[Any],
    parse_table_dataframe: Callable[[Any], Optional[pd.DataFrame]],
) -> list[Any]:
    """按更宽松的行标签语义信号补充筛选候选报表表格。

    当标准 caption/header 分类和严格 row-signal 都未命中时，部分 20-F/年报附件
    仍可能包含可结构化的报表表格，只是标题不标准、行标签更偏交易说明或组合报表。
    这里沿用同一套 HTML 结构化入口，但放宽行标签词表并提高最低命中阈值，
    以支持无 XBRL 场景下的 HTML fallback，同时避免把普通附注表误收进来。

    Args:
        statement_type: 目标报表类型。
        tables: 非 layout 表格列表。
        parse_table_dataframe: 表格对象到 DataFrame 的解析函数。

    Returns:
        宽松规则筛出的候选表格列表。

    Raises:
        RuntimeError: 筛选失败时抛出。
    """

    return _select_html_statement_tables_by_row_signals(
        tables=tables,
        line_item_patterns=_RELAXED_STATEMENT_LINE_ITEM_PATTERNS.get(statement_type, ()),
        min_hits=_RELAXED_ROW_SIGNAL_MIN_HITS_BY_STATEMENT.get(statement_type, 3),
        parse_table_dataframe=parse_table_dataframe,
    )


def _normalize_report_statement_text(value: str) -> str:
    """标准化报表分类文本。

    Args:
        value: 原始文本。

    Returns:
        统一大小写和空白后的文本。

    Raises:
        RuntimeError: 标准化失败时抛出。
    """

    return _normalize_whitespace(value).lower()


def _looks_like_non_statement_table(
    *,
    caption_text: str,
    headers_text: str,
) -> bool:
    """判断表格是否属于目录、附注或封面噪声表。

    Args:
        caption_text: 规范化 caption 文本。
        headers_text: 规范化 headers 文本。

    Returns:
        命中噪声模式且缺乏报表信号时返回 ``True``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    caption_or_header = f"{caption_text} {headers_text}".strip()
    if not caption_or_header:
        return False
    caption_has_noise = any(pattern.search(caption_text) for pattern in _NON_STATEMENT_TABLE_PATTERNS)
    if caption_has_noise:
        caption_has_statement_signal = any(
            _has_caption_or_header_signal(
                statement_patterns=patterns,
                caption_text=caption_text,
                headers_text="",
            )
            for patterns in _STATEMENT_PATTERNS.values()
        )
        if not caption_has_statement_signal:
            return True

    has_noise_pattern = any(pattern.search(caption_or_header) for pattern in _NON_STATEMENT_TABLE_PATTERNS)
    if not has_noise_pattern:
        return False
    has_statement_signal = any(
        _has_caption_or_header_signal(
            statement_patterns=patterns,
            caption_text=caption_text,
            headers_text=headers_text,
        )
        for patterns in _STATEMENT_PATTERNS.values()
    )
    return not has_statement_signal


def _score_statement_type(
    *,
    statement_type: str,
    statement_patterns: tuple[re.Pattern[str], ...],
    caption_text: str,
    headers_text: str,
    context_text: str,
) -> int:
    """计算某报表类型的匹配分数。

    Args:
        statement_type: 报表类型。
        statement_patterns: 该报表类型的关键词正则。
        caption_text: 规范化 caption 文本。
        headers_text: 规范化 headers 文本。
        context_text: 规范化上下文文本。

    Returns:
        匹配分数。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    caption_hits = _count_pattern_hits(statement_patterns=statement_patterns, text=caption_text)
    header_hits = _count_pattern_hits(statement_patterns=statement_patterns, text=headers_text)
    context_hits = _count_pattern_hits(statement_patterns=statement_patterns, text=context_text)
    line_item_hits = _count_pattern_hits(
        statement_patterns=_STATEMENT_LINE_ITEM_PATTERNS.get(statement_type, ()),
        text=headers_text,
    )
    return (
        caption_hits * _STATEMENT_CLASSIFICATION_WEIGHTS["caption"]
        + header_hits * _STATEMENT_CLASSIFICATION_WEIGHTS["headers"]
        + context_hits * _STATEMENT_CLASSIFICATION_WEIGHTS["context"]
        + line_item_hits * _STATEMENT_LINE_ITEM_WEIGHT
    )


def _count_pattern_hits(
    *,
    statement_patterns: tuple[re.Pattern[str], ...],
    text: str,
) -> int:
    """统计文本命中的模式数。

    Args:
        statement_patterns: 目标模式集合。
        text: 待匹配文本。

    Returns:
        命中的模式数量。

    Raises:
        RuntimeError: 统计失败时抛出。
    """

    if not text:
        return 0
    return sum(1 for pattern in statement_patterns if pattern.search(text))


def _has_caption_or_header_signal(
    *,
    statement_patterns: tuple[re.Pattern[str], ...],
    caption_text: str,
    headers_text: str,
) -> bool:
    """判断 caption/headers 是否包含报表类型信号。

    Args:
        statement_patterns: 目标模式集合。
        caption_text: 规范化 caption 文本。
        headers_text: 规范化 headers 文本。

    Returns:
        任一模式命中时返回 ``True``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    return any(
        pattern.search(caption_text) or pattern.search(headers_text)
        for pattern in statement_patterns
    )


__all__ = [
    "REPORT_FORM_HTML_FALLBACK_REASONS",
    "REPORT_FORM_SUPPORTED_STATEMENT_TYPES",
    "classify_report_statement_type_for_table",
    "select_report_statement_tables",
    "should_apply_report_statement_html_fallback",
]
