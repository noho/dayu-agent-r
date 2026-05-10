"""Host P2 ToolRuntime 边界测试。"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

import dayu.engine as engine
import dayu.host as host
import dayu.host.contracts as host_contracts
from dayu.contracts import (
    FRAMEWORK_FETCH_MORE_TOOL_NAME,
    JsonValue,
    ToolTruncateSpec,
    ToolTruncationInfo,
)
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    ToolResultTruncatedData,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._tool_runtime import InMemoryToolRuntime


@dataclass(frozen=True, slots=True)
class _Token:
    """测试用永不取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否取消。"""

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。"""

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。"""

        return None


@dataclass(slots=True)
class _Executor:
    """返回固定值的 fake executor。"""

    value: JsonValue

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行 fake 工具。

        :param request: 工具执行请求。
        :returns: 成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=self.value,
                truncation=None,
                meta=None,
            )
        )


def _request(
    *,
    run_id: str = "run_1",
    session_id: str = "session_1",
    tool_call_id: str = "tc_1",
) -> ToolExecutionRequest:
    """构造工具执行请求。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param tool_call_id: 工具调用 id。
    :returns: ToolExecutionRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id=tool_call_id,
            name="demo",
            arguments={},
            index_in_iteration=0,
            provider_state=None,
        ),
        context=ToolExecutionContext(
            run_id=run_id,
            session_id=session_id,
            iteration_id="iter_1",
            tool_call_id=tool_call_id,
            index_in_iteration=0,
            timeout_seconds=None,
            cancellation_token=_Token(),
            correlation_id=None,
        ),
    )


def _framework_request(
    *,
    cursor_value: str,
    scope_token: str,
    run_id: str = "run_1",
    session_id: str = "session_1",
    tool_call_id: str = "fetch_call_1",
) -> ToolExecutionRequest:
    """构造 framework ``fetch_more`` 工具执行请求。

    :param cursor_value: cursor 原文。
    :param scope_token: scope token 明文。
    :param run_id: Run id。
    :param session_id: 会话 id。
    :param tool_call_id: framework tool call id。
    :returns: ToolExecutionRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id=tool_call_id,
            name=FRAMEWORK_FETCH_MORE_TOOL_NAME,
            arguments={
                "cursor": cursor_value,
                "scope_token": scope_token,
            },
            index_in_iteration=0,
            provider_state=None,
        ),
        context=ToolExecutionContext(
            run_id=run_id,
            session_id=session_id,
            iteration_id="iter_1",
            tool_call_id=tool_call_id,
            index_in_iteration=0,
            timeout_seconds=None,
            cancellation_token=_Token(),
            correlation_id=None,
        ),
    )


def _runtime() -> tuple[InMemoryToolRuntime, InMemoryRunEventStore]:
    """构造 runtime。

    :returns: runtime 与 store。
    :raises Exception: 不主动抛出异常。
    """

    store = InMemoryRunEventStore()
    runtime = InMemoryToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3]),
        event_store=store,
        truncate_specs={
            "demo": ToolTruncateSpec(
                enabled=True,
                strategy="list_items",
                limits={"max_items": 1},
                target_field=None,
                field_path=None,
                ttl_seconds=30,
            )
        },
        token_generator=lambda: "cursor-boundary",
    )
    return runtime, store


def _imported_modules(root: Path) -> list[tuple[Path, str]]:
    """收集 Python 文件中的 import 模块。

    :param root: 扫描根目录。
    :returns: 文件与模块名元组列表。
    :raises SyntaxError: 源码无法解析时抛出。
    """

    modules: list[tuple[Path, str]] = []
    for file_path in sorted(root.rglob("*.py")):
        if "__pycache__" in file_path.parts:
            continue
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append((file_path, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                modules.append((file_path, node.module))
    return modules


def test_host_does_not_export_internal_tool_runtime_implementations() -> None:
    """Host 包根不得直接导出内部 ToolRuntime 实现。"""

    exported = frozenset(host.__all__)
    assert "ToolFetchMoreRequest" in exported
    assert "ToolFetchMoreHandle" not in exported
    assert "InMemoryToolRuntime" not in exported
    assert "ToolRuntimeToolExecutor" not in exported
    assert "ToolExecutor" not in exported
    assert not hasattr(host, "InMemoryToolRuntime")
    assert not hasattr(host, "ToolRuntimeToolExecutor")


def test_legacy_fetch_more_handle_contracts_are_not_public() -> None:
    """旧 public fetch_more handle 协议不得从包根或 contracts 导出。"""

    forbidden = frozenset(
        {
            "ToolFetchMoreHandleRequest",
            "ToolFetchMoreHandle",
            "ToolFetchMoreHandleSucceededResult",
            "ToolFetchMoreHandleFailedResult",
            "ToolFetchMoreHandleResult",
        }
    )
    assert forbidden.isdisjoint(frozenset(host.__all__))
    assert forbidden.isdisjoint(frozenset(host_contracts.__all__))
    for name in forbidden:
        assert not hasattr(host, name)
        assert not hasattr(host_contracts, name)


def test_engine_does_not_import_host_or_tool_runtime() -> None:
    """Engine 不得 import Host 或 ToolRuntime。"""

    engine_file = engine.__file__
    assert engine_file is not None
    root = Path(engine_file).resolve().parent
    violations = [
        (str(path), module)
        for path, module in _imported_modules(root)
        if module == "dayu.host" or module.startswith("dayu.host.")
    ]
    assert violations == []


@pytest.mark.asyncio
async def test_scope_token_delivered_only_via_outcome_truncation_not_eventlog() -> None:
    """scope token 不进入 EventLog，但通过 outcome.truncation 暴露给模型。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None
    assert truncation.scope_token

    events = await store.list_events("run_1", after=None)
    serialized_events = repr(events)
    assert "scope_token" not in serialized_events
    assert "cursor-boundary" not in serialized_events
    assert isinstance(events[0].data, ToolResultTruncatedData)

    fetch_outcome = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
        )
    )
    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    assert fetch_outcome.result.value == [2]


@pytest.mark.asyncio
async def test_scope_binding_rejects_cross_session_or_run() -> None:
    """cursor 绑定 session / run；framework fetch_more 跨边界返回失败。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    for session_id, run_id in (
        ("session_2", "run_1"),
        ("session_1", "run_2"),
    ):
        denied = await runtime.execute_tool_call(
            _framework_request(
                cursor_value=truncation.cursor,
                scope_token=truncation.scope_token,
                session_id=session_id,
                run_id=run_id,
                tool_call_id=f"fetch_call_{session_id}_{run_id}",
            )
        )
        assert isinstance(denied, ToolFailedOutcome)
        assert denied.result.error == "cursor_scope_mismatch"
    # cursor owner Run 仍只看到 owner 端的 denial 事实
    owner_events = await store.list_events("run_1", after=None)
    assert any(
        event.type is host.RunEventType.TOOL_CURSOR_DENIED
        for event in owner_events
    )


@pytest.mark.asyncio
async def test_cross_run_fetch_more_does_not_pollute_claimed_run() -> None:
    """跨 Run 补读拒绝事实只能归属 cursor owner Run。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    denied = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
            run_id="run_2",
        )
    )

    assert isinstance(denied, ToolFailedOutcome)
    assert denied.result.error == "cursor_scope_mismatch"
    owner_events = await store.list_events("run_1", after=None)
    claimed_events = await store.list_events("run_2", after=None)
    assert claimed_events == ()
    assert [event.type for event in owner_events[-2:]] == [
        host.RunEventType.TOOL_CURSOR_DENIED,
        host.RunEventType.TOOL_FETCH_MORE_FAILED,
    ]


def test_engine_tool_projection_includes_llm_fetch_more_hint() -> None:
    """Engine LLM projection 只在 tool message 中携带补读凭证。"""

    from dayu.engine.agent import _project_tool_outcome_for_llm

    projected = _project_tool_outcome_for_llm(
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"preview": "abc"},
                truncation=ToolTruncationInfo(
                    cursor="cursor-value",
                    scope_token="secret-token",
                    scope_hash="secret-hash",
                    has_more=True,
                    limit=None,
                    ttl_seconds=30,
                ),
                meta=None,
            )
        )
    )
    payload = json.loads(projected)
    assert payload == {
        "preview": "abc",
        "truncation": {
            "fetch_more_args": {
                "cursor": "cursor-value",
                "scope_token": "secret-token",
            },
            "has_more": True,
            "next_action": "fetch_more",
            "ttl_seconds": 30,
        },
    }
    assert "fetch_more_args" in projected
    assert "scope_token" in projected
    assert "secret-token" in projected
    assert "secret-hash" not in projected
