"""Fins storage 与 read tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import errno
import io
import json
import logging
import os
import pickle
import socket
import time
import traceback
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Final, Literal, cast

import pytest

from tests.fins.company_meta_test_support import stage_company_meta_fixture

import dayu.fins.storage._fs_source_snapshot as source_snapshot_module
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_execution import (
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ProcessBackedToolTarget,
    ProcessBackedToolTargetFactory,
)
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.documents.processors.base import (
    DocumentProcessor,
    SearchHit,
    SectionContent,
    SectionSummary,
    TableContent,
    TableSummary,
    build_search_hit,
    build_section_summary,
)
from dayu.runtime.filelock import RuntimeFileLockToken
from dayu.documents.processors.source import Source
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.domain.document_models import (
    BatchToken,
    CompanyMeta,
    DocumentMeta,
    DocumentSummary,
    DownloadRejectionEntry,
    FileObjectMeta,
    FinsSourceProvider,
    ProcessedCreateRequest,
    RejectedFilingArtifactUpsertRequest,
    SourceDocumentRevision,
    SourceDocumentStateChangeRequest,
    SourceFileEntry,
    SourceDocumentUpsertRequest,
    SourceHandle,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.filing_semantics import FISCAL_PERIODS
from dayu.fins.domain.xbrl_result_contract import XbrlQueryExecutionError
from dayu.fins.domain.tool_models import Citation
from dayu.fins.storage import (
    CompanyTickerIdentityCorruptionError,
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsFilingMaintenanceRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import _FsRepositorySet, build_fs_repository_set
from dayu.fins.storage._fs_storage_core import FsStorageCore
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.fins_limits import FinsToolLimits
from dayu.fins.tools.error_contract import ErrorCode
from dayu.fins.tools.fins_tools import build_fins_read_tool_definitions
from dayu.fins.tools.provider import discover_tools
from dayu.fins.tools.read_runtime import FinsReadRuntime
from dayu.fins.tools.read_runtime_helpers import FinsReadBusinessError, FinsReadCancelledError
from dayu.fins.tools.result_types import (
    financial_statement_result_description,
    xbrl_query_result_description,
)
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    HostEventRef,
    HostToolFactAcceptPort,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptedAck,
    ToolRuntimeHandle,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
    ProcessBackedToolExecutionCapsule,
)
from dayu.host.tooling import (
    FrameworkToolName,
    FrameworkToolPolicyView,
    default_framework_tool_policy_view,
)
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)

_FINS_READ_TOOL_NAMES = (
    "list_documents",
    "get_document_sections",
    "read_section",
    "search_document",
    "list_tables",
    "get_table",
    "get_page_content",
    "get_financial_statement",
    "query_xbrl_facts",
)
_FINANCIAL_HTML_DOCUMENT_ID: Final[str] = "aapl-html-2024-10k"
_FINANCIAL_HTML_PRIMARY_DOCUMENT: Final[str] = "aapl-html-2024-10k.html"
_INCOME_STATEMENT_TYPE: Final[str] = "income"
_AAPL_XBRL_FIXTURE_DIR: Final[Path] = (
    Path(__file__).resolve().parent / "fixtures" / "aapl_xbrl" / "fil_0000320193-24-000123"
)
_AAPL_XBRL_DOCUMENT_ID: Final[str] = "fil_0000320193-24-000123"
_AAPL_XBRL_VERIFIED_CONCEPT: Final[str] = "NetIncomeLoss"
_FORCED_XBRL_MAX_ITEMS: Final[int] = 1
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FINS_WAIT_ADAPTER_PATH = (_REPO_ROOT / "dayu" / "fins" / "ingestion" / "wait_adapter.py").resolve(strict=False)
_FINS_DEFAULT_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.host", "dayu.service", "dayu.ui")
_FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS = ("dayu.engine", "dayu.service", "dayu.ui")
_HOST_GOVERNANCE_CANCEL_REASON: Final[str] = (
    "run_id=run-secret session_id=session-secret correlation_id=correlation-secret "
    "payload_ref=payload-secret digest=sha256-secret cancellation_token=token-secret"
)
_HOST_GOVERNANCE_FORBIDDEN_TERMS: Final[tuple[str, ...]] = (
    "run_id",
    "session_id",
    "correlation_id",
    "payload_ref",
    "digest",
    "cancellation_token",
    "run-secret",
    "session-secret",
    "correlation-secret",
    "payload-secret",
    "sha256-secret",
    "token-secret",
)
_CompleteSourceFailureCase = Literal[
    "missing_meta",
    "empty_files",
    "duplicate_files",
    "dangling_file",
    "missing_primary",
    "invalid_ingest_method",
    "invalid_provider",
    "false_completion",
    "ticker_mismatch",
    "document_mismatch",
    "source_kind_mismatch",
    "uri_mismatch",
    "size_mismatch",
    "sha_mismatch",
    "symlink_file_escape",
    "filename_escape",
    "unmanifested_file",
    "missing_manifest",
    "dangling_manifest",
    "manifest_projection_mismatch",
    "duplicate_manifest_identity",
    "manifest_ticker_mismatch",
]


def _fresh_upload_file_entry(
    file_meta: FileObjectMeta,
    *,
    name: str,
    source: Literal["original", "docling"],
    original_filename: str,
    derived_from: str | None = None,
) -> dict[str, JsonValue]:
    """把已 staged blob 投影为 UF-FIX07 fresh filing file entry。

    Args:
        file_meta: blob repository 返回的 physical file meta。
        name: storage-owned exact asset identity。
        source: original 或 Docling role。
        original_filename: 用户输入 basename。
        derived_from: Docling 对应的 exact original identity。

    Returns:
        可直接写入 ``SourceDocumentUpsertRequest.file_entries`` 的严格条目。

    Raises:
        ValueError: Docling 缺少 derived identity，或 original 错带 derived identity 时抛出。
    """

    if source == "docling" and derived_from is None:
        raise ValueError("Docling fixture 必须携带 derived_from")
    if source == "original" and derived_from is not None:
        raise ValueError("original fixture 不得携带 derived_from")
    entry: dict[str, JsonValue] = {
        "name": name,
        "uri": file_meta.uri,
        "etag": file_meta.etag,
        "last_modified": file_meta.last_modified,
        "size": file_meta.size,
        "content_type": file_meta.content_type,
        "sha256": file_meta.sha256,
        "source": source,
        "original_filename": original_filename,
    }
    if derived_from is not None:
        entry["derived_from"] = derived_from
    return entry


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

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


class _ManualCancellationToken:
    """测试用手动取消 token。"""

    def __init__(self, *, cancel_reason: str = "test cancellation") -> None:
        """初始化未取消状态。

        Args:
            cancel_reason: 标记取消后返回的测试取消原因。

        Returns:
            无。
        """

        self._cancelled = False
        self._cancel_reason = cancel_reason

    def cancel(self) -> None:
        """标记 token 已取消。

        Returns:
            无。

        Raises:
            无。
        """

        self._cancelled = True

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        Returns:
            已调用 ``cancel`` 时返回 ``True``。
        """

        return self._cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            已取消时返回构造期传入的测试原因；否则返回 None。
        """

        if self._cancelled:
            return self._cancel_reason
        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            测试 token 不记录时间，始终返回 None。
        """

        return None


class _SearchCancellingProcessor:
    """测试用搜索时触发取消的处理器。"""

    def __init__(self, token: _ManualCancellationToken) -> None:
        """初始化处理器。

        Args:
            token: 搜索命中后要置为取消的 token。

        Returns:
            无。
        """

        self._token = token
        self.search_calls: list[str] = []

    @classmethod
    def get_parser_version(cls) -> str:
        """返回测试 parser 版本。

        Returns:
            parser 版本字符串。
        """

        return "test-search-cancelling"

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> bool:
        """返回是否支持来源。

        Args:
            source: 文档来源。
            form_type: 文档类型。
            media_type: 媒体类型。

        Returns:
            始终支持。
        """

        del source, form_type, media_type
        return True

    def list_sections(self) -> list[SectionSummary]:
        """返回测试章节列表。

        Returns:
            章节摘要列表。
        """

        return [
            build_section_summary(
                ref="s1",
                title="Business",
                level=1,
                parent_ref=None,
                preview="Annual recurring revenue",
            )
        ]

    def list_tables(self) -> list[TableSummary]:
        """返回测试表格列表。

        Returns:
            空列表。
        """

        return []

    def read_section(self, ref: str) -> SectionContent:
        """读取章节正文。

        Args:
            ref: 章节引用。

        Returns:
            不返回。

        Raises:
            AssertionError: 本测试不应调用章节读取。
        """

        raise AssertionError(f"read_section should not be called: {ref}")

    def read_table(self, table_ref: str) -> TableContent:
        """读取表格。

        Args:
            table_ref: 表格引用。

        Returns:
            不返回。

        Raises:
            AssertionError: 本测试不应调用表格读取。
        """

        raise AssertionError(f"read_table should not be called: {table_ref}")

    def get_section_title(self, ref: str) -> str | None:
        """读取章节标题。

        Args:
            ref: 章节引用。

        Returns:
            测试章节标题。
        """

        if ref == "s1":
            return "Business"
        return None

    def search(self, query: str, within_ref: str | None = None) -> list[SearchHit]:
        """记录搜索并触发取消。

        Args:
            query: 搜索词。
            within_ref: 可选章节范围。

        Returns:
            单条搜索命中。
        """

        del within_ref
        self.search_calls.append(query)
        self._token.cancel()
        return [
            build_search_hit(
                section_ref="s1",
                section_title="Business",
                snippet="Annual recurring revenue",
            )
        ]

    def get_full_text(self) -> str:
        """返回全文。

        Returns:
            测试全文。
        """

        return "Annual recurring revenue"

    def get_full_text_with_table_markers(self) -> str:
        """返回带表格标记的全文。

        Returns:
            测试全文。
        """

        return "Annual recurring revenue"


class _SearchIndexFailingProcessor(_SearchCancellingProcessor):
    """测试用 search index list stage 失败 processor。"""

    def list_sections(self) -> list[SectionSummary]:
        """在 index readiness 阶段抛出 sentinel。

        Args:
            无。

        Returns:
            不返回。

        Raises:
            RuntimeError: 始终抛出测试 sentinel。
        """

        raise RuntimeError("search index list sentinel")


class _ReadCancellingProcessor(_SearchCancellingProcessor):
    """测试用创建后取消且禁止读取章节的处理器。"""

    def __init__(self, token: _ManualCancellationToken) -> None:
        """初始化处理器。

        Args:
            token: processor 创建后要取消的 token。

        Returns:
            无。
        """

        super().__init__(token)
        self.read_section_calls = 0

    def read_section(self, ref: str) -> SectionContent:
        """记录章节读取调用。

        Args:
            ref: 章节引用。

        Returns:
            不返回。

        Raises:
            AssertionError: 取消应发生在 processor 读取前。
        """

        self.read_section_calls += 1
        raise AssertionError(f"read_section should not be called: {ref}")


class _ParentTitleLookupCancellingProcessor(_SearchCancellingProcessor):
    """测试用父标题查询期间触发取消的处理器。"""

    def __init__(self, token: _ManualCancellationToken) -> None:
        """初始化处理器。

        Args:
            token: 父标题查询时要置为取消的 token。

        Returns:
            无。
        """

        super().__init__(token)
        self.get_section_title_calls = 0

    def read_section(self, ref: str) -> SectionContent:
        """返回带父章节引用的章节正文。

        Args:
            ref: 章节引用。

        Returns:
            章节正文；额外携带 parent_ref 以覆盖父标题查询路径。
        """

        return cast(
            SectionContent,
            {
                "ref": ref,
                "title": "Services Margin",
                "content": "Services margin improved.",
                "tables": [],
                "word_count": 3,
                "contains_full_text": False,
                "parent_ref": "s1",
            },
        )

    def get_section_title(self, ref: str) -> str | None:
        """查询父章节标题并触发取消。

        Args:
            ref: 父章节引用。

        Returns:
            父章节标题。
        """

        self.get_section_title_calls += 1
        self._token.cancel()
        if ref == "s1":
            return "Business"
        return None


class _XbrlFactsProcessor(_SearchCancellingProcessor):
    """测试用 XBRL facts 处理器。"""

    def __init__(self, token: _ManualCancellationToken) -> None:
        """初始化查询计数。

        Args:
            token: XBRL 查询返回后要置为取消的 token。

        Returns:
            无。
        """

        super().__init__(token)
        self.query_calls = 0

    def query_xbrl_facts(
        self,
        *,
        concepts: list[str],
        statement_type: str | None,
        period_end: str | None,
        fiscal_year: int | None,
        fiscal_period: str | None,
        min_value: float | None,
        max_value: float | None,
    ) -> Mapping[str, JsonValue]:
        """返回多条 facts 供取消检查截断过滤。

        Args:
            concepts: 查询概念列表。
            statement_type: 报表类型过滤。
            period_end: 期末日期过滤。
            fiscal_year: 财年过滤。
            fiscal_period: 财期过滤。
            min_value: 最小值过滤。
            max_value: 最大值过滤。

        Returns:
            XBRL 查询载荷。
        """

        del statement_type, period_end, fiscal_year, fiscal_period, min_value, max_value
        self.query_calls += 1
        self._token.cancel()
        concept_values: list[JsonValue] = [concept for concept in concepts]
        facts: list[JsonValue] = [
            {"concept": "Revenue", "value": 100},
            {"concept": "Revenue", "value": 101},
            {"concept": "Revenue", "value": 102},
        ]
        return {
            "query_params": {"concepts": concept_values},
            "facts": facts,
            "data_quality": "xbrl",
        }


class _XbrlFailureReadRuntime:
    """process-backed target 测试使用的 XBRL 失败 read runtime。"""

    def query_xbrl_facts(
        self,
        *,
        ticker: str,
        document_id: str,
        concepts: list[str] | None = None,
        statement_type: str | None = None,
        period_end: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        min_value: float | None = None,
        max_value: float | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """模拟 read runtime 已把 all-failed 映射为 typed business failure。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            concepts: concept 列表。
            statement_type: 可选报表类型。
            period_end: 可选期末日期。
            fiscal_year: 可选财年。
            fiscal_period: 可选财期。
            min_value: 可选最小值。
            max_value: 可选最大值。
            cancellation_token: 取消观察令牌。

        Returns:
            本函数不会返回。

        Raises:
            FinsReadBusinessError: 始终以 ``xbrl_query_failed`` 抛出。
        """

        del (
            ticker,
            document_id,
            statement_type,
            period_end,
            fiscal_year,
            fiscal_period,
            min_value,
            max_value,
            cancellation_token,
        )
        failed_concepts = tuple(concepts or ["Revenue"])
        raise FinsReadBusinessError(
            ErrorCode.XBRL_QUERY_FAILED,
            "XBRL 查询执行失败，当前结果不可作为零命中使用。",
            hint="请稍后重试。",
        ) from XbrlQueryExecutionError(failed_concepts)


class _XbrlFailureDefaultRuntime:
    """只返回 XBRL 失败 read runtime 的测试 DefaultFinsRuntime 替身。"""

    def get_read_runtime(self, *, processor_cache_max_entries: int) -> _XbrlFailureReadRuntime:
        """返回 XBRL 失败 read runtime。

        Args:
            processor_cache_max_entries: processor cache 容量。

        Returns:
            XBRL 失败 read runtime。

        Raises:
            无。
        """

        del processor_cache_max_entries
        return _XbrlFailureReadRuntime()

    def close(self) -> None:
        """关闭测试 runtime。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """


def _create_xbrl_failure_default_runtime(*, workspace_root: Path) -> _XbrlFailureDefaultRuntime:
    """构造 process target 测试所需的失败 runtime。

    Args:
        workspace_root: Fins workspace root。

    Returns:
        失败 runtime 替身。

    Raises:
        无。
    """

    del workspace_root
    return _XbrlFailureDefaultRuntime()


class _CountingSourceRepository(FsSourceDocumentRepository):
    """统计 source meta 与 snapshot 读取次数的测试仓储。"""

    def __init__(self, workspace_root: Path, *, repository_set: _FsRepositorySet) -> None:
        """初始化计数仓储。

        Args:
            workspace_root: Fins workspace 根目录。
            repository_set: 文件系统仓储 core 集合。

        Returns:
            无。

        Raises:
            OSError: 底层仓储初始化失败时抛出。
        """

        super().__init__(workspace_root, repository_set=repository_set)
        self.get_source_meta_calls = 0
        self.snapshot_read_calls = 0

    def get_source_meta(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind,
    ) -> DocumentMeta:
        """统计并读取源文档 meta。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 来源类型。

        Returns:
            源文档 meta。

        Raises:
            FileNotFoundError: source meta 不存在时抛出。
            ValueError: source meta 非法时抛出。
        """

        self.get_source_meta_calls += 1
        return super().get_source_meta(ticker, document_id, source_kind)

    def read_source_snapshot(
        self,
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool,
    ) -> SourceSnapshotProtocol:
        """统计并执行真实 snapshot 读取。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            source_kind: 可选 source kind。
            materialize_files: 是否物化业务文件。

        Returns:
            storage-owned snapshot。

        Raises:
            FileNotFoundError: source 不存在时抛出。
            ValueError: snapshot 非法时抛出。
            OSError: snapshot I/O 失败时抛出。
        """

        self.snapshot_read_calls += 1
        return super().read_source_snapshot(
            ticker,
            document_id,
            source_kind,
            materialize_files=materialize_files,
        )


class _ConcurrentReadRuntimeProbe:
    """记录同一 provider read runtime 业务体并发进入情况。"""

    def __init__(self) -> None:
        """初始化并发探针。

        Returns:
            无。
        """

        self._active_guard = Lock()
        self.entered = Event()
        self._active_count = 0
        self.max_active_count = 0

    def list_documents(
        self,
        *,
        ticker: str,
        document_types: list[str] | None = None,
        fiscal_years: list[int] | None = None,
        fiscal_periods: list[str] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """测试用 list_documents 业务体。

        Args:
            ticker: 股票代码。
            document_types: 文档类型过滤。
            fiscal_years: 财年过滤。
            fiscal_periods: 财期过滤。
            cancellation_token: Host 取消令牌。

        Returns:
            最小文档列表载荷。

        Raises:
            无。
        """

        del ticker, document_types, fiscal_years, fiscal_periods, cancellation_token
        self._enter_business()
        return {"documents": [], "matched": 0, "total": 0}

    def get_document_sections(
        self,
        *,
        ticker: str,
        document_id: str,
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """测试用 get_document_sections 业务体。

        Args:
            ticker: 股票代码。
            document_id: 文档 ID。
            cancellation_token: Host 取消令牌。

        Returns:
            最小章节列表载荷。

        Raises:
            无。
        """

        del ticker, document_id, cancellation_token
        self._enter_business()
        return {"sections": [], "ticker": "AAPL", "document_id": "aapl-2024-10k"}

    def _enter_business(self) -> None:
        """记录进入业务体的并发计数。

        Returns:
            无。

        Raises:
            无。
        """

        with self._active_guard:
            self._active_count += 1
            self.max_active_count = max(self.max_active_count, self._active_count)
            self.entered.set()
        time.sleep(0.05)
        with self._active_guard:
            self._active_count -= 1


class _AcceptingPort(HostToolFactAcceptPort):
    """测试用 Host accept barrier。"""

    def __init__(self) -> None:
        """初始化记录列表。

        Returns:
            无。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self,
        candidate: ToolFactAcceptCandidate,
    ) -> ToolFactAcceptResult:
        """接受工具事实候选。

        Args:
            candidate: ToolRuntime 构造的工具事实候选。

        Returns:
            accepted ack。
        """

        self.candidates.append(candidate)
        requested_ref = HostEventRef(
            event_id=f"event-requested-{len(self.candidates)}",
            event_sequence=len(self.candidates) * 2 - 1,
        )
        result_ref = HostEventRef(
            event_id=f"event-result-{len(self.candidates)}",
            event_sequence=len(self.candidates) * 2,
        )
        return ToolFactAcceptedAck(
            accepted_event_refs=(requested_ref, result_ref),
            tool_fact_id=f"tool-fact-{len(self.candidates)}",
            tool_call_requested_event_ref=requested_ref,
            tool_call_governed_event_ref=None,
            tool_result_event_ref=result_ref,
            result_payload_ref=None,
            result_digest=f"sha256:{'2' * 64}",
            reuse_prior_event_refs=(),
            diagnostic_refs=(),
            idempotency_record_ref=f"idempotency-{len(self.candidates)}",
        )


def test_storage_repositories_list_and_read_fixture_documents(tmp_path: Path) -> None:
    """仓储协议和文件系统实现应能列出并读取确定性 fixture 文档。"""

    workspace_root = _build_fins_workspace(tmp_path)
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)

    document_ids = source_repository.list_source_document_ids("AAPL", SourceKind.FILING)
    handle = source_repository.get_source_handle("AAPL", "aapl-2024-10k", SourceKind.FILING)
    content = blob_repository.read_file_bytes(handle, "aapl-2024-10k.md").decode("utf-8")
    source = source_repository.get_primary_source("AAPL", "aapl-2024-10k", SourceKind.FILING)

    assert document_ids == ["aapl-2024-10k"]
    assert "Annual recurring revenue increased" in content
    assert source.media_type == "text/markdown"


def test_published_revision_is_persisted_and_changes_only_with_source_publication(
    tmp_path: Path,
) -> None:
    """revision 应由 source mutation 自动产生并跨 repository 实例持久化。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: revision 未持久化或同一次 source publication 未换 token 时抛出。
    """

    workspace_root = tmp_path / "persisted-revision"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    create_batch = batching.begin_batch("AAPL")
    _create_source_revision_document(repository, blob_repository, batch=create_batch)
    batching.commit_batch(create_batch)

    first_revision = _read_snapshot_revision(repository, "AAPL", "revision-doc", SourceKind.FILING)
    reopened_repository = FsSourceDocumentRepository(workspace_root)
    assert (
        _read_snapshot_revision(
            reopened_repository,
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
        )
        == first_revision
    )

    unchanged_business_meta = repository.get_source_meta(
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
    )
    replace_batch = batching.begin_batch("AAPL")
    repository.replace_source_meta(
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
        unchanged_business_meta,
        batch=replace_batch,
    )
    batching.commit_batch(replace_batch)

    second_revision = _read_snapshot_revision(repository, "AAPL", "revision-doc", SourceKind.FILING)
    assert second_revision != first_revision
    assert (
        _read_snapshot_revision(
            FsSourceDocumentRepository(workspace_root),
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
        )
        == second_revision
    )


def test_source_document_revision_accepts_nonempty_opaque_token_and_rejects_empty() -> None:
    """typed revision 只承诺非空 opaque token 与 exact equality。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: revision 冻结 grammar、保留旧字段或接受空 token 时抛出。
    """

    opaque_token = "任意 opaque token / spaces : punctuation"
    revision = SourceDocumentRevision(token=opaque_token)

    assert tuple(field.name for field in fields(SourceDocumentRevision)) == ("token",)
    assert revision == SourceDocumentRevision(token=opaque_token)
    assert revision != SourceDocumentRevision(token=f"{opaque_token}!")
    with pytest.raises(ValueError, match="不能为空"):
        SourceDocumentRevision(token="")


def test_rollback_and_non_source_batch_preserve_published_revision(tmp_path: Path) -> None:
    """rollback 与 company-only publication 不得改变 source revision。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 未发布 source token 泄漏或 non-source batch 改写 token 时抛出。
    """

    workspace_root = tmp_path / "revision-preservation"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    create_batch = batching.begin_batch("AAPL")
    _create_source_revision_document(repository, blob_repository, batch=create_batch)
    batching.commit_batch(create_batch)
    published_revision = _read_snapshot_revision(
        repository,
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
    )

    rollback_batch = batching.begin_batch("AAPL")
    repository.replace_source_meta(
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
        repository.get_source_meta("AAPL", "revision-doc", SourceKind.FILING),
        batch=rollback_batch,
    )
    batching.rollback_batch(rollback_batch)
    assert (
        _read_snapshot_revision(
            repository,
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
        )
        == published_revision
    )

    company_batch = batching.begin_batch("AAPL")
    stage_company_meta_fixture(
        company_repository,
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version="snapshot-test",
            updated_at=now_iso8601(),
        ),
        batch=company_batch,
    )
    batching.commit_batch(company_batch)
    assert (
        _read_snapshot_revision(
            repository,
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
        )
        == published_revision
    )


def test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision(
    tmp_path: Path,
) -> None:
    """light/full snapshot 的全部 descriptor 与临时文件必须来自同一 revision。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: snapshot 字段混版、暴露 published path 或 close 后仍可读时抛出。
    """

    workspace_root = tmp_path / "snapshot-descriptor"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    create_batch = batching.begin_batch("AAPL")
    _create_source_revision_document(repository, blob_repository, batch=create_batch)
    batching.commit_batch(create_batch)

    light = repository.read_source_snapshot(
        "AAPL",
        "revision-doc",
        materialize_files=False,
    )
    full = repository.read_source_snapshot(
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
        materialize_files=True,
    )
    primary_source = full.get_primary_source()
    exhibit_source = full.get_source("exhibit.html")
    primary_path = primary_source.materialize()
    snapshot_root = primary_path.parent
    try:
        assert light.ticker == full.ticker == "AAPL"
        assert light.document_id == full.document_id == "revision-doc"
        assert light.source_kind == full.source_kind == SourceKind.FILING
        assert light.revision == full.revision
        assert light.provenance == full.provenance
        assert light.files == full.files
        assert light.primary_filename == full.primary_filename == "primary.html"
        assert tuple(item.name for item in full.files) == ("primary.html", "exhibit.html")
        assert full.source_meta["source_provider"] == "sec_edgar"
        assert all("revision" not in field_name for field_name in full.source_meta)
        assert primary_path.read_bytes() == b"p" * 100
        assert exhibit_source.materialize().read_bytes() == b"e" * 50
        assert workspace_root not in primary_path.parents
        with pytest.raises(RuntimeError, match="未物化"):
            light.get_primary_source()
    finally:
        light.close()
        full.close()
    assert not snapshot_root.exists()
    with pytest.raises(RuntimeError, match="已关闭"):
        primary_source.open()
    with pytest.raises(RuntimeError, match="已关闭"):
        _ = full.source_meta
    full.close()


def test_snapshot_is_not_found_and_has_no_token_or_resource_after_source_delete_or_reset(
    tmp_path: Path,
) -> None:
    """逻辑删除与 physical reset 后 snapshot public boundary 都应返回 not found。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 已删除/reset source 仍返回 revision 或临时资源时抛出。
    """

    workspace_root = tmp_path / "snapshot-delete-reset"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    create_batch = batching.begin_batch("AAPL")
    _create_source_revision_document(repository, blob_repository, batch=create_batch)
    batching.commit_batch(create_batch)
    request = SourceDocumentStateChangeRequest(
        ticker="AAPL",
        document_id="revision-doc",
        source_kind=SourceKind.FILING.value,
    )

    delete_batch = batching.begin_batch("AAPL")
    repository.delete_source_document(request, batch=delete_batch)
    batching.commit_batch(delete_batch)
    with pytest.raises(FileNotFoundError, match="已删除"):
        repository.read_source_snapshot(
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
            materialize_files=True,
        )

    restore_batch = batching.begin_batch("AAPL")
    repository.restore_source_document(request, batch=restore_batch)
    batching.commit_batch(restore_batch)
    restored = repository.read_source_snapshot(
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
        materialize_files=False,
    )
    restored.close()
    reset_batch = batching.begin_batch("AAPL")
    repository.reset_source_document(
        "AAPL",
        "revision-doc",
        SourceKind.FILING,
        batch=reset_batch,
    )
    batching.commit_batch(reset_batch)
    with pytest.raises(FileNotFoundError, match="不存在"):
        repository.read_source_snapshot(
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
            materialize_files=False,
        )


def test_snapshot_explicit_source_kind_ignores_other_kind_with_same_document_id(
    tmp_path: Path,
) -> None:
    """显式 kind 的 post-check 不得把另一 namespace 合法共存误判为变化。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 显式 kind 误报 consistency failure 或缺省 kind 未拒绝歧义时抛出。
    """

    workspace_root = tmp_path / "snapshot-source-kind"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    for source_kind, filename, payload in (
        (SourceKind.FILING, "filing.html", b"filing-version"),
        (SourceKind.MATERIAL, "material.html", b"material-version"),
    ):
        handle = SourceHandle(
            ticker="AAPL",
            document_id="shared-document",
            source_kind=source_kind.value,
        )
        file_meta = blob_repository.store_file(
            handle,
            filename,
            io.BytesIO(payload),
            batch=batch,
            content_type="text/html",
        )
        original_name = f"original-{filename}"
        original_meta = (
            blob_repository.store_file(
                handle,
                original_name,
                io.BytesIO(b"original filing version"),
                batch=batch,
                content_type="text/html",
            )
            if source_kind is SourceKind.FILING
            else None
        )
        repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="shared-document",
                internal_document_id=f"{source_kind.value}-shared-document",
                form_type="10-K" if source_kind is SourceKind.FILING else "EX-99",
                primary_document=filename,
                meta={
                    "ingest_method": "upload",
                    "source_provider": "user_upload",
                },
                files=[file_meta] if original_meta is None else [],
                file_entries=(
                    None
                    if original_meta is None
                    else [
                        _fresh_upload_file_entry(
                            original_meta,
                            name=original_name,
                            source="original",
                            original_filename=filename,
                        ),
                        _fresh_upload_file_entry(
                            file_meta,
                            name=filename,
                            source="docling",
                            original_filename=filename,
                            derived_from=original_name,
                        ),
                    ]
                ),
            ),
            source_kind,
            batch=batch,
        )
    batching.commit_batch(batch)

    for source_kind, expected_payload in (
        (SourceKind.FILING, b"filing-version"),
        (SourceKind.MATERIAL, b"material-version"),
    ):
        snapshot = repository.read_source_snapshot(
            "AAPL",
            "shared-document",
            source_kind,
            materialize_files=True,
        )
        try:
            with snapshot.get_primary_source().open() as stream:
                assert stream.read() == expected_payload
        finally:
            snapshot.close()
    with pytest.raises(ValueError, match="同时存在"):
        repository.read_source_snapshot(
            "AAPL",
            "shared-document",
            materialize_files=False,
        )


def test_document_summary_decode_rejects_invalid_fiscal_period_and_quality() -> None:
    """验证文档摘要 decode 在 domain 边界拒绝非法财期与质量。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    valid_summary = {
        "document_id": "fil_0001",
        "internal_document_id": "0001",
        "source_kind": "filing",
        "form_type": "10-K",
        "fiscal_period": "FY",
        "quality": "full",
    }
    assert DocumentSummary.from_dict(valid_summary).fiscal_period == "FY"

    invalid_period = dict(valid_summary)
    invalid_period["fiscal_period"] = "Q5"
    with pytest.raises(ValueError, match="fiscal_period 非法"):
        DocumentSummary.from_dict(invalid_period)

    invalid_quality = dict(valid_summary)
    invalid_quality["quality"] = "xbrl"
    with pytest.raises(ValueError, match="quality 非法"):
        DocumentSummary.from_dict(invalid_quality)


def test_source_repository_projects_source_document_provenance(tmp_path: Path) -> None:
    """source repository 应从 meta 投影 provider 与 ingest method 真源。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: provenance 投影与 source meta 不一致时抛出。
    """

    workspace_root = tmp_path / "fins-provenance-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batches = {ticker: batching_repository.begin_batch(ticker) for ticker in ("AAPL", "600519", "0700")}

    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["AAPL"],
        ticker="AAPL",
        document_id="fil_sec",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.SEC_EDGAR.to_storage_value(),
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["600519"],
        ticker="600519",
        document_id="fil_cninfo",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.CNINFO.to_storage_value(),
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["0700"],
        ticker="0700",
        document_id="fil_hkexnews",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.HKEXNEWS.to_storage_value(),
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["AAPL"],
        ticker="AAPL",
        document_id="upload_10k",
        source_kind=SourceKind.FILING,
        ingest_method="upload",
        source_provider=FinsSourceProvider.USER_UPLOAD.to_storage_value(),
    )
    for batch in batches.values():
        batching_repository.commit_batch(batch)

    assert (
        source_repository.get_source_document_provenance(
            "AAPL",
            "fil_sec",
            SourceKind.FILING,
        ).source_provider
        is FinsSourceProvider.SEC_EDGAR
    )
    assert (
        source_repository.get_source_document_provenance(
            "600519",
            "fil_cninfo",
            SourceKind.FILING,
        ).source_provider
        is FinsSourceProvider.CNINFO
    )
    assert (
        source_repository.get_source_document_provenance(
            "0700",
            "fil_hkexnews",
            SourceKind.FILING,
        ).source_provider
        is FinsSourceProvider.HKEXNEWS
    )
    assert (
        source_repository.get_source_document_provenance(
            "AAPL",
            "upload_10k",
            SourceKind.FILING,
        ).source_provider
        is FinsSourceProvider.USER_UPLOAD
    )


def test_source_repository_requires_typed_provenance_and_owns_completion(tmp_path: Path) -> None:
    """final source 在 owner boundary 要求 typed provenance并固定完成态为真。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 非法 provenance 未被拒绝或 completion 未固定为真时抛出。
    """

    workspace_root = tmp_path / "fins-provenance-boundary-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)

    invalid_batch = batching_repository.begin_batch("AAPL")
    with pytest.raises(KeyError, match="source_provider"):
        _create_source_document_for_provenance(
            source_repository=source_repository,
            blob_repository=blob_repository,
            batch=invalid_batch,
            ticker="AAPL",
            document_id="missing_provider",
            source_kind=SourceKind.FILING,
            ingest_method="download",
            source_provider=None,
        )
    with pytest.raises(ValueError, match="source_provider 非法"):
        _create_source_document_for_provenance(
            source_repository=source_repository,
            blob_repository=blob_repository,
            batch=invalid_batch,
            ticker="AAPL",
            document_id="invalid_provider",
            source_kind=SourceKind.FILING,
            ingest_method="download",
            source_provider="unknown_provider",
        )
    batching_repository.rollback_batch(invalid_batch)

    valid_batch = batching_repository.begin_batch("AAPL")
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=valid_batch,
        ticker="AAPL",
        document_id="complete_source",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.SEC_EDGAR.to_storage_value(),
    )
    batching_repository.commit_batch(valid_batch)
    meta = source_repository.get_source_meta("AAPL", "complete_source", SourceKind.FILING)
    assert meta["ingest_complete"] is True
    assert meta["source_kind"] == SourceKind.FILING.value


def test_blob_first_staging_remains_unpublished_until_complete_source_commit(tmp_path: Path) -> None:
    """SourceHandle 可先写 blob，但 published read 只在完整 source commit 后可见。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: blob 在完整 source commit 前可见或 commit 后不可见时抛出。
    """

    workspace_root = tmp_path / "fins-blob-first-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    handle = SourceHandle(
        ticker="AAPL",
        document_id="fil_blob_first",
        source_kind=SourceKind.FILING.value,
    )
    file_meta = blob_repository.store_file(
        handle,
        "filing.htm",
        io.BytesIO(b"payload"),
        batch=batch,
        content_type="text/html",
    )

    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "fil_blob_first", SourceKind.FILING)
    with pytest.raises(FileNotFoundError):
        blob_repository.read_file_bytes(handle, "filing.htm")
    assert source_repository.list_source_document_ids("AAPL", SourceKind.FILING) == []

    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="fil_blob_first",
            internal_document_id="fil_blob_first",
            form_type="10-K",
            primary_document="filing.htm",
            files=[file_meta],
            meta={
                "ingest_method": "download",
                "source_provider": "sec_edgar",
                "source_fingerprint": "fingerprint-v1",
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching_repository.commit_batch(batch)

    completed_meta = source_repository.get_source_meta("AAPL", "fil_blob_first", SourceKind.FILING)
    provenance = source_repository.get_source_document_provenance(
        "AAPL",
        "fil_blob_first",
        SourceKind.FILING,
        meta=completed_meta,
    )
    manifest = json.loads(repository_set.core._filing_manifest_path_for_read("AAPL").read_text(encoding="utf-8"))
    assert completed_meta["primary_document"] == "filing.htm"
    assert completed_meta["files"][0]["uri"] == file_meta.uri
    assert provenance.ingest_complete is True
    assert provenance.source_provider is FinsSourceProvider.SEC_EDGAR
    assert manifest["documents"][0]["source_provider"] == "sec_edgar"
    assert manifest["documents"][0]["ingest_complete"] is True
    assert blob_repository.read_file_bytes(handle, "filing.htm") == b"payload"


@pytest.mark.parametrize("has_published_old", (False, True))
def test_invalid_primary_never_projects_first_file_and_commit_preserves_published_state(
    tmp_path: Path,
    has_published_old: bool,
) -> None:
    """错误 primary 不得猜第一文件，commit 必须消费 token 并保留 old/absent。

    Args:
        tmp_path: pytest 临时目录。
        has_published_old: 是否先发布一个完整旧 source。

    Returns:
        无。

    Raises:
        AssertionError: 错误 primary 被投影或非法 transaction 改变 published state 时抛出。
    """

    workspace_root = tmp_path / ("with-old" if has_published_old else "without-old")
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)

    if has_published_old:
        old_batch = batching_repository.begin_batch("AAPL")
        _create_source_document_for_provenance(
            source_repository=source_repository,
            blob_repository=blob_repository,
            batch=old_batch,
            ticker="AAPL",
            document_id="old_source",
            source_kind=SourceKind.FILING,
            ingest_method="upload",
            source_provider="user_upload",
        )
        batching_repository.commit_batch(old_batch)

    invalid_batch = batching_repository.begin_batch("AAPL")
    invalid_handle = SourceHandle("AAPL", "invalid_primary", SourceKind.FILING.value)
    first_file = blob_repository.store_file(
        invalid_handle,
        "first.htm",
        io.BytesIO(b"first"),
        batch=invalid_batch,
    )
    second_file = blob_repository.store_file(
        invalid_handle,
        "second.htm",
        io.BytesIO(b"second"),
        batch=invalid_batch,
    )
    projected_handle = source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="invalid_primary",
            internal_document_id="invalid_primary",
            form_type="10-K",
            primary_document="missing.htm",
            meta={
                "ingest_method": "download",
                "source_provider": "sec_edgar",
            },
            files=[first_file, second_file],
        ),
        SourceKind.FILING,
        batch=invalid_batch,
    )

    assert projected_handle.primary_file_uri is None
    with pytest.raises(
        ValueError,
        match="filing source publication 不满足 complete canonical manifest contract",
    ):
        batching_repository.commit_batch(invalid_batch)
    with pytest.raises(ValueError, match="未在当前 storage core 登记"):
        batching_repository.rollback_batch(invalid_batch)

    expected_ids = ["old_source"] if has_published_old else []
    assert source_repository.list_source_document_ids("AAPL", SourceKind.FILING) == expected_ids
    if has_published_old:
        old_handle = source_repository.get_source_handle("AAPL", "old_source", SourceKind.FILING)
        assert blob_repository.read_file_bytes(old_handle, "old_source.txt") == b"old_source"
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "invalid_primary", SourceKind.FILING)
    with pytest.raises(FileNotFoundError):
        blob_repository.read_file_bytes(invalid_handle, "first.htm")


def test_final_source_rejects_false_completion_without_publication(tmp_path: Path) -> None:
    """producer 显式 false completion 必须在 source owner boundary fail closed。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: false completion 被接受或 published tree 被改写时抛出。
    """

    workspace_root = tmp_path / "fins-false-completion-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    handle = SourceHandle("AAPL", "false_completion", SourceKind.FILING.value)
    file_meta = blob_repository.store_file(
        handle,
        "report.htm",
        io.BytesIO(b"payload"),
        batch=batch,
    )
    with pytest.raises(ValueError, match="ingest_complete 必须为 true"):
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id="false_completion",
                internal_document_id="false_completion",
                primary_document="report.htm",
                meta={
                    "ingest_method": "download",
                    "source_provider": "sec_edgar",
                    "ingest_complete": False,
                },
                files=[file_meta],
            ),
            SourceKind.FILING,
            batch=batch,
        )
    batching_repository.rollback_batch(batch)
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "false_completion", SourceKind.FILING)


def test_complete_filing_and_material_commit_share_one_source_truth(tmp_path: Path) -> None:
    """filing/material commit 后 meta、blob、primary、provenance 与 manifest 必须同源。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 source kind 的完成态投影不同源时抛出。
    """

    workspace_root = tmp_path / "complete-source-kinds-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    for document_id, source_kind in (
        ("fil_complete", SourceKind.FILING),
        ("mat_complete", SourceKind.MATERIAL),
    ):
        _create_source_document_for_provenance(
            source_repository=source_repository,
            blob_repository=blob_repository,
            batch=batch,
            ticker="AAPL",
            document_id=document_id,
            source_kind=source_kind,
            ingest_method="upload",
            source_provider="user_upload",
        )
    batching_repository.commit_batch(batch)

    for document_id, source_kind in (
        ("fil_complete", SourceKind.FILING),
        ("mat_complete", SourceKind.MATERIAL),
    ):
        handle = source_repository.get_source_handle("AAPL", document_id, source_kind)
        meta = source_repository.get_source_meta("AAPL", document_id, source_kind)
        primary = source_repository.get_primary_file("AAPL", document_id, source_kind)
        provenance = source_repository.get_source_document_provenance(
            "AAPL",
            document_id,
            source_kind,
            meta=meta,
        )
        raw_files = meta["files"]
        assert isinstance(raw_files, list)
        primary_name = meta["primary_document"]
        assert isinstance(primary_name, str)
        primary_items = [
            item
            for item in raw_files
            if isinstance(item, dict) and item.get("name") == primary_name
        ]
        assert len(primary_items) == 1
        assert primary.uri == primary_items[0]["uri"]
        assert blob_repository.read_file_bytes(handle, f"{document_id}.txt") == document_id.encode()
        assert provenance.source_provider is FinsSourceProvider.USER_UPLOAD
        assert provenance.ingest_complete is True

    filing_manifest = json.loads(repository_set.core._filing_manifest_path_for_read("AAPL").read_text(encoding="utf-8"))
    material_manifest = json.loads(
        repository_set.core._material_manifest_path_for_read("AAPL").read_text(encoding="utf-8")
    )
    assert filing_manifest["documents"][0]["source_provider"] == "user_upload"
    assert filing_manifest["documents"][0]["ingest_method"] == "upload"
    assert material_manifest["documents"][0]["source_provider"] == "user_upload"
    assert material_manifest["documents"][0]["ingest_method"] == "upload"


@pytest.mark.parametrize(
    "failure_case",
    (
        "missing_meta",
        "empty_files",
        "duplicate_files",
        "dangling_file",
        "missing_primary",
        "invalid_ingest_method",
        "invalid_provider",
        "false_completion",
        "ticker_mismatch",
        "document_mismatch",
        "source_kind_mismatch",
        "uri_mismatch",
        "size_mismatch",
        "sha_mismatch",
        "symlink_file_escape",
        "filename_escape",
        "unmanifested_file",
        "missing_manifest",
        "dangling_manifest",
        "manifest_projection_mismatch",
        "duplicate_manifest_identity",
        "manifest_ticker_mismatch",
    ),
)
def test_complete_source_validator_consumes_token_and_preserves_old(
    tmp_path: Path,
    failure_case: _CompleteSourceFailureCase,
) -> None:
    """validator 每个 failure grid 都必须在 swap 前失败、消费 token并保留 old。

    Args:
        tmp_path: pytest 临时目录。
        failure_case: 当前注入的单一完整性破坏类型。

    Returns:
        无。

    Raises:
        AssertionError: 非法 staged tree 被发布、token 未消费或 old 改变时抛出。
    """

    workspace_root = tmp_path / failure_case
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    old_batch = batching_repository.begin_batch("AAPL")
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=old_batch,
        ticker="AAPL",
        document_id="old_source",
        source_kind=SourceKind.FILING,
        ingest_method="upload",
        source_provider="user_upload",
    )
    batching_repository.commit_batch(old_batch)

    invalid_batch = batching_repository.begin_batch("AAPL")
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=invalid_batch,
        ticker="AAPL",
        document_id="new_source",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider="sec_edgar",
    )
    _corrupt_staged_complete_source(
        repository_set.core,
        failure_case=failure_case,
    )

    with pytest.raises(ValueError):
        batching_repository.commit_batch(invalid_batch)
    with pytest.raises(ValueError, match="未在当前 storage core 登记"):
        batching_repository.rollback_batch(invalid_batch)
    assert source_repository.list_source_document_ids("AAPL", SourceKind.FILING) == ["old_source"]
    old_handle = source_repository.get_source_handle("AAPL", "old_source", SourceKind.FILING)
    assert blob_repository.read_file_bytes(old_handle, "old_source.txt") == b"old_source"
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "new_source", SourceKind.FILING)


def test_blob_only_commit_failure_keeps_new_source_absent(tmp_path: Path) -> None:
    """old-absent transaction 只有 blob 没有 final meta 时 commit 必须失败且保持 absent。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: blob-only transaction 被发布或留下可见 source 时抛出。
    """

    workspace_root = tmp_path / "blob-only-absent-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    handle = SourceHandle("AAPL", "blob_only", SourceKind.FILING.value)
    blob_repository.store_file(
        handle,
        "blob_only.txt",
        io.BytesIO(b"blob-only"),
        batch=batch,
    )

    with pytest.raises(
        ValueError,
        match="filing source publication 不满足 complete canonical manifest contract",
    ):
        batching_repository.commit_batch(batch)
    with pytest.raises(FileNotFoundError):
        source_repository.get_source_meta("AAPL", "blob_only", SourceKind.FILING)
    with pytest.raises(FileNotFoundError):
        blob_repository.read_file_bytes(handle, "blob_only.txt")


def test_download_rejection_registry_roundtrips_typed_entries(tmp_path: Path) -> None:
    """下载拒绝注册表应通过 typed entry 读写并持久化 document_id。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: maintenance registry roundtrip 丢失业务事实时抛出。
    """

    workspace_root = tmp_path / "fins-download-rejection-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    repository = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    entry = DownloadRejectionEntry(
        document_id="fil_0000000000-25-000101",
        reason="6k_filtered",
        category="EXCLUDE_NON_QUARTERLY",
        form_type="6-K",
        filing_date="2025-01-02",
        download_version="sec-download-v1",
    )

    batch = batching.begin_batch("AAPL")
    repository.save_download_rejection_registry(
        "AAPL",
        {entry.document_id: entry},
        batch=batch,
    )
    batching.commit_batch(batch)
    loaded = repository.load_download_rejection_registry("AAPL")
    raw_path = repository_set.core._download_rejections_path_for_read("AAPL")
    raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))

    assert loaded == {entry.document_id: entry}
    assert raw_payload[entry.document_id] == entry.to_dict()


def test_download_rejection_registry_fails_closed_on_malformed_entry(tmp_path: Path) -> None:
    """下载拒绝注册表坏条目不得被静默跳过或字符串化。"""

    workspace_root = tmp_path / "fins-download-rejection-invalid-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    repository = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    state = repository_set.core._resolve_active_batch(batch, "AAPL")
    raw_path = repository_set.core._download_rejections_path("AAPL", state)
    raw_path.write_text(
        json.dumps(
            {
                "fil_0000000000-25-000101": {
                    "document_id": "fil_0000000000-25-000101",
                    "reason": "6k_filtered",
                    "category": "EXCLUDE_NON_QUARTERLY",
                    "form_type": "6-K",
                    "filing_date": 20250102,
                    "download_version": "sec-download-v1",
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    batching.commit_batch(batch)

    with pytest.raises(ValueError, match="filing_date 必须为字符串"):
        repository.load_download_rejection_registry("AAPL")


def test_download_rejection_registry_rejects_mismatched_storage_key(tmp_path: Path) -> None:
    """下载拒绝注册表保存时必须拒绝 key 与 entry document_id 冲突。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 冲突 identity 未被 storage owner 拒绝时抛出。
    """

    workspace_root = tmp_path / "fins-download-rejection-key-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    repository = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    entry = DownloadRejectionEntry(
        document_id="fil_0000000000-25-000101",
        reason="6k_filtered",
        category="EXCLUDE_NON_QUARTERLY",
        form_type="6-K",
        filing_date="2025-01-02",
        download_version="sec-download-v1",
    )

    batch = batching.begin_batch("AAPL")
    try:
        with pytest.raises(ValueError, match="document_id 不一致"):
            repository.save_download_rejection_registry(
                "AAPL",
                {"fil_other": entry},
                batch=batch,
            )
    finally:
        batching.rollback_batch(batch)


def test_canonical_ticker_and_opaque_document_identity_round_trip_all_storage_namespaces(
    tmp_path: Path,
) -> None:
    """canonical ticker 与 opaque document identity 应跨各仓储 namespace 往返。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: ticker 布局或 document identity 往返语义不一致时抛出。
    """

    workspace_root = tmp_path / "fins-document-id-owner-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    filing_repository = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    document_id = "fil_../季度\\C:报告.."
    source_request = SourceDocumentUpsertRequest(
        ticker=ticker,
        document_id=document_id,
        internal_document_id=document_id,
        form_type="10-K",
        primary_document="filing.htm",
        meta={
            "ingest_method": "download",
            "source_provider": "sec_edgar",
            "source_fingerprint": "fingerprint-v1",
            "company_id": "0000320193",
            "ingest_complete": True,
        },
    )
    processed_request = ProcessedCreateRequest(
        ticker=ticker,
        document_id=document_id,
        internal_document_id=document_id,
        source_kind=SourceKind.FILING.value,
        form_type="10-K",
        meta={},
        sections=[],
        tables=[],
    )
    batch = batching_repository.begin_batch(ticker)
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    file_meta = blob_repository.store_file(
        handle,
        "filing.htm",
        io.BytesIO(b"opaque payload"),
        batch=batch,
    )
    source_request = SourceDocumentUpsertRequest(
        ticker=source_request.ticker,
        document_id=source_request.document_id,
        internal_document_id=source_request.internal_document_id,
        form_type=source_request.form_type,
        primary_document=source_request.primary_document,
        files=[file_meta],
        meta=source_request.meta,
    )
    source_repository.create_source_document(source_request, SourceKind.FILING, batch=batch)
    processed_repository.create_processed(processed_request, batch=batch)
    rejected_meta = filing_repository.store_rejected_filing_file(
        ticker,
        document_id,
        "rejected.htm",
        io.BytesIO(b"rejected payload"),
        batch=batch,
    )
    filing_repository.upsert_rejected_filing_artifact(
        RejectedFilingArtifactUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            accession_number="opaque-accession",
            company_id="opaque-company",
            form_type="10-K",
            filing_date="2025-01-02",
            report_date="2024-12-31",
            primary_document="rejected.htm",
            selected_primary_document="rejected.htm",
            rejection_reason="policy",
            rejection_category="test",
            classification_version="v1",
            source_fingerprint="opaque-fingerprint",
            files=[
                SourceFileEntry(
                    name="rejected.htm",
                    uri=rejected_meta.uri,
                    size=rejected_meta.size,
                    content_type=rejected_meta.content_type,
                    sha256=rejected_meta.sha256,
                )
            ],
        ),
        batch=batch,
    )
    batching_repository.commit_batch(batch)

    assert source_repository.list_source_document_ids(ticker, SourceKind.FILING) == [document_id]
    assert source_repository.get_source_meta(ticker, document_id, SourceKind.FILING)["ticker"] == ticker
    assert blob_repository.read_file_bytes(handle, "filing.htm") == b"opaque payload"
    assert processed_repository.get_processed_meta(ticker, document_id)["document_id"] == document_id
    assert filing_repository.list_rejected_filing_artifacts(ticker)[0].document_id == document_id
    assert (
        filing_repository.read_rejected_filing_file_bytes(
            ticker,
            document_id,
            "rejected.htm",
        )
        == b"rejected payload"
    )
    assert rejected_meta.uri.startswith("local://")
    assert repository_set.core._target_ticker_dir(ticker) == (workspace_root / "portfolio" / ticker)
    assert document_id not in rejected_meta.uri


def test_opaque_document_identity_round_trips_path_shaped_values(
    tmp_path: Path,
) -> None:
    """document identity 的 Unicode、分隔符、drive 与 dot 值应保持 exact。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: document identity 被路径解释、归一化或丢失时抛出。
    """

    workspace_root = tmp_path / "opaque-identity-variants"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    processed = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    document_ids = ("文档/层级", "文档\\层级", "C:文档", ".", "..")
    batch = batching.begin_batch(ticker)
    for document_id in document_ids:
        processed.create_processed(
            ProcessedCreateRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=document_id,
                source_kind=SourceKind.MATERIAL.value,
            ),
            batch=batch,
        )
    batching.commit_batch(batch)

    for document_id in document_ids:
        assert processed.get_processed_meta(ticker, document_id)["document_id"] == document_id
    published_ticker_names = {entry.name for entry in repository_set.core.portfolio_root.iterdir()}
    processed_names = {
        entry.name
        for entry in (repository_set.core._target_ticker_dir(ticker) / "processed").iterdir()
        if entry.is_dir()
    }
    assert published_ticker_names == {ticker}
    assert len(processed_names) == len(document_ids)
    assert all(document_id not in processed_names for document_id in document_ids)


@pytest.mark.parametrize(
    "ticker",
    ("aapl", "aapl.us", "../AAPL", "AAPL/../MSFT", "Apple Inc."),
)
def test_storage_rejects_noncanonical_ticker_identity(
    tmp_path: Path,
    ticker: str,
) -> None:
    """storage mutation boundary 应拒绝非 canonical 或路径形态 ticker。

    Args:
        tmp_path: pytest 临时目录。
        ticker: 非 canonical ticker 输入。

    Returns:
        无。

    Raises:
        AssertionError: storage 静默归一化或接受非法 ticker 时抛出。
    """

    batching = FsBatchingRepository(tmp_path)

    with pytest.raises(ValueError, match="canonical ticker"):
        batching.begin_batch(ticker)


def test_identity_mapping_detects_collision_corruption_and_business_meta_mismatch(
    tmp_path: Path,
) -> None:
    """descriptor owner 应拒绝 locator collision、descriptor 损坏与业务 meta 冲突。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 identity 一致性破坏未 fail closed 时抛出。
    """

    collision_root = tmp_path / "collision"
    collision_set = build_fs_repository_set(workspace_root=collision_root)
    collision_batches = FsBatchingRepository(collision_root, repository_set=collision_set)
    original_batch = collision_batches.begin_batch("AAPL")
    collision_batches.commit_batch(original_batch)
    original_dir = collision_set.core._target_ticker_dir("AAPL")
    collision_dir = collision_set.core._target_ticker_dir("MSFT")
    original_dir.rename(collision_dir)
    with pytest.raises(CompanyTickerIdentityCorruptionError) as collision_error:
        collision_batches.begin_batch("MSFT")
    assert collision_error.value.kind == "invalid_descriptor"

    corrupt_root = tmp_path / "corrupt"
    corrupt_set = build_fs_repository_set(workspace_root=corrupt_root)
    corrupt_batches = FsBatchingRepository(corrupt_root, repository_set=corrupt_set)
    corrupt_batch = corrupt_batches.begin_batch("AAPL")
    corrupt_batches.commit_batch(corrupt_batch)
    corrupt_dir = corrupt_set.core._target_ticker_dir("AAPL")
    descriptor_path = next(
        path for path in corrupt_dir.iterdir() if path.name.startswith(".") and path.suffix == ".json"
    )
    descriptor_path.write_text("{}", encoding="utf-8")
    with pytest.raises(CompanyTickerIdentityCorruptionError) as descriptor_error:
        corrupt_batches.begin_batch("AAPL")
    assert descriptor_error.value.kind == "invalid_descriptor"

    mismatch_root = tmp_path / "business-mismatch"
    mismatch_set = build_fs_repository_set(workspace_root=mismatch_root)
    mismatch_batches = FsBatchingRepository(mismatch_root, repository_set=mismatch_set)
    company = FsCompanyMetaRepository(mismatch_root, repository_set=mismatch_set)
    mismatch_batch = mismatch_batches.begin_batch("AAPL")
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="company-aapl",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version="test",
            updated_at=now_iso8601(),
        ),
        batch=mismatch_batch,
    )
    mismatch_batches.commit_batch(mismatch_batch)
    meta_path = mismatch_set.core._company_meta_path_for_read("AAPL")
    meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
    assert isinstance(meta_payload, dict)
    meta_payload["ticker"] = "MSFT"
    meta_path.write_text(json.dumps(meta_payload), encoding="utf-8")
    with pytest.raises(CompanyTickerIdentityCorruptionError) as mismatch_error:
        company.get_company_meta("AAPL")
    assert mismatch_error.value.kind == "identity_mismatch"


def test_company_inventory_projects_canonical_ticker_and_hides_invalid_candidate(
    tmp_path: Path,
) -> None:
    """company inventory 应投影 canonical ticker 且不泄漏非法目录候选名。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: inventory 未投影 ticker 或泄漏非法目录候选名时抛出。
    """

    workspace_root = tmp_path / "company-inventory"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    batch = batching.begin_batch("AAPL")
    batching.commit_batch(batch)
    assert repository_set.core._target_ticker_dir("AAPL") == (workspace_root / "portfolio" / "AAPL")
    corrupt_key = "corrupt-private-candidate"
    (repository_set.core.portfolio_root / corrupt_key).mkdir()

    inventory = company.scan_company_meta_inventory()

    assert any(entry.ticker == "AAPL" and entry.status == "missing_meta" for entry in inventory)
    assert any(entry.ticker is None and entry.status == "invalid_meta" for entry in inventory)
    serialized = json.dumps(
        [{"ticker": entry.ticker, "status": entry.status, "detail": entry.detail} for entry in inventory],
        ensure_ascii=False,
    )
    assert "AAPL" in serialized
    assert corrupt_key not in serialized


def test_lock_only_company_inventory_has_no_business_ticker_without_descriptor(
    tmp_path: Path,
) -> None:
    """lock-only candidate 缺少 descriptor 时应保留 typed status 且不投影 ticker。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: lock stem 被误作有效 ticker 或 detail 泄漏 locator 时抛出。
    """

    workspace_root = tmp_path / "lock-only-inventory"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    batch = batching.begin_batch(ticker)
    private_key = repository_set.core._ticker_lock_path(ticker).name.removesuffix(".lock")
    try:
        inventory = company.scan_company_meta_inventory()
    finally:
        batching.rollback_batch(batch)

    unresolved = [entry for entry in inventory if entry.status == "invalid_meta"]
    assert unresolved
    assert all(entry.ticker is None for entry in unresolved)
    assert all(private_key not in entry.detail for entry in unresolved)


def test_public_storage_errors_never_expose_internal_locator_or_workspace_path(
    tmp_path: Path,
) -> None:
    """public storage exception 只应包含业务 identity，不得泄漏 private path/key。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一公开异常包含 internal locator 或绝对工作区路径时抛出。
    """

    workspace_root = tmp_path / "storage-error-redaction"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    processed = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    maintenance = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    document_id = "fil_缺失/错误\\.."
    batch = batching.begin_batch(ticker)
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="opaque-company",
            company_name="Opaque Company",
            ticker_identity=build_company_ticker_identity(ticker, ()),
            resolver_version="test",
            updated_at=now_iso8601(),
        ),
        batch=batch,
    )
    batching.commit_batch(batch)
    document_dir = repository_set.core._processed_dir_for_read(ticker, document_id)
    private_locators = (document_dir.name,)

    with pytest.raises(FileNotFoundError) as source_error:
        source.get_source_meta(ticker, document_id, SourceKind.FILING)
    with pytest.raises(FileNotFoundError) as processed_error:
        processed.get_processed_meta(ticker, document_id)
    with pytest.raises(FileNotFoundError) as blob_error:
        blob.read_file_bytes(
            SourceHandle(
                ticker=ticker,
                document_id=document_id,
                source_kind=SourceKind.FILING.value,
            ),
            "missing.htm",
        )
    with pytest.raises(FileNotFoundError) as rejected_error:
        maintenance.read_rejected_filing_file_bytes(
            ticker,
            document_id,
            "missing.htm",
        )
    company_meta_path = repository_set.core._company_meta_path_for_read(ticker)
    company_meta_path.write_text("{", encoding="utf-8")
    with pytest.raises(CompanyTickerIdentityCorruptionError) as company_error:
        company.get_company_meta(ticker)
    assert company_error.value.kind == "invalid_meta"

    errors = (
        source_error.value,
        processed_error.value,
        blob_error.value,
        rejected_error.value,
        company_error.value,
    )
    for error in errors:
        message = str(error)
        assert str(workspace_root) not in message
        assert all(locator not in message for locator in private_locators)


def test_public_storage_os_errors_are_path_free_across_read_and_inventory_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """company/source/processed/rejected/list 的 pathful OSError 必须在 storage owner 内投影。

    本测试先尝试真实 mode-based permission failure；若当前运行身份
    可绕过 mode 位（例如 root），则在同一 public boundary 注入等价
    pathful ``PermissionError``。真实 socket I/O failure 另由 blob 用例无条件覆盖。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 异常类别、errno、cause 或 non-leak contract 回退时抛出。
    """

    workspace_root = tmp_path / "storage-os-error-boundaries"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    processed = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    maintenance = FsFilingMaintenanceRepository(
        workspace_root,
        repository_set=repository_set,
    )
    ticker = "AAPL"
    document_id = "fil_权限/文档\\.."
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    batch = batching.begin_batch(ticker)
    stage_company_meta_fixture(
        company,
        CompanyMeta(
            company_id="permission-company",
            company_name="Permission Company",
            ticker_identity=build_company_ticker_identity(ticker, ()),
            resolver_version="test",
            updated_at=now_iso8601(),
        ),
        batch=batch,
    )
    source_file_meta = blob.store_file(
        handle,
        "filing.htm",
        io.BytesIO(b"source payload"),
        batch=batch,
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document="filing.htm",
            files=[source_file_meta],
            meta={
                "ingest_method": "download",
                "source_provider": "sec_edgar",
                "source_fingerprint": "permission-source",
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )
    processed.create_processed(
        ProcessedCreateRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            source_kind=SourceKind.FILING.value,
            form_type="10-K",
            sections=[],
            tables=[],
        ),
        batch=batch,
    )
    rejected_file_meta = maintenance.store_rejected_filing_file(
        ticker,
        document_id,
        "rejected.htm",
        io.BytesIO(b"rejected payload"),
        batch=batch,
    )
    maintenance.upsert_rejected_filing_artifact(
        RejectedFilingArtifactUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            accession_number="permission-accession",
            company_id="permission-company",
            form_type="10-K",
            filing_date="2025-01-02",
            report_date="2024-12-31",
            primary_document="rejected.htm",
            selected_primary_document="rejected.htm",
            rejection_reason="policy",
            rejection_category="test",
            classification_version="v1",
            source_fingerprint="permission-rejected",
            files=[
                SourceFileEntry(
                    name="rejected.htm",
                    uri=rejected_file_meta.uri,
                    size=rejected_file_meta.size,
                    content_type=rejected_file_meta.content_type,
                    sha256=rejected_file_meta.sha256,
                )
            ],
        ),
        batch=batch,
    )
    batching.commit_batch(batch)

    core = repository_set.core
    target_dir = core._target_ticker_dir(ticker)
    source_dir = core._source_meta_path_for_read(
        ticker,
        document_id,
        SourceKind.FILING,
    ).parent
    processed_dir = core._processed_dir_for_read(ticker, document_id)
    rejected_dir = core._rejected_filing_meta_path_for_read(ticker, document_id).parent
    private_locators = (
        source_dir.name,
        processed_dir.name,
        rejected_dir.name,
        core._ticker_lock_path(ticker).name,
        core._publication_lock_path(ticker).name,
    )
    permission_cases: tuple[tuple[Path, Callable[[], str]], ...] = (
        (
            core._company_meta_path_for_read(ticker),
            lambda: str(company.get_company_meta(ticker)),
        ),
        (
            core._source_meta_path_for_read(ticker, document_id, SourceKind.FILING),
            lambda: str(source.get_source_meta(ticker, document_id, SourceKind.FILING)),
        ),
        (
            core._processed_meta_path_for_read(ticker, document_id),
            lambda: str(processed.get_processed_meta(ticker, document_id)),
        ),
        (
            core._rejected_filing_meta_path_for_read(ticker, document_id),
            lambda: str(maintenance.get_rejected_filing_artifact(ticker, document_id)),
        ),
    )
    original_read_text = Path.read_text
    for protected_path, operation in permission_cases:
        original_mode = protected_path.stat().st_mode & 0o777
        protected_path.chmod(0)
        permission_is_enforced = False
        try:
            try:
                protected_path.read_text(encoding="utf-8")
            except PermissionError:
                permission_is_enforced = True

            if permission_is_enforced:
                with pytest.raises(PermissionError) as exc_info:
                    operation()
            else:

                def _deny_protected_read(
                    path: Path,
                    encoding: str | None = None,
                    errors: str | None = None,
                ) -> str:
                    """root-like 平台上仅对目标文件注入 pathful permission failure。

                    Args:
                        path: 待读取路径。
                        encoding: 文本编码。
                        errors: 解码错误策略。

                    Returns:
                        非目标文件的原始文本。

                    Raises:
                        PermissionError: 目标文件始终抛出携路径异常。
                    """

                    if path == protected_path:
                        raise PermissionError(
                            errno.EACCES,
                            "permission denied",
                            str(path),
                        )
                    return original_read_text(path, encoding=encoding, errors=errors)

                with monkeypatch.context() as patch_context:
                    patch_context.setattr(Path, "read_text", _deny_protected_read)
                    with pytest.raises(PermissionError) as exc_info:
                        operation()
            _assert_path_free_storage_os_error(
                exc_info.value,
                expected_errno=errno.EACCES,
                workspace_root=workspace_root,
                private_locators=private_locators,
            )
        finally:
            protected_path.chmod(original_mode)

    filing_root = source_dir.parent
    original_mode = filing_root.stat().st_mode & 0o777
    filing_root.chmod(0)
    try:
        try:
            list(filing_root.iterdir())
            permission_is_enforced = False
        except PermissionError:
            permission_is_enforced = True
        if permission_is_enforced:
            with pytest.raises(PermissionError) as list_error:
                source.list_source_document_ids(ticker, SourceKind.FILING)
        else:
            original_iterdir = Path.iterdir

            def _deny_filing_enumeration(path: Path) -> Iterator[Path]:
                """root-like 平台上仅对 filing root 注入 pathful enumeration failure。

                Args:
                    path: 待枚举目录。

                Returns:
                    非目标目录的原始 iterator。

                Raises:
                    PermissionError: filing root 始终抛出携路径异常。
                """

                if path == filing_root:
                    raise PermissionError(
                        errno.EACCES,
                        "permission denied",
                        str(path),
                    )
                return original_iterdir(path)

            with monkeypatch.context() as patch_context:
                patch_context.setattr(Path, "iterdir", _deny_filing_enumeration)
                with pytest.raises(PermissionError) as list_error:
                    source.list_source_document_ids(ticker, SourceKind.FILING)
        _assert_path_free_storage_os_error(
            list_error.value,
            expected_errno=errno.EACCES,
            workspace_root=workspace_root,
            private_locators=private_locators,
        )
    finally:
        filing_root.chmod(original_mode)

    descriptor_path = next(
        path for path in target_dir.iterdir() if path.name.startswith(".") and path.suffix == ".json"
    )
    descriptor_mode = descriptor_path.stat().st_mode & 0o777
    descriptor_path.chmod(0)
    try:
        inventory = company.scan_company_meta_inventory()
        if any(entry.ticker == ticker and entry.status == "available" for entry in inventory):
            original_read_text = Path.read_text

            def _deny_descriptor_read(
                path: Path,
                encoding: str | None = None,
                errors: str | None = None,
            ) -> str:
                """root-like 平台上对 ticker descriptor 注入 pathful permission failure。

                Args:
                    path: 待读取路径。
                    encoding: 文本编码。
                    errors: 解码错误策略。

                Returns:
                    非目标文件的原始文本。

                Raises:
                    PermissionError: descriptor 始终抛出携路径异常。
                """

                if path == descriptor_path:
                    raise PermissionError(
                        errno.EACCES,
                        "permission denied",
                        str(path),
                    )
                return original_read_text(path, encoding=encoding, errors=errors)

            with monkeypatch.context() as patch_context:
                patch_context.setattr(Path, "read_text", _deny_descriptor_read)
                inventory = company.scan_company_meta_inventory()
        unresolved = [entry for entry in inventory if entry.status == "invalid_meta"]
        assert unresolved
        typed_detail = json.dumps(
            [entry.detail for entry in unresolved],
            ensure_ascii=False,
        )
        assert str(workspace_root) not in typed_detail
        assert all(locator not in typed_detail for locator in private_locators)
    finally:
        descriptor_path.chmod(descriptor_mode)


def test_blob_read_projects_real_socket_io_error_without_private_locator(
    tmp_path: Path,
) -> None:
    """blob public read 必须投影真实 socket I/O error，不依赖 chmod/root 假设。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 真实 OS error 的类别、errno、cause 或 non-leak contract 回退时抛出。
        OSError: Unix-domain socket fixture 创建失败时抛出。
    """

    workspace_root = tmp_path / "storage-real-socket-io"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    document_id = "fil_socket/文档\\.."
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=SourceKind.FILING.value,
    )
    batch = batching.begin_batch(ticker)
    file_meta = blob.store_file(
        handle,
        "filing.htm",
        io.BytesIO(b"payload"),
        batch=batch,
    )
    source.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document="filing.htm",
            files=[file_meta],
            meta={
                "ingest_method": "download",
                "source_provider": "sec_edgar",
                "source_fingerprint": "socket-io",
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )
    batching.commit_batch(batch)
    physical_file = repository_set.core._resolve_handle_child_path(handle, "filing.htm")
    physical_file.unlink()
    socket_fixture = socket.socket(socket.AF_UNIX)
    original_cwd = Path.cwd()
    try:
        os.chdir(physical_file.parent)
        socket_fixture.bind(physical_file.name)
        os.chdir(original_cwd)
        try:
            physical_file.read_bytes()
        except OSError as raw_error:
            expected_errno = raw_error.errno
        else:
            raise AssertionError("socket fixture 未产生真实 I/O error")
        assert expected_errno is not None

        with pytest.raises(OSError) as exc_info:
            blob.read_file_bytes(handle, "filing.htm")

        _assert_path_free_storage_os_error(
            exc_info.value,
            expected_errno=expected_errno,
            workspace_root=workspace_root,
            private_locators=(physical_file.parent.name,),
        )
    finally:
        os.chdir(original_cwd)
        socket_fixture.close()


def test_stale_filing_cleanup_uses_descriptor_external_id_with_canonical_ticker_layout(
    tmp_path: Path,
) -> None:
    """stale cleanup 应先由 descriptor 恢复 external ID，再执行 fil_ 业务判断。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: cleanup 从 private key 反推业务 ID 或删除错误文档时抛出。
    """

    workspace_root = tmp_path / "opaque-stale-cleanup"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    maintenance = FsFilingMaintenanceRepository(workspace_root, repository_set=repository_set)
    ticker = "AAPL"
    keep_id = "fil_保留/2025\\Q1"
    stale_id = "fil_过期/2024\\Q4"
    batch = batching.begin_batch(ticker)
    for document_id in (keep_id, stale_id):
        handle = SourceHandle(
            ticker=ticker,
            document_id=document_id,
            source_kind=SourceKind.FILING.value,
        )
        file_meta = blob.store_file(
            handle,
            "filing.htm",
            io.BytesIO(document_id.encode("utf-8")),
            batch=batch,
        )
        source.create_source_document(
            SourceDocumentUpsertRequest(
                ticker=ticker,
                document_id=document_id,
                internal_document_id=document_id,
                form_type="10-K",
                primary_document="filing.htm",
                files=[file_meta],
                meta={
                    "ingest_method": "download",
                    "source_provider": "sec_edgar",
                    "source_fingerprint": f"fingerprint-{document_id}",
                },
            ),
            SourceKind.FILING,
            batch=batch,
        )
    batching.commit_batch(batch)

    cleanup_batch = batching.begin_batch(ticker)
    removed = maintenance.cleanup_stale_filing_documents(
        ticker,
        batch=cleanup_batch,
        active_form_types={"10-K"},
        valid_document_ids={keep_id},
    )
    batching.commit_batch(cleanup_batch)

    assert removed == 1
    assert source.list_source_document_ids(ticker, SourceKind.FILING) == [keep_id]


def test_read_runtime_citation_projects_provider_owned_source_types(tmp_path: Path) -> None:
    """read runtime citation 应只从 repository provenance 投影来源分类。"""

    runtime = _build_read_runtime_with_provenance_documents(tmp_path)

    expected = (
        ("AAPL", "fil_sec", "SEC_EDGAR", "SEC_EDGAR"),
        ("600519", "fil_cninfo", "CNINFO", "CNINFO"),
        ("0700", "fil_hkexnews", "HKEXNEWS", "HKEXNEWS"),
        ("AAPL", "fil_user_upload", "UPLOADED", "USER_UPLOAD"),
        ("AAPL", "mat_user_upload", "SUPPLEMENTARY", "USER_UPLOAD"),
    )
    for ticker, document_id, source_type, source_provider in expected:
        with runtime._borrow_processor(ticker=ticker, document_id=document_id) as borrow:
            citation = runtime._build_citation(borrow=borrow)
        assert citation["source_type"] == source_type
        assert citation["source_provider"] == source_provider
    runtime.close()


def test_read_runtime_citation_reuses_same_snapshot_provenance(tmp_path: Path) -> None:
    """citation 重复构造应消费同一 borrowed snapshot，不回读 repository。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: citation 回读 meta/snapshot 或 provider 投影错误时抛出。
    """

    workspace_root = tmp_path / "fins-citation-cache-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = _CountingSourceRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("AAPL")
    stage_company_meta_fixture(
        company_repository,
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker_identity=build_company_ticker_identity("AAPL", ()),
            resolver_version="test",
            updated_at=now_iso8601(),
        ),
        batch=batch,
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batch,
        ticker="AAPL",
        document_id="fil_sec",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.SEC_EDGAR.to_storage_value(),
        processor_compatible=True,
    )
    batching_repository.commit_batch(batch)
    runtime = FinsReadRuntime(
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        processor_registry=DefaultFinsRuntime.create(workspace_root=workspace_root).get_processor_registry(),
    )

    with runtime._borrow_processor(ticker="AAPL", document_id="fil_sec") as borrow:
        first_citation = runtime._build_citation(borrow=borrow)
        second_citation = runtime._build_citation(borrow=borrow)

    assert first_citation == second_citation
    assert first_citation["source_provider"] == "SEC_EDGAR"
    assert source_repository.snapshot_read_calls == 2
    assert source_repository.get_source_meta_calls == 0
    runtime.close()


def test_read_runtime_citation_inventory_uses_complete_published_sources(tmp_path: Path) -> None:
    """read runtime citation inventory 只消费 storage 已发布的完整 sources。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: inventory 未消费预期已发布 source 时抛出。
    """

    runtime = _build_read_runtime_with_provenance_documents(tmp_path)
    documents = runtime._collect_source_documents_by_kind("AAPL", SourceKind.FILING)

    assert {str(item["document_id"]) for item in documents} == {
        "fil_sec",
        "fil_user_upload",
    }
    for document_id in ("fil_sec", "fil_user_upload"):
        meta = runtime._source_repository.get_source_meta(
            "AAPL",
            document_id,
            SourceKind.FILING,
        )
        assert meta["ingest_complete"] is True


def test_citation_to_dict_omits_none_source_provider() -> None:
    """Citation.to_dict 只在 source_provider 非空时输出该字段。"""

    providerless = Citation(source_type="UPLOADED", document_id="doc", ticker="AAPL")
    with_provider = Citation(
        source_type="UPLOADED",
        source_provider="USER_UPLOAD",
        document_id="doc",
        ticker="AAPL",
    )

    assert "source_provider" not in providerless.to_dict()
    assert with_provider.to_dict()["source_provider"] == "USER_UPLOAD"


def test_fins_provider_discovers_read_tools_with_fins_read_tag(tmp_path: Path) -> None:
    """Provider 应发现带 fins/fins-read tags 的 read tools。"""

    workspace_root = _build_fins_workspace(tmp_path)
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=_spec(workspace_root), provider=discover_tools),)
    )

    assert tuple(definition.name for definition in result.tool_bundle.definitions) == _FINS_READ_TOOL_NAMES
    assert all("fins" in definition.tags for definition in result.tool_bundle.definitions)
    assert all("fins-read" in definition.tags for definition in result.tool_bundle.definitions)


def test_fins_read_tools_do_not_import_retired_adapter() -> None:
    """Fins read provider、工具和测试 helper 不得依赖退役适配器。"""

    paths = (
        Path("dayu/fins/tools/provider.py"),
        Path("dayu/fins/tools/fins_tools.py"),
        Path("dayu/fins/tools/read_runtime.py"),
        Path("dayu/fins/tools/read_runtime_helpers.py"),
        Path("dayu/fins/tools/search_engine.py"),
        Path(__file__),
    )
    forbidden = (
        "_legacy" + "_adapter",
        "LegacyTool" + "DeclarationCollector",
        "adapt_collected" + "_tools",
    )
    offenders: list[str] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in forbidden):
            offenders.append(str(path))

    assert offenders == []


def test_fins_read_tool_schemas_do_not_expose_execution_context(tmp_path: Path) -> None:
    """九个 Fins read tools 的 LLM-facing schema 不得暴露治理字段。"""

    workspace_root = _build_fins_workspace(tmp_path)
    definitions = _discover_definitions(workspace_root)
    ticker_schema: Mapping[str, JsonValue] = {
        "type": "string",
        "description": (
            "公司财报代码。可传工作区已接收的主代码或该公司的任一已接收别名；"
            "两者会查询同一家公司归档。不要传公司名称，也不要手工穷举代码变体。"
        ),
    }
    document_id_schema: Mapping[str, JsonValue] = {
        "type": "string",
        "description": (
            "文档 ID。只能使用同一 ticker 的 "
            "list_documents.documents[].document_id；切换 ticker 后必须重新调用 "
            "list_documents 选择，禁止猜测或复用其他 ticker 的 document_id。"
        ),
    }

    assert tuple(definition.name for definition in definitions) == _FINS_READ_TOOL_NAMES
    for definition in definitions:
        properties = definition.schema.function.parameters.properties
        required = definition.schema.function.parameters.required
        assert properties["ticker"] == ticker_schema
        if definition.name == "list_documents":
            assert "document_id" not in properties
        else:
            assert properties["document_id"] == document_id_schema
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "execution_context" not in required
        assert "cancellation_token" not in required


def test_fins_read_definitions_declare_process_backed_execution(tmp_path: Path) -> None:
    """九个 Fins read definitions 必须声明 process-backed execution。"""

    workspace_root = _build_fins_workspace(tmp_path)
    definitions = _discover_definitions(workspace_root)

    assert tuple(definition.name for definition in definitions) == _FINS_READ_TOOL_NAMES
    for definition in definitions:
        assert isinstance(definition.execution, ProcessBackedToolExecutionCapability)


def test_fins_tools_do_not_redeclare_process_envelope_constants() -> None:
    """Fins 工具不得重新声明本地 process envelope 常量。"""

    source = Path("dayu/fins/tools/fins_tools.py").read_text(encoding="utf-8")

    assert "_FINS_PROCESS_" not in source


def test_fins_read_process_target_factory_pickle_round_trip(tmp_path: Path) -> None:
    """Fins read process target factory / target 必须可 pickle 且不携带运行时对象。"""

    workspace_root = _build_fins_workspace(tmp_path)
    definitions = _definitions_by_name(_discover_definitions(workspace_root))
    factory = _process_target_factory(definitions["list_documents"])

    factory_payload = pickle.dumps(factory)
    round_tripped_factory = cast(
        ProcessBackedToolTargetFactory,
        pickle.loads(factory_payload),
    )
    target = round_tripped_factory.build_process_target(
        _call("list_documents", {"ticker": "AAPL"}),
        _process_context(),
    )
    target_payload = pickle.dumps(target)
    round_tripped_target = cast(ProcessBackedToolTarget, pickle.loads(target_payload))

    forbidden_payload_fragments = (
        b"FinsReadRuntime",
        b"Repository",
        b"provider_lock",
        b"CancellationToken",
        b"session-fins",
        b"run-fins",
    )
    for fragment in forbidden_payload_fragments:
        assert fragment not in factory_payload
        assert fragment not in target_payload
    assert callable(round_tripped_target)


def test_fins_read_process_target_fast_path_uses_default_runtime(tmp_path: Path) -> None:
    """process target 应能在当前进程重建 DefaultFinsRuntime 并执行 fast path。"""

    workspace_root = _build_fins_workspace(tmp_path)
    target = _build_process_target(
        workspace_root,
        "list_documents",
        {"ticker": "AAPL"},
    )

    envelope = target()

    value = _completed_envelope_value(envelope)
    assert isinstance(value, Mapping)
    assert value.get("matched") == 1


def test_list_documents_canonical_and_accepted_alias_route_same_corpus(
    tmp_path: Path,
) -> None:
    """canonical 与 accepted alias 应通过唯一 storage contract 返回同一 corpus。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: alias 被下游猜测、未命中或路由到不同 corpus 时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    canonical_value = _completed_envelope_value(
        _build_process_target(
            workspace_root,
            "list_documents",
            {"ticker": "AAPL"},
        )()
    )
    alias_value = _completed_envelope_value(
        _build_process_target(
            workspace_root,
            "list_documents",
            {"ticker": "apple"},
        )()
    )

    assert alias_value == canonical_value
    assert isinstance(alias_value, Mapping)
    assert alias_value.get("matched") == 1


def test_list_documents_meta_less_corpus_coexists_with_healthy_alias_corpus(
    tmp_path: Path,
) -> None:
    """meta-less corpus 应 canonical-only，且不影响 healthy corpus 的 alias e2e 路由。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: meta-less 被视为损坏、获得隐式 alias 或污染其它 corpus 时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    batch = batching_repository.begin_batch("DELTA")
    request = SourceDocumentUpsertRequest(
        ticker="DELTA",
        document_id="delta-material",
        internal_document_id="delta-material",
        form_type="material",
        primary_document="delta.md",
        meta={
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "ingest_method": "upload",
            "source_provider": "user_upload",
        },
    )
    source_repository.create_source_document(request, SourceKind.MATERIAL, batch=batch)
    handle = SourceHandle(
        ticker="DELTA",
        document_id="delta-material",
        source_kind=SourceKind.MATERIAL.value,
    )
    file_meta = blob_repository.store_file(
        handle,
        "delta.md",
        io.BytesIO(b"# Delta material\n"),
        batch=batch,
        content_type="text/markdown",
    )
    source_repository.update_source_document(
        SourceDocumentUpsertRequest(
            ticker=request.ticker,
            document_id=request.document_id,
            internal_document_id=request.internal_document_id,
            form_type=request.form_type,
            primary_document=request.primary_document,
            meta=request.meta,
            files=[file_meta],
        ),
        SourceKind.MATERIAL,
        batch=batch,
    )
    batching_repository.commit_batch(batch)

    delta_value = _completed_envelope_value(
        _build_process_target(workspace_root, "list_documents", {"ticker": "DELTA"})()
    )
    delta_variant_value = _completed_envelope_value(
        _build_process_target(workspace_root, "list_documents", {"ticker": "delta.us"})()
    )
    aapl_value = _completed_envelope_value(
        _build_process_target(workspace_root, "list_documents", {"ticker": "AAPL"})()
    )
    apple_value = _completed_envelope_value(
        _build_process_target(workspace_root, "list_documents", {"ticker": "APPLE"})()
    )

    assert delta_variant_value == delta_value
    assert isinstance(delta_value, Mapping)
    assert delta_value.get("matched") == 1
    assert apple_value == aapl_value
    assert company_repository.resolve_company_ticker("DLTA") is None
    assert not (workspace_root / "portfolio" / "DELTA" / "meta.json").exists()


def test_list_documents_projects_descriptor_corruption_as_actionable_business_error(
    tmp_path: Path,
) -> None:
    """read owner 应把 typed descriptor corruption 投影为固定可行动错误。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: corruption 泄露路径、落入 NOT_FOUND 或 execution error 时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    descriptor_candidates = tuple(
        path
        for path in (workspace_root / "portfolio" / "AAPL").iterdir()
        if path.name.startswith(".") and path.suffix == ".json"
    )
    assert len(descriptor_candidates) == 1
    descriptor_path = descriptor_candidates[0]
    descriptor_path.write_text("{}", encoding="utf-8")
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()

    with pytest.raises(FinsReadBusinessError) as exc_info:
        read_runtime.list_documents(ticker="AAPL")

    assert exc_info.value.code is ErrorCode.WORKSPACE_IDENTITY_CORRUPTED
    assert exc_info.value.message == "工作区中的公司代码身份数据不一致，当前无法安全解析该公司"
    assert exc_info.value.hint == "请修复该工作区的公司元数据后重试"
    assert str(workspace_root) not in str(exc_info.value)


def test_fins_read_process_target_processor_and_table_paths(tmp_path: Path) -> None:
    """process target 应覆盖 processor search path 与 table path。"""

    workspace_root = _build_fins_workspace(tmp_path)
    search_envelope = _build_process_target(
        workspace_root,
        "search_document",
        {
            "ticker": "AAPL",
            "document_id": "aapl-2024-10k",
            "query": "annual recurring revenue",
            "mode": "keyword",
        },
    )()
    tables_envelope = _build_process_target(
        workspace_root,
        "list_tables",
        {
            "ticker": "AAPL",
            "document_id": "aapl-2024-10k",
        },
    )()

    search_value = _completed_envelope_value(search_envelope)
    tables_value = _completed_envelope_value(tables_envelope)
    assert isinstance(search_value, Mapping)
    assert isinstance(search_value.get("matches"), list)
    assert isinstance(tables_value, Mapping)
    assert isinstance(tables_value.get("tables"), list)


def test_fins_read_process_target_failure_envelope(tmp_path: Path) -> None:
    """process target 参数失败应分离 failed message 与 hint。"""

    workspace_root = _build_fins_workspace(tmp_path)
    target = _build_process_target(workspace_root, "list_documents", {})

    envelope = target()

    assert isinstance(envelope, Mapping)
    assert envelope.get("status") == "failed"
    assert envelope.get("error_type") == "invalid_argument"
    assert "Hint:" not in str(envelope.get("message"))
    assert envelope.get("hint") == "Add required fields and retry: ticker."
    assert "host_cancelled" not in envelope.values()
    assert "cancelled" not in envelope.values()
    assert "timeout" not in envelope.values()
    assert "awaiting" not in envelope.values()


def test_fins_read_process_target_closes_runtime_on_success_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三种 process outcome 遇到首次 close 失败都应执行一次公共 follow-up。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 用于注入首次 close 失败并观察公共 follow-up。

    Returns:
        无。

    Raises:
        AssertionError: follow-up 次数、真实 cleanup 或 outcome 优先级漂移时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    success_target = _build_process_target(
        workspace_root,
        "list_documents",
        {"ticker": "AAPL"},
    )
    failure_target = _build_process_target(workspace_root, "list_documents", {})
    unexpected_failure_target = _build_process_target(
        workspace_root,
        "list_documents",
        {"ticker": "AAPL"},
    )
    original_close = DefaultFinsRuntime.close
    close_calls: dict[int, int] = {}
    runtime_by_id: dict[int, DefaultFinsRuntime] = {}

    def _fail_first_close_then_close(runtime: DefaultFinsRuntime) -> None:
        """每个 runtime 首次 close 失败，第二次执行真实公共 close。

        Args:
            runtime: process target 创建的默认 Fins runtime。

        Returns:
            无。

        Raises:
            OSError: 每个 runtime 的第一次 close 固定抛出 transient failure。
        """

        runtime_id = id(runtime)
        runtime_by_id[runtime_id] = runtime
        close_calls[runtime_id] = close_calls.get(runtime_id, 0) + 1
        if close_calls[runtime_id] == 1:
            raise OSError(errno.EBUSY, "transient close locator must remain private")
        original_close(runtime)

    monkeypatch.setattr(DefaultFinsRuntime, "close", _fail_first_close_then_close)

    success_envelope = success_target()
    failure_envelope = failure_target()
    monkeypatch.setattr(
        "dayu.fins.tools.fins_tools._execute_fins_read_business_value",
        _raise_unexpected_process_target_failure,
    )
    unexpected_failure_envelope = unexpected_failure_target()

    assert isinstance(success_envelope, Mapping)
    assert success_envelope.get("status") == "failed"
    assert success_envelope.get("error_type") == "execution_error"
    assert isinstance(failure_envelope, Mapping)
    assert failure_envelope.get("status") == "failed"
    assert failure_envelope.get("error_type") == "invalid_argument"
    assert isinstance(unexpected_failure_envelope, Mapping)
    assert unexpected_failure_envelope.get("status") == "failed"
    assert unexpected_failure_envelope.get("error_type") == "execution_error"
    assert len(runtime_by_id) == 3
    assert set(close_calls.values()) == {2}
    for runtime in runtime_by_id.values():
        with pytest.raises(RuntimeError, match="DefaultFinsRuntime 已关闭"):
            runtime.get_read_runtime()


def test_fins_read_process_target_persistent_close_failure_logs_path_free_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """公共 follow-up 仍失败时只记录 action/type/errno 且保留业务 outcome。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 用于注入两次 close failure。
        caplog: pytest 日志捕获器。

    Returns:
        无。

    Raises:
        AssertionError: outcome 漂移、follow-up 缺失或诊断泄漏 locator 时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    failure_target = _build_process_target(workspace_root, "list_documents", {})
    secret_message = (
        "/private/dayu-source-snapshot-secret key=private-key revision=private-revision cause=private-cause"
    )
    close_call_count = 0

    def _always_fail_close(runtime: DefaultFinsRuntime) -> None:
        """记录公共 close 次数并始终抛出带敏感 locator 的异常。

        Args:
            runtime: process target 创建的默认 Fins runtime。

        Returns:
            无。

        Raises:
            OSError: 始终抛出测试 cleanup failure。
        """

        nonlocal close_call_count
        del runtime
        close_call_count += 1
        raise OSError(errno.EBUSY, secret_message)

    monkeypatch.setattr(DefaultFinsRuntime, "close", _always_fail_close)
    with caplog.at_level(logging.WARNING, logger="dayu.fins.FINS.FINS_TOOLS"):
        failure_envelope = failure_target()

    assert isinstance(failure_envelope, Mapping)
    assert failure_envelope.get("status") == "failed"
    assert failure_envelope.get("error_type") == "invalid_argument"
    assert close_call_count == 2
    diagnostics = [
        record.getMessage() for record in caplog.records if "action=runtime.close.follow_up" in record.getMessage()
    ]
    assert diagnostics == [f"action=runtime.close.follow_up type=OSError errno={errno.EBUSY}"]
    diagnostic = diagnostics[0]
    for forbidden_fragment in (
        secret_message,
        "/private/",
        "private-key",
        "private-revision",
        "private-cause",
        "traceback",
    ):
        assert forbidden_fragment not in diagnostic


def test_default_runtime_public_close_retries_real_snapshot_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 snapshot 首次 cleanup 失败后，第二次公共 close 应删除临时根。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: 用于让真实 snapshot temp-root 删除首次失败。

    Returns:
        无。

    Raises:
        AssertionError: 公共幂等 close 未保留或未消费 cleanup authority 时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    read_runtime = runtime.get_read_runtime()
    result = read_runtime.get_document_sections(
        ticker="AAPL",
        document_id="aapl-2024-10k",
    )
    assert result["sections"]
    original_remove = source_snapshot_module._remove_snapshot_temp_root
    removal_attempts: list[Path] = []

    def _fail_first_snapshot_remove(temp_root: Path) -> None:
        """首次保留真实 temp root，后续调用执行真实删除。

        Args:
            temp_root: storage snapshot owner 创建的真实临时根。

        Returns:
            无。

        Raises:
            OSError: 第一次调用固定抛出 transient cleanup failure。
        """

        removal_attempts.append(temp_root)
        if len(removal_attempts) == 1:
            raise OSError(errno.EBUSY, "transient snapshot cleanup failure")
        original_remove(temp_root)

    monkeypatch.setattr(
        source_snapshot_module,
        "_remove_snapshot_temp_root",
        _fail_first_snapshot_remove,
    )
    with pytest.raises(OSError):
        runtime.close()

    assert len(removal_attempts) == 1
    snapshot_root = removal_attempts[0]
    assert snapshot_root.exists()

    runtime.close()
    runtime.close()

    assert len(removal_attempts) == 2
    assert not snapshot_root.exists()


def test_read_outputs_never_expose_revision_internal_key_local_uri_or_temp_path(
    tmp_path: Path,
) -> None:
    """九个 read tools 的成功、失败、取消投影均不得泄漏 storage 私有语义。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 任一 nested key/value 暴露 revision、key、URI 或路径时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    source_repository = FsSourceDocumentRepository(
        workspace_root,
        repository_set=repository_set,
    )
    revision = _read_snapshot_revision(
        source_repository,
        "AAPL",
        "aapl-2024-10k",
        SourceKind.FILING,
    )
    ticker_directory = repository_set.core._target_ticker_dir("AAPL")
    assert ticker_directory == workspace_root / "portfolio" / "AAPL"
    source_private_key = repository_set.core._source_meta_path_for_read(
        "AAPL",
        "aapl-2024-10k",
        SourceKind.FILING,
    ).parent.name
    runtime = DefaultFinsRuntime.create(workspace_root=workspace_root)
    read_runtime = runtime.get_read_runtime()
    definitions = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))
    completed_outcomes: dict[str, ToolExecutionOutcome] = {}
    try:
        sections_outcome = asyncio.run(
            definitions["get_document_sections"].callable(
                _call(
                    "get_document_sections",
                    {"ticker": "AAPL", "document_id": "aapl-2024-10k"},
                ),
                _context(),
            )
        )
        tables_outcome = asyncio.run(
            definitions["list_tables"].callable(
                _call(
                    "list_tables",
                    {"ticker": "AAPL", "document_id": "aapl-2024-10k"},
                ),
                _context(),
            )
        )
        assert isinstance(sections_outcome, ToolCompletedOutcome)
        assert isinstance(tables_outcome, ToolCompletedOutcome)
        sections_value = sections_outcome.result.value
        tables_value = tables_outcome.result.value
        assert isinstance(sections_value, Mapping)
        assert isinstance(tables_value, Mapping)
        sections = sections_value.get("sections")
        tables = tables_value.get("tables")
        assert isinstance(sections, list) and sections
        assert isinstance(tables, list) and tables
        first_section = sections[0]
        first_table = tables[0]
        assert isinstance(first_section, Mapping)
        assert isinstance(first_table, Mapping)
        section_ref = first_section.get("ref")
        table_ref = first_table.get("table_ref")
        assert isinstance(section_ref, str)
        assert isinstance(table_ref, str)

        completed_arguments: dict[str, Mapping[str, JsonValue]] = {
            "list_documents": {"ticker": "AAPL"},
            "get_document_sections": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
            },
            "read_section": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
                "ref": section_ref,
            },
            "search_document": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
                "query": "annual recurring revenue",
                "mode": "keyword",
            },
            "list_tables": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
            },
            "get_table": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
                "table_ref": table_ref,
            },
            "get_page_content": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
                "page_no": 1,
            },
            "get_financial_statement": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
                "statement_type": "income",
            },
            "query_xbrl_facts": {
                "ticker": "AAPL",
                "document_id": "aapl-2024-10k",
                "concepts": ["Revenue"],
            },
        }
        completed_outcomes["get_document_sections"] = sections_outcome
        completed_outcomes["list_tables"] = tables_outcome
        for tool_name, arguments in completed_arguments.items():
            if tool_name in completed_outcomes:
                continue
            completed_outcomes[tool_name] = asyncio.run(
                definitions[tool_name].callable(
                    _call(tool_name, arguments),
                    _context(),
                )
            )

        projected_outputs: list[JsonValue] = []
        for tool_name in _FINS_READ_TOOL_NAMES:
            completed = completed_outcomes[tool_name]
            assert isinstance(completed, ToolCompletedOutcome)
            projected_outputs.append(_project_llm_facing_outcome(completed))

            failed = asyncio.run(
                definitions[tool_name].callable(
                    _call(tool_name, {}),
                    _context(),
                )
            )
            assert isinstance(failed, ToolFailedOutcome)
            projected_outputs.append(_project_llm_facing_outcome(failed))

            cancellation_token = _ManualCancellationToken()
            cancellation_token.cancel()
            cancelled = asyncio.run(
                definitions[tool_name].callable(
                    _call(tool_name, completed_arguments[tool_name]),
                    _context(cancellation_token=cancellation_token),
                )
            )
            assert isinstance(cancelled, ToolCancelledOutcome)
            projected_outputs.append(_project_llm_facing_outcome(cancelled))

        forbidden_values = (
            revision.token,
            source_private_key,
            str(workspace_root),
            str(tmp_path),
        )
        for output in projected_outputs:
            _assert_read_output_has_no_storage_details(
                output,
                forbidden_values=forbidden_values,
            )
    finally:
        runtime.close()


def test_fins_read_process_target_runs_in_spawned_child(tmp_path: Path) -> None:
    """S2C pre-check：spawned child 能重建 DefaultFinsRuntime 并执行只读查询。"""

    workspace_root = _build_fins_workspace(tmp_path)
    target = _build_process_target(
        workspace_root,
        "list_documents",
        {"ticker": "AAPL"},
    )

    outcome = asyncio.run(_run_process_capsule(target))

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    assert value.get("matched") == 1


def test_fins_read_financial_statement_runs_in_spawned_child(tmp_path: Path) -> None:
    """spawned child 应能装配 FinancialDataProcessor 路径并执行财务工具。"""

    workspace_root = _build_fins_financial_html_workspace(tmp_path)
    target = _build_process_target(
        workspace_root,
        "get_financial_statement",
        {
            "ticker": "AAPL",
            "document_id": _FINANCIAL_HTML_DOCUMENT_ID,
            "statement_type": _INCOME_STATEMENT_TYPE,
        },
    )

    outcome = asyncio.run(_run_process_capsule(target))

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    assert value.get("document_id") == _FINANCIAL_HTML_DOCUMENT_ID
    assert value.get("statement_type") == _INCOME_STATEMENT_TYPE
    assert isinstance(value.get("periods"), list)
    assert isinstance(value.get("rows"), list)
    assert "scale" in value
    assert value.get("data_quality") == "partial"
    assert isinstance(value.get("reason"), str)
    assert set(value) == {
        "ticker",
        "document_id",
        "citation",
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
        "reason",
    }
    assert "supported" not in value
    assert "error" not in value


def test_fins_read_financial_statement_projects_statement_not_found(
    tmp_path: Path,
) -> None:
    """真实 XBRL 缺失目标报表时必须投影 producer 拥有的可操作原因。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: no-statement terminal 被 read 层改写时抛出。
    """

    workspace_root = _build_fins_aapl_xbrl_workspace(
        tmp_path,
        excluded_fixture_names=frozenset({"aapl-20240928_pre.xml"}),
        primary_payload_override=(b"<html><body><p>Business overview without tabular data.</p></body></html>"),
    )
    target = _build_process_target(
        workspace_root,
        "get_financial_statement",
        {
            "ticker": "AAPL",
            "document_id": _AAPL_XBRL_DOCUMENT_ID,
            "statement_type": "comprehensive_income",
        },
    )

    outcome = asyncio.run(_run_process_capsule(target))

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    assert value["rows"] == []
    assert value["data_quality"] == "partial"
    assert value["reason"] == "statement_not_found"
    assert set(value) == {
        "ticker",
        "document_id",
        "citation",
        "statement_type",
        "periods",
        "rows",
        "currency",
        "units",
        "scale",
        "data_quality",
        "reason",
    }


def test_fins_read_aapl_xbrl_query_runs_in_spawned_child(tmp_path: Path) -> None:
    """真实 AAPL XBRL fixture 应可通过 spawned child 查询稳定 fact。"""

    workspace_root = _build_fins_aapl_xbrl_workspace(tmp_path)
    target = _build_process_target(
        workspace_root,
        "query_xbrl_facts",
        {
            "ticker": "AAPL",
            "document_id": _AAPL_XBRL_DOCUMENT_ID,
            "concepts": [_AAPL_XBRL_VERIFIED_CONCEPT],
        },
    )

    outcome = asyncio.run(_run_process_capsule(target))

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    facts = value.get("facts")
    assert isinstance(facts, list)
    assert "fact_count" in value
    assert value["fact_count"] == len(facts)
    assert value.get("data_quality") == "xbrl"
    assert "reason" not in value
    assert set(value) == {
        "ticker",
        "document_id",
        "citation",
        "query_params",
        "facts",
        "fact_count",
        "data_quality",
    }
    concept_names = {_xbrl_fact_concept_local_name(fact) for fact in facts if isinstance(fact, Mapping)}
    assert _AAPL_XBRL_VERIFIED_CONCEPT in concept_names


def test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation(
    tmp_path: Path,
) -> None:
    """真实 XBRL public value、截断 envelope 与公开续读必须完整组合。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 三段公开链路的字段、顺序或计数语义不一致时抛出。
    """

    workspace_root = _build_fins_aapl_xbrl_workspace(tmp_path)
    extra_config: Mapping[str, JsonValue] = {
        "limits": {
            "query_xbrl_facts_max_items": _FORCED_XBRL_MAX_ITEMS,
        }
    }
    provider_output = discover_tools(_spec(workspace_root, extra_config=extra_config))
    definitions = _definitions_by_name(provider_output.definitions)
    query_arguments: Mapping[str, JsonValue] = {
        "ticker": "AAPL",
        "document_id": _AAPL_XBRL_DOCUMENT_ID,
        "concepts": [_AAPL_XBRL_VERIFIED_CONCEPT],
    }

    pre_outcome = asyncio.run(
        definitions["query_xbrl_facts"].callable(
            _call("query_xbrl_facts", query_arguments),
            _context(),
        )
    )
    assert isinstance(pre_outcome, ToolCompletedOutcome)
    pre_value = pre_outcome.result.value
    assert isinstance(pre_value, Mapping)
    assert "fact_count" in pre_value
    assert set(pre_value) == {
        "ticker",
        "document_id",
        "citation",
        "query_params",
        "facts",
        "fact_count",
        "data_quality",
    }
    pre_facts_value = pre_value["facts"]
    assert isinstance(pre_facts_value, list)
    assert len(pre_facts_value) > _FORCED_XBRL_MAX_ITEMS
    assert pre_value["fact_count"] == len(pre_facts_value)
    pre_value_copy = deepcopy(dict(pre_value))
    pre_facts_copy = deepcopy(pre_facts_value)

    assert FrameworkToolName.FETCH_MORE.value not in definitions
    runtime, _accepting_port = _tool_runtime(
        workspace_root,
        extra_config=extra_config,
        enable_truncation_manager=True,
    )
    assert FrameworkToolName.FETCH_MORE in (runtime.effective_bundle.injected_framework_tool_names)
    host_response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(_call("query_xbrl_facts", query_arguments),),
                context=_context(),
            )
        )
    )
    post_outcome = host_response.records[0].outcome
    assert isinstance(post_outcome, ToolCompletedOutcome)
    post_value = post_outcome.result.value
    assert isinstance(post_value, Mapping)
    assert set(post_value) == set(pre_value_copy)
    assert post_value["fact_count"] == pre_value_copy["fact_count"]
    for key, pre_item in pre_value_copy.items():
        if key != "facts":
            assert post_value[key] == pre_item

    facts_envelope = post_value["facts"]
    assert isinstance(facts_envelope, Mapping)
    assert set(facts_envelope) == {"truncated", "value", "fetch_more"}
    assert facts_envelope["truncated"] is True
    visible_value = facts_envelope["value"]
    fetch_more_reference = facts_envelope["fetch_more"]
    assert isinstance(visible_value, list)
    assert len(visible_value) == _FORCED_XBRL_MAX_ITEMS
    assert isinstance(fetch_more_reference, Mapping)
    cursor = fetch_more_reference["cursor"]
    scope_token = fetch_more_reference["scope_token"]
    assert isinstance(cursor, str)
    assert isinstance(scope_token, str)

    fetch_response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call(
                        FrameworkToolName.FETCH_MORE.value,
                        {"cursor": cursor, "scope_token": scope_token},
                    ),
                ),
                context=_context(),
            )
        )
    )
    fetch_outcome = fetch_response.records[0].outcome
    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    remainder = fetch_outcome.result.value
    assert isinstance(remainder, list)
    assert [*visible_value, *remainder] == pre_facts_copy


def test_financial_tool_descriptions_explain_owner_fields(tmp_path: Path) -> None:
    """两个 financial tool description 必须自足解释结果字段与降级语义。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: description 缺失 owner 字段或语义时抛出。
    """

    definitions = _definitions_by_name(_discover_definitions(_build_fins_workspace(tmp_path)))
    financial_description = definitions["get_financial_statement"].schema.function.description
    xbrl_description = definitions["query_xbrl_facts"].schema.function.description
    assert financial_description == financial_statement_result_description()
    assert xbrl_description == xbrl_query_result_description()

    for token in (
        "ticker",
        "document_id",
        "citation",
        "period_end:string",
        "fiscal_year:int|null",
        "fiscal_period:FY|H1|Q1|Q2|Q3|Q4|null",
        "scale",
        "units|thousands|millions|billions|null",
        "data_quality",
        "partial",
        "reason",
        "unsupported_statement_type",
        "xbrl_not_available",
        "statement_not_found",
        "low_confidence_extraction",
        "scale_unavailable",
        "period_semantics_unavailable",
        "scale_and_period_semantics_unavailable",
        "禁止跨期比较",
        "禁止数量级判断",
        "SEC_EDGAR",
    ):
        assert token in financial_description
    for token in (
        "ticker",
        "document_id",
        "citation",
        "query_params",
        "facts",
        "fact_count",
        '"fact_count":1',
        "fiscal_period:FY|H1|Q1|Q2|Q3|Q4",
        "data_quality=xbrl",
        "没有匹配事实",
        "partial",
        "reason",
        "xbrl_not_available",
        "query_partially_failed",
        "SEC_EDGAR",
    ):
        assert token in xbrl_description
    xbrl_parameters = definitions["query_xbrl_facts"].schema.function.parameters.properties
    fiscal_period_schema = xbrl_parameters["fiscal_period"]
    min_value_schema = xbrl_parameters["min_value"]
    max_value_schema = xbrl_parameters["max_value"]
    assert isinstance(fiscal_period_schema, Mapping)
    assert fiscal_period_schema["enum"] == sorted(FISCAL_PERIODS)
    assert isinstance(min_value_schema, Mapping)
    assert isinstance(max_value_schema, Mapping)
    assert min_value_schema["type"] == "number"
    assert max_value_schema["type"] == "number"
    forbidden_terms = (
        "Host",
        "Engine",
        "event_id",
        "digest",
        "cursor",
        "SSRF",
        "allowlist",
        "fallback branch",
    )
    assert not any(term in financial_description or term in xbrl_description for term in forbidden_terms)


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "valid_value"),
    [
        ("min_value", True, 0),
        ("max_value", False, 1.5),
    ],
)
def test_xbrl_number_parameters_reject_bool_and_accept_json_number(
    tmp_path: Path,
    field_name: str,
    invalid_value: JsonValue,
    valid_value: JsonValue,
) -> None:
    """XBRL 数值过滤参数的 callable 行为必须与 number schema 一致。

    Args:
        tmp_path: pytest 临时目录。
        field_name: 待验证的数值过滤字段。
        invalid_value: 必须拒绝的布尔值。
        valid_value: 必须接受的 JSON number。

    Returns:
        无。

    Raises:
        AssertionError: boolean 被接受或合法 number 被拒绝时抛出。
    """

    workspace_root = _build_fins_aapl_xbrl_workspace(tmp_path)
    definition = _definitions_by_name(_discover_definitions(workspace_root))["query_xbrl_facts"]
    base_arguments: dict[str, JsonValue] = {
        "ticker": "AAPL",
        "document_id": _AAPL_XBRL_DOCUMENT_ID,
        "concepts": [_AAPL_XBRL_VERIFIED_CONCEPT],
    }
    invalid_arguments = dict(base_arguments)
    invalid_arguments[field_name] = invalid_value
    valid_arguments = dict(base_arguments)
    valid_arguments[field_name] = valid_value

    invalid_outcome = asyncio.run(
        definition.callable(
            _call("query_xbrl_facts", invalid_arguments),
            _context(),
        )
    )
    valid_outcome = asyncio.run(
        definition.callable(
            _call("query_xbrl_facts", valid_arguments),
            _context(),
        )
    )

    assert isinstance(invalid_outcome, ToolFailedOutcome)
    assert invalid_outcome.result.error == "invalid_argument"
    assert isinstance(valid_outcome, ToolCompletedOutcome)


def test_financial_tool_process_target_preserves_xbrl_failed_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """process-backed target 必须把 typed XBRL failure 投影为 failed 信封。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: all-failed 被投影为 completed 空值时抛出。
    """

    target = _build_process_target(
        _build_fins_workspace(tmp_path),
        "query_xbrl_facts",
        {
            "ticker": "AAPL",
            "document_id": "aapl-2024-10k",
            "concepts": ["Revenue"],
        },
    )
    monkeypatch.setattr(
        DefaultFinsRuntime,
        "create",
        staticmethod(_create_xbrl_failure_default_runtime),
    )

    envelope = target()

    assert isinstance(envelope, Mapping)
    assert envelope.get("status") == "failed"
    assert envelope.get("error_type") == "xbrl_query_failed"
    assert "零命中" in str(envelope.get("message"))
    assert "value" not in envelope


def test_fins_read_process_backed_cancel_drops_late_result(tmp_path: Path) -> None:
    """ToolRuntime 取消真实 Fins process target 后不得接受子进程迟到结果。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime, accepting_port = _tool_runtime(workspace_root)
    token = _ManualCancellationToken()

    outcome = asyncio.run(_run_fins_process_tool_and_cancel(runtime, token))

    assert accepting_port.candidates
    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.hint is None


def test_fins_read_provider_requires_workspace_root_when_enabled(tmp_path: Path) -> None:
    """启用 read provider 时必须显式提供 workspace_root。"""

    with pytest.raises(ValueError, match="workspace_root"):
        discover_tools(
            _spec(
                tmp_path,
                extra_config={
                    "workspace_root": None,
                },
            )
        )


def test_list_documents_executes_through_current_tool_runtime(tmp_path: Path) -> None:
    """list_documents 应通过当前 ToolRuntime accept path 执行。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime, accepting_port = _tool_runtime(workspace_root)

    response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call(
                        "list_documents",
                        {
                            "ticker": "AAPL",
                        },
                    ),
                ),
                context=_context(),
            )
        )
    )

    outcome = response.records[0].outcome
    assert isinstance(outcome, ToolCompletedOutcome)
    assert accepting_port.candidates
    value = outcome.result.value
    assert isinstance(value, Mapping)
    assert value.get("matched") == 1
    assert "ok" not in value


@pytest.mark.parametrize("ticker", ("aapl.us", "apple"))
def test_list_documents_resolves_ticker_variant_and_alias_to_canonical_directory(
    tmp_path: Path,
    ticker: str,
) -> None:
    """list_documents 应把 ticker 变体与 alias 解析到同一 canonical 目录。

    Args:
        tmp_path: pytest 临时目录。
        ticker: 归一化变体或公司 ticker alias。

    Returns:
        无。

    Raises:
        AssertionError: read runtime 绕过 resolver 或无法读取 canonical 目录时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    definition = _definitions_by_name(_discover_definitions(workspace_root))["list_documents"]

    outcome = asyncio.run(
        definition.callable(
            _call("list_documents", {"ticker": ticker}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    company = value.get("company")
    assert isinstance(company, Mapping)
    assert company.get("ticker") == "AAPL"
    assert value.get("matched") == 1
    assert workspace_root.joinpath("portfolio", "AAPL").is_dir()


def test_list_documents_pre_cancel_returns_cancelled_outcome(tmp_path: Path) -> None:
    """list_documents 入口预取消时应投影为 Host cancelled outcome。"""

    workspace_root = _build_fins_workspace(tmp_path)
    definition = _definitions_by_name(_discover_definitions(workspace_root))["list_documents"]
    token = _ManualCancellationToken()
    token.cancel()

    outcome = asyncio.run(
        definition.callable(
            _call("list_documents", {"ticker": "AAPL"}),
            _context(cancellation_token=token),
        )
    )

    _assert_host_cancelled_outcome(outcome, "list_documents")


def test_cancelled_read_outcomes_hide_host_governance_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """取消 outcome 的 message / hint 不得暴露 Host 治理取消原因。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    definitions = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))

    pre_cancel_token = _ManualCancellationToken(
        cancel_reason=_HOST_GOVERNANCE_CANCEL_REASON,
    )
    pre_cancel_token.cancel()
    pre_cancel_outcome = asyncio.run(
        definitions["list_documents"].callable(
            _call("list_documents", {"ticker": "AAPL"}),
            _context(cancellation_token=pre_cancel_token),
        )
    )

    _assert_host_cancelled_outcome(pre_cancel_outcome, "list_documents")

    deep_cancel_token = _ManualCancellationToken(
        cancel_reason=_HOST_GOVERNANCE_CANCEL_REASON,
    )
    processor = _SearchCancellingProcessor(deep_cancel_token)
    _install_processor(read_runtime, cast(DocumentProcessor, processor), monkeypatch)
    deep_cancel_outcome = asyncio.run(
        definitions["search_document"].callable(
            _call(
                "search_document",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "query": "annual recurring revenue",
                    "mode": "keyword",
                },
            ),
            _context(cancellation_token=deep_cancel_token),
        )
    )

    _assert_host_cancelled_outcome(deep_cancel_outcome, "search_document")
    assert processor.search_calls == ["annual"]


def test_search_document_cancellation_during_search_stops_before_all_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_document 搜索循环中取消时不应继续执行后续候选查询。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    token = _ManualCancellationToken()
    processor = _SearchCancellingProcessor(token)
    _install_processor(read_runtime, cast(DocumentProcessor, processor), monkeypatch)
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))["search_document"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "search_document",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "query": "annual recurring revenue",
                    "mode": "keyword",
                },
            ),
            _context(cancellation_token=token),
        )
    )

    _assert_host_cancelled_outcome(outcome, "search_document")
    assert processor.search_calls == ["annual"]


def test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_document 语义增强降级块不应吞掉 Host 取消。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    token = _ManualCancellationToken()
    processor = _SearchCancellingProcessor(token)
    _install_processor(read_runtime, cast(DocumentProcessor, processor), monkeypatch)
    monkeypatch.setattr(
        read_runtime,
        "_enrich_sections_with_semantic",
        _raise_fins_cancelled_during_semantic_enrichment,
    )
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))["search_document"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "search_document",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "query": "annual recurring revenue",
                    "mode": "keyword",
                },
            ),
            _context(cancellation_token=token),
        )
    )

    _assert_host_cancelled_outcome(outcome, "search_document")
    assert processor.search_calls == []


def test_search_document_index_failure_returns_typed_failed_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search index readiness 异常应投影为 search_index_failed outcome。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: outcome 不是 typed failed 时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    processor = _SearchIndexFailingProcessor(_ManualCancellationToken())
    _install_processor(read_runtime, cast(DocumentProcessor, processor), monkeypatch)
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))["search_document"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "search_document",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "query": "annual recurring revenue",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == ErrorCode.SEARCH_INDEX_FAILED.value


def test_read_section_cancelled_before_processor_read_returns_cancelled_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_section 在 processor read 前观察到取消时应返回 cancelled outcome。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    token = _ManualCancellationToken()
    processor = _ReadCancellingProcessor(token)
    _install_processor(
        read_runtime,
        cast(DocumentProcessor, processor),
        monkeypatch,
        cancel_token_after_create=token,
    )
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))["read_section"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "read_section",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "ref": "s1",
                },
            ),
            _context(cancellation_token=token),
        )
    )

    _assert_host_cancelled_outcome(outcome, "read_section")
    assert processor.read_section_calls == 0


def test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_section 父标题查询降级块不应吞掉 Host 取消。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    token = _ManualCancellationToken()
    processor = _ParentTitleLookupCancellingProcessor(token)
    _install_processor(read_runtime, cast(DocumentProcessor, processor), monkeypatch)
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))["read_section"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "read_section",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "ref": "s2",
                },
            ),
            _context(cancellation_token=token),
        )
    )

    _assert_host_cancelled_outcome(outcome, "read_section")
    assert processor.get_section_title_calls == 1


def test_query_xbrl_facts_cancellation_during_filtering_stops_promptly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """query_xbrl_facts 在 facts 过滤检查中取消时应停止并返回 cancelled outcome。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    token = _ManualCancellationToken()
    processor = _XbrlFactsProcessor(token)
    _install_processor(read_runtime, cast(DocumentProcessor, processor), monkeypatch)
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))["query_xbrl_facts"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "query_xbrl_facts",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                    "concepts": ["Revenue"],
                },
            ),
            _context(cancellation_token=token),
        )
    )

    _assert_host_cancelled_outcome(outcome, "query_xbrl_facts")
    assert processor.query_calls == 1


def test_same_provider_read_tools_do_not_enter_read_runtime_concurrently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 provider 的两个 Fins read tools 不得并发进入 read runtime。"""

    workspace_root = _build_fins_workspace(tmp_path)
    read_runtime = DefaultFinsRuntime.create(workspace_root=workspace_root).get_read_runtime()
    probe = _ConcurrentReadRuntimeProbe()
    monkeypatch.setattr(read_runtime, "list_documents", probe.list_documents)
    monkeypatch.setattr(read_runtime, "get_document_sections", probe.get_document_sections)
    definitions = _definitions_by_name(_definitions_for_read_runtime(read_runtime, workspace_root))

    asyncio.run(_run_two_fins_read_tools_concurrently(definitions, probe.entered))

    assert probe.max_active_count == 1


def test_search_document_projection_and_failure_outcomes(tmp_path: Path) -> None:
    """search_document 应覆盖数组/标量投影和 current 成功/失败 outcome。"""

    workspace_root = _build_fins_workspace(tmp_path)
    runtime, _accepting_port = _tool_runtime(workspace_root)

    success_response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call(
                        "search_document",
                        {
                            "ticker": "AAPL",
                            "document_id": "aapl-2024-10k",
                            "queries": ["annual recurring revenue", "services margin"],
                            "mode": "keyword",
                        },
                    ),
                ),
                context=_context(),
            )
        )
    )
    failure_response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call(
                        "search_document",
                        {
                            "ticker": "AAPL",
                            "document_id": "aapl-2024-10k",
                            "query": "annual recurring revenue",
                            "queries": ["services margin"],
                        },
                    ),
                ),
                context=_context(),
            )
        )
    )

    success = success_response.records[0].outcome
    failure = failure_response.records[0].outcome
    assert isinstance(success, ToolCompletedOutcome)
    assert isinstance(failure, ToolFailedOutcome)
    assert failure.result.error == "invalid_argument"
    value = success.result.value
    assert isinstance(value, Mapping)
    assert value.get("queries") == ["annual recurring revenue", "services margin"]
    assert isinstance(value.get("matches"), list)
    assert "ok" not in value


def test_simple_matching_call_passes_through_provider_definition(tmp_path: Path) -> None:
    """匹配 schema 的简单调用应直接成功执行。"""

    workspace_root = _build_fins_workspace(tmp_path)
    definition = _definitions_by_name(_discover_definitions(workspace_root))["get_document_sections"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "get_document_sections",
                {
                    "ticker": "AAPL",
                    "document_id": "aapl-2024-10k",
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, Mapping)
    assert value.get("document_id") == "aapl-2024-10k"


def test_fins_truncate_specs_use_current_contract(tmp_path: Path) -> None:
    """Fins truncating tools 必须暴露当前 ToolTruncateSpec。"""

    workspace_root = _build_fins_workspace(tmp_path)
    definitions = _discover_definitions(workspace_root)
    truncate_by_name = {definition.name: definition.truncate for definition in definitions}
    list_documents_truncate = truncate_by_name["list_documents"]
    read_section_truncate = truncate_by_name["read_section"]
    search_document_truncate = truncate_by_name["search_document"]

    assert isinstance(list_documents_truncate, ToolTruncateSpec)
    assert isinstance(read_section_truncate, ToolTruncateSpec)
    assert isinstance(search_document_truncate, ToolTruncateSpec)
    assert list_documents_truncate.strategy is ToolTruncationStrategy.LIST_ITEMS
    assert read_section_truncate.strategy is ToolTruncationStrategy.TEXT_CHARS
    assert search_document_truncate.target_field == "matches"


def test_fins_provider_explicit_limits_shape_truncate_specs(tmp_path: Path) -> None:
    """Fins provider 必须把显式完整 limits 配置投影到各工具截断声明。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        ``None``。

    Raises:
        AssertionError: 截断声明未反映显式配置时抛出。
    """

    workspace_root = _build_fins_workspace(tmp_path)
    definitions = _definitions_by_name(
        discover_tools(
            _spec(
                workspace_root,
                extra_config={
                    "limits": {
                        "processor_cache_max_entries": 16,
                        "list_documents_max_items": 21,
                        "get_document_sections_max_items": 122,
                        "search_document_max_items": 23,
                        "list_tables_max_items": 54,
                        "read_section_max_chars": 8100,
                        "get_page_content_max_chars": 8200,
                        "get_table_max_items": 830,
                        "get_financial_statement_max_items": 1240,
                        "query_xbrl_facts_max_items": 1250,
                    },
                },
            )
        ).definitions
    )

    assert _truncate_limit(definitions["list_documents"], "max_items") == 21
    assert _truncate_limit(definitions["get_document_sections"], "max_items") == 122
    assert _truncate_limit(definitions["search_document"], "max_items") == 23
    assert _truncate_limit(definitions["list_tables"], "max_items") == 54
    assert _truncate_limit(definitions["read_section"], "max_chars") == 8100
    assert _truncate_limit(definitions["get_page_content"], "max_chars") == 8200
    assert _truncate_limit(definitions["get_table"], "max_items") == 830
    assert _truncate_limit(definitions["get_financial_statement"], "max_items") == 1240
    assert _truncate_limit(definitions["query_xbrl_facts"], "max_items") == 1250
    for definition in definitions.values():
        truncate = definition.truncate
        assert isinstance(truncate, ToolTruncateSpec)
        assert "processor_cache_max_entries" not in truncate.limits


def test_read_provider_only_exposes_read_tools(tmp_path: Path) -> None:
    """read provider 不应混入 download / preprocess ingestion tools。"""

    workspace_root = _build_fins_workspace(tmp_path)
    output = discover_tools(_spec(workspace_root))

    names = tuple(definition.name for definition in output.definitions)
    assert names == _FINS_READ_TOOL_NAMES
    assert "start_fins_download" not in names
    assert "start_fins_preprocess" not in names


def test_same_ticker_batch_blocks_across_independent_repository_cores(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 workspace 独立 core 的后 writer 必须阻塞并在前 writer 释放后成功。"""

    workspace_root = tmp_path / "fins-workspace"
    first_repository_set = build_fs_repository_set(workspace_root=workspace_root)
    first_repository = FsBatchingRepository(workspace_root, repository_set=first_repository_set)
    first_token = first_repository.begin_batch("AAPL")

    second_repository_set = build_fs_repository_set(workspace_root=workspace_root)
    second_repository = FsBatchingRepository(workspace_root, repository_set=second_repository_set)
    acquire_entered = Event()
    second_core = second_repository_set.core
    original_acquire = second_core._acquire_ticker_lock

    def record_blocking_acquire(ticker: str) -> RuntimeFileLockToken:
        """记录第二个 core 已进入真实 blocking file-lock acquire。"""

        acquire_entered.set()
        return original_acquire(ticker)

    monkeypatch.setattr(second_core, "_acquire_ticker_lock", record_blocking_acquire)
    with ThreadPoolExecutor(max_workers=1) as executor:
        waiting = executor.submit(second_repository.begin_batch, "AAPL")
        assert acquire_entered.wait(timeout=5)
        assert waiting.done() is False
        first_repository.rollback_batch(first_token)
        second_token = waiting.result(timeout=5)
    second_repository.rollback_batch(second_token)


def test_explicit_batch_allows_child_task_mutation_on_shared_core(tmp_path: Path) -> None:
    """显式 capability 应允许 child task 解析同一 core 的 active transaction。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: child task 无法用显式 capability 发布完整 source 时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    token = batching_repository.begin_batch("AAPL")

    try:
        asyncio.run(
            _create_source_in_child_task(
                source_repository,
                blob_repository,
                token,
            )
        )
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)

    assert source_repository.list_source_document_ids("AAPL", SourceKind.FILING) == ["aapl-child-task"]


async def _create_source_in_child_task(
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    batch: BatchToken,
) -> None:
    """在 child asyncio task 中使用显式 capability 写 source document。

    Args:
        source_repository: 共享同一 storage core 的 source repository。
        blob_repository: 共享同一 storage core 的 blob repository。
        batch: 调用方显式传入的 transaction capability。

    Returns:
        无。

    Raises:
        OSError: source 写入失败时抛出。
    """

    task = asyncio.create_task(_create_child_task_source(source_repository, blob_repository, batch))
    await task


async def _create_child_task_source(
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    batch: BatchToken,
) -> None:
    """在独立 task 中执行显式 transaction mutation。

    Args:
        source_repository: 共享同一 storage core 的 source repository。
        blob_repository: 共享同一 storage core 的 blob repository。
        batch: 调用方显式传入的 transaction capability。

    Returns:
        无。

    Raises:
        OSError: source 写入失败时抛出。
    """

    await asyncio.sleep(0)
    file_meta = blob_repository.store_file(
        SourceHandle("AAPL", "aapl-child-task", SourceKind.FILING.value),
        "aapl-child-task.md",
        io.BytesIO(b"child task source"),
        batch=batch,
        content_type="text/markdown",
    )
    original_name = "original-aapl-child-task.md"
    original_meta = blob_repository.store_file(
        SourceHandle("AAPL", "aapl-child-task", SourceKind.FILING.value),
        original_name,
        io.BytesIO(b"original child task source"),
        batch=batch,
        content_type="text/markdown",
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="aapl-child-task",
            internal_document_id="aapl-child-task",
            form_type="10-K",
            primary_document="aapl-child-task.md",
            file_entries=[
                _fresh_upload_file_entry(
                    original_meta,
                    name=original_name,
                    source="original",
                    original_filename="aapl-child-task.md",
                ),
                _fresh_upload_file_entry(
                    file_meta,
                    name="aapl-child-task.md",
                    source="docling",
                    original_filename="aapl-child-task.md",
                    derived_from=original_name,
                ),
            ],
            meta={
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "filing_date": "2024-11-01",
                "report_date": "2024-09-28",
                "amended": False,
                "ingest_method": "upload",
                "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
            },
        ),
        SourceKind.FILING,
        batch=batch,
    )


def test_explicit_batch_allows_worker_thread_mutation_on_shared_core(tmp_path: Path) -> None:
    """显式 capability 应允许 worker thread 解析同一 core 的 active transaction。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: worker thread 无法用显式 capability 发布完整 source 时抛出。
    """

    workspace_root = tmp_path / "fins-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    token = batching_repository.begin_batch("AAPL")
    file_meta = blob_repository.store_file(
        SourceHandle("AAPL", "aapl-worker-thread", SourceKind.FILING.value),
        "aapl-worker-thread.md",
        io.BytesIO(b"worker thread source"),
        batch=token,
        content_type="text/markdown",
    )
    original_name = "original-aapl-worker-thread.md"
    original_meta = blob_repository.store_file(
        SourceHandle("AAPL", "aapl-worker-thread", SourceKind.FILING.value),
        original_name,
        io.BytesIO(b"original worker thread source"),
        batch=token,
        content_type="text/markdown",
    )
    request = SourceDocumentUpsertRequest(
        ticker="AAPL",
        document_id="aapl-worker-thread",
        internal_document_id="aapl-worker-thread",
        form_type="10-K",
        primary_document="aapl-worker-thread.md",
        file_entries=[
            _fresh_upload_file_entry(
                original_meta,
                name=original_name,
                source="original",
                original_filename="aapl-worker-thread.md",
            ),
            _fresh_upload_file_entry(
                file_meta,
                name="aapl-worker-thread.md",
                source="docling",
                original_filename="aapl-worker-thread.md",
                derived_from=original_name,
            ),
        ],
        meta={
            "ingest_method": "upload",
            "source_provider": FinsSourceProvider.USER_UPLOAD.to_storage_value(),
        },
    )

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                source_repository.create_source_document,
                request,
                SourceKind.FILING,
                batch=token,
            )
            future.result(timeout=5)
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)

    assert source_repository.list_source_document_ids("AAPL", SourceKind.FILING) == ["aapl-worker-thread"]


def test_fins_workspace_root_must_be_explicit_absolute_path() -> None:
    """workspace_root 不得从 cwd 或环境隐式解析。"""

    spec = ToolsDiscoveryProviderSpec(
        spec_id="financial-read-tools",
        location=PythonImportPathProvider(import_path="dayu.fins.tools.provider:discover_tools"),
        enabled=True,
        config={
            "workspace_root": "workspace/fins",
            "limits": {},
        },
    )

    with pytest.raises(ValueError, match="absolute"):
        discover_tools(spec)


def test_fins_import_boundaries_do_not_reverse_depend() -> None:
    """Fins imports 不得引入 Host/Service/UI/Engine 反向依赖。"""

    offenders: list[str] = []
    for path in Path("dayu/fins").rglob("*.py"):
        imported_modules = _module_imports(path)
        forbidden = _fins_forbidden_import_roots(path)
        if any(_is_forbidden_import(name, forbidden) for name in imported_modules):
            offenders.append(str(path))

    assert offenders == []


def test_runtime_and_engine_do_not_import_fins() -> None:
    """Engine 仍不得 import Fins，runtime 也不得反向 import Fins。"""

    offenders: list[str] = []
    for root in (Path("dayu/engine"), Path("dayu/runtime")):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            if "import dayu.fins" in source or "from dayu.fins" in source:
                offenders.append(str(path))

    assert offenders == []


def _build_fins_workspace(tmp_path: Path) -> Path:
    """构造确定性 Fins fixture 工作区。

    Args:
        tmp_path: pytest 临时目录。

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
    token = batching_repository.begin_batch("AAPL")
    try:
        stage_company_meta_fixture(
            company_repository,
            CompanyMeta(
                company_id="0000320193",
                company_name="Apple Inc.",
                ticker_identity=build_company_ticker_identity("AAPL", ("APPLE",)),
                resolver_version="test",
                updated_at=now_iso8601(),
            ),
            batch=token,
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
                    "source_provider": "user_upload",
                },
            ),
            SourceKind.FILING,
            batch=token,
        )
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
            content_type="text/markdown",
        )
        original_name = "original-aapl-2024-10k.md"
        original_meta = blob_repository.store_file(
            handle,
            original_name,
            io.BytesIO(b"original upload fixture"),
            batch=token,
            content_type="text/markdown",
        )
        source_repository.update_source_document(
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
                    "source_provider": "user_upload",
                },
                file_entries=[
                    _fresh_upload_file_entry(
                        original_meta,
                        name=original_name,
                        source="original",
                        original_filename="aapl-2024-10k.md",
                    ),
                    _fresh_upload_file_entry(
                        file_meta,
                        name="aapl-2024-10k.md",
                        source="docling",
                        original_filename="aapl-2024-10k.md",
                        derived_from=original_name,
                    ),
                ],
            ),
            SourceKind.FILING,
            batch=token,
        )
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)
    return workspace_root


def _create_source_revision_document(
    repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    *,
    batch: BatchToken,
    replace_existing: bool = False,
) -> None:
    """创建 persisted opaque source revision 测试文档。

    Args:
        repository: source repository。
        blob_repository: 与 source repository 共享 core 的 blob repository。
        batch: 显式 transaction capability。
        replace_existing: 是否先重置同 ID 文档。

    Returns:
        无。

    Raises:
        OSError: source meta 写入失败时抛出。
    """

    if replace_existing:
        repository.reset_source_document(
            "AAPL",
            "revision-doc",
            SourceKind.FILING,
            batch=batch,
        )
    handle = SourceHandle(
        ticker="AAPL",
        document_id="revision-doc",
        source_kind=SourceKind.FILING.value,
    )
    primary_file = blob_repository.store_file(
        handle,
        "primary.html",
        io.BytesIO(b"p" * 100),
        batch=batch,
        content_type="text/html",
    )
    exhibit_file = blob_repository.store_file(
        handle,
        "exhibit.html",
        io.BytesIO(b"e" * 50),
        batch=batch,
        content_type="text/html",
    )
    repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker="AAPL",
            document_id="revision-doc",
            internal_document_id="revision-doc",
            form_type="10-K",
            primary_document="primary.html",
            meta={
                "ingest_method": "download",
                "source_provider": FinsSourceProvider.SEC_EDGAR.to_storage_value(),
                "ingest_complete": True,
                "is_deleted": False,
                "document_version": "v1",
                "source_fingerprint": "fingerprint-v1",
            },
            files=[primary_file, exhibit_file],
        ),
        SourceKind.FILING,
        batch=batch,
    )


def _read_snapshot_revision(
    repository: FsSourceDocumentRepository,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
) -> SourceDocumentRevision:
    """从 storage-owned light snapshot 读取 opaque published revision。

    Args:
        repository: source repository。
        ticker: exact external ticker。
        document_id: exact external document ID。
        source_kind: 显式 source kind。

    Returns:
        snapshot 同版 opaque revision。

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


def _create_source_document_for_provenance(
    *,
    source_repository: FsSourceDocumentRepository,
    blob_repository: FsDocumentBlobRepository,
    batch: BatchToken,
    ticker: str,
    document_id: str,
    source_kind: SourceKind,
    ingest_method: str,
    source_provider: str | None,
    processor_compatible: bool = False,
) -> None:
    """创建用于 provenance 测试的 source document。

    Args:
        source_repository: source 文档仓储。
        blob_repository: 与 source 仓储共享 core 的 blob 仓储。
        batch: 显式 transaction capability。
        ticker: 股票代码。
        document_id: 文档 ID。
        source_kind: 来源类型。
        ingest_method: ingest method 仓储值。
        source_provider: provider 仓储值；为 None 时故意不写入。
        processor_compatible: 是否使用 Markdown fixture 供 read processor 构建。

    Returns:
        无。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    meta: dict[str, JsonValue] = {
        "ingest_method": ingest_method,
        "fiscal_year": 2024,
        "fiscal_period": "FY",
        "filing_date": "2024-11-01",
        "report_date": "2024-09-28",
        "amended": False,
    }
    if source_provider is not None:
        meta["source_provider"] = source_provider
    filename = f"{document_id}.md" if processor_compatible else f"{document_id}.txt"
    handle = SourceHandle(
        ticker=ticker,
        document_id=document_id,
        source_kind=source_kind.value,
    )
    file_meta = blob_repository.store_file(
        handle,
        filename,
        io.BytesIO(
            (f"# {document_id}\n\nProvider provenance fixture.\n" if processor_compatible else document_id).encode(
                "utf-8"
            )
        ),
        batch=batch,
        content_type="text/markdown" if processor_compatible else "text/plain",
    )
    is_fresh_upload_filing = (
        source_kind is SourceKind.FILING
        and ingest_method == "upload"
        and source_provider == FinsSourceProvider.USER_UPLOAD.to_storage_value()
    )
    docling_name = f"{filename}_docling.json"
    docling_meta = (
        blob_repository.store_file(
            handle,
            docling_name,
            io.BytesIO(
                json.dumps(
                    {
                        "schema_name": "DoclingDocument",
                        "version": "1.10.0",
                        "name": document_id,
                        "furniture": {
                            "self_ref": "#/furniture",
                            "children": [],
                            "content_layer": "furniture",
                            "name": "_root_",
                            "label": "unspecified",
                        },
                        "body": {
                            "self_ref": "#/body",
                            "children": [],
                            "content_layer": "body",
                            "name": "_root_",
                            "label": "unspecified",
                        },
                        "groups": [],
                        "texts": [],
                        "pictures": [],
                        "tables": [],
                        "key_value_items": [],
                        "form_items": [],
                        "pages": {},
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
            ),
            batch=batch,
            content_type="application/json",
        )
        if is_fresh_upload_filing
        else None
    )
    file_entries = (
        [
            _fresh_upload_file_entry(
                file_meta,
                name=filename,
                source="original",
                original_filename=filename,
            ),
            _fresh_upload_file_entry(
                docling_meta,
                name=docling_name,
                source="docling",
                original_filename=filename,
                derived_from=filename,
            ),
        ]
        if docling_meta is not None
        else None
    )
    source_repository.create_source_document(
        SourceDocumentUpsertRequest(
            ticker=ticker,
            document_id=document_id,
            internal_document_id=document_id,
            form_type="10-K",
            primary_document=docling_name if docling_meta is not None else filename,
            meta=meta,
            files=[] if file_entries is not None else [file_meta],
            file_entries=file_entries,
        ),
        source_kind,
        batch=batch,
    )


def _corrupt_staged_complete_source(
    core: FsStorageCore,
    *,
    failure_case: _CompleteSourceFailureCase,
) -> None:
    """在 owner test 中只破坏一格 staged complete-source fact。

    Args:
        core: 当前测试唯一 shared storage core。
        failure_case: 要注入的完整性破坏类型。

    Returns:
        无。

    Raises:
        AssertionError: active batch 或测试 fixture 结构不符合预期时抛出。
        OSError: staged fixture 修改失败时抛出。
    """

    states = tuple(core._active_batches.values())
    assert len(states) == 1
    state = states[0]
    meta_path = core._source_meta_path(
        "AAPL",
        "new_source",
        SourceKind.FILING,
        state,
    )
    source_dir = meta_path.parent
    manifest_path = core._filing_manifest_path("AAPL", state)
    physical_path = source_dir / "new_source.txt"
    meta = cast(dict[str, JsonValue], json.loads(meta_path.read_text(encoding="utf-8")))
    manifest = cast(
        dict[str, JsonValue],
        json.loads(manifest_path.read_text(encoding="utf-8")),
    )
    raw_files = meta["files"]
    raw_documents = manifest["documents"]
    assert isinstance(raw_files, list) and raw_files and isinstance(raw_files[0], dict)
    assert isinstance(raw_documents, list) and len(raw_documents) == 2
    file_item = raw_files[0]
    manifest_item = next(
        item for item in raw_documents if isinstance(item, dict) and item.get("document_id") == "new_source"
    )

    if failure_case == "missing_meta":
        meta_path.unlink()
        return
    if failure_case == "empty_files":
        meta["files"] = []
    elif failure_case == "duplicate_files":
        raw_files.append(dict(file_item))
    elif failure_case == "dangling_file":
        physical_path.unlink()
    elif failure_case == "missing_primary":
        meta.pop("primary_document")
    elif failure_case == "invalid_ingest_method":
        meta["ingest_method"] = "side_load"
    elif failure_case == "invalid_provider":
        meta["source_provider"] = "unknown_provider"
    elif failure_case == "false_completion":
        meta["ingest_complete"] = False
    elif failure_case == "ticker_mismatch":
        meta["ticker"] = "MSFT"
    elif failure_case == "document_mismatch":
        meta["document_id"] = "other_source"
    elif failure_case == "source_kind_mismatch":
        meta["source_kind"] = SourceKind.MATERIAL.value
    elif failure_case == "uri_mismatch":
        raw_uri = file_item["uri"]
        assert isinstance(raw_uri, str)
        file_item["uri"] = f"{raw_uri.rsplit('/', 1)[0]}/other.txt"
    elif failure_case == "size_mismatch":
        file_item["size"] = 999
    elif failure_case == "sha_mismatch":
        file_item["sha256"] = "0" * 64
    elif failure_case == "symlink_file_escape":
        physical_path.unlink()
        outside_file = core.workspace_root / "outside-source.txt"
        outside_file.write_bytes(b"outside")
        physical_path.symlink_to(outside_file)
    elif failure_case == "filename_escape":
        file_item["name"] = "../escape.txt"
    elif failure_case == "unmanifested_file":
        (source_dir / "extra.txt").write_bytes(b"extra")
    elif failure_case == "missing_manifest":
        manifest_path.unlink()
        return
    elif failure_case == "dangling_manifest":
        dangling_item = dict(manifest_item)
        dangling_item["document_id"] = "ghost_source"
        raw_documents.append(dangling_item)
    elif failure_case == "manifest_projection_mismatch":
        manifest_item["source_provider"] = "user_upload"
    elif failure_case == "duplicate_manifest_identity":
        raw_documents.append(dict(manifest_item))
    elif failure_case == "manifest_ticker_mismatch":
        manifest["ticker"] = "MSFT"
    else:
        raise AssertionError(f"未处理的 complete source failure case: {failure_case}")

    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _build_read_runtime_with_provenance_documents(tmp_path: Path) -> FinsReadRuntime:
    """构造包含多 provider source 文档的 read runtime。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        已装配仓储的 read runtime。

    Raises:
        OSError: 仓储写入失败时抛出。
    """

    workspace_root = tmp_path / "fins-citation-provenance-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    processed_repository = FsProcessedDocumentRepository(workspace_root, repository_set=repository_set)
    batches = {ticker: batching_repository.begin_batch(ticker) for ticker in ("AAPL", "600519", "0700")}
    for ticker, company_id, market in (
        ("AAPL", "0000320193", "US"),
        ("600519", "600519_CNINFO", "CN"),
        ("0700", "0700_HKEX", "HK"),
    ):
        stage_company_meta_fixture(
            company_repository,
            CompanyMeta(
                company_id=company_id,
                company_name=f"{ticker} Test Company",
                ticker_identity=build_company_ticker_identity(ticker, ()),
                resolver_version="test",
                updated_at=now_iso8601(),
            ),
            batch=batches[ticker],
        )

    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["AAPL"],
        ticker="AAPL",
        document_id="fil_sec",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.SEC_EDGAR.to_storage_value(),
        processor_compatible=True,
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["600519"],
        ticker="600519",
        document_id="fil_cninfo",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.CNINFO.to_storage_value(),
        processor_compatible=True,
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["0700"],
        ticker="0700",
        document_id="fil_hkexnews",
        source_kind=SourceKind.FILING,
        ingest_method="download",
        source_provider=FinsSourceProvider.HKEXNEWS.to_storage_value(),
        processor_compatible=True,
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["AAPL"],
        ticker="AAPL",
        document_id="fil_user_upload",
        source_kind=SourceKind.FILING,
        ingest_method="upload",
        source_provider=FinsSourceProvider.USER_UPLOAD.to_storage_value(),
        processor_compatible=True,
    )
    _create_source_document_for_provenance(
        source_repository=source_repository,
        blob_repository=blob_repository,
        batch=batches["AAPL"],
        ticker="AAPL",
        document_id="mat_user_upload",
        source_kind=SourceKind.MATERIAL,
        ingest_method="upload",
        source_provider=FinsSourceProvider.USER_UPLOAD.to_storage_value(),
        processor_compatible=True,
    )
    for batch in batches.values():
        batching_repository.commit_batch(batch)
    return FinsReadRuntime(
        company_repository=company_repository,
        source_repository=source_repository,
        processed_repository=processed_repository,
        processor_registry=DefaultFinsRuntime.create(workspace_root=workspace_root).get_processor_registry(),
    )


def _build_fins_financial_html_workspace(tmp_path: Path) -> Path:
    """构造包含 HTML 10-K 的 Fins fixture 工作区。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        Fins workspace root。

    Raises:
        OSError: 文件写入失败时抛出。
    """

    workspace_root = tmp_path / "fins-financial-html-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    token = batching_repository.begin_batch("AAPL")
    try:
        stage_company_meta_fixture(
            company_repository,
            CompanyMeta(
                company_id="0000320193",
                company_name="Apple Inc.",
                ticker_identity=build_company_ticker_identity("AAPL", ()),
                resolver_version="test",
                updated_at=now_iso8601(),
            ),
            batch=token,
        )
        handle = SourceHandle(
            ticker="AAPL",
            document_id=_FINANCIAL_HTML_DOCUMENT_ID,
            source_kind=SourceKind.FILING.value,
        )
        file_meta = blob_repository.store_file(
            handle,
            _FINANCIAL_HTML_PRIMARY_DOCUMENT,
            io.BytesIO(_fixture_financial_html().encode("utf-8")),
            batch=token,
            content_type="text/html",
        )
        original_name = f"original-{_FINANCIAL_HTML_PRIMARY_DOCUMENT}"
        original_meta = blob_repository.store_file(
            handle,
            original_name,
            io.BytesIO(b"original financial upload fixture"),
            batch=token,
            content_type="text/html",
        )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id=_FINANCIAL_HTML_DOCUMENT_ID,
                internal_document_id=_FINANCIAL_HTML_DOCUMENT_ID,
                form_type="10-K",
                primary_document=_FINANCIAL_HTML_PRIMARY_DOCUMENT,
                meta={
                    "fiscal_year": 2024,
                    "fiscal_period": "FY",
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "amended": False,
                    "ingest_method": "upload",
                    "source_provider": "user_upload",
                },
                file_entries=[
                    _fresh_upload_file_entry(
                        original_meta,
                        name=original_name,
                        source="original",
                        original_filename=_FINANCIAL_HTML_PRIMARY_DOCUMENT,
                    ),
                    _fresh_upload_file_entry(
                        file_meta,
                        name=_FINANCIAL_HTML_PRIMARY_DOCUMENT,
                        source="docling",
                        original_filename=_FINANCIAL_HTML_PRIMARY_DOCUMENT,
                        derived_from=original_name,
                    ),
                ],
            ),
            SourceKind.FILING,
            batch=token,
        )
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)
    return workspace_root


def _build_fins_aapl_xbrl_workspace(
    tmp_path: Path,
    *,
    excluded_fixture_names: frozenset[str] = frozenset(),
    primary_payload_override: bytes | None = None,
) -> Path:
    """构造包含真实 AAPL XBRL fixture 的 Fins 工作区。

    Args:
        tmp_path: pytest 临时目录。
        excluded_fixture_names: 为真实缺失分支移除的可选 XBRL 关系文件名。
        primary_payload_override: 为无报表分支提供的可选主 HTML 字节。

    Returns:
        Fins workspace root。

    Raises:
        OSError: fixture 读取或仓储写入失败时抛出。
        AssertionError: fixture 元数据缺少仓储必填字段时抛出。
    """

    workspace_root = tmp_path / "fins-aapl-xbrl-workspace"
    repository_set = build_fs_repository_set(workspace_root=workspace_root)
    batching_repository = FsBatchingRepository(workspace_root, repository_set=repository_set)
    company_repository = FsCompanyMetaRepository(workspace_root, repository_set=repository_set)
    source_repository = FsSourceDocumentRepository(workspace_root, repository_set=repository_set)
    blob_repository = FsDocumentBlobRepository(workspace_root, repository_set=repository_set)
    meta = _aapl_xbrl_fixture_meta()
    internal_document_id = _fixture_meta_text(meta, "internal_document_id")
    form_type = _fixture_meta_text(meta, "form_type")
    primary_document = _fixture_meta_text(meta, "primary_document")
    source_meta = _source_meta_without_files(meta)
    token = batching_repository.begin_batch("AAPL")
    try:
        stage_company_meta_fixture(
            company_repository,
            CompanyMeta(
                company_id="0000320193",
                company_name="Apple Inc.",
                ticker_identity=build_company_ticker_identity("AAPL", ("APPLE",)),
                resolver_version="test",
                updated_at=now_iso8601(),
            ),
            batch=token,
        )
        handle = SourceHandle(
            ticker="AAPL",
            document_id=_AAPL_XBRL_DOCUMENT_ID,
            source_kind=SourceKind.FILING.value,
        )
        file_metas = []
        for file_path in _aapl_xbrl_fixture_files():
            if file_path.name in excluded_fixture_names:
                continue
            payload = (
                primary_payload_override
                if file_path.name == primary_document and primary_payload_override is not None
                else file_path.read_bytes()
            )
            file_metas.append(
                blob_repository.store_file(
                    handle,
                    file_path.name,
                    io.BytesIO(payload),
                    batch=token,
                    content_type=_fixture_content_type(file_path),
                )
            )
        source_repository.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="AAPL",
                document_id=_AAPL_XBRL_DOCUMENT_ID,
                internal_document_id=internal_document_id,
                form_type=form_type,
                primary_document=primary_document,
                meta=source_meta,
                files=file_metas,
            ),
            SourceKind.FILING,
            batch=token,
        )
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    batching_repository.commit_batch(token)
    return workspace_root


def _aapl_xbrl_fixture_meta() -> Mapping[str, JsonValue]:
    """读取 AAPL XBRL fixture 的 meta.json。

    Returns:
        JSON object 形态的 fixture 元数据。

    Raises:
        OSError: fixture 文件读取失败时抛出。
        AssertionError: meta.json 不是 JSON object 时抛出。
    """

    parsed = json.loads((_AAPL_XBRL_FIXTURE_DIR / "meta.json").read_text(encoding="utf-8"))
    assert isinstance(parsed, Mapping)
    return cast(Mapping[str, JsonValue], parsed)


def _fixture_meta_text(meta: Mapping[str, JsonValue], key: str) -> str:
    """从 fixture meta 中读取必填文本字段。

    Args:
        meta: fixture 元数据。
        key: 字段名。

    Returns:
        字段文本。

    Raises:
        AssertionError: 字段缺失或不是文本时抛出。
    """

    value = meta.get(key)
    assert isinstance(value, str)
    return value


def _source_meta_without_files(meta: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """返回去掉 files 列表后的 source meta。

    Args:
        meta: fixture 元数据。

    Returns:
        可写入仓储的 source meta。

    Raises:
        无。
    """

    return {key: value for key, value in meta.items() if key != "files"}


def _aapl_xbrl_fixture_files() -> tuple[Path, ...]:
    """列出 AAPL XBRL fixture 的业务文件。

    Returns:
        不包含 meta.json 的 fixture 文件路径。

    Raises:
        OSError: 目录遍历失败时抛出。
    """

    return tuple(
        file_path
        for file_path in sorted(_AAPL_XBRL_FIXTURE_DIR.iterdir())
        if file_path.is_file() and file_path.name != "meta.json"
    )


def _fixture_content_type(file_path: Path) -> str | None:
    """按 fixture 文件后缀返回最小 content type。

    Args:
        file_path: fixture 文件路径。

    Returns:
        content type；未知后缀返回 ``None``。

    Raises:
        无。
    """

    if file_path.suffix in {".htm", ".html"}:
        return "text/html"
    if file_path.suffix in {".xml", ".xsd"}:
        return "application/xml"
    return None


def _xbrl_fact_concept_local_name(fact: Mapping[str, JsonValue]) -> str:
    """提取 fact concept 的本地名。

    Args:
        fact: XBRL fact 载荷。

    Returns:
        去掉 taxonomy 前缀后的 concept 名；缺失时返回空字符串。

    Raises:
        无。
    """

    concept = fact.get("concept")
    if not isinstance(concept, str):
        return ""
    return concept.rsplit(":", maxsplit=1)[-1]


def _fixture_markdown() -> str:
    """返回测试财报 Markdown 内容。

    Returns:
        Markdown 文本。

    Raises:
        无。
    """

    return """# Business

Annual recurring revenue increased because Services subscriptions expanded.

## Services Margin

Services margin improved as paid subscriptions grew across the installed base.

| Metric | 2024 |
| --- | ---: |
| Revenue | 100 |
| Services margin | 42 |
"""


def _fixture_financial_html() -> str:
    """返回测试财报 HTML 内容。

    Returns:
        HTML 文本。

    Raises:
        无。
    """

    return """<html>
<body>
<h1>Apple Inc. 2024 Form 10-K</h1>
<table>
<caption>Consolidated Statements of Operations</caption>
<tr><th>Metric</th><th>2024</th><th>2023</th></tr>
<tr><td>Net sales</td><td>391035</td><td>383285</td></tr>
<tr><td>Net income</td><td>93736</td><td>96995</td></tr>
</table>
</body>
</html>
"""


def _spec(
    workspace_root: Path,
    *,
    extra_config: Mapping[str, JsonValue] | None = None,
) -> ToolsDiscoveryProviderSpec:
    """构造 Fins provider spec。

    Args:
        workspace_root: Fins workspace root。
        extra_config: 可选额外配置覆盖。

    Returns:
        provider spec。

    Raises:
        无。
    """

    config: dict[str, JsonValue] = {
        "workspace_root": str(workspace_root),
        "limits": {
            "search_document_max_items": 10,
            "list_documents_max_items": 20,
        },
    }
    if extra_config is not None:
        config.update(extra_config)
    return ToolsDiscoveryProviderSpec(
        spec_id="financial-read-tools",
        location=PythonImportPathProvider(import_path="dayu.fins.tools.provider:discover_tools"),
        enabled=True,
        config=config,
    )


def _discover_definitions(workspace_root: Path) -> tuple[ToolDefinition, ...]:
    """发现 Fins 工具定义。

    Args:
        workspace_root: Fins workspace root。

    Returns:
        工具定义元组。

    Raises:
        Exception: provider 解析失败时透出。
    """

    return discover_tools(_spec(workspace_root)).definitions


def _definitions_by_name(
    definitions: tuple[ToolDefinition, ...],
) -> dict[str, ToolDefinition]:
    """按工具名索引定义。

    Args:
        definitions: 工具定义元组。

    Returns:
        工具名字典。

    Raises:
        无。
    """

    return {definition.name: definition for definition in definitions}


def _truncate_limit(definition: ToolDefinition, limit_name: str) -> int:
    """读取工具截断声明中的限制值。

    Args:
        definition: 工具定义。
        limit_name: limit 字段名。

    Returns:
        截断限制值。

    Raises:
        AssertionError: 工具没有截断声明或限制值不是整数时抛出。
    """

    truncate = definition.truncate
    assert isinstance(truncate, ToolTruncateSpec)
    limit = truncate.limits[limit_name]
    assert isinstance(limit, int)
    return limit


def _assert_host_cancelled_outcome(
    outcome: ToolExecutionOutcome,
    tool_name: str,
) -> None:
    """断言工具调用返回 Host cancelled outcome。

    Args:
        outcome: 工具执行结果。
        tool_name: 预期工具名。

    Returns:
        无。

    Raises:
        AssertionError: outcome 类型、reason 或 meta 不符合预期时抛出。
    """

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == tool_name
    assert outcome.meta.started_at <= outcome.meta.finished_at
    _assert_host_governance_terms_hidden(outcome)


def _assert_host_governance_terms_hidden(outcome: ToolCancelledOutcome) -> None:
    """断言 cancelled outcome 的 LLM-facing 文本不含 Host 治理标识。

    Args:
        outcome: 要检查的 cancelled outcome。

    Returns:
        无。

    Raises:
        AssertionError: message 或 hint 泄漏治理标识时抛出。
    """

    llm_facing_texts = (outcome.message, outcome.hint or "")
    for text in llm_facing_texts:
        for forbidden_term in _HOST_GOVERNANCE_FORBIDDEN_TERMS:
            assert forbidden_term not in text


def _module_imports(path: Path) -> set[str]:
    """解析 Python 文件里的 import 目标模块。

    Args:
        path: Python 源文件路径。

    Returns:
        import 语句引用的模块名集合。

    Raises:
        SyntaxError: 源文件语法非法时抛出。
        OSError: 文件读取失败时抛出。
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
            for alias in node.names:
                if alias.name != "*":
                    modules.add(f"{node.module}.{alias.name}")
    return modules


def _is_forbidden_import(module_name: str, forbidden_roots: tuple[str, ...]) -> bool:
    """判断 import 目标是否命中禁用根模块。

    Args:
        module_name: AST 解析出的模块名。
        forbidden_roots: 禁止依赖的根模块集合。

    Returns:
        命中禁用根模块或其子模块时返回 ``True``。

    Raises:
        无。
    """

    return any(module_name == root or module_name.startswith(f"{root}.") for root in forbidden_roots)


def _fins_forbidden_import_roots(path: Path) -> tuple[str, ...]:
    """返回指定 Fins 源文件适用的禁用 import 根模块。

    Args:
        path: Fins 源文件路径。

    Returns:
        禁用 import 根模块元组。

    Raises:
        无。
    """

    if path.resolve(strict=False) == _FINS_WAIT_ADAPTER_PATH:
        return _FINS_WAIT_ADAPTER_FORBIDDEN_IMPORT_ROOTS
    return _FINS_DEFAULT_FORBIDDEN_IMPORT_ROOTS


def _build_process_target(
    workspace_root: Path,
    tool_name: str,
    arguments: Mapping[str, JsonValue],
) -> ProcessBackedToolTarget:
    """从真实 Fins provider 定义构造 process-backed target。

    Args:
        workspace_root: Fins workspace root。
        tool_name: 工具名。
        arguments: 工具参数。

    Returns:
        可序列化 process-backed target。

    Raises:
        AssertionError: 工具未声明 process-backed execution 时抛出。
    """

    definitions = _definitions_by_name(_discover_definitions(workspace_root))
    factory = _process_target_factory(definitions[tool_name])
    return factory.build_process_target(
        _call(tool_name, arguments),
        _process_context(),
    )


def _raise_unexpected_process_target_failure(
    *,
    tool_name: str,
    call: ToolCallRequest,
    parameters: ToolParametersSchema,
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """在 process target 业务执行阶段注入未预期失败。

    Args:
        tool_name: 当前工具名。
        call: 当前工具调用。
        parameters: 当前工具参数 schema。
        read_runtime: target 创建的 read runtime。
        limits: 当前 Fins 工具 limits。
        cancellation_token: process target 的取消观察 token。

    Returns:
        不返回。

    Raises:
        RuntimeError: 始终抛出测试 sentinel。
    """

    del tool_name, call, parameters, read_runtime, limits, cancellation_token
    raise RuntimeError("unexpected process target execution failure")


def _process_target_factory(
    definition: ToolDefinition,
) -> ProcessBackedToolTargetFactory:
    """读取工具定义中的 process-backed target factory。

    Args:
        definition: Fins read 工具定义。

    Returns:
        process-backed target factory。

    Raises:
        AssertionError: 工具未声明 process-backed execution 时抛出。
    """

    execution = definition.execution
    assert isinstance(execution, ProcessBackedToolExecutionCapability)
    return execution.target_factory


def _process_context() -> ProcessBackedToolContext:
    """构造 process-backed target factory 测试上下文。

    Args:
        无。

    Returns:
        可序列化 process-backed 上下文。

    Raises:
        无。
    """

    return ProcessBackedToolContext(
        run_id="run-fins",
        session_id="session-fins",
        iteration_id="iteration-fins",
        timeout_seconds=30.0,
        correlation_id="correlation-fins",
    )


def _completed_envelope_value(envelope: JsonValue) -> JsonValue:
    """读取 process-backed completed 信封的 value。

    Args:
        envelope: process target 返回的 JSON 信封。

    Returns:
        completed value。

    Raises:
        AssertionError: 信封不是 completed 形态时抛出。
    """

    assert isinstance(envelope, Mapping)
    assert envelope.get("status") == "completed"
    value = envelope.get("value")
    assert value is not None
    return value


def _project_llm_facing_outcome(outcome: ToolExecutionOutcome) -> JsonValue:
    """把 read tool outcome 投影为实际进入 LLM 上下文的 JSON 字段。

    Args:
        outcome: completed、failed 或 cancelled outcome。

    Returns:
        LLM-facing JSON projection。

    Raises:
        AssertionError: 测试意外收到 awaiting outcome 时抛出。
    """

    if isinstance(outcome, ToolCompletedOutcome):
        return {"status": "completed", "value": outcome.result.value}
    if isinstance(outcome, ToolFailedOutcome):
        return {
            "status": "failed",
            "error": outcome.result.error,
            "message": outcome.result.message,
            "hint": outcome.result.hint,
        }
    if isinstance(outcome, ToolCancelledOutcome):
        return {
            "status": "cancelled",
            "reason": outcome.reason,
            "message": outcome.message,
            "hint": outcome.hint,
        }
    raise AssertionError("read tool 不应返回 awaiting outcome")


def _assert_read_output_has_no_storage_details(
    value: JsonValue,
    *,
    forbidden_values: tuple[str, ...],
) -> None:
    """递归断言 read output nested key/value 不含 storage 私有细节。

    Args:
        value: 待检查 JSON 值。
        forbidden_values: 当前真实 workspace 的 revision/key/path 值。

    Returns:
        无。

    Raises:
        AssertionError: nested key/value 命中私有语义时抛出。
    """

    forbidden_key_fragments = (
        "revision",
        "storagekey",
        "internalkey",
        "localuri",
        "temppath",
    )
    forbidden_text_fragments = (
        "local://",
        "repo_batches",
        "repo_backups",
        "batch_locks",
    )
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = "".join(character for character in key.casefold() if character.isalnum())
            assert all(fragment not in normalized_key for fragment in forbidden_key_fragments)
            _assert_read_output_has_no_storage_details(
                nested,
                forbidden_values=forbidden_values,
            )
        return
    if isinstance(value, list):
        for nested in value:
            _assert_read_output_has_no_storage_details(
                nested,
                forbidden_values=forbidden_values,
            )
        return
    if not isinstance(value, str):
        return
    assert all(fragment not in value for fragment in forbidden_text_fragments)
    assert all(forbidden not in value for forbidden in forbidden_values)


async def _run_process_capsule(
    target: ProcessBackedToolTarget,
) -> ToolExecutionOutcome:
    """运行真实 process-backed capsule 并释放子进程资源。

    Args:
        target: 可序列化 process-backed target。

    Returns:
        工具 outcome。

    Raises:
        Exception: capsule run / close 失败时透出。
    """

    capsule = ProcessBackedToolExecutionCapsule(target)
    try:
        return await capsule.run()
    finally:
        await capsule.close()


async def _run_fins_process_tool_and_cancel(
    runtime: ToolRuntimeHandle,
    token: _ManualCancellationToken,
) -> ToolExecutionOutcome:
    """启动真实 Fins read process-backed 调用并触发 Host 取消。

    Args:
        runtime: 由真实 Fins provider 构造的 ToolRuntime。
        token: 可手动取消的测试 token。

    Returns:
        单条工具 outcome。

    Raises:
        asyncio.TimeoutError: 工具运行未在测试预算内完成时抛出。
    """

    task = asyncio.create_task(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call(
                        "search_document",
                        {
                            "ticker": "AAPL",
                            "document_id": "aapl-2024-10k",
                            "query": "annual recurring revenue",
                            "mode": "keyword",
                        },
                    ),
                ),
                context=_context(cancellation_token=token),
            )
        )
    )
    await asyncio.sleep(0.01)
    token.cancel()
    response = await asyncio.wait_for(task, timeout=2.0)
    return response.records[0].outcome


def _assert_path_free_storage_os_error(
    error: OSError,
    *,
    expected_errno: int,
    workspace_root: Path,
    private_locators: tuple[str, ...],
) -> None:
    """断言 storage 投影的 OSError 保留类别/errno/cause 且不含 locator。

    Args:
        error: public storage boundary 抛出的异常。
        expected_errno: 底层真实或注入异常的 errno。
        workspace_root: 必须从 message/args 排除的 workspace 根。
        private_locators: 必须从 message/args 排除的实际私有 locator。

    Returns:
        无。

    Raises:
        AssertionError: 异常语义或 non-leak contract 不成立时抛出。
    """

    pending: list[BaseException] = [error]
    visited_ids: set[int] = set()
    serialized_parts: list[str] = []
    while pending:
        node = pending.pop()
        node_id = id(node)
        if node_id in visited_ids:
            continue
        visited_ids.add(node_id)
        try:
            notes = tuple(node.__notes__)
        except AttributeError:
            notes = ()
        serialized_parts.extend(
            (
                node.__class__.__name__,
                str(node),
                repr(node.args),
                repr(notes),
                "".join(traceback.format_exception(node)),
            )
        )
        if node.__cause__ is not None:
            pending.append(node.__cause__)
        if node.__context__ is not None:
            pending.append(node.__context__)
    serialized = "\n".join(serialized_parts)
    assert error.errno == expected_errno
    assert error.filename is None
    assert error.filename2 is None
    assert error.__context__ is None
    assert str(workspace_root) not in serialized
    assert all(locator not in serialized for locator in private_locators)
    assert isinstance(error.__cause__, OSError)
    assert error.__cause__.errno == expected_errno


def _tool_runtime(
    workspace_root: Path,
    *,
    extra_config: Mapping[str, JsonValue] | None = None,
    enable_truncation_manager: bool = False,
) -> tuple[ToolRuntimeHandle, _AcceptingPort]:
    """构造当前 ToolRuntime。

    Args:
        workspace_root: Fins workspace root。
        extra_config: 原样传给真实 Fins provider 的可选配置。
        enable_truncation_manager: 是否通过公开 policy 启用截断与续读工具。

    Returns:
        ToolRuntime 与 accept port。

    Raises:
        Exception: 构造失败时透出。
    """

    output = discover_tools(_spec(workspace_root, extra_config=extra_config))
    accepting_port = _AcceptingPort()
    framework_tool_policy = default_framework_tool_policy_view()
    if enable_truncation_manager:
        framework_tool_policy = FrameworkToolPolicyView(
            reserved_framework_tool_names=frozenset({FrameworkToolName.FETCH_MORE}),
            enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
        )
    runtime = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=output.definitions),
                source_refs=output.source_refs,
                framework_tool_policy=framework_tool_policy,
                policy_snapshot_digest="sha256:" + "3" * 64,
                enable_truncation_manager=enable_truncation_manager,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id="session-fins",
                run_id="run-fins",
                attempt_id="attempt-fins",
                execution_id="execution-fins",
                allow_tool_calls=True,
            ),
            accept_port=accepting_port,
        )
    )
    return runtime, accepting_port


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    Args:
        name: 工具名。
        arguments: 工具参数。

    Returns:
        工具调用请求。

    Raises:
        无。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _definitions_for_read_runtime(
    read_runtime: FinsReadRuntime,
    workspace_root: Path,
) -> tuple[ToolDefinition, ...]:
    """为指定 read runtime 构造 Fins read 工具定义。

    Args:
        read_runtime: 已构造的 Fins read runtime。
        workspace_root: Fins workspace root。

    Returns:
        工具定义元组。

    Raises:
        Exception: 工具声明构造失败时透出。
    """

    return build_fins_read_tool_definitions(
        read_runtime=read_runtime,
        workspace_root=workspace_root,
        limits=FinsToolLimits(),
    )


async def _run_two_fins_read_tools_concurrently(
    definitions: dict[str, ToolDefinition],
    entered: Event,
) -> None:
    """并发执行两个同 provider Fins read tools。

    Args:
        definitions: 按工具名索引的工具定义。
        entered: 第一个业务体进入信号。

    Returns:
        无。

    Raises:
        AssertionError: 任一工具未成功完成时抛出。
    """

    first = asyncio.create_task(
        definitions["list_documents"].callable(
            _call("list_documents", {"ticker": "AAPL"}),
            _context(),
        )
    )
    await asyncio.to_thread(entered.wait, 1.0)
    second = asyncio.create_task(
        definitions["get_document_sections"].callable(
            _call(
                "get_document_sections",
                {"ticker": "AAPL", "document_id": "aapl-2024-10k"},
            ),
            _context(),
        )
    )
    outcomes = await asyncio.gather(first, second)
    assert all(isinstance(outcome, ToolCompletedOutcome) for outcome in outcomes)


def _install_processor(
    read_runtime: FinsReadRuntime,
    processor: DocumentProcessor,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cancel_token_after_create: _ManualCancellationToken | None = None,
) -> None:
    """把 read runtime 的 processor factory 替换为测试 processor。

    Args:
        read_runtime: 要安装 fake processor 的 Fins read runtime。
        processor: 测试 processor。
        monkeypatch: pytest monkeypatch fixture。
        cancel_token_after_create: 可选 token；返回 processor 后立即标记取消。

    Returns:
        无。

    Raises:
        Exception: monkeypatch 失败时透出。
    """

    def create_with_fallback(
        *,
        source: Source,
        form_type: str | None = None,
        media_type: str | None = None,
    ) -> DocumentProcessor:
        """返回指定测试 processor。

        Args:
            source: 文档来源。
            form_type: 文档类型。
            media_type: 媒体类型。

        Returns:
            测试 processor。

        Raises:
            无。
        """

        del source, form_type, media_type
        if cancel_token_after_create is not None:
            cancel_token_after_create.cancel()
        return processor

    monkeypatch.setattr(
        read_runtime._processor_registry,
        "create_with_fallback",
        create_with_fallback,
    )


def _raise_fins_cancelled_during_semantic_enrichment(
    *,
    sections: list[SectionSummary],
    form_type: str | None,
    cancellation_token: CancellationToken | None = None,
) -> list[dict[str, JsonValue]]:
    """在 search_document 语义增强块内抛出 Fins 取消错误。

    Args:
        sections: 调用方传入的章节摘要列表。
        form_type: 文档类型。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        不返回。

    Raises:
        FinsReadCancelledError: 始终抛出。
    """

    del sections, form_type, cancellation_token
    raise FinsReadCancelledError(
        message="语义增强已取消。",
        hint="当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。",
    )


def _context(cancellation_token: CancellationToken | None = None) -> BatchToolExecutionContext:
    """构造批执行上下文。

    Args:
        cancellation_token: 可选取消 token；未提供时使用未取消 token。

    Returns:
        批执行上下文。

    Raises:
        无。
    """

    return BatchToolExecutionContext(
        run_id="run-fins",
        session_id="session-fins",
        iteration_id="iteration-fins",
        timeout_seconds=30.0,
        cancellation_token=cancellation_token or _OpenCancellationToken(),
        correlation_id="correlation-fins",
    )
