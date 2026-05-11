"""Host P2 ToolRuntime 截断与补读语义测试。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast

import pytest

from dayu.contracts import JsonValue, ToolTruncateSpec
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import (
    ToolCallRequest,
    ToolExecutionContext,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import (
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._framework_tools import FRAMEWORK_FETCH_MORE_NAME
from dayu.host._tool_runtime import HostToolRuntime


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
class _OutcomeExecutor:
    """返回固定 outcome 的 fake executor。"""

    outcome: ToolExecutionOutcome

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回固定工具 outcome。

        :param request: 工具执行请求。
        :returns: 固定 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return self.outcome


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


class _ListLogHandler(logging.Handler):
    """测试用本地日志 handler。"""

    def __init__(self, messages: list[str]) -> None:
        """初始化测试日志 handler。

        :param messages: 用于收集日志文本的列表。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        """记录格式化后的日志文本。

        :param record: logging 记录。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.messages.append(self.format(record))


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


async def _runtime(
    *,
    value: JsonValue,
    spec: ToolTruncateSpec | None,
    clock: _Clock | None = None,
    tokens: _Tokens | None = None,
) -> tuple[HostToolRuntime, InMemoryRunEventStore]:
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
        HostToolRuntime(
            is_durable=False,
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
    assert outcome.result.truncation.cursor
    assert outcome.result.truncation.scope_token
    assert outcome.result.truncation.limit == 3

    assert await store.list_events("run_1", after=None) == ()


@pytest.mark.asyncio
async def test_tool_runtime_debug_logs_tool_call_boundary_without_secret() -> None:
    """ToolRuntime 统一记录工具调用边界，且不泄漏补读凭证明文。"""

    logger = logging.getLogger("dayu.host._tool_runtime")
    messages: list[str] = []
    handler = _ListLogHandler(messages=messages)
    handler.setFormatter(logging.Formatter("%(message)s"))
    original_level = logger.level
    original_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    runtime, _store = await _runtime(
        value="abcdef",
        spec=_spec("text_chars", "max_chars", 3),
    )
    try:
        outcome = await runtime.execute_tool_call(_request())
        assert isinstance(outcome, ToolCompletedOutcome)
        truncation = outcome.result.truncation
        assert truncation is not None
        fetch_request_base = _request(
            tool_call_id="fetch_call_1",
            tool_name=FRAMEWORK_FETCH_MORE_NAME,
        )
        fetch_request = replace(
            fetch_request_base,
            call=replace(
                fetch_request_base.call,
                arguments={
                    "cursor": truncation.cursor,
                    "scope_token": truncation.scope_token,
                    "limit": 1,
                },
            ),
        )

        fetch_outcome = await runtime.execute_tool_call(fetch_request)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate

    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    log_text = "\n".join(messages)
    assert "host.tool_runtime.tool_call_start" in log_text
    assert "host.tool_runtime.tool_call_finished" in log_text
    assert "tool_name=demo" in log_text
    assert f"tool_name={FRAMEWORK_FETCH_MORE_NAME}" in log_text
    assert "truncated=True" in log_text
    assert "framework=True" in log_text
    assert "cursor-1" not in log_text
    assert truncation.scope_token not in log_text


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

    runtime, _store = await _runtime(
        value=cast(JsonValue, b"abcdef"),
        spec=_spec("binary_bytes", "max_bytes", 2),
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == "YWI="
    assert outcome.result.truncation is not None

    fetch_outcome = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=outcome.result.truncation.cursor,
            scope_token=outcome.result.truncation.scope_token,
        )
    )

    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    assert fetch_outcome.result.value == "Y2Q="


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
    outcome_without_target = await runtime_without_target.execute_tool_call(_request())
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
async def test_field_path_mismatch_does_not_return_fake_truncated_wrapper() -> None:
    """field_path 中间路径不匹配时不生成带原始字段的截断结果。"""

    value: JsonValue = {"nested": {"long": "abcdef"}}
    runtime, store = await _runtime(
        value=value,
        spec=_spec(
            "text_chars",
            "max_chars",
            3,
            field_path=("nested", "missing", "long"),
        ),
    )

    outcome = await runtime.execute_tool_call(_request())

    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == value
    assert await store.list_events("run_1", after=None) == ()


@pytest.mark.asyncio
async def test_field_path_has_priority_over_target_field() -> None:
    """field_path 与 target_field 同时存在时优先使用 field_path。"""

    value: JsonValue = {"long": "abcdef", "nested": {"long": "uvwxyz"}}
    runtime, _store = await _runtime(
        value=value,
        spec=_spec(
            "text_chars",
            "max_chars",
            3,
            target_field="long",
            field_path=("nested", "long"),
        ),
    )

    outcome = await runtime.execute_tool_call(_request())

    assert isinstance(outcome, ToolCompletedOutcome)
    assert outcome.result.value == {"long": "abcdef", "nested": {"long": "uvw"}}


@pytest.mark.asyncio
async def test_non_completed_outcome_passthrough_without_cursor() -> None:
    """失败和等待 outcome 原样透传且不创建 cursor。"""

    failed = ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error="tool_failed",
            message="failed",
            hint=None,
            meta=None,
        )
    )
    awaiting = ToolAwaitingOutcome(
        await_spec=ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token="resume-1",
        ),
        snapshot=None,
    )

    for outcome in (failed, awaiting):
        store = InMemoryRunEventStore()
        runtime = HostToolRuntime(
            is_durable=False,
            executor=_OutcomeExecutor(outcome=outcome),
            event_store=store,
            truncate_specs={"demo": _spec("text_chars", "max_chars", 1)},
        )

        actual = await runtime.execute_tool_call(_request())

        assert actual == outcome
        assert await store.list_events("run_1", after=None) == ()


@pytest.mark.asyncio
async def test_fetch_more_single_use_limit_clamp_and_next_cursor() -> None:
    """成功补读后旧 cursor 失效，limit clamp，并在有剩余时签发新 cursor。"""

    runtime, _store = await _runtime(
        value=[1, 2, 3, 4, 5],
        spec=_spec("list_items", "max_items", 2),
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    first = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
            limit=99,
        )
    )
    assert isinstance(first, ToolCompletedOutcome)
    assert first.result.value == [3, 4]
    assert first.result.truncation is not None

    reused = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
            tool_call_id="fetch_call_2",
        )
    )
    assert isinstance(reused, ToolFailedOutcome)
    assert reused.result.error == "cursor_not_found"

    second = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=first.result.truncation.cursor,
            scope_token=first.result.truncation.scope_token,
            tool_call_id="fetch_call_3",
        )
    )
    assert isinstance(second, ToolCompletedOutcome)
    assert second.result.value == [5]
    assert second.result.truncation is None


@pytest.mark.asyncio
async def test_fetch_more_unknown_strategy_fails_without_next_cursor() -> None:
    """未知 strategy 必须 fail closed，不能签发 next cursor 造成补读循环。"""

    runtime, _store = await _runtime(
        value=[1, 2, 3],
        spec=_spec("list_items", "max_items", 1),
    )
    manager = runtime._default_manager
    record = manager._build_cursor_record(
        session_id="session_1",
        run_id="run_1",
        tool_call_id="tc_1",
        tool_name="demo",
        strategy="unknown_strategy",
        unit="items",
        limit=1,
        total=3,
        data=[1, 2, 3],
        offset=1,
        template=None,
        field_path=None,
        arguments={"q": "abc"},
        ttl_seconds=30,
        scope_hash=None,
    )
    manager._commit_cursor(record)

    failed = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=record.cursor,
            scope_token=record.scope_token,
        )
    )

    assert isinstance(failed, ToolFailedOutcome)
    assert failed.result.error == "unsupported_truncate_strategy"
    assert failed.result.meta is None
    reused = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=record.cursor,
            scope_token=record.scope_token,
            tool_call_id="fetch_call_2",
        )
    )
    assert isinstance(reused, ToolFailedOutcome)
    assert reused.result.error == "cursor_not_found"


@pytest.mark.asyncio
async def test_framework_fetch_more_definition_is_cached() -> None:
    """framework ToolDefinition 只构造一次并复用 executor / schema source。"""

    runtime, _store = await _runtime(
        value="abcdef",
        spec=_spec("text_chars", "max_chars", 3),
    )

    first = runtime._framework_tools.fetch_more_definition()
    second = runtime._framework_tools.fetch_more_definition()

    assert first is second
    assert runtime._framework_tools.tool_schemas() == (first.to_tool_schema(),)


@pytest.mark.asyncio
async def test_apply_truncation_and_fetch_more_share_state_lock() -> None:
    """apply_truncation 与 fetch_more 并发读写 cursor registry 时不破坏状态。"""

    runtime, _store = await _runtime(
        value=[1, 2, 3, 4],
        spec=_spec("list_items", "max_items", 2),
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    fetched, applied = await asyncio.gather(
        runtime.execute_tool_call(
            _framework_request(
                cursor_value=truncation.cursor,
                scope_token=truncation.scope_token,
            )
        ),
        asyncio.to_thread(
            runtime._default_manager.apply_truncation,
            request=_request(run_id="run_2", tool_call_id="tc_2"),
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value=[10, 20, 30, 40],
                    truncation=None,
                    meta=None,
                )
            ),
            spec=_spec("list_items", "max_items", 2),
        ),
    )

    assert isinstance(fetched, ToolCompletedOutcome)
    assert isinstance(applied, ToolCompletedOutcome)
    assert applied.result.truncation is not None


@pytest.mark.asyncio
async def test_concurrent_fetch_more_same_cursor_is_single_use() -> None:
    """同一 cursor 并发补读时只有一个成功，另一个返回 cursor_not_found。"""

    runtime, _store = await _runtime(
        value=[1, 2, 3, 4],
        spec=_spec("list_items", "max_items", 2),
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None

    request_a = _framework_request(
        cursor_value=truncation.cursor,
        scope_token=truncation.scope_token,
        tool_call_id="fetch_call_a",
    )
    request_b = _framework_request(
        cursor_value=truncation.cursor,
        scope_token=truncation.scope_token,
        tool_call_id="fetch_call_b",
    )

    first, second = await asyncio.gather(
        runtime.execute_tool_call(request_a),
        runtime.execute_tool_call(request_b),
    )

    results = (first, second)
    successes = [result for result in results if isinstance(result, ToolCompletedOutcome)]
    failures = [result for result in results if isinstance(result, ToolFailedOutcome)]
    assert len(successes) == 1
    assert successes[0].result.value == [3, 4]
    assert len(failures) == 1
    assert failures[0].result.error == "cursor_not_found"


@pytest.mark.asyncio
async def test_ttl_expired_and_opportunistic_cleanup() -> None:
    """过期 cursor 被拒绝，后续创建 cursor 时清理无人访问的过期 payload。"""

    clock = _Clock()
    runtime, _store = await _runtime(
        value="abcdef",
        spec=_spec("text_chars", "max_chars", 2, ttl_seconds=5),
        clock=clock,
    )
    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    truncation = outcome.result.truncation
    assert truncation is not None
    clock.now = 106.0

    expired = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
        )
    )
    assert isinstance(expired, ToolFailedOutcome)
    assert expired.result.error == "cursor_expired"

    await runtime.execute_tool_call(_request(run_id="run_2", tool_call_id="tc_2"))
    stale = await runtime.execute_tool_call(
        _framework_request(
            cursor_value=truncation.cursor,
            scope_token=truncation.scope_token,
            tool_call_id="fetch_call_stale",
        )
    )
    assert isinstance(stale, ToolFailedOutcome)
    assert stale.result.error == "cursor_not_found"


@pytest.mark.asyncio
async def test_truncation_strategy_value_type_mismatch_returns_original() -> None:
    """strategy 与 value 类型不匹配时静默跳过截断, 返回原始值。

    T3: ``strategy="list_items"`` 但 value 为 str 时, ``_apply_truncation``
    fallthrough 返回 ``None``, 不截断。
    """

    runtime, _store = await _runtime(
        value="not-a-list",
        spec=_spec("list_items", "max_items", 2),
    )

    outcome = await runtime.execute_tool_call(_request())
    assert isinstance(outcome, ToolCompletedOutcome)
    # 类型不匹配: 不截断, 返回原始值。
    assert outcome.result.value == "not-a-list"
    assert outcome.result.truncation is None
