"""Host P2 ToolRuntime EventLog 事实测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import pytest

from dayu.contracts import (
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
)
from dayu.host.contracts import RunEventDraft
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._framework_tools import FRAMEWORK_FETCH_MORE_NAME
from dayu.host._tool_runtime import HostToolRuntime


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
            name=FRAMEWORK_FETCH_MORE_NAME,
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


def _runtime() -> tuple[HostToolRuntime, InMemoryRunEventStore]:
    """构造 runtime 与 event store。

    :returns: runtime 与 store。
    :raises Exception: 不主动抛出异常。
    """

    store = InMemoryRunEventStore()
    runtime = HostToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3, 4]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=lambda: "cursor-eventlog",
    )
    return runtime, store


@pytest.mark.asyncio
async def test_runtime_truncation_does_not_append_special_eventlog_facts() -> None:
    """截断只改写普通工具 outcome，不追加 Host 专属工具事实。"""

    runtime, store = _runtime()

    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.truncation is not None
    assert outcome.result.truncation.cursor == "cursor-eventlog"

    events = await store.list_events("run_1", after=None)
    assert events == ()


@pytest.mark.asyncio
async def test_fetch_more_returns_ordinary_completed_outcome_without_special_facts() -> None:
    """framework ``fetch_more`` 返回普通 completed outcome，不追加专属事实。"""

    runtime, store = _runtime()
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    fetch_outcome = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
            limit=1,
        )
    )

    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    assert fetch_outcome.result.value == [3]
    assert fetch_outcome.result.truncation is not None
    events = await store.list_events("run_1", after=None)
    assert events == ()


@pytest.mark.asyncio
async def test_denied_fetch_more_returns_failed_outcome_without_special_facts() -> None:
    """scope token 错误时返回普通 failed outcome，不追加专属事实。"""

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
    assert events == ()


@pytest.mark.asyncio
async def test_cross_run_fetch_more_returns_failure_without_polluting_claimed_run() -> None:
    """跨 Run framework ``fetch_more`` 返回失败且不写伪造事实。"""

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
    assert owner_events == ()
    assert claimed_events == ()


@pytest.mark.asyncio
async def test_expired_cursor_returns_failure_without_special_fact() -> None:
    """过期 cursor 经 framework ``fetch_more`` 返回普通失败 outcome。"""

    clock = _Clock()
    store = InMemoryRunEventStore()
    runtime = HostToolRuntime(
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
    assert events == ()


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
