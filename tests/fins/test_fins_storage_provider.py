"""Fins storage 与 read tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import io
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from threading import Event, Lock
from typing import Final, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
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
from dayu.documents.processors.source import Source
from dayu.fins.domain.document_models import (
    CompanyMeta,
    SourceDocumentUpsertRequest,
    now_iso8601,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import (
    FsBatchingRepository,
    FsCompanyMetaRepository,
    FsDocumentBlobRepository,
    FsSourceDocumentRepository,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.fins_limits import FinsToolLimits
from dayu.fins.tools.fins_tools import build_fins_read_tool_definitions
from dayu.fins.tools.provider import discover_tools
from dayu.fins.tools.read_runtime import FinsReadRuntime
from dayu.fins.tools.read_runtime_helpers import FinsReadCancelledError
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
)
from dayu.host.tooling import default_framework_tool_policy_view
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
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FINS_WAIT_ADAPTER_PATH = (
    _REPO_ROOT / "dayu" / "fins" / "ingestion" / "wait_adapter.py"
).resolve(strict=False)
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
        }


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


def test_fins_provider_discovers_read_tools_with_fins_tag(tmp_path: Path) -> None:
    """Provider 应发现带 fins tag 的 read tools。"""

    workspace_root = _build_fins_workspace(tmp_path)
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=_spec(workspace_root), provider=discover_tools),)
    )

    assert tuple(definition.name for definition in result.tool_bundle.definitions) == _FINS_READ_TOOL_NAMES
    assert all("fins" in definition.tags for definition in result.tool_bundle.definitions)


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

    assert tuple(definition.name for definition in definitions) == _FINS_READ_TOOL_NAMES
    for definition in definitions:
        properties = definition.schema.function.parameters.properties
        required = definition.schema.function.parameters.required
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "execution_context" not in required
        assert "cancellation_token" not in required


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
    definitions = _definitions_by_name(_definitions_for_read_runtime(read_runtime))

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
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime))["search_document"]

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
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime))["search_document"]

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
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime))["read_section"]

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
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime))["read_section"]

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
    definition = _definitions_by_name(_definitions_for_read_runtime(read_runtime))["query_xbrl_facts"]

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
    definitions = _definitions_by_name(_definitions_for_read_runtime(read_runtime))

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


def test_same_ticker_batch_fails_fast_across_independent_repository_cores(tmp_path: Path) -> None:
    """同 workspace 独立仓储 core 的同 ticker 活动 batch 应保持 fail-fast 语义。"""

    workspace_root = tmp_path / "fins-workspace"
    first_repository_set = build_fs_repository_set(workspace_root=workspace_root)
    first_repository = FsBatchingRepository(workspace_root, repository_set=first_repository_set)
    first_token = first_repository.begin_batch("AAPL")

    second_repository_set = build_fs_repository_set(workspace_root=workspace_root)
    second_repository = FsBatchingRepository(workspace_root, repository_set=second_repository_set)
    with pytest.raises(RuntimeError, match="ticker=AAPL 已存在跨进程活动 batch"):
        second_repository.begin_batch("AAPL")

    first_repository.rollback_batch(first_token)
    second_token = second_repository.begin_batch("AAPL")
    second_repository.rollback_batch(second_token)


def test_fins_workspace_root_must_be_explicit_absolute_path() -> None:
    """workspace_root 不得从 cwd 或环境隐式解析。"""

    spec = ToolsDiscoveryProviderSpec(
        spec_id="financial-read-tools",
        location=PythonImportPathProvider(
            import_path="dayu.fins.tools.provider:discover_tools"
        ),
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
    company_repository.upsert_company_meta(
        CompanyMeta(
            company_id="0000320193",
            company_name="Apple Inc.",
            ticker="AAPL",
            market="US",
            resolver_version="test",
            updated_at=now_iso8601(),
            ticker_aliases=["APPLE"],
        )
    )
    token = batching_repository.begin_batch("AAPL")
    try:
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
                },
            ),
            SourceKind.FILING,
        )
        handle = source_repository.get_source_handle("AAPL", "aapl-2024-10k", SourceKind.FILING)
        file_meta = blob_repository.store_file(
            handle,
            "aapl-2024-10k.md",
            io.BytesIO(_fixture_markdown().encode("utf-8")),
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
                },
                files=[file_meta],
            ),
            SourceKind.FILING,
        )
        batching_repository.commit_batch(token)
    except Exception:
        batching_repository.rollback_batch(token)
        raise
    return workspace_root


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
        location=PythonImportPathProvider(
            import_path="dayu.fins.tools.provider:discover_tools"
        ),
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

    return any(
        module_name == root or module_name.startswith(f"{root}.")
        for root in forbidden_roots
    )


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


def _tool_runtime(workspace_root: Path) -> tuple[ToolRuntimeHandle, _AcceptingPort]:
    """构造当前 ToolRuntime。

    Args:
        workspace_root: Fins workspace root。

    Returns:
        ToolRuntime 与 accept port。

    Raises:
        Exception: 构造失败时透出。
    """

    output = discover_tools(_spec(workspace_root))
    accepting_port = _AcceptingPort()
    runtime = DefaultToolRuntimeFactory(
        EffectiveToolBundleBuilder()
    ).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=output.definitions),
                source_refs=output.source_refs,
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest="sha256:" + "3" * 64,
                enable_truncation_manager=False,
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


def _definitions_for_read_runtime(read_runtime: FinsReadRuntime) -> tuple[ToolDefinition, ...]:
    """为指定 read runtime 构造 Fins read 工具定义。

    Args:
        read_runtime: 已构造的 Fins read runtime。

    Returns:
        工具定义元组。

    Raises:
        Exception: 工具声明构造失败时透出。
    """

    return build_fins_read_tool_definitions(
        read_runtime=read_runtime,
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
        hint="当前工具调用已停止；等待新的用户指令或后续调度。",
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
