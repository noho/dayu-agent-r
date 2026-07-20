"""FinsReadRuntime 返回值类型定义。

本模块为 FinsReadRuntime 每个 public 方法定义结构化返回类型（TypedDict），
并持有财务报表与 XBRL 结果的唯一公共投影和 LLM-facing 描述。

设计原则：
- 默认 ``total=True``（所有字段 Required）；仅条件出现的键标注 ``NotRequired``。
- 深层嵌套结构（单条 match / 单条 row / 单条 fact 等）保留 ``dict[str, Any]``，
  后续可按需进一步收窄。
- ``get_financial_statement`` 和 ``query_xbrl_facts`` 只通过本模块的小型 builder
  投影已校验的领域结果，可选原因仅在 producer 明确提供时出现。
- ``NotSupportedResult`` 为三个降级路径共享返回类型，因 ``payload.update()``
  动态附加字段，保持 ``total=False`` 并通过 ``cast`` 桥接。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final, NotRequired, TypedDict

from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.base import SectionSummary, TableSummary
from dayu.fins.domain.financial_result_contract import (
    FinancialPeriod,
    FinancialScale,
    FinancialStatementResult as ProducerFinancialStatementResult,
    FinancialStatementReason,
)
from dayu.fins.domain.filing_semantics import FinancialDataQuality
from dayu.fins.domain.xbrl_result_contract import (
    XbrlDataQuality,
    XbrlQueryParams,
    XbrlQueryReason,
)

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


class PublicFinancialStatementResult(TypedDict):
    """``get_financial_statement`` 的唯一公共投影。"""

    ticker: str
    document_id: str
    citation: dict[str, JsonValue]
    statement_type: str
    periods: list[FinancialPeriod]
    rows: list[dict[str, JsonValue]]
    currency: str | None
    units: str | None
    scale: FinancialScale | None
    data_quality: FinancialDataQuality
    reason: NotRequired[FinancialStatementReason]


# ---------------------------------------------------------------------------
# query_xbrl_facts
# ---------------------------------------------------------------------------


class PublicXbrlQueryResult(TypedDict):
    """``query_xbrl_facts`` 的唯一公共投影。"""

    ticker: str
    document_id: str
    citation: dict[str, JsonValue]
    query_params: XbrlQueryParams
    facts: list[dict[str, JsonValue]]
    fact_count: int
    data_quality: XbrlDataQuality
    reason: NotRequired[XbrlQueryReason]


_FINANCIAL_STATEMENT_RESULT_DESCRIPTION: Final[str] = (
    "读取标准财务报表。返回对象字段：ticker（string，必填，公司代码）；"
    "document_id（string，必填，仅用于引用本次文档）；citation（object，必填，来源引用）；"
    "statement_type（string，必填，报表类型）；periods（array，必填，每项含 "
    "period_end:string、fiscal_year:int|null、"
    "fiscal_period:FY|H1|Q1|Q2|Q3|Q4|null）；rows（array，必填，报表行）；"
    "currency（string|null，必填，币种）；units（string|null，必填，货币或计量单位）；"
    "scale（string|null，必填，允许 units|thousands|millions|billions|null，表示数值倍率）；"
    "data_quality（string，必填，允许 xbrl|extracted|partial）；reason（string，可选，"
    "只在 data_quality=partial 时出现）。reason 允许值与安全动作："
    "unsupported_statement_type 表示当前文档能力不支持该报表类型，不重复同一请求，改选其它合法"
    "报表类型或文档；xbrl_not_available 表示当前来源没有可用 XBRL 结果，不重复同一 XBRL 请求，"
    "改用财务报表抽取结果或其它申报文件并谨慎核验；statement_not_found 表示当前文档没有可用目标"
    "报表，不重复同一请求，改选其它合法报表类型或文档；low_confidence_extraction 表示抽取置信度"
    "不足，不直接作确定性结论，需用其它报表或来源交叉验证；scale_unavailable 表示数值倍率不可靠，"
    "禁止数量级判断或依赖倍率的比较，先核验 scale；period_semantics_unavailable 表示财期语义不可靠，"
    "禁止跨期比较，先核验期间归属；scale_and_period_semantics_unavailable 表示倍率与财期语义均不可靠，"
    "禁止数量级判断和跨期比较，分别核验 scale 与 period。最小示例："
    '{"ticker":"AAPL","document_id":"opaque-document-id","citation":'
    '{"source_type":"SEC_EDGAR","document_id":"opaque-document-id","ticker":"AAPL",'
    '"source_provider":"SEC_EDGAR"},"statement_type":"income","periods":[],"rows":[],'
    '"currency":null,"units":null,"scale":null,"data_quality":"partial",'
    '"reason":"statement_not_found"}'
)

_XBRL_QUERY_RESULT_DESCRIPTION: Final[str] = (
    "查询结构化 XBRL facts。返回对象字段：ticker（string，必填，公司代码）；document_id（string，"
    "必填，仅用于引用本次文档）；citation（object，必填，来源引用）；query_params（object，必填，"
    "实际查询参数的扁平副本，其中 concepts:string[] 必填，statement_type:string、period_end:string、"
    "fiscal_year:int、fiscal_period:FY|H1|Q1|Q2|Q3|Q4、min_value:number、max_value:number 均可选，"
    "缺席的过滤条件不会补 null）；facts（array，必填，规范化并稳定去重后的事实）；fact_count（int，"
    "必填，恒等于同一结果中 facts 的长度）；data_quality（string，必填，允许 xbrl|partial）；reason"
    "（string，可选，只在 data_quality=partial 时出现，允许 xbrl_not_available|query_partially_failed）。"
    "xbrl_not_available 表示当前来源没有可用 XBRL 结果，应改用财务报表或其它文档并核验；"
    "query_partially_failed 表示部分概念查询失败，只能使用已返回 facts，并用其它来源交叉验证。"
    "data_quality=xbrl 且 facts 为空表示查询正常完成但没有匹配事实。最小示例："
    '{"ticker":"AAPL","document_id":"opaque-document-id","citation":'
    '{"source_type":"SEC_EDGAR","document_id":"opaque-document-id","ticker":"AAPL",'
    '"source_provider":"SEC_EDGAR"},"query_params":{"concepts":["Revenue"]},'
    '"facts":[{"concept":"Revenue","value":100}],"fact_count":1,"data_quality":"xbrl"}'
)


def project_financial_statement_result(
    *,
    ticker: str,
    document_id: str,
    citation: Mapping[str, JsonValue],
    producer_result: ProducerFinancialStatementResult,
) -> PublicFinancialStatementResult:
    """把已校验财务报表结果投影为唯一公共结果。

    Args:
        ticker: 当前 borrowed snapshot 对应的公司代码。
        document_id: 当前 borrowed snapshot 对应的文档 ID。
        citation: 当前 borrowed snapshot 产生的来源引用。
        producer_result: 已由领域 owner 校验的财务报表结果。

    Returns:
        与输入引用解耦、仅含公共字段的财务报表结果。

    Raises:
        无。
    """

    result = PublicFinancialStatementResult(
        ticker=ticker,
        document_id=document_id,
        citation=dict(citation),
        statement_type=producer_result["statement_type"],
        periods=list(producer_result["periods"]),
        rows=[dict(row) for row in producer_result["rows"]],
        currency=producer_result["currency"],
        units=producer_result["units"],
        scale=producer_result["scale"],
        data_quality=producer_result["data_quality"],
    )
    if "reason" in producer_result:
        result["reason"] = producer_result["reason"]
    return result


def project_xbrl_query_result(
    *,
    ticker: str,
    document_id: str,
    citation: Mapping[str, JsonValue],
    query_params: XbrlQueryParams,
    returned_facts: Sequence[Mapping[str, JsonValue]],
    data_quality: XbrlDataQuality,
    optional_reason: XbrlQueryReason | None,
) -> PublicXbrlQueryResult:
    """把最终 XBRL facts 投影为唯一公共结果。

    Args:
        ticker: 当前 borrowed snapshot 对应的公司代码。
        document_id: 当前 borrowed snapshot 对应的文档 ID。
        citation: 当前 borrowed snapshot 产生的来源引用。
        query_params: producer 实际执行的扁平查询参数。
        returned_facts: 已完成规范化与稳定去重的最终 facts。
        data_quality: producer 拥有的数据质量。
        optional_reason: producer 可选的降级原因。

    Returns:
        查询参数、facts 与引用均为独立容器的公共 XBRL 结果。

    Raises:
        无。
    """

    returned_facts_copy = [dict(fact) for fact in returned_facts]
    result = PublicXbrlQueryResult(
        ticker=ticker,
        document_id=document_id,
        citation=dict(citation),
        query_params=query_params.copy(),
        facts=returned_facts_copy,
        fact_count=len(returned_facts_copy),
        data_quality=data_quality,
    )
    if optional_reason is not None:
        result["reason"] = optional_reason
    return result


def financial_statement_result_description() -> str:
    """返回自足的财务报表公共结果说明。

    Args:
        无。

    Returns:
        包含字段、类型、枚举、原因动作与最小示例的说明。

    Raises:
        无。
    """

    return _FINANCIAL_STATEMENT_RESULT_DESCRIPTION


def xbrl_query_result_description() -> str:
    """返回自足的 XBRL 公共结果说明。

    Args:
        无。

    Returns:
        包含字段、类型、枚举、可选原因与最小示例的说明。

    Raises:
        无。
    """

    return _XBRL_QUERY_RESULT_DESCRIPTION
