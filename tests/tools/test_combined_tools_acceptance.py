"""Doc / Fins / Web 工具的 combined discovery 与 ToolRuntime 验收测试。"""

from __future__ import annotations

import ast
import asyncio
import io
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
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
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_schema import ToolTruncateSpec
from dayu.contracts.tool_source import ToolBundleSourceRef
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
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    FetchMoreToolCallable,
    HostEventRef,
    HostToolFactAcceptPort,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptedAck,
    ToolRuntimeHandle,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
)
from dayu.host.tooling import FrameworkToolName, FrameworkToolPolicyView
from dayu.runtime.config_loader import ConfigLoader
from dayu.runtime.location import resolve_runtime_locations
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    ScenePrepareRequest,
    SceneToolCatalog,
    SceneToolSelectionMode,
    SceneToolSelectionResult,
    prepare_scene,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceDiscoveredTools,
    ServiceOpenHostAssemblyRequest,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    discover_service_tools,
)
from dayu.tools.web import web_tools

_PACKAGE_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "dayu" / "config"
_DOC_TOOL_NAMES: Final[tuple[str, ...]] = (
    "list_files",
    "get_file_sections",
    "search_files",
    "read_file",
    "read_file_section",
)
_FINS_TOOL_NAMES: Final[tuple[str, ...]] = (
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
_FINS_AWAITING_TOOL_NAMES: Final[tuple[str, ...]] = (
    "start_fins_download",
    "start_fins_preprocess",
    "start_fins_upload",
)
_WEB_TOOL_NAMES: Final[tuple[str, ...]] = ("search_web", "fetch_web_page")
_FORBIDDEN_IMPORT_ROOTS: Final[tuple[str, ...]] = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tools.fetch_more",
)
_FORBIDDEN_PROJECTION_TOKENS: Final[tuple[str, ...]] = (
    "project_for_llm",
    "fetch_more_args",
    "continuation_hint",
)


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _AcceptingPort(HostToolFactAcceptPort):
    """记录 ToolRuntime 交给 Host accept barrier 的候选事实。"""

    def __init__(self) -> None:
        """初始化候选事实记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self,
        candidate: ToolFactAcceptCandidate,
    ) -> ToolFactAcceptResult:
        """接受工具事实候选。

        :param candidate: ToolRuntime 构造的工具事实候选。
        :returns: accepted ack。
        :raises Exception: 不主动抛出异常。
        """

        self.candidates.append(candidate)
        sequence = len(self.candidates)
        requested_ref = HostEventRef(
            event_id=f"combined-tool-call-requested-{sequence}",
            event_sequence=sequence * 2 - 1,
        )
        result_ref = HostEventRef(
            event_id=f"combined-tool-result-accepted-{sequence}",
            event_sequence=sequence * 2,
        )
        return ToolFactAcceptedAck(
            accepted_event_refs=(requested_ref, result_ref),
            tool_fact_id=f"combined-tool-fact-{sequence}",
            tool_call_requested_event_ref=requested_ref,
            tool_call_governed_event_ref=None,
            tool_result_event_ref=result_ref,
            result_payload_ref=None,
            result_digest=f"sha256:{'6' * 64}",
            reuse_prior_event_refs=(),
            diagnostic_refs=(),
            idempotency_record_ref=f"combined-idempotency-{sequence}",
        )


def test_combined_discovery_returns_single_bundle_without_reserved_names(
    tmp_path: Path,
) -> None:
    """Doc / Fins / Web provider 必须被同一个 ToolsDiscovery 聚合。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: bundle 名称重复或包含 reserved framework 名称时抛出。
    """

    discovered_tools = _discover_combined_tools(tmp_path)
    names = tuple(definition.name for definition in discovered_tools.tool_bundle.definitions)

    assert names == (
        *_FINS_TOOL_NAMES,
        *_FINS_AWAITING_TOOL_NAMES,
        *_DOC_TOOL_NAMES,
        *_WEB_TOOL_NAMES,
    )
    assert len(names) == len(set(names))
    assert FrameworkToolName.FETCH_MORE.value not in names
    assert len(discovered_tools.source_refs) == 6
    for definition in discovered_tools.tool_bundle.definitions:
        properties = definition.schema.function.parameters.properties
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "execution_context" not in definition.schema.function.parameters.required
        assert "cancellation_token" not in definition.schema.function.parameters.required


def test_combined_truncate_specs_and_fetch_more_owner(tmp_path: Path) -> None:
    """当前工具只暴露 current ToolTruncateSpec，fetch_more 由 ToolRuntime 注入。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 截断声明或 fetch_more owner 错误时抛出。
    """

    discovered_tools = _discover_combined_tools(tmp_path)
    truncating_definitions = tuple(
        definition
        for definition in discovered_tools.tool_bundle.definitions
        if definition.truncate is not None
    )
    runtime, _accept_port = _tool_runtime(discovered_tools.tool_bundle, discovered_tools.source_refs)

    assert truncating_definitions
    for definition in truncating_definitions:
        assert type(definition.truncate) is ToolTruncateSpec
    assert FrameworkToolName.FETCH_MORE.value not in _definition_names(
        discovered_tools.tool_bundle.definitions
    )
    assert FrameworkToolName.FETCH_MORE in runtime.effective_bundle.injected_framework_tool_names
    fetch_more = runtime.effective_bundle.definitions_by_name[FrameworkToolName.FETCH_MORE.value]
    assert fetch_more.schema in runtime.tool_schemas
    assert isinstance(fetch_more.callable, FetchMoreToolCallable)
    assert fetch_more.callable is runtime.effective_bundle.fetch_more_callable


def test_native_providers_do_not_import_old_runtime() -> None:
    """当前原生 provider 不得导入 OLD registry/truncation/fetch_more 投影。

    :returns: ``None``。
    :raises AssertionError: AST import 或旧投影 token 命中时抛出。
    """

    offenders: list[str] = []
    for source_path in _native_tool_source_paths():
        imported_modules = _module_imports(source_path)
        for module_name in imported_modules:
            if _is_forbidden_import(module_name):
                offenders.append(f"{source_path}:{module_name}")
        source = source_path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_PROJECTION_TOKENS:
            if token in source:
                offenders.append(f"{source_path}:{token}")

    assert offenders == []


def test_compose_open_host_options_passes_effective_bundle_to_host(
    tmp_path: Path,
) -> None:
    """Service assembly 必须把 effective ToolBundle 传给 HostToolingOptions。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: Host opener 收到的工具 bundle 不是 effective bundle 时抛出。
    """

    _write_combined_tool_discovery_overlay(tmp_path)
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=tmp_path / "workspace" / "config"
    )
    locations = resolve_runtime_locations(
        project_root=tmp_path,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    effective_provider_configs = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=tmp_path,
    )
    discovered_tools = discover_service_tools(effective_provider_configs)
    scene_inputs = _prepared_scene_inputs()

    result = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=tmp_path,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id="local",
                execution_profile_id="standard-256k",
                model_id="deepseek-v4-flash",
                runner_option_hint_id="interactive",
            ),
            env={"DEEPSEEK_API_KEY": "test-provider-key"},
        )
    )

    assert result.options.tooling_options is not None
    assert result.options.tooling_options.business_tool_bundle is result.effective_tool_bundle
    assert result.options.tooling_options.source_refs == discovered_tools.source_refs
    assert result.effective_tool_bundle.definitions
    for definition in result.effective_tool_bundle.definitions:
        if definition.truncate is not None:
            assert type(definition.truncate) is ToolTruncateSpec


def test_toolruntime_executes_representative_provider_tools_and_accepts_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ToolRuntime 应执行 Doc / Fins / Web 代表工具并记录 accepted facts。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 任一 provider outcome 或 accept 事实不符合预期时抛出。
    """

    search_calls: list[Mapping[str, JsonValue]] = []
    search_tokens: list[CancellationToken | None] = []

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """返回确定性 Web 搜索结果。

        :param kwargs: search_web 投影后的关键字参数。
        :returns: 当前工具成功响应。
        :raises Exception: 不主动抛出异常。
        """

        search_calls.append(kwargs)
        search_tokens.append(cast(CancellationToken | None, kwargs.get("cancellation_token")))
        return {
            "query": "AAPL revenue",
            "domains": ["sec.gov"],
            "total": 1,
            "preferred_result": {
                "title": "AAPL 10-K",
                "url": "https://www.sec.gov/Archives/aapl-2024-10k.htm",
                "snippet": "annual report",
                "published_date": "",
            },
            "preferred_result_summary": "AAPL 10-K annual report",
            "next_action": "fetch_web_page",
            "next_action_args": {"url": "https://www.sec.gov/Archives/aapl-2024-10k.htm"},
            "hint": "fetch the preferred result",
            "results": [
                {
                    "title": "AAPL 10-K",
                    "url": "https://www.sec.gov/Archives/aapl-2024-10k.htm",
                    "snippet": "annual report",
                    "published_date": "",
                }
            ],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    doc_file = _write_doc_fixture(tmp_path)
    discovered_tools = _discover_combined_tools(tmp_path)
    runtime, accept_port = _tool_runtime(discovered_tools.tool_bundle, discovered_tools.source_refs)
    context = _context()

    response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call("read_file", {"file_path": str(doc_file)}),
                    _call("list_documents", {"ticker": "AAPL"}),
                    _call(
                        "search_web",
                        {
                            "query": "AAPL revenue",
                            "domains": ["sec.gov"],
                            "recency_days": 7.0,
                            "max_results": 3.0,
                        },
                    ),
                ),
                context=context,
            )
        )
    )

    outcomes = tuple(record.outcome for record in response.records)
    assert len(accept_port.candidates) == 3
    assert tuple(candidate.call.tool_name for candidate in accept_port.candidates) == (
        "read_file",
        "list_documents",
        "search_web",
    )
    assert all(isinstance(outcome, ToolCompletedOutcome) for outcome in outcomes)
    doc_value = _mapping_value(cast(ToolCompletedOutcome, outcomes[0]).result.value)
    fins_value = _mapping_value(cast(ToolCompletedOutcome, outcomes[1]).result.value)
    web_value = _mapping_value(cast(ToolCompletedOutcome, outcomes[2]).result.value)
    assert doc_value["file_path"] == str(doc_file.resolve())
    assert "Revenue grew quickly." in str(doc_value["content"])
    assert fins_value["matched"] == 1
    assert web_value["total"] == 1
    assert "ok" not in doc_value
    assert "ok" not in fins_value
    assert "ok" not in web_value
    assert search_calls[0]["recency_days"] == 7
    assert search_calls[0]["max_results"] == 3
    assert search_tokens == [context.cancellation_token]
    assert runtime.tool_schemas == runtime.effective_bundle.tool_schemas
    assert runtime.effective_bundle.business_bundle is discovered_tools.tool_bundle


def test_representative_failures_project_to_current_failed_outcomes(
    tmp_path: Path,
) -> None:
    """代表性参数失败必须投影为 current ToolFailedOutcome。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 失败 outcome 仍带旧 envelope 或错误码不对时抛出。
    """

    doc_file = _write_doc_fixture(tmp_path)
    discovered_tools = _discover_combined_tools(tmp_path)
    runtime, accept_port = _tool_runtime(discovered_tools.tool_bundle, discovered_tools.source_refs)

    response = asyncio.run(
        runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call(
                        "read_file",
                        {
                            "file_path": str(doc_file),
                            "start_line": 8,
                            "end_line": 1,
                        },
                    ),
                    _call(
                        "search_document",
                        {
                            "ticker": "AAPL",
                            "document_id": "aapl-2024-10k",
                            "query": "revenue",
                            "queries": ["margin"],
                        },
                    ),
                    _call("search_web", {"max_results": 3}),
                ),
                context=_context(),
            )
        )
    )

    outcomes = tuple(record.outcome for record in response.records)
    assert len(accept_port.candidates) == 3
    assert all(isinstance(outcome, ToolFailedOutcome) for outcome in outcomes)
    assert cast(ToolFailedOutcome, outcomes[0]).result.ok is False
    assert cast(ToolFailedOutcome, outcomes[1]).result.error == "invalid_argument"
    assert cast(ToolFailedOutcome, outcomes[2]).result.error == "invalid_argument"


def test_scene_prepare_tags_select_doc_fins_and_web_tools(tmp_path: Path) -> None:
    """ScenePrepare 应能通过 doc/fins/web tags 选择当前工具。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: tag 选择结果未覆盖三个 provider 时抛出。
    """

    discovered_tools = _discover_combined_tools(tmp_path)
    manifest_root = tmp_path / "manifests"
    _write_json(
        manifest_root / "combined_tools.json",
        {
            "schema_version": 1,
            "scene": "combined_tools",
            "version": "v1",
            "description": "combined tools selection",
            "capability_tags": ["combined-tools"],
            "extends": [],
            "model": {"default_model_id": "deepseek-v4-flash"},
            "tool_selection": {
                "mode": "select",
                "tool_names": [],
                "tool_tags_any": ["doc", "fins", "web"],
            },
            "defaults": {"missing_required_fragment": "fail_closed"},
            "fragments": [],
            "context_slots": [],
        },
    )

    result = prepare_scene(
        ScenePrepareRequest(
            scene_id="combined_tools",
            scene_manifest_root=manifest_root,
            prompt_asset_root=tmp_path / "prompts",
            context_slot_values={},
            available_tools=SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle),
        )
    )

    selected = result.tool_selection.tool_names
    assert selected is not None
    assert "read_file" in selected
    assert "list_documents" in selected
    assert "search_web" in selected


def test_web_provider_serial_policy_holds_under_concurrent_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Web provider 的 SERIAL_PER_PROVIDER 策略应序列化并发 callable。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 并发执行进入同一 provider 临界区时抛出。
    """

    active_calls = 0
    max_active_calls = 0

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录并发进入次数并返回确定性结果。

        :param kwargs: search_web 投影后的关键字参数。
        :returns: 当前工具成功响应。
        :raises AssertionError: 参数未包含查询时抛出。
        """

        nonlocal active_calls, max_active_calls
        assert isinstance(kwargs.get("query"), str)
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        try:
            return {
                "query": kwargs["query"],
                "domains": [],
                "total": 0,
                "preferred_result": None,
                "preferred_result_summary": "",
                "next_action": "refine_query",
                "next_action_args": {},
                "hint": "try another query",
                "results": [],
            }
        finally:
            active_calls -= 1

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definitions = _definitions_by_name(_discover_combined_tools(tmp_path).tool_bundle.definitions)
    search_web = definitions["search_web"]

    async def run_concurrent_searches() -> tuple[ToolExecutionOutcome, ToolExecutionOutcome]:
        """并发调用同一个 provider 的 search_web definition。

        :returns: 两次工具执行 outcome。
        :raises Exception: 工具 callable 异常时透出。
        """

        first, second = await asyncio.gather(
            search_web.callable(_call("search_web", {"query": "first"}), _context()),
            search_web.callable(_call("search_web", {"query": "second"}), _context()),
        )
        return first, second

    first_outcome, second_outcome = asyncio.run(run_concurrent_searches())

    assert isinstance(first_outcome, ToolCompletedOutcome)
    assert isinstance(second_outcome, ToolCompletedOutcome)
    assert max_active_calls == 1


def _discover_combined_tools(tmp_path: Path) -> ServiceDiscoveredTools:
    """通过 fixture config 发现 Doc / Fins / Web 工具。

    :param tmp_path: pytest 临时目录。
    :returns: Service 工具发现结果。
    :raises Exception: 配置加载或 provider 发现失败时透出。
    """

    _write_doc_fixture(tmp_path)
    _build_fins_workspace(tmp_path)
    _write_combined_tool_discovery_overlay(tmp_path)
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=tmp_path / "workspace" / "config"
    )
    effective_provider_configs = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=tmp_path,
    )
    return discover_service_tools(effective_provider_configs)


def _tool_runtime(
    tool_bundle: ToolBundle,
    source_refs: tuple[ToolBundleSourceRef, ...],
) -> tuple[ToolRuntimeHandle, _AcceptingPort]:
    """构造启用 current fetch_more 的 ToolRuntime。

    :param tool_bundle: 业务工具 bundle。
    :param source_refs: 业务工具来源引用。
    :returns: ToolRuntime handle 与 accept port。
    :raises Exception: 构造失败时透出。
    """

    accept_port = _AcceptingPort()
    runtime = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=tool_bundle,
                source_refs=source_refs,
                framework_tool_policy=FrameworkToolPolicyView(
                    reserved_framework_tool_names=frozenset({FrameworkToolName.FETCH_MORE}),
                    enabled_framework_tools=frozenset({FrameworkToolName.FETCH_MORE}),
                ),
                policy_snapshot_digest="sha256:" + "7" * 64,
                enable_truncation_manager=True,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id="session-combined",
                run_id="run-combined",
                attempt_id="attempt-combined",
                execution_id="execution-combined",
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
        )
    )
    return runtime, accept_port


def _write_combined_tool_discovery_overlay(tmp_path: Path) -> None:
    """写入启用 Doc / Fins / Web provider 的确定性 fixture config。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises OSError: 配置写入失败时抛出。
    """

    _write_json(
        tmp_path / "workspace" / "config" / "tool_discovery.json",
        {
            "providers": {
                "financial-read-tools": {
                    "import_path": "dayu.fins.tools.provider:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.fins.tools.provider",
                    "enabled": True,
                    "config": {
                        "workspace_root": str(_fins_workspace_root(tmp_path)),
                        "limits": {
                            "list_documents_max_items": 20,
                            "search_document_max_items": 10,
                            "read_section_max_chars": 4000,
                        },
                    },
                },
                "doc-tools": {
                    "import_path": "dayu.tools.doc_provider:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.tools.doc_provider",
                    "enabled": True,
                    "config": {
                        "allowed_paths": [str(_doc_root(tmp_path))],
                        "limits": {
                            "list_files_max": 20,
                            "get_sections_max": 20,
                            "search_files_max_results": 20,
                            "read_file_max_chars": 4000,
                            "read_file_section_max_chars": 4000,
                        },
                    },
                },
                "web-tools": {
                    "import_path": "dayu.tools.web:discover_tools",
                    "entry_point": None,
                    "source_kind": "explicit_provider",
                    "source_id": "dayu.tools.web",
                    "enabled": True,
                    "config": {
                        "provider": "auto",
                        "request_timeout_seconds": 5.0,
                        "max_search_results": 8,
                        "fetch_truncate_chars": 4000,
                        "allow_private_network_url": False,
                        "playwright_channel": None,
                        "playwright_storage_state_dir": "",
                    },
                },
            }
        },
    )


def _write_doc_fixture(tmp_path: Path) -> Path:
    """写入确定性 Doc markdown fixture。

    :param tmp_path: pytest 临时目录。
    :returns: fixture 文件路径。
    :raises OSError: 文件写入失败时抛出。
    """

    doc_root = _doc_root(tmp_path)
    doc_root.mkdir(parents=True, exist_ok=True)
    target = doc_root / "sample.md"
    target.write_text(
        "# Business\n\nRevenue grew quickly.\n\n## Margin\n\nServices margin improved.\n",
        encoding="utf-8",
    )
    return target


def _build_fins_workspace(tmp_path: Path) -> Path:
    """构造确定性 Fins workspace。

    :param tmp_path: pytest 临时目录。
    :returns: Fins workspace root。
    :raises Exception: 仓储写入失败时透出。
    """

    workspace_root = _fins_workspace_root(tmp_path)
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
            resolver_version="combined-test",
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
            io.BytesIO(_fins_fixture_markdown().encode("utf-8")),
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


def _fins_fixture_markdown() -> str:
    """返回确定性财报 Markdown 内容。

    :returns: Markdown 文本。
    :raises Exception: 不主动抛出异常。
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


def _doc_root(tmp_path: Path) -> Path:
    """返回 Doc fixture 根目录。

    :param tmp_path: pytest 临时目录。
    :returns: Doc fixture 根目录。
    :raises Exception: 不主动抛出异常。
    """

    return tmp_path / "doc-root"


def _fins_workspace_root(tmp_path: Path) -> Path:
    """返回 Fins fixture workspace 根目录。

    :param tmp_path: pytest 临时目录。
    :returns: Fins workspace 根目录。
    :raises Exception: 不主动抛出异常。
    """

    return tmp_path / "fins-workspace"


def _prepared_scene_inputs() -> PreparedSceneInputs:
    """构造 Service assembly 使用的普通 scene 输入。

    :returns: PreparedSceneInputs。
    :raises Exception: 不主动抛出异常。
    """

    return PreparedSceneInputs(
        system_messages=("combined tools system",),
        system_prompt="combined tools system",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.ALL,
            tool_names=None,
        ),
        model_hints=None,
        agent_policy_override=None,
        fragment_refs=(),
        source_refs=(),
        content_digest="sha256:combined-tools",
        capability_tags=("combined-tools",),
    )


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    :param name: 工具名。
    :param arguments: 工具参数。
    :returns: 工具调用请求。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context() -> BatchToolExecutionContext:
    """构造批式工具执行上下文。

    :returns: BatchToolExecutionContext。
    :raises Exception: 不主动抛出异常。
    """

    return BatchToolExecutionContext(
        run_id="run-combined",
        session_id="session-combined",
        iteration_id="iteration-combined",
        timeout_seconds=30.0,
        cancellation_token=_OpenCancellationToken(),
        correlation_id="combined-tool-batch",
    )


def _mapping_value(value: JsonValue) -> Mapping[str, JsonValue]:
    """把 JSON 值收窄为 JSON object。

    :param value: 工具返回值。
    :returns: JSON object。
    :raises AssertionError: 值不是 JSON object 时抛出。
    """

    assert isinstance(value, Mapping)
    return value


def _definitions_by_name(
    definitions: tuple[ToolDefinition, ...],
) -> Mapping[str, ToolDefinition]:
    """按工具名索引工具定义。

    :param definitions: 工具定义元组。
    :returns: 工具名字典。
    :raises Exception: 不主动抛出异常。
    """

    return {definition.name: definition for definition in definitions}


def _definition_names(definitions: tuple[ToolDefinition, ...]) -> frozenset[str]:
    """返回工具名集合。

    :param definitions: 工具定义元组。
    :returns: 工具名集合。
    :raises Exception: 不主动抛出异常。
    """

    return frozenset(definition.name for definition in definitions)


def _native_tool_source_paths() -> tuple[Path, ...]:
    """返回需要扫描旧 runtime import 的原生 provider 源文件。

    :returns: Python 源文件路径元组。
    :raises Exception: 不主动抛出异常。
    """

    repo_root = Path(__file__).resolve().parents[2]
    roots = (
        repo_root / "dayu" / "tools" / "web",
        repo_root / "dayu" / "fins" / "tools",
    )
    explicit_paths = (
        repo_root / "dayu" / "tools" / "doc_provider.py",
        repo_root / "dayu" / "tools" / "doc_tools.py",
    )
    discovered: list[Path] = []
    for root in roots:
        discovered.extend(sorted(root.glob("*.py")))
    discovered.extend(explicit_paths)
    return tuple(path for path in discovered if path.exists())


def _module_imports(path: Path) -> set[str]:
    """解析 Python 文件里的 import 目标模块。

    :param path: Python 源文件路径。
    :returns: import 目标模块集合。
    :raises SyntaxError: 源文件语法非法时抛出。
    :raises OSError: 源文件读取失败时抛出。
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


def _is_forbidden_import(module_name: str) -> bool:
    """判断 import 目标是否命中旧 runtime 根模块。

    :param module_name: AST 解析出的模块名。
    :returns: 命中旧 runtime 根模块时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return any(
        module_name == root or module_name.startswith(f"{root}.")
        for root in _FORBIDDEN_IMPORT_ROOTS
    )


def _write_json(path: Path, value: JsonValue) -> None:
    """写入 JSON fixture。

    :param path: 目标路径。
    :param value: JSON 值。
    :returns: ``None``。
    :raises OSError: 写入失败时抛出。
    :raises TypeError: JSON 序列化失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
