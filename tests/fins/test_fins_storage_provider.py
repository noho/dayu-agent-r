"""Fins storage 与 read tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import io
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
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
from dayu.fins.tools.provider import discover_tools
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


def test_fins_provider_can_disable_read_tools_without_workspace_root(tmp_path: Path) -> None:
    """关闭 read tools 时 provider 不应解析 workspace_root。"""

    result = discover_tools(
        _spec(
            tmp_path,
            extra_config={
                "workspace_root": None,
                "include_read_tools": False,
            },
        )
    )

    assert result.definitions == ()


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


def test_read_provider_ignores_legacy_ingestion_switch(tmp_path: Path) -> None:
    """旧 include_ingestion_tools 开关不得让 read provider 暴露 ingestion tools。"""

    workspace_root = _build_fins_workspace(tmp_path)
    spec = _spec(
        workspace_root,
        extra_config={"include_ingestion_tools": True},
    )

    output = discover_tools(spec)

    assert tuple(definition.name for definition in output.definitions) == _FINS_READ_TOOL_NAMES


def test_fins_workspace_root_must_be_explicit_absolute_path() -> None:
    """workspace_root 不得从 cwd 或环境隐式解析。"""

    spec = ToolsDiscoveryProviderSpec(
        spec_id="financial-tools",
        location=PythonImportPathProvider(import_path="dayu.fins.tools:discover_tools"),
        enabled=True,
        allow_empty=False,
        config={
            "workspace_root": "workspace/fins",
            "include_read_tools": True,
            "include_ingestion_tools": False,
            "limits": {},
        },
    )

    with pytest.raises(ValueError, match="absolute"):
        discover_tools(spec)


def test_fins_import_boundaries_do_not_reverse_depend() -> None:
    """Fins imports 不得引入 Host/Service/UI/Engine 反向依赖。"""

    forbidden = ("dayu.engine", "dayu.host", "dayu.service", "dayu.ui")
    offenders: list[str] = []
    for path in Path("dayu/fins").rglob("*.py"):
        imported_modules = _module_imports(path)
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
        "include_read_tools": True,
        "include_ingestion_tools": False,
        "limits": {
            "search_document_max_items": 10,
            "list_documents_max_items": 20,
        },
    }
    if extra_config is not None:
        config.update(extra_config)
    return ToolsDiscoveryProviderSpec(
        spec_id="financial-tools",
        location=PythonImportPathProvider(import_path="dayu.fins.tools:discover_tools"),
        enabled=True,
        allow_empty=False,
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


def _context() -> BatchToolExecutionContext:
    """构造批执行上下文。

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
        cancellation_token=_OpenCancellationToken(),
        correlation_id="correlation-fins",
    )
