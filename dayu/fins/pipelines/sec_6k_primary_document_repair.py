"""6-K active source 主文件 reconcile 真源模块。

本模块解决一类稳定的 6-K 选文问题：同一 filing 下可能存在多份 HTML，
而真正能被当前 `BsSixKFormProcessor` 提取出核心报表的文件，并不一定等于
当前 source meta 里的 `primary_document`。

这类问题的真源不在评分器，而在 source primary 选文。模块职责包括：
- 基于当前 active source 与现有 6-K 处理器评估全部 HTML 候选文件；
- 选择当前最能稳定提取 `income + balance_sheet` 的主文件；
- 对下载稳态写入与历史数据一次性修正提供统一入口。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from dayu.fins.domain.document_models import FilingUpdateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.processors.bs_six_k_processor import BsSixKFormProcessor
from dayu.fins.pipelines.sec_6k_rules import _score_6k_filename
from dayu.fins.storage import (
    CompanyMetaRepositoryProtocol,
    FsCompanyMetaRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    SourceDocumentRepositoryProtocol,
)


@dataclass(frozen=True, slots=True)
class SixKPrimaryCandidateAssessment:
    """单个 6-K 候选文件的可提取性评估结果。"""

    filename: str
    income_row_count: int
    balance_sheet_row_count: int
    filename_priority: int

    @property
    def total_core_row_count(self) -> int:
        """返回核心报表总行数。"""

        return self.income_row_count + self.balance_sheet_row_count

    @property
    def has_extractable_core_statements(self) -> bool:
        """返回是否已提取到完整核心报表。"""

        return self.income_row_count > 0 and self.balance_sheet_row_count > 0


@dataclass(frozen=True, slots=True)
class SixKPrimaryReconcileOutcome:
    """单份 6-K 主文件 reconcile 结果。"""

    ticker: str
    document_id: str
    previous_primary_document: str
    selected_primary_document: str
    total_core_row_count: int


@dataclass(frozen=True, slots=True)
class SixKPrimaryReconcileReport:
    """批量 6-K 主文件 reconcile 报告。"""

    workspace_root: str
    updated: tuple[SixKPrimaryReconcileOutcome, ...]


_CORE_STATEMENT_TYPES: tuple[str, str] = ("income", "balance_sheet")


def reconcile_active_6k_primary_document(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    mark_processed_reprocess_required: Optional[Callable[[str, str], None]] = None,
) -> Optional[SixKPrimaryReconcileOutcome]:
    """按当前处理器真源 reconcile 单份 active 6-K 的主文件选文。

    Args:
        source_repository: source 仓储协议。
        ticker: 股票代码。
        document_id: 文档 ID。
        mark_processed_reprocess_required: 可选 processed 重处理标记回调。

    Returns:
        若发生主文件更新，返回 reconcile 结果；否则返回 `None`。

    Raises:
        OSError: 仓储读写失败时抛出。
        ValueError: 文档元数据非法时抛出。
    """

    meta = source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)
    if bool(meta.get("is_deleted", False)):
        return None
    if str(meta.get("form_type", "")).strip().upper() != "6-K":
        return None

    primary_document = str(meta.get("primary_document", "")).strip()
    candidate_filenames = _list_candidate_html_filenames(meta)
    if not candidate_filenames:
        return None

    candidate_assessments = _collect_candidate_assessments(
        source_repository=source_repository,
        ticker=ticker,
        document_id=document_id,
        candidate_filenames=candidate_filenames,
        primary_document=primary_document,
    )
    best_assessment = _select_best_primary_candidate(
        primary_document=primary_document,
        candidate_assessments=candidate_assessments,
    )
    if best_assessment is None:
        return None
    if best_assessment.filename.lower() == primary_document.lower():
        return None

    _update_active_6k_primary_document(
        source_repository=source_repository,
        ticker=ticker,
        document_id=document_id,
        meta=meta,
        selected_primary_document=best_assessment.filename,
    )
    if mark_processed_reprocess_required is not None:
        mark_processed_reprocess_required(ticker, document_id)

    return SixKPrimaryReconcileOutcome(
        ticker=ticker,
        document_id=document_id,
        previous_primary_document=primary_document,
        selected_primary_document=best_assessment.filename,
        total_core_row_count=best_assessment.total_core_row_count,
    )


def reconcile_active_6k_primary_documents(
    *,
    workspace_root: Path,
    target_tickers: Optional[list[str]] = None,
    target_document_ids: Optional[list[str]] = None,
) -> SixKPrimaryReconcileReport:
    """批量按当前处理器真源 reconcile active 6-K 的主文件选文。

    Args:
        workspace_root: workspace 根目录。
        target_tickers: 可选 ticker 子集；为空时扫描当前 workspace 全部可用公司。
        target_document_ids: 可选 document_id 子集；为空时扫描目标 ticker 下全部 active 6-K。

    Returns:
        批量 reconcile 报告。

    Raises:
        OSError: 仓储读写失败时抛出。
        ValueError: 过滤参数非法时抛出。
    """

    resolved_workspace_root = workspace_root.resolve()
    source_repository = FsSourceDocumentRepository(resolved_workspace_root)
    processed_repository = FsProcessedDocumentRepository(resolved_workspace_root)
    company_repository = FsCompanyMetaRepository(resolved_workspace_root)

    normalized_document_ids = _normalize_document_ids(target_document_ids)
    target_ticker_list = _resolve_target_tickers(
        company_repository=company_repository,
        target_tickers=target_tickers,
    )

    updated: list[SixKPrimaryReconcileOutcome] = []
    for ticker in target_ticker_list:
        for document_id in source_repository.list_source_document_ids(ticker, SourceKind.FILING):
            if normalized_document_ids is not None and document_id not in normalized_document_ids:
                continue
            outcome = reconcile_active_6k_primary_document(
                source_repository=source_repository,
                ticker=ticker,
                document_id=document_id,
                mark_processed_reprocess_required=lambda current_ticker, current_document_id: _mark_processed_for_batch(
                    processed_repository=processed_repository,
                    ticker=current_ticker,
                    document_id=current_document_id,
                ),
            )
            if outcome is not None:
                updated.append(outcome)

    updated.sort(key=lambda item: (item.ticker, item.document_id))
    return SixKPrimaryReconcileReport(
        workspace_root=str(resolved_workspace_root),
        updated=tuple(updated),
    )


def _resolve_target_tickers(
    *,
    company_repository: CompanyMetaRepositoryProtocol,
    target_tickers: Optional[list[str]],
) -> list[str]:
    """解析本轮要扫描的 ticker 列表。

    Args:
        company_repository: 公司元数据仓储。
        target_tickers: 可选 ticker 子集。

    Returns:
        规范化后的 ticker 列表。

    Raises:
        ValueError: 传入 ticker 子集但去空后为空时抛出。
    """

    if target_tickers is not None:
        normalized = [ticker.strip().upper() for ticker in target_tickers if ticker.strip()]
        if not normalized:
            raise ValueError("target_tickers 不能为空")
        ordered: list[str] = []
        for ticker in normalized:
            if ticker not in ordered:
                ordered.append(ticker)
        return ordered

    discovered: list[str] = []
    for entry in company_repository.scan_company_meta_inventory():
        if entry.status != "available" or entry.company_meta is None:
            continue
        discovered.append(entry.company_meta.ticker)
    return sorted(set(discovered))


def _normalize_document_ids(target_document_ids: Optional[list[str]]) -> Optional[set[str]]:
    """规范化 document_id 过滤集合。

    Args:
        target_document_ids: 可选 document_id 列表。

    Returns:
        规范化后的 document_id 集合；未传入时返回 `None`。

    Raises:
        ValueError: 传入非空列表但清洗后为空时抛出。
    """

    if target_document_ids is None:
        return None
    normalized = {item.strip() for item in target_document_ids if item.strip()}
    if not normalized:
        raise ValueError("target_document_ids 不能为空")
    return normalized


def _mark_processed_for_batch(
    *,
    processed_repository: FsProcessedDocumentRepository,
    ticker: str,
    document_id: str,
) -> None:
    """在批量修复中标记 processed 需要重处理。

    Args:
        processed_repository: processed 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    try:
        processed_repository.mark_processed_reprocess_required(ticker, document_id, True)
    except FileNotFoundError:
        return


def _list_candidate_html_filenames(meta: dict[str, JsonValue]) -> list[str]:
    """从 meta 中列出 HTML 候选文件名。

    Args:
        meta: source meta。

    Returns:
        HTML 文件名列表。

    Raises:
        ValueError: `meta.files` 结构非法时抛出。
    """

    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("6-K source meta.files 必须为 list")

    filenames: list[str] = []
    for entry in raw_files:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        if not name.lower().endswith((".htm", ".html")):
            continue
        filenames.append(name)
    return filenames


def _collect_candidate_assessments(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    candidate_filenames: list[str],
    primary_document: str,
) -> list[SixKPrimaryCandidateAssessment]:
    """评估全部 6-K HTML 候选文件的核心报表可提取性。

    Args:
        source_repository: source 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。
        candidate_filenames: 全部 HTML 候选文件名。
        primary_document: 当前主文件名，用于 filename 优先级排序。

    Returns:
        候选评估结果列表。

    Raises:
        OSError: 文件读取失败时抛出。
        RuntimeError: 处理器初始化失败时抛出。
    """

    assessments: list[SixKPrimaryCandidateAssessment] = []
    for filename in candidate_filenames:
        assessments.append(
            _assess_active_6k_candidate(
                source_repository=source_repository,
                ticker=ticker,
                document_id=document_id,
                filename=filename,
                primary_document=primary_document,
            )
        )
    return assessments


def _assess_active_6k_candidate(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    filename: str,
    primary_document: str,
) -> SixKPrimaryCandidateAssessment:
    """评估某个 active 6-K 候选文件的核心报表可提取性。

    Args:
        source_repository: source 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。
        filename: 待评估文件名。
        primary_document: 当前主文件名，用于 filename 优先级排序。

    Returns:
        候选评估结果。

    Raises:
        OSError: 文件读取失败时抛出。
        RuntimeError: 处理器初始化失败时抛出。
    """

    source = source_repository.get_source(ticker, document_id, SourceKind.FILING, filename)
    processor = BsSixKFormProcessor(source, form_type="6-K")
    statement_rows = {
        statement_type: _count_statement_rows(processor, statement_type)
        for statement_type in _CORE_STATEMENT_TYPES
    }
    return SixKPrimaryCandidateAssessment(
        filename=filename,
        income_row_count=statement_rows["income"],
        balance_sheet_row_count=statement_rows["balance_sheet"],
        filename_priority=_score_6k_filename(filename, primary_document)[0],
    )


def _count_statement_rows(processor: BsSixKFormProcessor, statement_type: str) -> int:
    """统计某类财务报表的已提取行数。

    Args:
        processor: 6-K 处理器。
        statement_type: 报表类型。

    Returns:
        已提取行数。

    Raises:
        RuntimeError: 处理器提取失败时抛出。
    """

    statement = processor.get_financial_statement(statement_type)
    rows = statement.get("rows")
    if not isinstance(rows, list):
        return 0
    return len(rows)


def _select_best_primary_candidate(
    *,
    primary_document: str,
    candidate_assessments: list[SixKPrimaryCandidateAssessment],
) -> Optional[SixKPrimaryCandidateAssessment]:
    """从候选文件中选择当前最适合写回 source meta 的主文件。

    Args:
        primary_document: 当前主文件名。
        candidate_assessments: 全部候选评估结果。

    Returns:
        最佳候选评估结果；若不存在可稳定提取核心报表的候选则返回 `None`。

    Raises:
        无。
    """

    extractable_assessments = [
        item for item in candidate_assessments if item.has_extractable_core_statements
    ]
    if not extractable_assessments:
        return None
    normalized_primary = primary_document.strip().lower()
    return min(
        extractable_assessments,
        key=lambda item: (
            -item.total_core_row_count,
            item.filename_priority,
            item.filename.lower() != normalized_primary,
            item.filename.lower(),
        ),
    )


def _update_active_6k_primary_document(
    *,
    source_repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    meta: dict[str, JsonValue],
    selected_primary_document: str,
) -> None:
    """写回修正后的 6-K 主文件。

    Args:
        source_repository: source 仓储。
        ticker: 股票代码。
        document_id: 文档 ID。
        meta: 当前 source meta。
        selected_primary_document: 修正后的主文件名。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
        ValueError: 元数据结构非法时抛出。
    """

    raw_files = meta.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("6-K source meta.files 必须为 list")
    preserved_meta = {
        key: value
        for key, value in meta.items()
        if key not in {"files", "primary_document"}
    }
    source_repository.update_source_document(
        FilingUpdateRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=str(meta.get("internal_document_id", "")),
            form_type=str(meta.get("form_type", "")) or None,
            primary_document=selected_primary_document,
            file_entries=[
                dict(entry)
                for entry in raw_files
                if isinstance(entry, dict)
            ],
            meta=preserved_meta,
        ),
        source_kind=SourceKind.FILING,
    )
