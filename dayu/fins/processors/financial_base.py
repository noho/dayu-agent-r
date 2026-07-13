"""Fins processor 的财务能力协议。

财务报表与 XBRL 结果类型由 ``dayu.fins.domain`` 拥有；本模块只声明
processor 能力，不兼容转发领域结果类型。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NotRequired, Protocol, TypedDict

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.financial_result_contract import FinancialStatementResult
from dayu.fins.domain.xbrl_result_contract import XbrlFactsResult


class FinancialMeta(TypedDict):
    """processor 可选消费的财务文档元信息。"""

    source_kind: NotRequired[str]
    document_id: NotRequired[str]


class FinancialDataProcessor(Protocol):
    """财务报表与 XBRL 查询能力协议。"""

    def get_financial_statement(
        self,
        statement_type: str,
        financials: Mapping[str, JsonValue] | None = None,
        *,
        meta: FinancialMeta | None = None,
    ) -> FinancialStatementResult:
        """读取财务报表。

        Args:
            statement_type: 报表类型。
            financials: 可选财务缓存。
            meta: 可选文档元信息。

        Returns:
            完整的 producer-owned 财务报表结果。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        ...

    def query_xbrl_facts(
        self,
        concepts: list[str],
        statement_type: str | None = None,
        period_end: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> XbrlFactsResult:
        """查询 XBRL facts。

        Args:
            concepts: XBRL 概念列表。
            statement_type: 可选报表类型。
            period_end: 可选期末日期。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值筛选。
            max_value: 可选最大值筛选。

        Returns:
            完整的 producer-owned XBRL facts 结果。

        Raises:
            RuntimeError: 查询失败时抛出。
        """

        ...


__all__ = ["FinancialDataProcessor", "FinancialMeta"]
