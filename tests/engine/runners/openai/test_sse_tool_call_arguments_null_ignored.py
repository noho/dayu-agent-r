"""``function.arguments == null`` 安全忽略测试（OLD 兼容点）。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerEventType,
    RunnerToolCallsCompletedData,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_arguments_null_is_ignored_not_error() -> None:
    """``function.arguments`` 为 ``null`` 应被忽略，不产生协议错误。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-1","type":"function",'
            b'"function":{"name":"do","arguments":null}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"function":{"arguments":"{\\"x\\":2}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    protocol_errors = [
        e for e in events
        if e.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    ]
    assert protocol_errors == []
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert data.tool_calls[0].arguments == {"x": 2}
