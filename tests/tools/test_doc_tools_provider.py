"""Doc tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
import inspect
import os
import pickle
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Final, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_execution import (
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ProcessBackedToolTarget,
)
from dayu.contracts.tool_outcome import TOOL_CANCELLED_REASON_HOST_CANCELLED
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import ToolCancelledOutcome, ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.documents.processors.base import DocumentProcessor
from dayu.documents.processors.local_file_source import LocalFileSource
from dayu.documents.processors.source_snapshot import SourceSnapshot
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
    ToolRuntimeHandle,
)
from dayu.host.tooling import default_framework_tool_policy_view
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)
from dayu.tools import doc_tools
from dayu.tools.doc_provider import discover_tools

_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "documents"
_DOC_TOOL_NAMES = (
    "list_files",
    "get_file_sections",
    "search_files",
    "read_file",
    "read_file_section",
)
_FORBIDDEN_CANCEL_MESSAGE_PARTS = (
    "run_id",
    "session_id",
    "payload_ref",
    "digest",
    "correlation_id",
    "cancellation_token",
)
_REAL_SMOKE_SMALL_FILE_COUNT: Final[int] = 10_001
_REAL_SMOKE_CHUNK_BYTES: Final[int] = 1024 * 1024
_REAL_SMOKE_CHUNK_COUNT: Final[int] = 34
_REAL_SMOKE_MIN_LARGE_FILE_BYTES: Final[int] = 33 * _REAL_SMOKE_CHUNK_BYTES
_REAL_SMOKE_LARGE_FILE_NAME: Final[str] = "zzzz-large-tail.txt"
_REAL_SMOKE_OUTSIDE_LINK_NAME: Final[str] = "zzzz-outside-link.txt"
_REAL_SMOKE_TAIL_MARKER: Final[str] = "DAYU_REAL_COMPLETE_INPUT_TAIL_MARKER"


@dataclass(frozen=True, slots=True)
class _SlowCompletedProcessTarget:
    """测试用慢 process-backed target。"""

    sleep_seconds: float

    def __call__(self) -> JsonValue:
        """阻塞一段时间后返回 completed 信封。

        :returns: process-backed completed JSON 信封。
        """

        time.sleep(self.sleep_seconds)
        return {"status": "completed", "value": {"late": True}}


@dataclass(frozen=True, slots=True)
class _SlowProcessTargetFactory:
    """测试用慢 process target factory。"""

    sleep_seconds: float

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> ProcessBackedToolTarget:
        """构造慢 process target。

        :param call: 单次工具调用请求。
        :param context: process-backed 投影上下文。
        :returns: 慢 process-backed target。
        """

        del call, context
        return _SlowCompletedProcessTarget(self.sleep_seconds)


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


class _CancelAfterObservationToken:
    """在固定观察次数后自动取消的测试 token。"""

    def __init__(self, cancel_at: int) -> None:
        """初始化自动取消 token。

        Args:
            cancel_at: 第几次 ``is_cancelled`` 观察起返回 ``True``。

        Returns:
            无。

        Raises:
            ValueError: ``cancel_at`` 小于 1 时抛出。
        """

        if cancel_at < 1:
            raise ValueError("cancel_at must be >= 1")
        self._cancel_at = cancel_at
        self._observations = 0

    def is_cancelled(self) -> bool:
        """记录观察并在阈值后返回取消。

        Returns:
            是否已达到取消阈值。

        Raises:
            无。
        """

        self._observations += 1
        return self._observations >= self._cancel_at

    def cancel_reason(self) -> str | None:
        """返回测试取消原因。

        Returns:
            固定测试原因。

        Raises:
            无。
        """

        return "cancel after observation"

    def requested_at(self) -> datetime | None:
        """返回测试取消时间。

        Returns:
            固定时间。

        Raises:
            无。
        """

        return datetime(2026, 1, 1, 0, 0, 0)


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
        required = definition.schema.function.parameters.required
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "execution_context" not in required
        assert "cancellation_token" not in required


def test_doc_provider_discovers_native_async_callables(tmp_path: Path) -> None:
    """Doc provider 必须直接发现 current 原生 async callable。"""

    definitions = _discover_definitions(tmp_path)

    assert tuple(definition.name for definition in definitions) == _DOC_TOOL_NAMES
    assert all(inspect.iscoroutinefunction(definition.callable) for definition in definitions)


def test_all_doc_tool_definitions_declare_process_backed_execution(tmp_path: Path) -> None:
    """五个 Doc tool 的生产 execution 必须声明为 process-backed。"""

    definitions = _discover_definitions(tmp_path)

    assert tuple(definition.name for definition in definitions) == _DOC_TOOL_NAMES
    for definition in definitions:
        assert isinstance(definition.execution, ProcessBackedToolExecutionCapability)


def test_doc_tools_do_not_redeclare_process_envelope_constants() -> None:
    """Doc 工具不得重新声明本地 process envelope 常量。"""

    source = Path(doc_tools.__file__).read_text(encoding="utf-8")

    assert "_DOC_PROCESS_" not in source


@pytest.mark.parametrize("tool_name", _DOC_TOOL_NAMES)
def test_doc_process_target_factory_is_pickle_round_trippable(
    tmp_path: Path,
    tool_name: str,
) -> None:
    """验证 Doc process target factory/target 可序列化且不捕获 live object。

    Args:
        tmp_path: pytest 临时目录。
        tool_name: 当前验证的 Doc 工具名。

    Returns:
        无。

    Raises:
        AssertionError: round-trip 结果或目标字段边界不符合约定时抛出。
    """

    target = _copy_fixture(tmp_path, "sample.md")
    definition = _definitions_by_name(_discover_definitions(tmp_path))[tool_name]
    execution = cast(ProcessBackedToolExecutionCapability, definition.execution)
    factory = cast(
        doc_tools._DocProcessTargetFactory,
        pickle.loads(pickle.dumps(execution.target_factory)),
    )

    process_target = factory.build_process_target(
        _call(tool_name, _pre_cancel_arguments(tool_name, tmp_path, target)),
        ProcessBackedToolContext(
            run_id="run-doc",
            session_id="session-doc",
            iteration_id="iteration-doc",
            timeout_seconds=10.0,
            correlation_id="correlation-doc",
        ),
    )
    round_tripped_target = cast(
        doc_tools._DocProcessTarget,
        pickle.loads(pickle.dumps(process_target)),
    )

    assert round_tripped_target.tool_name == tool_name
    target_repr = repr(round_tripped_target)
    assert tuple(field.name for field in fields(round_tripped_target)) == (
        "tool_name",
        "arguments",
        "allowed_root_locators",
        "limits",
        "timeout_seconds",
    )
    assert "provider_lock" not in target_repr
    assert "DocumentProcessor" not in target_repr
    assert "CancellationToken" not in target_repr


def test_doc_process_target_fast_path_matches_callable_baseline(tmp_path: Path) -> None:
    """read_file process target 成功输出应与 callable fallback 成功值一致。"""

    target = _copy_fixture(tmp_path, "sample.md")
    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]
    call = _call("read_file", {"file_path": str(target)})
    baseline = asyncio.run(definition.callable(call, _context()))
    assert isinstance(baseline, ToolCompletedOutcome)

    envelope = _run_definition_process_target(definition, call)

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "completed"
    assert envelope["value"] == baseline.result.value


def test_doc_process_target_read_file_partial_matches_direct_callable(
    tmp_path: Path,
) -> None:
    """read_file 字符 cap 的 partial 投影在 direct/process 路径必须同源。"""

    target = tmp_path / "long.txt"
    target.write_text("x" * 2500, encoding="utf-8")
    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]
    call = _call("read_file", {"file_path": str(target)})
    baseline = asyncio.run(definition.callable(call, _context()))
    assert isinstance(baseline, ToolCompletedOutcome)

    envelope = _run_definition_process_target(definition, call)

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "completed"
    assert envelope["value"] == baseline.result.value
    value = cast(Mapping[str, JsonValue], envelope["value"])
    assert value["content_truncated"] is True
    assert value["scan_complete"] is False
    assert value["total_lines"] is None


def test_doc_process_target_processor_path_supports_docling_sections(tmp_path: Path) -> None:
    """get_file_sections process target 应在子进程内重新创建 processor。"""

    target = _copy_fixture(tmp_path, "sample_docling.json")
    definition = _definitions_by_name(_discover_definitions(tmp_path))["get_file_sections"]

    envelope = _run_definition_process_target(
        definition,
        _call("get_file_sections", {"file_path": str(target)}),
    )

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "completed"
    value = cast(Mapping[str, JsonValue], envelope["value"])
    sections = cast(list[JsonValue], value["sections"])
    first_section = cast(Mapping[str, JsonValue], sections[0])
    assert isinstance(first_section["ref"], str)


def test_doc_process_target_path_denied_keeps_permission_semantics(tmp_path: Path) -> None:
    """process target 必须在子进程内重新执行路径白名单校验。"""

    allowed = tmp_path / "allowed"
    blocked = tmp_path / "blocked"
    allowed.mkdir()
    blocked.mkdir()
    target = blocked / "sample.md"
    target.write_text("blocked", encoding="utf-8")
    definition = _definitions_by_name(_discover_definitions(allowed))["read_file"]

    envelope = _run_definition_process_target(
        definition,
        _call("read_file", {"file_path": str(target)}),
    )

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "failed"
    assert envelope["error_type"] == "permission_denied"


def test_doc_process_target_nonexistent_allowed_path_keeps_file_not_found(
    tmp_path: Path,
) -> None:
    """白名单内不存在路径在 process target 中仍返回 file_not_found。"""

    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]

    envelope = _run_definition_process_target(
        definition,
        _call("read_file", {"file_path": str(tmp_path / "missing.md")}),
    )

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "failed"
    assert envelope["error_type"] == "file_not_found"
    assert "Verify the file path and retry." not in str(envelope["message"])
    assert envelope["hint"] == "Verify the file path and retry."


def test_doc_process_target_argument_validation_failure_separates_hint(
    tmp_path: Path,
) -> None:
    """process target 参数校验失败时 message 与 hint 必须分离。"""

    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]

    envelope = _run_definition_process_target(
        definition,
        _call("read_file", {}),
    )

    assert isinstance(envelope, Mapping)
    assert envelope["status"] == "failed"
    assert envelope["error_type"] == "invalid_argument"
    assert "Hint:" not in str(envelope["message"])
    assert envelope["hint"] == "Add required fields and retry: file_path."


@pytest.mark.parametrize("tool_name", _DOC_TOOL_NAMES)
def test_doc_tools_cancelled_before_work_return_host_cancelled(
    tmp_path: Path,
    tool_name: str,
) -> None:
    """五个 Doc tools 在业务入口预取消时必须返回 host_cancelled outcome。"""

    target = _copy_fixture(tmp_path, "sample.md")
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    token = _ManualCancellationToken()
    token.cancel(f"run_id=run-doc session_id=session-doc payload_ref=payload-{tool_name}")

    outcome = asyncio.run(
        definitions[tool_name].callable(
            _call(tool_name, _pre_cancel_arguments(tool_name, tmp_path, target)),
            _context(token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


@pytest.mark.parametrize("config", ({"limits": {}}, {"limits": {}, "allowed_paths": []}))
def test_provider_enabled_without_allowed_paths_fails_fast(
    config: Mapping[str, JsonValue],
) -> None:
    """启用 provider 但没有白名单时必须在 Doc provider 边界失败。

    :param config: 缺失或空白名单的 provider 配置。
    :returns: ``None``。
    :raises AssertionError: provider 未按预期失败时抛出。
    """

    spec = _spec_with_config(config)

    with pytest.raises(
        ValueError,
        match=(
            "doc provider config.allowed_paths must contain at least one path "
            "when doc-tools is enabled"
        ),
    ):
        discover_tools(spec)


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


def test_disallowed_nonexistent_path_returns_permission_denied(tmp_path: Path) -> None:
    """白名单外不存在路径不得泄漏 file_not_found。"""

    allowed = tmp_path / "allowed"
    blocked = tmp_path / "blocked"
    allowed.mkdir()
    blocked.mkdir()
    target = blocked / "missing.md"
    definition = _definitions_by_name(_discover_definitions(allowed))["read_file"]

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(target)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"


@pytest.mark.parametrize("tool_name", ("get_file_sections", "read_file", "read_file_section"))
def test_doc_file_path_pointing_to_directory_returns_invalid_argument(
    tmp_path: Path,
    tool_name: str,
) -> None:
    """file_path 指向目录时必须在路径投影层返回参数错误。"""

    target_directory = tmp_path / "reports"
    target_directory.mkdir()
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    arguments: dict[str, JsonValue] = {"file_path": str(target_directory)}
    if tool_name == "read_file_section":
        arguments["ref"] = "section-1"

    outcome = asyncio.run(
        definitions[tool_name].callable(
            _call(tool_name, arguments),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"


def test_path_validation_failure_does_not_enter_migrated_function_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """路径校验失败时必须在进入 Doc 业务函数前失败。"""

    allowed = tmp_path / "allowed"
    blocked = tmp_path / "blocked"
    allowed.mkdir()
    blocked.mkdir()
    target = blocked / "sample.md"
    target.write_text("blocked", encoding="utf-8")
    calls: list[str] = []

    def spy_read_file_business(
        *,
        file_path: str,
        start_line: int | None,
        end_line: int | None,
        max_chars: int,
        cancellation_token: CancellationToken,
    ) -> JsonValue:
        """记录是否进入 Doc 业务函数。

        :param file_path: 文件路径。
        :param start_line: 起始行号。
        :param end_line: 结束行号。
        :param max_chars: 最大返回字符数。
        :param cancellation_token: 取消令牌。
        :returns: 测试返回值。
        :raises AssertionError: 业务函数在路径拒绝前被调用时由测试断言抛出。
        """

        del start_line, end_line, max_chars
        del cancellation_token
        calls.append(file_path)
        return {"file_path": file_path}

    monkeypatch.setattr(doc_tools, "_read_file_business", spy_read_file_business)
    definition = _definitions_by_name(_discover_definitions(allowed))["read_file"]

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(target)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert calls == []


def test_native_doc_path_projection_accepts_allowed_absolute_paths(tmp_path: Path) -> None:
    """native Doc 路径投影必须接受白名单内绝对路径。"""

    markdown_path = _copy_fixture(tmp_path, "sample.md")
    definition = _definitions_by_name(_discover_definitions(tmp_path))["read_file"]

    outcome = asyncio.run(
        definition.callable(
            _call("read_file", {"file_path": str(markdown_path)}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)


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


def test_list_files_observes_all_entries_and_omits_partial_only_fields(
    tmp_path: Path,
) -> None:
    """list_files 必须完整观察目录并删除 entry partial 专用字段。"""

    nested = tmp_path / "nested"
    nested.mkdir()
    for name in ("c.txt", "a.txt", "b.txt"):
        (nested / name).write_text(name, encoding="utf-8")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._list_files_business(
            directory=str(tmp_path),
            pattern=None,
            recursive=True,
            limit=2,
            max_files=2,
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert value["scanned_entries"] == 4
    assert value["total"] == 3
    assert value["returned"] == 2
    assert "scan_complete" not in value
    assert "truncated_reason" not in value


def test_list_files_directory_iteration_observes_cancellation(tmp_path: Path) -> None:
    """list_files 在目录迭代窗口必须停止观察到的取消。"""

    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    token = _CancelAfterObservationToken(cancel_at=3)

    with pytest.raises(doc_tools._DocCancelledError):
        doc_tools._list_files_business(
            directory=str(tmp_path),
            pattern=None,
            recursive=False,
            limit=3,
            max_files=3,
            cancellation_token=token,
        )


def test_list_files_result_limit_keeps_exact_total_after_complete_scan(
    tmp_path: Path,
) -> None:
    """仅结果数受限时仍应完成 bounded scan 并给出精确 total。"""

    for name in ("c.txt", "a.txt", "b.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._list_files_business(
            directory=str(tmp_path),
            pattern="*.txt",
            recursive=False,
            limit=2,
            max_files=2,
            cancellation_token=_OpenCancellationToken(),
        ),
    )
    files = cast(list[Mapping[str, JsonValue]], value["files"])

    assert [item["name"] for item in files] == ["a.txt", "b.txt"]
    assert value["returned"] == 2
    assert value["total"] == 3
    assert value["scanned_entries"] == 3
    assert "scan_complete" not in value
    assert "truncated_reason" not in value


def test_list_and_search_order_is_stable_across_reversed_creation_order(
    tmp_path: Path,
) -> None:
    """相同目录内容按相反顺序创建时 list/search 结果顺序必须一致。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: list 记录或 search 命中顺序不稳定时抛出。
    """

    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    relative_files = (
        Path("zeta.txt"),
        Path("Alpha.txt"),
        Path("nested/bravo.txt"),
        Path("nested/Charlie.txt"),
    )
    fixed_timestamp = 1_700_000_000
    for root, creation_order in (
        (first_root, relative_files),
        (second_root, tuple(reversed(relative_files))),
    ):
        root.mkdir()
        for relative_path in creation_order:
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"Needle in {relative_path}\n", encoding="utf-8")
            os.utime(target, (fixed_timestamp, fixed_timestamp))

    list_values = [
        cast(
            Mapping[str, JsonValue],
            doc_tools._list_files_business(
                directory=str(root),
                pattern="*.txt",
                recursive=True,
                limit=len(relative_files),
                max_files=len(relative_files),
                cancellation_token=_OpenCancellationToken(),
            ),
        )
        for root in (first_root, second_root)
    ]
    search_values = [
        cast(
            Mapping[str, JsonValue],
            doc_tools._search_files_business(
                directory=str(root),
                query="Needle",
                include_types=None,
                limit=len(relative_files) + 1,
                max_results=len(relative_files) + 1,
                allowed_roots=(root.resolve(),),
                cancellation_token=_OpenCancellationToken(),
            ),
        )
        for root in (first_root, second_root)
    ]

    assert list_values[0]["files"] == list_values[1]["files"]
    list_files = cast(list[Mapping[str, JsonValue]], list_values[0]["files"])
    assert [record["name"] for record in list_files] == [
        "Alpha.txt",
        "bravo.txt",
        "Charlie.txt",
        "zeta.txt",
    ]
    assert search_values[0]["matches"] == search_values[1]["matches"]
    search_matches = cast(list[Mapping[str, JsonValue]], search_values[0]["matches"])
    assert [record["file"] for record in search_matches] == [
        "Alpha.txt",
        str(Path("nested/bravo.txt")),
        str(Path("nested/Charlie.txt")),
        "zeta.txt",
    ]


def test_directory_symlink_entry_is_yielded_without_recursing_target(
    tmp_path: Path,
) -> None:
    """确定性迭代器必须产出目录 symlink，但不得递归其目标。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: symlink entry 不可见或其目标被递归时抛出。
    """

    target_directory = tmp_path / "target"
    target_directory.mkdir()
    (target_directory / "inside.txt").write_text("inside", encoding="utf-8")
    link = tmp_path / "linked-directory"
    link.symlink_to(target_directory, target_is_directory=True)

    entries = [
        str(entry.relative_to(tmp_path))
        for entry in doc_tools._iter_directory_entries(
            tmp_path,
            recursive=True,
            cancellation_token=_OpenCancellationToken(),
        )
    ]

    assert "linked-directory" in entries
    assert str(Path("linked-directory/inside.txt")) not in entries
    assert str(Path("target/inside.txt")) in entries


def test_list_files_keeps_allowed_file_symlink_as_directory_entry(
    tmp_path: Path,
) -> None:
    """list_files 必须继续按 symlink entry 路径列出内部 file symlink。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: file symlink 未按自身路径与名称列出时抛出。
    """

    target = tmp_path / "target.txt"
    target.write_text("linked content", encoding="utf-8")
    link = tmp_path / "alias.txt"
    link.symlink_to(target)

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._list_files_business(
            directory=str(tmp_path),
            pattern="*.txt",
            recursive=False,
            limit=10,
            max_files=10,
            cancellation_token=_OpenCancellationToken(),
        ),
    )
    files = cast(list[Mapping[str, JsonValue]], value["files"])

    assert [record["name"] for record in files] == ["alias.txt", "target.txt"]
    assert files[0]["path"] == "alias.txt"
    assert files[0]["size"] == target.stat().st_size


def test_read_file_long_single_line_stops_at_character_limit(
    tmp_path: Path,
) -> None:
    """无换行长行必须最多累积字符预算加一个 probe。"""

    target = tmp_path / "long.txt"
    target.write_text("x" * 200, encoding="utf-8")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._read_file_business(
            file_path=str(target),
            start_line=None,
            end_line=None,
            max_chars=17,
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert value["content"] == "x" * 17
    assert value["returned_chars"] == 17
    assert value["content_truncated"] is True
    assert value["scan_complete"] is False
    assert value["total_lines"] is None


def test_read_file_multibyte_encoding_range_reports_complete_metadata(
    tmp_path: Path,
) -> None:
    """多字节 fallback 编码与行范围完整扫描必须返回精确元数据。"""

    target = tmp_path / "gbk.txt"
    target.write_bytes("第一行\n第二行\n第三行".encode("gbk"))

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._read_file_business(
            file_path=str(target),
            start_line=2,
            end_line=2,
            max_chars=100,
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert value["content"] == "第二行\n"
    assert value["returned_chars"] == 4
    assert value["content_truncated"] is False
    assert value["scan_complete"] is True
    assert value["total_lines"] == 3
    assert value["line_range"] == [2, 2]


def test_read_file_reads_complete_source_without_source_byte_limit(
    tmp_path: Path,
) -> None:
    """raw read 必须消费完整实际来源，不再产生 source byte limit 失败。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 返回文本或完整扫描事实不符合预期时抛出。
    """

    target = tmp_path / "complete-source.txt"
    target.write_bytes(b"123456789")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._read_file_business(
            file_path=str(target),
            start_line=None,
            end_line=None,
            max_chars=100,
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert value["content"] == "123456789"
    assert value["returned_chars"] == 9
    assert value["content_truncated"] is False
    assert value["scan_complete"] is True


def test_read_file_section_limit_returns_explicit_partial_fields(
    tmp_path: Path,
) -> None:
    """章节字符预算必须由 producer 显式投影，不依赖下游静默截断。"""

    target = _copy_fixture(tmp_path, "sample.md")
    value = cast(
        Mapping[str, JsonValue],
        doc_tools._read_file_section_business(
            file_path=str(target),
            ref="s_0001",
            max_chars=8,
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert len(str(value["content"])) == 8
    assert value["returned_chars"] == 8
    assert value["content_truncated"] is True
    assert value["scan_complete"] is False


def test_search_files_raw_long_line_finds_late_query_with_bounded_excerpt(
    tmp_path: Path,
) -> None:
    """raw search 不得按整行累积，仍须找到长行尾部关键词。"""

    target = tmp_path / "long.txt"
    target.write_text("x" * 700 + "Needle" + "y" * 50, encoding="utf-8")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._search_files_business(
            directory=str(tmp_path),
            query="needle",
            include_types=None,
            limit=5,
            max_results=5,
            allowed_roots=(tmp_path.resolve(),),
            cancellation_token=_OpenCancellationToken(),
        ),
    )
    matches = cast(list[Mapping[str, JsonValue]], value["matches"])

    assert value["total_matches"] == 1
    assert value["scan_complete"] is True
    assert "Needle" in str(matches[0]["matched_line_content"])
    assert len(str(matches[0]["matched_line_content"])) <= 300


def test_search_files_complete_source_enters_processor_and_returns_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search 必须把完整来源交给处理器并返回命中，不得按字节跳过。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: 处理器调用、命中或返回字段不符合预期时抛出。
    """

    target = tmp_path / "complete-source.md"
    target.write_text("# Title\n" + "Revenue" * 20, encoding="utf-8")
    processor_paths: list[Path] = []
    original_try_create = doc_tools._try_create_processor

    def spy_try_create_processor(
        source: SourceSnapshot,
        path: Path,
    ) -> DocumentProcessor | None:
        """记录实际进入 processor factory 的文件。

        Args:
            source: 已治理 Source。
            path: 原文件路径。

        Returns:
            原 helper 返回值。

        Raises:
            原 helper 异常原样透出。
        """

        processor_paths.append(path)
        return original_try_create(source, path)

    monkeypatch.setattr(doc_tools, "_try_create_processor", spy_try_create_processor)
    value = cast(
        Mapping[str, JsonValue],
        doc_tools._search_files_business(
            directory=str(tmp_path),
            query="Revenue",
            include_types=None,
            limit=5,
            max_results=5,
            allowed_roots=(tmp_path.resolve(),),
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    matches = cast(list[Mapping[str, JsonValue]], value["matches"])
    assert len(matches) == 1
    assert matches[0]["file"] == target.name
    assert value["scan_complete"] is True
    assert value["truncated_reason"] is None
    assert set(value) == {
        "query",
        "directory",
        "matches",
        "total_matches",
        "scanned_entries",
        "scan_complete",
        "truncated_reason",
    }
    assert processor_paths == [target.resolve()]


def test_search_files_cumulative_match_limit_returns_result_partial(
    tmp_path: Path,
) -> None:
    """累计 match cap 命中时必须停止并声明 result_limit。"""

    (tmp_path / "a.txt").write_text("Needle\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Needle\nNeedle\n", encoding="utf-8")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._search_files_business(
            directory=str(tmp_path),
            query="Needle",
            include_types=None,
            limit=2,
            max_results=2,
            allowed_roots=(tmp_path.resolve(),),
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert value["total_matches"] == 2
    assert value["scan_complete"] is False
    assert value["truncated_reason"] == "result_limit"


def test_search_files_scans_to_eof_when_result_limit_is_not_reached(
    tmp_path: Path,
) -> None:
    """search 未达到结果 limit 时必须扫描到 EOF 并返回完整事实。"""

    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text("no match", encoding="utf-8")
    (tmp_path / "c.txt").write_text("Needle", encoding="utf-8")

    value = cast(
        Mapping[str, JsonValue],
        doc_tools._search_files_business(
            directory=str(tmp_path),
            query="Needle",
            include_types=None,
            limit=5,
            max_results=5,
            allowed_roots=(tmp_path.resolve(),),
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert value["scanned_entries"] == 3
    assert value["total_matches"] == 1
    assert value["scan_complete"] is True
    assert value["truncated_reason"] is None


def test_search_files_processor_factory_receives_complete_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 search processor factory 接收完整快照而非自行重开原路径。

    Args:
        tmp_path: pytest 临时目录。
        monkeypatch: pytest monkeypatch fixture。

    Returns:
        无。

    Raises:
        AssertionError: factory 输入类型、调用次数或搜索结果不符合约定时抛出。
    """

    target = tmp_path / "report.md"
    target.write_text("# Report\nRevenue", encoding="utf-8")
    captured_sources: list[SourceSnapshot] = []

    def fake_create_processor(source: SourceSnapshot) -> None:
        """记录 factory 输入并强制 raw scan。

        Args:
            source: processor factory 输入。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        captured_sources.append(source)
        return None

    monkeypatch.setattr(doc_tools, "create_doc_file_processor", fake_create_processor)
    value = cast(
        Mapping[str, JsonValue],
        doc_tools._search_files_business(
            directory=str(tmp_path),
            query="Revenue",
            include_types=None,
            limit=5,
            max_results=5,
            allowed_roots=(tmp_path.resolve(),),
            cancellation_token=_OpenCancellationToken(),
        ),
    )

    assert len(captured_sources) == 1
    assert isinstance(captured_sources[0], SourceSnapshot)
    assert value["total_matches"] == 1


def test_doc_tool_descriptions_explain_only_retained_output_facts(
    tmp_path: Path,
) -> None:
    """LLM-facing 描述应自足解释完整 list 与合法 output limit。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 描述缺少完整遍历或合法 output limit 语义时抛出。
    """

    definitions = _definitions_by_name(_discover_definitions(tmp_path))

    list_description = definitions["list_files"].schema.function.description
    assert list_description == (
        "列出配置允许访问目录中的文件。files 是按稳定顺序返回的首批记录，returned 是返回数，"
        "total 是完整遍历后的匹配文件总数，scanned_entries 是完整检查的目录项数。"
        "若 total 大于 returned，表示 limit 限制了本次返回数量；可收紧 pattern 或在参数允许范围内提高 limit。"
        "定位后把 files[].path 交给 get_file_sections、read_file 或 read_file_section。"
    )
    assert "scan_complete" not in list_description
    assert "truncated_reason" not in list_description
    search_description = definitions["search_files"].schema.function.description
    assert "result_limit" in search_description
    assert search_description == (
        "在配置允许访问目录中按关键词查找。matches 是本次命中，total_matches 等于返回命中数，"
        "scanned_entries 是已检查目录项数。scan_complete=false 且 truncated_reason=result_limit 表示"
        "命中数达到 limit，可收紧关键词或在参数允许范围内提高 limit 后重试；完整扫描时"
        "scan_complete=true 且 truncated_reason 为 null。"
        "若命中带 ref，把 matches[].file 和 ref 交给 read_file_section；ref 为 null 时用 read_file。"
    )
    read_description = definitions["read_file"].schema.function.description
    assert "content_truncated" in read_description
    assert "scan_complete" in read_description


def test_doc_complete_input_real_smoke_above_legacy_thresholds(
    tmp_path: Path,
) -> None:
    """真实大目录与大文件必须经 discovery/callable 完整进入 Doc owner。

    Args:
        tmp_path: pytest 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: list/read/search 完整输入、symlink containment 或既有
            output limit contract 不符合预期时抛出。
        OSError: 真实 fixture 创建失败时透出。
    """

    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    small_content = b"ordinary content\n"
    for index in range(_REAL_SMOKE_SMALL_FILE_COUNT):
        (allowed_root / f"entry-{index:05d}.txt").write_bytes(small_content)

    large_file = allowed_root / _REAL_SMOKE_LARGE_FILE_NAME
    chunk = b"x" * _REAL_SMOKE_CHUNK_BYTES
    with large_file.open("wb") as stream:
        for _ in range(_REAL_SMOKE_CHUNK_COUNT):
            stream.write(chunk)
        stream.write(b"\n")
        stream.write(_REAL_SMOKE_TAIL_MARKER.encode("ascii"))
    assert large_file.stat().st_size > _REAL_SMOKE_MIN_LARGE_FILE_BYTES

    outside_file = outside_root / "outside.txt"
    outside_file.write_text(_REAL_SMOKE_TAIL_MARKER, encoding="utf-8")
    outside_link = allowed_root / _REAL_SMOKE_OUTSIDE_LINK_NAME
    outside_link.symlink_to(outside_file)
    expected_scanned_entries = _REAL_SMOKE_SMALL_FILE_COUNT + 2

    spec = _spec(allowed_root)
    provider_output = discover_tools(spec)
    definitions = _definitions_by_name(provider_output.definitions)

    list_outcome = asyncio.run(
        definitions["list_files"].callable(
            _call(
                "list_files",
                {
                    "directory": str(allowed_root),
                    "pattern": _REAL_SMOKE_LARGE_FILE_NAME,
                    "recursive": True,
                },
            ),
            _context(),
        )
    )
    assert isinstance(list_outcome, ToolCompletedOutcome)
    list_value = cast(Mapping[str, JsonValue], list_outcome.result.value)
    listed_files = cast(list[Mapping[str, JsonValue]], list_value["files"])
    assert list_value["total"] == 1
    assert list_value["returned"] == 1
    assert list_value["scanned_entries"] == expected_scanned_entries
    assert listed_files[0]["path"] == str(large_file.resolve())
    assert "scan_complete" not in list_value
    assert "truncated_reason" not in list_value

    read_definition = definitions["read_file"]
    read_outcome = asyncio.run(
        read_definition.callable(
            _call("read_file", {"file_path": str(large_file)}),
            _context(),
        )
    )
    assert isinstance(read_outcome, ToolCompletedOutcome)
    read_value = cast(Mapping[str, JsonValue], read_outcome.result.value)
    assert read_value["returned_chars"] == 2000
    assert read_value["content_truncated"] is True
    assert isinstance(read_definition.truncate, ToolTruncateSpec)
    assert read_definition.truncate.target_field == "content"

    search_outcome = asyncio.run(
        definitions["search_files"].callable(
            _call(
                "search_files",
                {
                    "directory": str(allowed_root),
                    "query": _REAL_SMOKE_TAIL_MARKER,
                },
            ),
            _context(),
        )
    )
    assert isinstance(search_outcome, ToolCompletedOutcome)
    search_value = cast(Mapping[str, JsonValue], search_outcome.result.value)
    matches = cast(list[Mapping[str, JsonValue]], search_value["matches"])
    assert search_value["scanned_entries"] == expected_scanned_entries
    assert search_value["total_matches"] == 1
    assert search_value["scan_complete"] is True
    assert search_value["truncated_reason"] is None
    assert matches[0]["file"] == str(large_file.resolve())
    assert _REAL_SMOKE_TAIL_MARKER in str(matches[0]["snippet"])

    direct_read_escape = asyncio.run(
        read_definition.callable(
            _call("read_file", {"file_path": str(outside_link)}),
            _context(),
        )
    )
    assert isinstance(direct_read_escape, ToolFailedOutcome)
    assert direct_read_escape.result.error == "permission_denied"


def test_search_files_does_not_read_symlink_escape(
    tmp_path: Path,
) -> None:
    """allowed root 内 symlink 指向 root 外时 search_files 不得读取目标内容。"""

    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / "secret.txt"
    outside_file.write_text("revenue outside root", encoding="utf-8")
    symlink_path = allowed_root / "linked-secret.txt"
    symlink_path.symlink_to(outside_file)
    definitions = _definitions_by_name(_discover_definitions(allowed_root))

    search_outcome = asyncio.run(
        definitions["search_files"].callable(
            _call(
                "search_files",
                {
                    "directory": str(allowed_root),
                    "query": "revenue",
                },
            ),
            _context(),
        )
    )

    assert isinstance(search_outcome, ToolCompletedOutcome)
    value = cast(Mapping[str, JsonValue], search_outcome.result.value)
    assert value["matches"] == []
    assert value["total_matches"] == 0


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

    def fake_try_create_processor(
        source: SourceSnapshot,
        path: Path,
    ) -> None:
        """强制搜索走行扫描 fallback。

        :param source: 已治理的 Source。
        :param path: 候选文件路径。
        :returns: 始终返回 ``None``。
        """

        del source, path
        return None

    def fake_search_via_line_scan(
        source: SourceSnapshot,
        relative_path: str,
        query: str,
        remaining: int,
        cancellation_token: CancellationToken | None = None,
    ) -> list[dict[str, JsonValue]]:
        """记录首个扫描文件并触发取消。

        :param source: 当前完整 Source 快照。
        :param relative_path: 相对路径。
        :param query: 搜索词。
        :param remaining: 剩余结果数量。
        :param cancellation_token: Host 注入的取消令牌。
        :returns: 空匹配，迫使外层继续迭代并命中 checkpoint。
        """

        del source, query, remaining, cancellation_token
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

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert len(scanned_paths) == 1


def test_search_via_line_scan_observes_loop_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_search_via_line_scan 行扫描循环内必须观察取消。"""

    target = tmp_path / "large.txt"
    target.write_text("Revenue\nRevenue\n", encoding="utf-8")
    token = _CancelAfterObservationToken(cancel_at=2)
    monkeypatch.setattr(doc_tools, "_DOC_STREAM_CHUNK_BYTES", 1)
    source = LocalFileSource(path=target, uri=str(target))
    with SourceSnapshot(source) as snapshot:
        with pytest.raises(doc_tools._DocCancelledError):
            doc_tools._search_via_line_scan(snapshot, "large.txt", "Revenue", 10, token)


def test_search_files_line_scan_cancellation_returns_host_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """line scan 观察到取消时 search_files 必须返回 host_cancelled。"""

    target = tmp_path / "large.txt"
    target.write_text("Revenue\nRevenue\n", encoding="utf-8")
    definitions = _definitions_by_name(_discover_definitions(tmp_path))
    token = _CancelAfterObservationToken(cancel_at=5)

    def fake_try_create_processor(
        source: SourceSnapshot,
        path: Path,
    ) -> None:
        """强制搜索走行扫描 fallback。

        :param source: 已治理的 Source。
        :param path: 候选文件路径。
        :returns: 始终返回 ``None``。
        """

        del source, path
        return None
    monkeypatch.setattr(doc_tools, "_DOC_STREAM_CHUNK_BYTES", 1)
    monkeypatch.setattr(doc_tools, "_try_create_processor", fake_try_create_processor)

    outcome = asyncio.run(
        definitions["search_files"].callable(
            _call("search_files", {"directory": str(tmp_path), "query": "Revenue"}),
            _context(token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


def test_read_file_cancelled_after_first_failed_encoding_stops_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """read_file 首个编码失败并触发取消后不得继续尝试 fallback 编码。"""

    target = tmp_path / "encoded.txt"
    target.write_bytes(b"\xffencoded")
    token = _CancelAfterObservationToken(cancel_at=2)
    source = LocalFileSource(path=target, uri=str(target))
    with SourceSnapshot(source) as snapshot:
        with pytest.raises(doc_tools._DocCancelledError):
            doc_tools._read_bounded_text(
                snapshot=snapshot,
                encodings=("utf-8", "latin1"),
                max_chars=100,
                start_line=1,
                end_line=None,
                cancellation_token=token,
            )


def test_markdown_section_extraction_observes_cooperative_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Markdown 章节提取长循环必须提供协作式取消检查。"""

    token = _ManualCancellationToken()
    token.cancel("cancel markdown extraction")
    monkeypatch.setattr(doc_tools, "_DOC_LOOP_CANCELLATION_CHECK_INTERVAL", 1)

    with pytest.raises(doc_tools._DocCancelledError):
        doc_tools._extract_markdown_sections(["# A\n", "# B\n"], token)


def test_count_file_lines_observes_cooperative_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """行数统计 helper 长循环必须提供协作式取消检查。"""

    target = tmp_path / "large.md"
    target.write_text("line 1\nline 2\n", encoding="utf-8")
    token = _ManualCancellationToken()
    token.cancel("cancel line count")
    monkeypatch.setattr(doc_tools, "_DOC_LOOP_CANCELLATION_CHECK_INTERVAL", 1)

    source = LocalFileSource(path=target, uri=str(target))
    with SourceSnapshot(source) as snapshot:
        with pytest.raises(doc_tools._DocCancelledError):
            doc_tools._count_source_lines(snapshot, token)


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

    output = discover_tools(_spec(_FIXTURE_ROOT))
    names = {definition.name for definition in output.definitions}

    assert "fetch_more" not in names


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
    tools_root = Path(__file__).resolve().parents[2] / "dayu" / "tools"
    doc_tools_source = (tools_root / "doc_tools.py").read_text(encoding="utf-8")
    doc_provider_source = (tools_root / "doc_provider.py").read_text(encoding="utf-8")
    old_runtime_modules = {
        "dayu.engine.tool_registry",
        "dayu.engine.truncation_manager",
        "dayu.engine.tool_result",
    }
    for source in (doc_tools_source, doc_provider_source):
        imported_modules = _imported_modules(source)
        assert old_runtime_modules.isdisjoint(imported_modules)
    assert "fetch_more" not in doc_tools_source
    assert "TruncationManager" not in doc_tools_source


def test_doc_provider_explicit_limits_shape_schema_and_truncate_specs(tmp_path: Path) -> None:
    """Doc provider 必须把显式完整 limits 配置投影到参数 schema 与截断声明。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 参数上限或截断声明未反映显式配置时抛出。
    """

    definitions = _definitions_by_name(
        discover_tools(
            _spec_with_config(
                {
                    "allowed_paths": [str(tmp_path)],
                    "limits": {
                        "list_files_max": 31,
                        "get_sections_max": 32,
                        "search_files_max_results": 33,
                        "read_file_max_chars": 3400,
                        "read_file_section_max_chars": 3500,
                    },
                }
            )
        ).definitions
    )

    assert _parameter_maximum(definitions["list_files"], "limit") == 31
    assert _parameter_maximum(definitions["get_file_sections"], "limit") == 32
    assert _parameter_maximum(definitions["search_files"], "limit") == 33
    assert _truncate_limit(definitions["read_file"], "max_chars") == 3400
    assert _truncate_limit(definitions["read_file_section"], "max_chars") == 3500


def test_doc_provider_partial_limits_fall_back_to_defaults(tmp_path: Path) -> None:
    """Doc provider 必须把缺失的单项 limits 回退到 dataclass 默认值。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 显式 limit 或默认 limit 投影不符合预期时抛出。
    """

    defaults = doc_tools.DocToolLimits()
    definitions = _definitions_by_name(
        discover_tools(
            _spec_with_config(
                {
                    "allowed_paths": [str(tmp_path)],
                    "limits": {
                        "list_files_max": 99,
                    },
                }
            )
        ).definitions
    )

    assert _parameter_maximum(definitions["list_files"], "limit") == 99
    assert _parameter_maximum(definitions["get_file_sections"], "limit") == (
        defaults.get_sections_max
    )
    assert _parameter_maximum(definitions["search_files"], "limit") == (
        defaults.search_files_max_results
    )
    assert _truncate_limit(definitions["read_file"], "max_chars") == defaults.read_file_max_chars
    assert _truncate_limit(definitions["read_file_section"], "max_chars") == (
        defaults.read_file_section_max_chars
    )


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


def test_doc_toolruntime_cancel_returns_governed_failure_without_late_accept(
    tmp_path: Path,
) -> None:
    """Doc process-backed 工具取消后不得接受旧子进程 late result。"""

    markdown_path = _copy_fixture(tmp_path, "sample.md")
    output = discover_tools(_spec(tmp_path))
    definitions = tuple(
        replace(
            definition,
            execution=ProcessBackedToolExecutionCapability(
                target_factory=_SlowProcessTargetFactory(sleep_seconds=5.0)
            ),
        )
        if definition.name == "read_file"
        else definition
        for definition in output.definitions
    )
    accept_port = _AcceptingPort()
    token = _ManualCancellationToken()
    tool_runtime = DefaultToolRuntimeFactory(
        EffectiveToolBundleBuilder()
    ).create_tool_runtime(
        ToolRuntimeBuildRequest(
            effective_bundle_request=EffectiveToolBundleBuildRequest(
                business_tool_bundle=ToolBundle(definitions=definitions),
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

    started_at = time.monotonic()
    governed_outcome = asyncio.run(
        _execute_doc_runtime_read_file_and_cancel(
            tool_runtime,
            markdown_path,
            token,
        )
    )
    elapsed = time.monotonic() - started_at
    time.sleep(0.3)

    assert elapsed < 2.0
    assert governed_outcome.result.hint is None
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_cancelled"
    )


def test_doc_toolruntime_cancel_terminates_real_doc_target_blocked_on_fifo(
    tmp_path: Path,
) -> None:
    """真实 Doc process target 阻塞在 FIFO 读取时取消应快速 governed closeout。"""

    if os.name != "posix":
        pytest.skip("POSIX FIFO is required for deterministic real Doc target blocking I/O")
    fifo_path = tmp_path / "blocked.md"
    os.mkfifo(fifo_path)
    output = discover_tools(_spec(tmp_path))
    accept_port = _AcceptingPort()
    token = _ManualCancellationToken()
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

    started_at = time.monotonic()
    governed_outcome = asyncio.run(
        _execute_doc_runtime_read_file_and_cancel(
            tool_runtime,
            fifo_path,
            token,
        )
    )
    elapsed = time.monotonic() - started_at
    time.sleep(0.3)

    assert elapsed < 2.0
    assert governed_outcome.result.hint is None
    assert len(accept_port.candidates) == 1
    assert accept_port.candidates[0].governance.policy_decision.reason_code == (
        "tool_runtime_cancelled"
    )


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


def _spec_with_config(config: Mapping[str, JsonValue]) -> ToolsDiscoveryProviderSpec:
    """构造 Doc provider spec。

    :param config: provider config。
    :returns: provider spec。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id="doc-tools",
        location=PythonImportPathProvider("dayu.tools.doc_provider:discover_tools"),
        enabled=True,
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


def _parameter_maximum(definition: ToolDefinition, parameter_name: str) -> int:
    """读取工具参数 schema 的 maximum。

    :param definition: 工具定义。
    :param parameter_name: 参数名。
    :returns: 参数 maximum。
    :raises AssertionError: 参数 schema 不是 JSON object 或 maximum 不是整数时抛出。
    """

    parameter_schema = definition.schema.function.parameters.properties[parameter_name]
    assert isinstance(parameter_schema, Mapping)
    maximum = parameter_schema.get("maximum")
    assert isinstance(maximum, int)
    return maximum


def _truncate_limit(definition: ToolDefinition, limit_name: str) -> int:
    """读取工具截断声明中的限制值。

    :param definition: 工具定义。
    :param limit_name: limit 字段名。
    :returns: 截断限制值。
    :raises AssertionError: 工具没有截断声明或限制值不是整数时抛出。
    """

    truncate = definition.truncate
    assert isinstance(truncate, ToolTruncateSpec)
    limit = truncate.limits[limit_name]
    assert isinstance(limit, int)
    return limit


def _run_definition_process_target(
    definition: ToolDefinition,
    call: ToolCallRequest,
) -> JsonValue:
    """构造并直接执行定义声明的 process target。

    :param definition: Doc 工具定义。
    :param call: 单次工具调用请求。
    :returns: process target 返回的 JSON 信封。
    :raises AssertionError: 定义未声明 process-backed execution 时抛出。
    """

    assert isinstance(definition.execution, ProcessBackedToolExecutionCapability)
    target = definition.execution.target_factory.build_process_target(
        call,
        ProcessBackedToolContext(
            run_id="run-doc",
            session_id="session-doc",
            iteration_id="iteration-doc",
            timeout_seconds=10.0,
            correlation_id="correlation-doc",
        ),
    )
    return target()


async def _execute_doc_runtime_read_file_and_cancel(
    tool_runtime: ToolRuntimeHandle,
    markdown_path: Path,
    token: _ManualCancellationToken,
) -> ToolFailedOutcome:
    """启动 ToolRuntime read_file 执行并触发取消。

    :param tool_runtime: 测试构造的 ToolRuntime handle。
    :param markdown_path: 待读取文件。
    :param token: 测试取消 token。
    :returns: 受治理的取消失败 outcome。
    :raises AssertionError: runtime 未返回失败 outcome 时抛出。
    """

    task = asyncio.create_task(
        tool_runtime.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(
                    _call("read_file", {"file_path": str(markdown_path)}),
                ),
                context=_context(token),
            )
        )
    )
    await asyncio.sleep(0.3)
    token.cancel("doc process cancel")
    outcome = await asyncio.wait_for(task, timeout=2.0)
    record_outcome = outcome.records[0].outcome
    assert isinstance(record_outcome, ToolFailedOutcome)
    return record_outcome


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


def _assert_no_governance_text(text: str) -> None:
    """断言 LLM-facing 文本未泄漏 Host 治理字符串。

    :param text: 待检查的 outcome message / hint 文本。
    :returns: 无。
    :raises AssertionError: 文本包含治理字符串时抛出。
    """

    for forbidden in _FORBIDDEN_CANCEL_MESSAGE_PARTS:
        assert forbidden not in text


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
