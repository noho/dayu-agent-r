"""SSE / 非流式协议错误归一为 :class:`RunnerProtocolErrorData` 测试。"""

from __future__ import annotations

import json

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
    RunnerProtocolErrorData,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)

from tests.engine.runners.openai._sse_helpers import (
    make_no_thought_hook,
    parse_sse,
)


@pytest.mark.asyncio
async def test_sse_invalid_json_emits_protocol_error() -> None:
    """SSE ``data:`` 行非合法 JSON → 立即 Done(ERROR)，不再处理后续 chunk。"""

    chunks = [
        b"data: not-a-json\n\n",
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "sse_invalid_json"
    assert isinstance(events[1].data, RunnerDoneData)
    assert events[1].data.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_tool_call_missing_id_emits_missing_id_error() -> None:
    """tool_call 始终缺失 ``id`` → fatal 错误 + Done(ERROR)，无 ToolCallsCompleted。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"function":{"name":"f","arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    codes = {
        e.data.error_code
        for e in events
        if isinstance(e.data, RunnerProtocolErrorData)
    }
    assert "tool_call_missing_id" in codes
    # 不得产出成功的 ToolCallsCompleted
    assert not any(
        e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED for e in events
    )
    # Done 终态必须是 ERROR
    done_events = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done_events) == 1
    assert isinstance(done_events[0].data, RunnerDoneData)
    assert done_events[0].data.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_tool_call_arguments_not_object_error() -> None:
    """tool_call 参数非对象 → fatal 错误 + Done(ERROR)，无 ToolCallsCompleted。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"c1","type":"function",'
            b'"function":{"name":"f","arguments":"[1,2,3]"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    codes = {
        e.data.error_code
        for e in events
        if isinstance(e.data, RunnerProtocolErrorData)
    }
    assert "tool_call_arguments_not_object" in codes
    assert not any(
        e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED for e in events
    )
    done_events = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done_events) == 1
    assert isinstance(done_events[0].data, RunnerDoneData)
    assert done_events[0].data.finish_reason is FinishReason.ERROR


def test_non_stream_invalid_json_error_then_done() -> None:
    """非流式响应非 JSON → ``non_stream_invalid_json`` + Done(ERROR)。"""

    events = list(
        parse_non_stream_response(b"not-json", hook=make_no_thought_hook())
    )
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "non_stream_invalid_json"
    assert isinstance(events[1].data, RunnerDoneData)
    assert events[1].data.finish_reason is FinishReason.ERROR


def test_non_stream_payload_not_object_error() -> None:
    """非流式响应顶层不是 object → ``non_stream_payload_not_object``。"""

    payload = json.dumps([1, 2, 3]).encode("utf-8")
    events = list(
        parse_non_stream_response(payload, hook=make_no_thought_hook())
    )
    assert events[0].type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "non_stream_payload_not_object"


def test_non_stream_missing_choices_error() -> None:
    """非流式响应缺 ``choices`` → ``non_stream_missing_choices``。"""

    payload = json.dumps({}).encode("utf-8")
    events = list(
        parse_non_stream_response(payload, hook=make_no_thought_hook())
    )
    assert events[0].type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "non_stream_missing_choices"
