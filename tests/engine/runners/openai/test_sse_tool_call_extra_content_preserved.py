"""SSE tool_call ``extra_content`` provider state 透传测试。

覆盖 Gemini ``thought_signature`` 在 SSE 流中的传递路径：parser 需要把
``extra_content.google.thought_signature`` 解析为
:class:`GeminiToolCallState` 并注入 :class:`ToolCallRequest.provider_state`。
"""

from __future__ import annotations

import pytest

from dayu.contracts.tool_call import GeminiToolCallState
from dayu.engine.contracts.runner_events import (
    RunnerEventType,
    RunnerToolCallsCompletedData,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_gemini_thought_signature_preserved_to_provider_state() -> None:
    """``extra_content.google.thought_signature`` → ``provider_state``。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-x","type":"function",'
            b'"function":{"name":"f","arguments":"{}"},'
            b'"extra_content":{"google":'
            b'{"thought_signature":"sig-123"}}}]}}]}\n\n'
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
    state = data.tool_calls[0].provider_state
    assert isinstance(state, GeminiToolCallState)
    assert state.thought_signature == "sig-123"
