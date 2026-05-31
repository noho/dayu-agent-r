"""SSE tool_call ``index`` 缺失时按 ``id`` 兜底归属测试（OLD 兼容点）。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerEventType,
    RunnerToolCallsCompletedData,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_missing_index_falls_back_to_id() -> None:
    """缺失 ``index`` 但有 ``id`` 时，多个 chunk 应按 ``id`` 归属同一 tool call。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"id":"call-z","type":"function",'
            b'"function":{"name":"do"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"id":"call-z","function":{"arguments":"{\\"k\\":1}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    completed = [e for e in events if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert len(data.tool_calls) == 1
    tc = data.tool_calls[0]
    assert tc.tool_call_id == "call-z"
    assert tc.name == "do"
    assert tc.arguments == {"k": 1}


@pytest.mark.asyncio
async def test_synthetic_index_does_not_collide_with_later_native_index() -> None:
    """缺 index 合成 key 不得与后续 provider 原生 index=0 碰撞。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"id":"call-synthetic","type":"function",'
            b'"function":{"name":"missing","arguments":"{}"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-native","type":"function",'
            b'"function":{"name":"native","arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    events = await parse_sse(chunks)
    completed = [e for e in events if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED]

    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert {(tool_call.tool_call_id, tool_call.name) for tool_call in data.tool_calls} == {
        ("call-synthetic", "missing"),
        ("call-native", "native"),
    }


@pytest.mark.asyncio
async def test_later_native_index_remaps_existing_id_partial() -> None:
    """同一 tool call id 后续补充原生 index 时，旧 partial 必须合并过去。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"id":"call-remap","type":"function",'
            b'"function":{"name":"lookup","arguments":"{\\"k\\""}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-remap",'
            b'"function":{"arguments":":1}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]

    events = await parse_sse(chunks)
    completed = [e for e in events if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED]

    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert len(data.tool_calls) == 1
    tool_call = data.tool_calls[0]
    assert tool_call.tool_call_id == "call-remap"
    assert tool_call.name == "lookup"
    assert tool_call.arguments == {"k": 1}
