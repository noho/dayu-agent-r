"""Fins ingestion runtime foundation 测试。"""

from __future__ import annotations

import ast
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
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from threading import Event, Lock as ThreadingLock, Thread, current_thread, enumerate as enumerate_threads
from typing import cast

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.documents.processors.source import Source
from dayu.documents.processors.base import DocumentProcessor
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.fins import ticker_normalization
import dayu.fins.download_contract as download_contract
from dayu.fins.downloaders.sec_downloader import SEC_USER_AGENT_ENV
from dayu.fins.domain.enums import SourceKind
from dayu.fins import ingestion_runtime
from dayu.fins.direct_events import (
    canonicalize_fins_public_file_label,
    FinsErrorKind,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsPublicFailureKind,
    FinsResultStatus,
    validate_fins_public_file_label,
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
    FileObjectMeta,
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
    FinsUploadUsageFailure,
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
from dayu.fins.pipelines.docling_upload_service import _build_filing_original_asset_identity
from dayu.fins.upload_failure import (
    FinsUploadFailureCode,
    FinsUploadFailureKind,
    FinsUploadFailureReason,
    FinsUploadPrevalidationError,
    fins_upload_failure_from_exception,
    fins_upload_source_integrity_unsafe_failure,
    upload_failure_reason_from_json,
)
from dayu.fins.upload_format_contract import (
    FinsUploadFilingFiles,
    FinsUploadFormatError,
    FinsUploadFormatFailureKind,
)
from dayu.fins.upload_repair_contract import (
    ExistingSourceAutoRepair,
    NoExistingSourceRepair,
)
from dayu.fins.pipelines.cn_pipeline import CnDownloadAdapter, CnPipeline
from dayu.fins.pipelines.docling_process_converter import (
    DoclingConversionConfig,
    DoclingConverter,
    DoclingConversionError,
    DoclingConversionFailureKind,
    DoclingConversionResult,
    ProcessDoclingConverter,
)
from dayu.fins.pipelines.docling_upload_service import build_sec_filing_ids
from dayu.fins.pipelines.upload_company_meta import (
    RESOLVER_VERSION,
    UploadCompanyNameRequiredError,
    resolve_upload_company_meta_decision,
)
from dayu.fins.pipelines.sec_pipeline import SecDownloadAdapter, SecPipeline
from dayu.fins.service_runtime import (
    DefaultFinsRuntime,
    ProductionFinsUploadRunner,
    prevalidate_fins_upload_filing_request_for_workspace,
)
from dayu.fins.storage import (
    BatchingRepositoryProtocol,
    CompanyTickerAliasConflictError,
    CompanyTickerIdentityCorruptionError,
    DocumentBlobRepositoryProtocol,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    FilingUploadPublishedState,
    SourceIntegrityClassification,
    SourceIntegrityReason,
    SourceIntegrityStatus,
    SourceDocumentRepositoryProtocol,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.ticker_normalization import NormalizedTicker, build_company_ticker_identity
from dayu.fins.tools.read_runtime import FinsReadRuntime
import dayu.runtime.log as runtime_log
from dayu.runtime.workspace_paths import WorkspacePaths

_PUBLISHED_SOURCE_REVISION_TOKEN = "test-published-source-revision"


def _fresh_filing_file_entries(
    original_meta: FileObjectMeta,
    docling_meta: FileObjectMeta,
    *,
    original_name: str,
    docling_name: str,
) -> list[dict[str, JsonValue]]:
    """构造 fresh user-upload filing 的 explicit original/Docling entries。

    Args:
        original_meta: 已 staged 的 authoritative original blob meta。
        docling_meta: 已 staged 的唯一 primary Docling blob meta。
        original_name: storage-owned original asset name。
        docling_name: storage-owned Docling asset name。

    Returns:
        可直接交给 source mutation owner 的严格 file entry 列表。

    Raises:
        无。
    """

    return [
        {
            "name": original_name,
            "uri": original_meta.uri,
            "etag": original_meta.etag,
            "last_modified": original_meta.last_modified,
            "size": original_meta.size,
            "content_type": original_meta.content_type,
            "sha256": original_meta.sha256,
            "source": "original",
            "original_filename": original_name,
        },
        {
            "name": docling_name,
            "uri": docling_meta.uri,
            "etag": docling_meta.etag,
            "last_modified": docling_meta.last_modified,
            "size": docling_meta.size,
            "content_type": docling_meta.content_type,
            "sha256": docling_meta.sha256,
            "source": "docling",
            "original_filename": original_name,
            "derived_from": original_name,
        },
    ]


def _filing_upload_published_state(
    request: FinsUploadFilingRequest,
    *,
    company_meta: CompanyMeta | None = None,
    source_meta: Mapping[str, JsonValue] | None = None,
    status: SourceIntegrityStatus,
    reasons: tuple[SourceIntegrityReason, ...],
) -> FilingUploadPublishedState:
    """为 request 构造 target 与 meta presence 精确匹配的 published state。

    Args:
        request: 需要静态解析 exact ticker 与 filing document ID 的原始请求。
        company_meta: 可选同版 company meta。
        source_meta: 可选可信 source business meta。
        status: 显式完整性状态。
        reasons: repair-required 或 unsafe 状态的 closed reasons。

    Returns:
        required integrity 与 source meta presence 一致的测试 state。

    Raises:
        FinsUploadUsageError: request 无法通过 workspace read 前静态校验时抛出。
        ValueError: 构造的 integrity 或 state 不满足 public contract 时抛出。
    """

    ticker, document_id = ingestion_runtime._filing_upload_request_identity(request)
    source_integrity = SourceIntegrityClassification(
        ticker=ticker,
        source_kind=SourceKind.FILING,
        document_id=document_id,
        revision=(
            None
            if status in {
                SourceIntegrityStatus.MISSING,
                SourceIntegrityStatus.UNSAFE,
            }
            else SourceDocumentRevision(_PUBLISHED_SOURCE_REVISION_TOKEN)
        ),
        status=status,
        reasons=reasons,
    )
    return FilingUploadPublishedState(
        company_meta=company_meta,
        source_integrity=source_integrity,
        source_meta=source_meta,
        publication_identity=None,
    )


def test_filing_upload_published_state_requires_matching_integrity_and_meta() -> None:
    """upload state 必须显式携带 filing integrity 并保持 meta presence 同源。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: state 接受 material target 或 status/meta 不一致组合时抛出。
    """

    missing = SourceIntegrityClassification(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        document_id="filing-a",
        revision=None,
        status=SourceIntegrityStatus.MISSING,
        reasons=(),
    )
    complete = SourceIntegrityClassification(
        ticker="AAPL",
        source_kind=SourceKind.FILING,
        document_id="filing-a",
        revision=SourceDocumentRevision(_PUBLISHED_SOURCE_REVISION_TOKEN),
        status=SourceIntegrityStatus.COMPLETE,
        reasons=(),
    )
    material = SourceIntegrityClassification(
        ticker="AAPL",
        source_kind=SourceKind.MATERIAL,
        document_id="material-a",
        revision=SourceDocumentRevision(_PUBLISHED_SOURCE_REVISION_TOKEN),
        status=SourceIntegrityStatus.COMPLETE,
        reasons=(),
    )

    assert FilingUploadPublishedState(
        company_meta=None,
        source_integrity=missing,
        source_meta=None,
        publication_identity=None,
    ).source_integrity is missing
    assert FilingUploadPublishedState(
        company_meta=None,
        source_integrity=complete,
        source_meta={"source_fingerprint": "published"},
        publication_identity=None,
    ).source_integrity is complete
    with pytest.raises(ValueError, match="MISSING/UNSAFE"):
        FilingUploadPublishedState(
            company_meta=None,
            source_integrity=missing,
            source_meta={"source_fingerprint": "published"},
            publication_identity=None,
        )
    with pytest.raises(ValueError, match="COMPLETE/REPAIR_REQUIRED"):
        FilingUploadPublishedState(
            company_meta=None,
            source_integrity=complete,
            source_meta=None,
            publication_identity=None,
        )
    with pytest.raises(ValueError, match="filing integrity"):
        FilingUploadPublishedState(
            company_meta=None,
            source_integrity=material,
            source_meta={"source_fingerprint": "published"},
            publication_identity=None,
        )


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
        FinsUploadPipelineResult.from_pipeline_json({"status": "failed", "stored_file_count": 0})
    with pytest.raises(ValueError):
        FinsUploadPipelineResult.from_pipeline_json(
            {
                "status": "ok",
                "stored_file_count": 1,
                "failure": {
                    "kind": "runtime",
                    "code": "unexpected_runtime",
                    "message": "上传执行失败，请检查运行日志后重试",
                    "retry_hint": None,
                    "file_label": None,
                },
            }
        )
    result = FinsUploadPipelineResult.from_pipeline_json(
        {
            "status": "failed",
            "stored_file_count": 0,
            "failure": {
                "kind": "content",
                "code": "docling_converter_execution",
                "message": "文件无法解析或已损坏，请检查文件后重试",
                "retry_hint": "请确认文件可正常打开并重新上传",
                "file_label": "report.pdf",
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

    reason = fins_upload_failure_from_exception(
        DoclingConversionError(kind, safe_message, None),
        file_label="report.pdf",
    )

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
            "file_label": None,
            "unknown": "forbidden",
        },
        {
            "kind": "unknown",
            "code": "unexpected_runtime",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
            "file_label": None,
        },
        {
            "kind": "runtime",
            "code": "unknown",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
            "file_label": None,
        },
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "workspace/private/report.pdf",
            "retry_hint": None,
            "file_label": None,
        },
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "x\nsecret",
            "retry_hint": None,
            "file_label": None,
        },
        {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "x" * 241,
            "retry_hint": None,
            "file_label": None,
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
        FinsUploadPipelineResult.from_pipeline_json({"status": "failed", "stored_file_count": 0, "failure": failure})


@pytest.mark.parametrize(
    ("raw_basename", "expected_label"),
    (
        ("report.pdf", "report.pdf"),
        ("job_id_notes.pdf", "输入文件（文件名已隐藏）"),
        ("财报正文.pdf", "输入文件（文件名已隐藏）"),
        ("line\nbreak.pdf", "输入文件（文件名已隐藏）"),
        ("report\u202ename.pdf", "输入文件（文件名已隐藏）"),
        (f"{'a' * 241}.pdf", "输入文件（文件名已隐藏）"),
    ),
)
def test_public_file_label_owner_canonicalizes_unsafe_legal_basenames(
    raw_basename: str,
    expected_label: str,
) -> None:
    """唯一 label owner 应原样保留安全名称并隐藏无法安全公开的合法 basename。

    Args:
        raw_basename: producer 从 ``Path.name`` 取得的原始 basename。
        expected_label: 唯一 owner 应返回的 canonical public label。

    Returns:
        无。

    Raises:
        AssertionError: canonical label 或 validator 接受集漂移时抛出。
    """

    canonical = canonicalize_fins_public_file_label(raw_basename)

    assert canonical == expected_label
    validate_fins_public_file_label(canonical)


@pytest.mark.parametrize("pathful", ("folder/report.pdf", "folder\\report.pdf", ".", "..", ""))
def test_public_file_label_owner_rejects_non_basename_input(pathful: str) -> None:
    """canonicalizer 必须拒绝 pathful、空或 dot-segment 输入。

    Args:
        pathful: 非法 basename fixture。

    Returns:
        无。

    Raises:
        AssertionError: 非 basename 输入未 fail closed 时抛出。
    """

    with pytest.raises(ValueError):
        canonicalize_fins_public_file_label(pathful)


@pytest.mark.parametrize(
    "file_label",
    (
        "job_id_notes.pdf",
        "财报正文.pdf",
        "line\nbreak.pdf",
        "report\u202ename.pdf",
        f"{'a' * 241}.pdf",
        "folder/report.pdf",
    ),
)
def test_upload_failure_reason_constructor_owns_canonical_label_invariant(
    file_label: str,
) -> None:
    """reason constructor 必须调用唯一 validator 并拒绝未 canonicalize label。

    Args:
        file_label: 绕过 producer 直接注入的非法 public label。

    Returns:
        无。

    Raises:
        AssertionError: reason constructor 接受非法 label 时抛出。
    """

    with pytest.raises(ValueError):
        FinsUploadFailureReason(
            kind=FinsUploadFailureKind.RUNTIME,
            code=FinsUploadFailureCode.UNEXPECTED_RUNTIME,
            message="上传执行失败，请检查运行日志后重试",
            retry_hint=None,
            file_label=file_label,
        )


@pytest.mark.parametrize("file_label", (None, "report.pdf", "输入文件（文件名已隐藏）"))
def test_upload_failure_reason_constructor_accepts_only_canonical_labels(
    file_label: str | None,
) -> None:
    """reason constructor 应接受 null、普通 canonical label 与固定隐藏标签。

    Args:
        file_label: 合法 canonical label 或 ``None``。

    Returns:
        无。

    Raises:
        AssertionError: 合法 owner 值被拒绝时抛出。
    """

    reason = FinsUploadFailureReason(
        kind=FinsUploadFailureKind.RUNTIME,
        code=FinsUploadFailureCode.UNEXPECTED_RUNTIME,
        message="上传执行失败，请检查运行日志后重试",
        retry_hint=None,
        file_label=file_label,
    )

    assert reason.file_label == file_label


def test_upload_direct_details_consume_typed_failure_label_and_retry_hint() -> None:
    """direct projection 只应消费 reason 中同一个 canonical label 与 retry hint。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: direct details 丢失或重分类 typed failure 字段时抛出。
    """

    reason = FinsUploadFailureReason(
        kind=FinsUploadFailureKind.CONTENT,
        code=FinsUploadFailureCode.EMPTY_INPUT_FILE,
        message="文件为空，无法上传",
        retry_hint="请提供非空文件后重试",
        file_label="输入文件（文件名已隐藏）",
    )
    summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status="failed",
        requested_file_count=1,
        stored_file_count=0,
        document_id="AAPL-2024-FY",
        failure_reason=reason,
    )

    projected_details = ingestion_runtime._upload_result_details(summary)
    details = {detail.label: detail.value for detail in projected_details}

    assert tuple(detail.label for detail in projected_details) == (
        "source kind",
        "status",
        "requested files",
        "stored files",
        "failure kind",
        "failure code",
        "file",
        "failure message",
        "retry hint",
        "document",
    )
    assert tuple(detail.label for detail in projected_details[:8]) == (
        "source kind",
        "status",
        "requested files",
        "stored files",
        "failure kind",
        "failure code",
        "file",
        "failure message",
    )
    assert details["failure kind"] == "content"
    assert details["failure code"] == "empty_input_file"
    assert details["failure message"] == "文件为空，无法上传"
    assert details["retry hint"] == "请提供非空文件后重试"
    assert details["file"] == "输入文件（文件名已隐藏）"


def test_upload_failure_parser_requires_five_fields_and_delegates_label_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parser 只应 exact-read 五字段并把 label 原样交给 reason constructor。

    Args:
        monkeypatch: constructor 入口替换夹具。

    Returns:
        无。

    Raises:
        AssertionError: parser 兼容旧 schema 或复制 label 规则时抛出。
    """

    old_shape: dict[str, JsonValue] = {
        "kind": "runtime",
        "code": "unexpected_runtime",
        "message": "上传执行失败，请检查运行日志后重试",
        "retry_hint": None,
    }
    with pytest.raises(ValueError, match="exact-key"):
        upload_failure_reason_from_json(old_shape)

    captured: list[tuple[FinsUploadFailureKind, FinsUploadFailureCode, str, str | None, str | None]] = []
    sentinel = FinsUploadFailureReason(
        kind=FinsUploadFailureKind.RUNTIME,
        code=FinsUploadFailureCode.UNEXPECTED_RUNTIME,
        message="上传执行失败，请检查运行日志后重试",
        retry_hint=None,
        file_label=None,
    )

    def capture_reason(
        *,
        kind: FinsUploadFailureKind,
        code: FinsUploadFailureCode,
        message: str,
        retry_hint: str | None,
        file_label: str | None,
    ) -> FinsUploadFailureReason:
        """记录 parser 传入 constructor 的 exact five-field 值。

        Args:
            kind: typed failure kind。
            code: typed failure code。
            message: public bounded message。
            retry_hint: 可选重试建议。
            file_label: parser 原样读取的可选 label。

        Returns:
            预先构造的合法 reason sentinel。

        Raises:
            无。
        """

        captured.append((kind, code, message, retry_hint, file_label))
        return sentinel

    monkeypatch.setattr("dayu.fins.upload_failure.FinsUploadFailureReason", capture_reason)
    parsed = upload_failure_reason_from_json(
        {
            **old_shape,
            "file_label": "job_id_notes.pdf",
        }
    )

    assert parsed is sentinel
    assert captured == [
        (
            FinsUploadFailureKind.RUNTIME,
            FinsUploadFailureCode.UNEXPECTED_RUNTIME,
            "上传执行失败，请检查运行日志后重试",
            None,
            "job_id_notes.pdf",
        )
    ]


@pytest.mark.parametrize(
    ("status", "stored_file_count"),
    (
        ("ok", 1),
        ("skipped", 0),
        ("deleted", 0),
        ("failed", 0),
        ("cancelled", 0),
    ),
)
def test_upload_pipeline_count_owner_accepts_complete_status_matrix(
    status: str,
    stored_file_count: int,
) -> None:
    """pipeline constructor 与 JSON parser 必须接受完整合法计数矩阵。

    Args:
        status: pipeline 终态。
        stored_file_count: 与终态匹配的已发布 original 数。

    Returns:
        无。

    Raises:
        AssertionError: direct constructor 或 parser 拒绝合法矩阵时抛出。
    """

    failure_reason = _runtime_failure_for_status(status)
    direct = FinsUploadPipelineResult(
        status=status,
        stored_file_count=stored_file_count,
        failure_reason=failure_reason,
    )
    payload: dict[str, JsonValue] = {
        "status": status,
        "stored_file_count": stored_file_count,
    }
    if failure_reason is not None:
        payload["failure"] = failure_reason.to_json()
    parsed = FinsUploadPipelineResult.from_pipeline_json(payload)

    assert direct.stored_file_count == stored_file_count
    assert parsed.stored_file_count == stored_file_count


@pytest.mark.parametrize(
    ("status", "stored_file_count"),
    (
        ("ok", 0),
        ("skipped", 1),
        ("deleted", 1),
        ("failed", 1),
        ("cancelled", 1),
    ),
)
def test_upload_pipeline_count_owner_rejects_invalid_status_matrix(
    status: str,
    stored_file_count: int,
) -> None:
    """pipeline constructor 与 JSON parser 必须共同拒绝非法计数矩阵。

    Args:
        status: pipeline 终态。
        stored_file_count: 与终态冲突的已发布 original 数。

    Returns:
        无。

    Raises:
        AssertionError: 任一入口接受非法矩阵时抛出。
    """

    failure_reason = _runtime_failure_for_status(status)
    with pytest.raises(ValueError, match="stored_file_count"):
        FinsUploadPipelineResult(
            status=status,
            stored_file_count=stored_file_count,
            failure_reason=failure_reason,
        )
    payload: dict[str, JsonValue] = {
        "status": status,
        "stored_file_count": stored_file_count,
    }
    if failure_reason is not None:
        payload["failure"] = failure_reason.to_json()
    with pytest.raises(ValueError, match="stored_file_count"):
        FinsUploadPipelineResult.from_pipeline_json(payload)


@pytest.mark.parametrize("stored_file_count", (True, -1, 1.5, "1", None))
def test_upload_pipeline_count_owner_rejects_missing_bool_negative_and_non_int(
    stored_file_count: JsonValue,
) -> None:
    """pipeline parser 必须拒绝缺失、bool、负数和非整数 count。

    Args:
        stored_file_count: 非法 count fixture；``None`` 表示缺失字段。

    Returns:
        无。

    Raises:
        AssertionError: parser 接受非法 count 时抛出。
    """

    payload: dict[str, JsonValue] = {"status": "ok"}
    if stored_file_count is not None:
        payload["stored_file_count"] = stored_file_count
    with pytest.raises(ValueError, match="stored_file_count"):
        FinsUploadPipelineResult.from_pipeline_json(payload)


@pytest.mark.parametrize("stored_file_count", (True, -1))
def test_upload_pipeline_constructor_rejects_bool_and_negative_count(
    stored_file_count: int,
) -> None:
    """pipeline direct constructor 必须拒绝 bool 与负数 count。

    Args:
        stored_file_count: 非法 typed count fixture。

    Returns:
        无。

    Raises:
        AssertionError: constructor 接受非法 count 时抛出。
    """

    with pytest.raises(ValueError, match="stored_file_count"):
        FinsUploadPipelineResult(
            status="cancelled",
            stored_file_count=stored_file_count,
        )


@pytest.mark.parametrize(
    ("status", "requested_file_count", "stored_file_count"),
    (
        ("ok", 2, 2),
        ("skipped", 2, 0),
        ("deleted", 0, 0),
        ("cancelled", 0, 0),
        ("failed", 0, 0),
    ),
)
def test_upload_summary_count_owner_accepts_complete_status_matrix(
    status: str,
    requested_file_count: int,
    stored_file_count: int,
) -> None:
    """runtime summary owner 必须接受完整合法 requested/stored 矩阵。

    Args:
        status: runtime 上传终态。
        requested_file_count: validated request 文件数。
        stored_file_count: commit 后发布的 original 数。

    Returns:
        无。

    Raises:
        AssertionError: 合法矩阵未被接受或 JSON 投影漂移时抛出。
    """

    summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status=status,
        requested_file_count=requested_file_count,
        stored_file_count=stored_file_count,
        failure_reason=_runtime_failure_for_status(status),
    )

    assert summary.to_json_summary()["requested_file_count"] == requested_file_count
    assert summary.to_json_summary()["stored_file_count"] == stored_file_count


@pytest.mark.parametrize(
    ("status", "requested_file_count", "stored_file_count"),
    (
        ("ok", 0, 0),
        ("ok", 2, 1),
        ("ok", 1, 2),
        ("skipped", 0, 0),
        ("skipped", 1, 1),
        ("deleted", 0, 1),
        ("cancelled", 0, 1),
        ("failed", 0, 1),
    ),
)
def test_upload_summary_count_owner_rejects_invalid_status_matrix(
    status: str,
    requested_file_count: int,
    stored_file_count: int,
) -> None:
    """runtime summary owner 必须拒绝不一致或非零 non-ok stored count。

    Args:
        status: runtime 上传终态。
        requested_file_count: validated request 文件数。
        stored_file_count: 非法 publication count fixture。

    Returns:
        无。

    Raises:
        AssertionError: constructor 接受非法矩阵时抛出。
    """

    with pytest.raises(ValueError, match="file_count"):
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status=status,
            requested_file_count=requested_file_count,
            stored_file_count=stored_file_count,
            failure_reason=_runtime_failure_for_status(status),
        )


@pytest.mark.parametrize(
    ("requested_file_count", "stored_file_count"),
    ((True, 0), (0, True), (-1, 0), (0, -1)),
)
def test_upload_summary_count_owner_rejects_bool_and_negative_counts(
    requested_file_count: int,
    stored_file_count: int,
) -> None:
    """runtime summary count owner 必须拒绝 bool 与负数。

    Args:
        requested_file_count: 非法 requested count fixture。
        stored_file_count: 非法 stored count fixture。

    Returns:
        无。

    Raises:
        AssertionError: constructor 接受非法整数语义时抛出。
    """

    with pytest.raises(ValueError, match="file_count"):
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="cancelled",
            requested_file_count=requested_file_count,
            stored_file_count=stored_file_count,
        )


def _constructor_keyword_sets(source_path: Path, constructor_name: str) -> list[frozenset[str]]:
    """读取 production AST 并返回指定 constructor 的显式关键字集合。

    Args:
        source_path: 待审计 production Python 文件。
        constructor_name: constructor 符号名。

    Returns:
        每个 constructor call 的显式关键字名称集合。

    Raises:
        OSError: production 文件读取失败时抛出。
        SyntaxError: production 文件无法解析时抛出。
    """

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    return [
        frozenset(keyword.arg for keyword in node.keywords if keyword.arg is not None)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == constructor_name
    ]


def _direct_exception_handler_names(
    source_path: Path,
    *,
    function_name: str,
    class_name: str | None,
) -> tuple[str, ...]:
    """读取 workflow 外层 try 的直接异常 handler 名称。

    Args:
        source_path: 待审计 production Python 文件。
        function_name: workflow 函数或异步方法名称。
        class_name: 方法所属类名；顶层函数传入 ``None``。

    Returns:
        workflow 外层 try 按声明顺序排列的异常类型名称。

    Raises:
        AssertionError: workflow、外层 try 或直接名称类型的 handler 不唯一时抛出。
        OSError: production 文件读取失败时抛出。
        SyntaxError: production 文件无法解析时抛出。
    """

    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    owner_body = tree.body
    if class_name is not None:
        owner_classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name]
        assert len(owner_classes) == 1
        owner_body = owner_classes[0].body
    workflow_functions = [
        node for node in owner_body if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name
    ]
    assert len(workflow_functions) == 1
    outer_tries = [node for node in workflow_functions[0].body if isinstance(node, ast.Try)]
    assert len(outer_tries) == 1
    handler_types = [handler.type for handler in outer_tries[0].handlers]
    assert all(isinstance(handler_type, ast.Name) for handler_type in handler_types)
    return tuple(handler_type.id for handler_type in handler_types if isinstance(handler_type, ast.Name))


def test_filing_workflows_consume_only_typed_admission_failure_before_generic_handlers() -> None:
    """filing 必须消费唯一 typed failure，material 则保持既有 generic 边界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: SEC/CN filing 直接捕获 Docling、typed handler 顺序漂移，或 material
            既有异常边界改变时抛出。
        OSError: production 文件读取失败时抛出。
        SyntaxError: production 文件无法解析时抛出。
    """

    pipelines_root = Path(ingestion_runtime.__file__).parent / "pipelines"
    workflow_contracts = (
        (
            pipelines_root / "sec_upload_workflow.py",
            None,
            "run_upload_filing_stream",
            ("FinsUploadFailureError", "OSError", "Exception"),
        ),
        (
            pipelines_root / "cn_pipeline.py",
            "CnPipeline",
            "upload_filing_stream",
            ("FinsUploadFailureError", "OSError", "Exception"),
        ),
        (
            pipelines_root / "sec_upload_workflow.py",
            None,
            "run_upload_material_stream",
            ("Exception",),
        ),
        (
            pipelines_root / "cn_pipeline.py",
            "CnPipeline",
            "upload_material_stream",
            ("Exception",),
        ),
    )

    for source_path, class_name, function_name, expected_handlers in workflow_contracts:
        assert (
            _direct_exception_handler_names(
                source_path,
                function_name=function_name,
                class_name=class_name,
            )
            == expected_handlers
        )


def test_production_upload_count_constructors_are_explicit_and_complete() -> None:
    """production constructor inventory 必须与 S1 review 裁决后的清单完全一致。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: constructor 数量或 required count 关键字缺失时抛出。
        OSError: production 文件读取失败时抛出。
        SyntaxError: production 文件无法解析时抛出。
    """

    fins_root = Path(ingestion_runtime.__file__).parent
    summary_calls = _constructor_keyword_sets(
        fins_root / "ingestion_runtime.py",
        "FinsUploadResultSummary",
    ) + _constructor_keyword_sets(
        fins_root / "service_runtime.py",
        "FinsUploadResultSummary",
    )
    operation_calls: list[frozenset[str]] = []
    for source_path in (
        fins_root / "pipelines" / "docling_upload_service.py",
        fins_root / "pipelines" / "sec_upload_workflow.py",
        fins_root / "pipelines" / "cn_pipeline.py",
    ):
        operation_calls.extend(_constructor_keyword_sets(source_path, "UploadOperationResult"))
    ingestion_tree = ast.parse(
        (fins_root / "ingestion_runtime.py").read_text(encoding="utf-8"),
        filename=str(fins_root / "ingestion_runtime.py"),
    )
    pipeline_class = next(
        node
        for node in ingestion_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "FinsUploadPipelineResult"
    )
    parser_method = next(
        node for node in pipeline_class.body if isinstance(node, ast.FunctionDef) and node.name == "from_pipeline_json"
    )
    pipeline_calls = [
        frozenset(keyword.arg for keyword in node.keywords if keyword.arg is not None)
        for node in ast.walk(parser_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "cls"
    ]

    assert len(summary_calls) == 4
    assert all({"requested_file_count", "stored_file_count"} <= keywords for keywords in summary_calls)
    assert len(operation_calls) == 4
    assert all("stored_file_count" in keywords for keywords in operation_calls)
    assert pipeline_calls == [
        frozenset(
            {
                "status",
                "stored_file_count",
                "document_id",
                "internal_document_id",
                "primary_document",
                "deleted",
                "skip_reason",
                "document_version",
                "source_fingerprint",
                "failure_reason",
            }
        )
    ]


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
    return fins_upload_failure_from_exception(RuntimeError(), file_label=None)


def test_upload_validator_accepts_v_dot_ba_alias_from_identity_grammar() -> None:
    """upload static validator 应接受 resolver 可产生的 ``V.BA`` alias。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: producer grammar 与 upload consumer 再次断裂时抛出。
    """

    request = FinsUploadFilingRequest(
        ticker="V",
        action="delete",
        fiscal_year=2024,
        fiscal_period="FY",
        ticker_aliases=("V.BA",),
    )
    validated = validate_fins_upload_filing_request(
        request,
        published_state=_filing_upload_published_state(
            request,
            source_meta={"source_fingerprint": "published"},
            status=SourceIntegrityStatus.COMPLETE,
            reasons=(),
        ),
    )

    assert validated.normalized_ticker.canonical == "V"
    assert validated.request.ticker_aliases == ("V.BA",)


def _pathful_basename_for_static_admission(file_path: Path) -> str:
    """为不能创建反斜杠文件名的平台提供等价 ``Path.name`` owner fixture。

    Args:
        file_path: static validator 接收的占位路径。

    Returns:
        canonicalizer 必须拒绝的 pathful basename。

    Raises:
        无。
    """

    del file_path
    return "a\\b.pdf"


def _fail_if_static_admission_probes_path(file_path: Path) -> bool:
    """证明 basename shape rejection 发生在任一 filesystem probe 前。

    Args:
        file_path: 不应被访问的文件路径。

    Returns:
        不返回。

    Raises:
        AssertionError: static validator 在 basename admission 前探测路径时始终抛出。
    """

    raise AssertionError(f"basename admission 前禁止探测文件系统：{file_path!s}")


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
        "files_not_allowed_for_delete",
        "duplicate_file_path",
        "multiple_primary_selectors",
        "missing_multi_file_primary",
        "primary_not_in_files",
        "primary_not_allowed_for_delete",
        "missing_fiscal_year",
        "invalid_fiscal_year",
        "missing_fiscal_period",
        "fiscal_period_too_long",
        "unsupported_cn_fiscal_period",
        "invalid_filing_date",
        "invalid_report_date",
        "company_name_too_long",
        "too_many_ticker_aliases",
        "missing_files",
        "invalid_file_basename",
        "file_not_found",
        "file_not_regular",
        "company_name_required",
        "create_target_exists",
        "update_target_missing",
        "existing_source_repair_requires_auto",
    }
    assert {code.value for code in FinsUploadUsageCode} == expected_codes
    exact_messages = {
        FinsUploadUsageCode.EMPTY_TICKER: "--ticker 不能为空，请提供公司代码",
        FinsUploadUsageCode.INVALID_TICKER: "--ticker 无法识别，请提供有效公司代码",
        FinsUploadUsageCode.MISSING_FISCAL_YEAR: "--fiscal-year 不能为空",
        FinsUploadUsageCode.MISSING_FISCAL_PERIOD: "--fiscal-period 不能为空",
        FinsUploadUsageCode.MISSING_FILES: "create/update 上传必须提供 --files",
        FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE: "delete 不得提供 --files",
        FinsUploadUsageCode.DUPLICATE_FILE_PATH: "--files 不能包含解析后相同的重复路径",
        FinsUploadUsageCode.MULTIPLE_PRIMARY_SELECTORS: "--primary 只能指定一次",
        FinsUploadUsageCode.MISSING_MULTI_FILE_PRIMARY: "多文件 filing 必须使用 --primary 明确指定主文件",
        FinsUploadUsageCode.PRIMARY_NOT_IN_FILES: "--primary 必须精确匹配 --files 中的一个文件",
        FinsUploadUsageCode.PRIMARY_NOT_ALLOWED_FOR_DELETE: "delete 不得提供 --primary",
        FinsUploadUsageCode.INVALID_FILE_BASENAME: "上传文件名无效；请提供单个非空文件名",
        FinsUploadUsageCode.COMPANY_NAME_REQUIRED: "当前公司缺少有效元数据；create/update 必须提供 --company-name",
        FinsUploadUsageCode.INVALID_FISCAL_YEAR: "财年（fiscal_year）必须是 1000..9999 的整数",
        FinsUploadUsageCode.INVALID_FILING_DATE: "披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期",
        FinsUploadUsageCode.INVALID_REPORT_DATE: "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期",
        FinsUploadUsageCode.FISCAL_PERIOD_TOO_LONG: "--fiscal-period 长度不能超过 240 个字符",
        FinsUploadUsageCode.UNSUPPORTED_CN_FISCAL_PERIOD: "CN/HK --fiscal-period 仅支持 Q1、Q2、Q3、Q4、H1、FY",
        FinsUploadUsageCode.EXISTING_SOURCE_REPAIR_REQUIRES_AUTO: (
            "目标 filing 不完整；请使用 auto 并提供完整文件重新上传"
        ),
    }
    for code in FinsUploadUsageCode:
        if code in {
            FinsUploadUsageCode.FILE_NOT_FOUND,
            FinsUploadUsageCode.FILE_NOT_REGULAR,
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
    for code in (
        FinsUploadUsageCode.INVALID_FISCAL_YEAR,
        FinsUploadUsageCode.INVALID_FILING_DATE,
        FinsUploadUsageCode.INVALID_REPORT_DATE,
    ):
        assert "--" not in fins_upload_usage_failure(code).message

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


def test_upload_usage_failure_fact_rejects_open_code_and_unbounded_message() -> None:
    """usage public fact 必须自身校验 closed code union 与 240 字符消息上界。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 直接 dataclass 构造可绕过 closed/bounded invariant 时抛出。
    """

    invalid_code = cast(
        FinsUploadUsageCode | FinsUploadFormatFailureKind,
        "open_code",
    )
    with pytest.raises(TypeError, match="closed contract"):
        FinsUploadUsageFailure(code=invalid_code, message="非法 code")
    with pytest.raises(ValueError, match="不能为空"):
        FinsUploadUsageFailure(code=FinsUploadUsageCode.EMPTY_TICKER, message="")
    with pytest.raises(ValueError, match="长度上限"):
        FinsUploadUsageFailure(
            code=FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED,
            message="x" * 241,
        )


def test_filing_static_admission_rejects_pathful_basename_before_filesystem_probes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pathful basename 必须在任一文件探测或 workspace read 前 typed 拒绝。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: Windows 等平台的等价 basename 与 probe guard 夹具。

    Returns:
        无。

    Raises:
        AssertionError: code/message、跨平台 owner contract 或校验顺序漂移时抛出。
    """

    raw_basename = "a\\b.pdf"
    if os.name == "nt":
        upload_file = tmp_path / "placeholder.pdf"
        upload_file.write_bytes(b"filing")
        monkeypatch.setattr(Path, "name", property(_pathful_basename_for_static_admission))
    else:
        upload_file = tmp_path / raw_basename
        upload_file.write_bytes(b"filing")
        assert upload_file.is_file()

    monkeypatch.setattr(Path, "exists", _fail_if_static_admission_probes_path)
    monkeypatch.setattr(Path, "is_file", _fail_if_static_admission_probes_path)
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        ingestion_runtime._filing_upload_request_identity(request)

    failure = exc_info.value.failure
    assert failure.code is FinsUploadUsageCode.INVALID_FILE_BASENAME
    assert failure.message == "上传文件名无效；请提供单个非空文件名"
    assert raw_basename not in failure.message
    with pytest.raises(ValueError, match="非文件 usage failure 不接受 file_name"):
        fins_upload_usage_failure(
            FinsUploadUsageCode.INVALID_FILE_BASENAME,
            file_name="report.pdf",
        )


@pytest.mark.parametrize(
    ("raw_basename", "expected_label"),
    (
        ("report.pdf", "report.pdf"),
        ("审计报告.pdf", "审计报告.pdf"),
        ("job_id_notes.pdf", "输入文件（文件名已隐藏）"),
        ("line\nbreak.pdf", "输入文件（文件名已隐藏）"),
        ("report\u202ename.pdf", "输入文件（文件名已隐藏）"),
        (f"{'a' * 241}.pdf", "输入文件（文件名已隐藏）"),
    ),
)
def test_filing_static_admission_accepts_every_canonicalizable_basename(
    raw_basename: str,
    expected_label: str,
) -> None:
    """static admission 不得把应由 failure label owner 隐藏的合法 basename 拒绝。

    Args:
        raw_basename: 普通、Unicode、fragment、Cc/Cf 或合法超长 basename。
        expected_label: 既有 failure label owner 必须保持的投影。

    Returns:
        无。

    Raises:
        AssertionError: static 接受集收紧或既有 failure label contract 漂移时抛出。
    """

    ingestion_runtime._admit_fins_upload_file_basename(raw_basename)

    assert canonicalize_fins_public_file_label(raw_basename) == expected_label


def test_validate_fins_upload_filing_request_resolves_state_aware_contract(
    tmp_path: Path,
) -> None:
    """validator 必须统一解析 identity、action 与 company decision。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: owner contract 未按 published state 解析时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"pdf")
    request = FinsUploadFilingRequest(
        ticker="aapl.us",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period=" fy ",
        company_name="Apple Inc.",
    )
    absent = _filing_upload_published_state(
        request,
        status=SourceIntegrityStatus.MISSING,
        reasons=(),
    )

    validated = validate_fins_upload_filing_request(request, published_state=absent)

    assert validated.request is request
    assert validated.normalized_ticker.canonical == "AAPL"
    assert validated.normalized_fiscal_period == "FY"
    assert validated.resolved_action == "create"
    assert validated.published_state is absent
    assert validated.company_meta_decision.disposition == "stage"
    assert validated.file_selection == FinsUploadFilingFiles.for_upsert(
        primary=upload_file.resolve(strict=False),
        companions=(),
    )
    assert isinstance(validated.repair_disposition, NoExistingSourceRepair)

    present = _filing_upload_published_state(
        request,
        company_meta=CompanyMeta(
            company_id="AAPL_US",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version=RESOLVER_VERSION,
            updated_at="2026-08-15T00:00:00+00:00",
        ),
        source_meta={"source_fingerprint": "old"},
        status=SourceIntegrityStatus.COMPLETE,
        reasons=(),
    )
    updated = validate_fins_upload_filing_request(
        replace(request, company_name=None),
        published_state=present,
    )
    assert updated.resolved_action == "update"
    assert updated.company_meta_decision.disposition == "keep"
    assert updated.file_selection == FinsUploadFilingFiles.for_upsert(
        primary=upload_file.resolve(strict=False),
        companions=(),
    )
    assert isinstance(updated.repair_disposition, NoExistingSourceRepair)


@pytest.mark.parametrize("overwrite", (False, True))
@pytest.mark.parametrize("is_deleted", (False, True))
def test_filing_validator_authorizes_only_complete_auto_repair_selection(
    tmp_path: Path,
    overwrite: bool,
    is_deleted: bool,
) -> None:
    """repair-required + exact auto 必须固定 update 并保留完整 authoritative selection。

    Args:
        tmp_path: 用于创建 primary 与 companion 输入文件。
        overwrite: 不得扩大或缩小 repair 资格的覆盖标志。
        is_deleted: 既有 source 的 logical deletion 状态。

    Returns:
        无。

    Raises:
        AssertionError: repair eligibility、selection 或 deleted/overwrite 语义漂移时抛出。
    """

    companion = tmp_path / "schema.xsd"
    primary = tmp_path / "report.html"
    companion.write_text("schema", encoding="utf-8")
    primary.write_text("report", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="aapl.us",
        action="auto",
        files=(companion, primary),
        primary_selectors=(primary,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
        overwrite=overwrite,
    )
    published_state = _filing_upload_published_state(
        request,
        source_meta={
            "is_deleted": is_deleted,
            "deleted_at": "2026-08-15T00:00:00+00:00" if is_deleted else None,
            "source_fingerprint": "published",
        },
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        reasons=(SourceIntegrityReason.DECLARED_FILE_MISSING,),
    )

    validated = validate_fins_upload_filing_request(
        request,
        published_state=published_state,
    )

    assert validated.resolved_action == "update"
    assert validated.file_selection.primary == primary.resolve(strict=False)
    assert validated.file_selection.companions == (companion.resolve(strict=False),)
    assert isinstance(validated.repair_disposition, ExistingSourceAutoRepair)
    assert (
        validated.repair_disposition.expected_integrity
        is published_state.source_integrity
    )


@pytest.mark.parametrize("action", ("create", "update", "delete", "AUTO", " auto "))
def test_filing_validator_repair_required_non_exact_auto_precedes_company_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    """repair-required 的非 exact-auto 动作必须返回唯一 usage failure。

    Args:
        tmp_path: 用于创建 upsert 输入文件。
        monkeypatch: 用于证明 company decision 尚未解析。
        action: 当前 requested action。

    Returns:
        无。

    Raises:
        AssertionError: precedence、code 或文案漂移时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"report")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action=action,
        files=() if action == "delete" else (upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    published_state = _filing_upload_published_state(
        request,
        source_meta={"is_deleted": False, "source_fingerprint": "published"},
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        reasons=(SourceIntegrityReason.DECLARED_FILE_MISSING,),
    )
    monkeypatch.setattr(
        ingestion_runtime,
        "resolve_upload_company_meta_decision",
        pytest.fail,
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        validate_fins_upload_filing_request(request, published_state=published_state)

    assert (
        exc_info.value.failure.code
        is FinsUploadUsageCode.EXISTING_SOURCE_REPAIR_REQUIRES_AUTO
    )
    assert (
        exc_info.value.failure.message
        == "目标 filing 不完整；请使用 auto 并提供完整文件重新上传"
    )


@pytest.mark.parametrize("action", ("auto", "create", "update", "delete"))
def test_filing_validator_unsafe_prevalidation_precedes_action_and_company(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    """UNSAFE 必须在 action resolution 与 company decision 前产生 typed failure。

    Args:
        tmp_path: 用于创建 upsert 输入文件。
        monkeypatch: 用于禁止下游 action/company owner 调用。
        action: 当前合法 requested action。

    Returns:
        无。

    Raises:
        AssertionError: UNSAFE precedence 或 path-free failure 漂移时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"report")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action=action,
        files=() if action == "delete" else (upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    published_state = _filing_upload_published_state(
        request,
        source_meta=None,
        status=SourceIntegrityStatus.UNSAFE,
        reasons=(SourceIntegrityReason.META_UNTRUSTED,),
    )
    monkeypatch.setattr(ingestion_runtime, "resolve_upload_action", pytest.fail)
    monkeypatch.setattr(
        ingestion_runtime,
        "resolve_upload_company_meta_decision",
        pytest.fail,
    )

    with pytest.raises(FinsUploadPrevalidationError) as exc_info:
        validate_fins_upload_filing_request(request, published_state=published_state)

    assert exc_info.value.failure == fins_upload_source_integrity_unsafe_failure()
    assert str(tmp_path) not in exc_info.value.failure.message
    assert _PUBLISHED_SOURCE_REVISION_TOKEN not in repr(exc_info.value.failure)


def test_validated_filing_repair_contract_rejects_incomplete_selection_and_target(
    tmp_path: Path,
) -> None:
    """validated repair contract 必须拒绝 empty/incomplete selection 与 expected target 错配。

    Args:
        tmp_path: 用于创建多文件 authoritative selection。

    Returns:
        无。

    Raises:
        AssertionError: direct constructor 可以绕过 validator repair contract 时抛出。
    """

    primary = tmp_path / "report.pdf"
    companion = tmp_path / "notes.txt"
    primary.write_bytes(b"primary")
    companion.write_text("notes", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="auto",
        files=(primary, companion),
        primary_selectors=(primary,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    published_state = _filing_upload_published_state(
        request,
        source_meta={"source_fingerprint": "published"},
        status=SourceIntegrityStatus.REPAIR_REQUIRED,
        reasons=(SourceIntegrityReason.DECLARED_FILE_MISSING,),
    )
    validated = validate_fins_upload_filing_request(
        request,
        published_state=published_state,
    )

    with pytest.raises(ValueError, match="非空完整"):
        replace(validated, file_selection=FinsUploadFilingFiles.for_delete())
    with pytest.raises(ValueError, match="不完整一致"):
        replace(
            validated,
            file_selection=FinsUploadFilingFiles.for_upsert(
                primary=primary.resolve(strict=False),
                companions=(),
            ),
        )
    with pytest.raises(ValueError, match="duplicate_file_path"):
        replace(
            validated,
            request=replace(
                request,
                files=(primary, primary),
                primary_selectors=(primary,),
            ),
        )
    mismatched_integrity = replace(
        published_state.source_integrity,
        document_id="other-filing",
    )
    with pytest.raises(ValueError, match="expected target"):
        replace(
            validated,
            repair_disposition=ExistingSourceAutoRepair(
                expected_integrity=mismatched_integrity
            ),
        )


@pytest.mark.parametrize("target_field", ("ticker", "document_id"))
def test_filing_validator_rejects_published_target_identity_mismatch(
    tmp_path: Path,
    target_field: str,
) -> None:
    """validator 必须在状态裁决前拒绝 storage producer 的 exact target 错配。

    Args:
        tmp_path: 用于创建合法静态输入。
        target_field: 当前故意错配的 classification identity 字段。

    Returns:
        无。

    Raises:
        AssertionError: validator 接受 ticker/document identity 漂移时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"report")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    valid_state = _filing_upload_published_state(
        request,
        status=SourceIntegrityStatus.MISSING,
        reasons=(),
    )
    replacement = "MSFT" if target_field == "ticker" else "other-filing"
    mismatched_state = replace(
        valid_state,
        source_integrity=replace(
            valid_state.source_integrity,
            **{target_field: replacement},
        ),
    )

    with pytest.raises(ValueError, match="expected target"):
        validate_fins_upload_filing_request(request, published_state=mismatched_state)


def test_raw_runtime_unsafe_prevalidation_creates_no_job_observation_or_mutation(
    tmp_path: Path,
) -> None:
    """raw runtime job/observation start 必须原样抛 typed failure 且零持久化。

    Args:
        tmp_path: 用于创建输入文件与隔离 workspace。

    Returns:
        无。

    Raises:
        AssertionError: prevalidation 被 generic 化或创建 job/observation/runner mutation 时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"report")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="auto",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    unsafe_state = _filing_upload_published_state(
        request,
        source_meta=None,
        status=SourceIntegrityStatus.UNSAFE,
        reasons=(SourceIntegrityReason.META_UNTRUSTED,),
    )
    workspace_root = tmp_path / "runtime-workspace"
    runtime, executor, state_repository, runner = _build_fixed_state_guarded_runtime(
        workspace_root,
        unsafe_state,
    )
    before = _snapshot_runtime_workspace_tree(workspace_root)

    with pytest.raises(FinsUploadPrevalidationError) as job_exc:
        runtime.start_upload(request)
    with pytest.raises(FinsUploadPrevalidationError) as observation_exc:
        runtime.prepare_observed_upload(request, _NeverCancelledToken())

    expected_failure = fins_upload_source_integrity_unsafe_failure()
    assert job_exc.value.failure == expected_failure
    assert observation_exc.value.failure == expected_failure
    assert state_repository.calls == [
        (unsafe_state.source_integrity.ticker, unsafe_state.source_integrity.document_id),
        (unsafe_state.source_integrity.ticker, unsafe_state.source_integrity.document_id),
    ]
    assert state_repository.batch_calls == []
    assert executor.operations == []
    assert runner.requests == []
    assert runtime._observations == {}
    assert _snapshot_runtime_workspace_tree(workspace_root) == before
    jobs_root = workspace_root / ".dayu" / "fins_ingestion" / "jobs"
    assert not jobs_root.exists() or tuple(jobs_root.glob("*.json")) == ()


def test_runtime_filing_state_fakes_conform_to_required_batch_read_contract() -> None:
    """两个 runtime structural fake 必须精确实现 required batch read contract。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: fixed/forbidden fake 的返回、失败或独立记录语义漂移时抛出。
    """

    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete",
        fiscal_year=2024,
        fiscal_period="FY",
    )
    state = _filing_upload_published_state(
        request,
        status=SourceIntegrityStatus.MISSING,
        reasons=(),
    )
    batch = BatchToken(transaction_id="fixture-batch", ticker="AAPL")
    document_id = state.source_integrity.document_id
    fixed_repository = _FixedFilingUploadStateRepository(state)
    forbidden_repository = _ForbiddenFilingUploadStateRepository()

    assert fixed_repository.read_filing_upload_state_in_batch(batch, document_id) is state
    assert fixed_repository.batch_calls == [(batch, document_id)]
    assert fixed_repository.calls == []

    with pytest.raises(
        AssertionError,
        match="static admission 前禁止读取 batch filing state",
    ):
        forbidden_repository.read_filing_upload_state_in_batch(batch, document_id)
    assert forbidden_repository.batch_calls == [(batch, document_id)]
    assert forbidden_repository.calls == []


def test_filing_validator_builds_role_selection_and_typed_delete_empty(
    tmp_path: Path,
) -> None:
    """validator 必须直接产生 non-Optional upsert/delete filing selection。

    Args:
        tmp_path: 用于创建 primary 与 companion 文件的临时目录。

    Returns:
        无。

    Raises:
        AssertionError: selection 角色、顺序或 delete 空状态漂移时抛出。
    """

    primary = tmp_path / "report.html"
    companion = tmp_path / "schema.xsd"
    primary.write_text("<html></html>", encoding="utf-8")
    companion.write_text("<schema></schema>", encoding="utf-8")
    upsert_request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(primary, companion),
        primary_selectors=(primary,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    upsert = validate_fins_upload_filing_request(
        upsert_request,
        published_state=_filing_upload_published_state(
            upsert_request,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
    )

    assert upsert.file_selection.primary == primary.resolve(strict=False)
    assert upsert.file_selection.companions == (companion.resolve(strict=False),)
    assert upsert.file_selection.ordered_files == (
        primary.resolve(strict=False),
        companion.resolve(strict=False),
    )
    assert upsert.file_selection.is_empty is False

    delete_request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete",
        fiscal_year=2024,
        fiscal_period="FY",
    )
    deleted = validate_fins_upload_filing_request(
        delete_request,
        published_state=_filing_upload_published_state(
            delete_request,
            source_meta={"source_fingerprint": "published"},
            status=SourceIntegrityStatus.COMPLETE,
            reasons=(),
        ),
    )
    assert deleted.resolved_action == "delete"
    assert deleted.file_selection == FinsUploadFilingFiles.for_delete()
    assert deleted.file_selection.is_empty is True


@pytest.mark.parametrize("primary_index", (0, 1, 2))
def test_filing_validator_selects_explicit_primary_at_any_position(
    tmp_path: Path,
    primary_index: int,
) -> None:
    """多文件 filing 的 authoritative primary 不得由输入位置推断。

    Args:
        tmp_path: 用于创建三个合法 filing 文件的临时目录。
        primary_index: selector 在 raw files 中的位置。

    Returns:
        无。

    Raises:
        AssertionError: primary 角色或 companion 相对顺序依赖首项时抛出。
    """

    files = tuple(tmp_path / f"part-{index}.txt" for index in range(3))
    for path in files:
        path.write_text(path.name, encoding="utf-8")
    primary = files[primary_index]
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=files,
        primary_selectors=(primary,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    validated = validate_fins_upload_filing_request(
        request,
        published_state=_filing_upload_published_state(
            request,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
    )

    normalized_files = tuple(path.resolve(strict=False) for path in files)
    normalized_primary = primary.resolve(strict=False)
    assert validated.request is request
    assert validated.request.files == files
    assert validated.request.primary_selectors == (primary,)
    assert validated.file_selection.primary == normalized_primary
    assert validated.file_selection.companions == tuple(
        path for path in normalized_files if path != normalized_primary
    )


@pytest.mark.parametrize(
    ("files_count", "selectors_count", "expected_code", "expected_message"),
    (
        (
            2,
            0,
            FinsUploadUsageCode.MISSING_MULTI_FILE_PRIMARY,
            "多文件 filing 必须使用 --primary 明确指定主文件",
        ),
        (
            1,
            2,
            FinsUploadUsageCode.MULTIPLE_PRIMARY_SELECTORS,
            "--primary 只能指定一次",
        ),
        (
            1,
            1,
            FinsUploadUsageCode.PRIMARY_NOT_IN_FILES,
            "--primary 必须精确匹配 --files 中的一个文件",
        ),
    ),
)
def test_filing_validator_rejects_invalid_primary_selector_contract(
    tmp_path: Path,
    files_count: int,
    selectors_count: int,
    expected_code: FinsUploadUsageCode,
    expected_message: str,
) -> None:
    """缺失、重复或集合外 selector 必须产生精确 closed failure。

    Args:
        tmp_path: 用于创建合法文件与集合外 selector 的临时目录。
        files_count: raw files 数量。
        selectors_count: raw selector occurrence 数量。
        expected_code: 预期 closed usage code。
        expected_message: 预期固定中文文案。

    Returns:
        无。

    Raises:
        AssertionError: selector admission 分类或文案漂移时抛出。
    """

    files = tuple(tmp_path / f"file-{index}.txt" for index in range(files_count))
    for path in files:
        path.write_text(path.name, encoding="utf-8")
    outside = tmp_path / "outside.txt"
    selectors = (
        (outside,)
        if selectors_count == 1
        else tuple(files[0] for _ in range(selectors_count))
    )
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=files,
        primary_selectors=selectors,
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        ingestion_runtime._filing_upload_request_identity(request)

    assert exc_info.value.failure.code is expected_code
    assert exc_info.value.failure.message == expected_message


@pytest.mark.parametrize(
    ("include_files", "include_primary", "expected_code", "expected_message"),
    (
        (
            True,
            False,
            FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE,
            "delete 不得提供 --files",
        ),
        (
            True,
            True,
            FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE,
            "delete 不得提供 --files",
        ),
        (
            False,
            True,
            FinsUploadUsageCode.PRIMARY_NOT_ALLOWED_FOR_DELETE,
            "delete 不得提供 --primary",
        ),
    ),
)
def test_filing_delete_rejects_files_before_primary_and_path_normalization(
    monkeypatch: pytest.MonkeyPatch,
    include_files: bool,
    include_primary: bool,
    expected_code: FinsUploadUsageCode,
    expected_message: str,
) -> None:
    """delete 必须按 files→primary 优先级在任一路径规范化前拒绝。

    Args:
        monkeypatch: 用于禁止路径规范化的 pytest 夹具。
        include_files: 是否携带 raw files。
        include_primary: 是否携带 raw primary selector。
        expected_code: 预期 closed usage code。
        expected_message: 预期固定中文文案。

    Returns:
        无。

    Raises:
        AssertionError: delete 校验越过静态边界或 precedence 漂移时抛出。
    """

    def forbid_expanduser(path: Path) -> Path:
        """禁止 delete rejection 进入路径规范化。

        Args:
            path: 不应被规范化的 raw 路径。

        Returns:
            不返回。

        Raises:
            AssertionError: static admission 错误进入路径规范化时始终抛出。
        """

        raise AssertionError(f"delete rejection 前禁止规范路径：{path!s}")

    monkeypatch.setattr(Path, "expanduser", forbid_expanduser)
    raw_path = Path("never-resolve.pdf")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete",
        files=(raw_path,) if include_files else (),
        primary_selectors=(raw_path,) if include_primary else (),
        fiscal_year=2024,
        fiscal_period="FY",
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        ingestion_runtime._filing_upload_request_identity(request)

    assert exc_info.value.failure.code is expected_code
    assert exc_info.value.failure.message == expected_message


def test_filing_delete_over_raw_limit_precedes_files_rejection() -> None:
    """delete 的 101 个 raw files 必须先返回 TOO_MANY_FILES。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: raw count 不再先于 delete-with-files contract 时抛出。
    """

    raw_path = Path("never-resolve.pdf")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete",
        files=(raw_path,) * 101,
        primary_selectors=(raw_path,),
        fiscal_year=2024,
        fiscal_period="FY",
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        ingestion_runtime._filing_upload_request_identity(request)

    assert exc_info.value.failure.code is FinsUploadUsageCode.TOO_MANY_FILES
    assert exc_info.value.failure.message == "--files 数量不能超过 100 个"


@pytest.mark.parametrize("loop_is_selector", (False, True))
def test_filing_symlink_loop_is_typed_file_not_found_before_all_side_effects(
    tmp_path: Path,
    loop_is_selector: bool,
) -> None:
    """file/selector symlink loop 必须安全映射并阻断全部下游副作用。

    Args:
        tmp_path: 用于创建 symlink loop、合法文件与受保护 workspace。
        loop_is_selector: ``True`` 时把 loop 作为 selector，否则作为 raw file。

    Returns:
        无。

    Raises:
        AssertionError: code/message、路径安全或 static admission 边界漂移时抛出。
        OSError: 测试平台无法创建 symlink 时由 pytest 环境抛出。
    """

    loop = tmp_path / "loop.pdf"
    loop.symlink_to(loop.name)
    valid_file = tmp_path / "valid.pdf"
    valid_file.write_bytes(b"valid")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(valid_file,) if loop_is_selector else (loop,),
        primary_selectors=(loop,) if loop_is_selector else (),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    workspace_root = tmp_path / "guarded-workspace"
    runtime, executor, state_repository, runner = _build_static_admission_guarded_runtime(
        workspace_root
    )
    before = _snapshot_runtime_workspace_tree(workspace_root)

    with pytest.raises(FinsUploadUsageError) as exc_info:
        runtime.start_upload(request)

    assert exc_info.value.failure.code is FinsUploadUsageCode.FILE_NOT_FOUND
    assert exc_info.value.failure.message == "上传文件不存在：loop.pdf"
    assert str(tmp_path) not in exc_info.value.failure.message
    assert state_repository.calls == []
    assert state_repository.batch_calls == []
    assert executor.operations == []
    assert runner.requests == []
    assert runtime._observations == {}
    assert _snapshot_runtime_workspace_tree(workspace_root) == before
    assert not (workspace_root / ".dayu" / "fins_ingestion" / "jobs").exists()
    assert not (workspace_root / "portfolio").exists()


def test_new_filing_admission_failures_precede_state_jobs_runner_and_workspace_mutation(
    tmp_path: Path,
) -> None:
    """本 slice 新增的静态失败必须阻断 state、job、runner 与 workspace mutation。

    Args:
        tmp_path: 用于创建输入文件与受保护 workspace 的临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一新规则越过 static admission owner boundary 时抛出。
    """

    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    outside = tmp_path / "outside.pdf"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    base_request = FinsUploadFilingRequest(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    invalid_requests = (
        (
            replace(
                base_request,
                action="delete",
                files=(first,),
            ),
            FinsUploadUsageCode.FILES_NOT_ALLOWED_FOR_DELETE,
        ),
        (
            replace(
                base_request,
                action="delete",
                primary_selectors=(first,),
            ),
            FinsUploadUsageCode.PRIMARY_NOT_ALLOWED_FOR_DELETE,
        ),
        (
            replace(
                base_request,
                files=(first, first),
                primary_selectors=(first,),
            ),
            FinsUploadUsageCode.DUPLICATE_FILE_PATH,
        ),
        (
            replace(
                base_request,
                files=(first,),
                primary_selectors=(first, first),
            ),
            FinsUploadUsageCode.MULTIPLE_PRIMARY_SELECTORS,
        ),
        (
            replace(
                base_request,
                files=(first, second),
            ),
            FinsUploadUsageCode.MISSING_MULTI_FILE_PRIMARY,
        ),
        (
            replace(
                base_request,
                files=(first,),
                primary_selectors=(outside,),
            ),
            FinsUploadUsageCode.PRIMARY_NOT_IN_FILES,
        ),
    )
    workspace_root = tmp_path / "guarded-workspace"
    runtime, executor, state_repository, runner = _build_static_admission_guarded_runtime(
        workspace_root
    )
    before = _snapshot_runtime_workspace_tree(workspace_root)

    for request, expected_code in invalid_requests:
        with pytest.raises(FinsUploadUsageError) as exc_info:
            runtime.start_upload(request)
        assert exc_info.value.failure.code is expected_code

    assert state_repository.calls == []
    assert state_repository.batch_calls == []
    assert executor.operations == []
    assert runner.requests == []
    assert runtime._observations == {}
    assert _snapshot_runtime_workspace_tree(workspace_root) == before
    assert not (workspace_root / ".dayu" / "fins_ingestion" / "jobs").exists()
    assert not (workspace_root / "portfolio").exists()


def test_filing_duplicate_normalized_paths_precede_selector_errors(
    tmp_path: Path,
) -> None:
    """规范后重复路径必须在 selector cardinality 与 membership 前拒绝。

    Args:
        tmp_path: 用于创建原文件、父目录别名与 symlink 的临时目录。

    Returns:
        无。

    Raises:
        AssertionError: duplicate identity、错误优先级或 symlink resolve 契约漂移时抛出。
        OSError: 测试平台无法创建 symlink 时由 pytest 环境抛出。
    """

    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    nested = tmp_path / "nested"
    nested.mkdir()
    aliases = (
        tmp_path / "." / "report.pdf",
        nested / ".." / "report.pdf",
        tmp_path / "report-link.pdf",
    )
    aliases[-1].symlink_to(report)

    for alias in aliases:
        request = FinsUploadFilingRequest(
            ticker="AAPL",
            files=(report, alias),
            primary_selectors=(report, alias),
            fiscal_year=2024,
            fiscal_period="FY",
            company_name="Apple Inc.",
        )
        with pytest.raises(FinsUploadUsageError) as exc_info:
            ingestion_runtime._filing_upload_request_identity(request)
        assert exc_info.value.failure.code is FinsUploadUsageCode.DUPLICATE_FILE_PATH
        assert exc_info.value.failure.message == "--files 不能包含解析后相同的重复路径"


def test_filing_path_identity_is_case_sensitive_and_does_not_merge_hardlinks(
    tmp_path: Path,
) -> None:
    """path identity 不得 case-fold，也不得按 inode 合并 hardlink。

    Args:
        tmp_path: 用于创建两个不同 resolved path string 的 hardlink。

    Returns:
        无。

    Raises:
        AssertionError: exact string 或 hardlink admission contract 漂移时抛出。
        OSError: 测试平台无法创建 hardlink 时由 pytest 环境抛出。
    """

    assert ingestion_runtime._fins_upload_path_identity(Path("/tmp/Report.pdf")) != (
        ingestion_runtime._fins_upload_path_identity(Path("/tmp/report.pdf"))
    )
    case_request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(Path("/tmp/report.pdf"),),
        primary_selectors=(Path("/tmp/Report.pdf"),),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    with pytest.raises(FinsUploadUsageError) as case_exc:
        ingestion_runtime._filing_upload_request_identity(case_request)
    assert case_exc.value.failure.code is FinsUploadUsageCode.PRIMARY_NOT_IN_FILES

    original = tmp_path / "original.pdf"
    linked = tmp_path / "linked.pdf"
    original.write_bytes(b"same inode")
    os.link(original, linked)
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(original, linked),
        primary_selectors=(linked,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    validated = validate_fins_upload_filing_request(
        request,
        published_state=_filing_upload_published_state(
            request,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
    )

    assert validated.file_selection.primary == linked.resolve(strict=False)
    assert validated.file_selection.companions == (original.resolve(strict=False),)


def test_filing_distinct_same_basename_and_same_stem_paths_are_accepted(
    tmp_path: Path,
) -> None:
    """不同规范路径不得因 basename 或 stem 相同被误判为重复。

    Args:
        tmp_path: 用于创建同 basename 与同 stem 的不同文件。

    Returns:
        无。

    Raises:
        AssertionError: duplicate owner 错用 basename 或 stem 时抛出。
    """

    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    first = first_directory / "report.html"
    second = second_directory / "report.html"
    same_stem = tmp_path / "report.xsd"
    for path in (first, second, same_stem):
        path.write_text(path.name, encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(first, same_stem, second),
        primary_selectors=(second,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    validated = validate_fins_upload_filing_request(
        request,
        published_state=_filing_upload_published_state(
            request,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
    )

    assert validated.file_selection.primary == second.resolve(strict=False)
    assert validated.file_selection.companions == (
        first.resolve(strict=False),
        same_stem.resolve(strict=False),
    )


def test_filing_file_count_limit_counts_raw_entries_before_duplicates(
    tmp_path: Path,
) -> None:
    """100 个不同文件应接受，101 个 raw entries 应先于 duplicate 拒绝。

    Args:
        tmp_path: 用于创建 100 个合法 filing 文件。

    Returns:
        无。

    Raises:
        AssertionError: inclusive 上限或 raw-entry precedence 漂移时抛出。
    """

    files = tuple(tmp_path / f"file-{index:03d}.txt" for index in range(100))
    for path in files:
        path.write_text(path.name, encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=files,
        primary_selectors=(files[-1],),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    accepted = validate_fins_upload_filing_request(
        request,
        published_state=_filing_upload_published_state(
            request,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
    )
    assert len(accepted.file_selection.ordered_files) == 100
    assert accepted.file_selection.primary == files[-1].resolve(strict=False)

    with pytest.raises(FinsUploadUsageError) as exc_info:
        ingestion_runtime._filing_upload_request_identity(
            FinsUploadFilingRequest(
                ticker="AAPL",
                files=(files[0],) * 101,
                fiscal_year=2024,
                fiscal_period="FY",
                company_name="Apple Inc.",
            )
        )
    assert exc_info.value.failure.code is FinsUploadUsageCode.TOO_MANY_FILES


def test_filing_explicit_roles_control_primary_and_companion_suffixes(
    tmp_path: Path,
) -> None:
    """primary/companion suffix 必须由 explicit role 而非 index 校验。

    Args:
        tmp_path: 用于创建 XSD companion 与 HTML primary。

    Returns:
        无。

    Raises:
        AssertionError: role suffix validation 仍依赖首项时抛出。
    """

    companion = tmp_path / "schema.xsd"
    primary = tmp_path / "report.html"
    companion.write_text("schema", encoding="utf-8")
    primary.write_text("report", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(companion, primary),
        primary_selectors=(primary,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    validated = validate_fins_upload_filing_request(
        request,
        published_state=_filing_upload_published_state(
            request,
            status=SourceIntegrityStatus.MISSING,
            reasons=(),
        ),
    )

    assert validated.file_selection.primary == primary.resolve(strict=False)
    assert validated.file_selection.companions == (companion.resolve(strict=False),)


@pytest.mark.parametrize("suffix", (".doc", ".ppt", ".xls", ".zip", ".xsd"))
def test_filing_validator_rejects_unsupported_primary_with_role_specific_usage(
    tmp_path: Path,
    suffix: str,
) -> None:
    """legacy、ZIP 与 companion-only XSD primary 必须产生角色明确的 usage failure。

    Args:
        tmp_path: 用于创建当前后缀测试文件的临时目录。
        suffix: 当前应被 primary contract 拒绝的扩展名。

    Returns:
        无。

    Raises:
        AssertionError: failure kind、文案或路径安全边界漂移时抛出。
    """

    upload_file = tmp_path / f"report{suffix}"
    upload_file.write_text("fixture", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    with pytest.raises(FinsUploadUsageError) as exc_info:
        validate_fins_upload_filing_request(
            request,
            published_state=_filing_upload_published_state(
                request,
                status=SourceIntegrityStatus.MISSING,
                reasons=(),
            ),
        )

    failure = exc_info.value.failure
    assert failure.code is FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED
    assert failure.message == f"财报主文件格式不受支持：{upload_file.name}"
    assert str(tmp_path) not in failure.message


def test_filing_validator_keeps_long_canonical_label_with_bounded_usage_message(
    tmp_path: Path,
) -> None:
    """长合法 basename 的 primary failure 必须保持 usage 分类且不转成 runtime error。

    Args:
        tmp_path: 用于创建长 basename primary 文件的临时目录。

    Returns:
        无。

    Raises:
        AssertionError: canonical label、usage code 或消息边界漂移时抛出。
    """

    basename = f"{'a' * 226}.doc"
    upload_file = tmp_path / basename
    upload_file.write_text("fixture", encoding="utf-8")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )

    with pytest.raises(FinsUploadUsageError) as exc_info:
        validate_fins_upload_filing_request(
            request,
            published_state=_filing_upload_published_state(
                request,
                status=SourceIntegrityStatus.MISSING,
                reasons=(),
            ),
        )

    failure = exc_info.value.failure
    cause = exc_info.value.__cause__
    assert isinstance(cause, FinsUploadFormatError)
    assert cause.file_label == basename
    assert failure.code is FinsUploadFormatFailureKind.PRIMARY_SUFFIX_UNSUPPORTED
    assert failure.message == "财报主文件格式不受支持"
    assert 0 < len(failure.message) <= 240
    assert str(tmp_path) not in failure.message


@pytest.mark.parametrize(
    "existing_meta",
    (
        None,
        CompanyMeta(
            company_id="AAPL_US",
            company_name="Stale Apple",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version="market_resolver_v0.9.0",
            updated_at="2026-08-14T00:00:00+00:00",
        ),
    ),
)
def test_upload_company_meta_missing_name_uses_typed_owner(
    existing_meta: CompanyMeta | None,
) -> None:
    """只有 new/stale company meta 缺少公司名时才抛专用异常。

    Args:
        existing_meta: 不存在或 resolver 版本过期的 company meta。

    Returns:
        无。

    Raises:
        AssertionError: 缺公司名未由 typed owner 表达时抛出。
    """

    with pytest.raises(UploadCompanyNameRequiredError):
        resolve_upload_company_meta_decision(
            existing_meta=existing_meta,
            ticker="AAPL",
            action="create",
            company_name=None,
            ticker_aliases=(),
        )

    with pytest.raises(ValueError) as exc_info:
        resolve_upload_company_meta_decision(
            existing_meta=existing_meta,
            ticker="AAPL",
            action="create",
            company_name="Apple Inc.",
            ticker_aliases=("NOT VALID",),
        )
    assert not isinstance(exc_info.value, UploadCompanyNameRequiredError)


def test_upload_validator_does_not_project_identity_mismatch_as_company_name_required(
    tmp_path: Path,
) -> None:
    """strict-valid published identity mismatch 不得伪装成缺少公司名。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: runtime 错误投影重新漂移时抛出。
    """

    upload_file = tmp_path / "report.pdf"
    upload_file.write_bytes(b"pdf")
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        files=(upload_file,),
        fiscal_year=2024,
        fiscal_period="FY",
        company_name="Apple Inc.",
    )
    mismatched_meta = CompanyMeta(
        company_id="MSFT_US",
        company_name="Microsoft Corporation",
        ticker_identity=build_company_ticker_identity("MSFT", ()),
        resolver_version=RESOLVER_VERSION,
        updated_at="2026-08-14T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="canonical ticker identity") as exc_info:
        validate_fins_upload_filing_request(
            request,
            published_state=_filing_upload_published_state(
                request,
                company_meta=mismatched_meta,
                source_meta=None,
                status=SourceIntegrityStatus.MISSING,
                reasons=(),
            ),
        )

    assert not isinstance(exc_info.value, FinsUploadUsageError)


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
            published_state=_filing_upload_published_state(
                request,
                status=SourceIntegrityStatus.MISSING,
                reasons=(),
            ),
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
    published_state = _filing_upload_published_state(
        request,
        source_meta={"is_deleted": False, "source_fingerprint": "published"},
        status=SourceIntegrityStatus.COMPLETE,
        reasons=(),
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
    deleted_state = _filing_upload_published_state(
        original_request,
        source_meta={"is_deleted": True, "source_fingerprint": "published"},
        status=SourceIntegrityStatus.COMPLETE,
        reasons=(),
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
            FinsUploadFilingRequest(
                ticker="AAPL",
                fiscal_year=2024,
                fiscal_period="FY",
                filing_date="2024-13-01",
                files=(Path("missing.pdf"),),
            ),
            FinsUploadUsageCode.INVALID_FILING_DATE,
        ),
        (
            FinsUploadFilingRequest(
                ticker="AAPL",
                fiscal_year=2024,
                fiscal_period="FY",
                report_date="2024-13-01",
                files=(Path("missing.pdf"),),
            ),
            FinsUploadUsageCode.INVALID_REPORT_DATE,
        ),
        (
            FinsUploadFilingRequest(ticker="AAPL", fiscal_year=2024, fiscal_period="FY"),
            FinsUploadUsageCode.MISSING_FILES,
        ),
    ),
)
def test_validate_fins_upload_filing_request_preserves_validation_priority(
    tmp_path: Path,
    upload_request: FinsUploadFilingRequest,
    expected_code: FinsUploadUsageCode,
) -> None:
    """冲突输入必须按 ticker→year→period→dates→files 的 owner 顺序失败。

    Args:
        tmp_path: pytest 临时目录，用于提供确定不存在的文件路径。
        upload_request: 当前非法请求。
        expected_code: 预期首个 usage code。

    Returns:
        无。

    Raises:
        AssertionError: validator 返回错误优先级时抛出。
    """

    if upload_request.files:
        missing_file = tmp_path / upload_request.files[0].name
        assert not missing_file.exists()
        upload_request = replace(upload_request, files=(missing_file,))

    with pytest.raises(FinsUploadUsageError) as exc_info:
        validate_fins_upload_filing_request(
            upload_request,
            published_state=_filing_upload_published_state(
                upload_request,
                status=SourceIntegrityStatus.MISSING,
                reasons=(),
            ),
        )
    assert exc_info.value.failure.code is expected_code


@pytest.mark.parametrize(
    ("upload_request", "expected_code", "expected_message"),
    (
        (
            FinsUploadFilingRequest(ticker="AAPL", action="delete", fiscal_year=False, fiscal_period="FY"),
            FinsUploadUsageCode.INVALID_FISCAL_YEAR,
            "财年（fiscal_year）必须是 1000..9999 的整数",
        ),
        *tuple(
            (
                FinsUploadFilingRequest(
                    ticker="AAPL",
                    action="delete",
                    fiscal_year=raw_year,
                    fiscal_period="FY",
                ),
                FinsUploadUsageCode.INVALID_FISCAL_YEAR,
                "财年（fiscal_year）必须是 1000..9999 的整数",
            )
            for raw_year in (0, -1, 999, 10000)
        ),
        *tuple(
            (
                FinsUploadFilingRequest(
                    ticker="AAPL",
                    action="delete",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    filing_date=raw_date,
                ),
                FinsUploadUsageCode.INVALID_FILING_DATE,
                "披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期",
            )
            for raw_date in (
                "",
                " ",
                " 2024-02-29 ",
                "2024-2-29",
                "2023-02-29",
                "2024-13-01",
                "2024/02/29",
            )
        ),
        *tuple(
            (
                FinsUploadFilingRequest(
                    ticker="AAPL",
                    action="delete",
                    fiscal_year=2024,
                    fiscal_period="FY",
                    report_date=raw_date,
                ),
                FinsUploadUsageCode.INVALID_REPORT_DATE,
                "报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期",
            )
            for raw_date in (
                "",
                "\t",
                "2024-02-29 ",
                "2024-2-29",
                "2023-02-29",
                "2024-00-01",
                "2024.02.29",
            )
        ),
    ),
)
def test_filing_calendar_year_static_admission_precedes_all_side_effects(
    tmp_path: Path,
    upload_request: FinsUploadFilingRequest,
    expected_code: FinsUploadUsageCode,
    expected_message: str,
) -> None:
    """非法 calendar/year 必须在 state、operation、runner 与 durable mutation 前失败。

    Args:
        tmp_path: pytest 临时目录。
        upload_request: 当前非法 filing upload request。
        expected_code: 当前字段对应的 typed usage code。
        expected_message: 当前字段的精确业务中立文案。

    Returns:
        无。

    Raises:
        AssertionError: 失败投影、校验顺序或零副作用边界漂移时抛出。
    """

    preflight_workspace = tmp_path / "preflight-workspace"
    before_preflight = _snapshot_runtime_workspace_tree(preflight_workspace)
    with pytest.raises(FinsUploadUsageError) as preflight_exc:
        prevalidate_fins_upload_filing_request_for_workspace(
            upload_request,
            workspace_root=preflight_workspace,
        )
    assert preflight_exc.value.failure.code is expected_code
    assert preflight_exc.value.failure.message == expected_message
    assert _snapshot_runtime_workspace_tree(preflight_workspace) == before_preflight

    runtime_workspace = tmp_path / "runtime-workspace"
    runtime, executor, state_repository, runner = _build_static_admission_guarded_runtime(runtime_workspace)
    before_runtime = _snapshot_runtime_workspace_tree(runtime_workspace)

    with pytest.raises(FinsUploadUsageError) as start_exc:
        runtime.start_upload(upload_request)
    assert start_exc.value.failure.code is expected_code
    assert start_exc.value.failure.message == expected_message

    with pytest.raises(FinsUploadUsageError) as observation_exc:
        runtime.prepare_observed_upload(
            upload_request,
            cancellation_token=_MutableCancellationToken(),
        )
    assert observation_exc.value.failure.code is expected_code
    assert observation_exc.value.failure.message == expected_message
    assert state_repository.calls == []
    assert state_repository.batch_calls == []
    assert executor.operations == []
    assert runner.requests == []
    assert runtime._observations == {}
    assert _snapshot_runtime_workspace_tree(runtime_workspace) == before_runtime
    assert not (runtime_workspace / ".dayu" / "fins_ingestion" / "jobs").exists()
    assert not (runtime_workspace / "portfolio").exists()


@pytest.mark.parametrize("fiscal_year", (1000, 9999))
def test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fiscal_year: int,
) -> None:
    """合法边界年与闰日必须委托共享 owner 并进入 state-aware path。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: shared owner 委托监视夹具。
        fiscal_year: 待验证的四位边界年。

    Returns:
        无。

    Raises:
        AssertionError: 合法值被拒绝、identity 不稳定或 owner 委托漂移时抛出。
    """

    original_year_parser = ingestion_runtime.parse_calendar_year
    original_date_parser = ingestion_runtime.parse_iso_calendar_date
    year_calls: list[int] = []
    date_calls: list[str] = []

    def record_year(value: int) -> int:
        """记录年份 owner 委托并返回其结果。

        Args:
            value: upload static admission 传入的原始年份。

        Returns:
            shared owner 返回的合法四位年份。

        Raises:
            ValueError: shared owner 判定年份非法时抛出。
        """

        year_calls.append(value)
        return original_year_parser(value)

    def record_date(value: str) -> date:
        """记录日期 owner 委托并返回其结果。

        Args:
            value: upload static admission 传入的原始日期文本。

        Returns:
            shared owner 返回的公历日期。

        Raises:
            ValueError: shared owner 判定日期非法时抛出。
        """

        date_calls.append(value)
        return original_date_parser(value)

    monkeypatch.setattr(ingestion_runtime, "parse_calendar_year", record_year)
    monkeypatch.setattr(ingestion_runtime, "parse_iso_calendar_date", record_date)
    request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="delete",
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        filing_date="2024-02-29",
        report_date="2024-03-01",
    )

    first = prevalidate_fins_upload_filing_request_for_workspace(
        request,
        workspace_root=tmp_path / "first",
    )
    second = prevalidate_fins_upload_filing_request_for_workspace(
        request,
        workspace_root=tmp_path / "second",
    )

    assert first.document_id == second.document_id
    assert first.internal_document_id == second.internal_document_id
    assert first.resolved_action == "delete"
    assert first.request is request
    assert year_calls
    assert set(year_calls) == {fiscal_year}
    assert date_calls
    assert set(date_calls) == {"2024-02-29", "2024-03-01"}


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
                requested_file_count=len(raw_request.files),
                stored_file_count=0,
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
            original_name = f"{self.document_id}.md"
            docling_name = f"{self.document_id}_docling.json"
            handle = SourceHandle(
                ticker=raw_request.ticker,
                document_id=self.document_id,
                source_kind=SourceKind.FILING.value,
            )
            original_meta = self.blob_repository.store_file(
                handle,
                original_name,
                io.BytesIO(b"# observed upload fixture"),
                batch=batch,
                content_type="text/markdown",
            )
            docling_meta = self.blob_repository.store_file(
                handle,
                docling_name,
                io.BytesIO(_fixture_docling_json_bytes()),
                batch=batch,
                content_type="application/json",
            )
            self.source_repository.create_source_document(
                SourceDocumentUpsertRequest(
                    ticker=raw_request.ticker,
                    document_id=self.document_id,
                    internal_document_id=self.document_id,
                    form_type="10-K",
                    primary_document=docling_name,
                    meta={
                        "fiscal_year": 2024,
                        "fiscal_period": "FY",
                        "filing_date": "2024-11-01",
                        "report_date": "2024-09-28",
                        "amended": False,
                        "ingest_method": "upload",
                        "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                    },
                    file_entries=_fresh_filing_file_entries(
                        original_meta,
                        docling_meta,
                        original_name=original_name,
                        docling_name=docling_name,
                    ),
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
            requested_file_count=1,
            stored_file_count=1,
            primary_document=f"{self.document_id}_docling.json",
        )


class _UploadRuntimeConverter:
    """runtime production upload 测试用 typed Docling converter。"""

    calls: list[str]
    _failing_stream_names: frozenset[str]

    def __init__(self, *, failing_stream_names: frozenset[str] = frozenset()) -> None:
        """初始化可选择失败文件的确定性 converter。

        Args:
            failing_stream_names: 需要抛出 closed conversion failure 的文件名集合。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls = []
        self._failing_stream_names = failing_stream_names

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
            DoclingConversionError: 当前文件名被配置为确定性失败时抛出。
        """

        del input_bytes, config, cancellation
        self.calls.append(stream_name)
        if stream_name in self._failing_stream_names:
            raise DoclingConversionError(
                DoclingConversionFailureKind.CONVERTER_EXECUTION,
                "Docling conversion execution failed",
                None,
            ) from RuntimeError("private deterministic converter failure")
        data = ('{"name": "' + stream_name + '", "format": "docling"}').encode()
        return DoclingConversionResult(data, len(data), hashlib.sha256(data).hexdigest())


def _inject_upload_runtime_converter(
    default_runtime: DefaultFinsRuntime,
    runtime: ingestion_runtime.FinsIngestionRuntime,
    *,
    converter: DoclingConverter | None = None,
) -> None:
    """通过 public constructor injection 替换测试 upload runner。

    Args:
        default_runtime: 持有共享 repositories 的默认运行时。
        runtime: 待装配 production runner 的 ingestion runtime。
        converter: 可选确定性 converter；省略时创建默认成功 converter。

    Returns:
        无。

    Raises:
        OSError: pipeline 初始化失败时抛出。
    """

    effective_converter = _UploadRuntimeConverter() if converter is None else converter
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
            docling_converter=effective_converter,
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
            docling_converter=effective_converter,
        ),
    )


def _build_direct_upload_test_runtime(
    *,
    workspace_root: Path,
    converter: DoclingConverter,
) -> tuple[DefaultFinsRuntime, ingestion_runtime.FinsIngestionRuntime, _HoldingExecutor]:
    """构造共享 Fins 仓储的 production direct upload 测试边界。

    Args:
        workspace_root: 当前测试的 Fins workspace root。
        converter: 通过 production pipeline constructor 注入的确定性 converter。

    Returns:
        默认运行时、direct ingestion runtime 与 holding executor。

    Raises:
        OSError: 仓储或 pipeline 初始化失败时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(workspace_root, executor=executor)
    _inject_upload_runtime_converter(
        default_runtime,
        ingestion,
        converter=converter,
    )
    return default_runtime, ingestion, executor


def _assert_direct_test_filing_was_not_published(default_runtime: DefaultFinsRuntime) -> None:
    """断言固定 direct test filing 未形成 company/source publication。

    Args:
        default_runtime: 持有待检查 Fins repositories 的默认运行时。

    Returns:
        无。

    Raises:
        AssertionError: company 或 source 已发布时抛出。
    """

    document_id, _internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    with pytest.raises(FileNotFoundError):
        default_runtime.source_repository.get_source_meta(
            "AAPL",
            document_id,
            SourceKind.FILING,
        )
    with pytest.raises(FileNotFoundError):
        default_runtime.company_repository.get_company_meta("AAPL")


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
        requested_file_count=1,
        stored_file_count=1,
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
        accepted_summary=FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="ok",
            requested_file_count=1,
            stored_file_count=1,
        ),
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
        accepted_summary=FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="ok",
            requested_file_count=1,
            stored_file_count=1,
        ),
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
                requested_file_count=1 if status == "ok" else 0,
                stored_file_count=1 if status == "ok" else 0,
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
    original_meta = blob.store_file(
        handle,
        "report.md",
        io.BytesIO(_fixture_markdown().encode("utf-8")),
        batch=batch,
        content_type="text/markdown",
    )
    docling_meta = blob.store_file(
        handle,
        "report_docling.json",
        io.BytesIO(_fixture_docling_json_bytes()),
        batch=batch,
        content_type="application/json",
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document="report_docling.json",
            file_entries=_fresh_filing_file_entries(
                original_meta,
                docling_meta,
                original_name="report.md",
                docling_name="report_docling.json",
            ),
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
            requested_file_count=1,
            stored_file_count=1,
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
    assert record.result_summary["requested_file_count"] == 0
    assert record.result_summary["stored_file_count"] == 0
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
            requested_file_count=1,
            stored_file_count=1,
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
    assert record.result_summary["requested_file_count"] == 1
    assert record.result_summary["stored_file_count"] == 1
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
    assert "requested_file_count" not in progress_events[0].payload
    assert "stored_file_count" not in progress_events[0].payload
    assert progress_events[1].document_id == "aapl-investor-day"
    assert progress_events[1].payload["upload_status"] == "ok"
    assert progress_events[1].payload["file_count"] == 1
    assert "requested_file_count" not in progress_events[1].payload
    assert "stored_file_count" not in progress_events[1].payload


@pytest.mark.asyncio
async def test_direct_upload_filing_success_publishes_fins_assets_without_host_or_legacy_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """direct upload_filing 成功正控只发布 Fins 资产，不创建 Host 或 legacy job 事实。

    Args:
        tmp_path: pytest 临时目录夹具。
        monkeypatch: processor registry spy 注入夹具。

    Returns:
        无。

    Raises:
        AssertionError: direct publication、summary 或 no-artifact 边界漂移时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    converter = _UploadRuntimeConverter()
    default_runtime, ingestion, executor = _build_direct_upload_test_runtime(
        workspace_root=workspace_root,
        converter=converter,
    )
    upload_file = tmp_path / "report.pdf"
    original_bytes = b"deterministic filing bytes"
    upload_file.write_bytes(original_bytes)

    events = await _collect_direct_events(
        ingestion.upload(
            FinsUploadFilingRequest(
                ticker="AAPL",
                action="create",
                files=(upload_file,),
                fiscal_year=2024,
                fiscal_period="FY",
                company_name="Apple Inc.",
            )
        )
    )

    result = events[-1].result
    assert result is not None
    assert result.status is FinsResultStatus.SUCCESS
    details = {detail.label: detail.value for detail in result.details}
    assert details["requested files"] == "1"
    assert details["stored files"] == "1"
    assert "uploaded files" not in details
    assert converter.calls == ["report.pdf"]

    document_id, _internal_document_id = build_sec_filing_ids(
        ticker="AAPL",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
    )
    source_meta = default_runtime.source_repository.get_source_meta(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    source_handle = default_runtime.source_repository.get_source_handle(
        "AAPL",
        document_id,
        SourceKind.FILING,
    )
    published_names = sorted(
        item.uri.rsplit("/", maxsplit=1)[-1] for item in default_runtime.blob_repository.list_files(source_handle)
    )
    original_identity = _build_filing_original_asset_identity(upload_file.resolve(strict=False))
    derived_identity = f"{original_identity}_docling.json"
    assert source_meta["ingest_method"] == "upload"
    assert source_meta["primary_document"] == derived_identity
    assert published_names == sorted((original_identity, derived_identity))
    assert default_runtime.blob_repository.read_file_bytes(source_handle, original_identity) == original_bytes
    assert (
        default_runtime.blob_repository.read_file_bytes(
            source_handle,
            derived_identity,
        )
        == b'{"name": "report.pdf", "format": "docling"}'
    )
    processor_inputs: list[bytes] = []
    original_create = ingestion.processor_registry.create_with_fallback

    def observe_processor_source(
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
        on_fallback: Callable[[type[DocumentProcessor], Exception, int, int], None] | None = None,
    ) -> DocumentProcessor:
        """记录 process_filing 交给 registry 的 exact snapshot primary。

        Args:
            source: snapshot ``get_primary_source()`` 返回的 source。
            form_type: 可选 filing form type。
            media_type: 可选媒体类型。
            on_fallback: 可选 processor fallback 回调。

        Returns:
            真实 registry 创建的 processor。

        Raises:
            OSError: source 无法读取时抛出。
            ValueError: 没有候选 processor 时抛出。
            RuntimeError: 全部候选 processor 创建失败时抛出。
        """

        with source.open() as stream:
            processor_inputs.append(stream.read())
        return original_create(
            source,
            form_type=form_type,
            media_type=media_type,
            on_fallback=on_fallback,
        )

    monkeypatch.setattr(
        ingestion.processor_registry,
        "create_with_fallback",
        observe_processor_source,
    )
    process_status = ingestion._preprocess_one_document(
        ticker="AAPL",
        document_id=document_id,
        source_kind=SourceKind.FILING,
        rebuild_processed=False,
    )

    assert process_status == "processed"
    assert processor_inputs == [b'{"name": "report.pdf", "format": "docling"}']
    assert default_runtime.company_repository.get_company_meta("AAPL").company_name == "Apple Inc."

    job_store = ingestion.job_store
    assert isinstance(job_store, ingestion_runtime.FsFinsIngestionJobStore)
    jobs_dir = job_store.root_dir
    paths = WorkspacePaths(workspace_root=workspace_root)
    assert executor.operations == []
    assert tuple(jobs_dir.glob("*.json")) == ()
    assert tuple(jobs_dir.glob("*.jsonl")) == ()
    assert not paths.host_dir.exists()
    assert not paths.host_sqlite_path.exists()
    assert not paths.artifact_root.exists()
    assert not paths.runtime_lanes_db_path.exists()


@pytest.mark.parametrize(
    (
        "file_name",
        "payload",
        "failing_stream_names",
        "expected_failure_code",
        "expected_converter_calls",
    ),
    (
        ("empty.pdf", b"", frozenset(), "empty_input_file", ()),
        (
            "corrupt.pdf",
            b"corrupt PDF",
            frozenset({"corrupt.pdf"}),
            "docling_converter_execution",
            ("corrupt.pdf",),
        ),
        (
            "corrupt.docx",
            b"corrupt DOCX",
            frozenset({"corrupt.docx"}),
            "docling_converter_execution",
            ("corrupt.docx",),
        ),
    ),
)
@pytest.mark.asyncio
async def test_direct_upload_filing_content_failure_is_typed_and_has_zero_publication(
    tmp_path: Path,
    file_name: str,
    payload: bytes,
    failing_stream_names: frozenset[str],
    expected_failure_code: str,
    expected_converter_calls: tuple[str, ...],
) -> None:
    """direct empty/corrupt filing 必须 typed fail 且不发布 company/source/blob。

    Args:
        tmp_path: pytest 临时目录夹具。
        file_name: 当前输入文件名。
        payload: 当前输入 bytes。
        failing_stream_names: converter 需要确定性拒绝的文件名集合。
        expected_failure_code: direct detail 中的 closed failure code。
        expected_converter_calls: 预期 converter 调用顺序。

    Returns:
        无。

    Raises:
        AssertionError: failure projection、count 或零发布边界漂移时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    converter = _UploadRuntimeConverter(failing_stream_names=failing_stream_names)
    default_runtime, ingestion, executor = _build_direct_upload_test_runtime(
        workspace_root=workspace_root,
        converter=converter,
    )
    upload_file = tmp_path / file_name
    upload_file.write_bytes(payload)

    events = await _collect_direct_events(
        ingestion.upload(
            FinsUploadFilingRequest(
                ticker="AAPL",
                action="create",
                files=(upload_file,),
                fiscal_year=2024,
                fiscal_period="FY",
                company_name="Apple Inc.",
            )
        )
    )

    result = events[-1].result
    assert result is not None
    assert result.status is FinsResultStatus.FAILURE
    details = {detail.label: detail.value for detail in result.details}
    assert details["requested files"] == "1"
    assert details["stored files"] == "0"
    assert details["failure kind"] == "content"
    assert details["failure code"] == expected_failure_code
    assert details["file"] == file_name
    assert "private deterministic converter failure" not in repr(result)
    assert converter.calls == list(expected_converter_calls)
    assert executor.operations == []
    _assert_direct_test_filing_was_not_published(default_runtime)


@pytest.mark.asyncio
async def test_direct_upload_filing_corrupt_primary_fails_without_partial_publication(
    tmp_path: Path,
) -> None:
    """direct filing 的损坏 primary 失败，有效 companion 不得形成 stored fact。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: 单次 primary 转换、count 或原子 publication 边界漂移时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    converter = _UploadRuntimeConverter(failing_stream_names=frozenset({"corrupt.pdf"}))
    default_runtime, ingestion, executor = _build_direct_upload_test_runtime(
        workspace_root=workspace_root,
        converter=converter,
    )
    corrupt_file = tmp_path / "corrupt.pdf"
    valid_file = tmp_path / "valid.docx"
    corrupt_file.write_bytes(b"corrupt filing")
    valid_file.write_bytes(b"valid companion")

    events = await _collect_direct_events(
        ingestion.upload(
            FinsUploadFilingRequest(
                ticker="AAPL",
                action="create",
                files=(corrupt_file, valid_file),
                primary_selectors=(corrupt_file,),
                fiscal_year=2024,
                fiscal_period="FY",
                company_name="Apple Inc.",
            )
        )
    )

    result = events[-1].result
    assert result is not None
    assert result.status is FinsResultStatus.FAILURE
    details = {detail.label: detail.value for detail in result.details}
    assert details["requested files"] == "2"
    assert details["stored files"] == "0"
    assert details["failure code"] == "docling_converter_execution"
    assert details["file"] == "corrupt.pdf"
    assert converter.calls == ["corrupt.pdf"]
    assert executor.operations == []
    _assert_direct_test_filing_was_not_published(default_runtime)


@pytest.mark.asyncio
async def test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text(tmp_path: Path) -> None:
    """direct upload 用户事件不得暴露路径、job id、raw payload 或正文。"""

    workspace_root = tmp_path / "fins-workspace"
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            document_id="aapl-2024-10k",
            status="ok",
            requested_file_count=1,
            stored_file_count=1,
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
    details = {detail.label: detail.value for detail in events[-1].result.details}
    assert details["requested files"] == "1"
    assert details["stored files"] == "1"
    assert "uploaded files" not in details
    assert str(tmp_path) not in event_text
    assert "aapl-10k.pdf" not in event_text
    assert "finsjob_" not in event_text
    assert "raw provider payload" not in event_text
    assert "Annual recurring revenue increased" not in event_text


@pytest.mark.asyncio
async def test_direct_upload_typed_failure_projection_bypasses_string_classifiers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """direct upload 应机械消费 typed reason，不进入异常字符串分类或安全化分支。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: generic string classifier 禁用夹具。

    Returns:
        无。

    Raises:
        AssertionError: typed reason 未直达 direct RESULT 时抛出。
    """

    def fail_classify(
        exc: Exception,
        *,
        operation_kind: FinsOperationKind,
    ) -> FinsErrorKind:
        """若 typed upload 误入 generic classifier 则立即失败。

        Args:
            exc: 意外传入的异常。
            operation_kind: 意外传入的 direct operation。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del exc, operation_kind
        raise AssertionError("typed upload failure 禁止字符串分类")

    def fail_safe_message(
        exc: Exception,
        *,
        error_kind: FinsErrorKind,
    ) -> str:
        """若 typed upload 误入 generic message sanitizer 则立即失败。

        Args:
            exc: 意外传入的异常。
            error_kind: 意外传入的 generic 分类。

        Returns:
            不返回。

        Raises:
            AssertionError: 始终抛出。
        """

        del exc, error_kind
        raise AssertionError("typed upload failure 禁止字符串安全化")

    monkeypatch.setattr(ingestion_runtime, "_classify_direct_error", fail_classify)
    monkeypatch.setattr(ingestion_runtime, "_safe_direct_error_message", fail_safe_message)
    reason = FinsUploadFailureReason(
        kind=FinsUploadFailureKind.CONTENT,
        code=FinsUploadFailureCode.EMPTY_INPUT_FILE,
        message="文件为空，无法上传",
        retry_hint="请提供非空文件后重试",
        file_label="输入文件（文件名已隐藏）",
    )
    runner = _FakeUploadRunner(
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="failed",
            requested_file_count=1,
            stored_file_count=0,
            failure_reason=reason,
        )
    )
    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
        upload_runner=runner,
    )
    upload_file = tmp_path / "private-job_id-notes.pdf"
    upload_file.write_bytes(b"filing")

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

    result = events[-1].result
    assert result is not None
    assert result.status is FinsResultStatus.FAILURE
    assert result.error_message == "文件为空，无法上传"
    details = {detail.label: detail.value for detail in result.details}
    assert details["failure code"] == "empty_input_file"
    assert details["retry hint"] == "请提供非空文件后重试"
    assert details["file"] == "输入文件（文件名已隐藏）"
    assert upload_file.name not in repr(result)


@pytest.mark.asyncio
async def test_alias_conflict_failure_is_identical_across_direct_durable_and_observation(
    tmp_path: Path,
) -> None:
    """alias conflict failure owner 必须同源投影 direct、durable 与 awaiting observation。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 surface 重分类、重写或丢失 exact failure JSON 时抛出。
    """

    reason = fins_upload_failure_from_exception(
        CompanyTickerAliasConflictError(
            alias="MSFT",
            existing_canonical_ticker="MSFT",
            incoming_canonical_ticker="AAPL",
        ),
        file_label=None,
    )
    summary = FinsUploadResultSummary(
        source_kind=SourceKind.MATERIAL,
        status="failed",
        requested_file_count=1,
        stored_file_count=0,
        failure_reason=reason,
    )
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=executor,
        upload_runner=_FakeUploadRunner(summary),
    )
    upload_file = tmp_path / "material.pdf"
    upload_file.write_bytes(b"material")
    request = FinsUploadMaterialRequest(
        ticker="AAPL",
        action="create",
        files=(upload_file,),
        material_name="Deck",
        company_name="Apple Inc.",
        ticker_aliases=("MSFT",),
    )

    direct_events = await _collect_direct_events(runtime.upload(request))
    direct_result = direct_events[-1].result
    assert direct_result is not None
    start = runtime.start_upload(request)
    executor.run_all()
    durable_record = runtime.read_job(start.job_id)
    handle = runtime.prepare_observed_upload(request, _NeverCancelledToken())
    runtime.activate_observation(handle)
    executor.run_all()
    observation = await runtime.poll_observation(handle)

    expected_failure = {
        "kind": "storage",
        "code": "ticker_alias_conflict",
        "message": "股票代码别名已属于当前工作区中的其他公司，请移除冲突别名后重试",
        "retry_hint": "请确认公司的主代码与别名声明后重新上传",
        "file_label": None,
    }
    assert reason.to_json() == expected_failure
    assert durable_record.failure_summary == expected_failure
    assert durable_record.result_summary["failure"] == expected_failure
    assert observation.status is FinsObservationStatus.FAILED
    assert observation.result == direct_result
    assert direct_result.error_message == expected_failure["message"]
    direct_details = {detail.label: detail.value for detail in direct_result.details}
    assert direct_details["failure kind"] == expected_failure["kind"]
    assert direct_details["failure code"] == expected_failure["code"]
    assert direct_details["failure message"] == expected_failure["message"]
    assert direct_details["retry hint"] == expected_failure["retry_hint"]
    public_surfaces = (direct_result, durable_record.result_summary, durable_record.failure_summary, observation)
    assert str(tmp_path) not in repr(public_surfaces)
    assert "company_identity.lock" not in repr(public_surfaces)
    assert "finsjob_" not in repr(observation)


@pytest.mark.asyncio
async def test_direct_upload_without_runner_reports_requested_and_zero_stored_counts(
    tmp_path: Path,
) -> None:
    """direct runner 未装配时必须从请求投影 requested，并保持 stored 为零。

    Args:
        tmp_path: pytest 临时目录夹具。

    Returns:
        无。

    Raises:
        AssertionError: failure 文案或 requested/stored count 语义漂移时抛出。
    """

    ingestion = _build_ingestion_runtime(
        tmp_path / "fins-workspace",
        executor=_HoldingExecutor(),
    )
    events = await _collect_direct_events(
        ingestion.upload(
            FinsUploadMaterialRequest(
                ticker="AAPL",
                files=(Path("first.pdf"), Path("second.pdf")),
            )
        )
    )

    result = events[-1].result
    assert result is not None
    assert result.status is FinsResultStatus.FAILURE
    assert result.error_message == direct_upload_runtime_unavailable_message()
    details = {detail.label: detail.value for detail in result.details}
    assert details["requested files"] == "2"
    assert details["stored files"] == "0"


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
            requested_file_count=1,
            stored_file_count=0,
            failure_reason=fins_upload_failure_from_exception(RuntimeError(), file_label=None),
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
        "file_label": None,
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
                requested_file_count=1 if status == "ok" else 0,
                stored_file_count=1 if status == "ok" else 0,
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
        accepted_summary=FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="ok",
            requested_file_count=1,
            stored_file_count=1,
        ),
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
        accepted_summary=FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="ok",
            requested_file_count=1,
            stored_file_count=1,
        ),
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
                requested_file_count=1 if status == "ok" else 0,
                stored_file_count=1 if status == "ok" else 0,
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
                requested_file_count=1 if status == "ok" else 0,
                stored_file_count=1 if status == "ok" else 0,
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
        requested_file_count=1,
        stored_file_count=1,
    ).to_json_summary()
    failed_summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status="failed",
        requested_file_count=0,
        stored_file_count=0,
        failure_reason=fins_upload_failure_from_exception(RuntimeError(), file_label=None),
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
    original_identity = _build_filing_original_asset_identity(filing_file.resolve(strict=False))
    derived_identity = f"{original_identity}_docling.json"
    assert record.result_summary["primary_document"] == derived_identity
    document_id = str(record.result_summary["document_id"])
    meta = ingestion.source_repository.get_source_meta("AAPL", document_id, SourceKind.FILING)
    assert meta["ingest_method"] == "upload"
    assert meta["primary_document"] == derived_identity
    assert [event.source_event_type for event in progress_events] == [
        "upload.started",
        "upload.completed",
    ]
    assert progress_events[0].payload["source_kind"] == "filing"
    assert progress_events[0].payload["file_count"] == 1
    assert progress_events[1].payload["upload_status"] == "ok"


def test_durable_upload_fresh_unsafe_persists_exact_typed_failure_reason(tmp_path: Path) -> None:
    """异步 job 必须原样持久化 workflow fresh validator 的 typed failure。

    Args:
        tmp_path: 临时 workspace。

    Returns:
        无。

    Raises:
        AssertionError: failure reason 被异常字符串或 generic runtime 改写时抛出。
        OSError: 真实 filesystem fixture 读写失败时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    ingestion = default_runtime.get_ingestion_runtime()
    _inject_upload_runtime_converter(default_runtime, ingestion)
    filing_file = tmp_path / "aapl-fresh-unsafe.pdf"
    filing_file.write_bytes(b"durable fresh unsafe")
    raw_request = FinsUploadFilingRequest(
        ticker="AAPL",
        action="auto",
        files=(filing_file,),
        fiscal_year=2025,
        fiscal_period="Q1",
        company_name="Apple Inc.",
    )
    created = ingestion.start_upload(raw_request)
    created_record = _wait_terminal(ingestion, created.job_id)
    assert created_record.status is FinsIngestionJobStatus.SUCCEEDED
    validated = prevalidate_fins_upload_filing_request_for_workspace(
        raw_request,
        workspace_root=workspace_root,
    )
    locator = default_runtime.source_repository.get_source_document_locator(
        validated.normalized_ticker.canonical,
        validated.document_id,
        SourceKind.FILING,
    )
    (workspace_root / locator / "private-undeclared.bin").write_bytes(b"unsafe")

    failed = ingestion.start_upload(validated)
    failed_record = _wait_terminal(ingestion, failed.job_id)

    expected = fins_upload_source_integrity_unsafe_failure().to_json()
    assert failed_record.status is FinsIngestionJobStatus.FAILED
    assert failed_record.failure_summary == expected
    assert failed_record.result_summary["failure"] == expected
    assert failed_record.result_summary["status"] == "failed"
    assert failed_record.result_summary["stored_file_count"] == 0
    assert "unexpected_runtime" not in json.dumps(failed_record.failure_summary)
    assert "private-undeclared.bin" not in json.dumps(failed_record.failure_summary)


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

    with pytest.raises(FinsUploadUsageError) as aliases_exc:
        runtime.start_upload(FinsUploadFilingRequest(ticker="AAPL", ticker_aliases=too_many_aliases))
    assert aliases_exc.value.failure.code is FinsUploadUsageCode.TOO_MANY_TICKER_ALIASES
    with pytest.raises(FinsUploadUsageError) as material_aliases_exc:
        runtime.start_upload(
            FinsUploadMaterialRequest(
                ticker="AAPL",
                ticker_aliases=too_many_aliases,
            )
        )
    assert material_aliases_exc.value.failure.code is FinsUploadUsageCode.TOO_MANY_TICKER_ALIASES
    with pytest.raises(ValueError, match="requested_file_count"):
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status="ok",
            requested_file_count=-1,
            stored_file_count=0,
        )
    assert executor.operations == []


@pytest.mark.parametrize(
    ("upload_request", "expected_code"),
    (
        (
            FinsUploadMaterialRequest(ticker="Apple Inc."),
            FinsUploadUsageCode.INVALID_TICKER,
        ),
        (
            FinsUploadMaterialRequest(ticker="AAPL", ticker_aliases=("a apl",)),
            FinsUploadUsageCode.INVALID_TICKER_ALIAS,
        ),
    ),
)
def test_material_upload_reuses_ticker_identity_admission_before_job_creation(
    tmp_path: Path,
    upload_request: FinsUploadMaterialRequest,
    expected_code: FinsUploadUsageCode,
) -> None:
    """material 非法 ticker/alias 必须复用 typed usage owner 且不创建 job。

    Args:
        tmp_path: pytest 临时目录。
        upload_request: 当前非法 material request。
        expected_code: 预期 closed usage code。

    Returns:
        无。

    Raises:
        AssertionError: material 绕过共享准入或产生 durable job 时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    executor = _HoldingExecutor()
    runtime = _build_ingestion_runtime(workspace_root, executor=executor)

    with pytest.raises(FinsUploadUsageError) as exc_info:
        runtime.start_upload(upload_request)

    assert exc_info.value.failure.code is expected_code
    assert executor.operations == []
    assert not tuple((workspace_root / ".dayu" / "fins_ingestion" / "jobs").glob("*.json"))


def test_start_upload_projects_real_corrupt_company_meta_before_job_creation(
    tmp_path: Path,
) -> None:
    """真实 malformed CompanyMeta 必须由 start boundary 透出 typed corruption。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: corruption 被归类为参数错误或 durable job 已创建时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    ticker_dir = workspace_root / "portfolio" / "AAPL"
    ticker_dir.mkdir(parents=True)
    (ticker_dir / ".identity.json").write_text(
        json.dumps({"namespace": "ticker", "external_identity": "AAPL"}),
        encoding="utf-8",
    )
    (ticker_dir / "meta.json").write_text("{}", encoding="utf-8")
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_ingestion_runtime()

    with pytest.raises(CompanyTickerIdentityCorruptionError) as exc_info:
        runtime.start_upload(
            FinsUploadFilingRequest(
                ticker="AAPL",
                action="delete",
                fiscal_year=2024,
                fiscal_period="FY",
            )
        )

    assert exc_info.value.kind == "invalid_meta"
    assert not tuple((workspace_root / ".dayu" / "fins_ingestion" / "jobs").glob("*.json"))


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
        requested_file_count=1,
        stored_file_count=1,
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

    stored_file_count = 1 if status == "ok" else 0
    requested_file_count = 1 if status in {"ok", "skipped"} else 0
    pipeline_json: dict[str, JsonValue] = {
        "status": status,
        "stored_file_count": stored_file_count,
    }
    if status == "failed":
        pipeline_json["failure"] = {
            "kind": "runtime",
            "code": "unexpected_runtime",
            "message": "上传执行失败，请检查运行日志后重试",
            "retry_hint": None,
            "file_label": None,
        }
    pipeline_result = FinsUploadPipelineResult.from_pipeline_json(pipeline_json)
    summary = FinsUploadResultSummary(
        source_kind=SourceKind.FILING,
        status=status,
        requested_file_count=requested_file_count,
        stored_file_count=stored_file_count,
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
        FinsUploadPipelineResult.from_pipeline_json({"status": status, "stored_file_count": 0})
    with pytest.raises(ValueError, match="upload status"):
        FinsUploadResultSummary(
            source_kind=SourceKind.FILING,
            status=status,
            requested_file_count=0,
            stored_file_count=0,
        )


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
            requested_file_count=1,
            stored_file_count=1,
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
            requested_file_count=1,
            stored_file_count=1,
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


class _ForbiddenFilingUploadStateRepository:
    """静态 admission 测试中禁止读取的 filing state 仓储。"""

    def __init__(self) -> None:
        """初始化读取记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.calls: list[tuple[str, str]] = []
        self.batch_calls: list[tuple[BatchToken, str]] = []

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """记录越界读取并立即失败。

        Args:
            ticker: 待读取的 canonical ticker。
            document_id: 待读取的 filing 文档 ID。

        Returns:
            不返回。

        Raises:
            AssertionError: 方法被调用时始终抛出。
        """

        self.calls.append((ticker, document_id))
        raise AssertionError("calendar/year static admission 前禁止读取 filing state")

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """记录越界 batch 读取并立即失败。

        Args:
            batch: runtime 请求的 batch capability。
            document_id: runtime 请求的 exact filing 文档 ID。

        Returns:
            不返回。

        Raises:
            AssertionError: 方法被调用时始终抛出。
        """

        self.batch_calls.append((batch, document_id))
        raise AssertionError("calendar/year static admission 前禁止读取 batch filing state")


class _FixedFilingUploadStateRepository:
    """返回显式 typed published state 的 runtime prevalidation fixture。"""

    state: FilingUploadPublishedState
    calls: list[tuple[str, str]]
    batch_calls: list[tuple[BatchToken, str]]

    def __init__(self, state: FilingUploadPublishedState) -> None:
        """初始化固定 state 与调用记录。

        Args:
            state: 已显式构造 classification 的 published state。

        Returns:
            无。

        Raises:
            无。
        """

        self.state = state
        self.calls = []
        self.batch_calls = []

    def read_filing_upload_state(
        self,
        ticker: str,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """返回固定 state，不读取 raw meta 或 filesystem。

        Args:
            ticker: runtime 请求的 canonical ticker。
            document_id: runtime 请求的 exact filing document ID。

        Returns:
            初始化时传入的 typed published state。

        Raises:
            无。
        """

        self.calls.append((ticker, document_id))
        return self.state

    def read_filing_upload_state_in_batch(
        self,
        batch: BatchToken,
        document_id: str,
    ) -> FilingUploadPublishedState:
        """记录 batch 读取并返回同一个固定 state。

        Args:
            batch: runtime 请求的 batch capability。
            document_id: runtime 请求的 exact filing document ID。

        Returns:
            初始化时传入的同一个 typed published state。

        Raises:
            无。
        """

        self.batch_calls.append((batch, document_id))
        return self.state


class _ForbiddenUploadRunner(FinsUploadRunner):
    """静态 admission 测试中禁止调用的 upload runner。"""

    def __init__(self) -> None:
        """初始化 runner 请求记录。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.requests: list[ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest] = []

    def run_upload(
        self,
        request: ValidatedFinsUploadFilingRequest | FinsUploadMaterialRequest,
        *,
        cancellation_checker: FinsJobCancellationChecker,
    ) -> FinsUploadResultSummary:
        """记录越界 runner 调用并立即失败。

        Args:
            request: runtime 传入的已验证请求。
            cancellation_checker: runtime 传入的取消检查器。

        Returns:
            不返回。

        Raises:
            AssertionError: 方法被调用时始终抛出。
        """

        del cancellation_checker
        self.requests.append(request)
        raise AssertionError("calendar/year static admission 前禁止调用 upload runner")


def _snapshot_runtime_workspace_tree(workspace_root: Path) -> tuple[tuple[str, str], ...]:
    """读取 runtime workspace 树的稳定目录/内容快照。

    Args:
        workspace_root: 待观测的 workspace 根目录。

    Returns:
        按相对路径排序的目录标记或文件 SHA-256 元组。

    Raises:
        OSError: workspace 遍历或文件读取失败时抛出。
    """

    if not workspace_root.exists():
        return ()
    entries: list[tuple[str, str]] = []
    for path in sorted(workspace_root.rglob("*")):
        relative_path = path.relative_to(workspace_root).as_posix()
        if path.is_dir():
            entries.append((relative_path, "directory"))
        elif path.is_file():
            entries.append((relative_path, hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(entries)


def _build_static_admission_guarded_runtime(
    workspace_root: Path,
) -> tuple[
    ingestion_runtime.FinsIngestionRuntime,
    _HoldingExecutor,
    _ForbiddenFilingUploadStateRepository,
    _ForbiddenUploadRunner,
]:
    """构造对 state、operation 与 runner 越界调用立即失败的 runtime。

    Args:
        workspace_root: Fins workspace 根目录。

    Returns:
        runtime、延迟执行器、禁止 state 仓储与禁止 runner。

    Raises:
        OSError: 默认 runtime 仓储装配失败时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    state_repository = _ForbiddenFilingUploadStateRepository()
    runner = _ForbiddenUploadRunner()
    runtime = ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=state_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=executor,
        upload_runner=runner,
    )
    return runtime, executor, state_repository, runner


def _build_fixed_state_guarded_runtime(
    workspace_root: Path,
    state: FilingUploadPublishedState,
) -> tuple[
    ingestion_runtime.FinsIngestionRuntime,
    _HoldingExecutor,
    _FixedFilingUploadStateRepository,
    _ForbiddenUploadRunner,
]:
    """构造只允许读取一个 typed state 的 prevalidation runtime。

    Args:
        workspace_root: Fins workspace 根目录。
        state: 当前请求 exact target 的显式 published state。

    Returns:
        runtime、延迟执行器、固定 state 仓储与禁止 runner。

    Raises:
        OSError: 默认 runtime 仓储装配失败时抛出。
    """

    default_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    executor = _HoldingExecutor()
    state_repository = _FixedFilingUploadStateRepository(state)
    runner = _ForbiddenUploadRunner()
    runtime = ingestion_runtime.FinsIngestionRuntime.create(
        batching_repository=default_runtime.batching_repository,
        source_repository=default_runtime.source_repository,
        blob_repository=default_runtime.blob_repository,
        filing_maintenance_repository=default_runtime.filing_maintenance_repository,
        filing_upload_state_repository=state_repository,
        processed_repository=default_runtime.processed_repository,
        processor_registry=default_runtime.processor_registry,
        job_store=default_runtime.ingestion_job_store,
        executor=executor,
        upload_runner=runner,
    )
    return runtime, executor, state_repository, runner


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
            original_name = f"{document_id}.md"
            docling_name = f"{document_id}_docling.json"
            handle = SourceHandle(
                ticker="AAPL",
                document_id=document_id,
                source_kind=SourceKind.FILING.value,
            )
            original_meta = blob_repository.store_file(
                handle,
                original_name,
                io.BytesIO(b"# Unmatched fixture"),
                batch=token,
                content_type="text/markdown",
            )
            docling_meta = blob_repository.store_file(
                handle,
                docling_name,
                io.BytesIO(_fixture_docling_json_bytes()),
                batch=token,
                content_type="application/json",
            )
            source_repository.create_source_document(
                SourceDocumentUpsertRequest(
                    ticker="AAPL",
                    document_id=document_id,
                    internal_document_id=document_id,
                    form_type="10-Q",
                    primary_document=docling_name,
                    meta={
                        "fiscal_year": 2024,
                        "fiscal_period": "Q",
                        "filing_date": "2024-08-01",
                        "report_date": "2024-06-29",
                        "amended": False,
                        "ingest_method": "upload",
                        "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                    },
                    file_entries=_fresh_filing_file_entries(
                        original_meta,
                        docling_meta,
                        original_name=original_name,
                        docling_name=docling_name,
                    ),
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
    stage_company_meta_fixture(
        company_repository,
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ("APPLE",)),
            resolver_version="test",
            updated_at=now_iso8601(),
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
        original_name = "aapl-2024-10k.md"
        docling_name = "aapl-2024-10k_docling.json"
        original_meta = blob_repository.store_file(
            handle,
            original_name,
            io.BytesIO(_fixture_markdown().encode("utf-8")),
            batch=token,
            content_type=content_type,
        )
        docling_meta = blob_repository.store_file(
            handle,
            docling_name,
            io.BytesIO(_fixture_docling_json_bytes()),
            batch=token,
            content_type="application/json",
        )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="aapl-2024-10k",
                internal_document_id="aapl-2024-10k",
                form_type="10-K",
                primary_document=docling_name,
                meta={
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "amended": False,
                    "ingest_method": "upload",
                    "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
                },
                file_entries=_fresh_filing_file_entries(
                    original_meta,
                    docling_meta,
                    original_name=original_name,
                    docling_name=docling_name,
                ),
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


def _fixture_docling_json_bytes() -> bytes:
    """读取共享的完整 DoclingDocument 测试产物。

    Args:
        无。

    Returns:
        可由 production Fins Docling processor 解析的 JSON bytes。

    Raises:
        OSError: fixture 文件读取失败时抛出。
    """

    fixture_path = (
        Path(__file__).parents[1]
        / "tools"
        / "fixtures"
        / "documents"
        / "sample_docling.json"
    )
    return fixture_path.read_bytes()


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
