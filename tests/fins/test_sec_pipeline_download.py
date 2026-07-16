"""SecPipeline 下载流程测试。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import json
import logging
import datetime as dt
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, cast

import pytest

from dayu.fins.downloaders.sec_downloader import (
    BrowseEdgarFiling,
    DownloaderEvent,
    RemoteFileDescriptor,
    Sc13PartyRoles,
    SecDownloader,
    StoreDownloadedFile,
    build_source_fingerprint,
)
from dayu.fins.domain.document_models import (
    BatchToken,
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
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines import sec_download_filing_workflow as _sec_download_filing_workflow
from dayu.fins.pipelines import sec_download_state as _sec_download_state
from dayu.fins.pipelines import sec_6k_primary_document_repair as _sec_6k_primary_repair
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
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.documents.processors.processor_registry import ProcessorRegistry


@dataclass(frozen=True, slots=True)
class _FiscalXbrlResult:
    """测试用最小 XBRL fiscal 投影。"""

    fiscal_year: int
    fiscal_period: str
    entity_info: dict[str, str]


@dataclass(slots=True)
class _FinancialStatementFixtureProcessor:
    """按 statement type 返回预设结果的 fiscal processor。"""

    results: dict[str, dict[str, JsonValue] | RuntimeError | str]

    def get_financial_statement(self, *, statement_type: str) -> dict[str, JsonValue]:
        """返回预设报表结果或抛出预设异常。

        Args:
            statement_type: 财务报表类型。

        Returns:
            预设报表 JSON。

        Raises:
            RuntimeError: 当前报表配置为失败时抛出。
        """

        result = self.results[statement_type]
        if isinstance(result, RuntimeError):
            raise result
        return cast(dict[str, JsonValue], result)


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
        self.document_id = document_id
        self.recorded_rebuild_values: list[bool] = []

    async def download_stream(
        self,
        ticker: str,
        form_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        overwrite: bool = False,
        rebuild: bool = False,
        *,
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
            cancel_checker: 取消检查器。

        Yields:
            单个完成事件。

        Raises:
            无。
        """

        del form_type, start_date, end_date, overwrite, cancel_checker
        self.recorded_rebuild_values.append(rebuild)
        result: sec_pipeline.SecPipelineDownloadResult = {
            "pipeline": "sec_download",
            "action": "download",
            "status": "ok",
            "ticker": ticker,
            "market_profile": {},
            "filters": {},
            "warnings": [],
            "filings": [{"document_id": self.document_id, "status": "downloaded"}],
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

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。

        Args:
            ticker: 股票代码。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 为空时抛出。
        """

        normalized = ticker.strip().upper()
        if not normalized:
            raise ValueError("ticker 不能为空")
        return normalized

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
            http_status = raw_http_status if isinstance(raw_http_status, int) and not isinstance(raw_http_status, bool) else None
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

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。

        Args:
            ticker: 股票代码。

        Returns:
            大写 ticker。

        Raises:
            ValueError: ticker 为空时抛出。
        """

        normalized = ticker.strip().upper()
        if not normalized:
            raise ValueError("ticker 不能为空")
        return normalized

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
        }
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
    result = pipeline.download(ticker="AAPL", overwrite=False)

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
    assert company_meta["ticker_aliases"] == ["AAPL", "APC"]


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
    )

    company_meta_path = _company_meta_path(tmp_path, "AAPL")
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker_aliases"] == ["AAPL", "APC", "AAPL.SW"]


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

    downloader = RebuildOnlyDownloader()
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(ticker=ticker, rebuild=True)

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
    assert rebuilt_processed_meta["reprocess_required"] is True

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
    processed_repository = FsProcessedDocumentRepository(
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
            processed_repository=processed_repository,
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
    processed_repository = FsProcessedDocumentRepository(
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
            processed_repository=processed_repository,
            ticker="AAPL",
            document_id="fil_0000000000-25-000001",
            previous_meta=_sec_rebuild_previous_meta(),
            company_meta=None,
            pipeline_download_version=SEC_PIPELINE_DOWNLOAD_VERSION,
        )

    assert exc_info.value is operation_error
    assert exc_info.value.__cause__ is rollback_error
    assert exc_info.value.__notes__ == [
        "rollback_batch failed; recovery evidence retained: "
        "injected rebuild rollback failure"
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
    processed_repository = FsProcessedDocumentRepository(
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
        processed_repository=processed_repository,
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

    pipeline.download(ticker="AAPL", overwrite=False)

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


def test_sec_fiscal_financial_payload_and_quality_contracts() -> None:
    """fiscal owner 应保留报表部分失败、XBRL 可用性与质量矩阵。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fiscal payload 或质量矩阵发生漂移时抛出。
    """

    processor = _FinancialStatementFixtureProcessor(
        results={
            "income": {
                "statement_type": "income",
                "rows": [{"label": "Revenue"}],
                "data_quality": "xbrl",
            },
            "balance_sheet": "invalid",
            "cash_flow": RuntimeError("cash unavailable"),
            "equity": {
                "statement_type": "equity",
                "rows": [],
                "data_quality": "partial",
            },
            "comprehensive_income": {
                "statement_type": "comprehensive_income",
                "rows": [],
                "data_quality": "partial",
            },
        }
    )

    payload, has_xbrl = _sec_fiscal_fields._build_financials_payload(processor)

    assert has_xbrl is True
    assert payload is not None
    statements = cast(dict[str, JsonValue], payload["statements"])
    assert cast(dict[str, JsonValue], statements["balance_sheet"])["reason"] == "invalid_statement_result"
    assert str(cast(dict[str, JsonValue], statements["cash_flow"])["reason"]).startswith("processor_error:")
    assert _sec_fiscal_fields._build_financials_payload(None) == (None, False)
    no_xbrl_payload, no_xbrl = _sec_fiscal_fields._build_financials_payload(
        _FinancialStatementFixtureProcessor(
            results={
                statement_type: {
                    "statement_type": statement_type,
                    "rows": [],
                    "data_quality": "partial",
                }
                for statement_type in _sec_fiscal_fields.FINANCIAL_STATEMENT_TYPES
            }
        )
    )
    assert (no_xbrl_payload, no_xbrl) == (None, False)
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
            "query_params": {},
            "facts": [{"fiscal_year": 2024, "fiscal_period": "FY"}],
            "total": 1,
            "data_quality": "xbrl",
            "reason": None,
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
    assert _sec_fiscal_fields._pick_download_xbrl_file(
        file_map,
        candidates=("_missing.xml",),
    ) is None
    assert _sec_fiscal_fields._pick_download_xbrl_file(
        file_map,
        candidates=("_missing.xml",),
        xml_fallback=True,
    ) == Path("b.xml")
    assert _sec_fiscal_fields._mapping_get_case_insensitive(
        {"DocumentFiscalYearFocus": "2024"},
        ("documentfiscalyearfocus",),
    ) == "2024"
    assert _sec_fiscal_fields._mapping_get_case_insensitive([], ("missing",)) is None
    assert _sec_fiscal_fields._pick_first_non_empty((None, " ", "FY")) == "FY"
    assert _sec_fiscal_fields._pick_first_non_empty((None, " ")) is None
    assert _sec_fiscal_fields._infer_download_fiscal_fields("10-K", "2024-12-31") == (2024, "FY")
    assert _sec_fiscal_fields._infer_download_fiscal_fields("6-K/A", "2024-12-31") == (None, None)
    assert _sec_fiscal_fields._resolve_fiscal_period_fallback(
        form_type="10-Q",
        fiscal_year=2024,
        fiscal_year_from_report_date=True,
    ) is None
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
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(
        _XbrlQueryFixtureProcessor({"facts": []})
    ) == (None, None)
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(
        _XbrlQueryFixtureProcessor(
            {
                "query_params": {},
                "facts": [
                    {"period_end": "2023-12-31"},
                    {"fiscal_year": 2024, "fiscal_period": "Q1"},
                ],
                "total": 2,
                "data_quality": "xbrl",
                "reason": None,
            }
        )
    ) == (2024, "Q1")
    assert _sec_fiscal_fields._extract_fiscal_from_xbrl_query(
        _XbrlQueryFixtureProcessor(
            {
                "query_params": {},
                "facts": [{"period_end": "2021-12-31"}],
                "total": 1,
                "data_quality": "xbrl",
                "reason": None,
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
    result = pipeline.download(ticker="AAPL", overwrite=False)

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
    result = pipeline.download(ticker="AAPL", overwrite=False)

    assert result["summary"]["skipped"] == 1
    assert result["summary"]["downloaded"] == 0
    assert downloader.download_files_called is False
    assert result["filings"][0]["skip_reason"] == "already_downloaded_complete"
    assert result["filings"][0]["reason_code"] == "already_downloaded_complete"


@pytest.mark.parametrize(
    ("existing_download_version", "expected_status", "expected_skip_reason"),
    [
        (SEC_PIPELINE_DOWNLOAD_VERSION, "skipped", "not_modified"),
        ("legacy-download-version", "downloaded", None),
        (None, "downloaded", None),
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
    result = pipeline.download(ticker="AAPL", overwrite=False)
    after_text = meta_path.read_text(encoding="utf-8")

    assert downloader.download_files_called is True
    assert result["filings"][0]["status"] == expected_status
    assert result["filings"][0].get("skip_reason") == expected_skip_reason
    if expected_skip_reason == "not_modified":
        assert result["summary"]["skipped"] == 1
        assert result["summary"]["downloaded"] == 0
        assert before_text == after_text
        assert result["filings"][0]["reason_code"] == "not_modified"
        assert "未修改" in str(result["filings"][0]["reason_message"])
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
    result = pipeline.download(ticker="AAPL", overwrite=False)

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
    result_skip = pipeline.download(ticker="AAPL", overwrite=False)
    assert result_skip["summary"]["skipped"] == 1
    assert result_skip["summary"]["downloaded"] == 0
    # 快速预检跳过时不应调用 list_filing_files（避免 SEC HEAD 请求）
    assert downloader.list_filing_files_call_count == 0

    # overwrite=True 仅替换当前目标文档，仍使用 previous_meta 递增版本。
    result = pipeline.download(ticker="AAPL", overwrite=True)

    assert result["summary"]["downloaded"] == 1
    updated_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated_meta["document_version"] == "v2"
    processed_meta = json.loads(processed_meta_path.read_text(encoding="utf-8"))
    # 目标文档替换时若 processed 快照存在，应标记 reprocess_required
    assert processed_meta["reprocess_required"] is True


def test_sec_cleanup_stale_filing_dirs_keeps_existing_docs_when_result_empty(tmp_path: Path) -> None:
    """本轮没有有效目标 document_id 时不得清理旧 filing。"""

    meta_path = _seed_complete_sec_source(
        workspace_root=tmp_path,
        document_id="fil_old",
    )
    repository_set = build_fs_repository_set(workspace_root=tmp_path)
    batching_repository = FsBatchingRepository(tmp_path, repository_set=repository_set)
    repository = FsFilingMaintenanceRepository(tmp_path, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")

    cleaned = sec_pipeline._cleanup_stale_filing_dirs(
        repository,
        "AAPL",
        {"10-K": dt.date(2024, 1, 1)},
        [],
        batch=batch,
    )
    batching_repository.commit_batch(batch)

    assert cleaned == 0
    assert meta_path.exists()


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
    result = pipeline.download(ticker="TCOM", overwrite=False)

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

    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["skipped"] == 0
    assert result["summary"]["rejected"] == 1
    assert (
        "美股下载完成: ticker=TCOM total=1 downloaded=0 skipped=0 rejected=1 failed=0"
        in caplog.text
    )
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
            source="sec",
            form_types=(),
            filed_after=None,
            filed_before=None,
            overwrite_existing=False,
            rebuild_processed=False,
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
        "filters": {},
        "warnings": [],
        "filings": [
            {
                "document_id": "fil-downloaded",
                "status": "downloaded",
            },
            {
                "document_id": "fil-already-complete",
                "status": "skipped",
                "skip_reason": "already_downloaded_complete",
                "reason_code": "already_downloaded_complete",
            },
            {
                "document_id": "fil-filtered-6k",
                "status": "skipped",
                "skip_reason": "6k_filtered",
                "reason_code": "6k_filtered",
            },
            {
                "document_id": "fil-failed",
                "status": "failed",
            },
            {
                "document_id": "fil-unknown-status",
                "status": "provider_new_status",
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

    summary = sec_pipeline._summary_from_pipeline_result(result)

    assert summary.discovered_count == 5
    assert summary.downloaded_count == 1
    assert summary.skipped_count == 1
    assert summary.rejected_count == 1
    assert summary.failed_count == 2
    assert summary.discovered_count == (
        summary.downloaded_count
        + summary.skipped_count
        + summary.rejected_count
        + summary.failed_count
    )
    assert (
        summary.discovered_count
        == summary.downloaded_count
        + summary.skipped_count
        + summary.rejected_count
        + summary.failed_count
    )


def test_sec_adapter_marks_processed_rebuild_for_written_documents(tmp_path: Path) -> None:
    """SEC adapter 应消费 rebuild_processed 并标记已写入文档的 processed。"""

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
            source="sec",
            form_types=("10-K",),
            filed_after=None,
            filed_before=None,
            overwrite_existing=False,
            rebuild_processed=True,
            cancellation_checker=_NeverCancelled(),
        )
    )

    processed_meta = pipeline._processed_repository.get_processed_meta("AAPL", document_id)

    assert pipeline.recorded_rebuild_values == [False]
    assert processed_meta["reprocess_required"] is True


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
    result = pipeline.download(ticker="TCOM", overwrite=False)

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
    result = pipeline.download(ticker="TCOM", overwrite=False)

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
            "sample-6k.htm": (
                b"FORM 6-K\nEXHIBIT INDEX\n"
                b"Exhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n"
            ),
            "d123dex991.htm": (
                b"Press Release\n"
                b"TCOM Announces Fourth Quarter and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False)

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
                b"FORM 6-K\n"
                b"Financial Results and Business Updates\n"
                b"Company reported strong quarterly performance\n"
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
    result = pipeline.download(ticker="ALVO", overwrite=False)

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
            "sample-6k.htm": (
                b"FORM 6-K\nEXHIBIT INDEX\n"
                b"Exhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n"
            ),
            "d123dex991.htm": (
                b"Press Release\n"
                b"TCOM Announces Fourth Quarter and Full Year 2024 Unaudited Financial Results\n"
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
        pipeline.download(ticker="TCOM", overwrite=False)

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
        target_tickers=[ticker, ticker.lower()],
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
    result = pipeline.download(ticker="AAPL", overwrite=False)

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
    result = pipeline.download(ticker="GS", form_type="SC13D/G", overwrite=False)

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
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

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
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

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

    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

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
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

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
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

    # 初始1年窗口找不到（2024-01-15 在1年+60天之外），重试后应找到
    assert result["summary"]["downloaded"] >= 1
    warnings = result.get("warnings") or []
    # 找到了 SC 13G，不应有缺失警告
    assert not any("SC 13D/G" in w for w in warnings)


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
    result = pipeline.download(ticker="AAPL", overwrite=False)

    # 最大重试后仍无 SC 13 → 应有缺失警告
    warnings = result.get("warnings") or []
    assert any("SC 13D/G" in w for w in warnings)
