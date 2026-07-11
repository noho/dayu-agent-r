"""财报读取运行时。

该模块是财报工具与底层仓储/处理器之间的中间调用层，职责包括：
- 参数校验与标准化。
- `document_id -> source_kind -> source -> processor` 路由。
- 统一能力降级（`not_supported`）。
- 仅做进程内 LRU 缓存：Processor 按 `ticker + document_id`，source meta 按来源维度隔离。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock, RLock
from typing import Any, Final, Literal, Optional, Protocol, TypedDict, runtime_checkable

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins._log import Log
from dayu.fins.domain.document_models import FinsSourceProvider
from dayu.documents.processors.base import (
    DocumentProcessor,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)
from dayu.documents.processors.processor_registry import ProcessorRegistry
from .error_contract import ErrorCode
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.tool_models import Citation, SourceType
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from .bm25f_scorer import BM25FSectionIndex, build_section_bm25f_index
from .section_semantic import (
    build_section_path,
    resolve_section_semantic,
)
from .cache import ProcessorCacheKey, ProcessorLRUCache

# 从拆分模块导入（FinsReadRuntime 直接使用）
from .search_models import (
    QueryDiagnosis,
    SectionSemanticProfile,
    SEARCH_MODE_AUTO,
    _SEARCH_RANKING_VERSION,
)
from .search_engine import (
    _resolve_search_queries,
    _resolve_search_mode,
    _diagnose_search_query,
    _execute_query_search,
    _build_empty_search_strategy_hit_counts,
    _deduplicate_ranked_search_entries,
    _sort_ranked_search_entries,
    _build_evidence_matches,
    _build_section_semantic_profiles,
    _cap_entries_with_exact_priority,
)
from .result_types import (
    DocumentSectionsResult,
    FinancialStatementResult,
    ListDocumentsResult,
    NotSupportedResult,
    PageContentResult,
    SearchDocumentResult,
    StatementLocator,
    SectionContentResult,
    TableDetailResult,
    TablesListResult,
    XbrlQueryParams,
    XbrlQueryResult,
)
from dayu.fins._converters import normalize_optional_text, require_non_empty_text
from dayu.fins.ticker_normalization import try_normalize_ticker
from .read_runtime_helpers import (
    FinsReadArgumentError,
    FinsReadBusinessError,
    FinsReadCancelledError,
    _collect_parent_titles,
    _normalize_form_type_for_matching,
    _normalize_document_types,
    _normalize_section_children,
    _normalize_periods,
    _build_not_supported_result,
    _extract_page_range,
    _infer_fiscal_period,
    _infer_fiscal_year,
    _resolve_fiscal_year_with_fallback,
    _resolve_fiscal_period_with_fallback,
    _build_table_data_payload,
    _normalize_table_type,
    _normalize_json_scalar_text,
    _resolve_processor_taxonomy,
    _resolve_default_xbrl_concepts,
    _normalize_xbrl_query_payload,
    _build_match_quality,
    _build_search_hint,
    build_search_next_section_fields,
    raise_if_fins_cancelled,
    resolve_has_financial_data,
    resolve_document_type_for_source,
)

# 匹配 CJK 统一汉字（基本区 + 扩展A），用于检测查询词是否含中文
_CN_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _any_query_has_chinese(queries: list[str]) -> bool:
    """检测查询列表中是否存在含中文字符的查询词。"""
    return any(_CN_CHAR_RE.search(q) for q in queries)


# 中文查询在未命中时给出的操作引导提示（通用，不假设文档语言）
_CHINESE_QUERY_NO_RESULTS_HINT = (
    "目标：把查询改成文档更可能命中的写法。允许动作：把中文词换成英文关键词再搜。"
    "不允许：继续用中文词反复重试。下一步：例如把“年度经常性收入”改成“annual recurring revenue”后再搜。"
)
_MISSING_TICKER_HINT = (
    "目标：先确认这家公司是否已被当前财报工具收录。允许动作：切到公司或网页来源确认公司标识。"
    "不允许：继续穷举 ticker 变体。下一步：先确认公司标识，再回到财报工具。"
)
_CITATION_PROVIDER_LABELS: Final[dict[FinsSourceProvider, str]] = {
    FinsSourceProvider.SEC_EDGAR: "SEC_EDGAR",
    FinsSourceProvider.CNINFO: "CNINFO",
    FinsSourceProvider.HKEXNEWS: "HKEXNEWS",
    FinsSourceProvider.USER_UPLOAD: "USER_UPLOAD",
}
"""source provider 到 LLM-facing provider 文本的唯一映射。"""

_FILING_SOURCE_TYPES_BY_PROVIDER: Final[dict[FinsSourceProvider, SourceType]] = {
    FinsSourceProvider.SEC_EDGAR: SourceType.SEC_EDGAR,
    FinsSourceProvider.CNINFO: SourceType.CNINFO,
    FinsSourceProvider.HKEXNEWS: SourceType.HKEXNEWS,
    FinsSourceProvider.USER_UPLOAD: SourceType.UPLOADED,
}
"""filing citation source_type 的 provider 派生规则。"""

_SOURCE_META_CACHE_DEFAULT_MAX_ENTRIES: Final[int] = 512
"""source meta 实例缓存默认容量。"""

_RECOMMENDED_DOCUMENT_KEYS: Final[tuple[str, ...]] = (
    "latest_document_id",
    "recommended_for_company_overview_document_id",
    "latest_annual_report_document_id",
    "latest_quarterly_report_document_id",
    "latest_current_report_document_id",
    "latest_proxy_document_id",
    "latest_ownership_document_id",
    "latest_earnings_call_document_id",
    "latest_earnings_presentation_document_id",
    "latest_material_document_id",
)
"""list_documents 推荐槽位键集合。"""

_FISCAL_PERIOD_SORT_ORDER: Final[dict[str, int]] = {
    "FY": 5,
    "H1": 4,
    "Q4": 4,
    "Q3": 3,
    "Q2": 2,
    "Q1": 1,
}
"""source document 财期排序权重。"""


class _SourceDocumentMeta(TypedDict):
    """read runtime 使用的 source meta 投影。

    该类型只承诺 read runtime 当前需要消费的字段；仓储 raw meta 的完整
    JSON schema 仍由 storage owner 持有。
    """

    form_type: str | None
    material_name: JsonValue | None
    fiscal_year: int | None
    fiscal_period: str | None
    report_date: str | None
    filing_date: str | None
    amended: bool
    internal_document_id: str | None
    accession_number: str | None
    ingest_method: str | None
    source_provider: str | None
    is_deleted: bool
    ingest_complete: bool


@dataclass(frozen=True)
class _CachedSourceDocumentMeta:
    """source meta 缓存值。

    Attributes:
        meta: 已收窄的 source meta；文档不存在时为 ``None``。
    """

    meta: _SourceDocumentMeta | None


class _SourceDocumentSummary(TypedDict):
    """list_documents 内部 source 文档摘要。"""

    document_id: str
    source_kind: str
    form_type: str | None
    material_name: JsonValue | None
    fiscal_year: int | None
    fiscal_period: str | None
    report_date: str | None
    filing_date: str | None
    amended: bool
    has_financial_data: bool | None


class _ListedDocumentSummary(_SourceDocumentSummary):
    """附加 LLM-facing document_type 后的文档摘要。"""

    document_type: str


class _ProcessorPageContentPayload(TypedDict, total=False):
    """processor 分页能力返回载荷。"""

    sections: list[SectionSummary]
    tables: list[TableSummary]
    text_preview: str
    has_content: bool
    total_items: int
    supported: bool


class _ProcessorFinancialStatementPayload(TypedDict, total=False):
    """processor 财务报表能力返回载荷。"""

    statement_type: str
    currency: str | None
    units: str | None
    rows: list[dict[str, JsonValue]]
    statement_locator: StatementLocator
    period_labels: list[str]
    column_headers: list[str]
    header: dict[str, JsonValue]
    supported: bool
    data_quality: str
    reason: str


@runtime_checkable
class _PageContentReadProcessor(Protocol):
    """read runtime 的分页 processor 能力协议。"""

    def get_page_content(self, page_no: int) -> _ProcessorPageContentPayload:
        """读取指定页内容。

        Args:
            page_no: 1-based 页码。

        Returns:
            页面内容载荷。

        Raises:
            RuntimeError: 底层读取失败时抛出。
        """

        ...


@runtime_checkable
class _FinancialStatementReadProcessor(Protocol):
    """read runtime 的财务报表 processor 能力协议。"""

    def get_financial_statement(self, statement_type: str) -> _ProcessorFinancialStatementPayload:
        """读取指定类型的财务报表。

        Args:
            statement_type: 报表类型。

        Returns:
            财务报表载荷。

        Raises:
            RuntimeError: 底层读取失败时抛出。
        """

        ...


@runtime_checkable
class _XbrlFactsReadProcessor(Protocol):
    """read runtime 的 XBRL facts processor 能力协议。"""

    def query_xbrl_facts(
        self,
        *,
        concepts: list[str],
        statement_type: str | None = None,
        period_end: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> Mapping[str, JsonValue]:
        """查询 XBRL facts。

        Args:
            concepts: XBRL concept 列表。
            statement_type: 可选报表类型。
            period_end: 可选期间结束日。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值。
            max_value: 可选最大值。

        Returns:
            XBRL facts 原始载荷。

        Raises:
            RuntimeError: 底层查询失败时抛出。
        """

        ...


def _raise_if_fins_cancelled(cancellation_token: CancellationToken | None) -> None:
    """在财报读取慢边界执行协作式取消检查。

    Args:
        cancellation_token: Host 注入的取消观察令牌；未注入时为 None。

    Returns:
        无。

    Raises:
        FinsReadCancelledError: 当前工具调用已被 Host 取消时抛出。
    """

    raise_if_fins_cancelled(cancellation_token, message="财报读取工具调用已被取消。")


def _parse_source_document_meta(raw_meta: Mapping[str, JsonValue]) -> _SourceDocumentMeta:
    """把仓储 raw meta 收窄为 read runtime 本地投影。

    Args:
        raw_meta: 仓储返回的 source meta JSON 对象。

    Returns:
        read runtime 当前消费的 typed meta 投影。

    Raises:
        ValueError: bool 字段存在但不是 bool 时抛出。
        RuntimeError: 其它字段收窄失败时抛出。
    """

    fiscal_year_value = raw_meta.get("fiscal_year")
    fiscal_year = (
        fiscal_year_value if isinstance(fiscal_year_value, int) and not isinstance(fiscal_year_value, bool) else None
    )
    return {
        "form_type": _normalize_json_scalar_text(raw_meta.get("form_type")),
        "material_name": raw_meta.get("material_name"),
        "fiscal_year": fiscal_year,
        "fiscal_period": _normalize_json_scalar_text(raw_meta.get("fiscal_period")),
        "report_date": _normalize_json_scalar_text(raw_meta.get("report_date")),
        "filing_date": _normalize_json_scalar_text(raw_meta.get("filing_date")),
        "amended": _read_bool_meta_field(raw_meta, field_name="amended", default=False),
        "internal_document_id": _normalize_json_scalar_text(raw_meta.get("internal_document_id")),
        "accession_number": _normalize_json_scalar_text(raw_meta.get("accession_number")),
        "ingest_method": _normalize_json_scalar_text(raw_meta.get("ingest_method")),
        "source_provider": _normalize_json_scalar_text(raw_meta.get("source_provider")),
        "is_deleted": _read_bool_meta_field(raw_meta, field_name="is_deleted", default=False),
        "ingest_complete": _read_bool_meta_field(raw_meta, field_name="ingest_complete", default=True),
    }


def _read_bool_meta_field(raw_meta: Mapping[str, JsonValue], *, field_name: str, default: bool) -> bool:
    """读取 source meta 的 bool 字段并执行严格校验。

    Args:
        raw_meta: 仓储返回的 source meta JSON 对象。
        field_name: 需要读取的字段名。
        default: 字段缺省时使用的 storage contract 默认值。

    Returns:
        字段 bool 值或缺省默认值。

    Raises:
        ValueError: 字段存在但不是 bool 时抛出。
    """

    if field_name not in raw_meta:
        return default
    value = raw_meta[field_name]
    if isinstance(value, bool):
        return value
    raise ValueError(f"source meta 字段 {field_name} 必须为 bool")


def _source_document_meta_to_storage_payload(meta: _SourceDocumentMeta) -> dict[str, JsonValue]:
    """把 read runtime meta 投影转换为 storage provenance 可消费的 JSON。

    Args:
        meta: read runtime typed meta 投影。

    Returns:
        可传给 storage provenance helper 的 JSON 对象。

    Raises:
        RuntimeError: 转换失败时抛出。
    """

    return {
        "form_type": meta["form_type"],
        "material_name": meta["material_name"],
        "fiscal_year": meta["fiscal_year"],
        "fiscal_period": meta["fiscal_period"],
        "report_date": meta["report_date"],
        "filing_date": meta["filing_date"],
        "amended": meta["amended"],
        "internal_document_id": meta["internal_document_id"],
        "accession_number": meta["accession_number"],
        "ingest_method": meta["ingest_method"],
        "source_provider": meta["source_provider"],
        "is_deleted": meta["is_deleted"],
        "ingest_complete": meta["ingest_complete"],
    }


def _source_document_recency_sort_key(
    item: _SourceDocumentSummary,
) -> tuple[int, str, str, int, int, str]:
    """构建 source document 摘要排序键。

    Args:
        item: read runtime typed source 文档摘要。

    Returns:
        可直接用于倒序排序的确定性键。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    report_date = item["report_date"] or ""
    filing_date = item["filing_date"] or ""
    has_explicit_date = bool(report_date or filing_date)
    fiscal_year = item["fiscal_year"] if item["fiscal_year"] is not None else -1
    fiscal_period_rank = _FISCAL_PERIOD_SORT_ORDER.get(item["fiscal_period"] or "", 0)
    has_fiscal_recency = fiscal_year > 0 or fiscal_period_rank > 0
    temporal_rank = 2 if has_explicit_date else 1 if has_fiscal_recency else 0
    primary_date = report_date or filing_date
    secondary_date = filing_date or report_date
    return (
        temporal_rank,
        primary_date,
        secondary_date,
        fiscal_year,
        fiscal_period_rank,
        item["document_id"],
    )


def _collect_available_document_types_for_source_documents(
    documents: list[_SourceDocumentSummary],
) -> list[str]:
    """提取 source document 列表中可用的 LLM-facing 文档类型。

    Args:
        documents: read runtime typed source 文档摘要列表。

    Returns:
        去重后的 document_type 列表。

    Raises:
        RuntimeError: 推导失败时抛出。
    """

    doc_types: set[str] = set()
    for item in documents:
        doc_types.add(
            resolve_document_type_for_source(
                form_type=item["form_type"],
                source_kind=item["source_kind"],
            )
        )
    return sorted(doc_types)


def _build_recommended_documents_for_list_result(
    documents: list[_ListedDocumentSummary],
) -> dict[str, str | None]:
    """构建 list_documents 推荐文档槽位。

    Args:
        documents: 已按时间倒序排列且附带 document_type 的文档列表。

    Returns:
        推荐槽位到 document_id 的映射；无推荐时值为 ``None``。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    recommendations: dict[str, str | None] = {key: None for key in _RECOMMENDED_DOCUMENT_KEYS}
    for item in documents:
        document_id = item["document_id"]
        doc_type = item["document_type"]
        if recommendations["latest_document_id"] is None:
            recommendations["latest_document_id"] = document_id
        if recommendations["latest_annual_report_document_id"] is None and doc_type == "annual_report":
            recommendations["latest_annual_report_document_id"] = document_id
        if recommendations["latest_quarterly_report_document_id"] is None and doc_type in {
            "quarterly_report",
            "semi_annual_report",
        }:
            recommendations["latest_quarterly_report_document_id"] = document_id
        if recommendations["latest_current_report_document_id"] is None and doc_type == "current_report":
            recommendations["latest_current_report_document_id"] = document_id
        if recommendations["latest_proxy_document_id"] is None and doc_type == "proxy":
            recommendations["latest_proxy_document_id"] = document_id
        if recommendations["latest_ownership_document_id"] is None and doc_type == "ownership":
            recommendations["latest_ownership_document_id"] = document_id
        if recommendations["latest_earnings_call_document_id"] is None and doc_type == "earnings_call":
            recommendations["latest_earnings_call_document_id"] = document_id
        if recommendations["latest_earnings_presentation_document_id"] is None and doc_type == "earnings_presentation":
            recommendations["latest_earnings_presentation_document_id"] = document_id
        if recommendations["latest_material_document_id"] is None and doc_type == "material":
            recommendations["latest_material_document_id"] = document_id
    recommendations["recommended_for_company_overview_document_id"] = (
        recommendations["latest_annual_report_document_id"]
        or recommendations["latest_quarterly_report_document_id"]
        or recommendations["latest_proxy_document_id"]
        or recommendations["latest_current_report_document_id"]
        or recommendations["latest_ownership_document_id"]
        or recommendations["latest_document_id"]
    )
    return recommendations


class FinsReadRuntime:
    """财报读取运行时。

    设计约束：
    - 不依赖 `processed/*.json` 产物。
    - 所有读取均通过实时 Processor 能力完成。
    - 缓存仅保留 Processor 实例。
    """

    MODULE = "FINS.READ_RUNTIME"

    def __init__(
        self,
        *,
        company_repository: CompanyMetaRepositoryProtocol,
        source_repository: SourceDocumentRepositoryProtocol,
        processed_repository: ProcessedDocumentRepositoryProtocol,
        processor_registry: ProcessorRegistry,
        processor_cache_max_entries: int = 128,
        source_meta_cache_max_entries: int = _SOURCE_META_CACHE_DEFAULT_MAX_ENTRIES,
    ) -> None:
        """初始化服务。

        Args:
            company_repository: 公司元数据仓储实现。
            source_repository: 源文档仓储实现。
            processed_repository: processed 文档仓储实现。
            processor_registry: 处理器注册表。
            processor_cache_max_entries: Processor LRU 缓存容量。
            source_meta_cache_max_entries: source meta LRU 缓存容量。

        Returns:
            无。

        Raises:
            ValueError: 当缓存容量非法时抛出。
        """

        if processor_cache_max_entries <= 0:
            raise ValueError("processor_cache_max_entries must be greater than 0")
        if source_meta_cache_max_entries <= 0:
            raise ValueError("source_meta_cache_max_entries must be greater than 0")
        self._company_repository = company_repository
        self._source_repository = source_repository
        self._processed_repository = processed_repository
        self._processor_registry = processor_registry
        self._processor_cache: ProcessorLRUCache[DocumentProcessor] = ProcessorLRUCache(
            max_entries=processor_cache_max_entries,
        )
        self._meta_cache: ProcessorLRUCache[_CachedSourceDocumentMeta] = ProcessorLRUCache(
            max_entries=source_meta_cache_max_entries,
        )
        self._creation_locks: dict[ProcessorCacheKey, Lock] = {}
        self._creation_locks_guard = RLock()

    def list_documents(
        self,
        *,
        ticker: str,
        document_types: Optional[list[str]] = None,
        fiscal_years: Optional[list[int]] = None,
        fiscal_periods: Optional[list[str]] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ListDocumentsResult:
        """列出可用文档。

        Args:
            ticker: 股票代码。
            document_types: 可选文档类型过滤（枚举数组，如 ["annual_report", "quarterly_report"]）。
            fiscal_years: 可选财年过滤。
            fiscal_periods: 可选财期过滤。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            文档列表结果。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
            RuntimeError: 仓储读取失败时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker = self._resolve_canonical_ticker(
            ticker=ticker,
            tool_name="list_documents",
            cancellation_token=cancellation_token,
        )
        normalized_document_types = _normalize_document_types(document_types)
        normalized_fiscal_periods = _normalize_periods(fiscal_periods)

        _raise_if_fins_cancelled(cancellation_token)
        company_name, market = self._read_company_info(normalized_ticker)
        _raise_if_fins_cancelled(cancellation_token)
        base_documents = self._collect_source_documents(
            normalized_ticker,
            cancellation_token=cancellation_token,
        )

        # 先为全量文档附加 document_type，供推荐槽位与过滤逻辑共享。
        documents_with_type: list[_ListedDocumentSummary] = []
        for item in base_documents:
            _raise_if_fins_cancelled(cancellation_token)
            output: _ListedDocumentSummary = {
                **item,
                "document_type": resolve_document_type_for_source(
                    form_type=item["form_type"],
                    source_kind=item["source_kind"],
                ),
            }
            documents_with_type.append(output)

        # 主过滤逻辑：按类型 / 财年 / 财期筛选；推荐槽位仍基于全量文档构建。
        filtered_documents: list[dict[str, JsonValue]] = []
        for item in documents_with_type:
            _raise_if_fins_cancelled(cancellation_token)
            doc_type = item["document_type"]
            if normalized_document_types is not None and doc_type not in normalized_document_types:
                continue
            fiscal_year = item["fiscal_year"]
            if fiscal_years and fiscal_year not in fiscal_years:
                continue
            fiscal_period = item["fiscal_period"]
            if normalized_fiscal_periods and fiscal_period not in normalized_fiscal_periods:
                continue
            # 屏蔽底层 SEC 表单名，不对 LLM 暴露。
            filtered_documents.append(
                {
                    "document_id": item["document_id"],
                    "source_kind": item["source_kind"],
                    "material_name": item["material_name"],
                    "fiscal_year": item["fiscal_year"],
                    "fiscal_period": item["fiscal_period"],
                    "report_date": item["report_date"],
                    "filing_date": item["filing_date"],
                    "amended": item["amended"],
                    "has_financial_data": item["has_financial_data"],
                    "document_type": item["document_type"],
                }
            )
        recommended_documents = _build_recommended_documents_for_list_result(documents_with_type)

        # 判定匹配状态并构建 suggestion
        if normalized_document_types is not None and len(filtered_documents) == 0:
            available = _collect_available_document_types_for_source_documents(base_documents)
            match_status = "no_match"
            suggestion: Optional[dict[str, Any]] = {
                "action": "broaden_filter",
                "available_document_types": available,
                "reason": "no_documents_matched_document_types",
            }
        else:
            match_status = "ok"
            suggestion = None

        result: ListDocumentsResult = {
            "company": {
                "ticker": normalized_ticker,
                "name": company_name,
                "market": market,
            },
            "filters": {
                "document_types": normalized_document_types,
                "fiscal_years": fiscal_years,
                "fiscal_periods": normalized_fiscal_periods,
            },
            "recommended_documents": recommended_documents,
            "documents": filtered_documents,
            "total": len(base_documents),
            "matched": len(filtered_documents),
            "match_status": match_status,
        }
        if suggestion is not None:
            result["suggestion"] = suggestion

        return result

    def get_document_sections(
        self,
        *,
        ticker: str,
        document_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> DocumentSectionsResult:
        """获取文档章节结构。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            章节结构结果。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
            FileNotFoundError: 文档不存在时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="get_document_sections",
            cancellation_token=cancellation_token,
        )
        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        _raise_if_fins_cancelled(cancellation_token)
        sections_raw: list[SectionSummary] = processor.list_sections()
        _raise_if_fins_cancelled(cancellation_token)
        form_type = self._resolve_document_form_type(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
        )
        enriched_sections = self._enrich_sections_with_semantic(
            sections_raw,
            form_type,
            cancellation_token=cancellation_token,
        )
        citation = self._build_citation(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
        )
        return {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "sections": enriched_sections,
            "citation": citation,
        }

    def read_section(
        self,
        *,
        ticker: str,
        document_id: str,
        ref: str,
        cancellation_token: CancellationToken | None = None,
    ) -> SectionContentResult:
        """读取章节正文。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            ref: 章节引用。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            章节正文结果。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
            KeyError: 章节不存在时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="read_section",
            cancellation_token=cancellation_token,
        )
        normalized_ref = require_non_empty_text(
            ref,
            empty_error=FinsReadArgumentError("read_section", "ref", ref, "Argument must not be empty"),
        )
        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        try:
            _raise_if_fins_cancelled(cancellation_token)
            section_raw: SectionContent = processor.read_section(normalized_ref)
            _raise_if_fins_cancelled(cancellation_token)
        except KeyError as exc:
            suspected_document_id = self._diagnose_cross_document_locator(
                ticker=normalized_ticker,
                current_document_id=normalized_document_id,
                kind="ref",
                locator=normalized_ref,
            )
            if suspected_document_id is not None:
                hint = (
                    f"章节不存在；疑似跨文档复用旧 ref——当前 document_id={normalized_document_id}，"
                    f"该 ref 在 document_id={suspected_document_id} 中存在。"
                    "请先对当前文档调用 get_document_sections 或 search_document 重新 grounding，再用新文档自己的 ref 调用 read_section。"
                )
            else:
                hint = "章节不存在；请先调用 get_document_sections，并原样复制返回的 ref，不要简写、重编号或自造 ref"
            raise FinsReadArgumentError(
                "read_section",
                "ref",
                normalized_ref,
                hint,
            ) from exc
        content = str(section_raw.get("content", ""))
        # tables 字段不输出给 LLM——content 中 [[t_XXXX]] 占位符已携带 ref + 位置上下文，
        # 纯 ref 列表无选择线索（与 children 同理：ref=入参，需有线索才有决策价值），
        # content 截断时 LLM 应走 list_tables(within_section_ref) 获取完整表格元数据。
        normalized_children = _normalize_section_children(section_raw.get("children"))
        content_word_count = int(
            section_raw.get("content_word_count") or section_raw.get("word_count") or len(content.split())
        )
        # 语义增强：解析 item/topic/path
        form_type = self._resolve_document_form_type(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
        )
        title = section_raw.get("title")
        # read_section 没有直接的 parent_ref 上下文，从 list_sections 获取
        parent_ref = section_raw.get("parent_ref")
        parent_title = None
        if parent_ref:
            # 直接走处理器的 O(1) 标题查询，避免为父标题再扫一遍全量 sections。
            try:
                _raise_if_fins_cancelled(cancellation_token)
                parent_title = processor.get_section_title(str(parent_ref))
                _raise_if_fins_cancelled(cancellation_token)
            except FinsReadCancelledError:
                raise
            except Exception:
                parent_title = None

        item_number, canonical_title, topic = resolve_section_semantic(
            title=title,
            form_type=form_type,
            parent_title=parent_title,
        )
        # 子章节无法自解析时，尝试从父章节标题继承 item/topic
        if (item_number is None or topic is None) and parent_title:
            parent_item, _, parent_topic = resolve_section_semantic(
                title=parent_title,
                form_type=form_type,
            )
            if item_number is None:
                item_number = parent_item
            if topic is None:
                topic = parent_topic
        parent_titles: list[str] = []
        if parent_title:
            parent_titles.append(parent_title)
        # path 计算保留供内部诊断与未来评估，但不输出给 LLM——
        # item + topic + title 已充分表达语义位置，path 是冗余拼合，
        # 与 get_document_sections 去 path 的 T1 决策保持一致。
        _path = build_section_path(
            form_type=form_type,
            item_number=item_number,
            canonical_title=canonical_title,
            section_title=title,
            parent_titles=parent_titles,
        )
        del _path  # 显式丢弃，静默 linter unused-variable 警告
        item_label = f"Item {item_number}" if item_number else None
        citation = self._build_citation(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            item=item_label,
            heading=str(title) if title else None,
        )
        return {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "ref": normalized_ref,
            "title": title,
            "item": item_label,
            "topic": topic,
            "content": content,
            "children": normalized_children,
            "page_range": _extract_page_range(section_raw),
            "content_word_count": content_word_count,
            "citation": citation,
        }

    def search_document(
        self,
        *,
        ticker: str,
        document_id: str,
        query: Optional[str] = None,
        queries: Optional[list[str]] = None,
        within_section_ref: Optional[str] = None,
        mode: Optional[str] = None,
        display_budget: Optional[int] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> SearchDocumentResult:
        """在文档内搜索关键词，支持单查询和批量查询。

        ``query`` 与 ``queries`` 互斥，必须提供其一。
        批量查询时逐条执行搜索后聚合去重排序。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            query: 单条搜索关键词（与 queries 互斥）。
            queries: 批量搜索关键词列表（与 query 互斥，上限 20 条）。
            within_section_ref: 可选章节范围。
            mode: 搜索模式，可选值：
                - ``auto``（默认）：先精确匹配，无命中时自动扩展。
                - ``exact``：仅精确匹配。
                - ``keyword``：仅关键词拆分搜索。
                - ``semantic``：语义扩展（短语变体 + 同义词 + 关键词）。
            display_budget: 可选展示预算上限，传递给 exact 优先限流，
                避免裁剪后条目数超出下游 truncation max_items 引发信号冲突。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            搜索结果。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _QUERIES_MAX = 20

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="search_document",
            cancellation_token=cancellation_token,
        )
        # 校验互斥：query 与 queries 必须提供其一
        resolved_queries = _resolve_search_queries(
            query=query,
            queries=queries,
            max_queries=_QUERIES_MAX,
        )
        # 保存查询词副本，供中文无结果 hint 检测使用
        original_queries = resolved_queries
        normalized_within_ref = normalize_optional_text(within_section_ref)
        resolved_mode = _resolve_search_mode(mode)

        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        # 预构建证据化所需的 form_type / ref_to_topic
        form_type = self._resolve_document_form_type(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
        )
        ref_to_topic: dict[str, Optional[str]] = {}
        semantic_profiles: dict[str, SectionSemanticProfile] = {}
        query_term_df: dict[str, int] = {}
        bm25f_index = BM25FSectionIndex(
            profiles={},
            document_frequency={},
            avg_field_lengths={},
            avg_content_length=0.0,
            document_count=0,
        )
        try:
            _raise_if_fins_cancelled(cancellation_token)
            all_secs = processor.list_sections()
            _raise_if_fins_cancelled(cancellation_token)
            enriched_for_search = self._enrich_sections_with_semantic(
                sections=all_secs,
                form_type=form_type,
                cancellation_token=cancellation_token,
            )
            _raise_if_fins_cancelled(cancellation_token)
            bm25f_index = build_section_bm25f_index(enriched_for_search)
            _raise_if_fins_cancelled(cancellation_token)
            semantic_profiles, query_term_df = _build_section_semantic_profiles(enriched_for_search)
            for sec in enriched_for_search:
                _raise_if_fins_cancelled(cancellation_token)
                ref = sec.get("ref")
                if ref:
                    ref_to_topic[ref] = sec.get("topic")
        except FinsReadCancelledError:
            raise
        except Exception:
            pass

        is_multi = len(resolved_queries) > 1

        if is_multi:
            # ---- 批量查询聚合路径 ----
            return self._search_document_multi(
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                resolved_queries=resolved_queries,
                original_queries=original_queries,
                normalized_within_ref=normalized_within_ref,
                resolved_mode=resolved_mode,
                processor=processor,
                form_type=form_type,
                ref_to_topic=ref_to_topic,
                bm25f_index=bm25f_index,
                semantic_profiles=semantic_profiles,
                query_term_df=query_term_df,
                display_budget=display_budget,
                cancellation_token=cancellation_token,
            )

        # ---- 单查询路径 ----
        normalized_query = resolved_queries[0]
        diagnosis = _diagnose_search_query(
            query=normalized_query,
            term_document_frequency=query_term_df,
            document_count=max(1, len(semantic_profiles)),
            mode=resolved_mode,
        )
        ranked_entries, strategy_hit_counts, exact_matches, expansion_queries = _execute_query_search(
            processor=processor,
            query=normalized_query,
            within_ref=normalized_within_ref,
            mode=resolved_mode,
            diagnosis=diagnosis,
            semantic_profiles=semantic_profiles,
            cancellation_token=cancellation_token,
        )

        _raise_if_fins_cancelled(cancellation_token)
        deduplicated_entries = _deduplicate_ranked_search_entries(ranked_entries)
        _raise_if_fins_cancelled(cancellation_token)
        sorted_entries = _sort_ranked_search_entries(
            deduplicated_entries,
            bm25f_index=bm25f_index,
            diagnosis=diagnosis,
            semantic_profiles=semantic_profiles,
        )
        # exact 优先限流：当精确命中存在时，压缩扩展结果占比
        capped_entries = _cap_entries_with_exact_priority(sorted_entries, display_budget=display_budget)
        _raise_if_fins_cancelled(cancellation_token)
        matches = _build_evidence_matches(capped_entries, form_type, ref_to_topic)
        _raise_if_fins_cancelled(cancellation_token)
        fallback_opened = any(bool(item.get("_token_fallback_opened", False)) for item in sorted_entries)
        noise_penalty_applied_count = sum(
            1 for item in sorted_entries if float(item.get("_context_noise_penalty", 0.0)) > 0.0
        )
        diagnostics = {
            "input_query": normalized_query,
            "mode": resolved_mode,
            "used_expansion": not bool(exact_matches) and bool(expansion_queries),
            "expanded_queries": expansion_queries,
            "expansion_query_count": len(expansion_queries),
            "strategy_hit_counts": strategy_hit_counts,
            "ranking_version": _SEARCH_RANKING_VERSION,
            "diagnosis_summary": {
                "intent": diagnosis.intent,
                "token_count": diagnosis.token_count,
                "ambiguity_score": diagnosis.ambiguity_score,
                "is_high_ambiguity": diagnosis.is_high_ambiguity,
            },
            "search_plan": {
                "fallback_gated": diagnosis.is_high_ambiguity and not diagnosis.allow_direct_token_fallback,
                "scoped_before_token": diagnosis.is_high_ambiguity,
            },
            "fallback_gated": diagnosis.is_high_ambiguity and not diagnosis.allow_direct_token_fallback,
            "fallback_opened": fallback_opened,
            "noise_penalty_applied_count": noise_penalty_applied_count,
        }
        Log.debug(
            "search_document 检索完成: "
            f"ticker={normalized_ticker} document_id={normalized_document_id} "
            f"query={normalized_query!r} mode={resolved_mode} "
            f"searched_in={normalized_within_ref or 'full text'} "
            f"exact_hits={len(exact_matches)} expansion_count={len(expansion_queries)} "
            f"total_matches={len(matches)} strategy_hits={strategy_hit_counts}",
            module=self.MODULE,
        )

        match_quality = _build_match_quality(matches)
        hint = _build_search_hint(matches, match_quality["primary_source"])
        # 中文查询无结果时补充操作引导提示
        if not hint and not matches and _any_query_has_chinese(original_queries):
            hint = _CHINESE_QUERY_NO_RESULTS_HINT
        next_section_to_read, next_section_by_query = build_search_next_section_fields(matches=matches)

        result: SearchDocumentResult = {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "query": normalized_query,
            "mode": resolved_mode,
            "searched_in": normalized_within_ref or "full text",
            "match_quality": match_quality,
            "matches": matches,
            "next_section_to_read": next_section_to_read,
            "total_matches": len(matches),
            "diagnostics": diagnostics,
            "citation": self._build_citation(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
            ),
        }
        if hint:
            result["hint"] = hint
        return result

    def _search_document_multi(
        self,
        *,
        normalized_ticker: str,
        normalized_document_id: str,
        resolved_queries: list[str],
        original_queries: list[str],
        normalized_within_ref: Optional[str],
        resolved_mode: str,
        processor: "DocumentProcessor",
        form_type: Optional[str],
        ref_to_topic: dict[str, Optional[str]],
        bm25f_index: BM25FSectionIndex,
        semantic_profiles: dict[str, SectionSemanticProfile],
        query_term_df: dict[str, int],
        display_budget: Optional[int] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> SearchDocumentResult:
        """批量查询聚合路径。

        逐条执行搜索后汇总 ranked_entries，统一去重排序构建结果。

        Args:
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化 document_id。
            resolved_queries: 已翻译并校验的查询列表。
            original_queries: 翻译前的原始查询列表，用于中文无结果 hint 检测。
            normalized_within_ref: 可选章节范围。
            resolved_mode: 搜索模式。
            processor: 文档处理器。
            form_type: 文档 form_type。
            ref_to_topic: ref → topic 映射。
            bm25f_index: BM25F 索引。
            semantic_profiles: 章节语义画像映射。
            query_term_df: 查询词 document frequency。
            display_budget: 可选展示预算上限，传递给 exact 优先限流。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            聚合搜索结果。
        """

        all_ranked: list[dict[str, Any]] = []
        per_query_stats: list[dict[str, Any]] = []
        merged_strategy_hits = _build_empty_search_strategy_hit_counts()

        for q in resolved_queries:
            _raise_if_fins_cancelled(cancellation_token)
            query_diagnosis = _diagnose_search_query(
                query=q,
                term_document_frequency=query_term_df,
                document_count=max(1, len(semantic_profiles)),
                mode=resolved_mode,
            )
            ranked, strategy_hits, exact_matches, expansion_queries = _execute_query_search(
                processor=processor,
                query=q,
                within_ref=normalized_within_ref,
                mode=resolved_mode,
                diagnosis=query_diagnosis,
                semantic_profiles=semantic_profiles,
                cancellation_token=cancellation_token,
            )
            _raise_if_fins_cancelled(cancellation_token)
            all_ranked.extend(ranked)
            # 合并策略命中计数
            for strat, cnt in strategy_hits.items():
                _raise_if_fins_cancelled(cancellation_token)
                merged_strategy_hits[strat] = merged_strategy_hits.get(strat, 0) + cnt
            per_query_stats.append(
                {
                    "query": q,
                    "hits": len(ranked),
                    "exact_hits": len(exact_matches),
                    "expansion_count": len(expansion_queries),
                    "is_high_ambiguity": query_diagnosis.is_high_ambiguity,
                    "intent": query_diagnosis.intent,
                }
            )

        _raise_if_fins_cancelled(cancellation_token)
        deduplicated = _deduplicate_ranked_search_entries(all_ranked)
        _raise_if_fins_cancelled(cancellation_token)
        sorted_entries = _sort_ranked_search_entries(
            deduplicated,
            bm25f_index=bm25f_index,
            diagnosis=None,
            semantic_profiles=semantic_profiles,
        )
        # exact 优先限流：当精确命中存在时，压缩扩展结果占比
        capped_entries = _cap_entries_with_exact_priority(sorted_entries, display_budget=display_budget)
        _raise_if_fins_cancelled(cancellation_token)
        matches = _build_evidence_matches(capped_entries, form_type, ref_to_topic)

        diagnostics = {
            "input_queries": resolved_queries,
            "mode": resolved_mode,
            "query_count": len(resolved_queries),
            "per_query_stats": per_query_stats,
            "strategy_hit_counts": merged_strategy_hits,
            "ranking_version": _SEARCH_RANKING_VERSION,
            "fallback_gated": any(bool(item.get("is_high_ambiguity")) for item in per_query_stats),
            "noise_penalty_applied_count": sum(
                1 for item in sorted_entries if float(item.get("_context_noise_penalty", 0.0)) > 0.0
            ),
        }
        Log.debug(
            "search_document(multi) 检索完成: "
            f"ticker={normalized_ticker} document_id={normalized_document_id} "
            f"queries={resolved_queries!r} mode={resolved_mode} "
            f"searched_in={normalized_within_ref or 'full text'} "
            f"total_matches={len(matches)} per_query_stats={per_query_stats}",
            module=self.MODULE,
        )

        match_quality = _build_match_quality(matches)
        hint = _build_search_hint(matches, match_quality["primary_source"])
        # 中文查询无结果时补充操作引导提示
        if not hint and not matches and _any_query_has_chinese(original_queries):
            hint = _CHINESE_QUERY_NO_RESULTS_HINT
        _next_section_to_read, next_section_by_query = build_search_next_section_fields(
            matches=matches,
            queries=resolved_queries,
        )
        del _next_section_to_read
        # 批量查询路径下 queries 非空，next_section_by_query 必有值
        assert next_section_by_query is not None

        result: SearchDocumentResult = {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "query": None,
            "queries": resolved_queries,
            "mode": resolved_mode,
            "searched_in": normalized_within_ref or "full text",
            "match_quality": match_quality,
            "matches": matches,
            "next_section_by_query": next_section_by_query,
            "total_matches": len(matches),
            "diagnostics": diagnostics,
            "citation": self._build_citation(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
            ),
        }
        if hint:
            result["hint"] = hint
        return result

    def list_tables(
        self,
        *,
        ticker: str,
        document_id: str,
        financial_only: bool = False,
        within_section_ref: Optional[str] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> TablesListResult:
        """列出文档表格元数据。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            financial_only: 是否仅返回财务表格。
            within_section_ref: 可选章节范围。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            表格列表结果。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="list_tables",
            cancellation_token=cancellation_token,
        )
        normalized_within_ref = normalize_optional_text(within_section_ref)

        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        _raise_if_fins_cancelled(cancellation_token)
        tables_raw: list[TableSummary] = processor.list_tables()

        filtered_tables: list[dict[str, Any]] = []
        for item in tables_raw:
            _raise_if_fins_cancelled(cancellation_token)
            is_financial = bool(item.get("is_financial", False))
            section_ref = item.get("section_ref")
            if financial_only and not is_financial:
                continue
            if normalized_within_ref is not None and section_ref != normalized_within_ref:
                continue
            page_no = item.get("page_no")
            # 构建表格条目：headers 截断至 80 chars/条，省略 null 可选字段减少序列化开销
            # context_before 已移除——753cd7a 后 caption 推断覆盖了其信息，
            # caption + headers + table_type 足够 LLM 判断表格相关性。
            raw_headers = item.get("headers")
            entry: dict[str, Any] = {
                "table_ref": item.get("table_ref"),
                "row_count": int(item.get("row_count", 0) or 0),
                "col_count": int(item.get("col_count", 0) or 0),
                "is_financial": is_financial,
                "table_type": _normalize_table_type(item.get("table_type")),
                "headers": ([str(h)[:80] for h in raw_headers if h] if isinstance(raw_headers, list) else None),
            }
            # within_section：与请求参数 within_section_ref 语义同源，表达 table 所属 section
            if section_ref:
                ws: dict[str, str] = {"ref": section_ref}
                _raise_if_fins_cancelled(cancellation_token)
                sec_title = processor.get_section_title(section_ref)
                _raise_if_fins_cancelled(cancellation_token)
                if sec_title:
                    ws["title"] = sec_title
                entry["within_section"] = ws
            caption = item.get("caption")
            if caption:
                entry["caption"] = caption
            if isinstance(page_no, int) and page_no > 0:
                entry["page_no"] = page_no
            filtered_tables.append(entry)

        # 复杂逻辑说明：先按财务优先排序，再按 table_ref 稳定排序，确保返回结果可复现。
        filtered_tables.sort(
            key=lambda item: (
                0 if bool(item.get("is_financial", False)) else 1,
                str(item.get("table_ref", "")),
            )
        )
        financial_count = sum(1 for item in filtered_tables if bool(item.get("is_financial", False)))
        return {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "tables": filtered_tables,
            "total": len(filtered_tables),
            "financial_count": financial_count,
            "citation": self._build_citation(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
            ),
        }

    def get_table(
        self,
        *,
        ticker: str,
        document_id: str,
        table_ref: str,
        cancellation_token: CancellationToken | None = None,
    ) -> TableDetailResult:
        """读取指定表格。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            table_ref: 表格引用。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            表格数据结果。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
            KeyError: 表格不存在时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="get_table",
            cancellation_token=cancellation_token,
        )
        normalized_table_ref = require_non_empty_text(
            table_ref,
            empty_error=FinsReadArgumentError("get_table", "table_ref", table_ref, "Argument must not be empty"),
        )
        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        try:
            _raise_if_fins_cancelled(cancellation_token)
            table_raw: TableContent = processor.read_table(normalized_table_ref)
            _raise_if_fins_cancelled(cancellation_token)
        except KeyError as exc:
            suspected_document_id = self._diagnose_cross_document_locator(
                ticker=normalized_ticker,
                current_document_id=normalized_document_id,
                kind="table_ref",
                locator=normalized_table_ref,
            )
            if suspected_document_id is not None:
                hint = (
                    f"表格不存在；疑似跨文档复用旧 table_ref——当前 document_id={normalized_document_id}，"
                    f"该 table_ref 在 document_id={suspected_document_id} 中存在。"
                    "请先对当前文档调用 list_tables / get_document_sections / search_document 重新 grounding，再用新文档自己的 table_ref 调用 get_table。"
                )
            else:
                hint = "表格不存在；请先调用 list_tables，并原样复制返回的 table_ref，不要简写、重编号或自造 table_ref"
            raise FinsReadArgumentError(
                "get_table",
                "table_ref",
                normalized_table_ref,
                hint,
            ) from exc
        data_payload = _build_table_data_payload(table_raw)
        _raise_if_fins_cancelled(cancellation_token)

        # within_section：通过 get_section_title O(1) 获取所属章节信息
        section_ref = table_raw.get("section_ref")
        within_section: dict[str, str] | None = None
        if section_ref:
            within_section = {"ref": section_ref}
            _raise_if_fins_cancelled(cancellation_token)
            sec_title = processor.get_section_title(section_ref)
            _raise_if_fins_cancelled(cancellation_token)
            if sec_title:
                within_section["title"] = sec_title

        page_no = table_raw.get("page_no")
        caption = table_raw.get("caption")
        result: TableDetailResult = {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "table_ref": normalized_table_ref,
            "data": data_payload,
            "row_count": int(table_raw.get("row_count", 0) or 0),
            "col_count": int(table_raw.get("col_count", 0) or 0),
            "is_financial": bool(table_raw.get("is_financial", False)),
            "table_type": _normalize_table_type(table_raw.get("table_type")),
            "citation": self._build_citation(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
            ),
        }
        # 条件字段：省略 null 值减少序列化噪声
        if within_section:
            result["within_section"] = within_section
        if caption:
            result["caption"] = caption
        if isinstance(page_no, int) and page_no > 0:
            result["page_no"] = page_no
        return result

    def get_page_content(
        self,
        *,
        ticker: str,
        document_id: str,
        page_no: int,
        cancellation_token: CancellationToken | None = None,
    ) -> PageContentResult | NotSupportedResult:
        """读取页面上下文。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            page_no: 目标页码（1-based）。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            页面内容结果；不支持时返回 `not_supported` 结构。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="get_page_content",
            cancellation_token=cancellation_token,
        )
        if not isinstance(page_no, int) or page_no <= 0:
            raise FinsReadArgumentError(
                "get_page_content",
                "page_no",
                page_no,
                "page_no must be a positive integer",
            )

        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        if not isinstance(processor, _PageContentReadProcessor):
            return _build_not_supported_result(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
                feature="get_page_content",
                payload={"page_no": page_no, "supported": False},
            )

        _raise_if_fins_cancelled(cancellation_token)
        page_payload = processor.get_page_content(page_no)
        _raise_if_fins_cancelled(cancellation_token)
        # processor 贡献的子字段通过 .get() 提取；已知字段由 PageContentResult 声明。
        result: PageContentResult = {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "page_no": page_no,
            "sections": list(page_payload.get("sections") or []),
            "tables": list(page_payload.get("tables") or []),
            "text_preview": str(page_payload.get("text_preview", "")),
            "has_content": bool(page_payload.get("has_content", False)),
            "total_items": int(page_payload.get("total_items", 0) or 0),
            "supported": bool(page_payload.get("supported", True)),
            "citation": self._build_citation(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
            ),
        }
        return result

    def get_financial_statement(
        self,
        *,
        ticker: str,
        document_id: str,
        statement_type: str,
        cancellation_token: CancellationToken | None = None,
    ) -> FinancialStatementResult | NotSupportedResult:
        """读取标准财务报表。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            statement_type: 报表类型。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            财务报表结果；成功时除标准报表数据外，还包含 `statement_locator`
            结构化定位信息，供写作链路生成可复核的“证据与出处”锚点；
            不支持时返回 `not_supported` 结构。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="get_financial_statement",
            cancellation_token=cancellation_token,
        )
        normalized_statement_type = require_non_empty_text(
            statement_type,
            empty_error=FinsReadArgumentError(
                "get_financial_statement",
                "statement_type",
                statement_type,
                "Argument must not be empty",
            ),
        )

        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        if not isinstance(processor, _FinancialStatementReadProcessor):
            return _build_not_supported_result(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
                feature="get_financial_statement",
                payload={"statement_type": normalized_statement_type},
            )

        _raise_if_fins_cancelled(cancellation_token)
        statement_payload = processor.get_financial_statement(normalized_statement_type)
        _raise_if_fins_cancelled(cancellation_token)
        citation = self._build_citation(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
        )
        rows = statement_payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("processor get_financial_statement result rows must be list")
        for _row in rows:
            _raise_if_fins_cancelled(cancellation_token)
        raw_statement_locator = statement_payload.get("statement_locator")
        if raw_statement_locator is None:
            statement_locator: StatementLocator = {
                "statement_type": normalized_statement_type,
                "period_labels": [],
                "row_labels": [],
            }
        else:
            statement_locator = raw_statement_locator
        result: FinancialStatementResult = {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "citation": citation,
            "statement_type": statement_payload.get("statement_type") or normalized_statement_type,
            "currency": statement_payload.get("currency"),
            "units": statement_payload.get("units"),
            "rows": rows,
            "statement_locator": statement_locator,
        }
        period_labels = statement_payload.get("period_labels")
        if period_labels is not None:
            result["period_labels"] = period_labels
        column_headers = statement_payload.get("column_headers")
        if column_headers is not None:
            result["column_headers"] = column_headers
        header = statement_payload.get("header")
        if header is not None:
            result["header"] = header
        supported = statement_payload.get("supported")
        if supported is not None:
            result["supported"] = supported
        return result

    def query_xbrl_facts(
        self,
        *,
        ticker: str,
        document_id: str,
        concepts: Optional[list[str]] = None,
        statement_type: Optional[str] = None,
        period_end: Optional[str] = None,
        fiscal_year: Optional[int] = None,
        fiscal_period: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        cancellation_token: CancellationToken | None = None,
    ) -> XbrlQueryResult | NotSupportedResult:
        """查询 XBRL facts。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            concepts: 可选 XBRL 概念列表。为空时按文档 form/taxonomy 选择默认概念包。
            statement_type: 可选报表类型。
            period_end: 可选期末日期。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值。
            max_value: 可选最大值。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            XBRL 数值 facts 查询结果；不支持时返回 `not_supported` 结构。

        Raises:
            FinsReadArgumentError: 参数非法时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="query_xbrl_facts",
            cancellation_token=cancellation_token,
        )
        if concepts is not None and not isinstance(concepts, list):
            raise FinsReadArgumentError(
                "query_xbrl_facts",
                "concepts",
                concepts,
                "concepts must be a string array or omitted",
            )
        normalized_concepts: list[str] = []
        for concept in concepts or []:
            _raise_if_fins_cancelled(cancellation_token)
            item = normalize_optional_text(concept)
            if item is not None:
                normalized_concepts.append(item)

        _raise_if_fins_cancelled(cancellation_token)
        form_type = self._resolve_document_form_type(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
        )
        _raise_if_fins_cancelled(cancellation_token)
        processor = self._get_or_create_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        )
        taxonomy = _resolve_processor_taxonomy(processor)
        resolved_concepts = (
            normalized_concepts
            if normalized_concepts
            else _resolve_default_xbrl_concepts(form_type=form_type, taxonomy=taxonomy)
        )
        if not isinstance(processor, _XbrlFactsReadProcessor):
            return _build_not_supported_result(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
                feature="query_xbrl_facts",
                payload={"concepts": resolved_concepts},
            )

        _raise_if_fins_cancelled(cancellation_token)
        payload = processor.query_xbrl_facts(
            concepts=resolved_concepts,
            statement_type=normalize_optional_text(statement_type),
            period_end=normalize_optional_text(period_end),
            fiscal_year=fiscal_year,
            fiscal_period=normalize_optional_text(fiscal_period),
            min_value=min_value,
            max_value=max_value,
        )
        _raise_if_fins_cancelled(cancellation_token)
        raw_facts_for_checkpoint = payload.get("facts")
        if isinstance(raw_facts_for_checkpoint, list):
            for _raw_fact in raw_facts_for_checkpoint:
                _raise_if_fins_cancelled(cancellation_token)
        normalized_payload = _normalize_xbrl_query_payload(
            payload=payload,
            default_concepts=resolved_concepts,
        )
        facts = normalized_payload.get("facts")
        if isinstance(facts, list):
            for _fact in facts:
                _raise_if_fins_cancelled(cancellation_token)
        query_params: XbrlQueryParams = {
            "concepts": resolved_concepts,
        }
        normalized_query_params = normalized_payload.get("query_params")
        if isinstance(normalized_query_params, Mapping):
            statement_type_value = normalized_query_params.get("statement_type")
            period_end_value = normalized_query_params.get("period_end")
            fiscal_year_value = normalized_query_params.get("fiscal_year")
            fiscal_period_value = normalized_query_params.get("fiscal_period")
            min_value_value = normalized_query_params.get("min_value")
            max_value_value = normalized_query_params.get("max_value")
            query_params["statement_type"] = statement_type_value if isinstance(statement_type_value, str) else None
            query_params["period_end"] = period_end_value if isinstance(period_end_value, str) else None
            query_params["fiscal_year"] = (
                fiscal_year_value
                if isinstance(fiscal_year_value, int) and not isinstance(fiscal_year_value, bool)
                else None
            )
            query_params["fiscal_period"] = fiscal_period_value if isinstance(fiscal_period_value, str) else None
            query_params["min_value"] = (
                float(min_value_value)
                if isinstance(min_value_value, int | float) and not isinstance(min_value_value, bool)
                else None
            )
            query_params["max_value"] = (
                float(max_value_value)
                if isinstance(max_value_value, int | float) and not isinstance(max_value_value, bool)
                else None
            )
        normalized_facts = normalized_payload.get("facts")
        if not isinstance(normalized_facts, list):
            raise ValueError("normalized XBRL payload missing facts")
        normalized_total = normalized_payload.get("total")
        if not isinstance(normalized_total, int) or isinstance(normalized_total, bool):
            raise ValueError("normalized XBRL payload missing total")
        result: XbrlQueryResult = {
            "ticker": normalized_ticker,
            "document_id": normalized_document_id,
            "query_params": query_params,
            "facts": normalized_facts,
            "total": normalized_total,
            "citation": self._build_citation(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
            ),
        }
        deduped_fact_count = normalized_payload.get("deduped_fact_count")
        if isinstance(deduped_fact_count, int) and not isinstance(deduped_fact_count, bool):
            result["deduped_fact_count"] = deduped_fact_count
        supported = normalized_payload.get("supported")
        if isinstance(supported, bool):
            result["supported"] = supported
        return result

    def _normalize_document_identity(
        self,
        *,
        ticker: str,
        document_id: str,
        tool_name: str,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[str, str]:
        """标准化文档身份参数。

        Args:
            ticker: 原始股票代码。
            document_id: 原始文档 ID。
            tool_name: 调用工具名。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            `(normalized_ticker, normalized_document_id)`。其中 ``normalized_document_id``
            始终是仓储可识别的规范 `document_id`。

        Raises:
            FinsReadArgumentError: 参数为空时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker = self._resolve_canonical_ticker(
            ticker=ticker,
            tool_name=tool_name,
            cancellation_token=cancellation_token,
        )
        normalized_document_id = require_non_empty_text(
            document_id,
            empty_error=FinsReadArgumentError(
                tool_name,
                "document_id",
                document_id,
                "Argument must not be empty",
            ),
        )
        _raise_if_fins_cancelled(cancellation_token)
        resolved_document_id = self._resolve_canonical_document_id(
            ticker=normalized_ticker,
            raw_document_id=normalized_document_id,
            tool_name=tool_name,
            cancellation_token=cancellation_token,
        )
        return normalized_ticker, resolved_document_id

    def _resolve_canonical_ticker(
        self,
        *,
        ticker: str,
        tool_name: str,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """将外部 ticker 归一化为可用 ticker。

        解析顺序：
        1. ``require_non_empty_text`` 拒绝空输入。
        2. 走 ``try_normalize_ticker`` 真源把 ``0700.HK`` / ``600519.SH`` 等
           常见变形归一化为 canonical；作为唯一查询候选。
        3. 若真源识别失败（例如用户传了 ``"Apple Inc."`` 这种公司名），回退到
           ``strip().upper()`` 作为候选；保留"公司名可当 ticker 传"的既有行为。
        4. 仓储 ``resolve_existing_ticker`` 在 canonical 未命中时会走公司级
           ``ticker_aliases`` 索引反查；alias 已全部归一化，无需再构造变体。

        Args:
            ticker: 原始 ticker。
            tool_name: 当前调用工具名。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            当前财报工具可用的 ticker。

        Raises:
            FinsReadArgumentError: ticker 为空时抛出。
            FinsReadBusinessError: ticker 未收录于当前工作区时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker = require_non_empty_text(
            ticker,
            empty_error=FinsReadArgumentError(
                tool_name,
                "ticker",
                ticker,
                "Argument must not be empty",
            ),
        )
        normalized_source = try_normalize_ticker(normalized_ticker)
        if normalized_source is not None:
            probe_ticker = normalized_source.canonical
        else:
            probe_ticker = normalized_ticker.strip().upper()
        _raise_if_fins_cancelled(cancellation_token)
        resolved_ticker = self._company_repository.resolve_existing_ticker([probe_ticker])
        _raise_if_fins_cancelled(cancellation_token)
        if resolved_ticker is None:
            raise FinsReadBusinessError(
                code=ErrorCode.NOT_FOUND.value,
                message=f"Financial Document Tools do not have this company: ticker='{normalized_ticker}'.",
                hint=_MISSING_TICKER_HINT,
            )
        if resolved_ticker != normalized_ticker:
            Log.debug(
                f"ticker 已归一化: tool={tool_name} raw={normalized_ticker!r} "
                f"probe={probe_ticker!r} canonical={resolved_ticker!r}",
                module=self.MODULE,
            )
        return resolved_ticker

    def _resolve_canonical_document_id(
        self,
        *,
        ticker: str,
        raw_document_id: str,
        tool_name: str,
        cancellation_token: CancellationToken | None = None,
    ) -> str:
        """将外部传入的文档标识归一化为仓储 `document_id`。

        这里仅依赖仓储公开元数据做最小归一化，不依赖 processor 内部实现。
        支持以下几类输入：
        - 已经是仓储 `document_id`
        - `meta.json` 中的 `internal_document_id`
        - `meta.json` 中的 `accession_number`
        - 去掉连字符后的 accession

        Args:
            ticker: 标准化股票代码。
            raw_document_id: 外部传入的文档标识。
            tool_name: 当前工具名，仅用于日志。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            仓储规范 `document_id`。

        Raises:
            无。
        """

        _raise_if_fins_cancelled(cancellation_token)
        direct_meta = self._get_document_meta_cached(ticker, raw_document_id)
        if direct_meta is not None:
            return raw_document_id

        normalized_alias = re.sub(r"\s+", "", raw_document_id).strip()
        for source_kind in (SourceKind.FILING, SourceKind.MATERIAL):
            _raise_if_fins_cancelled(cancellation_token)
            for candidate_document_id in self._source_repository.list_source_document_ids(ticker, source_kind):
                _raise_if_fins_cancelled(cancellation_token)
                candidate_meta = self._get_document_meta_cached(ticker, candidate_document_id)
                if not candidate_meta:
                    continue
                alias_fields = self._build_document_identity_aliases(
                    candidate_document_id=candidate_document_id,
                    meta=candidate_meta,
                )
                if normalized_alias not in alias_fields:
                    continue
                matched_field = alias_fields[normalized_alias]
                if matched_field != "document_id":
                    Log.debug(
                        f"文档标识已归一化: tool={tool_name} ticker={ticker} raw={raw_document_id!r} "
                        f"matched_field={matched_field} canonical={candidate_document_id!r}",
                        module=self.MODULE,
                    )
                return candidate_document_id

        Log.debug(
            f"文档标识未命中归一化映射: tool={tool_name} ticker={ticker} raw={raw_document_id!r}",
            module=self.MODULE,
        )
        return raw_document_id

    def _build_document_identity_aliases(
        self,
        *,
        candidate_document_id: str,
        meta: _SourceDocumentMeta,
    ) -> dict[str, str]:
        """构建单个文档可接受的身份别名集合。

        Args:
            candidate_document_id: 仓储规范 `document_id`。
            meta: 对应 `meta.json` 内容。

        Returns:
            `alias -> matched_field` 映射。

        Raises:
            无。
        """

        aliases: dict[str, str] = {
            re.sub(r"\s+", "", candidate_document_id).strip(): "document_id",
        }
        for field_name in ("internal_document_id", "accession_number"):
            normalized_value = meta.get(field_name)
            if not normalized_value:
                continue
            aliases[re.sub(r"\s+", "", normalized_value).strip()] = field_name
            aliases[normalized_value.replace("-", "")] = field_name
        return aliases

    def _collect_source_documents(
        self,
        ticker: str,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[_SourceDocumentSummary]:
        """汇总 source 层文档摘要。

        Args:
            ticker: 标准化股票代码。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            文档摘要列表。

        Raises:
            RuntimeError: 仓储读取失败时抛出。
        """

        documents: list[_SourceDocumentSummary] = []
        _raise_if_fins_cancelled(cancellation_token)
        documents.extend(
            self._collect_source_documents_by_kind(
                ticker,
                SourceKind.FILING,
                cancellation_token=cancellation_token,
            )
        )
        _raise_if_fins_cancelled(cancellation_token)
        documents.extend(
            self._collect_source_documents_by_kind(
                ticker,
                SourceKind.MATERIAL,
                cancellation_token=cancellation_token,
            )
        )
        _raise_if_fins_cancelled(cancellation_token)
        documents.sort(key=_source_document_recency_sort_key, reverse=True)
        return documents

    def _collect_source_documents_by_kind(
        self,
        ticker: str,
        source_kind: SourceKind,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[_SourceDocumentSummary]:
        """按来源类型采集文档摘要。

        Args:
            ticker: 标准化股票代码。
            source_kind: 文档来源。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            文档摘要列表。

        Raises:
            RuntimeError: 仓储读取失败时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        document_ids = self._source_repository.list_source_document_ids(ticker, source_kind)
        _raise_if_fins_cancelled(cancellation_token)
        results: list[_SourceDocumentSummary] = []
        for document_id in document_ids:
            _raise_if_fins_cancelled(cancellation_token)
            try:
                meta = self._get_source_meta_cached_by_kind(ticker, document_id, source_kind)
            except FileNotFoundError:
                continue
            if meta.get("is_deleted", False):
                continue
            if not meta.get("ingest_complete", True):
                continue
            meta_payload = _source_document_meta_to_storage_payload(meta)
            inferred_period = _infer_fiscal_period(meta_payload)
            inferred_year = _infer_fiscal_year(meta_payload, inferred_period)
            resolved_fiscal_year = _resolve_fiscal_year_with_fallback(
                raw_value=meta["fiscal_year"],
                inferred_year=inferred_year,
            )
            resolved_fiscal_period = _resolve_fiscal_period_with_fallback(
                raw_value=meta["fiscal_period"],
                inferred_period=inferred_period,
            )
            # 从 processed meta 读取能力标志（轻量 JSON），处理缺失的情况
            has_financial_data = self._read_capability_flags(
                ticker,
                document_id,
            )
            _raise_if_fins_cancelled(cancellation_token)
            results.append(
                {
                    "document_id": document_id,
                    "source_kind": source_kind.value,
                    "form_type": _normalize_form_type_for_matching(meta["form_type"]),
                    "material_name": meta["material_name"],
                    "fiscal_year": resolved_fiscal_year,
                    "fiscal_period": resolved_fiscal_period,
                    "report_date": meta["report_date"],
                    "filing_date": meta["filing_date"],
                    "amended": meta["amended"],
                    "has_financial_data": has_financial_data,
                }
            )
        return results

    def _build_citation(
        self,
        *,
        ticker: str,
        document_id: str,
        item: Optional[str] = None,
        heading: Optional[str] = None,
    ) -> dict[str, Any]:
        """构建统一 citation 对象。

        从 meta.json 读取文档元数据，构建可序列化的 citation 字典。
        同一 (ticker, document_id) 的 meta 读取会被 _get_document_meta_cached 缓存。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。
            item: 可选 Item 编号（如 "Item 1A"）。
            heading: 可选章节标题。

        Returns:
            citation 字典（值为 None 的键已移除）。
        """
        source_kind = self._resolve_source_kind(ticker=ticker, document_id=document_id)
        meta = self._get_source_meta_cached_by_kind(ticker, document_id, source_kind)
        provenance = self._source_repository.get_source_document_provenance(
            ticker,
            document_id,
            source_kind,
            meta=_source_document_meta_to_storage_payload(meta),
        )
        if not provenance.ingest_complete:
            raise FileNotFoundError(f"source document 尚未完成入库: ticker={ticker}, document_id={document_id}")
        if source_kind is SourceKind.MATERIAL:
            source_type = SourceType.SUPPLEMENTARY.value
        else:
            source_type = _FILING_SOURCE_TYPES_BY_PROVIDER[provenance.source_provider].value
        source_provider = _CITATION_PROVIDER_LABELS[provenance.source_provider]

        form_type = _normalize_form_type_for_matching(meta["form_type"])
        # 美股 filing 的 accession_number 存储在 meta.json 中
        accession_no = meta["accession_number"]

        citation = Citation(
            source_type=source_type,
            document_id=document_id,
            ticker=ticker,
            form_type=form_type,
            filing_date=meta["filing_date"],
            accession_no=accession_no,
            source_provider=source_provider,
            fiscal_year=meta["fiscal_year"],
            fiscal_period=meta["fiscal_period"],
            item=item,
            heading=heading,
        )
        return citation.to_dict()

    def _get_source_meta_cached_by_kind(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> _SourceDocumentMeta:
        """按已知 source kind 读取并缓存 source meta。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。
            source_kind: 已解析的 source kind 路由键。

        Returns:
            source meta 字典。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
        """

        cache_key = ProcessorCacheKey(ticker=ticker, document_id=document_id, source_kind=source_kind.value)
        cached = self._meta_cache.get(cache_key)
        if cached is not None and cached.meta is not None:
            return cached.meta
        raw_meta = self._source_repository.get_source_meta(ticker, document_id, source_kind)
        meta = _parse_source_document_meta(raw_meta)
        self._meta_cache.put(cache_key, _CachedSourceDocumentMeta(meta=meta))
        return meta

    def _get_document_meta_cached(self, ticker: str, document_id: str) -> _SourceDocumentMeta | None:
        """读取文档元数据（带实例级缓存）。

        同一 FinsReadRuntime 实例内，对相同 (ticker, document_id) 的
        meta.json 读取做内存缓存，避免同一次工具调用链中重复 IO。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。

        Returns:
            meta 字典；文档不存在时返回 None。
        """
        cache_key = ProcessorCacheKey(ticker=ticker, document_id=document_id)
        cached = self._meta_cache.get(cache_key)
        if cached is not None:
            return cached.meta
        try:
            source_kind = self._resolve_source_kind(ticker=ticker, document_id=document_id)
            raw_meta = self._source_repository.get_source_meta(ticker, document_id, source_kind)
            meta = _parse_source_document_meta(raw_meta)
        except FileNotFoundError:
            meta = None
        self._meta_cache.put(cache_key, _CachedSourceDocumentMeta(meta=meta))
        return meta

    def _enrich_sections_with_semantic(
        self,
        sections: list[SectionSummary],
        form_type: Optional[str],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict[str, Any]]:
        """为章节列表注入语义层字段。

        遍历 sections，为每个章节解析 item/topic/path，
        并构建 ref → section 索引以便通过 parent_ref 追溯路径。

        Args:
            sections: processor 返回的章节摘要列表。
            form_type: 文档的 form_type。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            增强后的章节字典列表。
        """
        # 构建 ref → section 索引，用于 parent_ref 追溯
        ref_to_section: dict[str, SectionSummary] = {}
        for sec in sections:
            _raise_if_fins_cancelled(cancellation_token)
            ref = sec.get("ref")
            if ref:
                ref_to_section[ref] = sec

        enriched: list[dict[str, Any]] = []
        # 记录已解析的 ref → (item_number, topic)，供子章节继承使用
        ref_to_resolved: dict[str, tuple[Optional[str], Optional[str]]] = {}
        for sec in sections:
            _raise_if_fins_cancelled(cancellation_token)
            entry = dict(sec)
            # 移除 preview 字段：与 title 高度重复，LLM 需要详情时用 read_section
            entry.pop("preview", None)
            title = sec.get("title")
            parent_ref = sec.get("parent_ref")

            # 获取父章节标题（用于 10-Q Part 消歧）
            parent_title = None
            if parent_ref and parent_ref in ref_to_section:
                parent_title = ref_to_section[parent_ref].get("title")

            item_number, canonical_title, topic = resolve_section_semantic(
                title=title,
                form_type=form_type,
                parent_title=parent_title,
            )

            # 子章节无法自解析时，从父章节继承 item/topic（支持多级辭传）
            if (item_number is None or topic is None) and parent_ref and parent_ref in ref_to_resolved:
                parent_item_number, parent_topic = ref_to_resolved[parent_ref]
                if item_number is None:
                    item_number = parent_item_number
                if topic is None:
                    topic = parent_topic

            # 记录当前解析结果，供下级子章节查表
            ref = sec.get("ref")
            if ref:
                ref_to_resolved[ref] = (item_number, topic)

            # 构建层级路径：上溯 parent_ref 链收集父标题
            parent_titles = _collect_parent_titles(sec, ref_to_section)
            path = build_section_path(
                form_type=form_type,
                item_number=item_number,
                canonical_title=canonical_title,
                section_title=title,
                parent_titles=parent_titles,
            )

            entry["item"] = f"Item {item_number}" if item_number else None
            entry["topic"] = topic
            # 只为顶层章节保留路径（子章节层级关系已由 parent_ref 表达）
            if sec.get("level", 0) <= 1:
                entry["path"] = path if path else None
            enriched.append(entry)
        return enriched

    def _resolve_document_form_type(self, *, ticker: str, document_id: str) -> Optional[str]:
        """读取文档 form_type。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。

        Returns:
            标准化后的 form_type；读取失败时返回 `None`。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        meta = self._get_document_meta_cached(ticker, document_id)
        if meta is None:
            return None
        return _normalize_form_type_for_matching(meta.get("form_type"))

    def _read_company_info(self, ticker: str) -> tuple[str, str]:
        """读取公司信息。

        Args:
            ticker: 标准化股票代码。

        Returns:
            `(company_name, market)`。

        Raises:
            RuntimeError: 仓储读取失败时抛出。
        """

        try:
            company_meta = self._company_repository.get_company_meta(ticker)
        except FileNotFoundError:
            return ticker, "unknown"
        return company_meta.company_name, company_meta.market

    def _read_capability_flags(
        self,
        ticker: str,
        document_id: str,
    ) -> Optional[bool]:
        """从 processed meta 读取文档财务数据能力标志。

        Args:
            ticker: 标准化股票代码。
            document_id: 文档 ID。

        Returns:
            `has_financial_data`：`True`（可调用 get_financial_statement）/
            `False`（无数据）/ `None`（未处理或无法判定）。

        Raises:
            无（内部异常已捕获）。
        """

        try:
            processed_meta = self._processed_repository.get_processed_meta(ticker, document_id)
        except (FileNotFoundError, ValueError):
            return None
        return resolve_has_financial_data(
            has_financial_data=processed_meta.get("has_financial_data"),
            availability=processed_meta.get("financial_statement_availability"),
            has_financial_statement=processed_meta.get("has_financial_statement"),
            has_xbrl=processed_meta.get("has_xbrl"),
            has_structured_financial_statements=processed_meta.get("has_structured_financial_statements"),
            has_financial_statement_sections=processed_meta.get("has_financial_statement_sections"),
        )

    def _diagnose_cross_document_locator(
        self,
        *,
        ticker: str,
        current_document_id: str,
        kind: Literal["ref", "table_ref"],
        locator: str,
    ) -> Optional[str]:
        """诊断 locator 是否疑似来自其他已缓存文档。

        当 ``read_section`` / ``get_table`` 在当前 ``document_id`` 下查不到 locator 时，
        本方法只在 ``ProcessorLRUCache`` 中已经存在的 processor 上做尝试性查询，
        命中即返回疑似来源 ``document_id``。本方法严格遵守"不主动构建新 processor、
        不扫描磁盘"的成本约束，仅做零成本的快照只读诊断。

        Args:
            ticker: 标准化股票代码。
            current_document_id: 当前调用使用的文档 ID。
            kind: locator 类型，``"ref"`` 表示章节引用，``"table_ref"`` 表示表格引用。
            locator: 已经标准化过的 locator 字符串。

        Returns:
            疑似来源的 ``document_id``；若所有已缓存 processor 都查不到则返回 ``None``。

        Raises:
            无。
        """

        for cache_key in self._processor_cache.keys_snapshot():
            if cache_key.ticker != ticker:
                continue
            if cache_key.document_id == current_document_id:
                continue
            cached_processor = self._processor_cache.peek(cache_key)
            if cached_processor is None:
                continue
            try:
                if kind == "ref":
                    cached_processor.read_section(locator)
                else:
                    cached_processor.read_table(locator)
            except KeyError:
                continue
            except Exception as exc:
                # 复杂逻辑说明：诊断属于尽力而为的辅助路径，任何非 KeyError 的底层异常都
                # 不应让原始参数错误失真；记录调试日志后直接跳过该候选。
                Log.debug(
                    f"cross-document locator 诊断遇到非预期异常: ticker={ticker} "
                    f"candidate_document_id={cache_key.document_id} kind={kind} exc={exc}",
                    module=self.MODULE,
                )
                continue
            return cache_key.document_id
        return None

    def _get_or_create_processor(
        self,
        *,
        ticker: str,
        document_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> DocumentProcessor:
        """读取或创建 Processor 实例。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            Processor 实例。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: 未匹配处理器时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        cache_key = ProcessorCacheKey(ticker=ticker, document_id=document_id)
        cached = self._processor_cache.get(cache_key)
        if cached is not None:
            return cached

        lock = self._get_creation_lock(cache_key)
        with lock:
            # 复杂逻辑说明：并发线程在锁内二次检查，避免重复构建 Processor。
            _raise_if_fins_cancelled(cancellation_token)
            cached = self._processor_cache.get(cache_key)
            if cached is not None:
                return cached
            processor = self._create_processor(
                ticker=ticker,
                document_id=document_id,
                cancellation_token=cancellation_token,
            )
            _raise_if_fins_cancelled(cancellation_token)
            self._processor_cache.put(cache_key, processor)
            Log.debug(
                f"processor 已创建并缓存: ticker={ticker} document_id={document_id} type={type(processor).__name__}",
                module=self.MODULE,
            )
            return processor

    def _create_processor(
        self,
        *,
        ticker: str,
        document_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> DocumentProcessor:
        """创建 Processor 实例。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            Processor 实例。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: 未匹配处理器时抛出。
            RuntimeError: 候选处理器全部创建失败时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        source_kind = self._resolve_source_kind(
            ticker=ticker,
            document_id=document_id,
            cancellation_token=cancellation_token,
        )
        _raise_if_fins_cancelled(cancellation_token)
        source = self._source_repository.get_primary_source(
            ticker=ticker,
            document_id=document_id,
            source_kind=source_kind,
        )
        _raise_if_fins_cancelled(cancellation_token)
        source_meta = self._source_repository.get_source_meta(ticker, document_id, source_kind)
        form_type = normalize_optional_text(source_meta.get("form_type"))
        _raise_if_fins_cancelled(cancellation_token)
        return self._processor_registry.create_with_fallback(
            source=source,
            form_type=form_type,
            media_type=getattr(source, "media_type", None),
        )

    def _resolve_source_kind(
        self,
        *,
        ticker: str,
        document_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> SourceKind:
        """解析文档来源类型。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            来源类型。

        Raises:
            FileNotFoundError: 当文档既不在 filing 也不在 material 中时抛出。
        """

        try:
            _raise_if_fins_cancelled(cancellation_token)
            self._source_repository.get_source_handle(ticker, document_id, SourceKind.FILING)
            _raise_if_fins_cancelled(cancellation_token)
            return SourceKind.FILING
        except FileNotFoundError:
            pass
        try:
            _raise_if_fins_cancelled(cancellation_token)
            self._source_repository.get_source_handle(ticker, document_id, SourceKind.MATERIAL)
            _raise_if_fins_cancelled(cancellation_token)
            return SourceKind.MATERIAL
        except FileNotFoundError:
            pass
        raise FileNotFoundError(f"Document not found: ticker={ticker}, document_id={document_id}")

    def _get_creation_lock(self, cache_key: ProcessorCacheKey) -> Lock:
        """读取或创建文档级构建锁。

        Args:
            cache_key: Processor 缓存键。

        Returns:
            文档级互斥锁。

        Raises:
            RuntimeError: 锁表访问失败时抛出。
        """

        with self._creation_locks_guard:
            lock = self._creation_locks.get(cache_key)
            if lock is not None:
                return lock
            created = Lock()
            self._creation_locks[cache_key] = created
            return created
