"""P8 ToolRuntime owner scope 与 P8.5 generic tool calling 边界测试。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import pytest

from dayu.contracts import JsonValue, ToolTruncateSpec
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
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
)
from dayu.host._framework_tools import FRAMEWORK_FETCH_MORE_NAME
from dayu.host._internal_contracts import AttemptState, FencingToken
from dayu.host._tool_result_truncation import (
    ToolResultTruncationHint,
    extract_truncation_hint,
)
from dayu.host._tool_runtime import (
    HostToolRuntime,
    PlainRunEventAppender,
    ToolRuntimeToolExecutor,
    ToolRuntimeOwnerScope,
    active_tool_runtime_appender,
)
from dayu.host.contracts import RunEvent, RunEventDraft


def _required_truncation(value: JsonValue) -> ToolResultTruncationHint:
    """提取测试期望存在的截断 hint。

    :param value: 工具成功结果值。
    :returns: 截断 hint。
    :raises AssertionError: 截断 hint 不存在时抛出。
    """

    truncation = extract_truncation_hint(value)
    assert truncation is not None
    return truncation


def _content_value(value: JsonValue) -> JsonValue:
    """读取非 object 工具值被截断后的 ``content`` 包装。

    :param value: 工具成功结果值。
    :returns: ``content`` 字段或原值。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, Mapping) and "content" in value:
        return value["content"]
    return value


@dataclass(frozen=True, slots=True)
class _Token:
    """测试用永不取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否取消。

        :returns: 始终为 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


@dataclass(slots=True)
class _Executor:
    """返回固定成功结果的 fake executor。

    :param value: 工具返回值。
    :param calls: 调用次数。
    """

    value: JsonValue
    calls: int = 0

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """执行 fake 工具。

        :param request: 工具执行请求。
        :returns: 成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        self.calls += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=self.value,
                meta=None,
            )
        )


@dataclass(slots=True)
class _Tokens:
    """确定性 cursor 原文生成器。"""

    next_index: int = 0

    def __call__(self) -> str:
        """生成下一个 cursor。

        :returns: cursor 原文。
        :raises Exception: 不主动抛出异常。
        """

        self.next_index += 1
        return f"cursor-{self.next_index}"


@dataclass(slots=True)
class _ManualClock:
    """测试用 monotonic clock。"""

    value: float = 100.0

    def __call__(self) -> float:
        """返回当前 monotonic 时间。

        :returns: 当前测试时间。
        :raises Exception: 不主动抛出异常。
        """

        return self.value


@dataclass(slots=True)
class _FencingAppender:
    """在 owner 校验阶段抛 fencing 的 appender。"""

    verify_calls: int = 0
    append_calls: int = 0

    async def verify_active_owner(self, *, run_id: str) -> None:
        """模拟 generic tool call 进入业务执行前 owner 已失效。

        :param run_id: Run id。
        :returns: 无返回值。
        :raises AttemptFencingError: 始终抛出 owner mismatch。
        """

        self.verify_calls += 1
        raise AttemptFencingError(
            attempt_id="attempt-fenced",
            run_id=run_id,
            reason=AttemptFencingReason.OWNER_MISMATCH,
            current_state=AttemptState.RUNNING,
            owner_id="other-owner",
            fencing_token=FencingToken(value=9),
        )

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """记录 append 调用并拒绝写入。

        :param draft: RunEvent 草稿。
        :returns: 永不返回。
        :raises AssertionError: 始终抛出，generic fencing 不应进入 append。
        """

        del draft
        self.append_calls += 1
        raise AssertionError("fenced generic tool call must not append")


def _spec() -> ToolTruncateSpec:
    """构造测试用截断声明。

    :returns: 截断声明。
    :raises Exception: 不主动抛出异常。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy="list_items",
        limits={"max_items": 1},
        target_field=None,
        field_path=None,
        ttl_seconds=30,
    )


def _request(
    *,
    tool_name: str = "demo",
    arguments: dict[str, JsonValue] | None = None,
    tool_call_id: str = "tc-1",
) -> ToolExecutionRequest:
    """构造工具执行请求。

    :param tool_name: 工具名。
    :param arguments: 工具参数。
    :param tool_call_id: 工具调用 id。
    :returns: 工具执行请求。
    :raises Exception: 不主动抛出异常。
    """

    return ToolExecutionRequest(
        call=ToolCallRequest(
            tool_call_id=tool_call_id,
            name=tool_name,
            arguments=arguments or {},
            index_in_iteration=0,
            provider_state=None,
        ),
        context=ToolExecutionContext(
            run_id="run-1",
            session_id="session-1",
            iteration_id="iter-1",
            tool_call_id=tool_call_id,
            index_in_iteration=0,
            timeout_seconds=None,
            cancellation_token=_Token(),
            correlation_id=None,
        ),
    )


@pytest.mark.asyncio
async def test_owner_scope_installs_and_restores_appender() -> None:
    """ToolRuntimeOwnerScope 仍按 ContextVar 安装并恢复 appender。"""

    store = InMemoryRunEventStore()
    appender = PlainRunEventAppender(event_store=store)

    assert active_tool_runtime_appender() is None
    async with ToolRuntimeOwnerScope(appender):
        assert active_tool_runtime_appender() is appender
    assert active_tool_runtime_appender() is None


@pytest.mark.asyncio
async def test_durable_runtime_requires_owner_scope() -> None:
    """durable runtime 缺少 owner scope 时仍 fail fast。"""

    runtime = HostToolRuntime(
        is_durable=True,
        executor=_Executor(value=[1, 2, 3]),
        event_store=InMemoryRunEventStore(),
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )

    with pytest.raises(RuntimeError):
        runtime._resolve_appender()


@pytest.mark.asyncio
async def test_durable_executor_rejects_without_scope_before_business_call() -> None:
    """durable 真实 executor 入口无 owner scope 时拒绝且不调用业务工具。"""

    executor = _Executor(value=[1, 2, 3])
    runtime = HostToolRuntime(
        is_durable=True,
        executor=executor,
        event_store=InMemoryRunEventStore(),
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )
    tool_executor = ToolRuntimeToolExecutor(runtime=runtime)

    with pytest.raises(RuntimeError, match="ToolRuntimeOwnerScope"):
        await tool_executor.execute(_request())

    assert executor.calls == 0


@pytest.mark.asyncio
async def test_durable_executor_with_scope_allows_business_truncation() -> None:
    """durable 真实 executor 入口有 owner scope 时执行业务工具并签发 cursor。"""

    store = InMemoryRunEventStore()
    executor = _Executor(value=[1, 2, 3])
    runtime = HostToolRuntime(
        is_durable=True,
        executor=executor,
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )
    tool_executor = ToolRuntimeToolExecutor(runtime=runtime)

    async with ToolRuntimeOwnerScope(PlainRunEventAppender(event_store=store)):
        outcome = await tool_executor.execute(_request())

    assert executor.calls == 1
    assert isinstance(outcome, ToolCompletedOutcome)
    assert extract_truncation_hint(outcome.result.value) is not None


@pytest.mark.asyncio
async def test_durable_generic_tool_call_fencing_happens_before_business_call() -> None:
    """generic tool call 被 owner fencing 拒绝时不调用业务工具、不写事实。"""

    store = InMemoryRunEventStore()
    executor = _Executor(value=[1, 2, 3])
    runtime = HostToolRuntime(
        is_durable=True,
        executor=executor,
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )
    tool_executor = ToolRuntimeToolExecutor(runtime=runtime)
    appender = _FencingAppender()

    async with ToolRuntimeOwnerScope(appender):
        with pytest.raises(AttemptFencingError) as excinfo:
            await tool_executor.execute(_request())

    assert excinfo.value.reason is AttemptFencingReason.OWNER_MISMATCH
    assert executor.calls == 0
    assert appender.verify_calls == 1
    assert appender.append_calls == 0
    assert await store.list_events("run-1", after=None) == ()


@pytest.mark.asyncio
async def test_durable_fetch_more_rejects_without_scope_before_cursor_consume() -> None:
    """durable ``fetch_more`` 无 owner scope 时拒绝且不消费已有 cursor。"""

    store = InMemoryRunEventStore()
    runtime = HostToolRuntime(
        is_durable=True,
        executor=_Executor(value=[1, 2, 3]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )
    tool_executor = ToolRuntimeToolExecutor(runtime=runtime)

    async with ToolRuntimeOwnerScope(PlainRunEventAppender(event_store=store)):
        first = await tool_executor.execute(_request())

    assert isinstance(first, ToolCompletedOutcome)
    truncation = _required_truncation(first.result.value)
    fetch_request = _request(
        tool_name=FRAMEWORK_FETCH_MORE_NAME,
        arguments={
            "cursor": truncation.cursor,
            "scope_token": truncation.scope_token,
        },
        tool_call_id="read-1",
    )

    with pytest.raises(RuntimeError, match="ToolRuntimeOwnerScope"):
        await tool_executor.execute(fetch_request)

    async with ToolRuntimeOwnerScope(PlainRunEventAppender(event_store=store)):
        read = await tool_executor.execute(fetch_request)

    assert isinstance(read, ToolCompletedOutcome)
    assert _content_value(read.result.value) == [2]


@pytest.mark.asyncio
async def test_truncation_and_fetch_more_do_not_append_special_facts() -> None:
    """截断与补读均返回普通 outcome，不追加 Host 专属工具事实。"""

    store = InMemoryRunEventStore()
    runtime = HostToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )

    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    assert _content_value(outcome.result.value) == [1]
    truncation = _required_truncation(outcome.result.value)

    read = await runtime.execute_tool_call(
        _request(
            tool_name=FRAMEWORK_FETCH_MORE_NAME,
            arguments={
                "cursor": truncation.cursor,
                "scope_token": truncation.scope_token,
            },
            tool_call_id="read-1",
        )
    )

    assert isinstance(read, ToolCompletedOutcome)
    assert _content_value(read.result.value) == [2]
    assert await store.list_events("run-1", after=None) == ()


@pytest.mark.asyncio
async def test_wrong_scope_returns_plain_failed_outcome() -> None:
    """scope token 错误时返回普通 failed outcome，不写专属事实。"""

    store = InMemoryRunEventStore()
    runtime = HostToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=lambda: 100.0,
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = _required_truncation(outcome.result.value)

    failed = await runtime.execute_tool_call(
        _request(
            tool_name=FRAMEWORK_FETCH_MORE_NAME,
            arguments={
                "cursor": truncation.cursor,
                "scope_token": "wrong",
            },
            tool_call_id="read-1",
        )
    )

    assert isinstance(failed, ToolFailedOutcome)
    assert failed.result.error == "cursor_scope_mismatch"
    assert await store.list_events("run-1", after=None) == ()


@pytest.mark.asyncio
async def test_expired_fetch_more_returns_plain_failed_outcome() -> None:
    """cursor 过期时 ``fetch_more`` 返回普通 failed outcome，不写专属事实。"""

    store = InMemoryRunEventStore()
    clock = _ManualClock()
    runtime = HostToolRuntime(
        is_durable=False,
        executor=_Executor(value=[1, 2, 3]),
        event_store=store,
        truncate_specs={"demo": _spec()},
        token_generator=_Tokens(),
        clock=clock,
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = _required_truncation(outcome.result.value)

    clock.value = 200.0
    failed = await runtime.execute_tool_call(
        _request(
            tool_name=FRAMEWORK_FETCH_MORE_NAME,
            arguments={
                "cursor": truncation.cursor,
                "scope_token": truncation.scope_token,
            },
            tool_call_id="read-1",
        )
    )

    assert isinstance(failed, ToolFailedOutcome)
    assert failed.result.error == "cursor_expired"
    assert await store.list_events("run-1", after=None) == ()
