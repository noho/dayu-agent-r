"""Fins ingestion runtime foundation 测试。"""

from __future__ import annotations

import io
import asyncio
import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import Event, Lock as ThreadingLock, Thread, current_thread, enumerate as enumerate_threads
from typing import cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.source import Source
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins import ticker_normalization
import dayu.fins.download_contract as download_contract
from dayu.fins.downloaders.sec_downloader import SEC_USER_AGENT_ENV
from dayu.fins.domain.enums import SourceKind
from dayu.fins import ingestion_runtime
from dayu.fins.direct_events import (
    FinsErrorKind,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsPublicFailureKind,
    FinsResultStatus,
)
from dayu.fins.direct_event_text import (
    direct_download_no_source_documents_message,
    direct_failure_message,
    direct_preprocess_no_requested_documents_message,
    direct_progress_message,
    direct_result_title,
    direct_upload_failed_status_message,
    direct_upload_runtime_unavailable_message,
    wait_cancelled_hint,
    wait_cancelled_message,
    wait_failed_hint,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadDocumentResult,
    FinsDownloadEffectiveFilters,
    FinsDownloadProviderError,
    FinsDownloadResultSummary,
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
    FinsDownloadTransportCategory,
    build_fins_download_request,
)
from dayu.fins.ingestion_events import (
    FinsIngestionJobEventAppend,
    FinsIngestionJobEventRecord,
    FinsIngestionJobEventType,
)
from dayu.fins.ingestion.observation_handle import (
    FinsObservationStatus,
)
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    FinsSourceProvider,
    FinsIngestMethod,
    ProcessedCreateRequest,
    RejectedFilingArtifactUpsertRequest,
    SourceDocumentRevision,
    SourceDocumentUpsertRequest,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.ingestion_runtime import (
    FinsDownloadedFile,
    FinsDownloadedSourceDocument,
    FinsDownloadProgressEvent,
    FinsJobCancellationChecker,
    FinsIngestionExecutor,
    FinsIngestionOperationKind,
    FinsIngestionJobStatus,
    FinsIngestionJobRecord,
    FinsPreprocessRequest,
    FinsPreprocessResultSummary,
    FinsPreprocessResultStatus,
    FinsRejectedFilingDownloadArtifact,
    FinsSourceDownloadAdapter,
    FinsSourceDownloadAdapterRequest,
    FinsSourceDownloadAdapterResult,
    FinsUploadFilingRequest,
    FinsUploadUsageCode,
    FinsUploadUsageError,
    ValidatedFinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadPipelineResult,
    FinsUploadResultSummary,
    FinsUploadRunner,
    FinsUploadTerminalDisposition,
    fins_upload_usage_failure,
    validate_fins_upload_filing_request,
)
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureKind,
    FinsUploadFailureReason,
    fins_upload_failure_from_exception,
)
from dayu.fins.pipelines.cn_pipeline import CnDownloadAdapter, CnPipeline
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConversionError,
    DoclingConversionFailureKind,
    DoclingConversionResult,
    ProcessDoclingConverter,
)
from dayu.fins.pipelines.sec_pipeline import SecDownloadAdapter, SecPipeline
from dayu.fins.service_runtime import DefaultFinsRuntime, ProductionFinsUploadRunner
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    DocumentBlobRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    FilingUploadPublishedState,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.ticker_normalization import NormalizedTicker
from dayu.fins.tools.read_runtime import FinsReadRuntime
import dayu.runtime.log as runtime_log


def test_failed_pipeline_result_requires_closed_typed_failure_reason() -> None:
    """failed pipeline JSON 必须携带 closed typed failure，非 failed 禁止携带。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: parser 接受缺失、未知、越界或错状态 failure 时抛出。
    """

    with pytest.raises(ValueError):
        FinsUploadPipelineResult.from_pipeline_json({"status": "failed"})
    with pytest.raises(ValueError):
        FinsUploadPipelineResult.from_pipeline_json(
            {
                "status": "ok",
                "failure": {
                    "kind": "runtime",
                    "code": "unexpected_runtime",
                    "message": "上传执行失败，请检查运行日志后重试",
                    "retry_hint": None,
                },
            }
        )
    result = FinsUploadPipelineResult.from_pipeline_json(
        {
            "status": "failed",
            "failure": {
                "kind": "content",
                "code": "docling_converter_execution",
                "message": "文件无法解析或已损坏，请检查文件后重试",
                "retry_hint": "请确认文件可正常打开并重新上传",
            },
        }
    )
    assert result.failure_reason is not None
    assert result.failure_reason.kind is FinsUploadFailureKind.CONTENT
    assert result.failure_reason.code is FinsUploadFailureCode.DOCLING_CONVERTER_EXECUTION


@pytest.mark.parametrize(
    ("kind", "safe_message", "expected_code"),
    (
        (
            DoclingConversionFailureKind.CONVERTER_CONSTRUCTION,
            "Docling converter construction failed",
            FinsUploadFailureCode.DOCLING_CONVERTER_CONSTRUCTION,
        ),
        (
            DoclingConversionFailureKind.CONVERTER_EXECUTION,
            "Docling conversion execution failed",
            FinsUploadFailureCode.DOCLING_CONVERTER_EXECUTION,
        ),
        (
            DoclingConversionFailureKind.RESULT_SERIALIZATION,
            "Docling conversion result serialization failed",
            FinsUploadFailureCode.DOCLING_RESULT_SERIALIZATION,
        ),
        (
            DoclingConversionFailureKind.IPC_PROTOCOL,
            "Docling conversion IPC protocol failed",
            FinsUploadFailureCode.DOCLING_IPC_PROTOCOL,
        ),
        (
            DoclingConversionFailureKind.CHILD_CRASH,
            "Docling conversion child crashed",
            FinsUploadFailureCode.DOCLING_CHILD_CRASH,
        ),
        (
            DoclingConversionFailureKind.CLEANUP,
            "Docling conversion cleanup failed",
            FinsUploadFailureCode.DOCLING_CLEANUP,
        ),
    ),
)
def test_upload_failure_mapper_exhaustively_maps_docling_kinds(
    kind: DoclingConversionFailureKind,
    safe_message: str,
    expected_code: FinsUploadFailureCode,
) -> None:
    """每个 Docling failure kind 必须映射到唯一 content code。

    Args:
        kind: Docling closed failure kind。
        safe_message: converter owner 的固定安全文案。
        expected_code: upload failure owner 的目标 code。

    Returns:
        无。

    Raises:
        AssertionError: kind、code 或 public 文案映射漂移时抛出。
    """

    reason = fins_upload_failure_from_exception(DoclingConversionError(kind, safe_message, None))

    assert reason.kind is FinsUploadFailureKind.CONTENT
    assert reason.code is expected_code
    assert reason.message == "文件无法解析或已损坏，请检查文件后重试"


@pytest.mark.parametrize(
    "failure",
    (
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
            "unknown": "forbidden",
        },
        {
            "kind": "unknown",
            "code": "unexpected_runtime",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
        },
        {
            "kind": "runtime",
            "code": "unknown",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
        },
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "workspace/private/report.pdf",
            "retry_hint": None,
        },
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "x\nsecret",
            "retry_hint": None,
        },
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "x" * 241,
            "retry_hint": None,
        },
    ),
)
def test_failed_pipeline_result_rejects_unsafe_or_open_failure_json(
    failure: dict[str, JsonValue],
) -> None:
    """failed parser 必须拒绝 open、未知、pathful、control 与过长 failure。

    Args:
        failure: 非法 failure JSON fixture。

    Returns:
        无。

    Raises:
        AssertionError: parser 未 fail closed 时抛出。
    """

    with pytest.raises(ValueError):
        FinsUploadPipelineResult.from_pipeline_json({"status": "failed", "failure": failure})


def _valid_runtime_filing_request(*, ticker: str = "AAPL") -> FinsUploadFilingRequest:
    """构造不依赖本地文件的合法 filing delete 请求。

    Args:
        ticker: 测试请求 ticker。

    Returns:
        满足统一 validation contract 的 filing request。

    Raises:
        无。
    """

    return FinsUploadFilingRequest(
        ticker=ticker,
        action="delete",
        fiscal_year=2024,
        fiscal_period="FY",
    )


def _runtime_failure_for_status(status: str) -> FinsUploadFailureReason | None:
    """为参数化 status 构造严格 runtime failure。

    Args:
        status: upload terminal status。

    Returns:
        failed 对应的 closed failure；其它状态返回 ``None``。

    Raises:
        无。
    """

    if status != "failed":
        return None
    return fins_upload_failure_from_exception(RuntimeError())


def test_fins_upload_usage_failure_mapping_is_closed_bounded_and_path_free() -> None:
    """usage code 到可行动文案的 mapping 必须穷尽、短小且不泄漏路径。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: code 集合、精确文案或安全边界漂移时抛出。
    """

    expected_codes = {
        "empty_ticker",
        "invalid_ticker",
        "invalid_ticker_alias",
        "invalid_source_kind",
        "invalid_action",
        "too_many_files",
        "missing_fiscal_year",
        "invalid_fiscal_year",
        "missing_fiscal_period",
        "fiscal_period_too_long",
        "unsupported_cn_fiscal_period",
        "filing_date_too_long",
        "report_date_too_long",
        "company_name_too_long",
        "too_many_ticker_aliases",
        "missing_files",
        "file_not_found",
        "file_not_regular",
        "file_suffix_not_allowed",
        "converter_suffix_unsupported",
        "company_name_required",
        "create_target_exists",
        "update_target_missing",
    }
    assert {code.value for code in FinsUploadUsageCode} == expected_codes
    exact_messages = {
        FinsUploadUsageCode.EMPTY_TICKER: "--ticker 不能为空，请提供公司代码",
        FinsUploadUsageCode.INVALID_TICKER: "--ticker 无法识别，请提供有效公司代码",
        FinsUploadUsageCode.MISSING_FISCAL_YEAR: "--fiscal-year 不能为空",
        FinsUploadUsageCode.MISSING_FISCAL_PERIOD: "--fiscal-period 不能为空",
        FinsUploadUsageCode.MISSING_FILES: "create/update 上传必须提供 --files",
        FinsUploadUsageCode.COMPANY_NAME_REQUIRED: "当前公司缺少有效元数据；create/update 必须提供 --company-name",
        FinsUploadUsageCode.INVALID_FISCAL_YEAR: "--fiscal-year 必须是非负整数",
        FinsUploadUsageCode.FISCAL_PERIOD_TOO_LONG: "--fiscal-period 长度不能超过 240 个字符",
        FinsUploadUsageCode.UNSUPPORTED_CN_FISCAL_PERIOD: "CN/HK --fiscal-period 仅支持 Q1、Q2、Q3、Q4、H1、FY",
    }
    for code in FinsUploadUsageCode:
        if code in {
            FinsUploadUsageCode.FILE_NOT_FOUND,
            FinsUploadUsageCode.FILE_NOT_REGULAR,
            FinsUploadUsageCode.FILE_SUFFIX_NOT_ALLOWED,
            FinsUploadUsageCode.CONVERTER_SUFFIX_UNSUPPORTED,
        }:
            failure = fins_upload_usage_failure(code, file_name="report.pdf")
        else:
            failure = fins_upload_usage_failure(code)
        assert failure.code is code
        assert 0 < len(failure.message) <= 240
        assert "/Users/" not in failure.message
        assert "\\" not in failure.message
        if code in exact_messages:
            assert failure.message == exact_messages[code]

    assert (
        fins_upload_usage_failure(
            FinsUploadUsageCode.FILE_NOT_FOUND,
            file_name="report.pdf",
        ).message
        == "上传文件不存在：report.pdf"
    )
    assert (
        fins_upload_usage_failure(
            FinsUploadUsageCode.FILE_NOT_REGULAR,
            file_name="report.pdf",
        ).message
        == "上传路径不是普通文件：report.pdf"
    )
    assert (
        fins_upload_usage_failure(
            FinsUploadUsageCode.FILE_SUFFIX_NOT_ALLOWED,
            file_name="report.exe",
        ).message
        == "上传文件后缀不在命令允许范围：report.exe"
    )
    assert (
        fins_upload_usage_failure(
            FinsUploadUsageCode.CONVERTER_SUFFIX_UNSUPPORTED,
            file_name="report.doc",
        ).message
        == "当前上传转换器不支持该文件后缀：report.doc"
    )


def test_validate_fins_upload_filing_request_resolves_state_aware_contract(
    tmp_path: Path,
) -> None:
    """validator 必须统一解析 identity、action、company decision 与 year 0 合法域。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: owner contract 未按 published state 解析时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"pdf")
    absent = FilingUploadPublishedState(company_meta=None, source_meta=None)
    request = FinsUploadFilingRequest(
        ticker="aapl.us",
        files=(upload_file,),
        fiscal_year=0,
        fiscal_period=" fy ",
        company_name="Apple Inc.",
    )

    validated = validate_fins_upload_filing_request(request, published_state=absent)

    assert validated.request is request
    assert validated.normalized_ticker.canonical == "AAPL"
    assert validated.normalized_fiscal_period == "FY"
    assert validated.resolved_action == "create"
    assert validated.published_state is absent
    assert validated.company_meta_decision.disposition == "stage"

    present = FilingUploadPublishedState(
        company_meta=validated.company_meta_decision.company_meta,
        source_meta={"source_fingerprint": "old"},
    )
    updated = validate_fins_upload_filing_request(
        replace(request, company_name=None),
        published_state=present,
    )
    assert updated.resolved_action == "update"
    assert updated.company_meta_decision.disposition == "keep"


@pytest.mark.parametrize("overwrite", (False, True))
def test_validate_fins_upload_filing_request_rejects_missing_explicit_update(
    tmp_path: Path,
    overwrite: bool,
) -> None:
    """显式 update 在目标缺失时不得由 overwrite 获得 upsert 权限。

    Args:
        tmp_path: pytest 临时目录。
        overwrite: 是否请求覆盖既有目标。

    Returns:
        无。

    Raises:
        AssertionError: owner 未返回精确 typed usage failure 时抛出。
    """

    upload_file = tmp_path / "report.txt"
    upload_file.write_text("report", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="update",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
        overwrite=overwrite,
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        validate_fins_upload_filing_request(
            request,
            published_state=FilingUploadPublishedState(company_meta=None, source_meta=None),
        )

    assert exc_info.value.failure.code is FinsUploadUsageCode.UPDATE_TARGET_MISSING
    assert exc_info.value.failure.message == "update 目标不存在；请改用 create"


@pytest.mark.parametrize(
    ("overwrite", "expected_code"),
    (
        (False, FinsUploadUsageCode.CREATE_TARGET_EXISTS),
        (True, None),
    ),
)
def test_validate_fins_upload_filing_request_limits_create_overwrite_to_existing_target(
    tmp_path: Path,
    overwrite: bool,
    expected_code: FinsUploadUsageCode | None,
) -> None:
    """create-existing 仅在显式 overwrite 时允许继续。

    Args:
        tmp_path: pytest 临时目录。
        overwrite: 是否请求覆盖既有目标。
        expected_code: 预期 typed failure code；允许时为 ``None``。

    Returns:
        无。

    Raises:
        AssertionError: create admission matrix 漂移时抛出。
    """

    upload_file = tmp_path / "report.txt"
    upload_file.write_text("report", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="create",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
        overwrite=overwrite,
    )
    published_state = FilingUploadPublishedState(
        company_meta=None,
        source_meta={"is_deleted": False, "source_fingerprint": "published"},
    )

    if expected_code is not None:
        with pytest.raises(FinsUploadUsageError) as exc_info:
            validate_fins_upload_filing_request(request, published_state=published_state)
        assert exc_info.value.failure.code is expected_code
        return

    validated = validate_fins_upload_filing_request(request, published_state=published_state)
    assert validated.resolved_action == "create"


def test_validate_fins_upload_filing_request_keeps_deleted_auto_identity_filename_independent(
    tmp_path: Path,
) -> None:
    """logical-deleted auto 必须解析 update，且 filing identity 不依赖文件名。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: action 或稳定 identity owner 漂移时抛出。
    """

    original_file = tmp_path / "report.txt"
    renamed_file = tmp_path / "renamed-report.txt"
    original_file.write_text("same filing", encoding="utf-8")
    renamed_file.write_text("same filing", encoding="utf-8")
    original_request = FinsUploadFilingRequest(
        ticker="aapl.us",
        files=(original_file,),
        fiscal_year=2024,
        fiscal_period=" fy ",
        company_name="Apple Inc.",
    )
    renamed_request = replace(original_request, files=(renamed_file,))
    deleted_state = FilingUploadPublishedState(
        company_meta=None,
        source_meta={"is_deleted": True, "source_fingerprint": "published"},
    )

    original = validate_fins_upload_filing_request(
        original_request,
        published_state=deleted_state,
    )
    renamed = validate_fins_upload_filing_request(
        renamed_request,
        published_state=deleted_state,
    )

    assert original.resolved_action == "update"
    assert renamed.resolved_action == "update"
    assert renamed.document_id == original.document_id
    assert renamed.internal_document_id == original.internal_document_id


@pytest.mark.parametrize(
    ("upload_request", "expected_code"),
    (
        (FinsUploadFilingRequest(ticker=""), FinsUploadUsageCode.EMPTY_TICKER),
        (FinsUploadFilingRequest(ticker="../../etc/passwd"), FinsUploadUsageCode.INVALID_TICKER),
        (
            FinsUploadFilingRequest(ticker="AAPL", fiscal_period="FY"),
            FinsUploadUsageCode.MISSING_FISCAL_YEAR,
        ),
        (
            FinsUploadFilingRequest(ticker="AAPL", fiscal_year=-1, fiscal_period="FY"),
            FinsUploadUsageCode.INVALID_FISCAL_YEAR,
        ),
        (
            FinsUploadFilingRequest(ticker="AAPL", fiscal_year=2024),
            FinsUploadUsageCode.MISSING_FISCAL_PERIOD,
        ),
        (
            FinsUploadFilingRequest(ticker="AAPL", fiscal_year=2024, fiscal_period="FY"),
            FinsUploadUsageCode.MISSING_FILES,
        ),
    ),
)
def test_validate_fins_upload_filing_request_preserves_validation_priority(
    upload_request: FinsUploadFilingRequest,
    expected_code: FinsUploadUsageCode,
) -> None:
    """冲突输入必须按 ticker→year→period→files 的 owner 顺序失败。

    Args:
        upload_request: 当前非法请求。
        expected_code: 预期首个 usage code。

    Returns:
        无。

    Raises:
        AssertionError: validator 返回错误优先级时抛出。
    """

    with pytest.raises(FinsUploadUsageError) as exc_info:
        validate_fins_upload_filing_request(
            upload_request,
            published_state=FilingUploadPublishedState(company_meta=None, source_meta=None),
        )
    assert exc_info.value.failure.code is expected_code


def test_default_runtime_create_and_ingestion_assembly_are_lazy(tmp_path: Path) -> None:
    """默认 runtime 构造与 ingestion 装配不得提前创建 workspace skeleton。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一装配步骤提前创建目录时抛出。
    """

    workspace_root = tmp_path / "lazy-workspace"

    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    assert not workspace_root.exists()

    runtime.get_ingestion_runtime()
    assert not workspace_root.exists()


def test_job_store_first_write_creates_root_but_missing_read_and_save_do_not(
    tmp_path: Path,
) -> None:
    """job store 仅由 create_job 首写创建目录，missing read/save 保持纯失败。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: missing 操作创建目录或 create_job 未创建目录时抛出。
    """

    workspace_root = tmp_path / "workspace"
    store = ingestion_runtime.FsFinsIngestionJobStore.from_workspace_root(workspace_root)
    record = FinsIngestionJobRecord(
        job_id="finsjob_00000000000000000000000000000001",
        operation_kind=FinsIngestionOperationKind.DOWNLOAD,
        normalized_ticker="AAPL",
        market="US",
        exchange=None,
        source="sec",
        source_kind=None,
        status=FinsIngestionJobStatus.QUEUED,
        created_at="2026-08-13T00:00:00+00:00",
        updated_at="2026-08-13T00:00:00+00:00",
        started_at=None,
        finished_at=None,
        request_summary={},
        result_summary={},
        failure_summary={},
        cancellation_requested=False,
    )

    with pytest.raises(FileNotFoundError):
        store.read_job(record.job_id)
    assert not workspace_root.exists()
    with pytest.raises(FileNotFoundError):
        store.save_job(record)
    assert not workspace_root.exists()

    assert store.create_job(record) == record
    assert store.root_dir.is_dir()


def _typed_download_summary(
    *,
    canonical_ticker: str = "AAPL",
    downloaded_ids: tuple[str, ...] = (),
    skipped_ids: tuple[str, ...] = (),
    rejected_ids: tuple[str, ...] = (),
    failed_ids: tuple[str, ...] = (),
    rebuild_local_artifacts: bool = False,
) -> FinsDownloadResultSummary:
    """构造满足 owner-level 守恒约束的测试下载摘要。

    Args:
        canonical_ticker: canonical ticker。
        downloaded_ids: 下载成功文档 ID。
        skipped_ids: 跳过文档 ID。
        rejected_ids: 拒绝文档 ID。
        failed_ids: 失败文档 ID。
        rebuild_local_artifacts: effective local rebuild 标记。

    Returns:
        计数与 typed rows 同源的下载摘要。

    Raises:
        ValueError: 输入违反生产契约时抛出。
    """

    rows = tuple(
        FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period="10-K",
            filing_date="2024-08-01",
            report_date="2024-06-30",
            covered_fiscal_periods=(),
            disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
            reason_category=None,
            reason_message=None,
            artifact_locator=PurePosixPath("source", document_id),
        )
        for document_id in downloaded_ids
    )
    rows += tuple(
        FinsDownloadDocumentResult(
            document_id=document_id,
            form_or_period="10-K",
            filing_date="2024-08-01",
            report_date="2024-06-30",
            covered_fiscal_periods=(),
            disposition=disposition,
            reason_category=reason_category,
            reason_message=reason_message,
            artifact_locator=None,
        )
        for disposition, reason_category, reason_message, document_ids in (
            (FinsDownloadDocumentDisposition.SKIPPED, "already_present", "本地已存在完整文档", skipped_ids),
            (FinsDownloadDocumentDisposition.REJECTED, "form_filter", "文档不符合筛选条件", rejected_ids),
            (FinsDownloadDocumentDisposition.FAILED, "provider_failure", "来源未能完成文档下载", failed_ids),
        )
        for document_id in document_ids
    )
    return FinsDownloadResultSummary.from_document_rows(
        source=FinsDownloadSource.SEC,
        canonical_ticker=canonical_ticker,
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=(),
            start_date=None,
            end_date=None,
            overwrite_existing=False,
            rebuild_local_artifacts=rebuild_local_artifacts,
        ),
        document_rows=rows,
    )


def test_public_download_json_preserves_cn_coverage_and_sec_empty_array() -> None:
    """runtime public projection 与 JSON serializer 原样保留 coverage array。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: CN coverage 被重算或 SEC 空数组缺失时抛出。
    """

    cn_row = FinsDownloadDocumentResult(
        document_id="fil-cn-q4",
        form_or_period="Q4",
        filing_date="2025-03-31",
        report_date=None,
        covered_fiscal_periods=("FY", "Q4"),
        disposition=FinsDownloadDocumentDisposition.SKIPPED,
        reason_category="already_present",
        reason_message="本地已有完整文档",
        artifact_locator=None,
    )
    cn_summary = FinsDownloadResultSummary.from_document_rows(
        source=FinsDownloadSource.HKEXNEWS,
        canonical_ticker="0005",
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=("FY", "H1"),
            start_date=None,
            end_date=None,
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        ),
        document_rows=(cn_row,),
        missing_periods=("FY", "H1"),
    )
    sec_summary = _typed_download_summary(canonical_ticker="AAPL", skipped_ids=("fil-sec",))

    cn_json = ingestion_runtime._public_download_summary(cn_summary).to_json_value()
    sec_json = ingestion_runtime._public_download_summary(sec_summary).to_json_value()
    cn_round_trip = json.loads(json.dumps(cn_json, ensure_ascii=False))
    sec_round_trip = json.loads(json.dumps(sec_json, ensure_ascii=False))

    assert cn_round_trip["documents"][0]["form_or_period"] == "Q4"
    assert cn_round_trip["documents"][0]["covered_fiscal_periods"] == ["FY", "Q4"]
    assert sec_round_trip["documents"][0]["form_or_period"] == "10-K"
    assert sec_round_trip["documents"][0]["covered_fiscal_periods"] == []


class _CommitFailingDownloadBatchingRepository(FsBatchingRepository):
    """模拟 storage 消费 token 后抛出 generic download commit 异常。"""

    def __init__(self, workspace_root: Path, repository_set: _FsRepositorySet) -> None:
        """初始化 commit failure batching spy。"""

        super().__init__(workspace_root, repository_set=repository_set)
        self.caller_rollback_calls = 0

    def commit_batch(self, batch: BatchToken) -> None:
        """由 storage owner 回滚并消费 token 后抛出 commit 主异常。"""

        FsBatchingRepository.rollback_batch(self, batch)
        raise OSError("forced generic commit failure")

    def rollback_batch(self, batch: BatchToken) -> None:
        """记录不应发生的 caller 二次 rollback。"""

        self.caller_rollback_calls += 1
        super().rollback_batch(batch)


class _RollbackFailingIngestionBatchingRepository(FsBatchingRepository):
    """执行真实 ingestion rollback 后注入指定次级失败并记录调用次数。"""

    def __init__(
        self,
        workspace_root: Path,
        repository_set: _FsRepositorySet,
        rollback_error: BaseException,
    ) -> None:
        """初始化 rollback failure batching spy。

        Args:
            workspace_root: 测试工作区根目录。
            repository_set: 与 ingestion repositories 共享的 repository set。
            rollback_error: 真实 rollback 完成后抛出的次级异常。

        Returns:
            无。

        Raises:
            OSError: 仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.rollback_error = rollback_error
        self.rollback_calls = 0

    def rollback_batch(self, batch: BatchToken) -> None:
        """执行并记录真实 rollback，随后抛出预置次级异常。

        Args:
            batch: 当前 shared core 登记的 open batch capability。

        Returns:
            不返回；始终抛出预置异常。

        Raises:
            BaseException: 初始化时提供的 rollback 次级异常。
            OSError: 真实 rollback 失败时抛出。
            ValueError: batch capability 非法时抛出。
        """

        self.rollback_calls += 1
        super().rollback_batch(batch)
        raise self.rollback_error


class _RejectedArtifactUpsertFailure:
    """在 rejected artifact owner mutation 边界抛出指定 operation 异常。"""

    def __init__(self, operation_error: BaseException) -> None:
        """保存需要原样抛出的 operation 异常。

        Args:
            operation_error: rejected artifact upsert 时抛出的主异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.operation_error = operation_error

    def __call__(
        self,
        request: RejectedFilingArtifactUpsertRequest,
        *,
        batch: BatchToken,
    ) -> None:
        """接收真实 mutation 输入后抛出预置 operation 异常。

        Args:
            request: rejected filing artifact upsert 请求。
            batch: caller-owned batch capability。

        Returns:
            不返回；始终抛出预置异常。

        Raises:
            BaseException: 初始化时提供的 operation 异常。
        """

        del request, batch
        raise self.operation_error


class _ProcessedCreateFailure:
    """在 preprocess processed-create owner 边界抛出指定 operation 异常。"""

    def __init__(self, operation_error: BaseException) -> None:
        """保存需要原样抛出的 operation 异常。

        Args:
            operation_error: processed create 时抛出的主异常。

        Returns:
            无。

        Raises:
            无。
        """

        self.operation_error = operation_error

    def __call__(
        self,
        request: ProcessedCreateRequest,
        *,
        batch: BatchToken,
    ) -> None:
        """接收真实 preprocess mutation 输入后抛出预置 operation 异常。

        Args:
            request: processed create 请求。
            batch: caller-owned batch capability。

        Returns:
            不返回；始终抛出预置异常。

        Raises:
            BaseException: 初始化时提供的 operation 异常。
        """

        del request, batch
        raise self.operation_error


def test_direct_event_text_helper_owns_result_titles_and_failure_messages() -> None:
    """direct 文案 helper 应统一选择 result 标题与失败说明。"""

    assert (
        direct_result_title(
            operation_kind=FinsOperationKind.DOWNLOAD,
            status=FinsResultStatus.SUCCESS,
        )
        == "操作完成"
    )
    assert (
        direct_result_title(
            operation_kind=FinsOperationKind.DOWNLOAD,
            status=FinsResultStatus.FAILURE,
        )
        == "下载失败"
    )
    assert (
        direct_result_title(
            operation_kind=FinsOperationKind.PROCESS_MATERIAL,
            status=FinsResultStatus.FAILURE,
        )
        == "预处理失败"
    )
    assert (
        direct_result_title(
            operation_kind=FinsOperationKind.UPLOAD_FILING,
            status=FinsResultStatus.CANCELLED,
        )
        == "操作已取消"
    )
    assert (
        direct_failure_message(
            error_kind=FinsErrorKind.STORAGE,
            fallback_message=None,
        )
        == "财报资料读写失败"
    )
    assert (
        direct_failure_message(
            error_kind=FinsErrorKind.PROVIDER,
            fallback_message="  provider failed safely  ",
        )
        == "provider failed safely"
    )
    assert direct_download_no_source_documents_message() == "下载请求未写入任何源文档"
    assert direct_preprocess_no_requested_documents_message() == "没有任何请求文档完成预处理"
    assert direct_upload_failed_status_message() == "上传运行时返回失败状态"
    assert direct_upload_runtime_unavailable_message() == "当前环境未装配财报上传能力"


def test_direct_event_text_helper_owns_progress_and_wait_copy() -> None:
    """direct/wait 文案 helper 应输出业务可读文案且不暴露内部等待术语。"""

    assert direct_progress_message(stage="download.preparing") == "下载准备中"
    assert direct_progress_message(stage="download.completed_with_failures") == "下载已完成，存在失败候选"
    assert direct_progress_message(stage="preprocess.document_not_supported") == "预处理源文档不支持"
    assert direct_progress_message(stage="upload.completed_with_failures") == "上传已完成，存在失败"
    assert direct_progress_message(stage="unknown.stage") == "财报处理进度已更新"
    assert wait_failed_hint() == "请检查财报处理摘要，必要时重新发起对应操作。"
    assert wait_cancelled_message() == "财报处理已取消。"
    assert wait_cancelled_hint() == "如仍需要该财报资料，请重新发起对应操作。"
    visible_wait_text = " ".join((wait_failed_hint(), wait_cancelled_message(), wait_cancelled_hint()))
    for forbidden in ("Host", "Engine", "wait", "poll", "runtime", "Fins ingestion"):
        assert forbidden not in visible_wait_text


class _HoldingExecutor(FinsIngestionExecutor):
    """测试用延迟执行器。"""

    def __init__(self) -> None:
        """初始化待执行操作列表。

        Args:
            无。

        Returns:
            无。
        """

        self.operations: list[Callable[[], None]] = []

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """记录后台操作但不立即执行。

        Args:
            job_id: opaque job id。
            operation: 待执行操作。

        Returns:
            无。

        Raises:
            无。
        """

        del job_id
        self.operations.append(operation)

    def run_all(self) -> None:
        """执行全部待执行操作。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        operations = tuple(self.operations)
        self.operations.clear()
        for operation in operations:
            operation()


class _FailingSubmitExecutor(FinsIngestionExecutor):
    """测试用提交失败执行器。"""

    def __init__(self, exc: Exception) -> None:
        """初始化提交异常。

        Args:
            exc: submit 时抛出的异常。

        Returns:
            无。
        """

        self.exc = exc
        self.submitted_job_ids: tuple[str, ...] = ()

    def submit(self, job_id: str, operation: Callable[[], None]) -> None:
        """记录提交并抛出预设异常。

        Args:
            job_id: opaque job id。
            operation: 待执行操作。

        Returns:
            无。

        Raises:
            Exception: 始终抛出初始化传入的异常。
        """

        del operation
        self.submitted_job_ids = self.submitted_job_ids + (job_id,)
        raise self.exc


class _HookedObservationLock:
    """可控阻塞的 observation lock，用于证明 cancel/activate 共用锁。"""

    def __init__(self) -> None:
        """初始化同步事件。

        Args:
            无。

        Returns:
            无。
        """

        self._lock = ThreadingLock()
        self.first_entered = Event()
        self.allow_first_exit = Event()
        self.second_enter_attempted = Event()
        self.enter_attempts = 0

    def __enter__(self) -> "_HookedObservationLock":
        """进入锁并在第一次进入后阻塞。

        Returns:
            当前锁对象。

        Raises:
            无。
        """

        self.enter_attempts += 1
        if self.enter_attempts == 2:
            self.second_enter_attempted.set()
        self._lock.acquire()
        if self.enter_attempts == 1:
            self.first_entered.set()
            self.allow_first_exit.wait()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        """释放锁。

        Args:
            exc_type: 异常类型。
            exc: 异常对象。
            traceback: traceback 对象。

        Returns:
            无。

        Raises:
            无。
        """

        del exc_type, exc, traceback
        self._lock.release()


class _FakeDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用确定性无网络下载 adapter。"""

    def __init__(self, *, include_rejected: bool = False) -> None:
        """初始化 fake adapter。

        Args:
            include_rejected: 是否返回一个 rejected filing artifact。

        Returns:
            无。
        """

        self.include_rejected = include_rejected
        self.requests: list[FinsSourceDownloadAdapterRequest] = []

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """返回确定性下载结果。

        Args:
            request: 已归一化下载请求。

        Returns:
            fake 下载结果。

        Raises:
            无。
        """

        self.requests.append(request)
        document_id = f"{request.normalized_ticker.canonical.lower()}-fake-10k"
        document = FinsDownloadedSourceDocument(
            source_kind=SourceKind.FILING,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document=f"{document_id}.md",
            meta={
                "form_type": "10-K",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "amended": False,
                "ingest_method": FinsIngestMethod.DOWNLOAD.to_storage_value(),
                "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
            },
            files=(
                FinsDownloadedFile(
                    filename=f"{document_id}.md",
                    content=b"# Fake 10-K\n\nRevenue increased.",
                    content_type="text/markdown",
                    metadata={"source": request.source},
                ),
            ),
        )
        rejected_artifacts: tuple[FinsRejectedFilingDownloadArtifact, ...] = ()
        if self.include_rejected:
            rejected_artifacts = (
                FinsRejectedFilingDownloadArtifact(
                    document_id=f"{request.normalized_ticker.canonical.lower()}-fake-rejected",
                    internal_document_id="fake-rejected-internal",
                    accession_number="0000000000-24-000001",
                    company_id=f"{request.normalized_ticker.canonical}_US",
                    form_type="8-K",
                    filing_date="2024-08-01",
                    report_date=None,
                    primary_document="rejected.htm",
                    selected_primary_document="rejected.htm",
                    rejection_reason="表单类型不在请求范围内",
                    rejection_category="form_filter",
                    source_fingerprint="fake-rejected-fingerprint",
                    files=(
                        FinsDownloadedFile(
                            filename="rejected.htm",
                            content=b"<html>rejected</html>",
                            content_type="text/html",
                        ),
                    ),
                ),
            )
        return FinsSourceDownloadAdapterResult(
            discovered_count=1 + len(rejected_artifacts),
            documents=(document,),
            rejected_artifacts=rejected_artifacts,
        )


class _PersistedSummaryDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用 persisted-summary 下载 adapter。"""

    def __init__(self, summary: FinsDownloadResultSummary | None = None) -> None:
        """初始化请求记录。

        Args:
            summary: 可选的固定下载摘要；为空时使用默认 skipped 摘要。

        Returns:
            无。
        """

        self.requests: list[FinsSourceDownloadAdapterRequest] = []
        self.summary = summary or _typed_download_summary(skipped_ids=("aapl-existing-10k",))

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """记录请求并返回已持久化摘要。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            只包含 persisted summary 的 adapter 结果。

        Raises:
            无。
        """

        self.requests.append(request)
        return FinsSourceDownloadAdapterResult(discovered_count=1, persisted_summary=self.summary)


class _ProviderFailureDownloadAdapter(FinsSourceDownloadAdapter):
    """抛出 owner-mapped provider transport error 的测试 adapter。"""

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """抛出不携带底层敏感内容的 typed provider failure。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            永不返回。

        Raises:
            FinsDownloadProviderError: 固定 connection 分类失败。
        """

        assert request.source is FinsDownloadSource.SEC
        raw_error = RuntimeError("contact-canary@example.invalid https://provider.invalid /Users/private/raw.json")
        raise FinsDownloadProviderError(
            source=FinsDownloadSource.SEC,
            transport_category=FinsDownloadTransportCategory.CONNECTION,
            retryable=True,
            safe_message="无法连接 SEC 来源",
        ) from raw_error


class _OperationFailureDownloadAdapter(FinsSourceDownloadAdapter):
    """原样抛出预构造 storage/execution exception 的测试 adapter。"""

    def __init__(self, failure: Exception) -> None:
        """保存 adapter 调用时应抛出的异常。

        Args:
            failure: 预构造 owner exception。

        Raises:
            无。
        """

        self.failure = failure

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """原样抛出预构造异常。

        Args:
            request: runtime typed request。

        Returns:
            永不返回。

        Raises:
            Exception: 预构造 owner exception。
        """

        del request
        raise self.failure


class _ProgressReportingDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用会通过 progress sink 上报文件级进度的 adapter。"""

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """上报文件进度并返回 persisted summary。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            固定 persisted summary。

        Raises:
            无。
        """

        if request.progress_sink is not None:
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.file_started",
                    message="开始下载",
                    document_id="fil-test",
                    file_name="sample-10k.htm",
                )
            )
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.conversion_started",
                    message="开始转换文档",
                    document_id="fil-test",
                    file_name="sample-10k_docling.json",
                )
            )
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.conversion_completed",
                    message="完成转换文档",
                    document_id="fil-test",
                    file_name="sample-10k_docling.json",
                )
            )
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.file_completed",
                    message="完成下载",
                    document_id="fil-test",
                    file_name="sample-10k.htm",
                )
            )
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=_typed_download_summary(downloaded_ids=("fil-test",)),
        )


class _CancellationAwareDownloadAdapter(FinsSourceDownloadAdapter):
    """测试用会观察取消检查器的下载 adapter。"""

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """执行两次取消检查后返回 persisted summary。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            固定 persisted summary。

        Raises:
            无。
        """

        request.cancellation_checker()
        request.cancellation_checker()
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=_typed_download_summary(downloaded_ids=("aapl-cancel-aware-10k",)),
        )


class _ConsumerAbortDownloadAdapter(FinsSourceDownloadAdapter):
    """以同步 barrier 观察 direct consumer abort 取消因果链的 adapter。"""

    def __init__(self) -> None:
        """初始化 adapter 的跨线程观察信号。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.entered = Event()
        self.allow_cancellation_check = Event()
        self.cancellation_checks: tuple[bool, ...] = ()
        self.late_progress_returned = Event()
        self.producer_thread_name: str | None = None
        self.producer_thread_ident: int | None = None
        self.producer_thread: Thread | None = None

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """等待 consumer abort，再观察取消并尝试一次 late progress。

        Args:
            request: runtime 传入的下载请求。

        Returns:
            固定 persisted summary。

        Raises:
            TimeoutError: 测试没有在边界内释放 cancellation check 时抛出。
            ValueError: late progress 事件违反 typed contract 时抛出。
        """

        producer_thread = current_thread()
        self.producer_thread = producer_thread
        self.producer_thread_name = producer_thread.name
        self.producer_thread_ident = producer_thread.ident
        self.entered.set()
        if not self.allow_cancellation_check.wait(timeout=1.0):
            raise TimeoutError("consumer abort cancellation check was not released")
        self.cancellation_checks = self.cancellation_checks + (request.cancellation_checker(),)
        if request.progress_sink is not None:
            request.progress_sink(
                FinsDownloadProgressEvent(
                    stage="download.late_after_abort",
                    message="consumer abort 后的迟到进度",
                    document_id="fil-late-after-abort",
                    file_name="late-after-abort.htm",
                )
            )
        self.late_progress_returned.set()
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=_typed_download_summary(downloaded_ids=("fil-late-after-abort",)),
        )


class _FakeUploadRunner(FinsUploadRunner):
    """测试用确定性上传 runner。"""

    def __init__(self, result_summary: FinsUploadResultSummary) -> None:
        """初始化 fake 上传 runner。

        Args:
            result_summary: 每次 run_upload 返回的确定性结果摘要。

        Returns:
            无。
        """

        self.result_summary = result_summary
        self.requests: list[ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest] = []
        self.cancellation_checks: list[bool] = []
        self.cancellation_tokens: list[FinsJobCancellationChecker] = []

    def run_upload(
        self,
        request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """记录上传请求并返回确定性结果摘要。

        Args:
            request: runtime 传入的上传请求。
            cancellation_checker: runtime 提供的取消检查器。

        Returns:
            初始化时传入的结果摘要。

        Raises:
            OSError: 取消检查器读取 job store 失败时由检查器抛出。
            ValueError: job record 非法时由检查器抛出。
        """

        self.requests.append(request)
        self.cancellation_tokens.append(cancellation_checker)
        self.cancellation_checks.append(cancellation_checker())
        return self.result_summary


class _BarrierUploadRunner(FinsUploadRunner):
    """用同步 barrier 控制 final checkpoint 或 commit 后窗口的上传 runner。"""

    def __init__(
        self,
        *,
        accepted_summary: FinsUploadResultSummary,
        observe_cancel_before_summary: bool,
    ) -> None:
        """初始化可控上传边界。

        Args:
            accepted_summary: 未在 final checkpoint 接受取消时返回的 summary。
            observe_cancel_before_summary: 释放 barrier 后是否执行 final cancellation checkpoint。

        Returns:
            无。

        Raises:
            无。
        """

        self.accepted_summary = accepted_summary
        self.observe_cancel_before_summary = observe_cancel_before_summary
        self.boundary_reached = Event()
        self.release_summary = Event()

    def run_upload(
        self,
        request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """在测试指定的 final checkpoint 或 commit 后边界返回 summary。

        Args:
            request: runtime 传入的上传请求。
            cancellation_checker: runtime 提供的 canonical 取消检查器。

        Returns:
            final checkpoint 前取消时返回 cancelled，否则返回 accepted summary。

        Raises:
            TimeoutError: 测试未在有界期限内释放 barrier 时抛出。
        """

        self.boundary_reached.set()
        if not self.release_summary.wait(timeout=1.0):
            raise TimeoutError("upload summary barrier 未释放")
        if self.observe_cancel_before_summary and cancellation_checker():
            raw_request = request.request if isinstance(request, ValidatedFinsUploadFilingRequest) else request
            return FinsUploadResultSummary(
                source_kind=raw_request.source_kind,
                status="cancelled",
            )
        return self.accepted_summary


class _BlockingArtifactUploadRunner(FinsUploadRunner):
    """写入源文档后阻塞的 observed upload runner。"""

    def __init__(
        self,
        *,
        batching_repository: BatchingRepositoryProtocol,
        source_repository: SourceDocumentRepositoryProtocol,
        blob_repository: DocumentBlobRepositoryProtocol,
        document_id: str,
    ) -> None:
        """初始化 runner。

        Args:
            batching_repository: batch lifecycle 唯一仓储。
            source_repository: Fins 源文档仓储协议实现。
            blob_repository: Fins blob 仓储协议实现。
            document_id: 测试写入的源文档 id。

        Returns:
            无。
        """

        self.batching_repository = batching_repository
        self.source_repository = source_repository
        self.blob_repository = blob_repository
        self.document_id = document_id
        self.artifact_written = Event()
        self.allow_finish = Event()
        self.cancellation_checks: tuple[bool, ...] = ()
        self.requests: tuple[ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest, ...] = ()

    def run_upload(
        self,
        request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """写入源文档后等待测试释放，并记录取消检查结果。

        Args:
            request: runtime 传入的上传请求。
            cancellation_checker: runtime 提供的取消检查器。

        Returns:
            fake 上传摘要。

        Raises:
            OSError: 仓储写入或取消检查失败时抛出。
            ValueError: 源文档字段非法时抛出。
        """

        self.requests = self.requests + (request,)
        raw_request = request.request if isinstance(request, ValidatedFinsUploadFilingRequest) else request
        batch = self.batching_repository.begin_batch(raw_request.ticker)
        try:
            filename = f"{self.document_id}.md"
            file_meta = self.blob_repository.store_file(
                SourceHandle(
                    ticker=raw_request.ticker,
                    document_id=self.document_id,
                    source_kind=SourceKind.FILING.value,
                ),
                filename,
                io.BytesIO(b"# observed upload fixture"),
                batch=batch,
                content_type="text/markdown",
            )
            self.source_repository.create_source_document(
                SourceDocumentUpsertRequest(
                    ticker=raw_request.ticker,
                    document_id=self.document_id,
                    internal_document_id=self.document_id,
                    form_type="10-K",
                    primary_document=filename,
                    meta={
                        "fiscal_year": 2024,
                        "fiscal_period": "FY",
                        "filing_date": "2024-11-01",
                        "report_date": "2024-09-28",
                        "amended": False,
                        "ingest_method": "upload",
                        "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                    },
                    files=[file_meta],
                ),
                SourceKind.FILING,
                batch=batch,
            )
        except BaseException:
            self.batching_repository.rollback_batch(batch)
            raise
        self.batching_repository.commit_batch(batch)
        self.artifact_written.set()
        self.allow_finish.wait(timeout=1.0)
        self.cancellation_checks = self.cancellation_checks + (cancellation_checker(),)
        return FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id=self.document_id,
            internal_document_id=self.document_id,
            status="ok",
            uploaded_files=(f"{self.document_id}.md",),
            primary_document=f"{self.document_id}.md",
        )


class _UploadRuntimeConverter:
    """runtime production upload 测试用 typed Docling converter。"""

    async def convert_to_json_bytes(
        self,
        input_bytes: bytes,
        stream_name: str,
        *,
        config: DoclingConversionConfig,
        cancellation: CancellationToken | None,
    ) -> DoclingConversionResult:
        """返回固定 Docling JSON bytes。

        Args:
            input_bytes: 上传文件字节。
            stream_name: 上传文件名。
            config: 闭合转换配置。
            cancellation: canonical token。

        Returns:
            typed conversion result。

        Raises:
            无。
        """

        del input_bytes, config, cancellation
        data = ('{"name": "' + stream_name + '", "format": "docling"}').encode()
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


def _inject_upload_runtime_converter(
    default_runtime: DefaultFinsRuntime,
    runtime: ingestion_runtime.FinsIngestionRuntime,
) -> None:
    """通过 public constructor injection 替换测试 upload runner。

    Args:
        default_runtime: 持有共享 repositories 的默认运行时。
        runtime: 待装配 production runner 的 ingestion runtime。

    Returns:
        无。

    Raises:
        OSError: pipeline 初始化失败时抛出。
    """

    converter = _UploadRuntimeConverter()
    runtime.upload_runner = ProductionFinsUploadRunner(
        sec_pipeline=SecPipeline(
            workspace_root=default_runtime.workspace_root,
            processor_registry=default_runtime.processor_registry,
            batching_repository=default_runtime.batching_repository,
            company_repository=default_runtime.company_repository,
            source_repository=default_runtime.source_repository,
            processed_repository=default_runtime.processed_repository,
            blob_repository=default_runtime.blob_repository,
            filing_maintenance_repository=default_runtime.filing_maintenance_repository,
            filing_upload_state_repository=default_runtime.filing_upload_state_repository,
            docling_converter=converter,
        ),
        cn_pipeline=CnPipeline(
            workspace_root=default_runtime.workspace_root,
            batching_repository=default_runtime.batching_repository,
            company_repository=default_runtime.company_repository,
            source_repository=default_runtime.source_repository,
            processed_repository=default_runtime.processed_repository,
            blob_repository=default_runtime.blob_repository,
            filing_maintenance_repository=default_runtime.filing_maintenance_repository,
            filing_upload_state_repository=default_runtime.filing_upload_state_repository,
            docling_converter=converter,
        ),
    )


def test_default_runtime_composition_shares_upload_state_and_docling_converter(tmp_path: Path) -> None:
    """production composition 必须共享 state repository 与 interruptible converter。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: runtime 缓存、repository 或 converter identity 漂移时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=tmp_path / "fins-workspace")
    ingestion = default_runtime.get_ingestion_runtime()
    repeated = default_runtime.get_ingestion_runtime()
    runner = ingestion.upload_runner

    assert repeated is ingestion
    assert isinstance(runner, ProductionFinsUploadRunner)
    assert runner.sec_pipeline._filing_upload_state_repository is default_runtime.filing_upload_state_repository
    assert runner.cn_pipeline._filing_upload_state_repository is default_runtime.filing_upload_state_repository

    converter = runner.cn_pipeline._docling_converter
    assert isinstance(converter, ProcessDoclingConverter)
    assert runner.sec_pipeline._upload_service._docling_converter is converter
    cn_adapter = ingestion.download_adapters[("cninfo", "CN")]
    hk_adapter = ingestion.download_adapters[("hkexnews", "HK")]
    assert isinstance(cn_adapter, CnDownloadAdapter)
    assert isinstance(hk_adapter, CnDownloadAdapter)
    assert cn_adapter._pipeline._docling_converter is converter
    assert hk_adapter._pipeline._docling_converter is converter


class _CancelOnSecondCheckToken(CancellationToken):
    """第二次 checkpoint 开始返回已取消的测试 token。"""

    def __init__(self) -> None:
        """初始化 checkpoint 计数。

        Args:
            无。

        Returns:
            无。
        """

        self.check_count = 0
        self._cancelled = False
        self._requested_at = datetime(2026, 6, 8, tzinfo=timezone.utc)

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        Returns:
            第一次返回 ``False``，第二次及之后返回 ``True``。
        """

        self.check_count += 1
        if self.check_count >= 2:
            self._cancelled = True
        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            取消被观察后返回测试原因，否则返回 ``None``。
        """

        if self._cancelled:
            return "host-cancelled"
        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            取消被观察后返回测试请求时间，否则返回 ``None``。
        """

        if self._cancelled:
            return self._requested_at
        return None


class _NeverCancelledToken(CancellationToken):
    """始终未取消的测试 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        Returns:
            始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            始终返回 ``None``。
        """

        return None


class _MutableCancellationToken(CancellationToken):
    """由测试 barrier 显式请求取消的 token。"""

    def __init__(self, *, cancelled: bool = False) -> None:
        """初始化取消状态。

        Args:
            cancelled: 是否从首个 checkpoint 开始已取消。

        Returns:
            无。

        Raises:
            无。
        """

        self._cancelled = Event()
        if cancelled:
            self._cancelled.set()

    def request_cancel(self) -> None:
        """请求取消。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._cancelled.set()

    def is_cancelled(self) -> bool:
        """返回当前取消状态。

        Returns:
            已请求取消时返回 ``True``。
        """

        return self._cancelled.is_set()

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Returns:
            已取消时返回固定原因，否则返回 ``None``。
        """

        return "test-cancelled" if self.is_cancelled() else None

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Returns:
            已取消时返回固定 UTC 时间，否则返回 ``None``。
        """

        if not self.is_cancelled():
            return None
        return datetime(2026, 8, 10, tzinfo=timezone.utc)


class _CancellationThenFailureDownloadAdapter(FinsSourceDownloadAdapter):
    """在取消 barrier 后抛出 provider 异常的竞态测试 adapter。"""

    def __init__(self) -> None:
        """初始化跨线程 barrier 与 producer 证据。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.entered = Event()
        self.release_failure = Event()
        self.producer_thread_ident: int | None = None
        self.producer_thread: Thread | None = None

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """等待 owner 请求取消后抛出迟到失败。

        Args:
            request: runtime 传入的 typed request。

        Returns:
            永不返回。

        Raises:
            TimeoutError: 测试未在有界时间内释放 barrier。
            RuntimeError: 固定的迟到 provider 失败。
        """

        del request
        self.producer_thread = current_thread()
        self.producer_thread_ident = self.producer_thread.ident
        self.entered.set()
        if not self.release_failure.wait(timeout=1.0):
            raise TimeoutError("late provider failure barrier was not released")
        raise RuntimeError("late provider failure")


class _ConsumerTaskCancelledDownloadAdapter(FinsSourceDownloadAdapter):
    """在有界轮询中观察 consumer task cancellation 的 adapter。"""

    def __init__(self) -> None:
        """初始化 ready/observed/finished barriers 与线程证据。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.entered = Event()
        self.cancellation_observed = Event()
        self.finished = Event()
        self.producer_thread_ident: int | None = None
        self.producer_thread: Thread | None = None

    def download(self, request: FinsSourceDownloadAdapterRequest) -> FinsSourceDownloadAdapterResult:
        """等待 runtime owner 把 consumer task cancellation 投影到 checker。

        Args:
            request: runtime 传入的 typed request。

        Returns:
            固定 persisted summary。

        Raises:
            TimeoutError: owner 未在有界期限内请求取消。
        """

        self.producer_thread = current_thread()
        self.producer_thread_ident = self.producer_thread.ident
        self.entered.set()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if request.cancellation_checker():
                self.cancellation_observed.set()
                self.finished.set()
                return FinsSourceDownloadAdapterResult(
                    discovered_count=1,
                    persisted_summary=_typed_download_summary(downloaded_ids=("consumer-cancelled",)),
                )
            time.sleep(0.01)
        self.finished.set()
        raise TimeoutError("consumer task cancellation was not observed")


class _ClaimRaceJobStore:
    """测试用 job store，精确模拟 claim-running 窗口中的取消请求。"""

    def __init__(self) -> None:
        """初始化空 job store。

        Args:
            无。

        Returns:
            无。
        """

        self._record: ingestion_runtime.FinsIngestionJobRecord | None = None
        self._events: list[FinsIngestionJobEventRecord] = []
        self.read_race_triggered = False
        self.claim_race_triggered = False
        self.claim_running_calls = 0
        self.save_job_calls = 0

    def create_job(
        self,
        record: ingestion_runtime.FinsIngestionJobRecord,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """创建测试 job record。

        Args:
            record: 待创建的 job record。

        Returns:
            已保存的 job record。

        Raises:
            FileExistsError: job 已存在时抛出。
        """

        if self._record is not None:
            raise FileExistsError(f"Fins ingestion job 已存在: {record.job_id}")
        self._record = record
        return record

    def save_job(
        self,
        record: ingestion_runtime.FinsIngestionJobRecord,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """保存完整测试 job record。

        Args:
            record: 待保存的 job record。

        Returns:
            已保存的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self._require_record(record.job_id)
        self.save_job_calls += 1
        self._record = record
        return record

    def save_succeeded_or_cancelled(
        self,
        job_id: str,
        *,
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """按当前取消状态保存 succeeded 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            result_summary: succeeded 终态结果摘要。
            finished_at: 终态写入时间。

        Returns:
            已保存的终态 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=finished_at,
                finished_at=finished_at,
                cancellation_requested=True,
            )
            self._record = cancelled
            return cancelled
        succeeded = replace(
            record,
            status=FinsIngestionJobStatus.SUCCEEDED,
            updated_at=finished_at,
            finished_at=finished_at,
            result_summary=result_summary,
            failure_summary={},
        )
        self._record = succeeded
        return succeeded

    def save_cancelled_if_active(
        self,
        job_id: str,
        *,
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """仅当当前测试 job 非终态时保存 cancelled 终态。

        Args:
            job_id: opaque job id。
            finished_at: 终态写入时间。

        Returns:
            已保存的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        cancelled = replace(
            record,
            status=FinsIngestionJobStatus.CANCELLED,
            updated_at=finished_at,
            finished_at=finished_at,
            cancellation_requested=True,
        )
        self._record = cancelled
        return cancelled

    def save_accepted_upload_terminal_if_active(
        self,
        job_id: str,
        *,
        disposition: FinsUploadTerminalDisposition,
        result_summary: dict[str, JsonValue],
        failure_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """保存测试用 accepted upload terminal，且不重读取消状态。

        Args:
            job_id: opaque job id。
            disposition: 已接受的 completed 或 failed disposition。
            result_summary: upload 结果摘要。
            failure_summary: upload 失败摘要。
            finished_at: 终态写入时间。

        Returns:
            已保存的最终 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            ValueError: disposition 不是 completed/failed 时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if disposition is FinsUploadTerminalDisposition.CANCELLED:
            raise ValueError("accepted upload terminal 不接受 cancelled")
        terminal = replace(
            record,
            status=(
                FinsIngestionJobStatus.SUCCEEDED
                if disposition is FinsUploadTerminalDisposition.COMPLETED
                else FinsIngestionJobStatus.FAILED
            ),
            updated_at=finished_at,
            finished_at=finished_at,
            result_summary=result_summary,
            failure_summary=failure_summary,
        )
        self._record = terminal
        return terminal

    def save_failed_or_cancelled_if_active(
        self,
        job_id: str,
        *,
        failure_summary: dict[str, JsonValue],
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """按当前测试 job 状态保存 failed 或 cancelled 终态。

        Args:
            job_id: opaque job id。
            failure_summary: failed 终态失败摘要。
            result_summary: failed 终态结果摘要。
            finished_at: 终态写入时间。

        Returns:
            已保存的 job record；若当前已是终态则原样返回。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=finished_at,
                finished_at=finished_at,
                cancellation_requested=True,
            )
            self._record = cancelled
            return cancelled
        failed = replace(
            record,
            status=FinsIngestionJobStatus.FAILED,
            updated_at=finished_at,
            finished_at=finished_at,
            failure_summary=failure_summary,
            result_summary=result_summary,
        )
        self._record = failed
        return failed

    def claim_running_or_cancelled(
        self,
        job_id: str,
        *,
        started_at: str,
        updated_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """在一次测试 claim 内模拟 queued 读取后收到取消请求。

        Args:
            job_id: opaque job id。
            started_at: running 开始时间。
            updated_at: 本次状态更新时间。

        Returns:
            claim 后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self.claim_running_calls += 1
        record = self._require_record(job_id)
        if not self.claim_race_triggered and record.status is FinsIngestionJobStatus.QUEUED:
            self.claim_race_triggered = True
            self.request_cancel(job_id, updated_at=updated_at)
            record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        if record.cancellation_requested or record.status is FinsIngestionJobStatus.CANCELLING:
            cancelled = replace(
                record,
                status=FinsIngestionJobStatus.CANCELLED,
                updated_at=updated_at,
                finished_at=updated_at,
                cancellation_requested=True,
            )
            self._record = cancelled
            return cancelled
        running = replace(
            record,
            status=FinsIngestionJobStatus.RUNNING,
            started_at=record.started_at or started_at,
            updated_at=updated_at,
        )
        self._record = running
        return running

    def read_job(self, job_id: str) -> ingestion_runtime.FinsIngestionJobRecord:
        """读取测试 job record，并模拟旧 read/save 窗口中的取消。

        Args:
            job_id: opaque job id。

        Returns:
            当前或刻意滞后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if not self.read_race_triggered and record.status is FinsIngestionJobStatus.QUEUED:
            self.read_race_triggered = True
            self.request_cancel(job_id, updated_at=record.updated_at)
            return record
        return record

    def request_cancel(
        self,
        job_id: str,
        *,
        updated_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """标记测试 job 取消请求。

        Args:
            job_id: opaque job id。
            updated_at: 本次状态更新时间。

        Returns:
            更新后的 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        record = self._require_record(job_id)
        if _is_terminal_job_status(record.status):
            return record
        updated = replace(
            record,
            status=FinsIngestionJobStatus.CANCELLING,
            updated_at=updated_at,
            cancellation_requested=True,
        )
        self._record = updated
        return updated

    def append_job_event(
        self,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """追加测试 job event。

        Args:
            job_id: opaque job id。
            event: 无 sequence 的事件追加输入。

        Returns:
            已追加且带 sequence 的事件。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self._require_record(job_id)
        record = FinsIngestionJobEventRecord(
            job_id=job_id,
            sequence=len(self._events) + 1,
            operation_kind=event.operation_kind,
            status=event.status,
            event_type=event.event_type,
            source_event_type=event.source_event_type,
            source_kind=event.source_kind,
            document_id=event.document_id,
            message=event.message,
            payload=event.payload,
            emitted_at=event.emitted_at,
        )
        self._events.append(record)
        return record

    def read_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int,
        limit: int,
    ) -> tuple[FinsIngestionJobEventRecord, ...]:
        """读取测试 job events。

        Args:
            job_id: opaque job id。
            after_sequence: 只返回 sequence 大于该值的事件。
            limit: 本次最多返回事件数量。

        Returns:
            满足游标条件的事件元组。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
        """

        self._require_record(job_id)
        return tuple(event for event in self._events if event.sequence > after_sequence)[:limit]

    def _require_record(self, job_id: str) -> ingestion_runtime.FinsIngestionJobRecord:
        """读取并校验当前测试 job record。

        Args:
            job_id: opaque job id。

        Returns:
            当前 job record。

        Raises:
            FileNotFoundError: 当前没有匹配 job 时抛出。
        """

        record = self._record
        if record is None or record.job_id != job_id:
            raise FileNotFoundError(f"Fins ingestion job 不存在: {job_id}")
        return record


def test_default_runtime_instances_share_workspace_job_store_without_singleton(tmp_path: Path) -> None:
    """同一 workspace 的两个 runtime 实例应共享持久化 store 而非 Python singleton。"""

    workspace_root = tmp_path / "fins-workspace"
    first_executor = _HoldingExecutor()
    second_executor = _HoldingExecutor()
    first_ingestion = _build_ingestion_runtime(workspace_root, executor=first_executor)
    second_ingestion = _build_ingestion_runtime(workspace_root, executor=second_executor)

    start = first_ingestion.start_download(
        build_fins_download_request(
            ticker="AAPL",
            form_types=("10-K",),
        )
    )
    job_file = _job_file(workspace_root, start.job_id)
    cross_instance_record = second_ingestion.read_job(start.job_id)

    assert first_ingestion is not second_ingestion
    assert job_file.is_file()
    assert cross_instance_record == start.record
    assert cross_instance_record.status is FinsIngestionJobStatus.QUEUED
    assert len(first_executor.operations) == 1


def test_start_download_persists_queued_record_and_uses_public_ticker_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """下载启动应通过 ticker_normalization 并先持久化 queued record。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    original_normalize = ticker_normalization.normalize_ticker
    calls: list[str] = []

    def normalize_spy(raw: str) -> NormalizedTicker:
        """记录归一化调用并委托公共实现。

        Args:
            raw: 原始 ticker。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 非法时由公共实现抛出。
        """

        calls.append(raw)
        return original_normalize(raw)

    monkeypatch.setattr(download_contract, "normalize_ticker", normalize_spy)

    request = build_fins_download_request(
        ticker="aapl.us",
        form_types=("10-K", "10-Q"),
        start="2024-01-01",
        end="2024-12-31",
        overwrite_existing=True,
    )
    start = runtime.start_download(request)
    record = runtime.read_job(start.job_id)

    assert calls == ["aapl.us"]
    assert start.status is FinsIngestionJobStatus.QUEUED
    assert record.normalized_ticker == "AAPL"
    assert record.market == "US"
    assert record.source == "sec"
    assert record.source_kind is None
    assert record.request_summary["form_types"] == ["10-K", "10-Q"]
    assert record.request_summary["overwrite_existing"] is True
    assert record.result_summary == {}
    assert record.failure_summary == {}
    assert not record.cancellation_requested
    assert len(executor.operations) == 1


def test_store_downloaded_document_overwrite_failure_rolls_back_target_scope(tmp_path: Path) -> None:
    """download overwrite 单文档写入失败时应保留旧目标和非目标文档。"""

    workspace_root = _build_fins_workspace(tmp_path)
    _add_unmatched_source_documents(workspace_root=workspace_root, count=1)
    runtime = _build_ingestion_runtime(workspace_root, executor=_HoldingExecutor())
    old_meta = runtime.source_repository.get_source_meta("AAPL", "aapl-2024-10k", SourceKind.FILING)
    non_target_meta = runtime.source_repository.get_source_meta("AAPL", "aapl-2024-10q-00", SourceKind.FILING)
    document = FinsDownloadedSourceDocument(
        source_kind=SourceKind.FILING,
        document_id="aapl-2024-10k",
        internal_document_id="aapl-2024-10k-new",
        form_type="10-K",
        primary_document="aapl-2024-10k-new.md",
        meta={
            "form_type": "10-K",
            "filing_date": "2025-11-01",
            "report_date": "2025-09-28",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "amended": False,
        },
        files=(
            FinsDownloadedFile(
                filename="",
                content=b"broken",
                content_type="text/markdown",
            ),
        ),
    )

    with pytest.raises(ValueError, match="filename 不能为空"):
        runtime._store_downloaded_document(
            ticker="AAPL",
            document=document,
            overwrite_existing=True,
        )

    assert runtime.source_repository.get_source_meta("AAPL", "aapl-2024-10k", SourceKind.FILING) == old_meta
    assert runtime.source_repository.get_source_meta("AAPL", "aapl-2024-10q-00", SourceKind.FILING) == non_target_meta


def test_store_downloaded_document_create_failure_leaves_document_absent(tmp_path: Path) -> None:
    """generic download create 的 blob 校验失败必须回滚 source 与 blob。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = _build_ingestion_runtime(workspace_root, executor=_HoldingExecutor())
    document = FinsDownloadedSourceDocument(
        source_kind=SourceKind.FILING,
        document_id="aapl-new-10k",
        internal_document_id="aapl-new-10k",
        form_type="10-K",
        primary_document="aapl-new-10k.md",
        meta={
            "form_type": "10-K",
            "ingest_method": FinsIngestMethod.DOWNLOAD.to_storage_value(),
            "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
        },
        files=(FinsDownloadedFile(filename="", content=b"broken"),),
    )

    with pytest.raises(ValueError, match="filename 不能为空"):
        runtime._store_downloaded_document(
            ticker="AAPL",
            document=document,
            overwrite_existing=False,
        )

    with pytest.raises(FileNotFoundError):
        runtime.source_repository.get_source_meta(
            "AAPL",
            "aapl-new-10k",
            SourceKind.FILING,
        )


def test_store_downloaded_document_commit_failure_does_not_caller_rollback(tmp_path: Path) -> None:
    """generic commit 失败后 caller 不得对 storage-owned token 二次 rollback。"""

    workspace_root = tmp_path / "fins-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = _CommitFailingDownloadBatchingRepository(workspace_root, repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    runtime = ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=batching_repository,
        source_repository=source_repository,
        blob_repository=FsDocumentBlobRepository(workspace_root, repository_set=repository_set),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        processed_repository=FsProcessedDocumentRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=_HoldingExecutor(),
    )
    document = FinsDownloadedSourceDocument(
        source_kind=SourceKind.FILING,
        document_id="aapl-commit-failed",
        internal_document_id="aapl-commit-failed",
        form_type="10-K",
        primary_document="report.md",
        meta={
            "form_type": "10-K",
            "ingest_method": FinsIngestMethod.DOWNLOAD.to_storage_value(),
            "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
        },
        files=(FinsDownloadedFile(filename="report.md", content=b"report"),),
    )

    with pytest.raises(OSError, match="forced generic commit failure"):
        runtime._store_downloaded_document(
            ticker="AAPL",
            document=document,
            overwrite_existing=False,
        )

    assert batching_repository.caller_rollback_calls == 0
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta(
            "AAPL",
            "aapl-commit-failed",
            SourceKind.FILING,
        )


def test_store_rejected_artifact_double_failure_preserves_operation_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rejected artifact 双失败必须以 operation 为主、rollback 为 cause且仅回滚一次。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主异常 identity、cause、note 或 rollback 次数漂移时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    operation_error = OSError("injected rejected artifact operation failure")
    rollback_error = RuntimeError("injected rejected artifact rollback failure")
    batching_repository = _RollbackFailingIngestionBatchingRepository(
        workspace_root,
        repository_set,
        rollback_error,
    )
    runtime = _build_ingestion_runtime_with_repository_set(
        workspace_root,
        repository_set=repository_set,
        batching_repository=batching_repository,
    )
    monkeypatch.setattr(
        runtime.filing_maintenance_repository,
        "upsert_rejected_filing_artifact",
        _RejectedArtifactUpsertFailure(operation_error),
    )
    artifact = FinsRejectedFilingDownloadArtifact(
        document_id="fil-rejected",
        internal_document_id="rejected-internal",
        accession_number="0000000000-25-000001",
        company_id="0000320193",
        form_type="8-K",
        filing_date="2025-02-01",
        report_date=None,
        primary_document="rejected.htm",
        selected_primary_document="rejected.htm",
        rejection_reason="不属于请求范围",
        rejection_category="form_filter",
        source_fingerprint="rejected-fingerprint",
    )

    with pytest.raises(OSError) as exc_info:
        runtime._store_rejected_filing_artifact(ticker="AAPL", artifact=artifact)

    assert exc_info.value is operation_error
    assert exc_info.value.__cause__ is rollback_error
    assert exc_info.value.__notes__ == [
        "rollback_batch failed; recovery evidence retained: injected rejected artifact rollback failure"
    ]
    assert batching_repository.rollback_calls == 1


def test_preprocess_double_failure_preserves_operation_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preprocess 双失败必须以 operation 为主、rollback 为 cause且仅回滚一次。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 主异常 identity、cause、note 或 rollback 次数漂移时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    operation_error = OSError("injected preprocess operation failure")
    rollback_error = RuntimeError("injected preprocess rollback failure")
    batching_repository = _RollbackFailingIngestionBatchingRepository(
        workspace_root,
        repository_set,
        rollback_error,
    )
    runtime = _build_ingestion_runtime_with_repository_set(
        workspace_root,
        repository_set=repository_set,
        batching_repository=batching_repository,
    )
    monkeypatch.setattr(
        runtime.processed_repository,
        "create_processed",
        _ProcessedCreateFailure(operation_error),
    )

    with pytest.raises(OSError) as exc_info:
        runtime._preprocess_one_document(
            ticker="AAPL",
            document_id="aapl-2024-10k",
            source_kind=SourceKind.FILING,
            rebuild_processed=False,
        )

    assert exc_info.value is operation_error
    assert exc_info.value.__cause__ is rollback_error
    assert exc_info.value.__notes__ == [
        "rollback_batch failed; recovery evidence retained: injected preprocess rollback failure"
    ]
    assert batching_repository.rollback_calls == 1


def test_start_download_allows_sec_amended_form_type(tmp_path: Path) -> None:
    """下载请求应允许 SEC 修正表单类型中的业务合法斜杠。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    start = runtime.start_download(build_fins_download_request(ticker="AAPL", form_types=("10-K/A",)))
    record = runtime.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.QUEUED
    assert record.request_summary["form_types"] == ["10-K/A"]


def test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit(
    tmp_path: Path,
) -> None:
    """下载 start 在 create 后、submit 前观察到取消时应标记 job 且不提交后台操作。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    token = _CancelOnSecondCheckToken()

    start = runtime.start_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=token,
    )
    record = runtime.read_job(start.job_id)

    assert start.status is FinsIngestionJobStatus.CANCELLED
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert executor.operations == []


def test_download_request_rejects_csv_ticker_before_runtime(tmp_path: Path) -> None:
    """下载 request owner 应在 runtime 前拒绝 CSV ticker。"""

    workspace_root = tmp_path / "fins-workspace"
    with pytest.raises(ValueError, match="只接受一个公司代码"):
        build_fins_download_request(ticker="AAPL,MSFT")

    assert not workspace_root.exists()


def test_start_download_fake_adapter_writes_source_document_through_storage(tmp_path: Path) -> None:
    """fake 下载 adapter 应通过 source/blob 仓储写入源文档。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    start = ingestion.start_download(build_fins_download_request(ticker="AAPL", form_types=("10-K",)))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    source_meta = runtime.source_repository.get_source_meta("AAPL", "aapl-fake-10k", SourceKind.FILING)
    handle = runtime.source_repository.get_source_handle("AAPL", "aapl-fake-10k", SourceKind.FILING)
    content = runtime.blob_repository.read_file_bytes(handle, "aapl-fake-10k.md")

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["discovered_count"] == 1
    assert record.result_summary["downloaded_count"] == 1
    assert record.result_summary["skipped_count"] == 0
    assert record.result_summary["rejected_count"] == 0
    assert record.result_summary["failed_count"] == 0
    assert record.result_summary["written_document_ids"] == ["aapl-fake-10k"]
    assert source_meta["ingest_method"] == "download"
    assert content == b"# Fake 10-K\n\nRevenue increased."
    assert adapter.requests[0].normalized_ticker.canonical == "AAPL"
    assert adapter.requests[0].normalized_ticker.market == "US"
    assert [event.source_event_type for event in progress_events] == [
        "download.started",
        "download.completed",
    ]
    assert progress_events[0].payload["ticker"] == "AAPL"
    assert progress_events[0].payload["source"] == "sec"
    assert progress_events[0].payload["form_types"] == ["10-K"]
    assert progress_events[1].payload["downloaded_count"] == 1
    assert progress_events[1].payload["written_document_count"] == 1


@pytest.mark.asyncio
async def test_direct_download_stream_writes_storage_and_does_not_create_job_record(
    tmp_path: Path,
) -> None:
    """direct download 应产出 progress/result，并且不创建 durable job record。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    events = await _collect_direct_events(
        ingestion.download(build_fins_download_request(ticker="AAPL", form_types=("10-K",)))
    )
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    source_meta = runtime.source_repository.get_source_meta("AAPL", "aapl-fake-10k", SourceKind.FILING)
    handle = runtime.source_repository.get_source_handle("AAPL", "aapl-fake-10k", SourceKind.FILING)
    content = runtime.blob_repository.read_file_bytes(handle, "aapl-fake-10k.md")
    jobs_dir = workspace_root / ".dayu" / "fins_ingestion" / "jobs"

    assert executor.operations == []
    assert [event.event_type for event in events].count(FinsEventType.RESULT) == 1
    assert events[0].event_type is FinsEventType.PROGRESS
    assert events[-1].event_type is FinsEventType.RESULT
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.SUCCESS
    assert events[-1].result.exit_code == 0
    assert source_meta["ingest_method"] == "download"
    assert content == b"# Fake 10-K\n\nRevenue increased."
    assert tuple(jobs_dir.glob("*.json")) == ()
    assert tuple(jobs_dir.glob("*.jsonl")) == ()


@pytest.mark.asyncio
async def test_direct_download_projects_adapter_file_progress_events(
    tmp_path: Path,
) -> None:
    """direct download 应投影 adapter 上报的文件级下载进度。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _ProgressReportingDownloadAdapter()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): adapter},
    )

    events = await _collect_direct_events(ingestion.download(build_fins_download_request(ticker="AAPL")))
    progress_events = [event for event in events if event.event_type is FinsEventType.PROGRESS]
    file_progress = [
        event
        for event in progress_events
        if event.progress is not None and event.progress.stage.startswith("download.file")
    ]
    conversion_progress = [
        event
        for event in progress_events
        if event.progress is not None and event.progress.stage.startswith("download.conversion_")
    ]

    file_progress_details: list[tuple[str, str | None, str]] = []
    for event in file_progress:
        assert event.progress is not None
        file_progress_details.append((event.progress.stage, event.document_label, event.message))
    assert file_progress_details == [
        ("download.file_started", "sample-10k.htm", "开始下载"),
        ("download.file_completed", "sample-10k.htm", "完成下载"),
    ]
    conversion_progress_details: list[tuple[str, str | None, str]] = []
    for event in conversion_progress:
        assert event.progress is not None
        conversion_progress_details.append((event.progress.stage, event.document_label, event.message))
    assert conversion_progress_details == [
        ("download.conversion_started", "sample-10k_docling.json", "开始转换文档"),
        ("download.conversion_completed", "sample-10k_docling.json", "完成转换文档"),
    ]


@pytest.mark.asyncio
async def test_direct_download_result_details_preserve_exclusive_skipped_count(
    tmp_path: Path,
) -> None:
    """direct download summary 展示应保留互斥 skipped 计数。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _PersistedSummaryDownloadAdapter(
        _typed_download_summary(
            canonical_ticker="FUTU",
            downloaded_ids=tuple(f"fil-{index}" for index in range(15)),
            skipped_ids=("fil-skipped",),
            rejected_ids=("fil-rejected-1", "fil-rejected-2"),
        )
    )
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): adapter},
    )

    events = await _collect_direct_events(ingestion.download(build_fins_download_request(ticker="FUTU")))
    result_event = events[-1]

    assert result_event.result is not None
    assert result_event.result.details == ()
    assert result_event.result.download is not None
    assert result_event.result.download.discovered_count == 18
    assert result_event.result.download.downloaded_count == 15
    assert result_event.result.download.skipped_count == 1
    assert result_event.result.download.rejected_count == 2
    assert result_event.result.download.failed_count == 0
    assert len(result_event.result.download.document_rows) == 10
    assert result_event.result.download.omitted_count == 8


@pytest.mark.asyncio
async def test_direct_download_missing_adapter_returns_failure_result(tmp_path: Path) -> None:
    """direct download 缺少目标 adapter 时应收口为 FAILURE RESULT。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        download_adapters={},
    )

    events = await _collect_direct_events(ingestion.download(build_fins_download_request(ticker="AAPL")))

    assert events[0].event_type is FinsEventType.PROGRESS
    assert events[-1].event_type is FinsEventType.RESULT
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.FAILURE
    assert events[-1].result.exit_code == 1
    assert events[-1].result.error_message is not None
    assert events[-1].result.error_message == "下载执行失败"
    assert events[-1].result.download is not None
    assert events[-1].result.download.discovered_count == 0
    assert events[-1].result.failure is not None
    assert events[-1].result.failure.safe_message == "下载执行失败"


@pytest.mark.asyncio
async def test_direct_download_projects_typed_provider_failure_without_raw_cause(
    tmp_path: Path,
) -> None:
    """runtime 应投影 owner 分类且不读取 typed error 的敏感异常链。

    Args:
        tmp_path: runtime workspace 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: failure 分类、空摘要或脱敏边界漂移时抛出。
    """

    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): _ProviderFailureDownloadAdapter()},
    )

    events = await _collect_direct_events(ingestion.download(build_fins_download_request(ticker="AAPL")))
    result = events[-1].result

    assert result is not None
    assert result.status is FinsResultStatus.FAILURE
    assert result.error_kind is FinsErrorKind.PROVIDER
    assert result.download is not None
    assert result.download.discovered_count == 0
    assert result.download.omitted_count == 0
    assert result.download.terminal_disposition is FinsDownloadTerminalDisposition.FAILED
    assert result.failure is not None
    assert result.failure.transport_category is FinsDownloadTransportCategory.CONNECTION
    serialized = str(result)
    assert "contact-canary" not in serialized
    assert "https://provider.invalid" not in serialized
    assert "/Users/private" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_error_kind", "expected_failure_kind", "expected_safe_message"),
    [
        (
            OSError("/Users/private/contact-canary/source.json"),
            FinsErrorKind.STORAGE,
            FinsPublicFailureKind.STORAGE,
            "下载产物读写失败",
        ),
        (
            RuntimeError("raw https://secret.invalid/payload contact-canary@example.invalid"),
            FinsErrorKind.EXECUTION,
            FinsPublicFailureKind.EXECUTION,
            "下载执行失败",
        ),
    ],
)
async def test_direct_download_projects_storage_and_execution_without_raw_text(
    tmp_path: Path,
    failure: Exception,
    expected_error_kind: FinsErrorKind,
    expected_failure_kind: FinsPublicFailureKind,
    expected_safe_message: str,
) -> None:
    """runtime 只按异常 owner 类型投影 storage/execution，不复制 raw text。"""

    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        download_adapters={
            ("sec", "US"): _OperationFailureDownloadAdapter(failure),
        },
    )

    events = await _collect_direct_events(ingestion.download(build_fins_download_request(ticker="AAPL")))
    result = events[-1].result

    assert result is not None
    assert result.error_kind is expected_error_kind
    assert result.failure is not None
    assert result.failure.kind is expected_failure_kind
    assert result.failure.safe_message == expected_safe_message
    serialized = str(result)
    assert "secret.invalid" not in serialized
    assert "contact-canary" not in serialized
    assert "/Users/private" not in serialized


@pytest.mark.parametrize(
    ("terminal", "is_allowed"),
    [
        (FinsDownloadTerminalDisposition.SUCCEEDED, True),
        (FinsDownloadTerminalDisposition.FAILED, True),
        (FinsDownloadTerminalDisposition.CANCELLED, True),
        (FinsDownloadTerminalDisposition.PARTIAL_FAILURE, False),
    ],
)
def test_download_summary_zero_candidate_terminal_override_matrix(
    terminal: FinsDownloadTerminalDisposition,
    is_allowed: bool,
) -> None:
    """零候选只接受正常 SUCCEEDED 或显式 FAILED/CANCELLED override。"""

    def build_summary() -> FinsDownloadResultSummary:
        """用当前 terminal 构造零候选 owner summary。"""

        return FinsDownloadResultSummary(
            source=FinsDownloadSource.SEC,
            canonical_ticker="AAPL",
            effective_filters=FinsDownloadEffectiveFilters(
                form_types=(),
                start_date=None,
                end_date=None,
                overwrite_existing=False,
                rebuild_local_artifacts=False,
            ),
            discovered_count=0,
            downloaded_count=0,
            skipped_count=0,
            rejected_count=0,
            failed_count=0,
            document_rows=(),
            terminal_disposition=terminal,
            missing_periods=(),
        )

    if is_allowed:
        summary = build_summary()
        assert summary.terminal_disposition is terminal
    else:
        with pytest.raises(ValueError, match="terminal_disposition"):
            build_summary()


def test_terminal_derivation_asserts_impossible_mixed_failure_counts() -> None:
    """defensive discovered_count witness 非正时必须 assert，不得静默 fallback。"""

    with pytest.raises(AssertionError, match="discovered_count"):
        download_contract._terminal_disposition_from_counts(
            discovered_count=0,
            downloaded_count=1,
            rejected_count=0,
            failed_count=1,
        )


@pytest.mark.asyncio
async def test_direct_download_uses_operation_scoped_cancellation_token(tmp_path: Path) -> None:
    """direct download 取消应使用 operation-scoped token/checker 并返回 cancelled RESULT。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): _CancellationAwareDownloadAdapter()},
    )
    token = _CancelOnSecondCheckToken()

    events = await _collect_direct_events(
        ingestion.download(
            build_fins_download_request(ticker="AAPL"),
            cancellation_token=token,
        )
    )

    assert executor.operations == []
    assert token.check_count >= 2
    assert events[-1].event_type is FinsEventType.RESULT
    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.CANCELLED
    assert events[-1].result.exit_code == 130
    assert sum(event.event_type is FinsEventType.RESULT for event in events) == 1


@pytest.mark.asyncio
async def test_direct_download_very_early_cancel_skips_adapter_and_joins_thread(
    tmp_path: Path,
) -> None:
    """在 operation task 启动前已取消必须产生唯一终态并清理线程。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: adapter 被调用、终态非唯一或线程遗留时抛出。
    """

    adapter = _PersistedSummaryDownloadAdapter()
    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): adapter},
    )
    events = await asyncio.wait_for(
        _collect_direct_events(
            ingestion.download(
                build_fins_download_request(ticker="AAPL"),
                cancellation_token=_MutableCancellationToken(cancelled=True),
            )
        ),
        timeout=1.0,
    )

    result_events = tuple(event for event in events if event.event_type is FinsEventType.RESULT)
    assert adapter.requests == []
    assert len(result_events) == 1
    assert result_events[0].result is not None
    assert result_events[0].result.status is FinsResultStatus.CANCELLED
    assert all(thread.name != "fins-direct-download" for thread in enumerate_threads())


@pytest.mark.asyncio
async def test_direct_cancel_wins_late_provider_failure_and_exhausts_after_join(
    tmp_path: Path,
) -> None:
    """已生效取消必须压过迟到 provider 失败并在 join 后 clean exhaust。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: 竞态终态、数量或线程 cleanup 不符合契约时抛出。
    """

    adapter = _CancellationThenFailureDownloadAdapter()
    token = _MutableCancellationToken()
    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): adapter},
    )
    collection_task = asyncio.create_task(
        _collect_direct_events(
            ingestion.download(
                build_fins_download_request(ticker="AAPL"),
                cancellation_token=token,
            )
        )
    )
    assert await asyncio.to_thread(adapter.entered.wait, 1.0)
    token.request_cancel()
    adapter.release_failure.set()

    events = await asyncio.wait_for(collection_task, timeout=1.0)

    result_events = tuple(event for event in events if event.event_type is FinsEventType.RESULT)
    assert len(result_events) == 1
    assert result_events[0].result is not None
    assert result_events[0].result.status is FinsResultStatus.CANCELLED
    assert adapter.producer_thread_ident is not None
    assert adapter.producer_thread is not None
    assert not adapter.producer_thread.is_alive()


def test_direct_terminal_state_is_atomic_and_ignores_late_cancel_or_result() -> None:
    """终态提交后的取消或第二终态不得改写 canonical outcome。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 原子终态仲裁失效时抛出。
    """

    state = ingestion_runtime._DirectStreamCancellationState.create()

    assert state.claim_terminal(FinsResultStatus.SUCCESS) is FinsResultStatus.SUCCESS
    assert not state.request_cancel()
    assert state.claim_terminal(FinsResultStatus.FAILURE) is None

    cancelled_state = ingestion_runtime._DirectStreamCancellationState.create()
    assert cancelled_state.request_cancel()
    assert cancelled_state.claim_terminal(FinsResultStatus.FAILURE) is FinsResultStatus.CANCELLED
    assert cancelled_state.claim_terminal(FinsResultStatus.CANCELLED) is None

    aborted_state = ingestion_runtime._DirectStreamCancellationState.create()
    aborted_state.request_consumer_abort()
    assert aborted_state.is_cancelled()
    assert not aborted_state.request_cancel()
    assert aborted_state.claim_terminal(FinsResultStatus.CANCELLED) is None
    assert aborted_state._terminal_status is None


@pytest.mark.parametrize(
    ("disposition", "expected_status"),
    (
        (FinsUploadTerminalDisposition.COMPLETED, FinsResultStatus.SUCCESS),
        (FinsUploadTerminalDisposition.FAILED, FinsResultStatus.FAILURE),
        (FinsUploadTerminalDisposition.CANCELLED, FinsResultStatus.CANCELLED),
    ),
)
def test_direct_upload_summary_claim_is_single_terminal_and_ignores_late_cancel(
    disposition: FinsUploadTerminalDisposition,
    expected_status: FinsResultStatus,
) -> None:
    """accepted upload summary 必须单 lock claim，且不被 late cancel 改写。

    Args:
        disposition: runner 已 first-commit 的 summary disposition。
        expected_status: 对应 direct RESULT status。

    Returns:
        无。

    Raises:
        AssertionError: claim、late cancel 或第二终态行为不符合契约时抛出。
    """

    state = ingestion_runtime._DirectStreamCancellationState.create()
    assert state.request_cancel()
    assert state.claim_upload_summary(disposition) is expected_status
    assert state.claim_upload_summary(disposition) is None

    claimed_state = ingestion_runtime._DirectStreamCancellationState.create()
    assert claimed_state.claim_upload_summary(disposition) is expected_status
    assert not claimed_state.request_cancel()
    assert claimed_state.claim_terminal(FinsResultStatus.CANCELLED) is None


@pytest.mark.asyncio
async def test_direct_upload_projection_failure_before_claim_emits_single_failure_result(
    tmp_path: Path,
) -> None:
    """accepted 事件构造失败必须在 claim 前收口为唯一 FAILURE RESULT。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: summary 边界、事件序列或单终态语义不符合契约时抛出。
    """

    oversized_direct_label = "D" * 121
    summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        document_id=oversized_direct_label,
        status="ok",
    )
    assert summary.to_json_summary()["document_id"] == oversized_direct_label
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        upload_runner=_FakeUploadRunner(summary),
    )

    events = await _collect_direct_events(runtime.upload(_valid_runtime_filing_request()))
    progress_stages = tuple(event.progress.stage for event in events if event.progress is not None)
    results = tuple(event.result for event in events if event.result is not None)

    assert progress_stages == ("upload.preparing", "upload.started")
    assert len(results) == 1
    assert results[0].status is FinsResultStatus.FAILURE
    assert results[0].error_kind is FinsErrorKind.USER_INPUT
    assert all(result.status is not FinsResultStatus.SUCCESS for result in results)


@pytest.mark.asyncio
async def test_direct_upload_cancel_before_final_checkpoint_returns_only_cancelled_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """时点 a：final checkpoint 前取消只能投影 cancelled，不得投影 completed。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        无。

    Raises:
        AssertionError: barrier、事件序列或单终态不符合契约时抛出。
    """

    states = _record_direct_cancellation_states(monkeypatch)
    runner = _BarrierUploadRunner(
        accepted_summary=FinsUploadResultSummary(source_kind=SourceKind.FILING, status="ok"),
        observe_cancel_before_summary=True,
    )
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        upload_runner=runner,
    )
    collection = asyncio.create_task(_collect_direct_events(runtime.upload(_valid_runtime_filing_request())))
    assert await asyncio.to_thread(runner.boundary_reached.wait, 1.0)
    assert len(states) == 1
    assert states[0].request_cancel()
    runner.release_summary.set()

    events = await asyncio.wait_for(collection, timeout=1.0)
    progress_types = tuple(event.progress.stage for event in events if event.progress is not None)
    results = tuple(event.result for event in events if event.result is not None)

    assert progress_types == ("upload.preparing", "upload.started")
    assert len(results) == 1
    assert results[0].status is FinsResultStatus.CANCELLED
    assert results[0].exit_code == 130


@pytest.mark.asyncio
async def test_direct_upload_cancel_after_commit_before_summary_keeps_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """时点 b：publication commit 后、summary 返回前取消不得改写 completed。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        无。

    Raises:
        AssertionError: barrier、progress/result 同源或 late cancel 行为漂移时抛出。
    """

    states = _record_direct_cancellation_states(monkeypatch)
    runner = _BarrierUploadRunner(
        accepted_summary=FinsUploadResultSummary(source_kind=SourceKind.FILING, status="ok"),
        observe_cancel_before_summary=False,
    )
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        upload_runner=runner,
    )
    collection = asyncio.create_task(_collect_direct_events(runtime.upload(_valid_runtime_filing_request())))
    assert await asyncio.to_thread(runner.boundary_reached.wait, 1.0)
    assert len(states) == 1
    assert states[0].request_cancel()
    runner.release_summary.set()

    events = await asyncio.wait_for(collection, timeout=1.0)
    progress_types = tuple(event.progress.stage for event in events if event.progress is not None)
    results = tuple(event.result for event in events if event.result is not None)

    assert progress_types == ("upload.preparing", "upload.started", "upload.completed")
    assert len(results) == 1
    assert results[0].status is FinsResultStatus.SUCCESS


@pytest.mark.parametrize(
    ("status", "expected_progress", "expected_result"),
    (
        ("ok", "upload.completed", FinsResultStatus.SUCCESS),
        ("failed", "upload.completed_with_failures", FinsResultStatus.FAILURE),
    ),
)
@pytest.mark.parametrize("cancel_before_claim", (True, False))
@pytest.mark.asyncio
async def test_direct_upload_cancel_around_summary_claim_keeps_progress_result_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected_progress: str,
    expected_result: FinsResultStatus,
    cancel_before_claim: bool,
) -> None:
    """时点 c/d：claim 前后取消不拆分 accepted progress 与 RESULT。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。
        status: accepted upload summary status。
        expected_progress: 预期 completed progress 类型。
        expected_result: 预期 direct RESULT status。
        cancel_before_claim: ``True`` 控制 claim 前窗口，否则控制 claim 后窗口。

    Returns:
        无。

    Raises:
        AssertionError: barrier、single claim 或 progress/result 投影不符合契约时抛出。
    """

    states = _record_direct_cancellation_states(monkeypatch)
    claim_boundary = Event()
    release_claim = Event()
    original_claim = ingestion_runtime._DirectStreamCancellationState.claim_upload_summary

    def controlled_claim(
        state: ingestion_runtime._DirectStreamCancellationState,
        disposition: FinsUploadTerminalDisposition,
    ) -> FinsResultStatus | None:
        """在 summary claim 前或后暂停 producer。

        Args:
            state: direct stream cancellation/terminal owner。
            disposition: runner 返回的 accepted upload disposition。

        Returns:
            原 owner 的 single-claim 结果。

        Raises:
            AssertionError: barrier 未在期限内释放时抛出。
        """

        if cancel_before_claim:
            claim_boundary.set()
            assert release_claim.wait(timeout=1.0)
            return original_claim(state, disposition)
        claimed = original_claim(state, disposition)
        claim_boundary.set()
        assert release_claim.wait(timeout=1.0)
        return claimed

    monkeypatch.setattr(
        ingestion_runtime._DirectStreamCancellationState,
        "claim_upload_summary",
        controlled_claim,
    )
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        upload_runner=_FakeUploadRunner(
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status=status,
                failure_reason=_runtime_failure_for_status(status),
            )
        ),
    )
    collection = asyncio.create_task(_collect_direct_events(runtime.upload(_valid_runtime_filing_request())))
    assert await asyncio.to_thread(claim_boundary.wait, 1.0)
    assert len(states) == 1
    cancel_accepted = states[0].request_cancel()
    release_claim.set()

    events = await asyncio.wait_for(collection, timeout=1.0)
    progress_types = tuple(event.progress.stage for event in events if event.progress is not None)
    results = tuple(event.result for event in events if event.result is not None)

    assert cancel_accepted is cancel_before_claim
    assert progress_types == ("upload.preparing", "upload.started", expected_progress)
    assert len(results) == 1
    assert results[0].status is expected_result


def test_direct_upload_cancel_before_and_after_summary_claim_keeps_accepted_terminal() -> None:
    """时点 c/d：summary claim 前后取消都不得改写已接受的 completed/failed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: Event barrier 下的 claim 或单终态不符合契约时抛出。
    """

    before_claim_state = ingestion_runtime._DirectStreamCancellationState.create()
    before_claim_entered = Event()
    release_before_claim = Event()
    before_claim_result: list[FinsResultStatus | None] = []

    def claim_after_release() -> None:
        """在测试释放前暂停 completed summary claim。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: barrier 未在期限内释放时抛出。
        """

        before_claim_entered.set()
        assert release_before_claim.wait(timeout=1.0)
        before_claim_result.append(before_claim_state.claim_upload_summary(FinsUploadTerminalDisposition.COMPLETED))

    before_claim_thread = Thread(target=claim_after_release)
    before_claim_thread.start()
    assert before_claim_entered.wait(timeout=1.0)
    assert before_claim_state.request_cancel()
    release_before_claim.set()
    before_claim_thread.join(timeout=1.0)

    after_claim_state = ingestion_runtime._DirectStreamCancellationState.create()
    after_claim_completed = Event()
    release_after_claim = Event()
    after_claim_result: list[FinsResultStatus | None] = []

    def hold_after_claim() -> None:
        """在 failed summary 已 claim 后暂停返回。

        Args:
            无。

        Returns:
            无。

        Raises:
            AssertionError: barrier 未在期限内释放时抛出。
        """

        after_claim_result.append(after_claim_state.claim_upload_summary(FinsUploadTerminalDisposition.FAILED))
        after_claim_completed.set()
        assert release_after_claim.wait(timeout=1.0)

    after_claim_thread = Thread(target=hold_after_claim)
    after_claim_thread.start()
    assert after_claim_completed.wait(timeout=1.0)
    assert not after_claim_state.request_cancel()
    release_after_claim.set()
    after_claim_thread.join(timeout=1.0)

    assert not before_claim_thread.is_alive()
    assert before_claim_result == [FinsResultStatus.SUCCESS]
    assert not after_claim_thread.is_alive()
    assert after_claim_result == [FinsResultStatus.FAILURE]
    assert after_claim_state.claim_terminal(FinsResultStatus.CANCELLED) is None


def test_direct_checker_freezes_external_reason_and_time_across_threads() -> None:
    """direct composite token 必须跨线程保存首次外部取消事实。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: reason/time 可见性或稳定性漂移时抛出。
    """

    external_token = _MutableCancellationToken()
    state = ingestion_runtime._DirectStreamCancellationState.create()
    checker = ingestion_runtime._DirectCancellationChecker(
        cancellation_token=external_token,
        cancellation_state=state,
    )
    start = Event()
    observed = Event()
    worker_results: list[bool] = []

    def observe_from_worker() -> None:
        """等待主线程请求取消后从 producer 线程观察。

        Returns:
            无。
        """

        start.wait(timeout=1.0)
        worker_results.append(checker.is_cancelled())
        observed.set()

    worker = Thread(target=observe_from_worker)
    worker.start()
    external_token.request_cancel()
    start.set()
    assert observed.wait(timeout=1.0)
    worker.join(timeout=1.0)

    assert worker_results == [True]
    assert checker() is True
    assert checker.cancel_reason() == "test-cancelled"
    assert checker.requested_at() == datetime(2026, 8, 10, tzinfo=timezone.utc)


def test_durable_checker_freezes_first_persisted_cancellation_record(tmp_path: Path) -> None:
    """durable composite token 必须以首次 cancelling record 为 reason/time 真源。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: durable reason/time 或 ``__call__`` 委托语义漂移时抛出。
    """

    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(tmp_path / "fins-workspace", executor=executor)
    start = runtime.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    checker = ingestion_runtime._RuntimeJobCancellationChecker(
        job_store=runtime.job_store,
        job_id=start.job_id,
    )

    assert checker() is False
    assert checker.cancel_reason() is None
    assert checker.requested_at() is None
    cancelling = runtime.request_cancel(start.job_id)
    expected_time = datetime.fromisoformat(cancelling.updated_at.replace("Z", "+00:00"))

    assert checker.is_cancelled() is True
    assert checker() is True
    assert checker.cancel_reason() == "job_cancel_requested"
    assert checker.requested_at() == expected_time


@pytest.mark.asyncio
async def test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """consumer abort 必须经真实 raw generator finally 请求取消并阻止 late event。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        无。

    Raises:
        AssertionError: raw close、取消因果链或 late-publication fence 失效时抛出。
    """

    cancellation_states = _record_direct_cancellation_states(monkeypatch)
    workspace_root = tmp_path / "fins-workspace"
    adapter = _ConsumerAbortDownloadAdapter()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): adapter},
    )
    stream = ingestion.download(build_fins_download_request(ticker="AAPL"))

    first_event = await anext(stream)
    assert first_event.event_type is FinsEventType.PROGRESS
    assert await asyncio.to_thread(adapter.entered.wait, 1.0)

    close_started = asyncio.Event()

    async def close_stream() -> None:
        """关闭 stream 并暴露 close task 已进入 owner boundary。

        Args:
            无。

        Returns:
            无。

        Raises:
            BaseException: stream cleanup 异常原样透传。
        """

        close_started.set()
        await stream.aclose()

    close_task = asyncio.create_task(close_stream())
    await asyncio.wait_for(close_started.wait(), timeout=1.0)
    assert not close_task.done()
    adapter.allow_cancellation_check.set()
    await asyncio.wait_for(close_task, timeout=1.0)
    await stream.aclose()

    assert adapter.late_progress_returned.is_set()
    assert adapter.cancellation_checks == (True,)
    assert adapter.producer_thread_name == "fins-direct-download"
    assert adapter.producer_thread_ident is not None
    assert adapter.producer_thread is not None
    assert not adapter.producer_thread.is_alive()
    assert len(cancellation_states) == 1
    assert cancellation_states[0].is_consumer_aborted()
    assert cancellation_states[0]._terminal_status is None
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    with pytest.raises(RuntimeError):
        _ = stream.terminal_result


@pytest.mark.asyncio
async def test_direct_consumer_task_cancel_waits_for_producer_cleanup_and_thread_join(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """consumer task cancellation 必须由 raw owner 等待 producer cleanup 与 join。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        无。

    Raises:
        AssertionError: cancellation 未传递、cleanup 未完成或线程遗留时抛出。
    """

    cancellation_states = _record_direct_cancellation_states(monkeypatch)
    adapter = _ConsumerTaskCancelledDownloadAdapter()
    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        download_adapters={("sec", "US"): adapter},
    )
    stream = ingestion.download(build_fins_download_request(ticker="AAPL"))
    collection_task = asyncio.create_task(_collect_direct_events(stream))
    assert await asyncio.to_thread(adapter.entered.wait, 1.0)

    collection_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(collection_task, timeout=1.0)

    assert adapter.cancellation_observed.is_set()
    assert adapter.finished.is_set()
    assert adapter.producer_thread_ident is not None
    assert adapter.producer_thread is not None
    assert not adapter.producer_thread.is_alive()
    assert len(cancellation_states) == 1
    assert cancellation_states[0].is_consumer_aborted()
    assert cancellation_states[0]._terminal_status is None
    await stream.aclose()


def test_start_download_production_adapter_boundary_emits_progress_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """production 下载 adapter 同步调用边界应产生 started/completed PROGRESS event。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    def fake_sec_download(
        adapter: SecDownloadAdapter,
        request: FinsSourceDownloadAdapterRequest,
    ) -> FinsSourceDownloadAdapterResult:
        """替换 production SEC adapter 的网络下载，只保留同步调用边界。

        Args:
            adapter: 被替换的 SEC adapter 实例。
            request: runtime 传入的下载请求。

        Returns:
            有界 persisted summary。

        Raises:
            无。
        """

        del adapter
        assert request.source is FinsDownloadSource.SEC
        return FinsSourceDownloadAdapterResult(
            discovered_count=1,
            persisted_summary=_typed_download_summary(downloaded_ids=("aapl-production-10k",)),
        )

    monkeypatch.setattr(SecDownloadAdapter, "download", fake_sec_download)

    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert [event.source_event_type for event in progress_events] == [
        "download.started",
        "download.completed",
    ]
    assert progress_events[0].payload["ticker"] == "AAPL"
    assert progress_events[0].payload["source"] == "sec"
    assert progress_events[1].payload["downloaded_count"] == 1
    assert progress_events[1].payload["written_document_count"] == 1


def test_start_download_failed_count_emits_completed_with_failures_progress(tmp_path: Path) -> None:
    """下载摘要含失败计数时应产生 completed_with_failures progress。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _PersistedSummaryDownloadAdapter(
        _typed_download_summary(
            downloaded_ids=("aapl-partial-10k",),
            failed_ids=("aapl-failed-10q",),
        )
    )
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert [event.source_event_type for event in progress_events] == [
        "download.started",
        "download.completed_with_failures",
    ]
    assert progress_events[1].message == "下载已完成，存在失败候选"
    assert progress_events[1].payload["failed_count"] == 1
    assert progress_events[1].payload["downloaded_count"] == 1


def test_start_download_missing_adapter_writes_failed_terminal_record(tmp_path: Path) -> None:
    """无目标 adapter 时应返回明确 unsupported-source 失败。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={},
    )
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["discovered_count"] == 0
    assert record.result_summary["failed_count"] == 0
    assert "不支持的下载来源" in str(record.failure_summary["message"])
    assert "source=sec" in str(record.failure_summary["message"])
    assert "market=US" in str(record.failure_summary["message"])


def test_default_runtime_registers_production_download_adapters(tmp_path: Path) -> None:
    """默认 runtime 应为 US/CN/HK 装配确定性的 production download adapter。"""

    workspace_root = tmp_path / "fins-workspace"
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    sec_adapter = ingestion.download_adapters[("sec", "US")]
    auto_adapter = ingestion.download_adapters[("auto", "US")]
    cn_adapter = ingestion.download_adapters[("cninfo", "CN")]
    auto_cn_adapter = ingestion.download_adapters[("auto", "CN")]
    hk_adapter = ingestion.download_adapters[("hkexnews", "HK")]
    auto_hk_adapter = ingestion.download_adapters[("auto", "HK")]

    assert isinstance(sec_adapter, SecDownloadAdapter)
    assert auto_adapter is sec_adapter
    assert isinstance(cn_adapter, CnDownloadAdapter)
    assert auto_cn_adapter is cn_adapter
    assert isinstance(hk_adapter, CnDownloadAdapter)
    assert auto_hk_adapter is hk_adapter


@pytest.mark.asyncio
async def test_default_runtime_logs_missing_sec_user_agent_only_at_download_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单次 production download 应在首次请求前记录一次缺配置诊断。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest 环境变量隔离夹具。

    Returns:
        无。

    Raises:
        AssertionError: 装配期报警、单次请求重复报警或失败分类漂移时抛出。
    """

    monkeypatch.delenv(SEC_USER_AGENT_ENV, raising=False)
    log_stream = io.StringIO()
    runtime_log.configure(level=runtime_log.LogLevel.WARNING, stream=log_stream)
    ingestion = DefaultFinsRuntime.create(workspace_root=tmp_path / "fins-workspace").get_ingestion_runtime()

    assert "SEC User-Agent 未配置:" not in log_stream.getvalue()

    events = await _collect_direct_events(ingestion.download(build_fins_download_request(ticker="AAPL")))
    result = events[-1].result

    assert log_stream.getvalue().count("SEC User-Agent 未配置:") == 1
    assert result is not None
    assert result.status is FinsResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.transport_category is FinsDownloadTransportCategory.UNCONFIGURED


def test_start_download_repeated_request_skips_existing_source_document(tmp_path: Path) -> None:
    """重复语义请求应由 runtime storage 语义确定性跳过已有源文档。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    first = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    executor.run_all()
    first_record = ingestion.read_job(first.job_id)
    second = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    executor.run_all()
    second_record = ingestion.read_job(second.job_id)

    assert first_record.status is FinsIngestionJobStatus.SUCCEEDED
    assert first_record.result_summary["downloaded_count"] == 1
    assert second_record.status is FinsIngestionJobStatus.SUCCEEDED
    assert second_record.result_summary["downloaded_count"] == 0
    assert second_record.result_summary["skipped_count"] == 1
    assert second_record.result_summary["written_document_ids"] == []


def test_start_download_persists_rejected_filing_artifact(tmp_path: Path) -> None:
    """adapter 返回 rejected filing 时应通过 filing maintenance 仓储保存。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter(include_rejected=True)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    artifacts = runtime.filing_maintenance_repository.list_rejected_filing_artifacts("AAPL")
    registry = runtime.filing_maintenance_repository.load_download_rejection_registry("AAPL")
    content = runtime.filing_maintenance_repository.read_rejected_filing_file_bytes(
        "AAPL",
        "aapl-fake-rejected",
        "rejected.htm",
    )

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["discovered_count"] == 2
    assert record.result_summary["downloaded_count"] == 1
    assert record.result_summary["rejected_count"] == 1
    assert len(artifacts) == 1
    assert artifacts[0].document_id == "aapl-fake-rejected"
    assert artifacts[0].rejection_category == "form_filter"
    assert registry["aapl-fake-rejected"].document_id == "aapl-fake-rejected"
    assert registry["aapl-fake-rejected"].reason == "表单类型不在请求范围内"
    assert registry["aapl-fake-rejected"].category == "form_filter"
    assert content == b"<html>rejected</html>"


def test_start_download_persisted_summary_adapter_receives_local_rebuild(tmp_path: Path) -> None:
    """下载 adapter 应接收 local rebuild 标记并记录请求。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    adapter = _PersistedSummaryDownloadAdapter(
        _typed_download_summary(
            skipped_ids=("aapl-existing-10k",),
            rebuild_local_artifacts=True,
        )
    )
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    start = ingestion.start_download(
        build_fins_download_request(
            ticker="AAPL",
            rebuild_local_artifacts=True,
        )
    )
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.request_summary["rebuild_local_artifacts"] is True
    assert record.result_summary["skipped_count"] == 1
    assert len(adapter.requests) == 1
    assert adapter.requests[0].rebuild_local_artifacts is True


def test_start_preprocess_persists_queued_record_and_uses_public_ticker_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预处理启动应通过 ticker_normalization 并先持久化 queued record。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    original_normalize = ticker_normalization.normalize_ticker
    calls: list[str] = []

    def normalize_spy(raw: str) -> NormalizedTicker:
        """记录归一化调用并委托公共实现。

        Args:
            raw: 原始 ticker。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 非法时由公共实现抛出。
        """

        calls.append(raw)
        return original_normalize(raw)

    monkeypatch.setattr(ticker_normalization, "normalize_ticker", normalize_spy)

    start = runtime.start_preprocess(
        FinsPreprocessRequest(
            ticker="HK.00700",
            source_kind=SourceKind.FILING,
            document_ids=("tencent-2024-annual",),
            form_types=("annual",),
            rebuild_processed=True,
        )
    )
    record = runtime.read_job(start.job_id)

    assert calls == ["HK.00700"]
    assert record.status is FinsIngestionJobStatus.QUEUED
    assert len(executor.operations) == 1
    assert record.normalized_ticker == "0700"
    assert record.market == "HK"
    assert record.exchange == "HKEX"
    assert record.source is None
    assert record.source_kind is SourceKind.FILING
    assert record.request_summary["document_ids"] == ["tencent-2024-annual"]
    assert record.request_summary["rebuild_processed"] is True


def test_start_preprocess_allows_slash_in_document_ids(tmp_path: Path) -> None:
    """预处理请求应允许 document_id 中的业务合法斜杠。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    start = runtime.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("sec/aapl-2024-10ka",),
            form_types=("10-K/A",),
        )
    )
    record = runtime.read_job(start.job_id)

    assert record.request_summary["document_ids"] == ["sec/aapl-2024-10ka"]
    assert record.request_summary["form_types"] == ["10-K/A"]


def test_preprocess_request_round_trips_hierarchical_document_id_through_storage(
    tmp_path: Path,
) -> None:
    """hierarchical document ID 应从 preprocess 请求精确往返到 processed storage。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: document ID 被路径解释、归一化或丢失时抛出。
    """

    workspace_root = tmp_path / "hierarchical-preprocess"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    document_id = "sec/苹果\\2024/C:10-k/.."
    batch = batching.begin_batch("AAPL")
    handle = SourceHandle(
        ticker="AAPL",
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    file_meta = blob.store_file(
        handle,
        "report.md",
        io.BytesIO(_fixture_markdown().encode("utf-8")),
        batch=batch,
        content_type="text/markdown",
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document="report.md",
            files=[file_meta],
            meta={
                "ingest_method": FinsIngestMethod.UPLOAD.to_storage_value(),
                "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching.commit_batch(batch)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=(document_id,),
            form_types=("10-K",),
        )
    )
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["processed_document_ids"] == [document_id]
    assert (
        runtime.processed_repository.get_processed_meta(
            "AAPL",
            document_id,
        )["document_id"]
        == document_id
    )


def test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit(
    tmp_path: Path,
) -> None:
    """预处理 start 在 create 后、submit 前观察到取消时应标记 job 且不提交后台操作。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    token = _CancelOnSecondCheckToken()

    start = runtime.start_preprocess(FinsPreprocessRequest(ticker="AAPL"), cancellation_token=token)
    record = runtime.read_job(start.job_id)

    assert start.status is FinsIngestionJobStatus.CANCELLED
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert executor.operations == []


def test_start_upload_persists_queued_record_and_uses_public_ticker_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """上传启动应通过 ticker_normalization 并先持久化 queued record。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="ok",
        )
    )
    runtime = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)
    original_normalize = ticker_normalization.normalize_ticker
    calls: list[str] = []

    def normalize_upload_ticker(raw: str) -> NormalizedTicker:
        """记录归一化调用并委托公共实现。

        Args:
            raw: 原始 ticker。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 非法时由公共实现抛出。
        """

        calls.append(raw)
        return original_normalize(raw)

    monkeypatch.setattr(ticker_normalization, "normalize_ticker", normalize_upload_ticker)

    upload_file = tmp_path / "aapl-10k.pdf"
    upload_file.write_bytes(b"filing")
    start = runtime.start_upload(
        FinsUploadFilingRequest(
            ticker="aapl.us",
            action="CREATE",
            files=(upload_file,),
            fiscal_year=2024,
            fiscal_period="FY",
            amended=True,
            filing_date="2024-11-01",
            report_date="2024-09-28",
            company_name="Apple Inc.",
            ticker_aliases=("APPLE",),
        )
    )
    record = runtime.read_job(start.job_id)
    payload_text = _job_file(workspace_root, start.job_id).read_text(encoding="utf-8")

    assert calls[0] == "aapl.us"
    assert "APPLE" in calls
    assert start.status is FinsIngestionJobStatus.QUEUED
    assert record.operation_kind is FinsIngestionOperationKind.UPLOAD
    assert record.normalized_ticker == "AAPL"
    assert record.market == "US"
    assert record.source is None
    assert record.source_kind is SourceKind.FILING
    assert record.request_summary["source_kind"] == "filing"
    assert record.request_summary["action"] == "create"
    assert record.request_summary["file_count"] == 1
    assert record.request_summary["fiscal_year"] == 2024
    assert record.request_summary["amended"] is True
    assert record.request_summary["ticker_aliases"] == ["APPLE"]
    assert str(tmp_path) not in payload_text
    assert "aapl-10k.pdf" not in payload_text
    assert len(executor.operations) == 1
    assert runner.requests == []


def test_upload_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit(
    tmp_path: Path,
) -> None:
    """上传 start 在 create 后、submit 前观察到取消时应标记 job 且不提交后台操作。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    token = _CancelOnSecondCheckToken()

    start = runtime.start_upload(_valid_runtime_filing_request(), cancellation_token=token)
    record = runtime.read_job(start.job_id)

    assert start.status is FinsIngestionJobStatus.CANCELLED
    assert record.operation_kind is FinsIngestionOperationKind.UPLOAD
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert executor.operations == []


def test_start_upload_without_runner_writes_failed_terminal_record(tmp_path: Path) -> None:
    """未装配 upload runner 时应写入明确 unsupported upload runtime 失败终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            action="delete",
            document_id="aapl-investor-day",
            material_name="Investor Day",
        )
    )
    executor.run_all()
    record = runtime.read_job(start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.operation_kind is FinsIngestionOperationKind.UPLOAD
    assert record.source_kind is SourceKind.MATERIAL
    assert record.result_summary["source_kind"] == "material"
    assert record.result_summary["status"] == "failed"
    assert record.result_summary["uploaded_files"] == []
    assert "unsupported upload runtime" in str(record.failure_summary["message"])
    assert "production upload runner" in str(record.failure_summary["message"])


def test_start_upload_with_runner_writes_bounded_result_summary(tmp_path: Path) -> None:
    """上传 runner 结果应按有界 JSON 摘要写入 succeeded 终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.MATERIAL,
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
            status="ok",
            uploaded_files=("primary.pdf",),
            primary_document="primary.pdf",
            deleted=False,
            skip_reason=None,
            document_version="v2",
            source_fingerprint="sha256:abc123",
        )
    )
    runtime = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)

    start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            action="auto",
            files=(tmp_path / "primary.pdf",),
            form_type="8-K",
            material_name="Investor Day",
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
        )
    )
    executor.run_all()
    record = runtime.read_job(start.job_id)
    progress_events = _progress_events(runtime, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["source_kind"] == "material"
    assert record.result_summary["document_id"] == "aapl-investor-day"
    assert record.result_summary["internal_document_id"] == "aapl-investor-day-internal"
    assert record.result_summary["status"] == "ok"
    assert record.result_summary["uploaded_files"] == ["primary.pdf"]
    assert record.result_summary["primary_document"] == "primary.pdf"
    assert record.result_summary["deleted"] is False
    assert record.result_summary["document_version"] == "v2"
    assert record.result_summary["source_fingerprint"] == "sha256:abc123"
    assert len(runner.requests) == 1
    assert isinstance(runner.requests[0], FinsUploadMaterialRequest)
    assert runner.requests[0].action == "auto"
    assert runner.cancellation_checks == [False]
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed",
    ]
    assert progress_events[0].document_id == "aapl-investor-day"
    assert progress_events[0].payload["source_kind"] == "material"
    assert progress_events[0].payload["file_count"] == 1
    assert progress_events[1].document_id == "aapl-investor-day"
    assert progress_events[1].payload["upload_status"] == "ok"


@pytest.mark.asyncio
async def test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text(tmp_path: Path) -> None:
    """direct upload 用户事件不得暴露路径、job id、raw payload 或正文。"""

    workspace_root = tmp_path / "fins-workspace"
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="ok",
            uploaded_files=("primary.pdf",),
            primary_document="primary.pdf",
        )
    )
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=_HoldingExecutor(),
        upload_runner=runner,
    )
    upload_file = tmp_path / "raw" / "aapl-10k.pdf"
    upload_file.parent.mkdir(parents=True)
    upload_file.write_text("Annual recurring revenue increased raw provider payload", encoding="utf-8")

    events = await _collect_direct_events(
        ingestion.upload(
            FinsUploadFilingRequest(
                ticker="AAPL",
                files=(upload_file,),
                fiscal_year=2024,
                fiscal_period="FY",
                company_name="Apple Inc.",
            )
        )
    )
    event_text = repr(events)

    assert events[-1].result is not None
    assert events[-1].result.status is FinsResultStatus.SUCCESS
    assert str(tmp_path) not in event_text
    assert "aapl-10k.pdf" not in event_text
    assert "finsjob_" not in event_text
    assert "raw provider payload" not in event_text
    assert "Annual recurring revenue increased" not in event_text


def test_start_upload_failed_status_emits_completed_with_failures_progress(tmp_path: Path) -> None:
    """上传摘要为 failed 状态时应产生 completed_with_failures progress。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.MATERIAL,
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
            status="failed",
            failure_reason=fins_upload_failure_from_exception(RuntimeError()),
            uploaded_files=(),
            primary_document=None,
            deleted=False,
            skip_reason="fixture failure",
            document_version=None,
            source_fingerprint=None,
        )
    )
    runtime = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)

    start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            action="auto",
            files=(tmp_path / "primary.pdf",),
            form_type="8-K",
            material_name="Investor Day",
            document_id="aapl-investor-day",
            internal_document_id="aapl-investor-day-internal",
        )
    )
    executor.run_all()
    record = runtime.read_job(start.job_id)
    progress_events = _progress_events(runtime, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["status"] == "failed"
    assert record.failure_summary == {
        "kind": "runtime",
        "code": "unexpected_runtime",
        "message": "上传执行失败，请检查运行日志后重试",
        "retry_hint": None,
    }
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed_with_failures",
    ]
    assert progress_events[1].message == "上传已完成，存在失败"
    assert progress_events[1].document_id == "aapl-investor-day"
    assert progress_events[1].payload["upload_status"] == "failed"


@pytest.mark.parametrize(
    ("status", "projection_status", "expected_job_status"),
    (
        ("ok", "failed", FinsIngestionJobStatus.SUCCEEDED),
        ("failed", "ok", FinsIngestionJobStatus.FAILED),
    ),
)
def test_durable_upload_projection_failure_preserves_accepted_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    projection_status: str,
    expected_job_status: FinsIngestionJobStatus,
) -> None:
    """accepted terminal 保存后的投影异常不得改写 record 或追加终态事件。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。
        status: runner 返回的 accepted upload status。
        projection_status: fake store 返回给投影层的不一致 status。
        expected_job_status: 已持久化 record 的预期终态。

    Returns:
        无。

    Raises:
        AssertionError: fallback 未读取 durable 真源、终态被改写或追加事件时抛出。
    """

    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=executor,
        upload_runner=_FakeUploadRunner(
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status=status,
                failure_reason=_runtime_failure_for_status(status),
            )
        ),
    )
    start = runtime.start_upload(_valid_runtime_filing_request())
    original_save = ingestion_runtime.FsFinsIngestionJobStore.save_accepted_upload_terminal_if_active
    original_read = ingestion_runtime.FsFinsIngestionJobStore.read_job
    accepted_records: list[ingestion_runtime.FinsIngestionJobRecord] = []
    fallback_reads: list[ingestion_runtime.FinsIngestionJobRecord] = []

    def save_then_return_invalid_projection_record(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        disposition: FinsUploadTerminalDisposition,
        result_summary: dict[str, JsonValue],
        failure_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """先由真实 store 保存终态，再向投影层返回不一致的 fake record。

        Args:
            store: 文件系统 job store。
            job_id: opaque job id。
            disposition: workflow 已接受的 upload disposition。
            result_summary: upload 结果摘要。
            failure_summary: upload 失败摘要。
            finished_at: 终态写入时间。

        Returns:
            仅供投影消费、status 与 durable record 不一致的 fake record。

        Raises:
            OSError: 真实 store 保存失败时抛出。
            ValueError: 真实 store contract 校验失败时抛出。
        """

        saved = original_save(
            store,
            job_id,
            disposition=disposition,
            result_summary=result_summary,
            failure_summary=failure_summary,
            finished_at=finished_at,
        )
        accepted_records.append(saved)
        return replace(
            saved,
            result_summary={**saved.result_summary, "status": projection_status},
        )

    def record_fallback_read(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """记录异常收口从 durable owner 重读的终态。

        Args:
            store: 文件系统 job store。
            job_id: opaque job id。

        Returns:
            durable owner 中的真实 job record。

        Raises:
            FileNotFoundError: job id 不存在时抛出。
            OSError: 文件系统读取失败时抛出。
            ValueError: durable record 非法时抛出。
        """

        record = original_read(store, job_id)
        if accepted_records:
            fallback_reads.append(record)
        return record

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_accepted_upload_terminal_if_active",
        save_then_return_invalid_projection_record,
    )
    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "read_job",
        record_fallback_read,
    )

    executor.run_all()

    store = cast(ingestion_runtime.FsFinsIngestionJobStore, runtime.job_store)
    record = original_read(store, start.job_id)
    events = runtime.read_job_events(start.job_id, after_sequence=0, limit=100)
    terminal_events = tuple(
        event
        for event in events
        if event.event_type
        in {
            FinsIngestionJobEventType.JOB_SUCCEEDED,
            FinsIngestionJobEventType.JOB_FAILED,
            FinsIngestionJobEventType.JOB_CANCELLED,
        }
    )

    assert len(accepted_records) == 1
    assert fallback_reads == accepted_records
    assert record == accepted_records[0]
    assert record.status is expected_job_status
    assert record.result_summary["status"] == status
    assert terminal_events == ()


def test_durable_upload_cancel_before_final_checkpoint_saves_only_cancelled(
    tmp_path: Path,
) -> None:
    """时点 a：durable runner final checkpoint 前取消只保存 cancelled。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: barrier、record 或 event 单终态不符合契约时抛出。
    """

    executor = _HoldingExecutor()
    runner = _BarrierUploadRunner(
        accepted_summary=FinsUploadResultSummary(source_kind=SourceKind.FILING, status="ok"),
        observe_cancel_before_summary=True,
    )
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=executor,
        upload_runner=runner,
    )
    start = runtime.start_upload(_valid_runtime_filing_request())
    operation_thread = Thread(target=executor.run_all)
    operation_thread.start()
    assert runner.boundary_reached.wait(timeout=1.0)
    runtime.request_cancel(start.job_id)
    runner.release_summary.set()
    operation_thread.join(timeout=1.0)

    record = runtime.read_job(start.job_id)
    events = runtime.read_job_events(start.job_id, after_sequence=0, limit=100)
    progress_types = tuple(
        event.source_event_type for event in events if event.event_type is FinsIngestionJobEventType.PROGRESS
    )
    terminal_types = tuple(
        event.event_type
        for event in events
        if event.event_type
        in {
            FinsIngestionJobEventType.JOB_SUCCEEDED,
            FinsIngestionJobEventType.JOB_FAILED,
            FinsIngestionJobEventType.JOB_CANCELLED,
        }
    )

    assert not operation_thread.is_alive()
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert progress_types == ("upload.started",)
    assert terminal_types == (FinsIngestionJobEventType.JOB_CANCELLED,)


def test_durable_upload_cancel_after_commit_before_summary_keeps_completed(
    tmp_path: Path,
) -> None:
    """时点 b：durable publication commit 后、summary 返回前取消保持 completed。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: barrier、record 或 event 投影不符合契约时抛出。
    """

    executor = _HoldingExecutor()
    runner = _BarrierUploadRunner(
        accepted_summary=FinsUploadResultSummary(source_kind=SourceKind.FILING, status="ok"),
        observe_cancel_before_summary=False,
    )
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=executor,
        upload_runner=runner,
    )
    start = runtime.start_upload(_valid_runtime_filing_request())
    operation_thread = Thread(target=executor.run_all)
    operation_thread.start()
    assert runner.boundary_reached.wait(timeout=1.0)
    runtime.request_cancel(start.job_id)
    runner.release_summary.set()
    operation_thread.join(timeout=1.0)

    record = runtime.read_job(start.job_id)
    progress_events = _progress_events(runtime, start.job_id)

    assert not operation_thread.is_alive()
    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.cancellation_requested
    assert record.result_summary["status"] == "ok"
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed",
    ]
    assert progress_events[-1].status is FinsIngestionJobStatus.SUCCEEDED


@pytest.mark.parametrize(
    ("status", "expected_job_status", "expected_progress", "expected_terminal"),
    (
        (
            "ok",
            FinsIngestionJobStatus.SUCCEEDED,
            "upload.completed",
            FinsIngestionJobEventType.JOB_SUCCEEDED,
        ),
        (
            "failed",
            FinsIngestionJobStatus.FAILED,
            "upload.completed_with_failures",
            FinsIngestionJobEventType.JOB_FAILED,
        ),
    ),
)
def test_durable_upload_cancel_before_atomic_save_keeps_accepted_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected_job_status: FinsIngestionJobStatus,
    expected_progress: str,
    expected_terminal: FinsIngestionJobEventType,
) -> None:
    """时点 c：accepted summary 返回后、atomic save 前取消不得改写终态。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。
        status: accepted upload summary status。
        expected_job_status: 预期 durable job status。
        expected_progress: 预期 completed progress 类型。
        expected_terminal: 预期 terminal event 类型。

    Returns:
        无。

    Raises:
        AssertionError: save barrier、record 或 event 投影不符合契约时抛出。
    """

    save_entered = Event()
    release_save = Event()
    original_save = ingestion_runtime.FsFinsIngestionJobStore.save_accepted_upload_terminal_if_active

    def save_after_release(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        disposition: FinsUploadTerminalDisposition,
        result_summary: dict[str, JsonValue],
        failure_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """在 accepted terminal 原子保存前等待测试释放。

        Args:
            store: 文件系统 job store。
            job_id: opaque job id。
            disposition: accepted upload disposition。
            result_summary: upload 结果摘要。
            failure_summary: upload 失败摘要。
            finished_at: 终态写入时间。

        Returns:
            原 owner 保存的最终 record。

        Raises:
            AssertionError: barrier 未在期限内释放时抛出。
            OSError: 原 owner 文件系统写入失败时抛出。
            ValueError: 原 owner contract 校验失败时抛出。
        """

        save_entered.set()
        assert release_save.wait(timeout=1.0)
        return original_save(
            store,
            job_id,
            disposition=disposition,
            result_summary=result_summary,
            failure_summary=failure_summary,
            finished_at=finished_at,
        )

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_accepted_upload_terminal_if_active",
        save_after_release,
    )
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=executor,
        upload_runner=_FakeUploadRunner(
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status=status,
                failure_reason=_runtime_failure_for_status(status),
            )
        ),
    )
    start = runtime.start_upload(_valid_runtime_filing_request())
    operation_thread = Thread(target=executor.run_all)
    operation_thread.start()
    assert save_entered.wait(timeout=1.0)
    runtime.request_cancel(start.job_id)
    release_save.set()
    operation_thread.join(timeout=1.0)

    record = runtime.read_job(start.job_id)
    events = runtime.read_job_events(start.job_id, after_sequence=0, limit=100)

    assert not operation_thread.is_alive()
    assert record.status is expected_job_status
    assert record.cancellation_requested
    assert record.result_summary["status"] == status
    assert [event.source_event_type for event in _progress_events(runtime, start.job_id)] == [
        "upload.started",
        expected_progress,
    ]
    assert [event.event_type for event in events].count(expected_terminal) == 1
    assert [event.event_type for event in events].count(FinsIngestionJobEventType.JOB_CANCELLED) == 0


@pytest.mark.parametrize(
    ("status", "expected_job_status", "expected_progress"),
    (
        ("ok", FinsIngestionJobStatus.SUCCEEDED, "upload.completed"),
        ("failed", FinsIngestionJobStatus.FAILED, "upload.completed_with_failures"),
    ),
)
def test_durable_upload_cancel_after_atomic_save_keeps_single_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected_job_status: FinsIngestionJobStatus,
    expected_progress: str,
) -> None:
    """时点 d：atomic save 后取消不得改变 record 或制造第二终态。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: pytest monkeypatch 夹具。
        status: accepted upload summary status。
        expected_job_status: 预期 durable job status。
        expected_progress: 预期 completed progress 类型。

    Returns:
        无。

    Raises:
        AssertionError: save barrier、record 或单终态不符合契约时抛出。
    """

    save_completed = Event()
    release_projection = Event()
    original_save = ingestion_runtime.FsFinsIngestionJobStore.save_accepted_upload_terminal_if_active

    def save_then_hold(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        disposition: FinsUploadTerminalDisposition,
        result_summary: dict[str, JsonValue],
        failure_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """原子保存 accepted terminal 后暂停 progress/event 投影。

        Args:
            store: 文件系统 job store。
            job_id: opaque job id。
            disposition: accepted upload disposition。
            result_summary: upload 结果摘要。
            failure_summary: upload 失败摘要。
            finished_at: 终态写入时间。

        Returns:
            原 owner 保存的最终 record。

        Raises:
            AssertionError: barrier 未在期限内释放时抛出。
            OSError: 原 owner 文件系统写入失败时抛出。
            ValueError: 原 owner contract 校验失败时抛出。
        """

        saved = original_save(
            store,
            job_id,
            disposition=disposition,
            result_summary=result_summary,
            failure_summary=failure_summary,
            finished_at=finished_at,
        )
        save_completed.set()
        assert release_projection.wait(timeout=1.0)
        return saved

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_accepted_upload_terminal_if_active",
        save_then_hold,
    )
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=executor,
        upload_runner=_FakeUploadRunner(
            FinsUploadResultSummary(
                source_kind=SourceKind.FILING,
                status=status,
                failure_reason=_runtime_failure_for_status(status),
            )
        ),
    )
    start = runtime.start_upload(_valid_runtime_filing_request())
    operation_thread = Thread(target=executor.run_all)
    operation_thread.start()
    assert save_completed.wait(timeout=1.0)
    after_terminal_cancel = runtime.request_cancel(start.job_id)
    release_projection.set()
    operation_thread.join(timeout=1.0)

    record = runtime.read_job(start.job_id)
    events = runtime.read_job_events(start.job_id, after_sequence=0, limit=100)
    terminal_events = tuple(
        event
        for event in events
        if event.event_type
        in {
            FinsIngestionJobEventType.JOB_SUCCEEDED,
            FinsIngestionJobEventType.JOB_FAILED,
            FinsIngestionJobEventType.JOB_CANCELLED,
        }
    )

    assert not operation_thread.is_alive()
    assert after_terminal_cancel.status is expected_job_status
    assert record.status is expected_job_status
    assert not record.cancellation_requested
    assert [event.source_event_type for event in _progress_events(runtime, start.job_id)] == [
        "upload.started",
        expected_progress,
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0].status is expected_job_status


def test_accepted_upload_terminal_store_rejects_mismatch_and_preserves_existing_terminal(
    tmp_path: Path,
) -> None:
    """upload atomic store 只接受匹配字段，并且不得覆盖已有 terminal。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: strict validation 或 existing-terminal 原子语义不符合契约时抛出。
    """

    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(tmp_path / "fins-workspace", executor=executor)
    start = runtime.start_upload(_valid_runtime_filing_request())
    store = runtime.job_store
    completed_summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status="ok",
    ).to_json_summary()
    failed_summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status="failed",
        failure_reason=fins_upload_failure_from_exception(RuntimeError()),
    ).to_json_summary()
    finished_at = datetime.now(timezone.utc).isoformat()

    with pytest.raises(ValueError, match="不接受 cancelled"):
        store.save_accepted_upload_terminal_if_active(
            start.job_id,
            disposition=FinsUploadTerminalDisposition.CANCELLED,
            result_summary={"status": "cancelled"},
            failure_summary={},
            finished_at=finished_at,
        )
    with pytest.raises(ValueError, match="不一致"):
        store.save_accepted_upload_terminal_if_active(
            start.job_id,
            disposition=FinsUploadTerminalDisposition.COMPLETED,
            result_summary=failed_summary,
            failure_summary={},
            finished_at=finished_at,
        )
    with pytest.raises(ValueError, match="必须包含 failure_summary"):
        store.save_accepted_upload_terminal_if_active(
            start.job_id,
            disposition=FinsUploadTerminalDisposition.FAILED,
            result_summary=failed_summary,
            failure_summary={},
            finished_at=finished_at,
        )
    with pytest.raises(ValueError, match="不得包含 failure_summary"):
        store.save_accepted_upload_terminal_if_active(
            start.job_id,
            disposition=FinsUploadTerminalDisposition.COMPLETED,
            result_summary=completed_summary,
            failure_summary={"message": "unexpected"},
            finished_at=finished_at,
        )

    saved = store.save_accepted_upload_terminal_if_active(
        start.job_id,
        disposition=FinsUploadTerminalDisposition.COMPLETED,
        result_summary=completed_summary,
        failure_summary={},
        finished_at=finished_at,
    )
    preserved = store.save_accepted_upload_terminal_if_active(
        start.job_id,
        disposition=FinsUploadTerminalDisposition.FAILED,
        result_summary=failed_summary,
        failure_summary={"message": "late failure"},
        finished_at=datetime.now(timezone.utc).isoformat(),
    )

    assert saved.status is FinsIngestionJobStatus.SUCCEEDED
    assert preserved == saved
    assert runtime.read_job(start.job_id) == saved


def test_default_runtime_start_upload_sec_filing_uses_production_runner(tmp_path: Path) -> None:
    """DefaultFinsRuntime 应装配 production runner 并执行 SEC filing 上传。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = default_runtime.get_ingestion_runtime()
    _inject_upload_runtime_converter(default_runtime, ingestion)
    upload_runner = ingestion.upload_runner
    assert isinstance(upload_runner, ProductionFinsUploadRunner)
    filing_file = tmp_path / "aapl-10q.pdf"
    filing_file.write_text("runtime sec filing", encoding="utf-8")

    start = ingestion.start_upload(
        FinsUploadFilingRequest(
            ticker="AAPL",
            action="create",
            files=(filing_file,),
            fiscal_year=2025,
            fiscal_period="Q1",
            filing_date="2025-05-01",
            report_date="2025-03-31",
            company_name="Apple Inc.",
            overwrite=False,
        )
    )
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["source_kind"] == "filing"
    assert record.result_summary["status"] == "ok"
    assert record.result_summary["primary_document"] == "aapl-10q_docling.json"
    document_id = str(record.result_summary["document_id"])
    meta = ingestion.source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    assert meta["ingest_method"] == "upload"
    assert meta["primary_document"] == "aapl-10q_docling.json"
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed",
    ]
    assert progress_events[0].payload["source_kind"] == "filing"
    assert progress_events[0].payload["file_count"] == 1
    assert progress_events[1].payload["upload_status"] == "ok"


def test_default_runtime_start_upload_cn_material_uses_production_runner(tmp_path: Path) -> None:
    """DefaultFinsRuntime 应装配 production runner 并执行 CN material 上传。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = default_runtime.get_ingestion_runtime()
    _inject_upload_runtime_converter(default_runtime, ingestion)
    upload_runner = ingestion.upload_runner
    assert isinstance(upload_runner, ProductionFinsUploadRunner)
    material_file = tmp_path / "deck.pdf"
    material_file.write_text("runtime cn material", encoding="utf-8")

    start = ingestion.start_upload(
        FinsUploadMaterialRequest(
            ticker="600519",
            action="create",
            files=(material_file,),
            form_type="MATERIAL_OTHER",
            material_name="Deck",
            company_name="贵州茅台",
            overwrite=False,
        )
    )
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.market == "CN"
    assert record.result_summary["source_kind"] == "material"
    assert record.result_summary["status"] == "ok"
    assert record.result_summary["primary_document"] == "deck_docling.json"
    document_id = str(record.result_summary["document_id"])
    meta = ingestion.source_repository.get_source_meta("600519", document_id, SourceKind.MATERIAL)
    assert meta["material_name"] == "Deck"
    assert meta["primary_document"] == "deck_docling.json"


def test_upload_request_and_result_summaries_enforce_bounds(tmp_path: Path) -> None:
    """上传请求与结果摘要应执行数量和长度边界。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    too_many_aliases = tuple(f"alias-{index}" for index in range(ingestion_runtime._MAX_TUPLE_ITEMS + 1))
    too_many_files = tuple(f"file-{index}.pdf" for index in range(ingestion_runtime._MAX_TUPLE_ITEMS + 1))

    with pytest.raises(FinsUploadUsageError) as aliases_exc:
        runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL", ticker_aliases=too_many_aliases))
    assert aliases_exc.value.failure.code is FinsUploadUsageCode.TOO_MANY_TICKER_ALIASES
    with pytest.raises(ValueError, match="uploaded_files 元素数量超出上限"):
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="ok",
            uploaded_files=too_many_files,
        ).to_json_summary()
    assert executor.operations == []


def test_upload_requests_use_source_kind_for_filing_material_discrimination(tmp_path: Path) -> None:
    """上传请求应使用 SourceKind 区分 filing/material，错误组合在建 job 前失败。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    with pytest.raises(FinsUploadUsageError) as source_kind_exc:
        runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL", source_kind=SourceKind.MATERIAL))
    assert source_kind_exc.value.failure.code is FinsUploadUsageCode.INVALID_SOURCE_KIND
    with pytest.raises(ValueError, match="material 上传请求必须使用 source_kind=material"):
        runtime.start_upload(FinsUploadMaterialRequest(ticker="AAPL", source_kind=SourceKind.FILING))

    material_start = runtime.start_upload(
        FinsUploadMaterialRequest(
            ticker="AAPL",
            source_kind=SourceKind.MATERIAL,
            document_id="aapl-investor-day",
        )
    )
    material_record = runtime.read_job(material_start.job_id)

    assert material_record.source_kind is SourceKind.MATERIAL
    assert material_record.request_summary["source_kind"] == "material"
    assert material_record.request_summary["document_id"] == "aapl-investor-day"
    assert len(executor.operations) == 1


def test_result_summaries_allow_slash_in_document_ids() -> None:
    """结果摘要中的 document-id 类字段应允许业务合法斜杠。"""

    download_summary = _typed_download_summary(downloaded_ids=("sec/aapl-2024-10ka",))
    preprocess_summary = FinsPreprocessResultSummary(
        selected_count=1,
        processed_count=1,
        processed_document_ids=("processed/aapl-2024-10ka",),
    )
    upload_summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status="ok",
        document_id="sec/aapl-2024-10ka",
        internal_document_id="sec/aapl-2024-10ka-internal",
    )

    assert download_summary.to_json_summary()["written_document_ids"] == ["sec/aapl-2024-10ka"]
    assert preprocess_summary.to_json_summary()["processed_document_ids"] == ["processed/aapl-2024-10ka"]
    assert upload_summary.to_json_summary()["document_id"] == "sec/aapl-2024-10ka"
    assert upload_summary.to_json_summary()["internal_document_id"] == "sec/aapl-2024-10ka-internal"


def test_preprocess_result_status_separates_skipped_and_not_supported() -> None:
    """预处理状态 helper 应区分 skipped 与 not_supported 语义。"""

    skipped_only = FinsPreprocessResultSummary(
        selected_count=1,
        skipped_count=1,
        skipped_document_ids=("aapl-2024-10k",),
    )
    unsupported_only = FinsPreprocessResultSummary(
        selected_count=1,
        not_supported_count=1,
        not_supported_document_ids=("aapl-2024-10k",),
    )

    assert skipped_only.result_status() is FinsPreprocessResultStatus.SUCCEEDED
    assert unsupported_only.result_status() is FinsPreprocessResultStatus.FAILED
    assert unsupported_only.to_json_summary()["skipped_count"] == 0
    assert unsupported_only.to_json_summary()["not_supported_count"] == 1


def test_preprocess_result_status_rejects_over_classified_counts() -> None:
    """预处理状态 helper 应拒绝分类计数超过选择数量的摘要。"""

    over_classified = FinsPreprocessResultSummary(
        selected_count=1,
        processed_count=1,
        skipped_count=1,
        processed_document_ids=("aapl-2024-10k",),
        skipped_document_ids=("msft-2024-10k",),
    )
    cancellation_partial = FinsPreprocessResultSummary(
        selected_count=2,
        skipped_count=1,
        skipped_document_ids=("aapl-2024-10k",),
    )

    with pytest.raises(ValueError, match="selected_count"):
        over_classified.result_status()
    assert cancellation_partial.result_status() is FinsPreprocessResultStatus.SUCCEEDED


def test_upload_pipeline_result_requires_status() -> None:
    """upload pipeline typed result 不得用 unknown 伪造缺失状态。"""

    with pytest.raises(ValueError, match="status"):
        FinsUploadPipelineResult.from_pipeline_json({"document_id": "aapl-2024-10k"})


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        ("ok", FinsUploadTerminalDisposition.COMPLETED),
        ("skipped", FinsUploadTerminalDisposition.COMPLETED),
        ("deleted", FinsUploadTerminalDisposition.COMPLETED),
        ("failed", FinsUploadTerminalDisposition.FAILED),
        ("cancelled", FinsUploadTerminalDisposition.CANCELLED),
    ),
)
def test_upload_status_owner_maps_only_exact_production_statuses(
    status: str,
    expected: FinsUploadTerminalDisposition,
) -> None:
    """pipeline result 与 runtime summary 必须复用同一个 exact status owner。

    Args:
        status: 合法 production upload status。
        expected: 对应的 closed terminal disposition。

    Returns:
        无。

    Raises:
        AssertionError: 两个 owner boundary 的映射不一致时抛出。
    """

    pipeline_json: dict[str, JsonValue] = {"status": status}
    if status == "failed":
        pipeline_json["failure"] = {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
        }
    pipeline_result = FinsUploadPipelineResult.from_pipeline_json(pipeline_json)
    summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status=status,
        failure_reason=_runtime_failure_for_status(status),
    )

    assert pipeline_result.status == status
    assert summary.terminal_disposition() is expected


@pytest.mark.parametrize(
    "status",
    ("uploaded", "unknown", "OK", " ok", "ok ", "", "CANCELLED"),
)
def test_upload_status_owner_rejects_unknown_case_and_whitespace_variants(status: str) -> None:
    """upload status owner 不得 loose parse、兼容 alias 或默认成功。

    Args:
        status: 非法或非 exact status。

    Returns:
        无。

    Raises:
        AssertionError: pipeline 或 summary boundary 未抛 ``ValueError`` 时抛出。
    """

    with pytest.raises(ValueError, match="upload status"):
        FinsUploadPipelineResult.from_pipeline_json({"status": status})
    with pytest.raises(ValueError, match="upload status"):
        FinsUploadResultSummary(source_kind=SourceKind.FILING, status=status)


def test_prepare_observed_operations_do_not_submit_until_activation(tmp_path: Path) -> None:
    """download/preprocess/upload prepare 只登记 observation，activation 才提交。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    download = runtime.prepare_observed_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )
    preprocess = runtime.prepare_observed_preprocess(
        FinsPreprocessRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )
    upload = runtime.prepare_observed_upload(
        _valid_runtime_filing_request(),
        cancellation_token=_NeverCancelledToken(),
    )

    assert executor.operations == []

    runtime.activate_observation(download)
    runtime.activate_observation(preprocess)
    runtime.activate_observation(upload)

    assert len(executor.operations) == 3


def test_activate_observation_is_idempotent_for_same_handle(tmp_path: Path) -> None:
    """同一 observation 重复 activation 不得 double-submit。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    runtime.activate_observation(handle)
    runtime.activate_observation(handle)

    assert len(executor.operations) == 1


def test_cancel_prepared_observation_prevents_later_activation_submit(
    tmp_path: Path,
) -> None:
    """prepared observation activation 前取消后不得提交，并可观察为 CANCELLED。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_preprocess(
        FinsPreprocessRequest(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    cancelled = asyncio.run(runtime.cancel_observation(handle))
    runtime.activate_observation(handle)
    polled = asyncio.run(runtime.poll_observation(handle))

    assert cancelled.status is FinsObservationStatus.CANCELLED
    assert cancelled.result is not None
    assert cancelled.result.status is FinsResultStatus.CANCELLED
    assert cancelled.result.error_kind is FinsErrorKind.CANCELLED
    assert cancelled.result.error_message == direct_failure_message(
        error_kind=FinsErrorKind.CANCELLED,
        fallback_message=None,
    )
    cancelled_error_message = cancelled.result.error_message
    assert cancelled_error_message is not None
    assert "Observation" not in cancelled_error_message
    assert polled.status is FinsObservationStatus.CANCELLED
    assert executor.operations == []


def test_abandon_cancelled_prepared_observation_releases_handle_before_activation(
    tmp_path: Path,
) -> None:
    """prepared observation 取消并 abandon 后不得提交且 handle 应释放。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    cancelled = asyncio.run(runtime.cancel_observation(handle))
    asyncio.run(runtime.abandon_observation(handle))
    runtime.activate_observation(handle)
    polled = asyncio.run(runtime.poll_observation(handle))

    assert cancelled.status is FinsObservationStatus.CANCELLED
    assert polled.status is FinsObservationStatus.LOST
    assert executor.operations == []


def test_abandoned_observation_does_not_pollute_repeat_download_observation(
    tmp_path: Path,
) -> None:
    """旧 observation abandon 后，第二次同类下载 observation 应独立完成。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    adapter = _FakeDownloadAdapter()
    runtime = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )
    first = runtime.prepare_observed_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    runtime.activate_observation(first)
    first_cancelled = asyncio.run(runtime.cancel_observation(first))
    asyncio.run(runtime.abandon_observation(first))
    second = runtime.prepare_observed_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )
    runtime.activate_observation(second)
    executor.run_all()
    first_polled = asyncio.run(runtime.poll_observation(first))
    second_polled = asyncio.run(runtime.poll_observation(second))

    assert first_cancelled.status is FinsObservationStatus.PENDING
    assert first_polled.status is FinsObservationStatus.LOST
    assert second_polled.status is FinsObservationStatus.SUCCEEDED
    assert second_polled.result is not None
    assert second_polled.result.status is FinsResultStatus.SUCCESS
    assert [request.source for request in adapter.requests] == [FinsDownloadSource.SEC]


def test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts(
    tmp_path: Path,
) -> None:
    """submitted observation abandon 后应协作式取消并保留已写入仓储产物。"""

    workspace_root = tmp_path / "fins-workspace"
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    document_id = "aapl-observed-upload"
    runner = _BlockingArtifactUploadRunner(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        document_id=document_id,
    )
    runtime = ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=executor,
        upload_runner=runner,
    )
    handle = runtime.prepare_observed_upload(
        _valid_runtime_filing_request(),
        cancellation_token=_NeverCancelledToken(),
    )

    runtime.activate_observation(handle)
    operation_thread = Thread(target=executor.run_all)
    operation_thread.start()
    assert runner.artifact_written.wait(timeout=1.0)

    asyncio.run(runtime.abandon_observation(handle))
    runner.allow_finish.set()
    operation_thread.join(timeout=1.0)
    polled = asyncio.run(runtime.poll_observation(handle))
    source_meta = default_runtime.source_repository.get_source_meta(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )

    assert not operation_thread.is_alive()
    assert runner.cancellation_checks == (True,)
    assert polled.status is FinsObservationStatus.LOST
    assert source_meta["ingest_method"] == "upload"


def test_cancel_and_activate_share_observation_lock_without_timing_sleep(
    tmp_path: Path,
) -> None:
    """cancel 持有 observation lock 时 activation 必须等待同一把锁。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    handle = runtime.prepare_observed_upload(
        _valid_runtime_filing_request(),
        cancellation_token=_NeverCancelledToken(),
    )
    hooked_lock = _HookedObservationLock()
    object.__setattr__(runtime, "_observation_lock", hooked_lock)
    snapshots: list[FinsObservationStatus] = []
    exceptions: list[BaseException] = []

    def cancel_operation() -> None:
        """执行取消并记录结果。"""

        try:
            snapshot = asyncio.run(runtime.cancel_observation(handle))
            snapshots.append(snapshot.status)
        except BaseException as exc:
            exceptions.append(exc)

    def activate_operation() -> None:
        """执行 activation 并记录异常。"""

        try:
            runtime.activate_observation(handle)
        except BaseException as exc:
            exceptions.append(exc)

    cancel_thread = Thread(target=cancel_operation)
    cancel_thread.start()
    assert hooked_lock.first_entered.wait(timeout=1.0)

    activate_thread = Thread(target=activate_operation)
    activate_thread.start()
    assert hooked_lock.second_enter_attempted.wait(timeout=1.0)
    assert executor.operations == []

    hooked_lock.allow_first_exit.set()
    cancel_thread.join(timeout=1.0)
    activate_thread.join(timeout=1.0)

    assert not cancel_thread.is_alive()
    assert not activate_thread.is_alive()
    assert exceptions == []
    assert snapshots == [FinsObservationStatus.CANCELLED]
    assert executor.operations == []


def test_activation_submit_failure_terminalizes_prepared_observation(
    tmp_path: Path,
) -> None:
    """activation submit failure 必须把 prepared observation 转为 FAILED。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = _build_ingestion_runtime(
        workspace_root,
        executor=_FailingSubmitExecutor(OSError("submit unavailable")),
    )
    handle = runtime.prepare_observed_download(
        build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
    )

    with pytest.raises(OSError):
        runtime.activate_observation(handle)
    snapshot = asyncio.run(runtime.poll_observation(handle))

    assert snapshot.status is FinsObservationStatus.FAILED


def test_unexpected_activation_exception_terminalizes_prepared_observation(
    tmp_path: Path,
) -> None:
    """prepared observation 存在后 activation 非预期异常不得遗留 PENDING。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = _build_ingestion_runtime(
        workspace_root,
        executor=_FailingSubmitExecutor(ValueError("unexpected activation error")),
    )
    handle = runtime.prepare_observed_upload(
        _valid_runtime_filing_request(),
        cancellation_token=_NeverCancelledToken(),
    )

    with pytest.raises(ValueError):
        runtime.activate_observation(handle)
    snapshot = asyncio.run(runtime.poll_observation(handle))

    assert snapshot.status is FinsObservationStatus.FAILED
    assert snapshot.result is not None
    assert snapshot.result.error_message == direct_failure_message(
        error_kind=FinsErrorKind.EXECUTION,
        fallback_message=None,
    )
    activation_error_message = snapshot.result.error_message
    assert activation_error_message is not None
    assert "Observation" not in activation_error_message


def test_observed_producer_without_result_uses_helper_failure_message(
    tmp_path: Path,
) -> None:
    """observed producer 静默结束时终态错误说明不得泄漏 observation 诊断文本。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    normalized = ticker_normalization.normalize_ticker("AAPL")

    def quiet_producer(context: ingestion_runtime._FinsIngestionExecutionContext) -> None:
        """模拟未投递 RESULT 的 observed producer。

        Args:
            context: direct stream 执行上下文。

        Returns:
            无。

        Raises:
            无。
        """

        del context

    handle = runtime._prepare_observed_stream(
        direct_operation_kind=FinsOperationKind.DOWNLOAD,
        operation_kind=FinsIngestionOperationKind.DOWNLOAD,
        normalized=normalized,
        source="fake",
        source_kind=SourceKind.FILING,
        download_request=build_fins_download_request(ticker="AAPL"),
        cancellation_token=_NeverCancelledToken(),
        producer=quiet_producer,
    )

    runtime.activate_observation(handle)
    executor.run_all()
    snapshot = asyncio.run(runtime.poll_observation(handle))

    assert snapshot.status is FinsObservationStatus.FAILED
    assert snapshot.result is not None
    assert snapshot.result.error_message == direct_failure_message(
        error_kind=FinsErrorKind.EXECUTION,
        fallback_message=None,
    )
    missing_result_error_message = snapshot.result.error_message
    assert missing_result_error_message is not None
    assert "Observation" not in missing_result_error_message


def test_job_serialization_validates_upload_operation_shape(tmp_path: Path) -> None:
    """upload job record 序列化/反序列化应校验 operation/source/source_kind 组合。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)
    start = runtime.start_upload(_valid_runtime_filing_request())
    job_file = _job_file(workspace_root, start.job_id)
    payload_value = cast(JsonValue, json.loads(job_file.read_text(encoding="utf-8")))

    assert isinstance(payload_value, Mapping)
    assert payload_value["operation_kind"] == "upload"
    assert payload_value["source"] is None
    assert payload_value["source_kind"] == "filing"

    corrupt_payload = dict(cast(Mapping[str, JsonValue], payload_value))
    corrupt_payload["source_kind"] = None
    job_file.write_text(json.dumps(corrupt_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="upload job record 必须包含 source_kind"):
        runtime.read_job(start.job_id)


def test_request_cancel_marks_active_job_and_keeps_terminal_job_terminal(tmp_path: Path) -> None:
    """取消请求应标记 active job，且不得把终态 job 回退为 active。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    queued_start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    cancelled = ingestion.request_cancel(queued_start.job_id)

    terminal_start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="MSFT"))
    terminal_record = replace(
        terminal_start.record,
        status=FinsIngestionJobStatus.SUCCEEDED,
        result_summary={"processed_count": 0},
        finished_at=terminal_start.record.updated_at,
    )
    ingestion.job_store.save_job(terminal_record)
    after_terminal_cancel = ingestion.request_cancel(terminal_start.job_id)

    assert cancelled.status is FinsIngestionJobStatus.CANCELLING
    assert cancelled.cancellation_requested
    assert after_terminal_cancel.status is FinsIngestionJobStatus.SUCCEEDED
    assert not after_terminal_cancel.cancellation_requested
    assert after_terminal_cancel.result_summary == {"processed_count": 0}


def test_job_events_record_queued_running_and_terminal_sequence(tmp_path: Path) -> None:
    """job 创建、running claim 与终态保存应产生单调递增状态事件。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )

    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    queued_events = ingestion.read_job_events(start.job_id)
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id, after_sequence=0, limit=100)
    after_first = ingestion.read_job_events(start.job_id, after_sequence=1, limit=100)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert [event.event_type for event in queued_events] == [FinsIngestionJobEventType.JOB_QUEUED]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
    ]
    assert [event.sequence for event in after_first] == [2, 3, 4, 5]


def test_request_cancel_records_cancel_requested_and_terminal_cancel_events(tmp_path: Path) -> None:
    """request_cancel 应记录 CANCEL_REQUESTED，后台取消收口应记录 JOB_CANCELLED。"""

    workspace_root = _build_fins_workspace(tmp_path)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    cancelling = ingestion.request_cancel(start.job_id)
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert cancelling.status is FinsIngestionJobStatus.CANCELLING
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert [event.sequence for event in events] == [1, 2, 3]
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.CANCEL_REQUESTED,
        FinsIngestionJobEventType.JOB_CANCELLED,
    ]


def test_job_event_sidecar_omits_paths_payload_bodies_and_raw_provider_payloads(tmp_path: Path) -> None:
    """event sidecar 不应包含绝对路径、完整文件路径、财报正文或 provider raw payload。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="ok",
        )
    )
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor, upload_runner=runner)
    upload_file = tmp_path / "raw" / "aapl-10k.pdf"
    upload_file.parent.mkdir(parents=True)
    upload_file.write_text("Annual recurring revenue increased raw provider payload", encoding="utf-8")

    start = ingestion.start_upload(
        FinsUploadFilingRequest(
            ticker="AAPL",
            files=(upload_file,),
            fiscal_year=2024,
            fiscal_period="FY",
            company_name="Apple Inc.",
        )
    )
    executor.run_all()
    event_text = _job_event_file(workspace_root, start.job_id).read_text(encoding="utf-8")

    assert str(workspace_root) not in event_text
    assert str(upload_file) not in event_text
    assert "aapl-10k.pdf" not in event_text
    assert "Annual recurring revenue increased" not in event_text
    assert "raw provider payload" not in event_text
    assert "raw_provider_payload" not in event_text
    assert "provider_raw_payload" not in event_text


def test_job_event_store_concurrent_append_allocates_unique_monotonic_sequences(tmp_path: Path) -> None:
    """并发 append 使用同一 store lock 后 sequence 不应重复或倒退。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    append_count = 40

    def append_progress(index: int) -> int:
        """追加一个测试 progress event 并返回 sequence。

        Args:
            index: 测试事件序号。

        Returns:
            已分配 sequence。

        Raises:
            FileNotFoundError: job id 不存在时由 store 抛出。
            OSError: event sidecar 写入失败时由 store 抛出。
            ValueError: event payload 非法时由 store 抛出。
        """

        event = ingestion.job_store.append_job_event(
            start.job_id,
            FinsIngestionJobEventAppend(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                status=None,
                event_type=FinsIngestionJobEventType.PROGRESS,
                source_event_type="test",
                source_kind=None,
                document_id=None,
                message="测试进度事件",
                payload={"index": index},
                emitted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )
        return event.sequence

    with ThreadPoolExecutor(max_workers=8) as pool:
        sequences = tuple(pool.map(append_progress, range(append_count)))

    events = ingestion.read_job_events(start.job_id, after_sequence=0, limit=100)

    assert len(sequences) == append_count
    assert len(set(sequences)) == append_count
    assert sorted(sequences) == list(range(2, append_count + 2))
    assert [event.sequence for event in events] == list(range(1, append_count + 2))


def test_job_event_sidecar_skips_corrupted_rows_and_append_continues(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """sidecar 坏行应被跳过，后续 append 仍按有效事件分配 sequence。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    event_path = _job_event_file(workspace_root, start.job_id)
    leaked_payload_value = "SHOULD_NOT_APPEAR_IN_WARNING"
    original_text = event_path.read_text(encoding="utf-8")
    event_path.write_text(
        f'{original_text}{{"payload":"{leaked_payload_value}"\n["{leaked_payload_value}"]\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        appended = ingestion.job_store.append_job_event(
            start.job_id,
            FinsIngestionJobEventAppend(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                status=None,
                event_type=FinsIngestionJobEventType.PROGRESS,
                source_event_type="test.progress",
                source_kind=None,
                document_id=None,
                message="测试进度事件",
                payload={"step": "after_corruption"},
                emitted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )
        events = ingestion.read_job_events(start.job_id)

    assert appended.sequence == 2
    assert [event.sequence for event in events] == [1, 2]
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.PROGRESS,
    ]
    assert "fins.ingestion.job_event_sidecar_row_skipped" in caplog.text
    assert "sidecar_kind=fins_ingestion_job_event" in caplog.text
    assert "sidecar_suffix=.events.jsonl" in caplog.text
    assert "line_number=2" in caplog.text
    assert "line_number=3" in caplog.text
    assert "error_summary=malformed_or_invalid_event_row" in caplog.text
    assert leaked_payload_value not in caplog.text
    assert start.job_id not in caplog.text


def test_job_event_sidecar_still_rejects_non_monotonic_valid_records(tmp_path: Path) -> None:
    """坏行跳过不得放宽有效 event record 的 sequence 单调性校验。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    event_path = _job_event_file(workspace_root, start.job_id)
    queued_event_text = event_path.read_text(encoding="utf-8")
    event_path.write_text(f"{queued_event_text}{queued_event_text}", encoding="utf-8")

    with pytest.raises(ValueError, match="sequence 未递增"):
        ingestion.read_job_events(start.job_id)


def test_job_event_append_rejects_non_json_compatible_payload(tmp_path: Path) -> None:
    """event append payload 非 JSON-compatible 时应 fail fast。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))

    with pytest.raises(ValueError, match="不是 JSON-compatible"):
        ingestion.job_store.append_job_event(
            start.job_id,
            FinsIngestionJobEventAppend(
                operation_kind=FinsIngestionOperationKind.DOWNLOAD,
                status=None,
                event_type=FinsIngestionJobEventType.PROGRESS,
                source_event_type="test",
                source_kind=None,
                document_id=None,
                message="非法 payload",
                payload=cast(dict[str, JsonValue], {"bad": {"not-json"}}),
                emitted_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            ),
        )


def test_non_terminal_event_append_failure_warns_and_job_still_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """non-terminal event append 失败时应 WARN，且 job 仍可正常进入成功终态。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    original_append = ingestion_runtime.FsFinsIngestionJobStore.append_job_event

    def raise_for_running_event(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """仅在 JOB_RUNNING event append 时模拟 sidecar 写入失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            event: 待追加事件。

        Returns:
            非 JOB_RUNNING event 的真实追加结果。

        Raises:
            OSError: JOB_RUNNING event append 时抛出。
        """

        if event.event_type is FinsIngestionJobEventType.JOB_RUNNING:
            raise OSError("event sidecar unavailable")
        return original_append(store, job_id, event)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "append_job_event",
        raise_for_running_event,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        executor.run_all()

    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["downloaded_count"] == 1
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
    ]
    assert "fins.ingestion.job_event_append_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "event_type=job_running" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "error_summary=event_append_failed" in caplog.text
    assert "event sidecar unavailable" not in caplog.text


def test_terminal_event_append_failure_warns_without_rolling_back_terminal_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminal event append 失败时应 WARN，且不回滚已保存 terminal job record。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )
    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    original_append = ingestion_runtime.FsFinsIngestionJobStore.append_job_event

    def raise_for_terminal_event(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """仅在 terminal event append 时模拟 sidecar 写入失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            event: 待追加事件。

        Returns:
            非 terminal event 的真实追加结果。

        Raises:
            OSError: terminal event append 时抛出。
        """

        if event.event_type is FinsIngestionJobEventType.JOB_SUCCEEDED:
            raise OSError("event sidecar unavailable")
        return original_append(store, job_id, event)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "append_job_event",
        raise_for_terminal_event,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        executor.run_all()

    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["downloaded_count"] == 1
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.PROGRESS,
        FinsIngestionJobEventType.PROGRESS,
    ]
    assert "fins.ingestion.job_event_append_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "event_type=job_succeeded" in caplog.text
    assert "error_type=OSError" in caplog.text


def test_progress_event_append_failure_warns_and_job_still_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """PROGRESS event append 失败时应 WARN，且不得改变 upload 业务终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="ok",
        )
    )
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        upload_runner=runner,
    )
    start = ingestion.start_upload(_valid_runtime_filing_request())
    original_append = ingestion_runtime.FsFinsIngestionJobStore.append_job_event

    def raise_for_progress_event(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        event: FinsIngestionJobEventAppend,
    ) -> FinsIngestionJobEventRecord:
        """仅在 PROGRESS event append 时模拟 sidecar 写入失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            event: 待追加事件。

        Returns:
            非 PROGRESS event 的真实追加结果。

        Raises:
            OSError: PROGRESS event append 时抛出。
        """

        if event.event_type is FinsIngestionJobEventType.PROGRESS:
            raise OSError("event sidecar unavailable")
        return original_append(store, job_id, event)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "append_job_event",
        raise_for_progress_event,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        executor.run_all()

    record = ingestion.read_job(start.job_id)
    events = ingestion.read_job_events(start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["document_id"] == "aapl-2024-10k"
    assert [event.event_type for event in events] == [
        FinsIngestionJobEventType.JOB_QUEUED,
        FinsIngestionJobEventType.JOB_RUNNING,
        FinsIngestionJobEventType.JOB_SUCCEEDED,
    ]
    assert "fins.ingestion.job_event_append_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "event_type=progress" in caplog.text
    assert "source_event_type=upload.started" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "event sidecar unavailable" not in caplog.text


def test_save_cancelled_does_not_overwrite_current_terminal_record(tmp_path: Path) -> None:
    """_save_cancelled 应读取 store 当前状态，不能用旧 active record 覆盖终态。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    terminal_record = replace(
        start.record,
        status=FinsIngestionJobStatus.SUCCEEDED,
        updated_at=start.record.updated_at,
        finished_at=start.record.updated_at,
        result_summary={"processed_count": 0, "sentinel": True},
        cancellation_requested=False,
    )
    ingestion.job_store.save_job(terminal_record)

    saved = ingestion._save_cancelled(start.record)
    reloaded = ingestion.read_job(start.job_id)

    assert saved.status is FinsIngestionJobStatus.SUCCEEDED
    assert reloaded.status is FinsIngestionJobStatus.SUCCEEDED
    assert not reloaded.cancellation_requested
    assert reloaded.result_summary == {"processed_count": 0, "sentinel": True}
    assert reloaded.finished_at == terminal_record.finished_at


def test_save_failed_uses_current_cancelling_record_instead_of_stale_active_record(
    tmp_path: Path,
) -> None:
    """_save_failed 应读取 store 当前状态，不能用旧 active record 覆盖取消请求。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL"))
    cancelling = ingestion.request_cancel(start.job_id)

    saved = ingestion._save_failed(
        start.record,
        message="late failure",
        result_summary={"processed_count": 1},
    )
    reloaded = ingestion.read_job(start.job_id)

    assert cancelling.status is FinsIngestionJobStatus.CANCELLING
    assert saved.status is FinsIngestionJobStatus.CANCELLED
    assert reloaded.status is FinsIngestionJobStatus.CANCELLED
    assert reloaded.cancellation_requested
    assert reloaded.result_summary == {}
    assert reloaded.failure_summary == {}
    assert reloaded.finished_at is not None


def test_job_records_do_not_expose_payload_bodies_raw_provider_payloads_or_paths(tmp_path: Path) -> None:
    """job record 只应包含治理摘要，不应暴露正文、raw payload 或文件系统路径。"""

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
            form_types=("10-K",),
        )
    )
    payload_text = _job_file(workspace_root, start.job_id).read_text(encoding="utf-8")
    payload_value = cast(JsonValue, json.loads(payload_text))

    assert isinstance(payload_value, Mapping)
    assert str(workspace_root) not in payload_text
    assert "Annual recurring revenue increased" not in payload_text
    assert "processed_payload" not in payload_text
    assert "provider_raw_payload" not in payload_text
    assert "raw_provider_payload" not in payload_text
    assert "aapl-2024-10k.md" not in payload_text
    assert payload_value["request_summary"] == {
        "source_kind": "filing",
        "document_ids": ["aapl-2024-10k"],
        "form_types": ["10-K"],
        "rebuild_processed": False,
    }


def test_start_preprocess_processes_source_document_to_processed_repository(tmp_path: Path) -> None:
    """预处理应通过仓储读取 source 并写入 processed 产物。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
            form_types=("10-K",),
        )
    )
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)
    processed_meta = runtime.processed_repository.get_processed_meta("AAPL", "aapl-2024-10k")

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]
    assert processed_meta["document_id"] == "aapl-2024-10k"
    assert int(processed_meta["section_count"]) > 0
    assert processed_meta["parser_version"] != ""
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_processed",
        "preprocess.completed",
    ]
    assert progress_events[0].payload["selected_count"] == 1
    assert progress_events[1].document_id == "aapl-2024-10k"
    assert progress_events[2].document_id == "aapl-2024-10k"
    assert progress_events[3].payload["processed_count"] == 1


def test_preprocess_snapshot_and_processed_publication_share_source_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preprocess 应先持 writer batch，再消费一份 snapshot 并在 commit 前关闭。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: begin/snapshot/close/commit 顺序或 revision preservation 漂移时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()
    published_revision = _read_snapshot_revision(
        runtime.source_repository,
        "AAPL",
        "aapl-2024-10k",
        SourceKind.FILING,
    )
    batch_started = False
    snapshot_revisions: list[SourceDocumentRevision] = []
    snapshot_sources: list[Source] = []
    snapshot_roots: list[Path] = []
    original_begin = ingestion.batching_repository.begin_batch
    original_commit = ingestion.batching_repository.commit_batch
    original_snapshot = ingestion.source_repository.read_source_snapshot

    def _observe_begin(ticker: str) -> BatchToken:
        """记录 writer batch 已在 snapshot 前开始。

        Args:
            ticker: preprocess ticker。

        Returns:
            真实 batching owner 返回的 capability。

        Raises:
            RuntimeError: 真实 writer mutex 获取失败时抛出。
            OSError: 真实 staging 初始化失败时抛出。
        """

        nonlocal batch_started
        token = original_begin(ticker)
        batch_started = True
        return token

    def _observe_snapshot(
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """消费真实 full snapshot 并记录同版 revision 与临时资源。

        Args:
            ticker: preprocess ticker。
            document_id: preprocess document ID。
            source_kind: 显式 source kind。
            materialize_files: 是否物化文件。

        Returns:
            真实 storage snapshot resource。

        Raises:
            AssertionError: snapshot 发生在 begin 前或不是 full snapshot 时抛出。
            OSError: 真实 snapshot 读取失败时抛出。
            ValueError: 真实 source 完整性非法时抛出。
        """

        assert batch_started
        assert materialize_files
        snapshot = original_snapshot(
            ticker,
            document_id,
            source_kind,
            materialize_files=materialize_files,
        )
        primary_source = snapshot.get_primary_source()
        snapshot_revisions.append(snapshot.revision)
        snapshot_sources.append(primary_source)
        snapshot_roots.append(primary_source.materialize().parent)
        return snapshot

    def _observe_commit(batch: BatchToken) -> None:
        """确认 snapshot 已在 storage commit authority 接管前关闭。

        Args:
            batch: preprocess caller 即将交给 storage 的 capability。

        Returns:
            无。

        Raises:
            AssertionError: snapshot 临时树仍存在或 Source 仍可读时抛出。
            OSError: 真实 commit 失败时抛出。
            ValueError: capability 非法时抛出。
        """

        assert snapshot_roots
        assert all(not root.exists() for root in snapshot_roots)
        for source in snapshot_sources:
            with pytest.raises(RuntimeError, match="已关闭"):
                source.open()
        original_commit(batch)

    monkeypatch.setattr(ingestion.batching_repository, "begin_batch", _observe_begin)
    monkeypatch.setattr(
        ingestion.source_repository,
        "read_source_snapshot",
        _observe_snapshot,
    )
    monkeypatch.setattr(ingestion.batching_repository, "commit_batch", _observe_commit)

    result = ingestion._preprocess_one_document(
        ticker="AAPL",
        document_id="aapl-2024-10k",
        source_kind=SourceKind.FILING,
        rebuild_processed=False,
    )
    with original_snapshot(
        "AAPL",
        "aapl-2024-10k",
        SourceKind.FILING,
        materialize_files=False,
    ) as preserved_snapshot:
        preserved_revision = preserved_snapshot.revision
    processed_meta = runtime.processed_repository.get_processed_meta(
        "AAPL",
        "aapl-2024-10k",
    )

    assert result == "processed"
    assert snapshot_revisions == [published_revision]
    assert preserved_revision == published_revision
    assert published_revision.token not in json.dumps(processed_meta, ensure_ascii=False)
    assert all(not root.exists() for root in snapshot_roots)


def test_default_runtime_close_is_idempotent_and_preserves_lazy_read_creation(
    tmp_path: Path,
) -> None:
    """DefaultFinsRuntime.close 不得为清理创建 read runtime，且关闭保持幂等。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: close 破坏 lazy assembly、幂等或关闭后 fail-fast 时抛出。
    """

    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path / "lazy-close")
    assert runtime._read_runtime is None

    runtime.close()
    runtime.close()

    assert runtime._read_runtime is None
    with pytest.raises(RuntimeError, match="已关闭"):
        runtime.get_read_runtime()


def test_start_preprocess_whole_ticker_applies_limit_after_form_filter(tmp_path: Path) -> None:
    """整 ticker 预处理上限应作用于表单过滤后的实际工作集。"""

    workspace_root = _build_fins_workspace(tmp_path)
    _add_unmatched_source_documents(
        workspace_root=workspace_root,
        count=ingestion_runtime._MAX_PREPROCESS_DOCUMENTS + 1,
    )
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            form_types=("10-K",),
        )
    )
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]


def test_preprocess_selection_rejects_missing_completion_and_keeps_complete_source(
    tmp_path: Path,
) -> None:
    """预处理选择应拒绝缺失完成事实的 source，并保留显式完成态 source。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 缺失完成事实的 source 被选择，或完成态 source 未被保留时抛出。
        OSError: fixture 文件读写失败时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    _add_unmatched_source_documents(workspace_root=workspace_root, count=1)
    incomplete_document_id = "aapl-2024-10q-00"
    incomplete_meta_path = build_fs_repository_set(
        workspace_root=workspace_root,
    ).core._source_meta_path_for_read(
        "AAPL",
        incomplete_document_id,
        SourceKind.FILING,
    )
    incomplete_meta = cast(
        dict[str, JsonValue],
        json.loads(incomplete_meta_path.read_text(encoding="utf-8")),
    )
    assert incomplete_meta.pop("ingest_complete") is True
    incomplete_meta_path.write_text(
        json.dumps(incomplete_meta, ensure_ascii=False),
        encoding="utf-8",
    )

    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()
    complete_meta = runtime.source_repository.get_source_meta(
        "AAPL",
        "aapl-2024-10k",
        SourceKind.FILING,
    )
    corrupted_meta = runtime.source_repository.get_source_meta(
        "AAPL",
        incomplete_document_id,
        SourceKind.FILING,
    )

    assert complete_meta["ingest_complete"] is True
    assert "ingest_complete" not in corrupted_meta

    selected_document_ids = ingestion._select_preprocess_documents(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        document_ids=("aapl-2024-10k", incomplete_document_id),
        form_types=(),
    )

    assert selected_document_ids == ("aapl-2024-10k",)


def test_start_preprocess_skips_existing_processed_document_without_rebuild(tmp_path: Path) -> None:
    """rebuild_processed=False 时已有 processed 文档应被跳过。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()
    first = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    _wait_terminal(ingestion, first.job_id)

    second = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    record = _wait_terminal(ingestion, second.job_id)
    progress_events = _progress_events(ingestion, second.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["processed_count"] == 0
    assert record.result_summary["skipped_count"] == 1
    assert record.result_summary["skipped_document_ids"] == ["aapl-2024-10k"]
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_skipped",
        "preprocess.completed",
    ]
    assert progress_events[2].document_id == "aapl-2024-10k"
    assert progress_events[3].payload["skipped_count"] == 1


def test_start_preprocess_rebuild_updates_existing_processed_document(tmp_path: Path) -> None:
    """rebuild_processed=True 时已有 processed 文档应走 update。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = runtime.get_ingestion_runtime()
    first = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    _wait_terminal(ingestion, first.job_id)

    second = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
            rebuild_processed=True,
        )
    )
    record = _wait_terminal(ingestion, second.job_id)

    assert record.status is FinsIngestionJobStatus.SUCCEEDED
    assert record.result_summary["processed_count"] == 1
    assert record.result_summary["processed_document_ids"] == ["aapl-2024-10k"]


def test_start_preprocess_cancel_before_execution_writes_cancelled_terminal(tmp_path: Path) -> None:
    """queued 后执行前收到取消请求时，后台执行应收口为 cancelled。"""

    workspace_root = _build_fins_workspace(tmp_path)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    cancelling = ingestion.request_cancel(start.job_id)
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert cancelling.status is FinsIngestionJobStatus.CANCELLING
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested


def test_claim_running_preserves_cancel_between_read_and_running_write(
    tmp_path: Path,
) -> None:
    """claim running 期间收到取消请求时，不得覆盖为 running。"""

    workspace_root = _build_fins_workspace(tmp_path)
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    job_store = _ClaimRaceJobStore()
    ingestion = ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=job_store,
        executor=executor,
    )

    start = ingestion.start_preprocess(
        FinsPreprocessRequest(
            ticker="AAPL",
            document_ids=("aapl-2024-10k",),
        )
    )
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert job_store.claim_running_calls == 1
    assert job_store.save_job_calls == 0
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.status is not FinsIngestionJobStatus.RUNNING
    assert record.cancellation_requested


def test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功终态写入前收到取消请求时，应以当前取消状态收口为 cancelled。"""

    workspace_root = tmp_path / "fins-workspace"
    adapter = _FakeDownloadAdapter()
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(
        workspace_root,
        executor=executor,
        download_adapters={("sec", "US"): adapter},
    )
    original_save = ingestion.job_store.save_succeeded_or_cancelled

    def cancel_before_success_terminalization(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """在 success 终态裁决前插入取消请求。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            result_summary: success 结果摘要。
            finished_at: 终态写入时间。

        Returns:
            真实 success-or-cancelled 终态写入结果。

        Raises:
            FileNotFoundError: job id 不存在时由真实实现抛出。
            OSError: job store 读写失败时由真实实现抛出。
            ValueError: record 或摘要非法时由真实实现抛出。
        """

        del store
        ingestion.request_cancel(job_id)
        return original_save(job_id, result_summary=result_summary, finished_at=finished_at)

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_succeeded_or_cancelled",
        cancel_before_success_terminalization,
    )

    start = ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)

    assert len(adapter.requests) == 1
    assert record.status is FinsIngestionJobStatus.CANCELLED
    assert record.cancellation_requested
    assert record.result_summary == {}


def test_runners_return_for_preterminalized_jobs_without_executing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已进入终态的 download 与 preprocess job 不应被后台 runner 再次执行。"""

    download_workspace = tmp_path / "download-workspace"
    download_adapter = _FakeDownloadAdapter()
    download_executor = _HoldingExecutor()
    download_ingestion = _build_ingestion_runtime(
        download_workspace,
        executor=download_executor,
        download_adapters={("sec", "US"): download_adapter},
    )
    download_start = download_ingestion.start_download(build_fins_download_request(ticker="AAPL"))
    download_ingestion.job_store.save_job(
        replace(
            download_start.record,
            status=FinsIngestionJobStatus.SUCCEEDED,
            finished_at=download_start.record.updated_at,
            result_summary={"sentinel": True},
        )
    )

    preprocess_workspace = _build_fins_workspace(tmp_path)
    preprocess_executor = _HoldingExecutor()
    preprocess_ingestion = _build_ingestion_runtime(preprocess_workspace, executor=preprocess_executor)
    preprocess_start = preprocess_ingestion.start_preprocess(
        FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",))
    )
    preprocess_ingestion.job_store.save_job(
        replace(
            preprocess_start.record,
            status=FinsIngestionJobStatus.SUCCEEDED,
            finished_at=preprocess_start.record.updated_at,
            result_summary={"sentinel": True},
        )
    )
    preprocess_execute_calls = 0

    def count_preprocess_execution(
        record: ingestion_runtime.FinsIngestionJobRecord,
        request: FinsPreprocessRequest,
    ) -> FinsPreprocessResultSummary:
        """记录 preprocess 执行调用。

        Args:
            record: runner 传入的 job record。
            request: runner 传入的预处理请求。

        Returns:
            空预处理摘要。

        Raises:
            无。
        """

        nonlocal preprocess_execute_calls
        del record, request
        preprocess_execute_calls += 1
        return FinsPreprocessResultSummary()

    monkeypatch.setattr(preprocess_ingestion, "_execute_preprocess_request", count_preprocess_execution)

    download_executor.run_all()
    preprocess_executor.run_all()
    download_record = download_ingestion.read_job(download_start.job_id)
    preprocess_record = preprocess_ingestion.read_job(preprocess_start.job_id)

    assert download_adapter.requests == []
    assert download_record.result_summary == {"sentinel": True}
    assert preprocess_execute_calls == 0
    assert preprocess_record.result_summary == {"sentinel": True}


def test_start_preprocess_missing_document_fails_terminal_record(tmp_path: Path) -> None:
    """显式缺失文档应写入 failed 终态而不是后台异常逃逸。"""

    workspace_root = _build_fins_workspace(tmp_path)
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("missing-doc",)))
    record = _wait_terminal(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert "源文档不存在" in str(record.failure_summary["message"])


def test_start_preprocess_general_exception_emits_document_failed_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单文档预处理出现一般异常时应产生 document_failed progress。"""

    workspace_root = _build_fins_workspace(tmp_path)
    ingestion = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    def fail_preprocess_document(
        *,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
        rebuild_processed: bool,
    ) -> str:
        """模拟处理器执行期一般异常。

        Args:
            ticker: 标准化 ticker。
            document_id: 源文档 ID。
            source_kind: 源文档类型。
            rebuild_processed: 是否重建 processed 产物。

        Returns:
            不返回；总是抛出异常。

        Raises:
            RuntimeError: 始终抛出，用于触发一般异常分支。
        """

        del ticker, document_id, source_kind, rebuild_processed
        raise RuntimeError("processor crashed")

    monkeypatch.setattr(ingestion, "_preprocess_one_document", fail_preprocess_document)

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["failed_document_ids"] == ["aapl-2024-10k"]
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_failed",
        "preprocess.completed",
    ]
    assert progress_events[2].message == "预处理源文档失败"
    assert progress_events[2].document_id == "aapl-2024-10k"


def test_start_preprocess_unsupported_document_records_not_supported_summary(tmp_path: Path) -> None:
    """无可用处理器时应记录 not_supported 文档并按无可处理文档失败。"""

    workspace_root = _build_fins_workspace(tmp_path)
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=ProcessorRegistry(),
        job_store=default_runtime.ingestion_job_store,
    )

    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))
    record = _wait_terminal(ingestion, start.job_id)
    progress_events = _progress_events(ingestion, start.job_id)

    assert record.status is FinsIngestionJobStatus.FAILED
    assert record.result_summary["selected_count"] == 1
    assert record.result_summary["processed_count"] == 0
    assert record.result_summary["skipped_count"] == 0
    assert record.result_summary["not_supported_count"] == 1
    assert record.result_summary["not_supported_document_ids"] == ["aapl-2024-10k"]
    assert "没有任何请求文档完成预处理" in str(record.failure_summary["message"])
    assert [event.source_event_type for event in progress_events] == [
        "preprocess.selected",
        "preprocess.document_started",
        "preprocess.document_not_supported",
        "preprocess.completed",
    ]
    assert progress_events[2].message == "预处理源文档不支持"
    assert progress_events[2].document_id == "aapl-2024-10k"
    assert progress_events[3].payload["skipped_count"] == 0
    assert progress_events[3].payload["not_supported_count"] == 1


def test_save_failed_from_exception_logs_secondary_job_store_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """失败收口二次写 job store 失败时应记录诊断且不向外传播。"""

    workspace_root = _build_fins_workspace(tmp_path)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    start = ingestion.start_preprocess(FinsPreprocessRequest(ticker="AAPL", document_ids=("aapl-2024-10k",)))

    def raise_save_failed_or_cancelled(
        store: ingestion_runtime.FsFinsIngestionJobStore,
        job_id: str,
        *,
        failure_summary: dict[str, JsonValue],
        result_summary: dict[str, JsonValue],
        finished_at: str,
    ) -> ingestion_runtime.FinsIngestionJobRecord:
        """模拟 failed 终态落盘失败。

        Args:
            store: 被替换方法所属 job store。
            job_id: opaque job id。
            failure_summary: failed 终态失败摘要。
            result_summary: failed 终态结果摘要。
            finished_at: 终态写入时间。

        Returns:
            不返回；始终抛出异常。

        Raises:
            OSError: 始终抛出，模拟 job store 写入失败。
        """

        del store, job_id, failure_summary, result_summary, finished_at
        raise OSError("job store save failed")

    monkeypatch.setattr(
        ingestion_runtime.FsFinsIngestionJobStore,
        "save_failed_or_cancelled_if_active",
        raise_save_failed_or_cancelled,
    )

    with caplog.at_level(logging.WARNING, logger="dayu.fins.ingestion_runtime"):
        ingestion._save_failed_from_exception(start.job_id, RuntimeError("primary failure"))

    assert "fins.ingestion.failed_terminalization_failed" in caplog.text
    assert f"job_id={start.job_id}" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "original_error_type=RuntimeError" in caplog.text


def test_job_store_removes_temp_file_when_atomic_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """atomic replace 失败时 job store 应删除本次写入留下的临时文件。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()
    jobs_dir = workspace_root / ".dayu" / "fins_ingestion" / "jobs"

    def raise_replace(
        src: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        dst: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        """模拟 atomic replace 在临时文件已写入后失败。

        Args:
            src: 源路径。
            dst: 目标路径。

        Returns:
            无。

        Raises:
            OSError: 始终抛出，模拟文件系统 replace 失败。
        """

        raise OSError("replace failed")

    monkeypatch.setattr(ingestion_runtime.os, "replace", raise_replace)

    with pytest.raises(OSError, match="replace failed"):
        runtime.start_download(build_fins_download_request(ticker="AAPL"))

    assert jobs_dir.is_dir()
    assert tuple(jobs_dir.glob(".*.tmp")) == ()


def test_default_runtime_keeps_read_runtime_lazy_singleton(tmp_path: Path) -> None:
    """新增 ingestion runtime 不应破坏 read runtime 懒加载行为。"""

    workspace_root = tmp_path / "fins-workspace"
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    first_read_runtime = runtime.get_read_runtime()
    second_read_runtime = runtime.get_read_runtime()

    assert isinstance(first_read_runtime, FinsReadRuntime)
    assert first_read_runtime is second_read_runtime


def _job_file(workspace_root: Path, job_id: str) -> Path:
    """返回 S1 约定的 job record 文件路径。

    Args:
        workspace_root: Fins 工作区根目录。
        job_id: opaque job id。

    Returns:
        job record JSON 文件路径。

    Raises:
        无。
    """

    return workspace_root / ".dayu" / "fins_ingestion" / "jobs" / f"{job_id}.json"


def _job_event_file(workspace_root: Path, job_id: str) -> Path:
    """返回 S1 约定的 job event sidecar 路径。

    Args:
        workspace_root: Fins 工作区根目录。
        job_id: opaque job id。

    Returns:
        job event JSONL 文件路径。

    Raises:
        无。
    """

    return workspace_root / ".dayu" / "fins_ingestion" / "jobs" / f"{job_id}.events.jsonl"


def _build_ingestion_runtime(
    workspace_root: Path,
    *,
    executor: FinsIngestionExecutor,
    download_adapters: Mapping[tuple[str, ticker_normalization.Market], FinsSourceDownloadAdapter] | None = None,
    upload_runner: FinsUploadRunner | None = None,
) -> ingestion_runtime.FinsIngestionRuntime:
    """构建测试用 ingestion runtime。

    Args:
        workspace_root: Fins workspace root。
        executor: 测试执行器。
        download_adapters: 可选下载 adapter 映射。
        upload_runner: 可选上传 runner。

    Returns:
        ingestion runtime。

    Raises:
        OSError: 仓储初始化失败时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    return ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=executor,
        download_adapters=download_adapters,
        upload_runner=upload_runner,
    )


def _build_ingestion_runtime_with_repository_set(
    workspace_root: Path,
    *,
    repository_set: _FsRepositorySet,
    batching_repository: BatchingRepositoryProtocol,
) -> ingestion_runtime.FinsIngestionRuntime:
    """用显式 shared repository set 构造 owner-failure ingestion runtime。

    Args:
        workspace_root: Fins workspace root。
        repository_set: 所有 mutation wrapper 共用的 repository set。
        batching_repository: 注入 rollback 行为的 batch lifecycle 仓储。

    Returns:
        与 batching repository 共享同一 storage core 的 ingestion runtime。

    Raises:
        OSError: 仓储、processor registry 或 job store 初始化失败时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    return ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=batching_repository,
        source_repository=FsSourceDocumentRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        blob_repository=FsDocumentBlobRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        filing_maintenance_repository=FsFilingMaintenanceRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        filing_upload_state_repository=default_runtime.filing_upload_state_repository,
        processed_repository=FsProcessedDocumentRepository(
            workspace_root,
            repository_set=repository_set,
        ),
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=_HoldingExecutor(),
    )


def _add_unmatched_source_documents(
    *,
    workspace_root: Path,
    count: int,
) -> None:
    """追加不匹配 10-K 表单过滤条件的源文档。

    Args:
        workspace_root: Fins workspace root。
        count: 需要追加的 10-Q 源文档数量。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
        ValueError: 源文档字段非法时抛出。
    """

    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    token = batching_repository.begin_batch("AAPL")
    try:
        for index in range(count):
            document_id = f"aapl-2024-10q-{index:02d}"
            filename = f"{document_id}.md"
            handle = SourceHandle(
                ticker="AAPL",
                document_id=document_id,
                source_kind=SourceKind.FILING.value,
            )
            file_meta = blob_repository.store_file(
                handle,
                filename,
                io.BytesIO(b"# Unmatched fixture"),
                batch=token,
                content_type="text/markdown",
            )
            source_repository.create_source_document(
                SourceDocumentUpsertRequest(
                    ticker="AAPL",
                    document_id=document_id,
                    internal_document_id=document_id,
                    form_type="10-Q",
                    primary_document=filename,
                    meta={
                        "fiscal_year": 2024,
                        "fiscal_period": "Q",
                        "filing_date": "2024-08-01",
                        "report_date": "2024-06-29",
                        "amended": False,
                        "ingest_method": "upload",
                        "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                    },
                    files=[file_meta],
                ),
                SourceKind.FILING,
                batch=token,
            )
    except BaseException:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)


def _wait_terminal(
    ingestion: ingestion_runtime.FinsIngestionRuntime,
    job_id: str,
) -> ingestion_runtime.FinsIngestionJobRecord:
    """等待 job 进入终态。

    Args:
        ingestion: ingestion runtime。
        job_id: opaque job id。

    Returns:
        终态 job record。

    Raises:
        AssertionError: 超时未进入终态时抛出。
    """

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        record = ingestion.read_job(job_id)
        if record.status in {
            FinsIngestionJobStatus.SUCCEEDED,
            FinsIngestionJobStatus.FAILED,
            FinsIngestionJobStatus.CANCELLED,
        }:
            return record
        time.sleep(0.02)
    raise AssertionError(f"job 未进入终态: {job_id}")


def _progress_events(
    ingestion: ingestion_runtime.FinsIngestionRuntime,
    job_id: str,
) -> tuple[FinsIngestionJobEventRecord, ...]:
    """读取指定 job 的 PROGRESS events。

    Args:
        ingestion: ingestion runtime。
        job_id: opaque job id。

    Returns:
        按 sequence 升序排列的 PROGRESS event 元组。

    Raises:
        FileNotFoundError: job id 不存在时由 runtime 抛出。
        OSError: event sidecar 读取失败时由 runtime 抛出。
        ValueError: event sidecar 内容非法时由 runtime 抛出。
    """

    return tuple(
        event
        for event in ingestion.read_job_events(job_id, after_sequence=0, limit=1000)
        if event.event_type is FinsIngestionJobEventType.PROGRESS
    )


def _record_direct_cancellation_states(
    monkeypatch: pytest.MonkeyPatch,
) -> list[ingestion_runtime._DirectStreamCancellationState]:
    """记录 direct stream 真实使用的 cancellation owner state。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        按创建顺序记录的 state 列表。

    Raises:
        无。
    """

    states: list[ingestion_runtime._DirectStreamCancellationState] = []

    def create_state(
        _state_type: type[ingestion_runtime._DirectStreamCancellationState],
    ) -> ingestion_runtime._DirectStreamCancellationState:
        """创建并记录一个真实 owner state。

        Args:
            _state_type: 被替换 classmethod 传入的 state 类型。

        Returns:
            新的 cancellation state。

        Raises:
            无。
        """

        state = ingestion_runtime._DirectStreamCancellationState(_lock=ThreadingLock())
        states.append(state)
        return state

    monkeypatch.setattr(
        ingestion_runtime._DirectStreamCancellationState,
        "create",
        classmethod(create_state),
    )
    return states


async def _collect_direct_events(events: AsyncIterator[FinsEvent]) -> tuple[FinsEvent, ...]:
    """收集 direct stream 事件。

    Args:
        events: Fins direct async event stream。

    Returns:
        已收集事件元组。

    Raises:
        Exception: stream 迭代失败时原样抛出。
    """

    collected: list[FinsEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)


def _read_snapshot_revision(
    repository: SourceDocumentRepositoryProtocol,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> SourceDocumentRevision:
    """从 storage-owned light snapshot 读取 opaque published revision。

    Args:
        repository: source repository protocol。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 显式 source kind。

    Returns:
        snapshot 同版 revision。

    Raises:
        FileNotFoundError: source 不存在或已删除时抛出。
        ValueError: snapshot descriptor 非法时抛出。
        OSError: snapshot I/O 或 close 失败时抛出。
    """

    with repository.read_source_snapshot(
        ticker,
        document_id,
        source_kind,
        materialize_files=False,
    ) as snapshot:
        return snapshot.revision


def _build_fins_workspace(
    tmp_path: Path,
    *,
    content_type: str = "text/markdown",
) -> Path:
    """构造确定性 Fins fixture 工作区。

    Args:
        tmp_path: pytest 临时目录。
        content_type: 主文件 content type。

    Returns:
        Fins workspace root。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    company_batch = batching_repository.begin_batch("AAPL")
    company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            market="US",
            resolver_version="test",
            updated_at=now_iso8601(),
            ticker_aliases=["APPLE"],
        ),
        batch=company_batch,
    )
    batching_repository.commit_batch(company_batch)
    token = batching_repository.begin_batch("AAPL")
    try:
        handle = SourceHandle(
            ticker="AAPL",
            document_id="aapl-2024-10k",
            source_kind=SourceKind.FILING.value,
        )
        file_meta = blob_repository.store_file(
            handle,
            "aapl-2024-10k.md",
            io.BytesIO(_fixture_markdown().encode("utf-8")),
            batch=token,
            content_type=content_type,
        )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="aapl-2024-10k",
                internal_document_id="aapl-2024-10k",
                form_type="10-K",
                primary_document="aapl-2024-10k.md",
                meta={
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "amended": False,
                    "ingest_method": "upload",
                    "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                },
                files=[file_meta],
            ),
            SourceKind.FILING,
            batch=token,
        )
    except BaseException:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)
    return workspace_root


def _fixture_markdown() -> str:
    """返回测试财报 Markdown 内容。

    Args:
        无。

    Returns:
        Markdown 财报片段。

    Raises:
        无。
    """

    return "\n".join(
        (
            "# Apple 2024 Form 10-K",
            "",
            "## Item 1. Business",
            "Annual recurring revenue increased in services.",
            "",
            "## Item 7. Management Discussion",
            "| Segment | Revenue |",
            "| --- | ---: |",
            "| Services | 100 |",
        )
    )


def _is_terminal_job_status(status: FinsIngestionJobStatus) -> bool:
    """判断 Fins ingestion job 状态是否为终态。

    Args:
        status: 待判断的 job 状态。

    Returns:
        终态返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    return status in {
        FinsIngestionJobStatus.SUCCEEDED,
        FinsIngestionJobStatus.FAILED,
        FinsIngestionJobStatus.CANCELLED,
    }
