"""Host P2 ToolRuntime EventLog 事实测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

import pytest

from dayu.contracts import (
    FRAMEWORK_FETCH_MORE_TOOL_NAME,
    JsonValue,
    ToolTruncateSpec,
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
from dayu.engine import FinalAnswerData, FinishReason
from dayu.host import (
    RunEventKind,
    RunEventSource,
    RunEventType,
    ToolFetchMoreCompletedData,
    ToolFetchMoreFailedData,
    ToolFetchMoreRequestedData,
    ToolResultTruncatedData,
)
from dayu.host.contracts import RunEventDraft
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


@dataclass(slots=True)
class _Clock:
    """可手动推进的 monotonic clock。"""

    now: float = 100.0

    def __call__(self) -> float:
        """返回当前 monotonic 时间。

        :returns: 当前 monotonic 秒数。
        :raises Exception: 不主动抛出异常。
        """

        return self.now


def _spec() -> ToolTruncateSpec:
    """构造列表截断声明。

    :returns: ToolTruncateSpec。
    :raises Exception: 不主动抛出异常。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy="list_items",
        limits={"max_items": 2},
        target_field=None,
        field_path=None,
        ttl_seconds=30,
    )


def _request(
    *,
    run_id: str = "run_1",
    session_id: str = "session_1",
    tool_call_id: str = "tc_1",
    tool_name: str = "demo",
) -> ToolExecutionRequest:
    """构造工具执行请求。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :returns: ToolExecutionRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id=tool_call_id,
            name=tool_name,
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
    limit: int | None = None,
) -> ToolExecutionRequest:
    """构造 framework ``fetch_more`` 工具执行请求。

    :param cursor_value: cursor 原文。
    :param scope_token: scope token 明文。
    :param run_id: Run id。
    :param session_id: 会话 id。
    :param tool_call_id: framework tool call id。
    :param limit: 可选 limit。
    :returns: ToolExecutionRequest。
    :raises Exception: 不主动抛出异常。
    """

    arguments: dict[str, JsonValue] = {
        "cursor": cursor_value,
        "scope_token": scope_token,
    }
    if limit is not None:
        arguments["limit"] = limit
    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id=tool_call_id,
            name=FRAMEWORK_FETCH_MORE_TOOL_NAME,
            arguments=arguments,
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
    """构造 runtime 与 event store。

    :returns: runtime 与 store。
    :raises Exception: 不主动抛出异常。
    """

    store = InMemoryRunEventStore()
    runtime = InMemoryToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3, 4]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=lambda: "cursor-eventlog",
    )
    return runtime, store


@pytest.mark.asyncio
async def test_eventlog_contains_neutral_truncation_facts_without_token() -> None:
    """RunEvent 只保存中性摘要，不保存 token 明文或大结果。"""

    runtime, store = _runtime()

    await runtime.execute_tool_call(_request())

    events = await store.list_events("run_1", after=None)
    serialized = repr(events)
    assert "cursor-eventlog" not in serialized
    assert "scope_token" not in serialized
    assert "1, 2, 3, 4" not in serialized
    assert [event.kind for event in events] == [
        RunEventKind.CANONICAL,
        RunEventKind.CANONICAL,
    ]
    assert [event.source for event in events] == [
        RunEventSource.HOST,
        RunEventSource.HOST,
    ]


@pytest.mark.asyncio
async def test_fetch_more_event_order_and_return_event_cursor() -> None:
    """framework ``fetch_more`` 按 requested -> completed 顺序写入事实。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None
    first_event = (await store.list_events("run_1", after=None))[0]
    truncated = cast(ToolResultTruncatedData, first_event.data)

    fetch_outcome = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
            limit=1,
        )
    )

    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    events = await store.list_events("run_1", after=None)
    assert [event.type for event in events] == [
        RunEventType.TOOL_RESULT_TRUNCATED,
        RunEventType.TOOL_CURSOR_ISSUED,
        RunEventType.TOOL_FETCH_MORE_REQUESTED,
        RunEventType.TOOL_FETCH_MORE_COMPLETED,
        RunEventType.TOOL_CURSOR_ISSUED,
    ]
    requested = events[2].data
    completed = events[3].data
    assert isinstance(requested, ToolFetchMoreRequestedData)
    assert isinstance(completed, ToolFetchMoreCompletedData)
    assert requested.cursor_fingerprint == truncated.cursor_fingerprint
    assert completed.next_cursor_fingerprint is not None


@pytest.mark.asyncio
async def test_denied_fetch_more_appends_denied_and_failed_facts() -> None:
    """scope token 错误时追加 denied 与 failed canonical facts。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    fetch_outcome = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token="wrong-token",
        )
    )

    assert isinstance(fetch_outcome, ToolFailedOutcome)
    events = await store.list_events("run_1", after=None)
    assert [event.type for event in events[-3:]] == [
        RunEventType.TOOL_FETCH_MORE_REQUESTED,
        RunEventType.TOOL_CURSOR_DENIED,
        RunEventType.TOOL_FETCH_MORE_FAILED,
    ]
    failed = events[-1].data
    assert isinstance(failed, ToolFetchMoreFailedData)
    assert failed.denied is True


@pytest.mark.asyncio
async def test_cross_run_fetch_more_appends_owner_cursor_denied_fact() -> None:
    """跨 Run framework ``fetch_more`` 拒绝事实进入 cursor owner Run。"""

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
    owner_events = await store.list_events("run_1", after=None)
    claimed_events = await store.list_events("run_2", after=None)
    assert claimed_events == ()
    assert owner_events[-1].type == RunEventType.TOOL_FETCH_MORE_FAILED
    assert RunEventType.TOOL_CURSOR_DENIED in {event.type for event in owner_events}


@pytest.mark.asyncio
async def test_expired_cursor_appends_owner_cursor_expired_fact() -> None:
    """过期 cursor 经 framework ``fetch_more`` 进入 cursor owner RunEvent。"""

    clock = _Clock()
    store = InMemoryRunEventStore()
    runtime = InMemoryToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3, 4]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        clock=clock,
        token_generator=lambda: "cursor-handle-expired",
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None
    clock.now = 131.0

    expired = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
        )
    )

    assert isinstance(expired, ToolFailedOutcome)
    events = await store.list_events("run_1", after=None)
    event_types = [event.type for event in events]
    assert RunEventType.TOOL_CURSOR_EXPIRED in event_types
    assert events[-1].type == RunEventType.TOOL_FETCH_MORE_FAILED


@pytest.mark.asyncio
async def test_terminal_run_fetch_more_returns_failure_without_new_event() -> None:
    """terminal Run 后 framework ``fetch_more`` 返回失败 outcome，不追加新 RunEvent。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None
    await store.append(
        RunEventDraft(
            run_id="run_1",
            session_id="session_1",
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.ENGINE,
            type=RunEventType.FINAL_ANSWER,
            occurred_at=datetime.now(tz=timezone.utc),
            data=FinalAnswerData(
                content="done",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            source_engine_event_id="engine-final",
        )
    )
    before_terminal = await store.list_events("run_1", after=None)

    fetch_outcome = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
        )
    )

    after = await store.list_events("run_1", after=None)
    assert isinstance(fetch_outcome, ToolFailedOutcome)
    assert fetch_outcome.result.error == "run_terminal"
    # framework fetch_more 在 run terminal 时不追加新 RunEvent
    assert len(after) == len(before_terminal)
