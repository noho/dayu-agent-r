"""SecPipeline 下载流程测试。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import asyncio
import json
import logging
import datetime as dt
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from threading import Event
from typing import BinaryIO, Literal, Optional, cast

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture

from dayu.fins.downloaders.sec_downloader import (
    BrowseEdgarFiling,
    DownloaderEvent,
    RemoteFileDescriptor,
    Sc13PartyRoles,
    SecDownloader,
    StoreDownloadedFile,
    SecDownloadCancelledError,
    _PrefetchEvent,
    _PrefetchFailed,
    _PrefetchedFile,
    _PrefetchSkipped,
    _PrefetchStarted,
    build_source_fingerprint,
)
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    DownloadRejectionEntry,
    FileObjectMeta,
    FilingUpdateRequest,
    FinsSourceProvider,
    ProcessedCreateRequest,
    SourceDocumentUpsertRequest,
    SourceFileEntry,
    SourceHandle,
)
from dayu.fins.ingestion_runtime import FinsSourceDownloadAdapterRequest
from dayu.fins.download_contract import (
    FinsDownloadDateRange,
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines import sec_download_filing_workflow as _sec_download_filing_workflow
from dayu.fins.pipelines import sec_download_state as _sec_download_state
from dayu.fins.pipelines import sec_6k_rules as _sec_6k_rules
from dayu.fins.pipelines import sec_6k_primary_document_repair as _sec_6k_primary_repair
from dayu.fins.pipelines import sec_filing_collection as _sec_filing_collection
from dayu.fins.pipelines import sec_fiscal_fields as _sec_fiscal_fields
from dayu.fins.pipelines import sec_pipeline
from dayu.fins.pipelines import sec_rebuild_workflow as _sec_rebuild_workflow
from dayu.fins.pipelines.sec_6k_rules import _extract_head_text
from dayu.fins.processors.source_text import FinsSourceDecodeError
from dayu.fins.domain.filing_semantics import (
    expand_sec_form_aliases,
    normalize_document_quality,
    normalize_financial_data_quality,
    normalize_fiscal_period,
    parse_sec_form_filter_value,
    parse_sec_form_type,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.pipelines.sec_download_event_mapping import DownloadFileResult
from dayu.fins.pipelines.sec_pipeline import (
    SEC_PIPELINE_DOWNLOAD_VERSION,
    SecPipeline as _SecPipeline,
)
from dayu.fins.pipelines.sec_sc13_filtering import SC13_FORMS as _SC13_FORMS, SC13_RETRY_MAX as _SC13_RETRY_MAX
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    SourceIntegrityClassification,
    SourceIntegrityPreflightError,
    SourceIntegrityPreflightReason,
    SourceIntegrityReason,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.repository_protocols import (
    ProcessedDocumentRepositoryProtocol,
    SourceDocumentRepositoryProtocol,
    SourceSnapshotProtocol,
)
from dayu.fins.ticker_normalization import build_company_ticker_identity, normalize_ticker
from dayu.documents.processors.processor_registry import ProcessorRegistry


@dataclass(frozen=True, slots=True)
class _FiscalXbrlResult:
    """测试用最小 XBRL fiscal 投影。"""

    fiscal_year: int
    fiscal_period: str
    entity_info: dict[str, str]


@dataclass(slots=True)
class _XbrlQueryFixtureProcessor:
    """返回预设 XBRL facts payload 的 fiscal processor。"""

    payload: dict[str, JsonValue] | RuntimeError

    def query_xbrl_facts(self, *, concepts: list[str]) -> dict[str, JsonValue]:
        """返回预设 facts payload 或抛出预设异常。

        Args:
            concepts: consumer 请求的 XBRL concepts。

        Returns:
            预设 facts payload。

        Raises:
            RuntimeError: 当前查询配置为失败时抛出。
        """

        del concepts
        if isinstance(self.payload, RuntimeError):
            raise self.payload
        return self.payload


class _NeverCancelled:
    """测试用取消检查器。"""

    def __call__(self) -> bool:
        """始终返回未取消。"""

        return False


def test_collect_filings_normalizes_sec_xsl_primary_document_path() -> None:
    """SEC XSL 展示路径应在 filing 收集 owner 处投影为归档文件名。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 收集结果仍携带路径分隔符或 filing 字段漂移时抛出。
    """

    records: dict[str, _sec_filing_collection.FilingRecord] = {}
    accession_number = "0002100119-26-000139"

    _sec_filing_collection.collect_filings_from_table(
        records=records,
        table={
            "form": ["SCHEDULE 13G"],
            "filingDate": ["2026-04-29"],
            "reportDate": [""],
            "accessionNumber": [accession_number],
            "primaryDocument": ["xslSCHEDULE_13G_X02/primary_doc.xml"],
            "fileNumber": ["005-33632"],
        },
        form_windows={"SC 13G": dt.date(2026, 1, 1)},
        end_date=dt.date(2026, 12, 31),
    )

    filing = records[accession_number]
    assert filing.form_type == "SC 13G"
    assert filing.primary_document == "primary_doc.xml"


def test_normalize_sec_primary_document_preserves_single_filename() -> None:
    """普通 SEC 单文件名应保持原值。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: helper 改写合法单文件名时抛出。
    """

    assert _sec_filing_collection._normalize_sec_primary_document_name("aapl-20240928.htm") == "aapl-20240928.htm"


@pytest.mark.parametrize(
    "value",
    (
        "",
        " ",
        "/primary_doc.xml",
        "xsl/primary_doc.xml/",
        "xsl\\primary_doc.xml",
        "xsl/./primary_doc.xml",
        "xsl/../primary_doc.xml",
        "xsl//primary_doc.xml",
        "C:primary_doc.xml",
        "C:/primary_doc.xml",
        "xsl/C:/primary_doc.xml",
        None,
    ),
)
def test_normalize_sec_primary_document_rejects_invalid_path_syntax(
    value: JsonValue,
) -> None:
    """非法 SEC 主文档路径必须在 filing 收集 owner 处失败关闭。

    Args:
        value: 待验证的 SEC primaryDocument 值。

    Returns:
        无。

    Raises:
        AssertionError: 非法路径被降成看似合法文件名时抛出。
    """

    with pytest.raises(ValueError, match="SEC primaryDocument"):
        _sec_filing_collection._normalize_sec_primary_document_name(value)


class _RollbackOutcomeBatchingRepository(FsBatchingRepository):
    """记录 SEC rebuild rollback，并可在真实 rollback 后注入次级失败。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        rollback_error: BaseException | None,
    ) -> None:
        """初始化 rollback 结果仓储。

        Args:
            workspace_root: 测试工作区根目录。
            repository_set: 与 source/processed wrapper 共享的 repository set。
            rollback_error: 真实 rollback 后需要抛出的次级异常；`None` 表示成功。

        Returns:
            无。

        Raises:
            OSError: 仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.rollback_error = rollback_error
        self.rollback_calls = 0

    def rollback_batch(self, batch: BatchToken) -> None:
        """执行并记录一次真实 rollback，随后按配置抛出次级异常。

        Args:
            batch: 当前 shared core 登记的 open batch capability。

        Returns:
            未配置次级异常时不返回业务值。

        Raises:
            BaseException: 配置的 rollback 次级异常。
            OSError: 真实 rollback 失败时抛出。
            ValueError: batch capability 非法时抛出。
        """

        self.rollback_calls += 1
        super().rollback_batch(batch)
        if self.rollback_error is not None:
            raise self.rollback_error


@dataclass(slots=True)
class _SecPhaseBMutationCalls:
    """记录 SEC Phase B UNSAFE gate 前后的 mutation 调用次数。"""

    begin: int = 0
    staged_classify: int = 0
    reset: int = 0
    blob: int = 0
    commit: int = 0
    rollback: int = 0


class _RebuildUpdateFailure:
    """在 SEC rebuild source update owner 边界抛出指定异常。"""

    def __init__(self, operation_error: BaseException) -> None:
        """保存需要原样抛出的 operation/cancellation 异常。

        Args:
            operation_error: source update 时抛出的主异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.operation_error = operation_error

    def __call__(
        self,
        request: FilingUpdateRequest,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> None:
        """接收真实 rebuild mutation 输入后抛出预置主异常。

        Args:
            request: SEC rebuild 构造的完整 filing update 请求。
            source_kind: filing source kind。
            batch: caller-owned batch capability。

        Returns:
            不返回；始终抛出预置异常。

        Raises:
            BaseException: 初始化时提供的 operation/cancellation 异常。
        """

        del request, source_kind, batch
        raise self.operation_error


def _sec_rebuild_previous_meta() -> dict[str, JsonValue]:
    """返回触发 SEC rebuild mutation 的最小完成态 meta。

    Args:
        无。

    Returns:
        包含 form、日期、fingerprint 与单文件 manifest 的 source meta。

    Raises:
        无。
    """

    return {
        "internal_document_id": "0000000000-25-000001",
        "form_type": "10-K",
        "filing_date": "2025-02-01",
        "report_date": "2024-12-31",
        "primary_document": "report.htm",
        "source_fingerprint": "published-fingerprint",
        "files": [{"name": "report.htm"}],
    }


def test_sec_6k_preview_rejects_invalid_utf8() -> None:
    """6-K preview 遇到非法 UTF-8 时应 typed fail，不得返回删字文本。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 非法 bytes 未触发 typed decode failure 时抛出。
    """

    with pytest.raises(FinsSourceDecodeError) as error_info:
        _extract_head_text(b"valid\xffinvalid", max_lines=10)

    assert "\\xff" not in str(error_info.value)
    assert isinstance(error_info.value.__cause__, UnicodeDecodeError)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("", "NO_MATCH"),
        ("   \n\t", "NO_MATCH"),
        ("Company will announce second quarter results next week.", "EXCLUDE_NON_QUARTERLY"),
        (
            "Notice of board meeting to consider and approve unaudited financial results for the quarter.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        (
            "Results for announcement to the market. Earnings release and Appendix 4E.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Response to ASX aware letter from ASX compliance.", "EXCLUDE_NON_QUARTERLY"),
        ("Operating results for June 2025. Contents: monthly sales.", "EXCLUDE_NON_QUARTERLY"),
        (
            "Preliminary expected financial results are subject to revision.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        (
            "Management will present at the investor conference; presentation slides are attached.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Annual general meeting voting results.", "EXCLUDE_NON_QUARTERLY"),
        (
            "Consolidated financial statements for the years ended December 31. "
            "Report of independent registered public accounting firm.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        (
            "Group reporting changes and segmental reporting data pack in advance of the publication "
            "of the earnings release.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Transcript of the earnings call.", "EXCLUDE_NON_QUARTERLY"),
        ("Appendix 3A.1 - Notification of dividend / distribution.", "EXCLUDE_NON_QUARTERLY"),
        ("Transaction in own shares.", "EXCLUDE_NON_QUARTERLY"),
        (
            "Minutes of the Board of Directors Meeting to approve the financial statements.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Update Note scheduled to be published on 1 August.", "EXCLUDE_NON_QUARTERLY"),
        (
            "In response to the official letter, Dear Sirs, regarding the news article.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Operating statistics: production ounces and reporting method.", "EXCLUDE_NON_QUARTERLY"),
        (
            "Investor day provided an update on the company's business and reaffirmed guidance.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Presentation for the Mining Forum with forward-looking statements.", "EXCLUDE_NON_QUARTERLY"),
        (
            "Adjustment to exercise price of convertible senior notes.",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Our strategy agenda, Q & A and summary and conclusions.", "EXCLUDE_NON_QUARTERLY"),
        ("Trading statement: will publish financial results.", "EXCLUDE_NON_QUARTERLY"),
        ("Operating update: production per metal and guidance.", "EXCLUDE_NON_QUARTERLY"),
        (
            "TCOM Announces Second Quarter 2025 Unaudited Financial Results.",
            "RESULTS_RELEASE",
        ),
        (
            "RECONCILIATION BETWEEN U.S. GAAP AND IFRS.",
            "IFRS_RECON",
        ),
        (
            "xbrli: iso4217: ifrs-full: 2025Q1true 2025-01-012025-03-31",
            "RESULTS_RELEASE",
        ),
        ("Investor presentation for an investor meeting.", "NO_MATCH"),
    ],
)
def test_sec_6k_classification_owner_covers_business_signal_matrix(
    content: str,
    expected: str,
) -> None:
    """6-K 分类真源应区分结果正文、治理材料、运营更新与中性材料。

    Args:
        content: 待分类的最小业务文本。
        expected: 预期稳定分类。

    Returns:
        无。

    Raises:
        AssertionError: 分类真源与业务信号不一致时抛出。
    """

    assert _sec_6k_rules._classify_6k_text(content) == expected


def test_sec_6k_candidate_owner_uses_type_filename_and_positive_classification() -> None:
    """6-K 候选 owner 应统一使用类型、文件名优先级和正向分类选择正文。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 候选收集、排序或正向选择漂移时抛出。
    """

    entries: list[dict[str, JsonValue]] = [
        {"uri": "https://example.com/cover.htm", "type": "6-K"},
        {"name": "release.htm", "sec_document_type": "EX-99.1"},
        {"name": "release.htm", "sec_document_type": ""},
        {"name": "ignored.pdf", "sec_document_type": "EX-99.2"},
    ]

    assert _sec_6k_rules._infer_filename_from_uri("") == ""
    assert _sec_6k_rules._infer_filename_from_uri("https://example.com/path/cover.htm") == "cover.htm"
    assert _sec_6k_rules._collect_6k_candidate_entries(entries, "cover.htm") == [
        ("cover.htm", "6-K"),
        ("release.htm", "EX-99.1"),
    ]
    assert _sec_6k_rules._select_6k_target_name(entries, "cover.htm") == "release.htm"
    with pytest.raises(ValueError, match="文件列表为空"):
        _sec_6k_rules._select_6k_target_name([], "")

    diagnoses = [
        _sec_6k_rules._SixKCandidateDiagnosis(
            filename="cover.htm",
            filename_priority=3,
            classification="EXCLUDE_NON_QUARTERLY",
            is_primary_document=True,
        ),
        _sec_6k_rules._SixKCandidateDiagnosis(
            filename="release-b.htm",
            filename_priority=1,
            classification="RESULTS_RELEASE",
            is_primary_document=False,
        ),
        _sec_6k_rules._SixKCandidateDiagnosis(
            filename="release-a.htm",
            filename_priority=1,
            classification="IFRS_RECON",
            is_primary_document=False,
        ),
    ]
    selected = _sec_6k_rules._select_best_positive_6k_candidate(diagnoses)
    assert selected is not None
    assert selected.filename == "release-a.htm"
    assert _sec_6k_rules._select_best_positive_6k_candidate(diagnoses[:1]) is None

    remote_files = [
        RemoteFileDescriptor(
            name="release.htm",
            source_url="https://example.com/release.htm",
            http_etag=None,
            http_last_modified=None,
            remote_size=1,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
        RemoteFileDescriptor(
            name="issuer-2025_htm.xml",
            source_url="https://example.com/issuer-2025_htm.xml",
            http_etag=None,
            http_last_modified=None,
            remote_size=1,
            http_status=200,
        ),
    ]
    assert _sec_6k_rules._has_6k_exhibit_candidate(remote_files) is True
    assert _sec_6k_rules._has_6k_xbrl_instance(remote_files) is True
    assert _sec_6k_rules._remote_files_have_xbrl_instance(remote_files) is True


class _RecordingSecPipelineForAdapter:
    """仅覆盖 SEC adapter 所需面的测试 pipeline。"""

    def __init__(self, workspace_root: Path, document_id: str) -> None:
        """初始化测试 pipeline。

        Args:
            workspace_root: 测试工作区根目录。
            document_id: adapter 摘要中返回的已写入文档 ID。

        Returns:
            无。

        Raises:
            OSError: processed 仓储初始化失败时抛出。
        """

        repository_set = build_fs_repository_set(workspace_root=workspace_root)
        self._batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
        self._processed_repository = FsProcessedDocumentRepository(
            workspace_root,
            repository_set=repository_set,
        )
        self._source_repository = FsSourceDocumentRepository(
            workspace_root,
            repository_set=repository_set,
        )
        self.document_id = document_id
        self.recorded_rebuild_values: list[bool] = []

    @property
    def source_repository(self) -> SourceDocumentRepositoryProtocol:
        """返回测试 pipeline 使用的 source repository。

        Returns:
            source repository。

        Raises:
            无。
        """

        return self._source_repository

    async def download_stream(
        self,
        ticker: str,
        form_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        overwrite: bool = False,
        rebuild: bool = False,
        *,
        start_is_explicit: bool,
        cancel_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloadEvent]:
        """记录 OLD rebuild 参数并返回完成事件。

        Args:
            ticker: 股票代码。
            form_type: 表单过滤。
            start_date: 起始披露日期。
            end_date: 结束披露日期。
            overwrite: 是否覆盖。
            rebuild: OLD 本地 rebuild 标记。
            start_is_explicit: 起始日期是否来自调用方显式输入。
            cancel_checker: 取消检查器。

        Yields:
            单个完成事件。

        Raises:
            无。
        """

        del start_is_explicit, cancel_checker
        self.recorded_rebuild_values.append(rebuild)
        form_values: list[JsonValue] = [] if form_type is None else [item for item in form_type.split(",")]
        filters: dict[str, JsonValue] = {
            "forms": form_values,
            "start_date": start_date,
            "end_date": end_date,
            "overwrite": overwrite,
            "rebuild": rebuild,
        }
        result: sec_pipeline.SecPipelineDownloadResult = {
            "pipeline": "sec_download",
            "action": "download",
            "status": "ok",
            "ticker": ticker,
            "market_profile": {},
            "filters": filters,
            "warnings": [],
            "filings": [
                {
                    "document_id": self.document_id,
                    "status": "skipped",
                    "reason_code": "already_downloaded_complete",
                    "form_type": "10-K",
                    "filing_date": "2024-08-01",
                    "report_date": "2024-06-30",
                }
            ],
            "summary": {
                "total": 1,
                "downloaded": 1,
                "skipped": 0,
                "rejected": 0,
                "failed": 0,
                "elapsed_ms": 0,
                "reused_downloads": 0,
                "converted": 0,
            },
        }
        yield DownloadEvent(
            event_type=DownloadEventType.PIPELINE_COMPLETED,
            ticker=ticker,
            payload={"result": cast(JsonValue, result)},
        )


def _require_json_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    """断言 JSON 值是对象并返回只读 mapping。"""

    assert isinstance(value, Mapping)
    return value


def _require_json_list(value: JsonValue) -> list[JsonValue]:
    """断言 JSON 值是数组并返回 list。"""

    assert isinstance(value, list)
    return value


def test_sec_pipeline_rejection_helpers_consume_typed_registry() -> None:
    """SEC pipeline 拒绝 helper 应写入并消费 typed registry 条目。"""

    registry: dict[str, DownloadRejectionEntry] = {}
    document_id = "fil_0000000000-25-000101"

    sec_pipeline._record_rejection(
        registry=registry,
        document_id=document_id,
        reason="6k_filtered",
        category="EXCLUDE_NON_QUARTERLY",
        form_type="6-K",
        filing_date="2025-01-02",
    )

    assert registry[document_id] == DownloadRejectionEntry(
        document_id=document_id,
        reason="6k_filtered",
        category="EXCLUDE_NON_QUARTERLY",
        form_type="6-K",
        filing_date="2025-01-02",
        download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
    )
    assert sec_pipeline._is_rejected(registry, document_id, overwrite=False) is True
    assert sec_pipeline._is_rejected(registry, document_id, overwrite=True) is False
    registry[document_id] = DownloadRejectionEntry(
        document_id=document_id,
        reason="6k_filtered",
        category="EXCLUDE_NON_QUARTERLY",
        form_type="6-K",
        filing_date="2025-01-02",
        download_version="legacy-download-version",
    )
    assert sec_pipeline._is_rejected(registry, document_id, overwrite=False) is False


class StubDownloader:
    """用于测试的下载器桩。"""

    def __init__(
        self,
        submissions: dict[str, JsonValue],
        remote_files: list[RemoteFileDescriptor],
        download_results: list[DownloadFileResult],
        content_by_name: Optional[dict[str, bytes]] = None,
        browse_entries: Optional[list[BrowseEdgarFiling]] = None,
        primary_documents: Optional[dict[str, str]] = None,
        sc13_roles_by_accession: Optional[dict[str, Optional[tuple[str, str]]]] = None,
    ) -> None:
        """初始化下载器桩。

        Args:
            submissions: submissions JSON。
            remote_files: 远端文件描述列表。
            download_results: download_files 返回值。

        Returns:
            无。

        Raises:
            无。
        """

        self._submissions = submissions
        self._remote_files = remote_files
        self._download_results = download_results
        self._content_by_name = content_by_name or {}
        self._browse_entries = browse_entries or []
        self._primary_documents = primary_documents or {}
        self._sc13_roles_by_accession = sc13_roles_by_accession or {}
        self.download_files_called = False
        self.list_filing_files_call_count = 0
        self.fetch_file_calls: list[str] = []
        self.browse_calls: list[str] = []
        self.sc13_role_calls: list[str] = []

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """配置参数（占位）。

        Args:
            user_agent: User-Agent。
            sleep_seconds: 间隔秒数。
            max_retries: 重试次数。

        Returns:
            无。

        Raises:
            无。
        """

        return None

    def resolve_company(
        self,
        ticker: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[str, str, str]:
        """返回固定公司信息。

        Args:
            ticker: 股票代码。
            cancellation_checker: 可选取消检查器。

        Returns:
            `(cik, company_name, cik10)`。

        Raises:
            无。
        """

        del ticker, cancellation_checker
        return ("320193", "Test Inc.", "0000320193")

    def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """返回固定 submissions。

        Args:
            cik10: 10 位 CIK。
            cancellation_checker: 可选取消检查器。

        Returns:
            submissions JSON。

        Raises:
            无。
        """

        del cik10, cancellation_checker
        return self._submissions

    def list_filing_files(
        self,
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool = True,
        include_exhibits: bool = True,
        include_http_metadata: bool = True,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[RemoteFileDescriptor]:
        """返回固定远端文件列表。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            primary_document: primary 文件名。
            form_type: form。
            include_xbrl: 是否含 XBRL。
            include_exhibits: 是否含 exhibits。
            include_http_metadata: 是否拉取 HTTP 元数据。
            cancellation_checker: 可选取消检查器。

        Returns:
            远端文件描述列表。

        Raises:
            无。
        """

        self.list_filing_files_call_count += 1
        del (
            cik,
            accession_no_dash,
            primary_document,
            form_type,
            include_xbrl,
            include_exhibits,
            include_http_metadata,
            cancellation_checker,
        )
        return self._remote_files

    def download_files(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[DownloadFileResult]:
        """模拟下载并返回文件元数据。

        Args:
            remote_files: 远端文件列表。
            overwrite: 是否覆盖。
            store_file: 文件存储回调。
            existing_files: 既有文件映射。
            primary_document: 主文档文件名。
            cancellation_checker: 可选取消检查器。

        Returns:
            下载结果列表。

        Raises:
            无。
        """

        self.download_files_called = True
        del remote_files, overwrite, existing_files, primary_document, cancellation_checker
        results: list[DownloadFileResult] = []
        for item in self._download_results:
            name = str(item.get("name", ""))
            payload = self._content_by_name.get(name, f"dummy:{name}".encode("utf-8"))
            if item.get("status") == "downloaded":
                file_meta = store_file(name, BytesIO(payload), batch=batch)
                enriched = dict(item)
                enriched["file_meta"] = file_meta
                results.append(enriched)
            else:
                results.append(item)
        return results

    async def prefetch_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        *,
        allow_not_modified: bool,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[_PrefetchEvent]:
        """按固定测试结果产生 storage-neutral typed prefetch variants。

        Args:
            remote_files: 远端 descriptors。
            allow_not_modified: 是否允许 304；测试按固定结果投影。
            existing_files: 既有文件映射。
            primary_document: 主文档名。
            cancellation_checker: 可选取消检查器。

        Yields:
            started 与固定终态 prefetch variants。

        Raises:
            无。
        """

        del allow_not_modified, existing_files, primary_document, cancellation_checker
        self.download_files_called = True
        descriptors = {item.name: item for item in remote_files}
        for item in self._download_results:
            name = str(item.get("name", ""))
            descriptor = descriptors.get(name)
            if descriptor is None:
                base = remote_files[0]
                descriptor = RemoteFileDescriptor(
                    name=name,
                    source_url=str(item.get("source_url") or base.source_url),
                    http_etag=base.http_etag,
                    http_last_modified=base.http_last_modified,
                    remote_size=base.remote_size,
                    http_status=base.http_status,
                )
            yield _PrefetchStarted(descriptor=descriptor)
            status = item.get("status")
            if status == "downloaded":
                payload = self._content_by_name.get(name, f"dummy:{name}".encode())
                yield _PrefetchedFile(
                    descriptor=descriptor,
                    http_status=descriptor.http_status or 200,
                    content=payload,
                )
            elif status == "skipped":
                yield _PrefetchSkipped(
                    descriptor=descriptor,
                    http_status=304,
                    reason_code="not_modified",
                    reason_message="远端文件未修改，跳过重新下载",
                )
            else:
                reason = str(item.get("reason_message") or "")
                yield _PrefetchFailed(
                    descriptor=descriptor,
                    http_status=descriptor.http_status,
                    reason_code=str(item.get("reason_code") or "download_failed"),
                    reason_message=reason,
                    error=reason,
                )

    def materialize_prefetched_event(
        self,
        event: _PrefetchEvent,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
    ) -> DownloaderEvent:
        """复用 production 唯一 materializer 处理测试 prefetch variant。

        Args:
            event: typed prefetch variant。
            store_file: 真实 test storage callback。
            batch: 真实 open batch capability。

        Returns:
            production mapping 产生的 downloader event。

        Raises:
            OSError: test storage callback 失败时抛出。
            ValueError: batch 非法时抛出。
        """

        return SecDownloader.materialize_prefetched_event(
            cast(SecDownloader, self),
            event,
            store_file,
            batch=batch,
        )

    async def download_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """按真实 downloader callback contract 投影固定文件结果。

        Args:
            remote_files: 远端文件列表。
            overwrite: 是否覆盖。
            store_file: invocation-time 显式接收 batch 的存储回调。
            batch: caller-owned batch capability。
            existing_files: 既有文件映射。
            primary_document: 主文档文件名。
            cancellation_checker: 可选取消检查器。

        Yields:
            每个文件的 started 与终态事件。

        Raises:
            OSError: store callback 失败时传播。
        """

        results = self.download_files(
            remote_files,
            overwrite,
            store_file,
            batch=batch,
            existing_files=existing_files,
            primary_document=primary_document,
            cancellation_checker=cancellation_checker,
        )
        for item in results:
            name = str(item.get("name", ""))
            source_url = str(item.get("source_url", ""))
            yield DownloaderEvent(
                event_type="file_download_started",
                name=name,
                source_url=source_url,
                http_etag=str(item.get("http_etag") or "") or None,
                http_last_modified=str(item.get("http_last_modified") or "") or None,
                http_status=None,
            )
            status = str(item.get("status", "failed"))
            raw_file_meta = item.get("file_meta")
            file_meta = raw_file_meta if isinstance(raw_file_meta, FileObjectMeta) else None
            raw_http_status = item.get("http_status")
            http_status = (
                raw_http_status if isinstance(raw_http_status, int) and not isinstance(raw_http_status, bool) else None
            )
            if status == "downloaded":
                event_type = "file_downloaded"
            elif status == "skipped":
                event_type = "file_skipped"
            else:
                event_type = "file_failed"
            yield DownloaderEvent(
                event_type=event_type,
                name=name,
                source_url=source_url,
                http_etag=str(item.get("http_etag") or "") or None,
                http_last_modified=str(item.get("http_last_modified") or "") or None,
                http_status=http_status,
                file_meta=file_meta,
                reason_code=str(item.get("reason_code") or "") or None,
                reason_message=str(item.get("reason_message") or "") or None,
                error=str(item.get("error") or "") or None,
            )

    def fetch_file_bytes(
        self,
        url: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> bytes:
        """模拟预下载文件内容。

        Args:
            url: 文件 URL。
            cancellation_checker: 可选取消检查器。

        Returns:
            文件内容字节。

        Raises:
            无。
        """

        del cancellation_checker
        self.fetch_file_calls.append(url)
        filename = url.rsplit("/", 1)[-1]
        return self._content_by_name.get(filename, f"prefetch:{filename}".encode("utf-8"))

    def fetch_browse_edgar_filenum(
        self,
        filenum: str,
        count: int = 100,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[BrowseEdgarFiling]:
        """模拟 browse-edgar 拉取。

        Args:
            filenum: filenum。
            count: 拉取条数上限。
            cancellation_checker: 可选取消检查器。

        Returns:
            filings 列表。

        Raises:
            无。
        """

        del count, cancellation_checker
        self.browse_calls.append(filenum)
        return self._browse_entries

    def resolve_primary_document(
        self,
        cik: str,
        accession_no_dash: str,
        form_type: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> str:
        """模拟解析 primary_document。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            form_type: form。

        Returns:
            文件名。

        Raises:
            无。
        """

        del cancellation_checker
        key = f"{cik}:{accession_no_dash}:{form_type}"
        return self._primary_documents.get(key, "primary.htm")

    def fetch_sc13_party_roles(
        self,
        archive_cik: str,
        accession_number: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Optional[Sc13PartyRoles]:
        """模拟解析 SC13 方向角色。

        Args:
            archive_cik: archive CIK。
            accession_number: accession。

        Returns:
            方向角色对象或 `None`。

        Raises:
            无。
        """

        del archive_cik, cancellation_checker
        self.sc13_role_calls.append(accession_number)
        if accession_number in self._sc13_roles_by_accession:
            role_pair = self._sc13_roles_by_accession[accession_number]
            if role_pair is None:
                return None
            filed_by_cik, subject_cik = role_pair
            return Sc13PartyRoles(filed_by_cik=filed_by_cik, subject_cik=subject_cik)
        # 默认保留：模拟“别人持股当前 ticker(320193)”。
        return Sc13PartyRoles(filed_by_cik="999999", subject_cik="320193")


class StreamStubDownloader(StubDownloader):
    """带流式文件事件的下载器桩。"""

    async def download_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: StoreDownloadedFile,
        *,
        batch: BatchToken,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """模拟流式下载并在每个文件结果前产出 started 事件。

        Args:
            remote_files: 远端文件列表。
            overwrite: 是否覆盖。
            store_file: 文件存储回调。
            existing_files: 既有文件映射。
            primary_document: 主文档文件名。
            cancellation_checker: 可选取消检查器。

        Yields:
            文件 started 事件与终态文件事件。

        Raises:
            无。
        """

        self.download_files_called = True
        del remote_files, overwrite, existing_files, primary_document, cancellation_checker
        for item in self._download_results:
            name = str(item.get("name", ""))
            source_url = str(item.get("source_url", ""))
            http_etag = str(item.get("http_etag", "")) or None
            http_last_modified = str(item.get("http_last_modified", "")) or None
            yield DownloaderEvent(
                event_type="file_download_started",
                name=name,
                source_url=source_url,
                http_etag=http_etag,
                http_last_modified=http_last_modified,
                http_status=200,
            )
            if item.get("status") == "downloaded":
                payload = self._content_by_name.get(name, f"dummy:{name}".encode("utf-8"))
                file_meta = store_file(name, BytesIO(payload), batch=batch)
                yield DownloaderEvent(
                    event_type="file_downloaded",
                    name=name,
                    source_url=source_url,
                    http_etag=http_etag,
                    http_last_modified=http_last_modified,
                    http_status=200,
                    file_meta=file_meta,
                )
                continue
            yield DownloaderEvent(
                event_type="file_failed",
                name=name,
                source_url=source_url,
                http_etag=http_etag,
                http_last_modified=http_last_modified,
                http_status=500,
                reason_code=str(item.get("reason_code", "download_error")),
                reason_message=str(item.get("reason_message", "download failed")),
                error=str(item.get("error", "download failed")),
            )


class BarrierPrefetchDownloader(StubDownloader):
    """用 Event 精确控制 Phase A prefetch 与 writer publication 顺序的测试下载器。"""

    def __init__(
        self,
        *,
        role: Literal["first", "second"],
        submissions: dict[str, JsonValue],
        remote_files: list[RemoteFileDescriptor],
        download_results: list[DownloadFileResult],
        first_prefetch_payload: bytes,
        retry_payload: bytes,
        second_prefetch_complete: Event,
        first_source_committed: Event,
    ) -> None:
        """初始化 deterministic prefetch barrier。

        Args:
            role: first writer 或 second writer。
            submissions: 固定 submissions。
            remote_files: 固定 descriptors。
            download_results: 固定文件结果。
            first_prefetch_payload: 第一轮 payload。
            retry_payload: identity churn 后重试 payload。
            second_prefetch_complete: second 第一轮预取完成事件。
            first_source_committed: first source commit 完成事件。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(
            submissions=submissions,
            remote_files=remote_files,
            download_results=download_results,
        )
        self.role = role
        self.first_prefetch_payload = first_prefetch_payload
        self.retry_payload = retry_payload
        self.second_prefetch_complete = second_prefetch_complete
        self.first_source_committed = first_source_committed
        self.prefetch_rounds = 0

    async def prefetch_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        *,
        allow_not_modified: bool,
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[_PrefetchEvent]:
        """在第二 writer 旧预取完成与第一 writer commit 两处放置 Event barrier。"""

        self.prefetch_rounds += 1
        if self.role == "first":
            ready = await asyncio.to_thread(self.second_prefetch_complete.wait, 5)
            if not ready:
                raise TimeoutError("second writer prefetch barrier 未到达")
        payload = self.retry_payload if self.prefetch_rounds > 1 else self.first_prefetch_payload
        self._content_by_name = {remote_files[0].name: payload}
        async for event in super().prefetch_files_stream(
            remote_files,
            allow_not_modified=allow_not_modified,
            existing_files=existing_files,
            primary_document=primary_document,
            cancellation_checker=cancellation_checker,
        ):
            yield event
        if self.role == "second" and self.prefetch_rounds == 1:
            self.second_prefetch_complete.set()
            committed = await asyncio.to_thread(self.first_source_committed.wait, 5)
            if not committed:
                raise TimeoutError("first writer source commit barrier 未释放")


class RebuildOnlyDownloader:
    """仅用于重建模式测试的下载器桩。"""

    def __init__(self) -> None:
        """初始化调用计数。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.configure_called = False
        self.network_called = False

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """记录配置调用。

        Args:
            user_agent: User-Agent。
            sleep_seconds: 休眠秒数。
            max_retries: 重试次数。

        Returns:
            无。

        Raises:
            无。
        """

        del user_agent, sleep_seconds, max_retries
        self.configure_called = True

    def resolve_company(
        self,
        ticker: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[str, str, str]:
        """重建模式不应触发远端公司解析。

        Args:
            ticker: 股票代码。
            cancellation_checker: 可选取消检查器。

        Returns:
            不返回；被调用时会抛出异常。

        Raises:
            AssertionError: 被调用时抛出。
        """

        del ticker, cancellation_checker
        self.network_called = True
        raise AssertionError("rebuild 模式不应调用 resolve_company")

    def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """重建模式不应触发 submissions 拉取。

        Args:
            cik10: 10 位 CIK。
            cancellation_checker: 可选取消检查器。

        Returns:
            不返回；被调用时会抛出异常。

        Raises:
            AssertionError: 被调用时抛出。
        """

        del cik10, cancellation_checker
        self.network_called = True
        raise AssertionError("rebuild 模式不应调用 fetch_submissions")


_TestDownloader = StubDownloader | RebuildOnlyDownloader | SecDownloader


def _as_sec_downloader(downloader: _TestDownloader) -> SecDownloader:
    """把测试 downloader 显式收窄到生产签名。"""

    return cast(SecDownloader, downloader)


def SecPipeline(
    *,
    workspace_root: Path,
    processor_registry: ProcessorRegistry,
    downloader: Optional[_TestDownloader] = None,
) -> sec_pipeline.SecPipeline:
    """构造测试用 SecPipeline，并在装配边界收窄 stub 类型。"""

    return _SecPipeline(
        workspace_root=workspace_root,
        processor_registry=processor_registry,
        downloader=None if downloader is None else _as_sec_downloader(downloader),
    )


def _build_submissions() -> dict[str, JsonValue]:
    """构建 submissions JSON。

    Args:
        无。

    Returns:
        submissions JSON。

    Raises:
        无。
    """

    return {
        "tickers": ["AAPL", "APC"],
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2025-02-01"],
                "reportDate": ["2024-12-31"],
                "accessionNumber": ["0000000000-25-000001"],
                "primaryDocument": ["sample-10k.htm"],
            },
            "files": [],
        },
    }


def _build_single_filing_submissions(
    *,
    accession_number: str,
    primary_document: str,
) -> dict[str, JsonValue]:
    """构造一个指定 accession identity 的 SEC submissions。

    Args:
        accession_number: 精确 accession number。
        primary_document: 精确主文档名。

    Returns:
        只包含指定 filing 的 submissions JSON。

    Raises:
        无。
    """

    return {
        "tickers": ["AAPL", "APC"],
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2025-02-01"],
                "reportDate": ["2024-12-31"],
                "accessionNumber": [accession_number],
                "primaryDocument": [primary_document],
            },
            "files": [],
        },
    }


def _build_foreign_submissions() -> dict[str, JsonValue]:
    """构建 foreign issuer 的 submissions JSON。

    Args:
        无。

    Returns:
        submissions JSON。

    Raises:
        无。
    """

    return {
        "filings": {
            "recent": {
                "form": ["6-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": ["2024-12-31"],
                "accessionNumber": ["0000000000-25-000101"],
                "primaryDocument": ["sample-6k.htm"],
            },
            "files": [],
        }
    }


def _make_descriptor(etag: str) -> RemoteFileDescriptor:
    """构建远端文件描述。

    Args:
        etag: ETag 值。

    Returns:
        `RemoteFileDescriptor`。

    Raises:
        无。
    """

    return RemoteFileDescriptor(
        name="sample-10k.htm",
        source_url="https://example.com/sample-10k.htm",
        http_etag=etag,
        http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
        remote_size=100,
        http_status=200,
    )


def test_sec_download_filing_provider_evidence_failure_is_unique_failed_row_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """file evidence typed failure 只终止当前 filing，且下一 filing 可完成。"""

    expected = FinsDownloadProviderError(
        source=FinsDownloadSource.SEC,
        transport_category=FinsDownloadTransportCategory.PROTOCOL,
        retryable=False,
        safe_message="SEC 来源响应格式不符合预期",
    )
    downloader = StreamStubDownloader(
        submissions=_build_submissions(),
        remote_files=[_make_descriptor("etag-v1")],
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.invalid/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    original_list = downloader.list_filing_files
    list_calls = 0

    def fail_first_list(
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool = True,
        include_exhibits: bool = True,
        include_http_metadata: bool = True,
        cancellation_checker: Callable[[], bool] | None = None,
    ) -> list[RemoteFileDescriptor]:
        """首次抛 typed evidence failure，第二次返回有效列表。"""

        nonlocal list_calls
        list_calls += 1
        if list_calls == 1:
            raise expected
        return original_list(
            cik=cik,
            accession_no_dash=accession_no_dash,
            primary_document=primary_document,
            form_type=form_type,
            include_xbrl=include_xbrl,
            include_exhibits=include_exhibits,
            include_http_metadata=include_http_metadata,
            cancellation_checker=cancellation_checker,
        )

    monkeypatch.setattr(downloader, "list_filing_files", fail_first_list)
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    begin_calls = 0
    original_begin = pipeline._batching_repository.begin_batch

    def record_begin(ticker: str) -> BatchToken:
        """记录 filing mutation batch 启动次数。"""

        nonlocal begin_calls
        begin_calls += 1
        return original_begin(ticker)

    monkeypatch.setattr(pipeline._batching_repository, "begin_batch", record_begin)
    first = _sec_filing_collection.FilingRecord(
        form_type="10-K",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000001",
        primary_document="sample-10k.htm",
    )
    second = _sec_filing_collection.FilingRecord(
        form_type="10-K",
        filing_date="2025-03-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000002",
        primary_document="sample-10k.htm",
    )
    rejection_registry: dict[str, DownloadRejectionEntry] = {}

    async def collect(filing: _sec_filing_collection.FilingRecord) -> list[DownloadEvent]:
        """直接消费 single-filing owner 事件。"""

        return [
            event
            async for event in pipeline._download_single_filing_stream(
                ticker="AAPL",
                cik="320193",
                filing=filing,
                overwrite=False,
                rejection_registry=rejection_registry,
            )
        ]

    first_events = asyncio.run(collect(first))
    assert [event.event_type for event in first_events] == [DownloadEventType.FILING_FAILED]
    first_result = first_events[0].payload["filing_result"]
    assert isinstance(first_result, dict)
    assert first_result["status"] == "failed"
    assert first_result["reason_code"] == "provider_protocol"
    assert first_result["reason_message"] == expected.safe_message
    assert rejection_registry == {}
    assert begin_calls == 0

    second_events = asyncio.run(collect(second))
    terminal_types = [
        event.event_type
        for event in second_events
        if event.event_type in {DownloadEventType.FILING_COMPLETED, DownloadEventType.FILING_FAILED}
    ]
    assert terminal_types == [DownloadEventType.FILING_COMPLETED]
    assert begin_calls == 1
    assert list_calls == 2


def test_sec_download_filing_6k_preview_provider_failure_stays_local_and_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6-K preview typed failure 形成唯一 FAILED row、固定日志并允许下一 filing。"""

    expected = FinsDownloadProviderError(
        source=FinsDownloadSource.SEC,
        transport_category=FinsDownloadTransportCategory.CONNECTION,
        retryable=True,
        safe_message="无法连接 SEC 来源",
    )
    descriptor = RemoteFileDescriptor(
        name="sample-6k.htm",
        source_url="https://secret.invalid/raw-preview",
        http_etag=None,
        http_last_modified=None,
        remote_size=100,
        http_status=200,
        sec_document_type="6-K",
    )
    downloader = StreamStubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=[descriptor],
        download_results=[
            {
                "name": descriptor.name,
                "status": "downloaded",
                "source_url": descriptor.source_url,
            }
        ],
    )

    def fail_preview(
        url: str,
        cancellation_checker: Callable[[], bool] | None = None,
    ) -> bytes:
        """模拟携带 raw URL/contact 的真实 provider failure。"""

        del url, cancellation_checker
        raise expected from RuntimeError("raw https://secret.invalid/payload contact-canary@example.invalid")

    logs: list[str] = []
    monkeypatch.setattr(downloader, "fetch_file_bytes", fail_preview)
    monkeypatch.setattr(
        sec_pipeline.Log,
        "warn",
        lambda message, *, module: logs.append(f"{module}:{message}"),
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    preview = asyncio.run(
        pipeline._precheck_6k_filter(
            remote_files=[descriptor],
            primary_document=descriptor.name,
            ticker="FUTU",
            document_id="fil_0000000000-25-000101",
        )
    )
    assert preview == (False, "DOWNLOAD_FAILED", descriptor.name)

    six_k = _sec_filing_collection.FilingRecord(
        form_type="6-K",
        filing_date="2025-08-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000101",
        primary_document=descriptor.name,
    )
    later = _sec_filing_collection.FilingRecord(
        form_type="10-K",
        filing_date="2025-09-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000102",
        primary_document=descriptor.name,
    )

    async def collect(filing: _sec_filing_collection.FilingRecord) -> list[DownloadEvent]:
        """直接消费 single-filing owner 事件。"""

        return [
            event
            async for event in pipeline._download_single_filing_stream(
                ticker="FUTU",
                cik="320193",
                filing=filing,
                overwrite=False,
                rejection_registry={},
            )
        ]

    failed_events = asyncio.run(collect(six_k))
    assert [event.event_type for event in failed_events] == [DownloadEventType.FILING_FAILED]
    failed_result = failed_events[0].payload["filing_result"]
    assert isinstance(failed_result, dict)
    assert failed_result["reason_code"] == "6k_prefetch_failed"
    later_events = asyncio.run(collect(later))
    assert later_events[-1].event_type is DownloadEventType.FILING_COMPLETED
    serialized_logs = "\n".join(logs)
    assert "transport_category=connection" in serialized_logs
    assert "secret.invalid" not in serialized_logs
    assert "contact-canary" not in serialized_logs
    assert "raw " not in serialized_logs


def _seed_complete_sec_source(
    *,
    workspace_root: Path,
    ticker: str = "AAPL",
    document_id: str = "fil_0000000000-25-000001",
    source_fingerprint: str = "seed-fingerprint",
    download_version: str | None = SEC_PIPELINE_DOWNLOAD_VERSION,
    http_etag: str = "etag-before",
) -> Path:
    """通过真实 public contract 写入可供 SEC flow 读取的完整 source。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: 事务绑定 ticker。
        document_id: source 文档 ID。
        source_fingerprint: 已发布 source fingerprint。
        download_version: 可选下载版本；``None`` 表示字段缺失。
        http_etag: 已发布文件的 HTTP ETag。

    Returns:
        已发布 source meta 路径。

    Raises:
        OSError: blob、source 或 commit 失败时抛出。
        ValueError: fixture 字段违反 public contract 时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    filename = "sample-10k.htm"
    batch = batching_repository.begin_batch(ticker)
    try:
        file_meta = blob_repository.store_file(
            SourceHandle(
                ticker=ticker,
                document_id=document_id,
                source_kind=SourceKind.FILING.value,
            ),
            filename,
            BytesIO(b"<html>seed</html>"),
            batch=batch,
            content_type="text/html",
        )
        meta: dict[str, JsonValue] = {
            "accession_number": document_id.removeprefix("fil_"),
            "ingest_method": "download",
            "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
            "company_id": "320193",
            "document_version": "v1",
            "source_fingerprint": source_fingerprint,
            "filing_date": "2025-02-01",
            "report_date": "2024-12-31",
            "fiscal_year": 2024,
            "fiscal_period": "FY",
            "amended": False,
        }
        if download_version is not None:
            meta["download_version"] = download_version
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=document_id.removeprefix("fil_"),
                form_type="10-K",
                primary_document=filename,
                meta=meta,
                file_entries=[
                    SourceFileEntry(
                        name=filename,
                        uri=file_meta.uri,
                        etag=file_meta.etag,
                        last_modified=file_meta.last_modified,
                        size=file_meta.size,
                        content_type=file_meta.content_type,
                        sha256=file_meta.sha256,
                        source_url="https://example.com/sample-10k.htm",
                        http_etag=http_etag,
                        http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
                    ).to_dict()
                ],
            ),
            SourceKind.FILING,
            batch=batch,
        )
    except BaseException:
        batching_repository.rollback_batch(batch)
        raise
    batching_repository.commit_batch(batch)
    return _source_meta_path(workspace_root, ticker, document_id)


def _source_meta_path(
    workspace_root: Path,
    ticker: str,
    document_id: str,
) -> Path:
    """通过 storage identity owner 定位 published filing meta。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: exact external ticker。
        document_id: exact external document ID。

    Returns:
        已通过 descriptor 校验的 filing meta 路径。

    Raises:
        ValueError: identity descriptor 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    core = build_fs_repository_set(workspace_root=workspace_root).core
    return core._source_meta_path_for_read(ticker, document_id, SourceKind.FILING)


def _company_meta_path(workspace_root: Path, ticker: str) -> Path:
    """通过 storage identity owner 定位 published company meta。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: exact external ticker。

    Returns:
        已通过 descriptor 校验的 company meta 路径。

    Raises:
        ValueError: identity descriptor 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    core = build_fs_repository_set(workspace_root=workspace_root).core
    return core._company_meta_path_for_read(ticker)


def _filing_manifest_path(workspace_root: Path, ticker: str) -> Path:
    """通过 storage identity owner 定位 published filing manifest。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: exact external ticker。

    Returns:
        filing manifest 路径。

    Raises:
        ValueError: identity descriptor 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    core = build_fs_repository_set(workspace_root=workspace_root).core
    return core._filing_manifest_path_for_read(ticker)


def _processed_meta_path(
    workspace_root: Path,
    ticker: str,
    document_id: str,
) -> Path:
    """通过 storage identity owner 定位 published processed meta。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: exact external ticker。
        document_id: exact external document ID。

    Returns:
        processed meta 路径。

    Raises:
        ValueError: identity descriptor 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    core = build_fs_repository_set(workspace_root=workspace_root).core
    return core._processed_meta_path_for_read(ticker, document_id)


def _download_rejections_path(workspace_root: Path, ticker: str) -> Path:
    """通过 storage identity owner 定位 published rejection registry。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: exact external ticker。

    Returns:
        download rejection registry 路径。

    Raises:
        ValueError: identity descriptor 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    core = build_fs_repository_set(workspace_root=workspace_root).core
    return core._download_rejections_path_for_read(ticker)


def _rejected_meta_path(
    workspace_root: Path,
    ticker: str,
    document_id: str,
) -> Path:
    """通过 storage identity owner 定位 published rejected filing meta。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: exact external ticker。
        document_id: exact external document ID。

    Returns:
        已通过 descriptor 校验的 rejected filing meta 路径。

    Raises:
        ValueError: identity descriptor 不一致时抛出。
        OSError: 文件系统读取失败时抛出。
    """

    core = build_fs_repository_set(workspace_root=workspace_root).core
    return core._rejected_filing_meta_path_for_read(ticker, document_id)


def _seed_complete_6k_source_and_processed(
    *,
    workspace_root: Path,
    ticker: str,
    document_id: str,
) -> None:
    """通过同一真实 batch 写入完整 6-K source、两个 HTML blob 与 processed。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: 事务绑定 ticker。
        document_id: 6-K source 文档 ID。

    Returns:
        无。

    Raises:
        OSError: blob/source/processed 或 commit 写入失败时抛出。
        ValueError: fixture 违反 complete publication contract 时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    source_handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    file_entries: list[dict[str, JsonValue]] = []
    batch = batching_repository.begin_batch(ticker)
    try:
        for filename in ("form6-k.htm", "ex99-1.htm"):
            file_meta = blob_repository.store_file(
                source_handle,
                filename,
                BytesIO(f"<html>{filename}</html>".encode("utf-8")),
                batch=batch,
                content_type="text/html",
            )
            file_entries.append(
                SourceFileEntry(
                    name=filename,
                    uri=file_meta.uri,
                    etag=file_meta.etag,
                    last_modified=file_meta.last_modified,
                    size=file_meta.size,
                    content_type=file_meta.content_type,
                    sha256=file_meta.sha256,
                    source_url=f"https://example.com/{filename}",
                ).to_dict()
            )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=document_id.removeprefix("fil_"),
                form_type="6-K",
                primary_document="form6-k.htm",
                meta={
                    "accession_number": document_id.removeprefix("fil_"),
                    "ingest_method": "download",
                    "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                    "company_id": "320193",
                    "document_version": "v1",
                    "source_fingerprint": "six-k-seed",
                    "filing_date": "2025-02-01",
                    "report_date": "2024-12-31",
                },
                file_entries=file_entries,
            ),
            SourceKind.FILING,
            batch=batch,
        )
        processed_repository.create_processed(
            ProcessedCreateRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=document_id.removeprefix("fil_"),
                source_kind=SourceKind.FILING.value,
                form_type="6-K",
                meta={"reprocess_required": False},
                sections=[],
                tables=[],
            ),
            batch=batch,
        )
    except BaseException:
        batching_repository.rollback_batch(batch)
        raise
    batching_repository.commit_batch(batch)


def _seed_complete_xbrl_source(
    *,
    workspace_root: Path,
    ticker: str,
    document_id: str,
) -> list[dict[str, JsonValue]]:
    """通过真实 batch 发布一组完整 XBRL source 文件。

    Args:
        workspace_root: Fins 工作区根目录。
        ticker: 事务绑定 ticker。
        document_id: source 文档 ID。

    Returns:
        与已发布 source 同版的完整文件描述符列表。

    Raises:
        OSError: blob/source 或 commit 写入失败时抛出。
        ValueError: fixture 违反 complete publication contract 时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    source_handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    file_entries: list[dict[str, JsonValue]] = []
    filenames = (
        "report_htm.xml",
        "report.xsd",
        "report_pre.xml",
        "report_cal.xml",
        "report_def.xml",
        "report_lab.xml",
    )
    batch = batching_repository.begin_batch(ticker)
    try:
        for filename in filenames:
            file_meta = blob_repository.store_file(
                source_handle,
                filename,
                BytesIO(f"<{filename}>payload</{filename}>".encode("utf-8")),
                batch=batch,
                content_type="application/xml",
            )
            file_entries.append(
                SourceFileEntry(
                    name=filename,
                    uri=file_meta.uri,
                    etag=file_meta.etag,
                    last_modified=file_meta.last_modified,
                    size=file_meta.size,
                    content_type=file_meta.content_type,
                    sha256=file_meta.sha256,
                    source_url=f"https://example.com/{filename}",
                ).to_dict()
            )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=document_id.removeprefix("fil_"),
                form_type="10-K",
                primary_document="report_htm.xml",
                meta={
                    "accession_number": document_id.removeprefix("fil_"),
                    "ingest_method": "download",
                    "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                    "company_id": "320193",
                    "document_version": "v1",
                    "source_fingerprint": "xbrl-seed",
                },
                file_entries=file_entries,
            ),
            SourceKind.FILING,
            batch=batch,
        )
    except BaseException:
        batching_repository.rollback_batch(batch)
        raise
    batching_repository.commit_batch(batch)
    return file_entries


def test_sec_pipeline_download_writes_meta_and_manifest(tmp_path: Path) -> None:
    """验证下载成功后写 meta 与 manifest。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StreamStubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    meta_path = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000001")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["files"][0]["uri"].endswith("sample-10k.htm")
    assert meta["fiscal_year"] == 2024
    assert meta["fiscal_period"] == "FY"
    assert meta["source_provider"] == "sec_edgar"
    manifest_path = _filing_manifest_path(tmp_path, "AAPL")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["documents"][0]["document_id"] == "fil_0000000000-25-000001"
    company_meta_path = _company_meta_path(tmp_path, "AAPL")
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker"] == "AAPL"
    assert company_meta["market"] == "US"
    assert company_meta["ticker_aliases"] == ["APC"]


def test_sec_pipeline_download_merges_cli_aliases_with_sec_aliases(tmp_path: Path) -> None:
    """验证 download 会按顺序合并 SEC alias 与 CLI 传入 alias。"""

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    pipeline.download(
        ticker="AAPL",
        overwrite=False,
        ticker_aliases=["AAPL", "AAPL.SW", "APC"],
        start_is_explicit=False,
    )

    company_meta_path = _company_meta_path(tmp_path, "AAPL")
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker_aliases"] == ["APC", "AAPL-SW"]


def test_sec_pipeline_rebuild_local_meta_manifest_without_redownload(tmp_path: Path) -> None:
    """验证 `download --rebuild` 基于本地文件重建 meta/manifest 且不触发远端下载。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    ticker = "AAPL"
    document_id = "fil_0000000000-25-000001"
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(tmp_path, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    batch = batching_repository.begin_batch(ticker)
    file_meta = blob_repository.store_file(
        SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=SourceKind.FILING.value,
        ),
        "sample-10k.htm",
        BytesIO(b"<html>sample</html>"),
        batch=batch,
        content_type="text/html",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id="0000000000-25-000001",
            form_type="10-K",
            primary_document="sample-10k.htm",
            meta={
                "accession_number": "0000000000-25-000001",
                "ingest_method": "download",
                "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                "company_id": "320193",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "report_date": "2024-12-31",
                "filing_date": "2025-02-01",
                "first_ingested_at": "2025-02-02T00:00:00+00:00",
                "document_version": "v7",
                "source_fingerprint": "",
                "amended": False,
                "download_version": "legacy_download_version",
            },
            files=[file_meta],
        ),
        SourceKind.FILING,
        batch=batch,
    )
    processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id="0000000000-25-000001",
            source_kind=SourceKind.FILING.value,
            form_type="10-K",
            meta={"reprocess_required": False},
            sections=[],
            tables=[],
        ),
        batch=batch,
    )
    batching_repository.commit_batch(batch)
    meta_path = _source_meta_path(tmp_path, ticker, document_id)
    manifest_path = _filing_manifest_path(tmp_path, ticker)
    source_handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    source_bytes_before = blob_repository.read_file_bytes(source_handle, "sample-10k.htm")

    downloader = RebuildOnlyDownloader()
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(ticker=ticker, rebuild=True, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    assert result["summary"]["failed"] == 0
    assert bool(result["filters"]["rebuild"]) is True
    assert downloader.network_called is False
    assert downloader.configure_called is False

    rebuilt_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert rebuilt_meta["document_version"] == "v7"
    assert isinstance(rebuilt_meta["source_fingerprint"], str)
    assert rebuilt_meta["source_fingerprint"]
    assert rebuilt_meta["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
    rebuilt_processed_meta = processed_repository.get_processed_meta(ticker, document_id)
    assert rebuilt_processed_meta["reprocess_required"] is False
    assert blob_repository.read_file_bytes(source_handle, "sample-10k.htm") == source_bytes_before

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["documents"]) == 1
    assert manifest["documents"][0]["document_id"] == document_id
    assert manifest["documents"][0]["document_version"] == "v7"
    assert manifest["documents"][0]["form_type"] == "10-K"
    assert manifest["documents"][0]["ingest_method"] == "download"


@pytest.mark.parametrize(
    "cancellation_type",
    (KeyboardInterrupt, SystemExit),
    ids=("keyboard_interrupt", "system_exit"),
)
def test_sec_rebuild_rolls_back_once_and_reraises_cancellation_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cancellation_type: type[KeyboardInterrupt] | type[SystemExit],
) -> None:
    """SEC rebuild commit 前取消必须 rollback 一次并原样传播。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。
        cancellation_type: 本 case 注入的取消异常类型。

    Returns:
        无。

    Raises:
        AssertionError: 取消 identity 被替换、未传播或 rollback 次数不为一时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = _RollbackOutcomeBatchingRepository(
        tmp_path,
        repository_set,
        None,
    )
    source_repository = FsSourceDocumentRepository(
        tmp_path,
        repository_set=repository_set,
    )
    cancellation = cancellation_type("injected rebuild cancellation")
    monkeypatch.setattr(
        source_repository,
        "update_source_document",
        _RebuildUpdateFailure(cancellation),
    )

    with pytest.raises(cancellation_type) as exc_info:
        _sec_rebuild_workflow.rebuild_single_local_filing(
            batching_repository=batching_repository,
            source_repository=source_repository,
            ticker="AAPL",
            document_id="fil_0000000000-25-000001",
            previous_meta=_sec_rebuild_previous_meta(),
            company_meta=None,
            pipeline_download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
        )

    assert exc_info.value is cancellation
    assert exc_info.value.__cause__ is None
    assert batching_repository.rollback_calls == 1


def test_sec_rebuild_operation_and_rollback_failure_preserve_primary_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC rebuild 双失败必须以 operation 为主、rollback 为 cause并只回滚一次。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主异常 identity、cause、note 或 rollback 次数漂移时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    operation_error = OSError("injected rebuild operation failure")
    rollback_error = RuntimeError("injected rebuild rollback failure")
    batching_repository = _RollbackOutcomeBatchingRepository(
        tmp_path,
        repository_set,
        rollback_error,
    )
    source_repository = FsSourceDocumentRepository(
        tmp_path,
        repository_set=repository_set,
    )
    monkeypatch.setattr(
        source_repository,
        "update_source_document",
        _RebuildUpdateFailure(operation_error),
    )

    with pytest.raises(OSError) as exc_info:
        _sec_rebuild_workflow.rebuild_single_local_filing(
            batching_repository=batching_repository,
            source_repository=source_repository,
            ticker="AAPL",
            document_id="fil_0000000000-25-000001",
            previous_meta=_sec_rebuild_previous_meta(),
            company_meta=None,
            pipeline_download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
        )

    assert exc_info.value is operation_error
    assert exc_info.value.__cause__ is rollback_error
    assert exc_info.value.__notes__ == [
        "rollback_batch failed; recovery evidence retained: injected rebuild rollback failure"
    ]
    assert batching_repository.rollback_calls == 1


def test_sec_rebuild_ordinary_failure_with_successful_rollback_returns_failed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC rebuild ordinary operation 失败且 rollback 成功时应保留既有 failed result。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: ordinary failure 被抛出、结果分类漂移或 rollback 次数不为一时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    operation_error = OSError("injected ordinary rebuild failure")
    batching_repository = _RollbackOutcomeBatchingRepository(
        tmp_path,
        repository_set,
        None,
    )
    source_repository = FsSourceDocumentRepository(
        tmp_path,
        repository_set=repository_set,
    )
    monkeypatch.setattr(
        source_repository,
        "update_source_document",
        _RebuildUpdateFailure(operation_error),
    )

    result = _sec_rebuild_workflow.rebuild_single_local_filing(
        batching_repository=batching_repository,
        source_repository=source_repository,
        ticker="AAPL",
        document_id="fil_0000000000-25-000001",
        previous_meta=_sec_rebuild_previous_meta(),
        company_meta=None,
        pipeline_download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
    )

    assert result["status"] == "failed"
    assert result["reason_code"] == "rebuild_write_failed"
    assert result["error"] == "injected ordinary rebuild failure"
    assert operation_error.__cause__ is None
    assert batching_repository.rollback_calls == 1


@pytest.mark.parametrize(
    ("meta", "target_forms", "start_bound", "end_bound", "expected"),
    [
        ({"filing_date": "2025-02-01"}, {"10-K"}, None, None, False),
        ({"form_type": "invalid", "filing_date": "2025-02-01"}, {"10-K"}, None, None, False),
        ({"form_type": "10-Q", "filing_date": "2025-02-01"}, {"10-K"}, None, None, False),
        ({"form_type": "10-K"}, {"10-K"}, dt.date(2025, 1, 1), None, False),
        (
            {"form_type": "10-K", "filing_date": "not-a-date"},
            {"10-K"},
            dt.date(2025, 1, 1),
            None,
            False,
        ),
        (
            {"form_type": "10-K", "filing_date": "2024-12-31"},
            {"10-K"},
            dt.date(2025, 1, 1),
            None,
            False,
        ),
        (
            {"form_type": "10-K", "filing_date": "2025-02-01"},
            {"10-K"},
            None,
            dt.date(2025, 1, 31),
            False,
        ),
        (
            {"form_type": "10-K", "filing_date": "2025-02-01"},
            {"10-K"},
            dt.date(2025, 1, 1),
            dt.date(2025, 2, 28),
            True,
        ),
    ],
)
def test_sec_rebuild_filter_contract(
    meta: dict[str, JsonValue],
    target_forms: set[str] | None,
    start_bound: dt.date | None,
    end_bound: dt.date | None,
    expected: bool,
) -> None:
    """SEC rebuild filter owner 对缺失、非法和边界日期应 fail closed。"""

    assert (
        _sec_rebuild_workflow.passes_rebuild_filters(
            meta=meta,
            target_forms=target_forms,
            start_bound=start_bound,
            end_bound=end_bound,
            parse_sec_form=parse_sec_form_type,
            parse_date=sec_pipeline.parse_date,
        )
        is expected
    )


def test_sec_rebuild_state_preserves_published_fingerprint() -> None:
    """rebuild state owner 应保留既有指纹，且缺席 meta 不得命中当前版本。"""

    assert _sec_download_state.has_current_download_version(None, SEC_PIPELINE_DOWNLOAD_VERSION) is False
    assert (
        _sec_download_state._resolve_rebuild_source_fingerprint(
            previous_meta={"source_fingerprint": "published-fingerprint"},
            file_entries=[],
        )
        == "published-fingerprint"
    )


def test_sec_pipeline_download_prefers_dei_fiscal_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证下载落盘优先使用 DEI fiscal 字段。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    from dayu.fins.pipelines import sec_fiscal_fields as _sec_fiscal_fields_mod

    monkeypatch.setattr(
        _sec_fiscal_fields_mod,
        "_extract_download_fiscal_from_xbrl",
        lambda **_kwargs: (2023, "FY"),
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    meta_path = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000001")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["fiscal_year"] == 2023
    assert meta["fiscal_period"] == "FY"


def test_sec_fiscal_files_consume_one_storage_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC fiscal 多文件读取必须来自同一份 full snapshot。

    Args:
        tmp_path: 临时工作区根目录。
        monkeypatch: pytest monkeypatch。

    Returns:
        无。

    Raises:
        AssertionError: consumer 重回逐文件仓储读取或资源未清理时抛出。
    """

    from edgar.xbrl import XBRL

    ticker = "AAPL"
    document_id = "fil_0000000000-25-000001"
    file_entries = _seed_complete_xbrl_source(
        workspace_root=tmp_path,
        ticker=ticker,
        document_id=document_id,
    )
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    original_read_snapshot = source_repository.read_source_snapshot
    snapshots: list[SourceSnapshotProtocol] = []
    materialized_paths: list[Path] = []

    def _observe_snapshot_read(
        observed_ticker: str,
        observed_document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """记录真实 storage snapshot 调用并返回原始资源。"""

        snapshot = original_read_snapshot(
            observed_ticker,
            observed_document_id,
            source_kind,
            materialize_files=materialize_files,
        )
        snapshots.append(snapshot)
        return snapshot

    def _forbid_legacy_source_read(source_handle: SourceHandle, filename: str) -> None:
        """禁止 fiscal consumer 退回逐文件 source 读取。"""

        del source_handle, filename
        raise AssertionError("fiscal consumer must use its one snapshot")

    def _fake_xbrl_from_files(
        instance_file: str | Path | None = None,
        schema_file: str | Path | None = None,
        presentation_file: str | Path | None = None,
        calculation_file: str | Path | None = None,
        definition_file: str | Path | None = None,
        label_file: str | Path | None = None,
    ) -> _FiscalXbrlResult:
        """记录解析器看到的同版临时文件并返回确定 fiscal 值。"""

        raw_paths = (
            instance_file,
            schema_file,
            presentation_file,
            calculation_file,
            definition_file,
            label_file,
        )
        materialized_paths.extend(Path(path) for path in raw_paths if path is not None)
        return _FiscalXbrlResult(
            fiscal_year=2024,
            fiscal_period="FY",
            entity_info={},
        )

    monkeypatch.setattr(source_repository, "read_source_snapshot", _observe_snapshot_read)
    monkeypatch.setattr(source_repository, "get_source", _forbid_legacy_source_read)
    monkeypatch.setattr(XBRL, "from_files", staticmethod(_fake_xbrl_from_files))

    fiscal_year, fiscal_period = _sec_fiscal_fields._extract_download_fiscal_from_xbrl(
        source_handle=SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=SourceKind.FILING.value,
        ),
        source_repository=source_repository,
        file_entries=file_entries,
        form_type="10-K",
    )

    assert (fiscal_year, fiscal_period) == (2024, "FY")
    assert len(snapshots) == 1
    assert materialized_paths
    assert all(not path.exists() for path in materialized_paths)
    with pytest.raises(RuntimeError, match="已关闭"):
        snapshots[0].get_primary_source()


def test_sec_fiscal_processed_quality_contract() -> None:
    """fiscal owner 应仅保留 processed 文档质量矩阵。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: processed 质量矩阵发生漂移时抛出。
    """

    assert _sec_fiscal_fields._resolve_processed_quality(True, True, "10-K") == "full"
    assert _sec_fiscal_fields._resolve_processed_quality(False, True, "10-K") == "partial"
    assert _sec_fiscal_fields._resolve_processed_quality(False, False, "10-K") == "fallback"
    assert _sec_fiscal_fields._resolve_processed_quality(True, True, "DEF14A") == "partial"


def test_sec_fiscal_processed_resolution_precedence_and_fallbacks() -> None:
    """processed fiscal 字段应按 source、query、payload、report date 顺序解析。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fiscal precedence 或 form 约束发生漂移时抛出。
    """

    query_processor = _XbrlQueryFixtureProcessor(
        payload={
            "query_params": {"concepts": ["Revenue"]},
            "facts": [{"fiscal_year": 2024, "fiscal_period": "FY"}],
            "data_quality": "xbrl",
        }
    )
    financials_payload: dict[str, JsonValue] = {
        "statements": {
            "income": {
                "periods": [{"fiscal_year": 2023, "fiscal_period": "Q2"}],
            }
        }
    }

    assert _sec_fiscal_fields._resolve_processed_fiscal_fields(
        {"form_type": "10-K", "fiscal_year": 2022, "fiscal_period": "FY"},
        financials_payload,
        query_processor,
    ) == (2022, "FY")
    assert _sec_fiscal_fields._resolve_processed_fiscal_fields(
        {"form_type": "10-K"},
        financials_payload,
        query_processor,
    ) == (2024, "FY")
    assert _sec_fiscal_fields._resolve_processed_fiscal_fields(
        {"form_type": "10-Q", "fiscal_year": 2025},
        financials_payload,
        query_processor,
        allow_xbrl_query=False,
    ) == (2025, "Q2")
    assert _sec_fiscal_fields._resolve_processed_fiscal_fields(
        {"form_type": "20-F", "report_date": "2021-12-31"},
        None,
        None,
    ) == (2021, "FY")
    assert _sec_fiscal_fields._resolve_processed_fiscal_fields(
        {"form_type": "6-K", "report_date": "bad-date"},
        None,
        None,
    ) == (None, None)


def test_sec_fiscal_download_resolution_preserves_existing_business_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """download fiscal 合并只替换文件来源，不改变 DEI 与日期回退规则。

    Args:
        tmp_path: 临时工作区根目录。
        monkeypatch: pytest monkeypatch。

    Returns:
        无。

    Raises:
        AssertionError: download fiscal precedence 发生漂移时抛出。
    """

    source_repository = FsSourceDocumentRepository(tmp_path)
    source_handle = SourceHandle(
        ticker="AAPL",
        document_id="fil_0000000000-25-000001",
        source_kind=SourceKind.FILING.value,
    )
    extracted: tuple[int | None, str | None] = (None, None)

    def _extract_fixture(
        *,
        source_handle: SourceHandle,
        source_repository: FsSourceDocumentRepository,
        file_entries: list[dict[str, JsonValue]],
        form_type: str | None,
    ) -> tuple[int | None, str | None]:
        """返回当前测试场景配置的 DEI fiscal 字段。"""

        del source_handle, source_repository, file_entries, form_type
        return extracted

    monkeypatch.setattr(
        _sec_fiscal_fields,
        "_extract_download_fiscal_from_xbrl",
        _extract_fixture,
    )

    assert _sec_fiscal_fields._resolve_download_fiscal_fields(
        source_handle=source_handle,
        source_repository=source_repository,
        file_entries=[],
        form_type="10-K",
        report_date="2023-12-31",
    ) == (2023, "FY")
    extracted = (2024, "Q3")
    assert _sec_fiscal_fields._resolve_download_fiscal_fields(
        source_handle=source_handle,
        source_repository=source_repository,
        file_entries=[],
        form_type="10-Q",
        report_date="2023-09-30",
    ) == (2024, "Q3")
    extracted = (None, "Q2")
    assert _sec_fiscal_fields._resolve_download_fiscal_fields(
        source_handle=source_handle,
        source_repository=source_repository,
        file_entries=[],
        form_type="10-Q",
        report_date="2023-06-30",
    ) == (2023, "Q2")
    extracted = (2025, None)
    assert _sec_fiscal_fields._resolve_download_fiscal_fields(
        source_handle=source_handle,
        source_repository=source_repository,
        file_entries=[],
        form_type="20-F",
        report_date="2024-12-31",
    ) == (2025, "FY")
    assert _sec_fiscal_fields._resolve_download_fiscal_fields(
        source_handle=source_handle,
        source_repository=source_repository,
        file_entries=[],
        form_type="6-K",
        report_date="2024-12-31",
    ) == (2025, None)


def test_sec_fiscal_helper_contract_matrix() -> None:
    """fiscal helper 应保留 XBRL 选择、解析、归一与 skip 合同。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 任一 fiscal helper owner contract 漂移时抛出。
    """

    file_map = {
        "a_pre.xml": Path("a_pre.xml"),
        "b.xml": Path("b.xml"),
        "c_ins.xml": Path("c_ins.xml"),
        "d.xsd": Path("d.xsd"),
        "filingsummary.xml": Path("filingsummary.xml"),
    }
    assert _sec_fiscal_fields._pick_download_xbrl_file(
        file_map,
        candidates=("_ins.xml",),
    ) == Path("c_ins.xml")
    assert (
        _sec_fiscal_fields._pick_download_xbrl_file(
            file_map,
            candidates=("_missing.xml",),
        )
        is None
    )
    assert _sec_fiscal_fields._pick_download_xbrl_file(
        file_map,
        candidates=("_missing.xml",),
        xml_fallback=True,
    ) == Path("b.xml")
    assert (
        _sec_fiscal_fields._mapping_get_case_insensitive(
            {"DocumentFiscalYearFocus": "2024"},
            ("documentfiscalyearfocus",),
        )
        == "2024"
    )
    assert _sec_fiscal_fields._mapping_get_case_insensitive([], ("missing",)) is None
    assert _sec_fiscal_fields._pick_first_non_empty((None, " ", "FY")) == "FY"
    assert _sec_fiscal_fields._pick_first_non_empty((None, " ")) is None
    assert _sec_fiscal_fields._infer_download_fiscal_fields("10-K", "2024-12-31") == (2024, "FY")
    assert _sec_fiscal_fields._infer_download_fiscal_fields("6-K/A", "2024-12-31") == (None, None)
    assert (
        _sec_fiscal_fields._resolve_fiscal_period_fallback(
            form_type="10-Q",
            fiscal_year=2024,
            fiscal_year_from_report_date=True,
        )
        is None
    )
    assert _sec_fiscal_fields._coerce_optional_int(None) is None
    assert _sec_fiscal_fields._coerce_optional_int(True) is None
    assert _sec_fiscal_fields._coerce_optional_int(2024) == 2024
    assert _sec_fiscal_fields._coerce_optional_int(" ") is None
    assert _sec_fiscal_fields._coerce_optional_int("20x4") is None
    assert _sec_fiscal_fields._normalize_optional_period("q1") == "Q1"
    assert _sec_fiscal_fields._normalize_optional_period("n/a") is None
    assert _sec_fiscal_fields._coerce_year_from_date("2024-12-31") == 2024
    assert _sec_fiscal_fields._coerce_year_from_date("2024") is None
    assert _sec_fiscal_fields._should_skip_financial_extraction(None) is False
    assert _sec_fiscal_fields._should_skip_financial_extraction("DEF14A") is True
    assert _sec_fiscal_fields._should_skip_financial_extraction("SC 13D/A") is True
    assert _sec_fiscal_fields._should_skip_financial_extraction("10-K") is False


def test_sec_fiscal_payload_and_query_extractors_fail_closed() -> None:
    """financials 与 XBRL query extractor 应拒绝非法 shape 并保留有效 fiscal。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: extractor 接受非法 payload 或丢失有效 fiscal 时抛出。
    """

    assert _sec_fiscal_fields._extract_fiscal_from_financials(None) == (None, None)
    assert _sec_fiscal_fields._extract_fiscal_from_financials({"statements": []}) == (None, None)
    assert _sec_fiscal_fields._extract_fiscal_from_financials(
        {
            "statements": {
                "income": {
                    "periods": [None, {"period_end": "2022-12-31", "fiscal_period": "FY"}],
                }
            }
        }
    ) == (2022, "FY")
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(None) == (None, None)
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(
        _XbrlQueryFixtureProcessor(RuntimeError("query failed"))
    ) == (None, None)
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(_XbrlQueryFixtureProcessor({"facts": []})) == (None, None)
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(
        _XbrlQueryFixtureProcessor(
            {
                "query_params": {"concepts": ["Revenue"]},
                "facts": [
                    {"period_end": "2023-12-31"},
                    {"fiscal_year": 2024, "fiscal_period": "Q1"},
                ],
                "data_quality": "xbrl",
            }
        )
    ) == (2024, "Q1")
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(
        _XbrlQueryFixtureProcessor(
            {
                "query_params": {"concepts": ["Revenue"]},
                "facts": [{"period_end": "2021-12-31"}],
                "data_quality": "xbrl",
            }
        )
    ) == (2021, None)


def test_sec_pipeline_skip_when_meta_matches(tmp_path: Path) -> None:
    """验证 meta 指纹一致时跳过下载。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-same")]
    fingerprint = build_source_fingerprint(remote_files)
    _seed_complete_sec_source(
        workspace_root=tmp_path,
        source_fingerprint=fingerprint,
    )
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert result["summary"]["skipped"] == 1
    assert downloader.download_files_called is False
    # 快速预检跳过时不应调用 list_filing_files
    assert downloader.list_filing_files_call_count == 0
    assert result["filings"][0]["skip_reason"] == "already_downloaded_complete"
    assert result["filings"][0]["reason_code"] == "already_downloaded_complete"
    assert "完整下载结果" in str(result["filings"][0]["reason_message"])


def test_sec_pipeline_skip_with_etag_gzip_variant_without_re_download(tmp_path: Path) -> None:
    """验证 ETag `-gzip` 变体不应触发重复下载。"""

    remote_files = [_make_descriptor("etag-same-gzip")]
    _seed_complete_sec_source(
        workspace_root=tmp_path,
        source_fingerprint="legacy-fp",
        http_etag='"etag-same"',
    )
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-same-gzip",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert result["summary"]["skipped"] == 1
    assert result["summary"]["downloaded"] == 0
    assert downloader.download_files_called is False
    assert result["filings"][0]["skip_reason"] == "already_downloaded_complete"
    assert result["filings"][0]["reason_code"] == "already_downloaded_complete"


@pytest.mark.parametrize(
    ("existing_download_version", "expected_status", "expected_skip_reason"),
    [
        (SEC_PIPELINE_DOWNLOAD_VERSION, "skipped", "integrity_complete"),
        ("legacy-download-version", "skipped", "integrity_complete"),
        (None, "skipped", "integrity_complete"),
    ],
)
def test_sec_pipeline_all_files_not_modified_respects_download_version(
    tmp_path: Path,
    existing_download_version: str | None,
    expected_status: str,
    expected_skip_reason: str | None,
) -> None:
    """全文件未修改只能在 current download version 下形成 terminal skip。

    Args:
        tmp_path: pytest 临时目录。
        existing_download_version: 既有 meta 的下载版本；``None`` 表示缺失。
        expected_status: 期望 filing 状态。
        expected_skip_reason: 期望 skip reason；继续 commit 时为 ``None``。

    Returns:
        无。

    Raises:
        AssertionError: version owner 未控制 not-modified skip 时抛出。
    """

    remote_files = [_make_descriptor("etag-same")]
    meta_path = _seed_complete_sec_source(
        workspace_root=tmp_path,
        source_fingerprint="",
        download_version=existing_download_version,
    )
    before_text = meta_path.read_text(encoding="utf-8")
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "skipped",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-same",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)
    after_text = meta_path.read_text(encoding="utf-8")

    assert downloader.download_files_called is False
    assert result["filings"][0]["status"] == expected_status
    assert result["filings"][0].get("skip_reason") == expected_skip_reason
    if expected_skip_reason == "integrity_complete":
        assert result["summary"]["skipped"] == 1
        assert result["summary"]["downloaded"] == 0
        assert before_text == after_text
        assert result["filings"][0]["reason_code"] == "integrity_complete"
        assert "完整" in str(result["filings"][0]["reason_message"])
        return

    assert result["summary"]["skipped"] == 0
    assert result["summary"]["downloaded"] == 1
    assert before_text != after_text
    committed_meta = json.loads(after_text)
    assert committed_meta["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION


def test_sec_pipeline_failed_filing_does_not_write_meta(tmp_path: Path) -> None:
    """验证下载失败时不写 meta。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "failed",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert result["summary"]["failed"] == 1
    meta_path = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000001")
    assert not meta_path.exists()
    assert result["filings"][0]["reason_code"] == "file_download_failed"
    assert result["filings"][0]["reason_message"] == "存在文件下载失败"


def test_sec_pipeline_remote_change_marks_reprocess(tmp_path: Path) -> None:
    """验证远端变更会重拉并标记 processed 需重处理。

    快速预检机制（_can_skip_fast）在 ingest_complete + 版本匹配时会跳过远端比较，
    因此需要 overwrite=True 才能检测到远端变更（设计取舍：避免每次下载都做大量 HEAD 请求）。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files_v1 = [_make_descriptor("etag-v1")]
    fingerprint_v1 = build_source_fingerprint(remote_files_v1)
    meta_path = _seed_complete_sec_source(
        workspace_root=tmp_path,
        source_fingerprint=fingerprint_v1,
    )
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    processed_batch = batching_repository.begin_batch("AAPL")
    processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker="AAPL",
            document_id="fil_0000000000-25-000001",
            internal_document_id="0000000000-25-000001",
            source_kind=SourceKind.FILING.value,
            form_type="10-K",
            meta={"reprocess_required": False},
            sections=[],
            tables=[],
        ),
        batch=processed_batch,
    )
    batching_repository.commit_batch(processed_batch)
    processed_meta_path = _processed_meta_path(
        tmp_path,
        "AAPL",
        "fil_0000000000-25-000001",
    )

    remote_files_v2 = [_make_descriptor("etag-v2")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files_v2,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v2",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    # 非 overwrite 模式下，快速预检会直接跳过（不发远端请求）
    result_skip = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)
    assert result_skip["summary"]["skipped"] == 1
    assert result_skip["summary"]["downloaded"] == 0
    # 快速预检跳过时不应调用 list_filing_files（避免 SEC HEAD 请求）
    assert downloader.list_filing_files_call_count == 0

    # overwrite=True 仅替换当前目标文档，仍使用 previous_meta 递增版本。
    result = pipeline.download(ticker="AAPL", overwrite=True, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    updated_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated_meta["document_version"] == "v2"
    processed_meta = json.loads(processed_meta_path.read_text(encoding="utf-8"))
    # 目标文档替换时若 processed 快照存在，应标记 reprocess_required
    assert processed_meta["reprocess_required"] is True


def test_sec_ordinary_download_keeps_unselected_historical_document(tmp_path: Path) -> None:
    """普通 SEC 下载不得清理本轮未选择的历史 source 文档。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非目标历史文档被删除或目标下载失败时抛出。
    """

    historical_meta_path = _seed_complete_sec_source(
        workspace_root=tmp_path,
        document_id="fil_0000000000-23-000099",
        download_version="legacy-download-version",
    )
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=[_make_descriptor("etag-current")],
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-current",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    assert historical_meta_path.exists()


def test_sec_pipeline_download_parses_year_month_date_inputs(tmp_path: Path) -> None:
    """验证下载入口支持 YYYY/ YYYY-MM/ YYYY-MM-DD 日期输入。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(
        ticker="AAPL",
        start_date="2024",
        end_date="2025-02",
        overwrite=False,
        start_is_explicit=True,
    )

    start_dates = _require_json_mapping(result["filters"]["start_dates"])
    assert start_dates["10-K"] == "2024-01-01"
    assert start_dates["10-Q"] == "2024-01-01"
    assert result["filters"]["end_date"] == "2025-02-28"


def test_sec_pipeline_download_resolves_foreign_issuer_from_submissions(tmp_path: Path) -> None:
    """验证根据 submissions 自动识别 foreign issuer 并写入 company meta。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-v1",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
            sec_document_type="EX-99.1",
        )
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        content_by_name={
            "sample-6k.htm": b"Financial Results and Business Updates\\n",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    forms = _require_json_list(result["filters"]["forms"])
    assert "6-K" in forms
    assert "20-F" in forms
    company_meta_path = _company_meta_path(tmp_path, "TCOM")
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker"] == "TCOM"
    assert company_meta["market"] == "US"


def test_sec_pipeline_filters_6k_excluded(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """验证 6-K 命中排除规则时跳过落盘。

    Args:
        tmp_path: 临时目录。
        caplog: 日志捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            # 分类信号源改为封面文档，此处模拟封面含非季报描述
            "sample-6k.htm": b"FORM 6-K\nEXHIBIT INDEX\nExhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    caplog.set_level(logging.INFO, logger="dayu.fins.FINS.SEC_PIPELINE")

    result = pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    assert result["summary"]["skipped"] == 0
    assert result["summary"]["rejected"] == 1
    assert "美股下载完成: ticker=TCOM total=1 downloaded=0 skipped=0 rejected=1 failed=0" in caplog.text
    assert downloader.download_files_called is True
    meta_path = _source_meta_path(tmp_path, "TCOM", "fil_0000000000-25-000101")
    assert not meta_path.exists()
    rejected_meta_path = _rejected_meta_path(
        tmp_path,
        "TCOM",
        "fil_0000000000-25-000101",
    )
    assert rejected_meta_path.exists()
    rejected_meta = json.loads(rejected_meta_path.read_text(encoding="utf-8"))
    assert rejected_meta["rejection_reason"] == "6k_filtered"
    assert rejected_meta["rejection_category"] == "EXCLUDE_NON_QUARTERLY"
    registry_path = _download_rejections_path(tmp_path, "TCOM")
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    rejected_registry_entry = registry_payload["fil_0000000000-25-000101"]
    assert rejected_registry_entry["document_id"] == "fil_0000000000-25-000101"
    assert rejected_registry_entry["reason"] == "6k_filtered"
    assert rejected_registry_entry["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION


def test_sec_download_adapter_counts_6k_filtered_as_rejected_in_persisted_summary(tmp_path: Path) -> None:
    """验证 SEC adapter persisted summary 会统计 6-K filtered rejected artifact。"""

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "sample-6k.htm": b"FORM 6-K\nEXHIBIT INDEX\nExhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    adapter = sec_pipeline.SecDownloadAdapter(pipeline=pipeline)

    result = adapter.download(
        FinsSourceDownloadAdapterRequest(
            normalized_ticker=normalize_ticker("TCOM"),
            source=FinsDownloadSource.SEC,
            form_types=(),
            date_range=FinsDownloadDateRange(None, None, False, False),
            overwrite_existing=False,
            rebuild_local_artifacts=False,
            cancellation_checker=_NeverCancelled(),
        )
    )

    summary = result.persisted_summary
    assert summary is not None
    assert summary.rejected_count == 1
    assert summary.skipped_count == 0
    assert summary.downloaded_count == 0


def test_sec_download_adapter_summary_classifies_skipped_and_rejected_exclusively() -> None:
    """SEC adapter summary 应互斥统计真实跳过与 rejected filing。"""

    result: sec_pipeline.SecPipelineDownloadResult = {
        "pipeline": "sec_download",
        "action": "download",
        "status": "ok",
        "ticker": "ATAT",
        "market_profile": {},
        "filters": {
            "forms": ["10-K"],
            "start_date": None,
            "end_date": None,
            "overwrite": False,
            "rebuild": False,
        },
        "warnings": [],
        "filings": [
            {
                "document_id": "fil-downloaded",
                "status": "downloaded",
                "form_type": "10-K",
                "filing_date": "2024-08-01",
                "report_date": "2024-06-30",
            },
            {
                "document_id": "fil-already-complete",
                "status": "skipped",
                "skip_reason": "already_downloaded_complete",
                "reason_code": "already_downloaded_complete",
                "form_type": "10-K",
                "filing_date": "2024-08-01",
                "report_date": "2024-06-30",
            },
            {
                "document_id": "fil-filtered-6k",
                "status": "skipped",
                "skip_reason": "6k_filtered",
                "reason_code": "6k_filtered",
                "form_type": "6-K",
                "filing_date": "2024-08-02",
                "report_date": "2024-06-30",
            },
            {
                "document_id": "fil-failed",
                "status": "failed",
                "form_type": "10-Q",
                "filing_date": "2024-08-03",
                "report_date": "2024-06-30",
            },
        ],
        "summary": {
            "total": 999,
            "downloaded": 1,
            "skipped": 2,
            "rejected": 1,
            "failed": 99,
            "elapsed_ms": 42,
            "reused_downloads": 0,
            "converted": 0,
        },
    }

    class _LocatorRepository:
        """只为 downloaded row 提供 relative locator 的仓储桩。"""

        def get_source_document_locator(
            self,
            ticker: str,
            document_id: str,
            source_kind: SourceKind,
        ) -> PurePosixPath:
            """返回与输入身份对应的 relative locator。"""

            assert ticker == "ATAT"
            assert source_kind is SourceKind.FILING
            return PurePosixPath("source", document_id)

    request = FinsSourceDownloadAdapterRequest(
        normalized_ticker=normalize_ticker("ATAT"),
        source=FinsDownloadSource.SEC,
        form_types=("10-K",),
        date_range=FinsDownloadDateRange(None, None, False, False),
        overwrite_existing=False,
        rebuild_local_artifacts=False,
        cancellation_checker=_NeverCancelled(),
    )
    summary = sec_pipeline._summary_from_pipeline_result(
        cast(dict[str, JsonValue], result),
        request=request,
        source_repository=cast(SourceDocumentRepositoryProtocol, _LocatorRepository()),
    )

    assert summary.discovered_count == 4
    assert summary.downloaded_count == 1
    assert summary.skipped_count == 1
    assert summary.rejected_count == 1
    assert summary.failed_count == 1
    assert all(row.covered_fiscal_periods == () for row in summary.document_rows)
    assert summary.discovered_count == (
        summary.downloaded_count + summary.skipped_count + summary.rejected_count + summary.failed_count
    )
    assert (
        summary.discovered_count
        == summary.downloaded_count + summary.skipped_count + summary.rejected_count + summary.failed_count
    )
    invalid_result = cast(dict[str, JsonValue], dict(result))
    invalid_result["filings"] = [
        {
            "document_id": "fil-unknown-status",
            "status": "provider_new_status",
            "form_type": "10-K",
            "filing_date": "2024-08-04",
            "report_date": "2024-06-30",
        }
    ]
    with pytest.raises(ValueError, match="status 未封闭"):
        sec_pipeline._summary_from_pipeline_result(
            invalid_result,
            request=request,
            source_repository=cast(
                SourceDocumentRepositoryProtocol,
                _LocatorRepository(),
            ),
        )


def test_sec_adapter_local_rebuild_does_not_mutate_processed_documents(tmp_path: Path) -> None:
    """SEC local rebuild 应走现有 pipeline 且不标记 processed 重处理。"""

    document_id = "fil_sec_rebuild"
    pipeline = _RecordingSecPipelineForAdapter(tmp_path, document_id)
    batch = pipeline._batching_repository.begin_batch("AAPL")
    pipeline._processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker="AAPL",
            document_id=document_id,
            internal_document_id=document_id,
            source_kind=SourceKind.FILING.value,
            form_type="10-K",
            meta={"reprocess_required": False},
            sections=[],
            tables=[],
        ),
        batch=batch,
    )
    pipeline._batching_repository.commit_batch(batch)
    adapter = sec_pipeline.SecDownloadAdapter(pipeline=cast(sec_pipeline.SecPipeline, pipeline))

    adapter.download(
        FinsSourceDownloadAdapterRequest(
            normalized_ticker=normalize_ticker("AAPL"),
            source=FinsDownloadSource.SEC,
            form_types=("10-K",),
            date_range=FinsDownloadDateRange(None, None, False, False),
            overwrite_existing=False,
            rebuild_local_artifacts=True,
            cancellation_checker=_NeverCancelled(),
        )
    )

    processed_meta = pipeline._processed_repository.get_processed_meta("AAPL", document_id)

    assert pipeline.recorded_rebuild_values == [True]
    assert processed_meta["reprocess_required"] is False


def test_sec_pipeline_keeps_6k_results_release(tmp_path: Path) -> None:
    """验证 6-K 命中结果发布规则时保留落盘。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            # 封面自身已被真源判成季度结果时，应保留封面作为 primary_document。
            "sample-6k.htm": (
                b"FORM 6-K\nFor the month of August 2025\n"
                b"EXHIBIT INDEX\n"
                b"Exhibit 99.1 - Press Release - TCOM Announces Fourth Quarter "
                b"and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.download_files_called is True
    meta_path = _source_meta_path(tmp_path, "TCOM", "fil_0000000000-25-000101")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "sample-6k.htm"


def test_sec_pipeline_keeps_primary_only_6k_results_release(tmp_path: Path) -> None:
    """验证没有 EX-99/XBRL 时，命中季度结果的 6-K 主文仍会落盘。"""

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        content_by_name={
            "sample-6k.htm": (
                b"FORM 6-K\n"
                b"For the month of August 2025\n"
                b"TCOM Announces Second Quarter 2025 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.download_files_called is True
    meta_path = _source_meta_path(tmp_path, "TCOM", "fil_0000000000-25-000101")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "sample-6k.htm"


def test_sec_pipeline_promotes_positive_6k_exhibit_when_cover_is_excluded(tmp_path: Path) -> None:
    """验证 6-K 封面被排除时，会提升同 filing 的季度正文 exhibit。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "sample-6k.htm": (b"FORM 6-K\nEXHIBIT INDEX\nExhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n"),
            "d123dex991.htm": (
                b"Press Release\nTCOM Announces Fourth Quarter and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.download_files_called is True
    meta_path = _source_meta_path(tmp_path, "TCOM", "fil_0000000000-25-000101")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "d123dex991.htm"


def test_sec_pipeline_repairs_cover_primary_when_attachment_has_core_statements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证下载完成后会修复 6-K cover primary 到可提取核心报表的附件。"""

    remote_files = [
        RemoteFileDescriptor(
            name="form6-k.htm",
            source_url="https://example.com/form6-k.htm",
            http_etag="etag-cover",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="ex99-1.htm",
            source_url="https://example.com/ex99-1.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "form6-k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/form6-k.htm",
                "http_etag": "etag-cover",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "ex99-1.htm",
                "status": "downloaded",
                "source_url": "https://example.com/ex99-1.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "form6-k.htm": (
                b"FORM 6-K\nFinancial Results and Business Updates\nCompany reported strong quarterly performance\n"
            ),
            "ex99-1.htm": b"EX-99.1\nCompany quarterly results attachment\n",
        },
    )

    assessment_by_filename = {
        "form6-k.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="form6-k.htm",
            income_row_count=0,
            balance_sheet_row_count=0,
            filename_priority=3,
        ),
        "ex99-1.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="ex99-1.htm",
            income_row_count=22,
            balance_sheet_row_count=31,
            filename_priority=0,
        ),
    }

    def _fake_assess_prepared_6k_candidate(
        *,
        temporary_root: Path,
        position: int,
        filename: str,
        payload: bytes,
        primary_document: str,
    ) -> _sec_6k_primary_repair.SixKPrimaryCandidateAssessment:
        """返回固定候选评估结果。"""

        del temporary_root, position, payload, primary_document
        return assessment_by_filename[filename]

    monkeypatch.setattr(
        _sec_6k_primary_repair,
        "_assess_prepared_6k_candidate",
        _fake_assess_prepared_6k_candidate,
    )

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="ALVO", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    meta_path = _source_meta_path(tmp_path, "ALVO", "fil_0000000000-25-000101")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "ex99-1.htm"


def test_sec_pipeline_rolls_back_when_prepared_primary_selection_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6-K publication 前选文失败必须回滚，不能发布 provisional primary。"""

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "sample-6k.htm": (b"FORM 6-K\nEXHIBIT INDEX\nExhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n"),
            "d123dex991.htm": (
                b"Press Release\nTCOM Announces Fourth Quarter and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )

    def _raise_prepared_selection(
        *,
        ticker: str,
        document_id: str,
        meta: dict[str, JsonValue],
        candidate_payloads: dict[str, bytes],
    ) -> _sec_6k_primary_repair.SixKPrimaryReconcileOutcome | None:
        """模拟 publication 前 6-K 选文异常。"""

        del ticker, document_id, meta, candidate_payloads
        raise RuntimeError("boom")

    monkeypatch.setattr(
        _sec_download_filing_workflow,
        "select_prepared_6k_primary_document",
        _raise_prepared_selection,
    )

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    with pytest.raises(RuntimeError, match="boom"):
        pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    meta_path = _source_meta_path(tmp_path, "TCOM", "fil_0000000000-25-000101")
    assert not meta_path.exists()


def test_standalone_6k_reconcile_publishes_source_and_processed_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """standalone 6-K owner 必须共享 core，并在同批次发布主文件与 marker。"""

    ticker = "TCOM"
    document_id = "fil_0000000000-25-000101"
    _seed_complete_6k_source_and_processed(
        workspace_root=tmp_path,
        ticker=ticker,
        document_id=document_id,
    )
    discovery_repository_set = build_fs_repository_set(workspace_root=tmp_path)
    discovery_batching = FsBatchingRepository(
        tmp_path,
        repository_set=discovery_repository_set,
    )
    discovery_company = FsCompanyMetaRepository(
        tmp_path,
        repository_set=discovery_repository_set,
    )
    discovery_batch = discovery_batching.begin_batch(ticker)
    stage_company_meta_fixture(
        discovery_company,
        CompanyMeta(
            company_id="0000000000",
            company_name="Test Company",
            ticker_identity=build_company_ticker_identity(ticker, ()),
            resolver_version="test",
            updated_at="2026-08-14T00:00:00+00:00",
        ),
        batch=discovery_batch,
    )
    discovery_batching.commit_batch(discovery_batch)
    assessments = {
        "form6-k.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="form6-k.htm",
            income_row_count=0,
            balance_sheet_row_count=0,
            filename_priority=3,
        ),
        "ex99-1.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="ex99-1.htm",
            income_row_count=20,
            balance_sheet_row_count=30,
            filename_priority=0,
        ),
    }

    def _assess_active_candidate(
        *,
        snapshot: SourceSnapshotProtocol,
        filename: str,
        primary_document: str,
    ) -> _sec_6k_primary_repair.SixKPrimaryCandidateAssessment:
        """保留真实 batch/publication，只稳定处理器评估结果。"""

        del snapshot, primary_document
        return assessments[filename]

    monkeypatch.setattr(
        _sec_6k_primary_repair,
        "_assess_active_6k_candidate",
        _assess_active_candidate,
    )

    report = _sec_6k_primary_repair.reconcile_active_6k_primary_documents(
        workspace_root=tmp_path,
        target_tickers=None,
        target_document_ids=[document_id],
    )

    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    published_meta = source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)
    processed_meta = processed_repository.get_processed_meta(ticker, document_id)
    assert len(report.updated) == 1
    assert report.updated[0].selected_primary_document == "ex99-1.htm"
    assert published_meta["primary_document"] == "ex99-1.htm"
    assert processed_meta["reprocess_required"] is True


def test_prepared_6k_reconcile_handles_non_candidates_and_invalid_files() -> None:
    """publication 前 6-K owner 应跳过非候选并拒绝非法 files contract。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: public owner 的早退或校验边界漂移时抛出。
    """

    assert (
        _sec_6k_primary_repair.select_prepared_6k_primary_document(
            ticker="TCOM",
            document_id="fil-non-6k",
            meta={"form_type": "20-F", "primary_document": "form.htm", "files": []},
            candidate_payloads={},
        )
        is None
    )
    assert (
        _sec_6k_primary_repair.select_prepared_6k_primary_document(
            ticker="TCOM",
            document_id="fil-no-html",
            meta={
                "form_type": "6-K",
                "primary_document": "form.htm",
                "files": [None, {}, {"name": "notes.txt"}],
            },
            candidate_payloads={},
        )
        is None
    )
    assert (
        _sec_6k_primary_repair.select_prepared_6k_primary_document(
            ticker="TCOM",
            document_id="fil-missing-payload",
            meta={
                "form_type": "6-K",
                "primary_document": "form.htm",
                "files": [{"name": "missing.htm"}],
            },
            candidate_payloads={},
        )
        is None
    )
    with pytest.raises(ValueError, match="meta.files 必须为 list"):
        _sec_6k_primary_repair.select_prepared_6k_primary_document(
            ticker="TCOM",
            document_id="fil-invalid-files",
            meta={"form_type": "6-K", "primary_document": "form.htm"},
            candidate_payloads={},
        )


def test_standalone_6k_reconcile_normalizes_public_filters(tmp_path: Path) -> None:
    """standalone public path 应稳定去重 ticker 并拒绝清洗后的空过滤器。

    Args:
        tmp_path: pytest 临时工作区。

    Returns:
        无。

    Raises:
        AssertionError: public filter owner 的规范化或空值合同漂移时抛出。
    """

    report = _sec_6k_primary_repair.reconcile_active_6k_primary_documents(
        workspace_root=tmp_path,
        target_tickers=[" aapl ", "AAPL", "", " msft "],
        target_document_ids=None,
    )

    assert report.updated == ()
    with pytest.raises(ValueError, match="target_tickers 不能为空"):
        _sec_6k_primary_repair.reconcile_active_6k_primary_documents(
            workspace_root=tmp_path,
            target_tickers=[" ", ""],
        )
    with pytest.raises(ValueError, match="target_document_ids 不能为空"):
        _sec_6k_primary_repair.reconcile_active_6k_primary_documents(
            workspace_root=tmp_path,
            target_tickers=["AAPL"],
            target_document_ids=[" ", ""],
        )


def test_standalone_6k_reconcile_rolls_back_failed_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单文档 reconcile 异常时 public owner 必须 rollback 且保留 published meta。

    Args:
        tmp_path: pytest 临时工作区。
        monkeypatch: pytest monkeypatch。

    Returns:
        无。

    Raises:
        AssertionError: rollback 后 published state 发生变化时抛出。
    """

    ticker = "TCOM"
    document_id = "fil_0000000000-25-000101"
    _seed_complete_6k_source_and_processed(
        workspace_root=tmp_path,
        ticker=ticker,
        document_id=document_id,
    )
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    before_meta = source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)

    def _raise_reconcile_failure(
        *,
        source_repository: SourceDocumentRepositoryProtocol,
        processed_repository: ProcessedDocumentRepositoryProtocol,
        ticker: str,
        document_id: str,
        batch: BatchToken,
    ) -> _sec_6k_primary_repair.SixKPrimaryReconcileOutcome | None:
        """模拟单文档 owner 在 batch 内失败。

        Args:
            source_repository: source 仓储协议。
            processed_repository: processed 仓储协议。
            ticker: 当前 ticker。
            document_id: 当前文档 ID。
            batch: caller-owned batch。

        Returns:
            不返回。

        Raises:
            RuntimeError: 始终抛出以验证 rollback。
        """

        del source_repository, processed_repository, ticker, document_id, batch
        raise RuntimeError("forced 6-K reconcile failure")

    monkeypatch.setattr(
        _sec_6k_primary_repair,
        "reconcile_active_6k_primary_document",
        _raise_reconcile_failure,
    )

    with pytest.raises(RuntimeError, match="forced 6-K reconcile failure"):
        _sec_6k_primary_repair.reconcile_active_6k_primary_documents(
            workspace_root=tmp_path,
            target_tickers=[ticker],
            target_document_ids=[document_id],
        )

    after_repository_set = build_fs_repository_set(workspace_root=tmp_path)
    after_repository = FsSourceDocumentRepository(
        tmp_path,
        repository_set=after_repository_set,
    )
    assert after_repository.get_source_meta(ticker, document_id, SourceKind.FILING) == before_meta


def test_active_6k_candidate_assessment_consumes_one_storage_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """active 6-K 全部候选评估必须共享同一份 full snapshot。

    Args:
        tmp_path: 临时工作区根目录。
        monkeypatch: pytest monkeypatch。

    Returns:
        无。

    Raises:
        AssertionError: consumer 逐文件读取仓储、混用 snapshot 或泄漏资源时抛出。
    """

    ticker = "TCOM"
    document_id = "fil_0000000000-25-000101"
    _seed_complete_6k_source_and_processed(
        workspace_root=tmp_path,
        ticker=ticker,
        document_id=document_id,
    )
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(tmp_path, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(tmp_path, repository_set=repository_set)
    original_read_snapshot = source_repository.read_source_snapshot
    acquired_snapshots: list[SourceSnapshotProtocol] = []
    assessed_snapshots: list[SourceSnapshotProtocol] = []
    materialized_paths: list[Path] = []
    assessments = {
        "form6-k.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="form6-k.htm",
            income_row_count=0,
            balance_sheet_row_count=0,
            filename_priority=3,
        ),
        "ex99-1.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="ex99-1.htm",
            income_row_count=20,
            balance_sheet_row_count=30,
            filename_priority=0,
        ),
    }

    def _observe_snapshot_read(
        observed_ticker: str,
        observed_document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """记录真实 storage snapshot 调用并返回原始资源。"""

        snapshot = original_read_snapshot(
            observed_ticker,
            observed_document_id,
            source_kind,
            materialize_files=materialize_files,
        )
        acquired_snapshots.append(snapshot)
        return snapshot

    def _forbid_source_meta_read(
        observed_ticker: str,
        observed_document_id: str,
        source_kind: SourceKind | None = None,
    ) -> None:
        """禁止 6-K consumer 在 snapshot 外重复读取 meta。"""

        del observed_ticker, observed_document_id, source_kind
        raise AssertionError("6-K consumer must read meta from its snapshot")

    def _forbid_source_file_read(source_handle: SourceHandle, filename: str) -> None:
        """禁止 6-K consumer 在 snapshot 外逐文件读取 source。"""

        del source_handle, filename
        raise AssertionError("6-K consumer must read files from its snapshot")

    def _assess_active_candidate(
        *,
        snapshot: SourceSnapshotProtocol,
        filename: str,
        primary_document: str,
    ) -> _sec_6k_primary_repair.SixKPrimaryCandidateAssessment:
        """记录候选共享的 snapshot 及其临时文件生命周期。"""

        del primary_document
        assessed_snapshots.append(snapshot)
        materialized_paths.append(snapshot.get_source(filename).materialize())
        return assessments[filename]

    monkeypatch.setattr(source_repository, "read_source_snapshot", _observe_snapshot_read)
    monkeypatch.setattr(source_repository, "get_source_meta", _forbid_source_meta_read)
    monkeypatch.setattr(source_repository, "get_source", _forbid_source_file_read)
    monkeypatch.setattr(
        _sec_6k_primary_repair,
        "_assess_active_6k_candidate",
        _assess_active_candidate,
    )

    batch = batching_repository.begin_batch(ticker)
    commit_started = False
    try:
        outcome = _sec_6k_primary_repair.reconcile_active_6k_primary_document(
            source_repository=source_repository,
            processed_repository=processed_repository,
            ticker=ticker,
            document_id=document_id,
            batch=batch,
        )
        commit_started = True
        batching_repository.commit_batch(batch)
    finally:
        if not commit_started:
            batching_repository.rollback_batch(batch)

    assert outcome is not None
    assert outcome.selected_primary_document == "ex99-1.htm"
    assert len(acquired_snapshots) == 1
    assert assessed_snapshots
    assert all(snapshot is acquired_snapshots[0] for snapshot in assessed_snapshots)
    assert materialized_paths
    assert all(not path.exists() for path in materialized_paths)
    with pytest.raises(RuntimeError, match="已关闭"):
        acquired_snapshots[0].get_primary_source()


def test_sec_form_domain_parser_accepts_supported_aliases() -> None:
    """验证 SEC form domain parser 接受当前支持的别名。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert parse_sec_form_type("10K") == "10-K"
    assert parse_sec_form_type("10-K/A") == "10-K/A"
    assert parse_sec_form_type("def 14a") == "DEF 14A"
    assert parse_sec_form_filter_value("SC13D/G") == "SC 13D/G"
    assert expand_sec_form_aliases(["SC13D/G"]) == ["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"]
    assert parse_sec_form_type("SCHEDULE 13D") == "SC 13D"


def test_shared_domain_parsers_reject_invalid_values() -> None:
    """验证共享 domain parser 对非法业务值 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    with pytest.raises(ValueError, match="form_type 不能为空"):
        parse_sec_form_type("")
    with pytest.raises(ValueError, match="form_type 不支持"):
        parse_sec_form_type("F-1")
    with pytest.raises(ValueError, match="fiscal_period 非法"):
        normalize_fiscal_period("Q5")
    with pytest.raises(ValueError, match="quality 非法"):
        normalize_document_quality("xbrl")
    with pytest.raises(ValueError, match="data_quality 非法"):
        normalize_financial_data_quality("raw")


def test_sec_pipeline_warns_missing_sc13(tmp_path: Path) -> None:
    """验证缺失 SC 13D/G 时输出提示。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    submissions = _build_submissions()
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    warnings = result.get("warnings") or []
    assert any("SC 13D/G" in item for item in warnings)


def test_sec_pipeline_sc13_direction_filters_gs_like_records(tmp_path: Path) -> None:
    """验证 GS-like 场景（ticker 持股别人）会被 SC13 方向过滤为 0 条。"""

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G", "SC 13D/A"],
                "filingDate": ["2025-08-10", "2025-08-11"],
                "reportDate": ["", ""],
                "accessionNumber": ["0000000000-25-000701", "0000000000-25-000702"],
                "primaryDocument": ["sc13g-1.htm", "sc13da-1.htm"],
                "fileNumber": ["005-10001", "005-10002"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        sc13_roles_by_accession={
            "0000000000-25-000701": ("320193", "999999"),
            "0000000000-25-000702": ("320193", "888888"),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="GS", form_type="SC13D/G", overwrite=False, start_is_explicit=False)

    assert result["summary"]["total"] == 0
    assert result["summary"]["downloaded"] == 0
    assert downloader.download_files_called is True
    assert _rejected_meta_path(
        tmp_path,
        "GS",
        "fil_0000000000-25-000701",
    ).exists()
    assert _rejected_meta_path(
        tmp_path,
        "GS",
        "fil_0000000000-25-000702",
    ).exists()


def test_sec_pipeline_sc13_transport_failure_publishes_registry_only(
    tmp_path: Path,
) -> None:
    """SC13 rejected artifact transport failure 必须保留 registry-only durable 语义。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: transport typed failure 未回退到 registry-only 或伪造 artifact 时抛出。
    """

    accession_number = "0000000000-25-000703"
    document_id = f"fil_{accession_number}"
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G"],
                "filingDate": ["2025-08-12"],
                "reportDate": [""],
                "accessionNumber": [accession_number],
                "primaryDocument": ["sc13g-failed.htm"],
                "fileNumber": ["005-10003"],
            },
            "files": [],
        }
    }
    descriptor = RemoteFileDescriptor(
        name="sc13g-failed.htm",
        source_url="https://example.com/sc13g-failed.htm",
        http_etag=None,
        http_last_modified=None,
        remote_size=None,
        http_status=503,
    )
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=[descriptor],
        download_results=[
            {
                "name": descriptor.name,
                "status": "failed",
                "source_url": descriptor.source_url,
                "reason_code": "provider_unavailable",
                "reason_message": "来源暂不可用",
            }
        ],
        sc13_roles_by_accession={accession_number: ("320193", "999999")},
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(
        ticker="GS",
        form_type="SC13D/G",
        overwrite=False,
        start_is_explicit=False,
    )

    registry_payload = json.loads(_download_rejections_path(tmp_path, "GS").read_text(encoding="utf-8"))
    assert result["summary"]["total"] == 0
    assert registry_payload[document_id]["reason"] == "sc13_direction_rejected"
    assert not _rejected_meta_path(tmp_path, "GS", document_id).exists()


def test_sec_pipeline_sc13_direction_keeps_aapl_like_records(tmp_path: Path) -> None:
    """验证 AAPL-like 场景仅保留“别人持股 ticker”的 SC13。"""

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G", "SC 13D", "SC 13G/A"],
                "filingDate": ["2025-08-10", "2025-08-11", "2025-08-12"],
                "reportDate": ["", "", ""],
                "accessionNumber": [
                    "0000000000-25-000801",
                    "0000000000-25-000802",
                    "0000000000-25-000803",
                ],
                "primaryDocument": ["sc13g-1.htm", "sc13d-1.htm", "sc13ga-1.htm"],
                "fileNumber": ["005-20001", "005-20002", "005-20003"],
            },
            "files": [],
        }
    }
    remote_files = [
        RemoteFileDescriptor(
            name="sc13g-1.htm",
            source_url="https://example.com/sc13g-1.htm",
            http_etag="etag-v1",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sc13g-1.htm",
                "status": "downloaded",
                "path": "sc13g-1.htm",
                "source_url": "https://example.com/sc13g-1.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        sc13_roles_by_accession={
            "0000000000-25-000801": ("111111", "320193"),
            "0000000000-25-000802": ("320193", "999999"),
            "0000000000-25-000803": None,
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(
        ticker="AAPL",
        form_type="SC13D/G",
        start_date="2025-01-01",
        end_date="2026-12-31",
        overwrite=False,
        start_is_explicit=False,
    )

    assert result["summary"]["downloaded"] == 1
    kept_meta = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000801")
    filtered_meta = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000802")
    unknown_meta = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000803")
    assert kept_meta.exists()
    assert not filtered_meta.exists()
    assert not unknown_meta.exists()


def test_sec_pipeline_supplements_sc13_from_browse(tmp_path: Path) -> None:
    """验证通过 browse-edgar 补齐 SC 13D/G。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000010"],
                "primaryDocument": ["sample-8k.htm"],
                "fileNumber": ["005-12345"],
            },
            "files": [],
        }
    }
    browse_entries = [
        BrowseEdgarFiling(
            form_type="SCHEDULE 13G",
            filing_date="2025-08-10",
            accession_number="0000000000-25-000777",
            cik="1000",
            index_url="https://example.com/0000000000-25-000777-index.htm",
        )
    ]
    remote_files = [
        RemoteFileDescriptor(
            name="primary.htm",
            source_url="https://example.com/primary.htm",
            http_etag="etag-sc13",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "primary.htm",
                "status": "downloaded",
                "source_url": "https://example.com/primary.htm",
                "http_etag": "etag-sc13",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        browse_entries=browse_entries,
        primary_documents={
            "1000:000000000025000777:SC 13G": "primary.htm",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.browse_calls == ["005-12345"]
    meta_path = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000777")
    assert meta_path.exists()


def test_sec_pipeline_sc13_keeps_latest_per_filer(tmp_path: Path) -> None:
    """验证同一申报主体（filenum）仅保留最新 SC 13。"""

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000010"],
                "primaryDocument": ["sample-8k.htm"],
                "fileNumber": ["005-12345"],
            },
            "files": [],
        }
    }
    browse_entries = [
        BrowseEdgarFiling(
            form_type="SCHEDULE 13G",
            filing_date="2025-08-10",
            accession_number="0000000000-25-000777",
            cik="1000",
            index_url="https://example.com/0000000000-25-000777-index.htm",
        ),
        BrowseEdgarFiling(
            form_type="SCHEDULE 13G/A",
            filing_date="2025-09-01",
            accession_number="0000000000-25-000888",
            cik="1000",
            index_url="https://example.com/0000000000-25-000888-index.htm",
        ),
    ]
    remote_files = [
        RemoteFileDescriptor(
            name="primary.htm",
            source_url="https://example.com/primary.htm",
            http_etag="etag-sc13",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "primary.htm",
                "status": "downloaded",
                "source_url": "https://example.com/primary.htm",
                "http_etag": "etag-sc13",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        browse_entries=browse_entries,
        primary_documents={
            "1000:000000000025000777:SC 13G": "primary.htm",
            "1000:000000000025000888:SC 13G/A": "primary.htm",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False, start_is_explicit=False)

    assert result["summary"]["downloaded"] == 1
    old_meta = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000777")
    latest_meta = _source_meta_path(tmp_path, "AAPL", "fil_0000000000-25-000888")
    assert not old_meta.exists()
    assert latest_meta.exists()


# ---------------------------------------------------------------------------
# SC 13 渐进式回溯测试
# ---------------------------------------------------------------------------


def test_sc13_constants() -> None:
    """验证 SC 13 渐进式回溯常量配置。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert _SC13_FORMS == frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"})
    assert _SC13_RETRY_MAX == 2


def test_sc13_no_retry_when_found_in_initial_window(tmp_path: Path) -> None:
    """SC 13 在初始1年窗口内有结果时不触发重试。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    # SC 13G 在最近1年内
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000100"],
                "primaryDocument": ["sc13g.htm"],
                "fileNumber": ["005-99999"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-sc13")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sc13g.htm",
                "status": "downloaded",
                "path": "sc13g.htm",
                "source_url": "https://example.com/sc13g.htm",
                "http_etag": "etag-sc13",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False, start_is_explicit=False)

    # 找到了 SC 13G，无需重试 → browse_calls 不应被调用（submissions 无 005- filenum 除自身外）
    assert result["summary"]["downloaded"] == 1
    warnings = result.get("warnings") or []
    assert not any("SC 13D/G" in w for w in warnings)


def test_sc13_retry_expands_window_and_finds_filing(tmp_path: Path) -> None:
    """SC 13 初始窗口无结果，通过渐进式回溯在扩大窗口后找到 filing。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    # SC 13G 在2年前（超出初始1年窗口，但在第1次重试的2年窗口内）
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K", "SC 13G"],
                "filingDate": ["2025-08-01", "2024-01-15"],
                "reportDate": ["", ""],
                "accessionNumber": ["0000000000-25-000010", "0000000000-24-000050"],
                "primaryDocument": ["sample-8k.htm", "sc13g-old.htm"],
                "fileNumber": ["001-12345", "005-67890"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sc13g-old.htm",
                "status": "downloaded",
                "path": "sc13g-old.htm",
                "source_url": "https://example.com/sc13g-old.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False, start_is_explicit=False)

    # 初始1年窗口找不到（2024-01-15 在1年+60天之外），重试后应找到
    assert result["summary"]["downloaded"] >= 1
    warnings = result.get("warnings") or []
    # 找到了 SC 13G，不应有缺失警告
    assert not any("SC 13D/G" in w for w in warnings)


def test_sc13_explicit_start_never_expands_lower_bound(tmp_path: Path) -> None:
    """显式 SC13 起点必须阻止渐进回溯选择更早 filing。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 窗口外 filing 被下载或持久化时抛出。
    """

    old_accession = "0000000000-24-000050"
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G"],
                "filingDate": ["2024-01-15"],
                "reportDate": [""],
                "accessionNumber": [old_accession],
                "primaryDocument": ["sc13g-old.htm"],
                "fileNumber": ["005-67890"],
            },
            "files": [],
        }
    }
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=[_make_descriptor("etag-old")],
        download_results=[
            {
                "name": "sc13g-old.htm",
                "status": "downloaded",
                "path": "sc13g-old.htm",
                "source_url": "https://example.com/sc13g-old.htm",
                "http_etag": "etag-old",
                "http_last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(
        ticker="AAPL",
        form_type="SC13D/G",
        start_date="2025-01-01",
        end_date="2026-12-31",
        overwrite=False,
        start_is_explicit=True,
    )

    assert result["summary"]["downloaded"] == 0
    assert result["summary"]["rejected"] == 0
    assert downloader.download_files_called is False
    assert not _source_meta_path(tmp_path, "AAPL", f"fil_{old_accession}").exists()


def test_sc13_retry_warns_after_max_retries(tmp_path: Path) -> None:
    """SC 13 渐进式回溯达到最大重试次数仍无结果时发出警告。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    # 无任何 SC 13 filing
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000010"],
                "primaryDocument": ["sample-8k.htm"],
                "fileNumber": ["001-12345"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-8k.htm",
                "status": "downloaded",
                "path": "sample-8k.htm",
                "source_url": "https://example.com/sample-8k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    # 最大重试后仍无 SC 13 → 应有缺失警告
    warnings = result.get("warnings") or []
    assert any("SC 13D/G" in w for w in warnings)


@pytest.mark.parametrize("corruption", ["size", "digest", "missing", "manifest"])
def test_sec_top_level_repairs_selected_corruption_before_company_mutation(
    tmp_path: Path,
    corruption: str,
) -> None:
    """真实 SEC top-level overwrite=False 必须修复唯一 selected corruption。"""

    meta_path = _seed_complete_sec_source(workspace_root=tmp_path)
    payload_path = meta_path.parent / "sample-10k.htm"
    old_payload = payload_path.read_bytes()
    if corruption == "size":
        payload_path.write_bytes(old_payload + b"-corrupt")
    elif corruption == "digest":
        payload_path.write_bytes(b"X" * len(old_payload))
    elif corruption == "missing":
        payload_path.unlink()
    else:
        _filing_manifest_path(tmp_path, "AAPL").unlink()
    replacement = b"<html>repaired</html>"
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=[_make_descriptor("etag-repair")],
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-repair",
            }
        ],
        content_by_name={"sample-10k.htm": replacement},
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(
        ticker="AAPL",
        overwrite=False,
        start_is_explicit=False,
    )

    assert result["summary"]["downloaded"] == 1
    assert pipeline._source_repository.classify_source_integrity(
        "AAPL",
        "fil_0000000000-25-000001",
        SourceKind.FILING,
    ).status is SourceIntegrityStatus.COMPLETE
    assert _filing_manifest_path(tmp_path, "AAPL").is_file()
    with pipeline._source_repository.read_source_snapshot(
        "AAPL",
        "fil_0000000000-25-000001",
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        with snapshot.get_primary_source().open() as stream:
            assert stream.read() == replacement


@pytest.mark.parametrize("corruption", ["missing_file", "manifest_missing"])
def test_sec_top_level_unselected_corruption_fails_before_company_batch(
    tmp_path: Path,
    corruption: str,
) -> None:
    """未选中 corruption 必须在任何 company/source/rejection mutation 前 typed fail closed。

    Args:
        tmp_path: pytest 临时目录。
        corruption: 未选中 source 的 physical 或 whole-manifest 损坏类型。

    Returns:
        无。

    Raises:
        AssertionError: typed reason 或零副作用 contract 漂移时抛出。
    """

    meta_path = _seed_complete_sec_source(
        workspace_root=tmp_path,
        document_id="fil_unselected",
    )
    if corruption == "missing_file":
        (meta_path.parent / "sample-10k.htm").unlink()
    else:
        _filing_manifest_path(tmp_path, "AAPL").unlink()
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=StubDownloader(
            submissions=_build_submissions(),
            remote_files=[_make_descriptor("etag")],
            download_results=[],
        ),
        processor_registry=build_fins_processor_registry(),
    )

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        pipeline.download(
            ticker="AAPL",
            overwrite=False,
            start_is_explicit=False,
        )

    assert exc_info.value.reason is SourceIntegrityPreflightReason.UNSELECTED_REPAIR_REQUIRED
    with pytest.raises(FileNotFoundError):
        pipeline._company_repository.get_company_meta("AAPL")


def test_sec_unsafe_phase_a_and_whole_tree_preflight_have_zero_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC single-filing Phase A 与 whole-tree 都必须在 UNSAFE 后零副作用拒绝。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: UNSAFE 后仍读取 provider filing、开启 batch 或发布 durable fact 时抛出。
    """

    document_id = "fil_0000000000-25-000001"
    meta_path = _seed_complete_sec_source(workspace_root=tmp_path, document_id=document_id)
    payload_path = meta_path.parent / "sample-10k.htm"
    manifest_path = _filing_manifest_path(tmp_path, "AAPL")
    unsafe_path = meta_path.parent / "undeclared.bin"
    unsafe_path.write_bytes(b"unsafe")
    old_bytes = {
        "meta": meta_path.read_bytes(),
        "payload": payload_path.read_bytes(),
        "manifest": manifest_path.read_bytes(),
        "unsafe": unsafe_path.read_bytes(),
    }
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=[_make_descriptor("etag")],
        download_results=[],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    begin_calls = 0

    def reject_begin(ticker: str) -> BatchToken:
        """任何越过 UNSAFE gate 的 batch 都使测试立即失败。

        Args:
            ticker: 待开启事务的 ticker。

        Returns:
            不返回。

        Raises:
            AssertionError: 本 helper 被调用时始终抛出。
        """

        del ticker
        nonlocal begin_calls
        begin_calls += 1
        raise AssertionError("UNSAFE preflight 后不得 begin_batch")

    monkeypatch.setattr(pipeline._batching_repository, "begin_batch", reject_begin)
    filing = _sec_filing_collection.FilingRecord(
        form_type="10-K",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000001",
        primary_document="sample-10k.htm",
    )

    async def collect_single() -> list[DownloadEvent]:
        """消费真实 single-filing owner 直到 typed preflight 失败。

        Args:
            无。

        Returns:
            异常未抛出时返回已产生事件。

        Raises:
            SourceIntegrityPreflightError: Phase A 分类为 UNSAFE 时抛出。
        """

        return [
            event
            async for event in pipeline._download_single_filing_stream(
                ticker="AAPL",
                cik="320193",
                filing=filing,
                overwrite=False,
                rejection_registry={},
            )
        ]

    with pytest.raises(SourceIntegrityPreflightError) as phase_a_error:
        asyncio.run(collect_single())
    with pytest.raises(SourceIntegrityPreflightError) as whole_tree_error:
        pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert phase_a_error.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert whole_tree_error.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert begin_calls == 0
    assert downloader.list_filing_files_call_count == 0
    assert meta_path.read_bytes() == old_bytes["meta"]
    assert payload_path.read_bytes() == old_bytes["payload"]
    assert manifest_path.read_bytes() == old_bytes["manifest"]
    assert unsafe_path.read_bytes() == old_bytes["unsafe"]
    assert not _company_meta_path(tmp_path, "AAPL").exists()
    assert not _download_rejections_path(tmp_path, "AAPL").exists()


def test_sec_unsafe_phase_b_rolls_back_without_reset_blob_or_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEC Phase B typed UNSAFE 必须回滚一次且保持 published source 完全不变。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: Phase B 未返回 exact typed error，或发生 reset/blob/commit 副作用时抛出。
    """

    document_id = "fil_0000000000-25-000001"
    meta_path = _seed_complete_sec_source(workspace_root=tmp_path, document_id=document_id)
    payload_path = meta_path.parent / "sample-10k.htm"
    manifest_path = _filing_manifest_path(tmp_path, "AAPL")
    old_meta = meta_path.read_bytes()
    old_payload = payload_path.read_bytes()
    old_manifest = manifest_path.read_bytes()
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=[_make_descriptor("etag-phase-b")],
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-phase-b",
            }
        ],
        content_by_name={"sample-10k.htm": b"phase-b-prefetched"},
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    calls = _SecPhaseBMutationCalls()
    original_begin = pipeline._batching_repository.begin_batch
    original_rollback = pipeline._batching_repository.rollback_batch

    def observe_begin(ticker: str) -> BatchToken:
        """记录并执行真实 batch begin。

        Args:
            ticker: 当前事务 ticker。

        Returns:
            真实 batching owner 生成的 token。

        Raises:
            OSError: 真实 batch begin 失败时抛出。
        """

        calls.begin += 1
        return original_begin(ticker)

    def classify_staged_unsafe(
        ticker: str,
        staged_document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> SourceIntegrityClassification:
        """返回 invariant-valid 的 staged UNSAFE typed fact。

        Args:
            ticker: exact ticker。
            staged_document_id: exact document ID。
            source_kind: exact source kind。
            batch: 已打开的 batch capability。

        Returns:
            storage boundary 已分类的 staged UNSAFE fact。

        Raises:
            无。
        """

        del batch
        calls.staged_classify += 1
        return SourceIntegrityClassification(
            ticker=ticker,
            source_kind=source_kind,
            document_id=staged_document_id,
            revision=None,
            status=SourceIntegrityStatus.UNSAFE,
            reasons=(SourceIntegrityReason.META_UNTRUSTED,),
        )

    def reject_reset(
        ticker: str,
        staged_document_id: str,
        source_kind: SourceKind,
        *,
        batch: BatchToken,
    ) -> None:
        """记录任何越过 UNSAFE gate 的 source reset 并立即失败。

        Args:
            ticker: exact ticker。
            staged_document_id: exact document ID。
            source_kind: exact source kind。
            batch: 已打开的 batch capability。

        Returns:
            不返回。

        Raises:
            AssertionError: 本 helper 被调用时始终抛出。
        """

        del ticker, staged_document_id, source_kind, batch
        calls.reset += 1
        raise AssertionError("Phase B UNSAFE 后不得 reset source")

    def reject_blob(
        handle: SourceHandle,
        filename: str,
        data: BinaryIO,
        *,
        batch: BatchToken,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> FileObjectMeta:
        """记录任何越过 UNSAFE gate 的 blob mutation 并立即失败。

        Args:
            handle: source handle。
            filename: blob 文件名。
            data: 待写入字节流。
            batch: 已打开的 batch capability。
            content_type: 可选内容类型。
            metadata: 可选 blob 元数据。

        Returns:
            不返回。

        Raises:
            AssertionError: 本 helper 被调用时始终抛出。
        """

        del handle, filename, data, batch, content_type, metadata
        calls.blob += 1
        raise AssertionError("Phase B UNSAFE 后不得写 blob")

    def reject_commit(batch: BatchToken) -> None:
        """记录任何越过 UNSAFE gate 的 commit 并立即失败。

        Args:
            batch: 已打开的 batch capability。

        Returns:
            不返回。

        Raises:
            AssertionError: 本 helper 被调用时始终抛出。
        """

        del batch
        calls.commit += 1
        raise AssertionError("Phase B UNSAFE 后不得 commit")

    def observe_rollback(batch: BatchToken) -> None:
        """记录并执行真实 batch rollback。

        Args:
            batch: 已打开的 batch capability。

        Returns:
            无。

        Raises:
            OSError: 真实 rollback 失败时抛出。
            ValueError: batch capability 非法时抛出。
        """

        calls.rollback += 1
        original_rollback(batch)

    monkeypatch.setattr(pipeline._batching_repository, "begin_batch", observe_begin)
    monkeypatch.setattr(pipeline._batching_repository, "commit_batch", reject_commit)
    monkeypatch.setattr(pipeline._batching_repository, "rollback_batch", observe_rollback)
    monkeypatch.setattr(
        pipeline._source_repository,
        "classify_staged_source_integrity",
        classify_staged_unsafe,
    )
    monkeypatch.setattr(pipeline._source_repository, "reset_source_document", reject_reset)
    monkeypatch.setattr(pipeline._blob_repository, "store_file", reject_blob)
    filing = _sec_filing_collection.FilingRecord(
        form_type="10-K",
        filing_date="2025-02-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000001",
        primary_document="sample-10k.htm",
    )

    async def collect_single() -> list[DownloadEvent]:
        """消费真实 SEC single-filing owner 直到 Phase B typed failure。

        Args:
            无。

        Returns:
            异常未抛出时返回已产生事件。

        Raises:
            SourceIntegrityPreflightError: staged classification 为 UNSAFE 时抛出。
        """

        return [
            event
            async for event in pipeline._download_single_filing_stream(
                ticker="AAPL",
                cik="320193",
                filing=filing,
                overwrite=True,
                rejection_registry={},
            )
        ]

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        asyncio.run(collect_single())

    assert exc_info.value.reason is SourceIntegrityPreflightReason.UNSAFE_PUBLICATION
    assert calls == _SecPhaseBMutationCalls(
        begin=1,
        staged_classify=1,
        reset=0,
        blob=0,
        commit=0,
        rollback=1,
    )
    assert downloader.download_files_called is True
    assert meta_path.read_bytes() == old_meta
    assert payload_path.read_bytes() == old_payload
    assert manifest_path.read_bytes() == old_manifest
    assert pipeline._source_repository.classify_source_integrity(
        "AAPL",
        document_id,
        SourceKind.FILING,
    ).status is SourceIntegrityStatus.COMPLETE


def test_sec_whole_manifest_missing_with_multiple_actual_sources_fails_closed(
    tmp_path: Path,
) -> None:
    """whole manifest 缺失且存在多个 actual source 时不得选择局部 repair。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: typed MULTIPLE reason、零 mutation 或 shared reason 漂移时抛出。
    """

    document_ids = (
        "fil_0000000000-25-000001",
        "fil_0000000000-24-000002",
    )
    meta_paths = tuple(
        _seed_complete_sec_source(workspace_root=tmp_path, document_id=document_id)
        for document_id in document_ids
    )
    manifest_path = _filing_manifest_path(tmp_path, "AAPL")
    manifest_path.unlink()
    old_meta = tuple(path.read_bytes() for path in meta_paths)
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=[_make_descriptor("etag")],
        download_results=[],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        pipeline.download(ticker="AAPL", overwrite=False, start_is_explicit=False)

    assert exc_info.value.reason is SourceIntegrityPreflightReason.MULTIPLE_REPAIR_REQUIRED
    assert downloader.list_filing_files_call_count == 0
    assert tuple(path.read_bytes() for path in meta_paths) == old_meta
    assert manifest_path.exists() is False
    assert not _company_meta_path(tmp_path, "AAPL").exists()
    assert not _download_rejections_path(tmp_path, "AAPL").exists()
    for document_id in document_ids:
        classification = pipeline._source_repository.classify_source_integrity(
            "AAPL",
            document_id,
            SourceKind.FILING,
        )
        assert classification.status is SourceIntegrityStatus.REPAIR_REQUIRED
        assert classification.reasons == (SourceIntegrityReason.SOURCE_MANIFEST_MISSING,)


def test_sec_same_target_overwrite_discards_stale_prefetch_and_last_writer_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 target 双 overwrite 都成功，后 writer 必须丢弃旧 payload 并重新预取。"""

    second_prefetch_complete = Event()
    first_source_committed = Event()
    remote_files = [_make_descriptor("etag-race")]
    download_results: list[DownloadFileResult] = [
        {
            "name": "sample-10k.htm",
            "status": "downloaded",
            "source_url": "https://example.com/sample-10k.htm",
        }
    ]
    first_downloader = BarrierPrefetchDownloader(
        role="first",
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=download_results,
        first_prefetch_payload=b"writer-a",
        retry_payload=b"unused-a",
        second_prefetch_complete=second_prefetch_complete,
        first_source_committed=first_source_committed,
    )
    second_downloader = BarrierPrefetchDownloader(
        role="second",
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=download_results,
        first_prefetch_payload=b"writer-b-stale",
        retry_payload=b"writer-b-final",
        second_prefetch_complete=second_prefetch_complete,
        first_source_committed=first_source_committed,
    )
    first_pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=first_downloader,
        processor_registry=build_fins_processor_registry(),
    )
    second_pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=second_downloader,
        processor_registry=build_fins_processor_registry(),
    )
    original_first_commit = first_pipeline._batching_repository.commit_batch

    def observe_first_source_commit(batch: BatchToken) -> None:
        """在真实 commit 后仅当 target 已完整时释放 second writer。"""

        original_first_commit(batch)
        classification = first_pipeline._source_repository.classify_source_integrity(
            "AAPL",
            "fil_0000000000-25-000001",
            SourceKind.FILING,
        )
        if classification.status.value == "complete":
            first_source_committed.set()

    monkeypatch.setattr(
        first_pipeline._batching_repository,
        "commit_batch",
        observe_first_source_commit,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            first_pipeline.download,
            "AAPL",
            overwrite=True,
            start_is_explicit=False,
        )
        second_future = executor.submit(
            second_pipeline.download,
            "AAPL",
            overwrite=True,
            start_is_explicit=False,
        )
        first_result = first_future.result(timeout=10)
        second_result = second_future.result(timeout=10)

    assert first_result["summary"]["downloaded"] == 1
    assert second_result["summary"]["downloaded"] == 1
    assert first_downloader.prefetch_rounds == 1
    assert second_downloader.prefetch_rounds == 2
    with second_pipeline._source_repository.read_source_snapshot(
        "AAPL",
        "fil_0000000000-25-000001",
        SourceKind.FILING,
        materialize_files=True,
    ) as snapshot:
        with snapshot.get_primary_source().open() as stream:
            assert stream.read() == b"writer-b-final"


def test_sec_different_target_overwrite_writers_publish_union(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 ticker 不同 target writer 必须从 latest tree 发布最终 union。"""

    second_prefetch_complete = Event()
    first_source_committed = Event()
    first_descriptor = RemoteFileDescriptor(
        name="sample-10k-a.htm",
        source_url="https://example.com/sample-10k-a.htm",
        http_etag="etag-a",
        http_last_modified=None,
        remote_size=None,
        http_status=200,
    )
    second_descriptor = RemoteFileDescriptor(
        name="sample-10k-b.htm",
        source_url="https://example.com/sample-10k-b.htm",
        http_etag="etag-b",
        http_last_modified=None,
        remote_size=None,
        http_status=200,
    )
    first_downloader = BarrierPrefetchDownloader(
        role="first",
        submissions=_build_single_filing_submissions(
            accession_number="0000000000-25-000001",
            primary_document=first_descriptor.name,
        ),
        remote_files=[first_descriptor],
        download_results=[
            {
                "name": first_descriptor.name,
                "status": "downloaded",
                "source_url": first_descriptor.source_url,
            }
        ],
        first_prefetch_payload=b"target-a",
        retry_payload=b"unused-a",
        second_prefetch_complete=second_prefetch_complete,
        first_source_committed=first_source_committed,
    )
    second_downloader = BarrierPrefetchDownloader(
        role="second",
        submissions=_build_single_filing_submissions(
            accession_number="0000000000-25-000002",
            primary_document=second_descriptor.name,
        ),
        remote_files=[second_descriptor],
        download_results=[
            {
                "name": second_descriptor.name,
                "status": "downloaded",
                "source_url": second_descriptor.source_url,
            }
        ],
        first_prefetch_payload=b"target-b",
        retry_payload=b"unused-b",
        second_prefetch_complete=second_prefetch_complete,
        first_source_committed=first_source_committed,
    )
    first_pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=first_downloader,
        processor_registry=build_fins_processor_registry(),
    )
    second_pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=second_downloader,
        processor_registry=build_fins_processor_registry(),
    )
    original_first_commit = first_pipeline._batching_repository.commit_batch

    def release_second_after_first_source(batch: BatchToken) -> None:
        """在 target A 真实 publication 后释放 target B。"""

        original_first_commit(batch)
        try:
            first_pipeline._source_repository.get_source_meta(
                "AAPL",
                "fil_0000000000-25-000001",
                SourceKind.FILING,
            )
        except FileNotFoundError:
            return
        first_source_committed.set()

    monkeypatch.setattr(
        first_pipeline._batching_repository,
        "commit_batch",
        release_second_after_first_source,
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(
            first_pipeline.download,
            "AAPL",
            overwrite=True,
            start_is_explicit=False,
        )
        second_future = executor.submit(
            second_pipeline.download,
            "AAPL",
            overwrite=True,
            start_is_explicit=False,
        )
        first_result = first_future.result(timeout=10)
        second_result = second_future.result(timeout=10)

    assert first_result["summary"]["downloaded"] == 1
    assert second_result["summary"]["downloaded"] == 1
    assert first_downloader.prefetch_rounds == 1
    assert second_downloader.prefetch_rounds == 1
    for document_id, expected in (
        ("fil_0000000000-25-000001", b"target-a"),
        ("fil_0000000000-25-000002", b"target-b"),
    ):
        with second_pipeline._source_repository.read_source_snapshot(
            "AAPL",
            document_id,
            SourceKind.FILING,
            materialize_files=True,
        ) as snapshot:
            with snapshot.get_primary_source().open() as stream:
                assert stream.read() == expected


def test_rejected_prefetch_cancelled_before_begin_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rejected prefetch 返回后取消必须发生在 begin_batch 前。"""

    descriptor = RemoteFileDescriptor(
        name="sample-6k.htm",
        source_url="https://example.com/sample-6k.htm",
        http_etag="etag-rejected",
        http_last_modified=None,
        remote_size=None,
        http_status=200,
    )
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=[descriptor],
        download_results=[
            {
                "name": descriptor.name,
                "status": "downloaded",
                "source_url": descriptor.source_url,
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    begin_called = False

    def observe_begin(ticker: str) -> BatchToken:
        """记录任何越过取消 gate 的 batch 开启。"""

        del ticker
        nonlocal begin_called
        begin_called = True
        raise AssertionError("取消后不得 begin_batch")

    monkeypatch.setattr(pipeline._batching_repository, "begin_batch", observe_begin)
    filing = _sec_filing_collection.FilingRecord(
        form_type="6-K",
        filing_date="2025-08-01",
        report_date="2024-12-31",
        accession_number="0000000000-25-000101",
        primary_document=descriptor.name,
    )

    with pytest.raises(SecDownloadCancelledError):
        asyncio.run(
            pipeline._persist_rejected_filing_artifact(
                ticker="TCOM",
                cik="320193",
                filing=filing,
                remote_files=[descriptor],
                overwrite=True,
                rejection_reason="6k_filtered",
                rejection_category="EXCLUDE_NON_QUARTERLY",
                selected_primary_document=descriptor.name,
                source_fingerprint="fingerprint",
                registry_after={},
                cancel_checker=lambda: True,
            )
        )

    assert downloader.download_files_called is True
    assert begin_called is False


def test_sec_selected_repair_that_6k_policy_rejects_fails_before_mutation(
    tmp_path: Path,
) -> None:
    """selected repair 在 6-K Phase A 被拒时必须保留全部 old facts。"""

    document_id = "fil_0000000000-25-000101"
    meta_path = _seed_complete_sec_source(
        workspace_root=tmp_path,
        ticker="TCOM",
        document_id=document_id,
    )
    payload_path = meta_path.parent / "sample-10k.htm"
    payload_path.write_bytes(payload_path.read_bytes() + b"-corrupt")
    old_meta = meta_path.read_bytes()
    old_payload = payload_path.read_bytes()
    descriptor = RemoteFileDescriptor(
        name="sample-6k.htm",
        source_url="https://example.com/sample-6k.htm",
        http_etag="etag-6k-reject",
        http_last_modified=None,
        remote_size=None,
        http_status=200,
    )
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=[descriptor],
        download_results=[
            {
                "name": descriptor.name,
                "status": "downloaded",
                "source_url": descriptor.source_url,
            }
        ],
        content_by_name={descriptor.name: b"Annual general meeting voting results."},
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    with pytest.raises(SourceIntegrityPreflightError) as exc_info:
        pipeline.download(ticker="TCOM", overwrite=False, start_is_explicit=False)

    assert exc_info.value.reason is SourceIntegrityPreflightReason.SELECTED_REJECTED_REPAIR_REQUIRED
    assert meta_path.read_bytes() == old_meta
    assert payload_path.read_bytes() == old_payload
    assert not _company_meta_path(tmp_path, "TCOM").exists()
    assert not _download_rejections_path(tmp_path, "TCOM").exists()
    assert not _rejected_meta_path(tmp_path, "TCOM", document_id).exists()
