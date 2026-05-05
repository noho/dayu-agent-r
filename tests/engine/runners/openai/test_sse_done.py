"""SSE Done / 终态收口测试。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_done_emitted_after_done_marker() -> None:
    """``data: [DONE]`` 之后必须 emit 一次 :class:`RunnerDoneData`。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"x"},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    assert isinstance(events[-1].data, RunnerDoneData)
    assert events[-1].data.finish_reason is FinishReason.STOP


@pytest.mark.asyncio
async def test_done_finish_reason_length() -> None:
    """``finish_reason='length'`` 应映射为 :attr:`FinishReason.LENGTH`。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"x"},"finish_reason":"length"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.LENGTH


@pytest.mark.asyncio
async def test_done_finish_reason_content_filter() -> None:
    """``finish_reason='content_filter'`` 映射为 ``CONTENT_FILTER``。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"content":"x"},'
            b'"finish_reason":"content_filter"}]}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.CONTENT_FILTER
