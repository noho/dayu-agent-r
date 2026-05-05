"""SSE ``content`` delta 事件测试。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEventType,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_content_delta_emitted_for_each_chunk() -> None:
    """每个 ``delta.content`` 文本应转化为一个 :class:`RunnerContentDeltaData`。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    deltas = [
        e
        for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_DELTA
    ]
    assert len(deltas) == 2
    assert isinstance(deltas[0].data, RunnerContentDeltaData)
    assert deltas[0].data.delta == "Hello"
    assert isinstance(deltas[1].data, RunnerContentDeltaData)
    assert deltas[1].data.delta == " world"

    # 完成事件 + Done
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
    ]
    assert len(completed) == 1
    assert isinstance(completed[0].data, RunnerContentCompletedData)
    assert completed[0].data.content == "Hello world"
    assert completed[0].data.finish_reason is FinishReason.STOP

    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.STOP


@pytest.mark.asyncio
async def test_empty_content_string_does_not_emit_delta() -> None:
    """空字符串 ``content`` 不应产生 delta 事件。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":""}}]}\n\n',
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    deltas = [
        e for e in events if e.type is RunnerEventType.RUNNER_CONTENT_DELTA
    ]
    assert deltas == []
