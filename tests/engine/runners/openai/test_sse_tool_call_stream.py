"""SSE tool_call 流式聚合测试。"""

from __future__ import annotations

import logging

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
    RunnerProtocolErrorData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
)
from dayu.engine.runners.openai.tool_call_aggregator import ToolCallAggregator

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_tool_call_aggregated_across_chunks() -> None:
    """``name`` / ``arguments`` 在多个 chunk 上累加；最终聚合为一次完成事件。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-1","type":"function",'
            b'"function":{"name":"search"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"function":{"arguments":"{\\"q\\":"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"function":{"arguments":"\\"hello\\"}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)

    deltas = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALL_DELTA
    ]
    assert len(deltas) == 3
    for d in deltas:
        assert isinstance(d.data, RunnerToolCallDeltaData)
        assert d.data.tool_call_index == 0

    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert len(data.tool_calls) == 1
    tc = data.tool_calls[0]
    assert tc.tool_call_id == "call-1"
    assert tc.name == "search"
    assert tc.arguments == {"q": "hello"}
    assert tc.index_in_iteration == 0

    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    # finish_reason 为 tool_calls
    from dayu.engine.contracts.runner_events import RunnerDoneData

    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.TOOL_CALLS


@pytest.mark.asyncio
async def test_tool_call_position_ignores_non_dict_elements() -> None:
    """无 index 的 tool_call 位置只按有效对象计数。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[null,{"id":"call-1","type":"function",'
            b'"function":{"name":"search","arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)

    deltas = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALL_DELTA
    ]
    assert len(deltas) == 1
    assert isinstance(deltas[0].data, RunnerToolCallDeltaData)
    assert deltas[0].data.tool_call_index == -1
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert data.tool_calls[0].index_in_iteration == 0


@pytest.mark.asyncio
async def test_tool_calls_with_stop_finish_reason_fail_closed() -> None:
    """流式 tool calls 与非 tool finish reason 冲突时必须失败收口。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-1","type":"function",'
            b'"function":{"name":"search","arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)

    assert [event.type for event in events] == [
        RunnerEventType.RUNNER_TOOL_CALL_DELTA,
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[-2].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_tool_calls_finish_reason_mismatch"
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_bool_index_tool_calls_fail_closed() -> None:
    """显式 bool index 必须 fatal，不能按 id fallback 聚合。

    :returns: 无返回值。
    :raises AssertionError: 聚合顺序或参数归属错误时由 pytest 抛出。
    """

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":true,"id":"call-a","type":"function",'
            b'"function":{"name":"lookup","arguments":"{\\"ticker\\":"}},'
            b'{"index":false,"id":"call-b","type":"function",'
            b'"function":{"name":"price","arguments":"{\\"symbol\\":"}}'
            b']}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":true,"id":"call-a",'
            b'"function":{"arguments":"\\"AAPL\\"}"}},'
            b'{"index":false,"id":"call-b",'
            b'"function":{"arguments":"\\"MSFT\\"}"}}'
            b']}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    events = await parse_sse(chunks)

    assert RunnerEventType.RUNNER_TOOL_CALL_DELTA not in {
        event.type for event in events
    }
    assert RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED not in {
        event.type for event in events
    }
    errors = [
        event.data
        for event in events
        if event.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    ]
    assert len(errors) == 4
    assert all(isinstance(error, RunnerProtocolErrorData) for error in errors)
    assert all(
        error.error_code == "tool_call_invalid_index"
        for error in errors
        if isinstance(error, RunnerProtocolErrorData)
    )
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_unowned_tool_call_delta_is_not_emitted_as_index_zero(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """无法归属的 tool call delta 不得回退成 index=0。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"function":{"arguments":"{\\"leaked\\":"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    caplog.set_level(
        logging.WARNING,
        logger="dayu.engine.runners.openai.sse_parser",
    )

    events = await parse_sse(chunks)

    deltas = [
        event for event in events
        if event.type is RunnerEventType.RUNNER_TOOL_CALL_DELTA
    ]
    assert deltas == []
    assert any(
        "tool_call_delta_unowned" in record.getMessage()
        for record in caplog.records
    )


def test_aggregator_rejects_bool_index_without_id_fallback() -> None:
    """aggregator 直接收到 bool index 时必须 fatal 且不创建 partial。

    :returns: 无返回值。
    :raises AssertionError: bool index 被误当作 int 路由时由 pytest 抛出。
    """

    aggregator = ToolCallAggregator(provider_request_id=None)
    delta: dict[str, JsonValue] = {
        "index": True,
        "id": "call-bool",
        "function": {"name": "lookup", "arguments": "{}"},
    }

    resolved_index = aggregator.feed(delta)

    assert resolved_index is None
    result = aggregator.finalize()
    assert result.tool_calls == ()
    assert len(result.fatal_errors) == 1
    assert result.fatal_errors[0].error_code == "tool_call_invalid_index"
