"""金融数据处理器协议与占位类型。

本模块定义金融业务域专有的协议和数据类型：
- ``FinancialDataProcessor``：财务数据处理能力协议
- ``FinancialStatementResult``：财务报表查询结果
- ``XbrlFactsResult``：XBRL 查询结果
- ``FinancialMeta``：财务元信息

这些类型仅在 fins 层使用，engine 层保持业务中立。
"""

from __future__ import annotations

from typing import Any, NotRequired, Optional, Protocol, TypedDict


class FinancialStatementResult(TypedDict):
    """财务报表结果。"""

    statement_type: str
    periods: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    currency: str | None
    units: str | None
    scale: str | None
    data_quality: str
    reason: NotRequired[str]
    statement_locator: NotRequired[dict[str, Any]]


class XbrlFactsResult(TypedDict):
    """XBRL 查询结果。"""

    query_params: dict[str, Any]
    facts: list[dict[str, Any]]
    total: int
    data_quality: NotRequired[str]
    reason: NotRequired[str]


class FinancialMeta(TypedDict, total=False):
    """财务元信息。"""

    source_kind: str
    document_id: str
    statement_locator: dict[str, Any]


class FinancialDataProcessor(Protocol):
    """财务数据能力协议。"""

    def get_financial_statement(
        self,
        statement_type: str,
        financials: Optional[dict[str, Any]] = None,
        *,
        meta: Optional[FinancialMeta] = None,
    ) -> FinancialStatementResult:
        """读取财务报表。

        Args:
            statement_type: 报表类型。
            financials: 可选财务缓存。
            meta: 可选元信息。

        Returns:
            报表结果。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        ...

    def query_xbrl_facts(
        self,
        concepts: list[str],
        statement_type: Optional[str] = None,
        period_end: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> XbrlFactsResult:
        """查询 XBRL facts。

        Args:
            concepts: XBRL 概念列表。
            statement_type: 可选报表类型。
            period_end: 可选期末日期（YYYY-MM-DD）。
            fiscal_year: 可选财年。
            fiscal_period: 可选财季。
            min_value: 可选最小值筛选。
            max_value: 可选最大值筛选。

        Returns:
            查询结果。

        Raises:
            RuntimeError: 查询失败时抛出。
        """

        ...


__all__ = [
    "FinancialDataProcessor",
    "FinancialMeta",
    "FinancialStatementResult",
    "XbrlFactsResult",
]
