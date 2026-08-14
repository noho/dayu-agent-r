"""财报读取运行时。

该模块是财报工具与底层仓储/处理器之间的中间调用层，职责包括：
- 参数校验与标准化。
- storage snapshot 到 processor 的同版路由。
- 统一能力降级（`not_supported`）。
- 仅做进程内 LRU 缓存，并通过 borrow/retire 生命周期保护 snapshot 资源。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from threading import Lock, RLock
from types import TracebackType
from typing import Any, Final, Literal, NoReturn, Optional, Protocol, TypedDict, runtime_checkable
from weakref import WeakValueDictionary

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.fins._log import Log
from dayu.fins.domain.document_models import FinsSourceProvider
from dayu.fins.domain.financial_result_contract import (
    FinancialStatementResult as ProcessorFinancialStatementResult,
    validate_financial_statement_result_payload,
)
from dayu.fins.domain.filing_semantics import (
    FiscalPeriod,
    fiscal_period_recency_rank,
    normalize_fiscal_period,
    normalize_fiscal_year,
)
from dayu.fins.domain.xbrl_result_contract import (
    XbrlFactsResult as ProcessorXbrlFactsResult,
    XbrlQueryExecutionError,
)
from dayu.documents.processors.base import (
    DocumentProcessor,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
)
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins.processors.source_text import FinsSourceDecodeError, validate_source_utf8_text
from .error_contract import ErrorCode
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.tool_models import Citation, SourceType
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage.repository_protocols import (
    SourceSnapshotConsistencyError,
    SourceSnapshotProtocol,
)
from .bm25f_scorer import BM25FSectionIndex, build_section_bm25f_index
from .section_semantic import (
    build_section_path,
    resolve_section_semantic,
)
from .cache import ProcessorCacheKey, ProcessorLRUCache

# 从拆分模块导入（FinsReadRuntime 直接使用）
from .search_models import (
    SectionSemanticProfile,
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
    ListDocumentsResult,
    NotSupportedResult,
    PageContentResult,
    PublicFinancialStatementResult,
    PublicXbrlQueryResult,
    SearchDocumentResult,
    SectionContentResult,
    TableDetailResult,
    TablesListResult,
    project_financial_statement_result,
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

class _SourceDocumentMeta(TypedDict):
    """read runtime 使用的 source meta 投影。

    该类型只承诺 read runtime 当前需要消费的字段；仓储 raw meta 的完整
    JSON schema 仍由 storage owner 持有。
    """

    form_type: str | None
    material_name: JsonValue | None
    fiscal_year: int | None
    fiscal_period: FiscalPeriod | None
    report_date: str | None
    filing_date: str | None
    amended: bool
    internal_document_id: str | None
    accession_number: str | None
    ingest_method: str | None
    source_provider: str | None
    is_deleted: bool
    ingest_complete: bool


class _CachedProcessor:
    """持有同版 processor、source meta 与 snapshot 资源的私有缓存条目。"""

    def __init__(
        self,
        *,
        processor: DocumentProcessor,
        source_meta: _SourceDocumentMeta,
        snapshot: SourceSnapshotProtocol,
    ) -> None:
        """初始化 live 缓存条目。

        Args:
            processor: 从 ``snapshot`` 主文件构建的处理器。
            source_meta: 从同一 ``snapshot`` 解析的 read-side meta 投影。
            snapshot: 条目独占的 full storage snapshot 资源。

        Returns:
            无。

        Raises:
            无。
        """

        self.processor = processor
        self.source_meta = source_meta
        self.snapshot = snapshot
        self._active_borrows = 0
        self._retired = False
        self._closed = False
        self._closing = False
        self._lock = RLock()

    def matches(self, snapshot: SourceSnapshotProtocol) -> bool:
        """判断条目是否与候选 snapshot 属于同一 source publication。

        Args:
            snapshot: 待比较的 light 或 full snapshot。

        Returns:
            source kind 与 opaque revision 均相等时返回 ``True``。

        Raises:
            RuntimeError: 任一 snapshot 已关闭时抛出。
        """

        with self._lock:
            if self._retired or self._closed:
                return False
            return (
                self.snapshot.source_kind is snapshot.source_kind
                and self.snapshot.revision == snapshot.revision
            )

    def try_acquire_borrow(self) -> bool:
        """尝试为 live 条目增加一个 active borrow。

        Args:
            无。

        Returns:
            成功借用返回 ``True``；条目已 retired/closed 时返回 ``False``。

        Raises:
            无。
        """

        with self._lock:
            if self._retired or self._closed:
                return False
            self._active_borrows += 1
            return True

    def release_borrow(self) -> bool:
        """释放一个 active borrow，并判断是否应执行延迟 close。

        Args:
            无。

        Returns:
            retired 条目最后一个 borrow 释放且可开始 close 时返回 ``True``。

        Raises:
            RuntimeError: borrow 计数下溢时抛出。
        """

        with self._lock:
            if self._active_borrows <= 0:
                raise RuntimeError("processor cache borrow 计数下溢")
            self._active_borrows -= 1
            return self._begin_close_if_ready()

    def retire(self) -> bool:
        """把条目标记为不可再借用，并判断是否可立即 close。

        Args:
            无。

        Returns:
            当前无 active borrow 且可开始 close 时返回 ``True``。

        Raises:
            无。
        """

        with self._lock:
            self._retired = True
            return self._begin_close_if_ready()

    def retry_close(self) -> bool:
        """尝试重新取得失败 cleanup 的 close authority。

        Args:
            无。

        Returns:
            条目 retired、无 active borrow 且尚未 closed 时返回 ``True``。

        Raises:
            无。
        """

        with self._lock:
            return self._begin_close_if_ready()

    def finish_close(self, *, succeeded: bool) -> None:
        """记录一次 snapshot close 的结果。

        Args:
            succeeded: snapshot 私有 cleanup 是否成功。

        Returns:
            无。

        Raises:
            无。
        """

        with self._lock:
            self._closing = False
            if succeeded:
                self._closed = True

    @property
    def closed(self) -> bool:
        """返回条目资源是否已经成功关闭。

        Args:
            无。

        Returns:
            snapshot cleanup 已成功完成时返回 ``True``。

        Raises:
            无。
        """

        with self._lock:
            return self._closed

    def _begin_close_if_ready(self) -> bool:
        """在持锁状态下判定并占有一次 snapshot close authority。

        Args:
            无。

        Returns:
            当前调用取得 close authority 时返回 ``True``。

        Raises:
            无。
        """

        if (
            not self._retired
            or self._active_borrows != 0
            or self._closed
            or self._closing
        ):
            return False
        self._closing = True
        return True


class _ProcessorBorrow:
    """一次 read 调用对 cached processor/snapshot 的私有 active borrow。"""

    def __init__(self, *, runtime: FinsReadRuntime, entry: _CachedProcessor) -> None:
        """初始化已取得计数的 borrow。

        Args:
            runtime: borrow release 与 cleanup 的 owner runtime。
            entry: 已成功增加 active borrow 的缓存条目。

        Returns:
            无。

        Raises:
            无。
        """

        self._runtime = runtime
        self._entry = entry
        self._released = False

    def __enter__(self) -> _ProcessorBorrow:
        """进入 borrow scope 并返回自身。

        Args:
            无。

        Returns:
            当前已取得 active count 的 borrow。

        Raises:
            无。
        """

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """退出 borrow scope，并在 retired 最后借用处释放 snapshot。

        Args:
            exc_type: scope 内活动异常类型。
            exc: scope 内活动异常。
            traceback: scope 内活动异常 traceback。

        Returns:
            始终返回 ``False``，不压制活动异常。

        Raises:
            RuntimeError: borrow 被重复释放时抛出。
            OSError: 无活动异常且 snapshot cleanup 失败时抛出。
        """

        del exc_type, traceback
        if self._released:
            raise RuntimeError("processor borrow 已释放")
        self._released = True
        self._runtime._release_processor_borrow(self._entry, active_error=exc)
        return False

    @property
    def processor(self) -> DocumentProcessor:
        """返回 borrow scope 内的 processor。

        Args:
            无。

        Returns:
            与当前 snapshot 同版的 processor。

        Raises:
            无。
        """

        return self._entry.processor

    @property
    def source_meta(self) -> _SourceDocumentMeta:
        """返回与 processor 同版的 source meta。

        Args:
            无。

        Returns:
            当前 cache entry 持有的 typed source meta。

        Raises:
            无。
        """

        return self._entry.source_meta

    @property
    def snapshot(self) -> SourceSnapshotProtocol:
        """返回与 processor 同版且仍受 borrow 保护的 snapshot。

        Args:
            无。

        Returns:
            当前 active borrow 对应的 full storage snapshot。

        Raises:
            无。
        """

        return self._entry.snapshot


class _SourceDocumentSummary(TypedDict):
    """list_documents 内部 source 文档摘要。"""

    document_id: str
    source_kind: str
    form_type: str | None
    material_name: JsonValue | None
    fiscal_year: int | None
    fiscal_period: FiscalPeriod | None
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

    def get_financial_statement(self, statement_type: str) -> ProcessorFinancialStatementResult:
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
    ) -> ProcessorXbrlFactsResult:
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

    fiscal_year = normalize_fiscal_year(raw_meta.get("fiscal_year"))
    raw_fiscal_period = raw_meta.get("fiscal_period")
    if raw_fiscal_period is not None and not isinstance(raw_fiscal_period, str):
        raise ValueError("fiscal_period 必须为字符串")
    return {
        "form_type": _normalize_json_scalar_text(raw_meta.get("form_type")),
        "material_name": raw_meta.get("material_name"),
        "fiscal_year": fiscal_year,
        "fiscal_period": normalize_fiscal_period(raw_fiscal_period),
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
    fiscal_period_rank = fiscal_period_recency_rank(item["fiscal_period"])
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


def _collect_list_document_recommendations(
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
    - processor 缓存条目独占一个 storage-owned full snapshot。
    - active borrow 完成前，replacement/eviction/close 不得释放其 snapshot。
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
    ) -> None:
        """初始化服务。

        Args:
            company_repository: 公司元数据仓储实现。
            source_repository: 源文档仓储实现。
            processed_repository: processed 文档仓储实现。
            processor_registry: 处理器注册表。
            processor_cache_max_entries: Processor LRU 缓存容量。

        Returns:
            无。

        Raises:
            ValueError: 当缓存容量非法时抛出。
        """

        if processor_cache_max_entries <= 0:
            raise ValueError("processor_cache_max_entries must be greater than 0")
        self._company_repository = company_repository
        self._source_repository = source_repository
        self._processed_repository = processed_repository
        self._processor_registry = processor_registry
        self._processor_cache: ProcessorLRUCache[_CachedProcessor] = ProcessorLRUCache(
            max_entries=processor_cache_max_entries,
        )
        self._creation_locks: WeakValueDictionary[ProcessorCacheKey, Lock] = WeakValueDictionary()
        self._creation_locks_guard = RLock()
        self._lifecycle_lock = RLock()
        self._retired_entries: set[_CachedProcessor] = set()
        self._pending_snapshots: list[SourceSnapshotProtocol] = []
        self._closed = False

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

        self._ensure_open()
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
        recommended_documents = _collect_list_document_recommendations(documents_with_type)

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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            _raise_if_fins_cancelled(cancellation_token)
            sections_raw: list[SectionSummary] = borrow.processor.list_sections()
            _raise_if_fins_cancelled(cancellation_token)
            form_type = self._resolve_document_form_type(borrow=borrow)
            enriched_sections = self._enrich_sections_with_semantic(
                sections_raw,
                form_type,
                cancellation_token=cancellation_token,
            )
            citation = self._build_citation(borrow=borrow)
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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._read_section_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                normalized_ref=normalized_ref,
                cancellation_token=cancellation_token,
            )

    def _read_section_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        normalized_ref: str,
        cancellation_token: CancellationToken | None,
    ) -> SectionContentResult:
        """在一个 active processor/snapshot borrow 内完成章节读取与 citation。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            normalized_ref: 已校验章节 ref。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            章节正文结果。

        Raises:
            FinsReadArgumentError: ref 不属于当前文档时抛出。
            FinsReadCancelledError: 调用被取消时抛出。
        """

        processor = borrow.processor
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
        form_type = self._resolve_document_form_type(borrow=borrow)
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
            borrow=borrow,
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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._search_document_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                resolved_queries=resolved_queries,
                original_queries=original_queries,
                normalized_within_ref=normalized_within_ref,
                resolved_mode=resolved_mode,
                display_budget=display_budget,
                cancellation_token=cancellation_token,
            )

    def _search_document_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        resolved_queries: list[str],
        original_queries: list[str],
        normalized_within_ref: Optional[str],
        resolved_mode: str,
        display_budget: Optional[int],
        cancellation_token: CancellationToken | None,
    ) -> SearchDocumentResult:
        """在一个 active borrow 内完成单/多查询搜索与 citation 构造。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            resolved_queries: 已校验查询数组。
            original_queries: 原始查询数组。
            normalized_within_ref: 可选章节范围。
            resolved_mode: 搜索模式。
            display_budget: 可选展示预算。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            搜索结果。

        Raises:
            FinsReadBusinessError: 搜索索引构建失败时抛出。
            FinsReadCancelledError: 调用被取消时抛出。
        """

        processor = borrow.processor
        # 预构建证据化所需的 form_type / ref_to_topic
        form_type = self._resolve_document_form_type(borrow=borrow)
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
            ref_to_topic: dict[str, Optional[str]] = {}
            for sec in enriched_for_search:
                _raise_if_fins_cancelled(cancellation_token)
                ref = sec.get("ref")
                if ref:
                    ref_to_topic[ref] = sec.get("topic")
        except FinsReadCancelledError:
            raise
        except Exception as exc:
            # 异常与取消同时发生时，Host 取消仍是优先终态；只有未取消的
            # index readiness 失败才投影为搜索业务失败。
            _raise_if_fins_cancelled(cancellation_token)
            raise FinsReadBusinessError(
                ErrorCode.SEARCH_INDEX_FAILED,
                "文档搜索索引构建失败，当前搜索结果不可用。",
                hint="请稍后重新发起搜索；也可先读取章节列表定位内容。",
            ) from exc

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
                borrow=borrow,
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
                borrow=borrow,
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
        borrow: _ProcessorBorrow,
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
            borrow: 当前 read 调用的 active borrow。
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
                borrow=borrow,
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

        self._ensure_open()
        _raise_if_fins_cancelled(cancellation_token)
        normalized_ticker, normalized_document_id = self._normalize_document_identity(
            ticker=ticker,
            document_id=document_id,
            tool_name="list_tables",
            cancellation_token=cancellation_token,
        )
        normalized_within_ref = normalize_optional_text(within_section_ref)

        _raise_if_fins_cancelled(cancellation_token)
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._list_tables_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                financial_only=financial_only,
                normalized_within_ref=normalized_within_ref,
                cancellation_token=cancellation_token,
            )

    def _list_tables_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        financial_only: bool,
        normalized_within_ref: Optional[str],
        cancellation_token: CancellationToken | None,
    ) -> TablesListResult:
        """在一个 active borrow 内完成表格列表与 citation 构造。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            financial_only: 是否只返回财务表格。
            normalized_within_ref: 可选章节范围。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            表格列表结果。

        Raises:
            FinsReadCancelledError: 调用被取消时抛出。
        """

        processor = borrow.processor
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
                borrow=borrow,
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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._get_table_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                normalized_table_ref=normalized_table_ref,
                cancellation_token=cancellation_token,
            )

    def _get_table_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        normalized_table_ref: str,
        cancellation_token: CancellationToken | None,
    ) -> TableDetailResult:
        """在一个 active borrow 内完成表格读取与 citation 构造。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            normalized_table_ref: 已校验表格 ref。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            表格详情结果。

        Raises:
            FinsReadArgumentError: table ref 不属于当前文档时抛出。
            FinsReadCancelledError: 调用被取消时抛出。
        """

        processor = borrow.processor
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
                borrow=borrow,
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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._get_page_content_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                page_no=page_no,
                cancellation_token=cancellation_token,
            )

    def _get_page_content_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        page_no: int,
        cancellation_token: CancellationToken | None,
    ) -> PageContentResult | NotSupportedResult:
        """在一个 active borrow 内完成分页读取与 citation 构造。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            page_no: 目标页码。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            页面内容或不支持结果。

        Raises:
            FinsReadCancelledError: 调用被取消时抛出。
        """

        processor = borrow.processor
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
                borrow=borrow,
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
    ) -> PublicFinancialStatementResult | NotSupportedResult:
        """读取标准财务报表。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            statement_type: 报表类型。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            财务报表公共结果；不支持时返回 `not_supported` 结构。

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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._get_financial_statement_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                normalized_statement_type=normalized_statement_type,
                cancellation_token=cancellation_token,
            )

    def _get_financial_statement_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        normalized_statement_type: str,
        cancellation_token: CancellationToken | None,
    ) -> PublicFinancialStatementResult | NotSupportedResult:
        """在一个 active borrow 内完成财务报表读取与 citation 构造。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            normalized_statement_type: 已校验报表类型。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            财务报表或不支持结果。

        Raises:
            FinsReadCancelledError: 调用被取消时抛出。
            ValueError: processor 返回无效财务报表 payload 时抛出。
        """

        processor = borrow.processor
        if not isinstance(processor, _FinancialStatementReadProcessor):
            return _build_not_supported_result(
                ticker=normalized_ticker,
                document_id=normalized_document_id,
                feature="get_financial_statement",
                payload={"statement_type": normalized_statement_type},
            )

        _raise_if_fins_cancelled(cancellation_token)
        statement_payload = validate_financial_statement_result_payload(
            processor.get_financial_statement(normalized_statement_type)
        )
        _raise_if_fins_cancelled(cancellation_token)
        citation = self._build_citation(
            borrow=borrow,
        )
        for _row in statement_payload["rows"]:
            _raise_if_fins_cancelled(cancellation_token)
        return project_financial_statement_result(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            citation=citation,
            producer_result=statement_payload,
        )

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
    ) -> PublicXbrlQueryResult | NotSupportedResult:
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
        with self._borrow_processor(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            cancellation_token=cancellation_token,
        ) as borrow:
            return self._query_xbrl_facts_with_borrow(
                borrow=borrow,
                normalized_ticker=normalized_ticker,
                normalized_document_id=normalized_document_id,
                normalized_concepts=normalized_concepts,
                statement_type=statement_type,
                period_end=period_end,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                min_value=min_value,
                max_value=max_value,
                cancellation_token=cancellation_token,
            )

    def _query_xbrl_facts_with_borrow(
        self,
        *,
        borrow: _ProcessorBorrow,
        normalized_ticker: str,
        normalized_document_id: str,
        normalized_concepts: list[str],
        statement_type: Optional[str],
        period_end: Optional[str],
        fiscal_year: Optional[int],
        fiscal_period: Optional[str],
        min_value: Optional[float],
        max_value: Optional[float],
        cancellation_token: CancellationToken | None,
    ) -> PublicXbrlQueryResult | NotSupportedResult:
        """在一个 active borrow 内完成 XBRL 查询与 citation 构造。

        Args:
            borrow: 当前 read 调用的 active borrow。
            normalized_ticker: 标准化 ticker。
            normalized_document_id: 标准化文档 ID。
            normalized_concepts: 已校验 concept 数组。
            statement_type: 可选报表类型。
            period_end: 可选期末日期。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值。
            max_value: 可选最大值。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            XBRL 查询或不支持结果。

        Raises:
            FinsReadBusinessError: processor XBRL 查询执行失败时抛出。
            FinsReadCancelledError: 调用被取消时抛出。
        """

        processor = borrow.processor
        form_type = self._resolve_document_form_type(borrow=borrow)
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
        try:
            payload = processor.query_xbrl_facts(
                concepts=resolved_concepts,
                statement_type=normalize_optional_text(statement_type),
                period_end=normalize_optional_text(period_end),
                fiscal_year=fiscal_year,
                fiscal_period=normalize_optional_text(fiscal_period),
                min_value=min_value,
                max_value=max_value,
            )
        except XbrlQueryExecutionError as exc:
            raise FinsReadBusinessError(
                ErrorCode.XBRL_QUERY_FAILED,
                "XBRL 查询执行失败，当前结果不可作为零命中使用。",
                hint="请稍后重试；若持续失败，可改用财务报表或原文读取工具。",
            ) from exc
        _raise_if_fins_cancelled(cancellation_token)
        for _raw_fact in payload["facts"]:
            _raise_if_fins_cancelled(cancellation_token)
        normalized_payload = _normalize_xbrl_query_payload(
            ticker=normalized_ticker,
            document_id=normalized_document_id,
            citation=self._build_citation(
                borrow=borrow,
            ),
            payload=payload,
        )
        for _fact in normalized_payload["facts"]:
            _raise_if_fins_cancelled(cancellation_token)
        return normalized_payload

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
                code=ErrorCode.NOT_FOUND,
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
        try:
            direct_snapshot = self._read_source_snapshot(
                ticker=ticker,
                document_id=raw_document_id,
                source_kind=None,
                materialize_files=False,
            )
        except FileNotFoundError:
            pass
        else:
            self._close_unowned_snapshot(direct_snapshot, active_error=None)
            return raw_document_id

        normalized_alias = re.sub(r"\s+", "", raw_document_id).strip()
        matched_documents: dict[str, str] = {}
        for source_kind in SourceKind:
            _raise_if_fins_cancelled(cancellation_token)
            for candidate_document_id in self._source_repository.list_source_document_ids(ticker, source_kind):
                _raise_if_fins_cancelled(cancellation_token)
                try:
                    candidate_meta = _parse_source_document_meta(
                        self._source_repository.get_source_meta(
                            ticker,
                            candidate_document_id,
                            source_kind,
                        )
                    )
                except FileNotFoundError:
                    continue
                alias_fields = self._build_document_identity_aliases(
                    candidate_document_id=candidate_document_id,
                    meta=candidate_meta,
                )
                if normalized_alias not in alias_fields:
                    continue
                matched_field = alias_fields[normalized_alias]
                matched_documents[candidate_document_id] = matched_field

        if len(matched_documents) > 1:
            raise FinsReadArgumentError(
                tool_name,
                "document_id",
                raw_document_id,
                "document_id alias matches multiple documents; use an exact list_documents document_id",
            )
        if matched_documents:
            candidate_document_id, matched_field = next(iter(matched_documents.items()))
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
                meta = _parse_source_document_meta(
                    self._source_repository.get_source_meta(ticker, document_id, source_kind)
                )
            except FileNotFoundError:
                continue
            if meta.get("is_deleted", False):
                continue
            if not meta.get("ingest_complete", True):
                continue
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
                    "fiscal_year": meta["fiscal_year"],
                    "fiscal_period": meta["fiscal_period"],
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
        borrow: _ProcessorBorrow,
        item: Optional[str] = None,
        heading: Optional[str] = None,
    ) -> dict[str, Any]:
        """从当前 processor borrow 的同版 snapshot 构建 citation。

        Args:
            borrow: 当前 read 调用持有的 processor/snapshot borrow。
            item: 可选 Item 编号（如 "Item 1A"）。
            heading: 可选章节标题。

        Returns:
            citation 字典（值为 None 的键已移除）。

        Raises:
            FileNotFoundError: snapshot provenance 表示 source 尚未完成时抛出。
            RuntimeError: borrow 对应 snapshot 已关闭时抛出。
        """

        snapshot = borrow.snapshot
        meta = borrow.source_meta
        provenance = snapshot.provenance
        if not provenance.ingest_complete:
            raise FileNotFoundError(
                f"source document 尚未完成入库: ticker={snapshot.ticker}, "
                f"document_id={snapshot.document_id}"
            )
        if snapshot.source_kind is SourceKind.MATERIAL:
            source_type = SourceType.SUPPLEMENTARY.value
        else:
            source_type = _FILING_SOURCE_TYPES_BY_PROVIDER[provenance.source_provider].value
        source_provider = _CITATION_PROVIDER_LABELS[provenance.source_provider]

        form_type = _normalize_form_type_for_matching(meta["form_type"])
        # 美股 filing 的 accession_number 存储在 meta.json 中
        accession_no = meta["accession_number"]

        citation = Citation(
            source_type=source_type,
            document_id=snapshot.document_id,
            ticker=snapshot.ticker,
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

    def _resolve_document_form_type(self, *, borrow: _ProcessorBorrow) -> Optional[str]:
        """从当前 processor borrow 的同版 meta 读取 form_type。

        Args:
            borrow: 当前 read 调用持有的 processor/snapshot borrow。

        Returns:
            标准化后的 form_type。

        Raises:
            无。
        """

        return _normalize_form_type_for_matching(borrow.source_meta.get("form_type"))

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
        return company_meta.company_name, company_meta.ticker_identity.market

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
            borrow = self._get_cached_processor_borrow_for_diagnosis(cache_key)
            if borrow is None:
                continue
            try:
                with borrow:
                    if kind == "ref":
                        borrow.processor.read_section(locator)
                    else:
                        borrow.processor.read_table(locator)
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

    def _get_cached_processor_borrow_for_diagnosis(
        self,
        cache_key: ProcessorCacheKey,
    ) -> _ProcessorBorrow | None:
        """借用仍与 storage lightweight snapshot 一致的诊断候选 processor。

        Args:
            cache_key: 无 source-kind 维度的 processor cache key。

        Returns:
            snapshot 一致的 active borrow；未命中、source 失效或 mismatch
            时返回 ``None``。

        Raises:
            RuntimeError: document lock 或缓存内部操作失败时抛出。
        """

        lock = self._get_creation_lock(cache_key)
        with lock:
            cached = self._processor_cache.peek(cache_key)
            if cached is None:
                return None
            try:
                source_kind = cached.snapshot.source_kind
                light_snapshot = self._read_source_snapshot(
                    ticker=cache_key.ticker,
                    document_id=cache_key.document_id,
                    source_kind=source_kind,
                    materialize_files=False,
                )
            except Exception as read_error:
                self._evict_processor_entry(cache_key, active_error=read_error)
                return None
            try:
                is_matching = cached.matches(light_snapshot)
                acquired = is_matching and cached.try_acquire_borrow()
            except Exception as exc:
                self._close_unowned_snapshot(light_snapshot, active_error=exc)
                self._evict_processor_entry(cache_key, active_error=exc)
                return None
            try:
                self._close_unowned_snapshot(light_snapshot, active_error=None)
            except Exception as close_error:
                if acquired:
                    self._release_processor_borrow(cached, active_error=close_error)
                self._evict_processor_entry(cache_key, active_error=close_error)
                return None
            if not acquired:
                self._evict_processor_entry(cache_key)
                return None
            return _ProcessorBorrow(runtime=self, entry=cached)

    def _borrow_processor(
        self,
        *,
        ticker: str,
        document_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> _ProcessorBorrow:
        """读取或创建同版 processor cache entry，并返回 active borrow。

        Args:
            ticker: 标准化股票代码。
            document_id: 标准化文档 ID。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            覆盖 processor/meta/provenance/citation/result 全路径的 active borrow。

        Raises:
            FileNotFoundError: 文档不存在时抛出。
            ValueError: 未匹配处理器时抛出。
            FinsReadBusinessError: source 解码失败或 storage 稳定读取耗尽时抛出。
            RuntimeError: runtime 已关闭时抛出。
        """

        self._ensure_open()
        _raise_if_fins_cancelled(cancellation_token)
        cache_key = ProcessorCacheKey(ticker=ticker, document_id=document_id)
        lock = self._get_creation_lock(cache_key)
        cached_before_read = self._processor_cache.peek(cache_key)
        try:
            light_snapshot = self._read_source_snapshot(
                ticker=ticker,
                document_id=document_id,
                source_kind=None,
                materialize_files=False,
            )
        except BaseException as read_error:
            if cached_before_read is not None:
                self._evict_processor_entry_if_matches(
                    cache_key,
                    expected=cached_before_read,
                    active_error=read_error,
                )
            raise

        cached = self._processor_cache.get(cache_key)
        acquired_cached = False
        try:
            acquired_cached = (
                cached is not None
                and cached.matches(light_snapshot)
                and cached.try_acquire_borrow()
            )
        except BaseException as compare_error:
            self._close_unowned_snapshot(light_snapshot, active_error=compare_error)
            if cached is not None:
                self._evict_processor_entry_if_matches(
                    cache_key,
                    expected=cached,
                    active_error=compare_error,
                )
            raise
        try:
            self._close_unowned_snapshot(light_snapshot, active_error=None)
        except BaseException as close_error:
            if acquired_cached and cached is not None:
                self._release_processor_borrow(cached, active_error=close_error)
            raise
        if acquired_cached and cached is not None:
            return _ProcessorBorrow(runtime=self, entry=cached)
        if cached is not None:
            self._evict_processor_entry_if_matches(
                cache_key,
                expected=cached,
            )

        _raise_if_fins_cancelled(cancellation_token)
        full_snapshot = self._read_source_snapshot(
            ticker=ticker,
            document_id=document_id,
            source_kind=None,
            materialize_files=True,
        )
        snapshot_transferred = False
        try:
            with lock:
                self._ensure_open()
                _raise_if_fins_cancelled(cancellation_token)
                competing = self._processor_cache.get(cache_key)
                if (
                    competing is not None
                    and competing.matches(full_snapshot)
                    and competing.try_acquire_borrow()
                ):
                    try:
                        self._close_unowned_snapshot(full_snapshot, active_error=None)
                    except BaseException as close_error:
                        self._release_processor_borrow(
                            competing,
                            active_error=close_error,
                        )
                        raise
                    return _ProcessorBorrow(runtime=self, entry=competing)
                if competing is not None:
                    self._evict_processor_entry(cache_key)

                processor, source_meta = self._create_processor_from_snapshot(
                    snapshot=full_snapshot,
                    cancellation_token=cancellation_token,
                )
                _raise_if_fins_cancelled(cancellation_token)
                created = _CachedProcessor(
                    processor=processor,
                    source_meta=source_meta,
                    snapshot=full_snapshot,
                )
                if not created.try_acquire_borrow():
                    raise RuntimeError("新建 processor cache entry 无法借用")
                # 复杂逻辑说明：最终 closed-check 与 cache publication 必须和
                # close() 的状态切换共用同一线性化锁。processor 构建本身仍不持锁。
                with self._lifecycle_lock:
                    self._ensure_open()
                    displaced = self._processor_cache.put(cache_key, created)
                    snapshot_transferred = True
                try:
                    self._retire_entries(displaced)
                except BaseException as retire_error:
                    removed = self._processor_cache.evict(cache_key)
                    if removed is not None:
                        self._retire_entry(removed, active_error=retire_error)
                    self._release_processor_borrow(created, active_error=retire_error)
                    raise
            Log.debug(
                f"processor 已创建并缓存: ticker={ticker} document_id={document_id} type={type(processor).__name__}",
                module=self.MODULE,
            )
            return _ProcessorBorrow(runtime=self, entry=created)
        except BaseException as build_error:
            if not snapshot_transferred:
                self._close_unowned_snapshot(full_snapshot, active_error=build_error)
            raise

    def _create_processor_from_snapshot(
        self,
        *,
        snapshot: SourceSnapshotProtocol,
        cancellation_token: CancellationToken | None = None,
    ) -> tuple[DocumentProcessor, _SourceDocumentMeta]:
        """从一个 full snapshot 创建 Processor 与同版 meta 投影。

        Args:
            snapshot: storage 已稳定物化的 full snapshot。
            cancellation_token: Host 注入的取消观察令牌。

        Returns:
            ``(processor, source_meta)``。

        Raises:
            ValueError: 未匹配处理器时抛出。
            RuntimeError: 候选处理器全部创建失败时抛出。
            FinsReadBusinessError: 文本 source 无法可靠解码时抛出。
        """

        _raise_if_fins_cancelled(cancellation_token)
        source = snapshot.get_primary_source()
        source_meta = snapshot.source_meta
        parsed_source_meta = _parse_source_document_meta(source_meta)
        if parsed_source_meta["is_deleted"] or not parsed_source_meta["ingest_complete"]:
            raise FileNotFoundError(
                f"source document 当前不可读取: ticker={snapshot.ticker}, "
                f"document_id={snapshot.document_id}"
            )
        form_type = normalize_optional_text(parsed_source_meta["form_type"])
        _raise_if_fins_cancelled(cancellation_token)
        try:
            validate_source_utf8_text(source)
            processor = self._processor_registry.create_with_fallback(
                source=source,
                form_type=form_type,
                media_type=source.media_type,
            )
            return processor, parsed_source_meta
        except FinsSourceDecodeError as exc:
            raise FinsReadBusinessError(
                ErrorCode.SOURCE_DECODE_FAILED,
                "源文档无法被可靠解码，当前读取结果不可用。",
                hint="请重新获取有效的 UTF-8 源文档后再试。",
            ) from exc

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

    def _read_source_snapshot(
        self,
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """读取 storage snapshot，并单点映射稳定读取耗尽错误。

        Args:
            ticker: exact external ticker。
            document_id: exact external document ID。
            source_kind: 可选显式 source kind。
            materialize_files: 是否物化全部业务文件。

        Returns:
            storage-owned light/full snapshot。

        Raises:
            FinsReadBusinessError: storage 稳定读取预算耗尽时抛出。
            FileNotFoundError: source 不存在时抛出。
            ValueError: source kind 歧义或 snapshot 不完整时抛出。
            OSError: snapshot 文件系统读取失败时抛出。
        """

        try:
            return self._source_repository.read_source_snapshot(
                ticker,
                document_id,
                source_kind,
                materialize_files=materialize_files,
            )
        except SourceSnapshotConsistencyError as exc:
            self._raise_source_changed_during_read(cause=exc)

    def _evict_processor_entry(
        self,
        cache_key: ProcessorCacheKey,
        *,
        active_error: BaseException | None = None,
    ) -> None:
        """从 LRU 移除一个 processor entry 并交给 lifecycle owner retire。

        Args:
            cache_key: 无 source-kind 维度的 processor cache key。
            active_error: 当前活动主异常；正常 eviction 为 ``None``。

        Returns:
            无。

        Raises:
            OSError: 无 active borrow 且 snapshot cleanup 失败时抛出。
        """

        displaced = self._processor_cache.evict(cache_key)
        if displaced is not None:
            self._retire_entry(displaced, active_error=active_error)

    def _evict_processor_entry_if_matches(
        self,
        cache_key: ProcessorCacheKey,
        *,
        expected: _CachedProcessor,
        active_error: BaseException | None = None,
    ) -> None:
        """只 retire caller 先前观察到且尚未被替换的 entry。

        Args:
            cache_key: processor cache key。
            expected: caller 先前观察到的 entry 实例。
            active_error: 当前活动主异常；正常 stale eviction 为 ``None``。

        Returns:
            无。

        Raises:
            OSError: 无活动主异常且 snapshot cleanup 失败时抛出。
        """

        displaced = self._processor_cache.evict_if(cache_key, expected)
        if displaced is not None:
            self._retire_entry(displaced, active_error=active_error)

    def _retire_entries(self, entries: tuple[_CachedProcessor, ...]) -> None:
        """完整 retire 一组 LRU displaced entries。

        Args:
            entries: replacement/eviction/clear 返回的旧条目。

        Returns:
            无。

        Raises:
            BaseException: 完整处理所有条目后，抛出遇到的第一个 snapshot cleanup 失败。
        """

        first_error: BaseException | None = None
        for entry in entries:
            try:
                self._retire_entry(entry, active_error=None)
            except BaseException as close_error:
                if first_error is None:
                    first_error = close_error
                else:
                    first_error.add_note(
                        f"另一个 processor snapshot cleanup 失败: type={type(close_error).__name__}"
                    )
        if first_error is not None:
            raise first_error

    def _retire_entry(
        self,
        entry: _CachedProcessor,
        *,
        active_error: BaseException | None,
    ) -> None:
        """把单个 cache entry 转为 retired，并按 borrow 状态释放资源。

        Args:
            entry: 待 retire 的缓存条目。
            active_error: 当前业务主异常；正常路径为 ``None``。

        Returns:
            无。

        Raises:
            OSError: 无业务主异常且 snapshot cleanup 失败时抛出。
        """

        with self._lifecycle_lock:
            self._retired_entries.add(entry)
        if entry.retire():
            self._close_retired_entry(entry, active_error=active_error)

    def _release_processor_borrow(
        self,
        entry: _CachedProcessor,
        *,
        active_error: BaseException | None,
    ) -> None:
        """释放 borrow，并在 retired 最后借用处执行 snapshot cleanup。

        Args:
            entry: borrow 所属缓存条目。
            active_error: borrow scope 内活动业务异常。

        Returns:
            无。

        Raises:
            RuntimeError: borrow 计数下溢时抛出。
            OSError: 无业务主异常且 snapshot cleanup 失败时抛出。
        """

        if entry.release_borrow():
            self._close_retired_entry(entry, active_error=active_error)

    def _close_retired_entry(
        self,
        entry: _CachedProcessor,
        *,
        active_error: BaseException | None,
    ) -> None:
        """关闭一个已取得 close authority 的 retired entry。

        Args:
            entry: 已 retired 且无 active borrow 的条目。
            active_error: 当前业务主异常；存在时 cleanup 失败只追加 path-free note。

        Returns:
            无。

        Raises:
            BaseException: 无业务主异常且 snapshot cleanup 失败时原样抛出。
        """

        try:
            entry.snapshot.close()
        except BaseException as close_error:
            entry.finish_close(succeeded=False)
            if active_error is not None:
                self._append_cleanup_note(active_error, close_error)
                return
            raise
        entry.finish_close(succeeded=True)
        with self._lifecycle_lock:
            self._retired_entries.discard(entry)

    def _close_unowned_snapshot(
        self,
        snapshot: SourceSnapshotProtocol,
        *,
        active_error: BaseException | None,
    ) -> None:
        """关闭尚未交给 cache entry 的 snapshot，并保留失败重试 authority。

        Args:
            snapshot: light、losing 或 processor build 失败的 snapshot。
            active_error: 当前业务主异常；正常路径为 ``None``。

        Returns:
            无。

        Raises:
            BaseException: 无业务主异常且 snapshot cleanup 失败时原样抛出。
        """

        try:
            snapshot.close()
        except BaseException as close_error:
            with self._lifecycle_lock:
                if all(candidate is not snapshot for candidate in self._pending_snapshots):
                    self._pending_snapshots.append(snapshot)
            if active_error is not None:
                self._append_cleanup_note(active_error, close_error)
                return
            raise

    def _retry_pending_cleanup(self) -> None:
        """重试此前失败的 unowned snapshot 与 retired entry cleanup。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: 任一重试仍失败时，在尝试全部资源后抛出首个失败。
        """

        with self._lifecycle_lock:
            snapshots = tuple(self._pending_snapshots)
            entries = tuple(self._retired_entries)
        first_error: BaseException | None = None
        for snapshot in snapshots:
            try:
                snapshot.close()
            except BaseException as close_error:
                if first_error is None:
                    first_error = close_error
                continue
            with self._lifecycle_lock:
                self._pending_snapshots = [
                    candidate for candidate in self._pending_snapshots if candidate is not snapshot
                ]
        for entry in entries:
            if not entry.retry_close():
                continue
            try:
                self._close_retired_entry(entry, active_error=None)
            except BaseException as close_error:
                if first_error is None:
                    first_error = close_error
        if first_error is not None:
            raise first_error

    def _ensure_open(self) -> None:
        """确认 runtime 仍允许发起新的 read borrow。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: runtime 已关闭时抛出。
        """

        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("Fins read runtime 已关闭")

    def close(self) -> None:
        """幂等关闭 runtime，并 retire/clear 全部 processor snapshot 资源。

        已在执行的 active borrow 可以完成；对应 retired snapshot 会在最后一个
        borrow release 时关闭。关闭后禁止发起新的 read。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: snapshot cleanup 失败且无业务主异常可承载时抛出。
        """

        with self._lifecycle_lock:
            first_close = not self._closed
            self._closed = True
        if first_close:
            self._retire_entries(self._processor_cache.clear())
        self._retry_pending_cleanup()

    @staticmethod
    def _append_cleanup_note(primary_error: BaseException, close_error: BaseException) -> None:
        """向业务主异常追加不含 locator/message 的 cleanup 次要诊断。

        Args:
            primary_error: 应保持优先级的业务异常。
            close_error: snapshot cleanup 次要异常。

        Returns:
            无。

        Raises:
            无。
        """

        errno_text = ""
        if isinstance(close_error, OSError) and close_error.errno is not None:
            errno_text = f" errno={close_error.errno}"
        primary_error.add_note(
            "processor snapshot cleanup 失败: "
            f"type={type(close_error).__name__}{errno_text}"
        )

    @staticmethod
    def _raise_source_changed_during_read(*, cause: Exception | None = None) -> NoReturn:
        """抛出读取期间 source revision 变化的 typed failure。

        Args:
            cause: 可选的第二次 revision 读取异常。

        Returns:
            不返回。

        Raises:
            FinsReadBusinessError: 始终以 ``source_changed_during_read`` 抛出。
        """

        failure = FinsReadBusinessError(
            ErrorCode.SOURCE_CHANGED_DURING_READ,
            "源文档持续更新，暂时无法取得完整一致的读取版本。",
            hint="请稍后重新发起读取。",
        )
        if cause is None:
            raise failure
        raise failure from cause
