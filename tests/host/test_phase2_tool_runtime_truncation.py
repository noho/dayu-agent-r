"""Host P2 ToolRuntime 截断与补读语义测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pytest

from dayu.contracts import JsonValue, ToolTruncateSpec
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    RunEventType,
    ToolFetchMoreHandleRequest,
    ToolFetchMoreHandleSucceededResult,
    ToolFetchMoreRequest,
    ToolFetchMoreSucceededResult,
    ToolResultTruncatedData,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._tool_runtime import InMemoryToolRuntime


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
    """返回固定成功结果的 fake executor。"""

    value: JsonValue

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回固定工具结果。

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
        """返回当前时间。

        :returns: 当前 monotonic 时间。
        :raises Exception: 不主动抛出异常。
        """

        return self.now


@dataclass(slots=True)
class _Tokens:
    """确定性 cursor 原文生成器。"""

    next_index: int = 0

    def __call__(self) -> str:
        """返回下一个 cursor。

        :returns: cursor 原文。
        :raises Exception: 不主动抛出异常。
        """

        self.next_index += 1
        return f"cursor-{self.next_index}"


def _spec(
    strategy: str,
    limit_key: str,
    limit: int,
    *,
    target_field: str | None = None,
    field_path: tuple[str, ...] | None = None,
    ttl_seconds: int | None = 30,
) -> ToolTruncateSpec:
    """构造截断声明。

    :param strategy: 策略。
    :param limit_key: limit key。
    :param limit: limit 值。
    :param target_field: 顶层目标字段。
    :param field_path: 嵌套目标路径。
    :param ttl_seconds: TTL 秒数。
    :returns: ToolTruncateSpec。
    :raises Exception: 不主动抛出异常。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=strategy,
        limits={limit_key: limit},
        target_field=target_field,
        field_path=field_path,
        ttl_seconds=ttl_seconds,
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
            arguments={"q": "abc"},
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


async def _runtime(
    *,
    value: JsonValue,
    spec: ToolTruncateSpec | None,
    clock: _Clock | None = None,
    tokens: _Tokens | None = None,
) -> tuple[InMemoryToolRuntime, InMemoryRunEventStore]:
    """构造测试 runtime。

    :param value: 工具返回值。
    :param spec: 截断声明。
    :param clock: 可选 clock。
    :param tokens: 可选 token 生成器。
    :returns: runtime 与 event store。
    :raises Exception: 不主动抛出异常。
    """

    store = InMemoryRunEventStore()
    specs: dict[str, ToolTruncateSpec] = {}
    if spec is not None:
        specs["demo"] = spec
    return (
        InMemoryToolRuntime(
            executor=_Executor(value=value),
            event_store=store,
            truncate_specs=specs,
            clock=clock if clock is not None else _Clock(),
            token_generator=tokens if tokens is not None else _Tokens(),
        ),
        store,
    )


@pytest.mark.asyncio
async def test_truncates_text_chars_and_issues_execute_time_cursor() -> None:
    """text_chars 截断在 execute 返回前生成 cursor 与 canonical facts。"""

    runtime, store = await _runtime(
        value="abcdef",
        spec=_spec("text_chars", "max_chars", 3),
    )

    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == "abc"
    assert outcome.result.truncation is not None
    assert outcome.result.truncation.scope_token == ""

    events = await store.list_events("run_1", after=None)
    assert [event.type for event in events] == [
        RunEventType.TOOL_RESULT_TRUNCATED,
        RunEventType.TOOL_CURSOR_ISSUED,
    ]
    truncated = events[0].data
    assert isinstance(truncated, ToolResultTruncatedData)
    assert truncated.cursor_fingerprint
    assert truncated.total_estimate == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "spec", "expected"),
    [
        ("a\nb\nc\n", _spec("text_lines", "max_lines", 2), "a\nb\n"),
        ([1, 2, 3], _spec("list_items", "max_items", 2), [1, 2]),
        (
            cast(JsonValue, b"abcd"),
            _spec("binary_bytes", "max_bytes", 2),
            "YWI=",
        ),
    ],
)
async def test_truncation_strategies(
    value: JsonValue,
    spec: ToolTruncateSpec,
    expected: JsonValue,
) -> None:
    """验证 P2 支持的四类通用截断策略。"""

    runtime, _store = await _runtime(value=value, spec=spec)

    outcome = await runtime.execute_tool_call(_request())

    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == expected


@pytest.mark.asyncio
async def test_binary_bytes_fetch_more_returns_base64_json_string() -> None:
    """binary_bytes 补读结果保持 base64 JsonValue 字符串契约。"""

    runtime, store = await _runtime(
        value=cast(JsonValue, b"abcdef"),
        spec=_spec("binary_bytes", "max_bytes", 2),
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == "YWI="
    truncated = cast(
        ToolResultTruncatedData,
        (await store.list_events("run_1", after=None))[0].data,
    )
    handle = await runtime.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor_fingerprint=truncated.cursor_fingerprint,
        )
    )
    assert isinstance(handle, ToolFetchMoreHandleSucceededResult)

    result = await runtime.fetch_more(
        ToolFetchMoreRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor=handle.handle.cursor,
            scope_token=handle.handle.scope_token,
            limit=None,
        )
    )

    assert isinstance(result, ToolFetchMoreSucceededResult)
    assert result.value == "Y2Q="


@pytest.mark.asyncio
async def test_no_spec_disabled_unknown_or_illegal_limit_do_not_truncate() -> None:
    """无 spec、未启用、未知策略和非法 limit 均不截断。"""

    cases = (
        None,
        ToolTruncateSpec(
            enabled=False,
            strategy="text_chars",
            limits={"max_chars": 1},
            target_field=None,
            field_path=None,
            ttl_seconds=None,
        ),
        _spec("unknown", "max_chars", 1),
        _spec("text_chars", "max_chars", 0),
    )
    for spec in cases:
        runtime, store = await _runtime(value="abcdef", spec=spec)
        outcome = await runtime.execute_tool_call(_request())
        assert isinstance(outcome, ToolCompletedOutcome)
        assert outcome.result.value == "abcdef"
        assert await store.list_events("run_1", after=None) == ()


@pytest.mark.asyncio
async def test_wrapper_requires_explicit_target() -> None:
    """wrapper dict 没有显式 target 时不走 OLD 启发式。"""

    value: JsonValue = {"short": "x", "long": "abcdef"}
    runtime_without_target, store_without_target = await _runtime(
        value=value,
        spec=_spec("text_chars", "max_chars", 3),
    )
    outcome_without_target = await runtime_without_target.execute_tool_call(
        _request()
    )
    assert isinstance(outcome_without_target, ToolCompletedOutcome)
    assert outcome_without_target.result.value == value
    assert await store_without_target.list_events("run_1", after=None) == ()

    runtime_with_target, _store_with_target = await _runtime(
        value=value,
        spec=_spec("text_chars", "max_chars", 3, target_field="long"),
    )
    outcome_with_target = await runtime_with_target.execute_tool_call(_request())
    assert isinstance(outcome_with_target, ToolCompletedOutcome)
    assert outcome_with_target.result.value == {"short": "x", "long": "abc"}


@pytest.mark.asyncio
async def test_fetch_more_single_use_limit_clamp_and_next_cursor() -> None:
    """成功补读后旧 cursor 失效，limit clamp，并在有剩余时签发新 cursor。"""

    runtime, store = await _runtime(
        value=[1, 2, 3, 4, 5],
        spec=_spec("list_items", "max_items", 2),
    )
    await runtime.execute_tool_call(_request())
    truncated = cast(
        ToolResultTruncatedData,
        (await store.list_events("run_1", after=None))[0].data,
    )
    handle_result = await runtime.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor_fingerprint=truncated.cursor_fingerprint,
        )
    )
    assert isinstance(handle_result, ToolFetchMoreHandleSucceededResult)

    first = await runtime.fetch_more(
        ToolFetchMoreRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor=handle_result.handle.cursor,
            scope_token=handle_result.handle.scope_token,
            limit=99,
        )
    )
    assert isinstance(first, ToolFetchMoreSucceededResult)
    assert first.value == [3, 4]
    assert first.truncation is not None

    reused = await runtime.fetch_more(
        ToolFetchMoreRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor=handle_result.handle.cursor,
            scope_token=handle_result.handle.scope_token,
            limit=None,
        )
    )
    assert not isinstance(reused, ToolFetchMoreSucceededResult)
    assert reused.error_code == "cursor_not_found"

    next_handle = await runtime.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor_fingerprint=first.truncation.fingerprint,
        )
    )
    assert isinstance(next_handle, ToolFetchMoreHandleSucceededResult)
    second = await runtime.fetch_more(
        ToolFetchMoreRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor=next_handle.handle.cursor,
            scope_token=next_handle.handle.scope_token,
            limit=None,
        )
    )
    assert isinstance(second, ToolFetchMoreSucceededResult)
    assert second.value == [5]
    assert second.truncation is None


@pytest.mark.asyncio
async def test_ttl_expired_and_opportunistic_cleanup() -> None:
    """过期 cursor 被拒绝，后续创建 cursor 时清理无人访问的过期 payload。"""

    clock = _Clock()
    runtime, store = await _runtime(
        value="abcdef",
        spec=_spec("text_chars", "max_chars", 2, ttl_seconds=5),
        clock=clock,
    )
    await runtime.execute_tool_call(_request())
    first = cast(
        ToolResultTruncatedData,
        (await store.list_events("run_1", after=None))[0].data,
    )
    handle = await runtime.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor_fingerprint=first.cursor_fingerprint,
        )
    )
    assert isinstance(handle, ToolFetchMoreHandleSucceededResult)
    clock.now = 106.0

    expired = await runtime.fetch_more(
        ToolFetchMoreRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor=handle.handle.cursor,
            scope_token=handle.handle.scope_token,
            limit=None,
        )
    )
    assert not isinstance(expired, ToolFetchMoreSucceededResult)
    assert expired.error_code == "cursor_expired"

    await runtime.execute_tool_call(_request(run_id="run_2", tool_call_id="tc_2"))
    stale_handle = await runtime.get_tool_fetch_more_handle(
        ToolFetchMoreHandleRequest(
            session_id="session_1",
            run_id="run_1",
            tool_call_id="tc_1",
            cursor_fingerprint=first.cursor_fingerprint,
        )
    )
    assert not isinstance(stale_handle, ToolFetchMoreHandleSucceededResult)
    assert stale_handle.error_code == "cursor_not_found"
