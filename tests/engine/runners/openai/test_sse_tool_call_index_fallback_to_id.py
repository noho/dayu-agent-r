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
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert len(data.tool_calls) == 1
    tc = data.tool_calls[0]
    assert tc.tool_call_id == "call-z"
    assert tc.name == "do"
    assert tc.arguments == {"k": 1}
