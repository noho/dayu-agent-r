"""SSE tool_call 流式聚合测试。"""

from __future__ import annotations

import logging

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
)
from dayu.engine.runners.openai._types import _OpenAIToolCallDelta
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
    assert deltas[0].data.tool_call_index == 0
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert data.tool_calls[0].index_in_iteration == 0


@pytest.mark.asyncio
async def test_tool_call_done_finish_reason_prefers_tool_calls_over_stop() -> None:
    """流式响应出现 tool_calls 时，Done 必须以 TOOL_CALLS 收口。"""

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

    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]

    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.TOOL_CALLS


@pytest.mark.asyncio
async def test_bool_index_tool_calls_stay_separate_by_id() -> None:
    """bool index 必须被 parser 拒绝，并按 id fallback 稳定聚合。

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

    deltas: list[RunnerToolCallDeltaData] = []
    for event in events:
        if event.type is RunnerEventType.RUNNER_TOOL_CALL_DELTA:
            assert isinstance(event.data, RunnerToolCallDeltaData)
            deltas.append(event.data)
    assert len(deltas) == 4
    assert [delta.tool_call_index for delta in deltas] == [0, 1, 0, 1]

    completed_events = [
        event for event in events
        if event.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed_events) == 1
    completed = completed_events[0].data
    assert isinstance(completed, RunnerToolCallsCompletedData)
    assert [
        (call.tool_call_id, call.name, call.arguments)
        for call in completed.tool_calls
    ] == [
        ("call-a", "lookup", {"ticker": "AAPL"}),
        ("call-b", "price", {"symbol": "MSFT"}),
    ]


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


def test_aggregator_rejects_bool_index_and_falls_back_to_id() -> None:
    """aggregator 直接收到 bool index 时也必须按非法 index 处理。

    :returns: 无返回值。
    :raises AssertionError: bool index 被误当作 int 路由时由 pytest 抛出。
    """

    aggregator = ToolCallAggregator(provider_request_id=None)
    delta: _OpenAIToolCallDelta = {
        "index": True,
        "id": "call-bool",
        "function": {"name": "lookup", "arguments": "{}"},
    }

    resolved_index = aggregator.feed(delta)

    assert resolved_index == 0
    assert resolved_index is not True
    result = aggregator.finalize()
    assert result.fatal_errors == ()
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_call_id == "call-bool"
    assert result.tool_calls[0].index_in_iteration == 0
