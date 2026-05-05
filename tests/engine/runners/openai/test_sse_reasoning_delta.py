"""SSE ``reasoning_content`` delta 事件测试。

覆盖两路输入：

- 原生 ``delta.reasoning_content`` 字段。
- 通过 ``<thought>...</thought>`` XML 标签从 ``content`` 中剥离。
"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerContentDeltaData,
    RunnerEventType,
    RunnerReasoningDeltaData,
)

from tests.engine.runners.openai._sse_helpers import (
    make_thought_hook,
    parse_sse,
)


@pytest.mark.asyncio
async def test_reasoning_delta_native_field() -> None:
    """原生 ``reasoning_content`` 应产生 :class:`RunnerReasoningDeltaData`。"""

    chunks = [
        b'data: {"choices":[{"delta":{"reasoning_content":"thinking..."}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    reasonings = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_REASONING_DELTA
    ]
    assert len(reasonings) == 1
    assert isinstance(reasonings[0].data, RunnerReasoningDeltaData)
    assert reasonings[0].data.delta == "thinking..."


@pytest.mark.asyncio
async def test_reasoning_delta_via_thought_tag_extraction() -> None:
    """``<thought>`` 标签内文本应转为 reasoning delta；标签外为 content delta。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"<thought>plan</thought>ans"}}]}\n\n',
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks, hook=make_thought_hook())
    reasoning_data = [
        e.data for e in events
        if e.type is RunnerEventType.RUNNER_REASONING_DELTA
    ]
    content_data = [
        e.data for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_DELTA
    ]
    assert any(
        isinstance(d, RunnerReasoningDeltaData) and "plan" in d.delta
        for d in reasoning_data
    )
    assert any(
        isinstance(d, RunnerContentDeltaData) and "ans" in d.delta
        for d in content_data
    )
