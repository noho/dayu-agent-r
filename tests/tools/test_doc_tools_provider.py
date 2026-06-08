"""Doc tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import builtins
import io
import shutil
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.host.tool_runtime import (
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    HostEventRef,
    HostToolFactAcceptPort,
    ToolFactAcceptCandidate,
    ToolFactAcceptResult,
    ToolFactAcceptedAck,
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
from dayu.tools._legacy_adapter.definition_adapter import (
    LegacyToolConcurrencyPolicy,
    ToolPathValidationPolicy,
    adapt_collected_tool,
)
from dayu.tools._legacy_adapter.registry_collector import (
    CollectedLegacyTool,
    LegacyToolDeclarationCollector,
    LegacyToolKeywordValue,
)
from dayu.tools import doc_tools
from dayu.tools.doc_provider import discover_tools
from dayu.tools.doc_tools import register_doc_tools

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "documents"
_DOC_TOOL_NAMES = (
    "list_files",
    "get_file_sections",
    "search_files",
    "read_file",
    "read_file_section",
)


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


class _ManualCancellationToken:
    """测试用可手动切换取消状态的 token。"""

    def __init__(self) -> None:
        """初始化未取消状态。

        :returns: ``None``。
        """

        self._is_cancelled = False
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def cancel(self, reason: str) -> None:
        """请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self._is_cancelled = True
        self._reason = reason
        self._requested_at = datetime(2026, 1, 1, 0, 0, 0)

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已调用 ``cancel`` 后返回 ``True``。
        """

        return self._is_cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 已取消时返回原因，否则返回 ``None``。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 已取消时返回固定时间戳，否则返回 ``None``。
        """

        return self._requested_at


class _AcceptingPort(HostToolFactAcceptPort):
    """测试用 Host accept barrier。"""

    def __init__(self) -> None:
        """初始化记录列表。

        :returns: ``None``。
        """

        self.candidates: list[ToolFactAcceptCandidate] = []

    def accept_tool_fact(
        self,
        candidate: ToolFactAcceptCandidate,
    ) -> ToolFactAcceptResult:
        """接受工具事实候选。

        :param candidate: ToolRuntime 构造的工具事实候选。
        :returns: accepted ack。
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
            result_digest=f"sha256:{'1' * 64}",
            reuse_prior_event_refs=(),
            diagnostic_refs=(),
            idempotency_record_ref=f"idempotency-{len(self.candidates)}",
        )


def test_provider_discovers_exactly_five_doc_tools(tmp_path: Path) -> None:
    """ToolsDiscovery 应发现五个 Doc tools。"""

    spec = _spec(tmp_path)
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=spec, provider=discover_tools),)
    )

    assert tuple(definition.name for definition in result.tool_bundle.definitions) == _DOC_TOOL_NAMES
    assert result.provider_reports[0].tool_names == _DOC_TOOL_NAMES


def test_doc_tool_schemas_do_not_expose_execution_context(tmp_path: Path) -> None:
    """execution_context 注入参数不得进入 LLM-facing tool schema。"""

    definitions = _discover_definitions(tmp_path)

    for definition in definitions:
        properties = definition.schema.function.parameters.properties
        assert "execution_context" not in properties


@pytest.mark.parametrize("tool_name", _DOC_TOOL_NAMES)
def test_doc_tools_cancelled_before_work_return_tool_cancelled(
    tmp_path: Path,
    tool_name: str,
) -> None:
    """五个 Doc tools 在业务入口预取消时必须返回稳定 tool_cancelled。"""

    target = _copy_fixture(tmp_path, "sample.md")
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    token = _ManualCancellationToken()
    token.cancel(f"cancel {tool_name}")

    outcome = asyncio.run(
        definitions[tool_name].callable(
            _call(tool_name, _pre_cancel_arguments(tool_name, tmp_path, target)),
            _context(token),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "tool_cancelled"


def test_provider_enabled_without_allowed_paths_fails_closed() -> None:
    """启用 provider 但没有白名单时不得注册可执行 Doc tools。"""

    spec = _spec_with_config({"limits": {}, "allowed_paths": []}, allow_empty=True)
    output = discover_tools(spec)
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=spec, provider=discover_tools),)
    )

    assert output.definitions == ()
    assert result.tool_bundle.definitions == ()


def test_disallowed_path_returns_failed_outcome(tmp_path: Path) -> None:
    """白名单外路径必须返回 current ToolFailedOutcome。"""

    allowed = tmp_path / "allowed"
    blocked = tmp_path / "blocked"
    allowed.mkdir()
    blocked.mkdir()
    target = blocked / "sample.md"
    target.write_text("blocked", encoding="utf-8")
    definition = _definitions_by_name(_discover_definitions(allowed))["read_file"]

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(target)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"


def test_path_validation_failure_does_not_enter_migrated_function_body(
    tmp_path: Path,
) -> None:
    """路径校验失败时必须在进入迁移函数体前失败。"""

    allowed = tmp_path / "allowed"
    blocked = tmp_path / "blocked"
    allowed.mkdir()
    blocked.mkdir()
    target = blocked / "sample.md"
    target.write_text("blocked", encoding="utf-8")
    calls: list[Mapping[str, JsonValue]] = []
    declaration = _collected_by_name()["read_file"]

    def spy_read_file(file_path: LegacyToolKeywordValue) -> JsonValue:
        """记录是否进入迁移函数体。

        :param file_path: 文件路径。
        :returns: 测试返回值。
        """

        calls.append({"file_path": cast(JsonValue, file_path)})
        return {"file_path": file_path if isinstance(file_path, str) else ""}

    spied = replace(declaration, callable=spy_read_file)
    definition = adapt_collected_tool(
        spied,
        path_policy=ToolPathValidationPolicy(
            allowed_roots=(allowed,),
            file_path_params=spied.file_path_params,
            must_exist=True,
        ),
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(target)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert calls == []


def test_file_path_params_metadata_is_collected_and_used(tmp_path: Path) -> None:
    """file_path_params metadata 必须由旧 decorators 收集并用于路径验证。"""

    markdown_path = _copy_fixture(tmp_path, "sample.md")
    declarations = _collected_by_name()
    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(markdown_path)}),
            _context(),
        )
    )

    assert declarations["list_files"].file_path_params == ("directory",)
    assert declarations["read_file"].file_path_params == ("file_path",)
    assert isinstance(outcome, ToolCompletedOutcome)


def test_collector_allowed_paths_are_not_trusted(tmp_path: Path) -> None:
    """collector.register_allowed_paths 记录值不能成为可信路径安全源。"""

    target = _copy_fixture(tmp_path, "sample.md")
    collector = LegacyToolDeclarationCollector()
    register_doc_tools(
        collector,
        allowed_paths=[tmp_path],
        allow_file_write=True,
        allowed_write_paths=[str(tmp_path)],
        timeout_budget=1.0,
    )
    declaration = _by_name(collector.collected_tools())["read_file"]
    definition = adapt_collected_tool(
        declaration,
        path_policy=None,
        concurrency_policy=LegacyToolConcurrencyPolicy.SERIAL_PER_TOOL,
    )

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(target)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"
    assert collector._allowed_path_calls == []


def test_path_args_are_projected_to_validated_absolute_paths(tmp_path: Path) -> None:
    """路径参数进入迁移函数前必须投影为验证后的绝对路径。"""

    markdown_path = _copy_fixture(tmp_path, "sample.md")
    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(markdown_path)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = cast(Mapping[str, JsonValue], outcome.result.value)
    assert value["file_path"] == str(markdown_path.resolve())


def test_list_and_search_return_paths_can_chain_to_read_tools(
    tmp_path: Path,
) -> None:
    """列表和搜索返回的文件路径必须能直接交给读取工具。"""

    allowed_root = tmp_path / "allowed-root"
    report_dir = allowed_root / "reports"
    report_dir.mkdir(parents=True)
    target = report_dir / "sample.md"
    shutil.copyfile(_FIXTURE_ROOT / "sample.md", target)
    assert allowed_root.resolve() != Path.cwd().resolve()
    definitions = _definitions_by_name(_discover_definitions(allowed_root))

    list_outcome = asyncio.run(
        definitions["list_files"].callable(
            _call(
                "list_files",
                {
                    "directory": str(allowed_root),
                    "recursive": True,
                },
            ),
            _context(),
        )
    )
    assert isinstance(list_outcome, ToolCompletedOutcome)
    listed_path = _first_listed_file_path(list_outcome)
    assert listed_path == str(target.resolve())

    read_outcome = asyncio.run(
        definitions["read_file"].callable(
            _call("read_file", {"file_path": listed_path}),
            _context(),
        )
    )
    sections_outcome = asyncio.run(
        definitions["get_file_sections"].callable(
            _call("get_file_sections", {"file_path": listed_path}),
            _context(),
        )
    )

    assert isinstance(read_outcome, ToolCompletedOutcome)
    assert isinstance(sections_outcome, ToolCompletedOutcome)

    search_outcome = asyncio.run(
        definitions["search_files"].callable(
            _call(
                "search_files",
                {
                    "directory": str(allowed_root),
                    "query": "Revenue",
                },
            ),
            _context(),
        )
    )
    assert isinstance(search_outcome, ToolCompletedOutcome)
    matched_path, matched_ref = _first_search_match_file_and_ref(search_outcome)
    assert matched_path == str(target.resolve())
    assert isinstance(matched_ref, str)

    read_search_outcome = asyncio.run(
        definitions["read_file"].callable(
            _call("read_file", {"file_path": matched_path}),
            _context(),
        )
    )
    read_section_from_search_outcome = asyncio.run(
        definitions["read_file_section"].callable(
            _call(
                "read_file_section",
                {
                    "file_path": matched_path,
                    "ref": matched_ref,
                },
            ),
            _context(),
        )
    )
    assert isinstance(read_search_outcome, ToolCompletedOutcome)
    assert isinstance(read_section_from_search_outcome, ToolCompletedOutcome)


def test_search_files_cancelled_during_iteration_stops_before_later_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_files 遍历中取消后不得继续扫描后续文件。"""

    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    third = tmp_path / "c.txt"
    first.write_text("first revenue", encoding="utf-8")
    second.write_text("second revenue", encoding="utf-8")
    third.write_text("third revenue", encoding="utf-8")
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    token = _ManualCancellationToken()
    scanned_paths: list[str] = []

    def fake_try_create_processor(path: Path) -> None:
        """强制搜索走行扫描 fallback。

        :param path: 候选文件路径。
        :returns: 始终返回 ``None``。
        """

        del path
        return None

    def fake_search_via_line_scan(
        file_path: Path,
        relative_path: str,
        query: str,
        remaining: int,
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict[str, JsonValue]]:
        """记录首个扫描文件并触发取消。

        :param file_path: 当前扫描文件。
        :param relative_path: 相对路径。
        :param query: 搜索词。
        :param remaining: 剩余结果数量。
        :param cancellation_token: Host 注入的取消令牌。
        :returns: 空匹配，迫使外层继续迭代并命中 checkpoint。
        """

        del file_path, query, remaining, cancellation_token
        scanned_paths.append(relative_path)
        token.cancel("cancel during iteration")
        return []

    monkeypatch.setattr(doc_tools, "_try_create_processor", fake_try_create_processor)
    monkeypatch.setattr(doc_tools, "_search_via_line_scan", fake_search_via_line_scan)

    outcome = asyncio.run(
        definitions["search_files"].callable(
            _call("search_files", {"directory": str(tmp_path), "query": "revenue"}),
            _context(token),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "tool_cancelled"
    assert len(scanned_paths) == 1


def test_read_file_cancelled_after_first_failed_encoding_stops_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_file 首个编码失败并触发取消后不得继续尝试 fallback 编码。"""

    target = tmp_path / "encoded.txt"
    target.write_bytes(b"\xffencoded")
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    token = _ManualCancellationToken()
    attempted_encodings: list[str] = []
    original_open = builtins.open

    def fake_open(
        file: int | str | bytes | Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
        closefd: bool = True,
        opener: Callable[[str, int], int] | None = None,
    ) -> TextIO:
        """在 utf-8 解码失败后请求取消。

        :param file: 打开的文件路径或描述符。
        :param mode: 打开模式。
        :param buffering: buffering 参数。
        :param encoding: 文本编码。
        :param errors: 解码错误策略。
        :param newline: 换行策略。
        :param closefd: 是否关闭 fd。
        :param opener: 自定义 opener。
        :returns: 文本文件对象。
        :raises UnicodeDecodeError: 模拟 utf-8 解码失败。
        """

        if isinstance(file, (str, Path)) and Path(file).resolve() == target.resolve():
            if encoding is not None:
                attempted_encodings.append(encoding)
            if encoding == "utf-8":
                token.cancel("cancel before fallback encoding")
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
            return io.StringIO("fallback content")
        return cast(
            TextIO,
            original_open(file, mode, buffering, encoding, errors, newline, closefd, opener),
        )

    monkeypatch.setattr(builtins, "open", fake_open)

    outcome = asyncio.run(
        definitions["read_file"].callable(
            _call("read_file", {"file_path": str(target)}),
            _context(token),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "tool_cancelled"
    assert attempted_encodings == ["utf-8"]


def test_success_and_failure_responses_do_not_contain_old_envelope(
    tmp_path: Path,
) -> None:
    """代表性成功/失败响应不得包含 OLD ok/value envelope。"""

    markdown_path = _copy_fixture(tmp_path, "sample.md")
    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]

    success = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(markdown_path)}),
            _context(),
        )
    )
    failure = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(markdown_path), "start_line": 9, "end_line": 1}),
            _context(),
        )
    )

    assert isinstance(success, ToolCompletedOutcome)
    assert isinstance(success.result.value, Mapping)
    assert "ok" not in success.result.value
    assert "value" not in success.result.value
    assert isinstance(failure, ToolFailedOutcome)
    assert failure.result.ok is False


@pytest.mark.parametrize("fixture_name", ("sample.md", "sample_docling.json"))
def test_markdown_and_docling_fixtures_support_sections_search_and_read(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    """Markdown 与 Docling JSON fixture 必须支持章节列表、搜索和章节读取。"""

    target = _copy_fixture(tmp_path, fixture_name)
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    sections_outcome = asyncio.run(
        definitions["get_file_sections"].callable(
            _call("get_file_sections", {"file_path": str(target)}),
            _context(),
        )
    )

    assert isinstance(sections_outcome, ToolCompletedOutcome)
    sections_value = cast(Mapping[str, JsonValue], sections_outcome.result.value)
    sections = cast(list[JsonValue], sections_value["sections"])
    first_section = cast(Mapping[str, JsonValue], sections[0])
    ref_value = first_section["ref"]
    assert isinstance(ref_value, str)

    search_outcome = asyncio.run(
        definitions["search_files"].callable(
            _call("search_files", {"directory": str(tmp_path), "query": "Revenue"}),
            _context(),
        )
    )
    read_outcome = asyncio.run(
        definitions["read_file_section"].callable(
            _call("read_file_section", {"file_path": str(target), "ref": ref_value}),
            _context(),
        )
    )

    assert isinstance(search_outcome, ToolCompletedOutcome)
    assert isinstance(read_outcome, ToolCompletedOutcome)
    read_value = cast(Mapping[str, JsonValue], read_outcome.result.value)
    assert "Revenue grew quickly." in str(read_value["content"])


def test_no_old_fetch_more_business_tool() -> None:
    """Doc provider 不得暴露 OLD fetch_more business tool。"""

    declarations = _collected_by_name()

    assert "fetch_more" not in declarations


def test_read_tools_expose_current_truncate_spec_and_no_old_imports(
    tmp_path: Path,
) -> None:
    """read_file/read_file_section 必须声明 current ToolTruncateSpec 且不导入 OLD runtime。"""

    definitions = _definitions_by_name(_discover_definitions(tmp_path))

    for tool_name in ("read_file", "read_file_section"):
        truncate = definitions[tool_name].truncate
        assert isinstance(truncate, ToolTruncateSpec)
        assert truncate.strategy is ToolTruncationStrategy.TEXT_CHARS
        assert truncate.target_field == "content"
    source = (Path(__file__).resolve().parents[2] / "dayu" / "tools" / "doc_tools.py").read_text(
        encoding="utf-8"
    )
    imported_modules = _imported_modules(source)
    assert "dayu.engine.tool_registry" not in imported_modules
    assert "dayu.engine.truncation_manager" not in imported_modules
    assert "dayu.engine.tool_result" not in imported_modules
    assert "fetch_more" not in source
    assert "TruncationManager" not in source


def test_toolruntime_executes_doc_tool_through_accept_barrier(tmp_path: Path) -> None:
    """当前 ToolRuntime 至少能通过 accept barrier 执行一个 Doc tool。"""

    markdown_path = _copy_fixture(tmp_path, "sample.md")
    output = discover_tools(_spec(tmp_path))
    accept_port = _AcceptingPort()
    tool_runtime = DefaultToolRuntimeFactory(
        EffectiveToolBundleBuilder()
    ).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=output.definitions),
                source_refs=output.source_refs,
                framework_tool_policy=default_framework_tool_policy_view(),
                policy_snapshot_digest="sha256:" + "2" * 64,
                enable_truncation_manager=False,
            ),
            execution_scope=ToolRuntimeExecutionScope(
                session_id="session-doc",
                run_id="run-doc",
                attempt_id="attempt-doc",
                execution_id="execution-doc",
                allow_tool_calls=True,
            ),
            accept_port=accept_port,
        )
    )

    outcome = asyncio.run(
        tool_runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call("read_file", {"file_path": str(markdown_path)}),
                ),
                context=_context(),
            )
        )
    )

    assert len(accept_port.candidates) == 1
    record_outcome = outcome.records[0].outcome
    assert isinstance(record_outcome, ToolCompletedOutcome)
    value = cast(Mapping[str, JsonValue], record_outcome.result.value)
    assert "Revenue grew quickly." in str(value["content"])


def _spec(path: Path) -> ToolsDiscoveryProviderSpec:
    """构造启用 Doc provider 的 spec。

    :param path: 允许访问路径。
    :returns: provider spec。
    """

    return _spec_with_config(
        {
            "allowed_paths": [str(path)],
            "limits": {
                "list_files_max": 20,
                "get_sections_max": 20,
                "search_files_max_results": 20,
                "read_file_max_chars": 2000,
                "read_file_section_max_chars": 2000,
            },
        }
    )


def _spec_with_config(
    config: Mapping[str, JsonValue],
    *,
    allow_empty: bool = False,
) -> ToolsDiscoveryProviderSpec:
    """构造 Doc provider spec。

    :param config: provider config。
    :param allow_empty: 是否允许空工具集合。
    :returns: provider spec。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id="doc-tools",
        location=PythonImportPathProvider("dayu.tools.doc_provider:discover_tools"),
        enabled=True,
        allow_empty=allow_empty,
        config=config,
    )


def _discover_definitions(path: Path) -> tuple[ToolDefinition, ...]:
    """返回指定白名单下发现的工具定义。

    :param path: 白名单路径。
    :returns: 工具定义元组。
    """

    return discover_tools(_spec(path)).definitions


def _definitions_by_name(
    definitions: tuple[ToolDefinition, ...],
) -> Mapping[str, ToolDefinition]:
    """按工具名索引工具定义。

    :param definitions: 工具定义元组。
    :returns: 工具名到定义的映射。
    """

    return {definition.name: definition for definition in definitions}


def _collected_by_name() -> Mapping[str, CollectedLegacyTool]:
    """收集迁移 Doc 声明并按名称索引。

    :returns: 工具名到收集声明的映射。
    """

    collector = LegacyToolDeclarationCollector()
    register_doc_tools(collector)
    return _by_name(collector.collected_tools())


def _by_name(
    declarations: tuple[CollectedLegacyTool, ...],
) -> Mapping[str, CollectedLegacyTool]:
    """按名称索引收集声明。

    :param declarations: 收集声明。
    :returns: 工具名到声明的映射。
    """

    return {declaration.name: declaration for declaration in declarations}


def _copy_fixture(tmp_path: Path, fixture_name: str) -> Path:
    """复制确定性文档 fixture 到临时目录。

    :param tmp_path: pytest 临时目录。
    :param fixture_name: fixture 文件名。
    :returns: 临时文件路径。
    """

    source = _FIXTURE_ROOT / fixture_name
    target = tmp_path / fixture_name
    shutil.copyfile(source, target)
    return target


def _first_listed_file_path(outcome: ToolCompletedOutcome) -> str:
    """读取 ``list_files`` 第一个返回文件路径。

    :param outcome: ``list_files`` 成功 outcome。
    :returns: 第一个文件路径。
    :raises AssertionError: 响应形状不是测试预期时抛出。
    """

    value = cast(Mapping[str, JsonValue], outcome.result.value)
    files = cast(list[JsonValue], value["files"])
    assert files
    first_file = cast(Mapping[str, JsonValue], files[0])
    path_value = first_file["path"]
    assert isinstance(path_value, str)
    return path_value


def _first_search_match_file_and_ref(outcome: ToolCompletedOutcome) -> tuple[str, JsonValue]:
    """读取 ``search_files`` 第一个命中的文件路径和章节 ref。

    :param outcome: ``search_files`` 成功 outcome。
    :returns: 第一个命中的文件路径和章节 ref。
    :raises AssertionError: 响应形状不是测试预期时抛出。
    """

    value = cast(Mapping[str, JsonValue], outcome.result.value)
    matches = cast(list[JsonValue], value["matches"])
    assert matches
    first_match = cast(Mapping[str, JsonValue], matches[0])
    file_value = first_match["file"]
    assert isinstance(file_value, str)
    return file_value, first_match["ref"]


def _pre_cancel_arguments(
    tool_name: str,
    directory: Path,
    file_path: Path,
) -> Mapping[str, JsonValue]:
    """返回各 Doc tool 预取消测试所需的最小合法参数。

    :param tool_name: Doc tool 名称。
    :param directory: 已允许访问的目录。
    :param file_path: 已存在的文件路径。
    :returns: 工具调用参数。
    :raises AssertionError: 工具名不在测试覆盖集合中时抛出。
    """

    if tool_name == "list_files":
        return {"directory": str(directory)}
    if tool_name == "get_file_sections":
        return {"file_path": str(file_path)}
    if tool_name == "search_files":
        return {"directory": str(directory), "query": "Revenue"}
    if tool_name == "read_file":
        return {"file_path": str(file_path)}
    if tool_name == "read_file_section":
        return {"file_path": str(file_path), "ref": "section_1"}
    raise AssertionError(f"unexpected doc tool: {tool_name}")


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    :param name: 工具名。
    :param arguments: 工具参数。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context(
    cancellation_token: CancellationToken | None = None,
) -> BatchToolExecutionContext:
    """构造批式执行上下文。

    :param cancellation_token: 可选测试取消令牌。
    :returns: BatchToolExecutionContext。
    """

    if cancellation_token is None:
        cancellation_token = _OpenCancellationToken()
    return BatchToolExecutionContext(
        run_id="run-doc",
        session_id="session-doc",
        iteration_id="iteration-doc",
        timeout_seconds=10.0,
        cancellation_token=cancellation_token,
        correlation_id="correlation-doc",
    )


def _imported_modules(source: str) -> set[str]:
    """读取源码中的 import 模块名。

    :param source: Python 源码。
    :returns: import 模块名集合。
    """

    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules
