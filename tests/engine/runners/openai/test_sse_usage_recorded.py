"""SSE ``usage`` 字段归一为 :class:`RunnerUsageRecordedData` 测试。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerEventType,
    RunnerUsageRecordedData,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_usage_recorded_in_final_chunk() -> None:
    """末尾 chunk 携带 ``usage`` 时应产生一次 :class:`RunnerUsageRecordedData`。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n',
        (
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}],'
            b'"usage":{"prompt_tokens":12,"completion_tokens":3,'
            b'"total_tokens":15}}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    usages = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_USAGE_RECORDED
    ]
    assert len(usages) == 1
    data = usages[0].data
    assert isinstance(data, RunnerUsageRecordedData)
    assert data.prompt_tokens == 12
    assert data.completion_tokens == 3
    assert data.total_tokens == 15
