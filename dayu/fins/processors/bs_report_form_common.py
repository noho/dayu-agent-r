"""BS 报告类表单处理器基类。

本模块提供基于 BeautifulSoup 的报告类表单（10-K/10-Q/20-F）处理器共享能力：
- 复用 `_VirtualSectionProcessorMixin` 的虚拟章节切分；
- 独立加载 XBRL 提供 `get_financial_statement` / `query_xbrl_facts` 能力；
- 不依赖 edgartools 黑箱，HTML 解析完全由 BeautifulSoup 驱动。

设计意图：
- 与 `_BaseSecReportFormProcessor`（基于 edgartools/SecProcessor）平行，
  提供另一条技术路线的报告类表单处理器；
- 便于对比 LLM 可喂性和代码可维护性。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Optional

from edgar.xbrl import XBRL
import pandas as pd

from .financial_base import (
    FinancialMeta,
    FinancialStatementResult,
    XbrlFactsResult,
)
from dayu.documents.processors.bs_processor import BSProcessor
from dayu.documents.processors.source import Source
from dayu.documents.processors.table_utils import parse_html_table_dataframe

from dayu.fins.domain.filing_semantics import normalize_sec_form_type_for_matching as _parse_report_sec_form
from .fins_bs_processor import FinsBSProcessor
from .sec_form_section_common import _VirtualSectionProcessorMixin

# XBRL 辅助函数直接从拆分后的 sec_xbrl_query 模块导入（这些函数与 edgartools
# 文档解析无关，仅操作 XBRL 对象和 DataFrame，属于共享工具逻辑）。
from .sec_xbrl_query import (
    _STATEMENT_METHODS,
    _build_period_summary,
    _build_statement_rows,
    _extract_period_columns,
    _infer_currency_from_units,
    _infer_units_from_xbrl_query,
    _infer_xbrl_taxonomy,
    _normalize_fact_row,
    _normalize_query_statement_type,
    _query_facts_rows,
    build_statement_locator,
)
from .sec_table_extraction import _safe_statement_dataframe
from dayu.fins.xbrl_file_discovery import discover_xbrl_files
from .html_financial_statement_common import (
    build_html_statement_result_from_tables as _build_html_statement_result_from_tables,
)
from .report_form_financial_statement_common import (
    REPORT_FORM_SUPPORTED_STATEMENT_TYPES,
    select_report_statement_tables as _select_report_statement_tables,
    should_apply_report_statement_html_fallback as _should_apply_report_statement_html_fallback,
)


def _parse_report_table_dataframe_from_bs(table: Any) -> Optional[pd.DataFrame]:
    """从 BSProcessor 表格对象安全提取 DataFrame。

    Args:
        table: BS 路线内部表格对象。

    Returns:
        DataFrame；不可用时返回 ``None``。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    table_tag = getattr(table, "tag", None)
    if table_tag is None:
        return None
    return parse_html_table_dataframe(table_tag)


class _BaseBsReportFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor):
    """基于 BeautifulSoup 的报告类表单处理器基类。

    继承链：
    ``_BaseBsReportFormProcessor → _VirtualSectionProcessorMixin → FinsBSProcessor → BSProcessor``

    虚拟章节切分复用 ``_VirtualSectionProcessorMixin``，
    XBRL 能力通过独立加载实现（不经过 edgartools 文档对象）。
    """

    _SUPPORTED_FORMS: ClassVar[frozenset[str]] = frozenset()
    _MIN_VIRTUAL_SECTIONS: ClassVar[int] = 3

    def __init__(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> None:
        """初始化处理器。

        执行顺序：
        1. ``FinsBSProcessor.__init__``（BeautifulSoup 解析 + 表格金融标注）；
        2. XBRL 延迟加载状态初始化；
        3. 虚拟章节切分。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            无。

        Raises:
            ValueError: 参数非法时抛出。
            RuntimeError: 解析失败时抛出。
        """

        super().__init__(source=source, form_type=form_type, media_type=media_type)
        # 记录源文件路径用于 XBRL 文件发现
        self._source_path = source.materialize(suffix=".html")

        # XBRL 延迟加载状态
        self._xbrl: Optional[XBRL] = None
        self._xbrl_loaded: bool = False
        self._xbrl_taxonomy: Optional[str] = None
        self._xbrl_taxonomy_loaded: bool = False

        # 虚拟章节切分（标记不足时自动回退 BSProcessor 原生章节）
        self._initialize_virtual_sections(min_sections=self._MIN_VIRTUAL_SECTIONS)

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> bool:
        """判断是否支持处理指定报告类表单。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            是否支持。

        Raises:
            OSError: 文件访问失败时可能抛出。
        """

        normalized_form = _parse_report_sec_form(form_type)
        if normalized_form not in cls._SUPPORTED_FORMS:
            return False
        # 复用 BSProcessor 的文件类型可解析能力判断
        return BSProcessor.supports(source, form_type=form_type, media_type=media_type)

    def _collect_document_text(self) -> str:
        """提取用于报告类 marker 检测的全文文本（尽量保留换行结构）。

        对 10-K/10-Q/20-F 而言，部分 Item 标题依赖换行边界识别。
        ``BSProcessor.get_full_text()`` 会归一化空白并压平成单行，
        容易丢失“行首编号 + 标题”结构信号。

        因此报告类 BS 路线复用父类 ``__init__`` 已解析并清理过的
        ``_root`` DOM 树，以 ``separator="\\n"`` 提取文本保留换行结构，
        避免重新读取 HTML 文件并重复创建 BeautifulSoup 对象。

        Args:
            无。

        Returns:
            保留基础换行结构的全文文本；失败时回退父类结果。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        try:
            # 复用父类 __init__ 已解析的 DOM 树，避免二次 BS 解析开销
            extracted = self._root.get_text(separator="\n", strip=True).strip()
            if extracted:
                return extracted
        except Exception:
            pass
        return super()._collect_document_text()

    # ── XBRL 财务能力 ──────────────────────────────────────────

    def get_financial_statement(
        self,
        statement_type: str,
        financials: Optional[dict[str, Any]] = None,
        *,
        meta: Optional[FinancialMeta] = None,
    ) -> FinancialStatementResult:
        """获取标准财务报表。

        通过独立加载 XBRL 文件获取财务数据，不依赖 edgartools 文档对象。

        Args:
            statement_type: 报表类型。
            financials: 预留参数，当前实现不使用。
            meta: 预留参数，当前实现不使用。

        Returns:
            财务报表结果。

        Raises:
            RuntimeError: XBRL 读取或转换失败时抛出。
        """

        del financials
        del meta

        normalized_statement_type = statement_type.strip().lower()
        base_result: FinancialStatementResult = {
            "statement_type": statement_type,
            "periods": [],
            "rows": [],
            "currency": None,
            "units": None,
            "scale": None,
            "data_quality": "partial",
        }
        if normalized_statement_type not in _STATEMENT_METHODS:
            base_result["reason"] = "unsupported_statement_type"
            return base_result

        xbrl_result, xbrl_reason = self._get_statement_from_xbrl(
            statement_type=statement_type,
            normalized_statement_type=normalized_statement_type,
        )
        if xbrl_result is not None:
            return xbrl_result

        base_result["reason"] = xbrl_reason or "xbrl_not_available"
        if normalized_statement_type not in REPORT_FORM_SUPPORTED_STATEMENT_TYPES:
            return base_result
        if not _should_apply_report_statement_html_fallback(base_result["reason"]):
            return base_result

        candidate_tables = self._get_report_statement_tables(normalized_statement_type)
        if not candidate_tables:
            return base_result
        extracted = self._build_html_statement_from_tables(
            statement_type=normalized_statement_type,
            tables=candidate_tables,
        )
        if extracted is None:
            base_result["reason"] = "low_confidence_extraction"
            return base_result
        return extracted

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
            XBRL 查询结果。

        Raises:
            RuntimeError: 查询执行失败时抛出。
        """

        normalized_concepts = [str(item).strip() for item in concepts if str(item).strip()]
        normalized_statement_type = _normalize_query_statement_type(statement_type)
        query_params = {
            "concepts": normalized_concepts,
            "statement_type": normalized_statement_type or statement_type,
            "filters_applied": {
                "period_end": period_end,
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "min_value": min_value,
                "max_value": max_value,
            },
        }
        if not normalized_concepts:
            return {
                "query_params": query_params,
                "facts": [],
                "total": 0,
            }

        xbrl = self._get_xbrl()
        if xbrl is None:
            return {
                "query_params": query_params,
                "facts": [],
                "total": 0,
                "data_quality": "partial",
                "reason": "xbrl_not_available",
            }

        rows = _query_facts_rows(
            xbrl=xbrl,
            concepts=normalized_concepts,
            statement_type=normalized_statement_type,
            period_end=period_end,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            min_value=min_value,
            max_value=max_value,
        )
        facts = [_normalize_fact_row(row) for row in rows]
        return {
            "query_params": query_params,
            "facts": facts,
            "total": len(facts),
        }

    def _get_statement_from_xbrl(
        self,
        *,
        statement_type: str,
        normalized_statement_type: str,
    ) -> tuple[Optional[FinancialStatementResult], Optional[str]]:
        """从 XBRL 提取财务报表并返回失败原因。

        Args:
            statement_type: 原始报表类型。
            normalized_statement_type: 标准化后的报表类型。

        Returns:
            ``(结果, 失败原因)`` 二元组。成功时失败原因为 ``None``。

        Raises:
            RuntimeError: XBRL 读取失败时抛出。
        """

        method_name = _STATEMENT_METHODS.get(normalized_statement_type)
        if method_name is None:
            return None, "unsupported_statement_type"

        xbrl = self._get_xbrl()
        if xbrl is None:
            return None, "xbrl_not_available"

        statements = getattr(xbrl, "statements", None)
        method = getattr(statements, method_name, None)
        if not callable(method):
            return None, "statement_method_missing"

        statement_obj = method()
        if statement_obj is None:
            return None, "statement_not_found"

        statement_df = _safe_statement_dataframe(statement_obj)
        if statement_df is None or statement_df.empty:
            return None, "statement_empty"

        period_columns = _extract_period_columns(statement_df.columns)
        rows = _build_statement_rows(statement_df, period_columns)
        periods = [_build_period_summary(period) for period in period_columns]
        units = _infer_units_from_xbrl_query(xbrl)
        currency = _infer_currency_from_units(units)
        return (
            {
                "statement_type": statement_type,
                "periods": periods,
                "rows": rows,
                "currency": currency,
                "units": units,
                "scale": None,
                "data_quality": "xbrl" if rows else "partial",
                "statement_locator": build_statement_locator(
                    statement_type=statement_type,
                    periods=periods,
                    rows=rows,
                ),
            },
            None,
        )

    def _get_report_statement_tables(self, statement_type: str) -> list[Any]:
        """获取报告类表单的财务报表候选表。

        Args:
            statement_type: 目标报表类型。

        Returns:
            候选表格列表。

        Raises:
            RuntimeError: 筛选失败时抛出。
        """

        return _select_report_statement_tables(
            statement_type=statement_type,
            tables=list(getattr(self, "_tables", [])),
            parse_table_dataframe=_parse_report_table_dataframe_from_bs,
        )

    def _build_html_statement_from_tables(
        self,
        *,
        statement_type: str,
        tables: list[Any],
    ) -> Optional[FinancialStatementResult]:
        """从候选 HTML 表中构建结构化财务报表。

        Args:
            statement_type: 目标报表类型。
            tables: 候选表格列表。

        Returns:
            结构化财务报表结果；失败时返回 ``None``。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return _build_html_statement_result_from_tables(
            statement_type=statement_type,
            tables=tables,
            parse_table_dataframe=_parse_report_table_dataframe_from_bs,
        )

    def _get_xbrl(self) -> Optional[XBRL]:
        """延迟加载并缓存 XBRL 对象。

        通过发现源文件同目录下的 XBRL 关联文件独立构建，
        不经过 edgartools HTMLParser。

        Args:
            无。

        Returns:
            ``XBRL`` 实例或 ``None``。

        Raises:
            RuntimeError: XBRL 构建失败时抛出。
        """

        if self._xbrl_loaded:
            return self._xbrl

        self._xbrl_loaded = True
        xbrl_files = discover_xbrl_files(self._source_path.parent)
        instance_file = xbrl_files.get("instance")
        schema_file = xbrl_files.get("schema")
        if instance_file is None or schema_file is None:
            self._xbrl = None
            return None
        try:
            self._xbrl = XBRL.from_files(
                instance_file=instance_file,
                schema_file=schema_file,
                presentation_file=xbrl_files.get("presentation"),
                calculation_file=xbrl_files.get("calculation"),
                definition_file=xbrl_files.get("definition"),
                label_file=xbrl_files.get("label"),
            )
        except Exception:
            self._xbrl = None
        return self._xbrl

    def get_xbrl_taxonomy(self) -> Optional[str]:
        """读取当前文档 XBRL taxonomy。

        Args:
            无。

        Returns:
            taxonomy（``us-gaap`` / ``ifrs-full``）或 ``None``。

        Raises:
            RuntimeError: 解析失败时抛出。
        """

        if self._xbrl_taxonomy_loaded:
            return self._xbrl_taxonomy
        self._xbrl_taxonomy_loaded = True
        xbrl = self._get_xbrl()
        if xbrl is None:
            self._xbrl_taxonomy = None
            return None
        self._xbrl_taxonomy = _infer_xbrl_taxonomy(xbrl)
        return self._xbrl_taxonomy


__all__ = [
    "_BaseBsReportFormProcessor",
]
