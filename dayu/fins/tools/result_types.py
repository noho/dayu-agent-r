"""FinsReadRuntime 返回值类型定义。

本模块为 FinsReadRuntime 每个 public 方法定义结构化返回类型（TypedDict），
消除方法签名中的 ``dict[str, Any]``，使消费方获得编译期键检查。

设计原则：
- 默认 ``total=True``（所有字段 Required）；仅条件出现的键标注 ``NotRequired``。
- 深层嵌套结构（单条 match / 单条 row / 单条 fact 等）保留 ``dict[str, Any]``，
  后续可按需进一步收窄。
- ``get_financial_statement`` 和 ``query_xbrl_facts`` 逐字段投影已校验的领域结果，
  核心业务字段全部 required。
- ``NotSupportedResult`` 为三个降级路径共享返回类型，因 ``payload.update()``
  动态附加字段，保持 ``total=False`` 并通过 ``cast`` 桥接。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, NotRequired, TypedDict

from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.base import SectionSummary, TableSummary
from dayu.fins.domain.financial_result_contract import (
    FinancialPeriod,
    FinancialScale,
    FinancialStatementReason,
    StatementLocator,
)
from dayu.fins.domain.filing_semantics import FinancialDataQuality
from dayu.fins.domain.xbrl_result_contract import XbrlQueryReason

# ---------------------------------------------------------------------------
# 共享子结构
# ---------------------------------------------------------------------------


class ErrorDetail(TypedDict):
    """工具错误详情。"""

    code: str
    message: str


class CompanyInfo(TypedDict):
    """公司基本信息。"""

    ticker: str
    name: str
    market: str


class ListDocumentsFilters(TypedDict):
    """list_documents 过滤条件回显。"""

    document_types: list[str] | None
    fiscal_years: list[int] | None
    fiscal_periods: list[str] | None


# ---------------------------------------------------------------------------
# NotSupportedResult — 三个降级路径共享
# ---------------------------------------------------------------------------


class _NotSupportedBase(TypedDict):
    """降级返回的基础字段，始终由 ``_build_not_supported_result`` 填充。"""

    ticker: str
    document_id: str
    supported: bool
    error: ErrorDetail


class NotSupportedResult(_NotSupportedBase, total=False):
    """能力不支持时的降级返回结构。

    基础字段（ticker, document_id, supported, error）始终存在（继承 Required）；
    各方法降级路径通过 ``payload.update()`` 动态附加回显字段，保持
    ``total=False`` 并搭配 ``cast()`` 使用。
    """

    # 各方法降级路径可能附带不同回显字段
    page_no: int
    statement_type: str
    concepts: list[str]


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------


class ListDocumentsResult(TypedDict):
    """``list_documents`` 返回结构。"""

    company: CompanyInfo
    filters: ListDocumentsFilters
    recommended_documents: dict[str, str | None]
    documents: Sequence[Mapping[str, JsonValue]]
    total: int
    matched: int
    match_status: str
    suggestion: NotRequired[dict[str, Any]]


# ---------------------------------------------------------------------------
# get_document_sections
# ---------------------------------------------------------------------------


class DocumentSectionsResult(TypedDict):
    """``get_document_sections`` 返回结构。"""

    ticker: str
    document_id: str
    sections: list[dict[str, Any]]
    citation: dict[str, Any]


# ---------------------------------------------------------------------------
# read_section
# ---------------------------------------------------------------------------


class SectionContentResult(TypedDict):
    """``read_section`` 返回结构。

    所有字段无条件赋值；``title`` / ``item`` / ``topic`` / ``page_range``
    的值可能为 ``None``。
    """

    ticker: str
    document_id: str
    ref: str
    title: str | None
    item: str | None
    topic: str | None
    content: str
    children: list[dict[str, str]]
    page_range: list[int] | None
    content_word_count: int
    citation: dict[str, Any]


# ---------------------------------------------------------------------------
# search_document（单查询 + 批量查询）
# ---------------------------------------------------------------------------


class SearchDocumentResult(TypedDict):
    """``search_document`` 返回结构。

    单查询与批量查询共享此结构。公共必有字段默认 Required，
    路径差异字段使用 ``NotRequired``：

    - 单查询：总有 ``next_section_to_read``，无 ``queries`` / ``next_section_by_query``
    - 批量查询：总有 ``queries`` / ``next_section_by_query``，无 ``next_section_to_read``
    - ``hint`` 仅在有搜索提示时出现
    - ``diagnostics`` 仅内部使用，被 ``fins_tools.py`` 包装层 ``pop``
    """

    ticker: str
    document_id: str
    query: str | None
    mode: str
    searched_in: str
    match_quality: dict[str, Any]
    matches: list[dict[str, Any]]
    total_matches: int
    citation: dict[str, Any]
    # 路径差异字段
    queries: NotRequired[list[str]]
    next_section_to_read: NotRequired[dict[str, Any] | None]
    next_section_by_query: NotRequired[dict[str, dict[str, Any] | None]]
    hint: NotRequired[str]
    diagnostics: NotRequired[dict[str, Any]]


# ---------------------------------------------------------------------------
# list_tables
# ---------------------------------------------------------------------------


class TablesListResult(TypedDict):
    """``list_tables`` 返回结构。"""

    ticker: str
    document_id: str
    tables: list[dict[str, Any]]
    total: int
    financial_count: int
    citation: dict[str, Any]


# ---------------------------------------------------------------------------
# get_table
# ---------------------------------------------------------------------------


class TableDetailResult(TypedDict):
    """``get_table`` 返回结构。

    必有字段默认 Required；``within_section`` / ``caption`` / ``page_no``
    仅当数据存在时附加。
    """

    ticker: str
    document_id: str
    table_ref: str
    data: dict[str, Any]
    row_count: int
    col_count: int
    is_financial: bool
    table_type: str | None
    citation: dict[str, Any]
    within_section: NotRequired[dict[str, str]]
    caption: NotRequired[str]
    page_no: NotRequired[int]


# ---------------------------------------------------------------------------
# get_page_content
# ---------------------------------------------------------------------------


class PageContentResult(TypedDict):
    """``get_page_content`` 返回结构。"""

    ticker: str
    document_id: str
    page_no: int
    sections: list[SectionSummary]
    tables: list[TableSummary]
    text_preview: str
    has_content: bool
    total_items: int
    supported: bool
    citation: dict[str, Any]


# ---------------------------------------------------------------------------
# get_financial_statement
# ---------------------------------------------------------------------------


class FinancialStatementResult(TypedDict):
    """``get_financial_statement`` 的完整公共投影。"""

    ticker: str
    document_id: str
    citation: dict[str, Any]
    statement_type: str
    periods: list[FinancialPeriod]
    rows: list[dict[str, JsonValue]]
    currency: str | None
    units: str | None
    scale: FinancialScale | None
    data_quality: FinancialDataQuality
    reason: FinancialStatementReason | None
    statement_locator: StatementLocator


# ---------------------------------------------------------------------------
# query_xbrl_facts
# ---------------------------------------------------------------------------


class _XbrlQueryParamsBase(TypedDict):
    """查询参数核心字段。"""

    concepts: list[str]


class XbrlQueryParams(_XbrlQueryParamsBase, total=False):
    """XBRL 查询参数回显。"""

    statement_type: str | None
    period_end: str | None
    fiscal_year: int | None
    fiscal_period: str | None
    min_value: float | None
    max_value: float | None


class XbrlQueryResult(TypedDict):
    """``query_xbrl_facts`` 的完整公共投影。"""

    ticker: str
    document_id: str
    citation: dict[str, Any]
    query_params: XbrlQueryParams
    facts: list[dict[str, JsonValue]]
    total: int
    deduped_fact_count: int
    data_quality: FinancialDataQuality
    reason: XbrlQueryReason | None
