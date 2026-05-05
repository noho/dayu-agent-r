"""SSE ``choices=[]`` 但 ``usage`` 存在时仍归一为 usage 事件（OLD 兼容点）。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerEventType,
    RunnerUsageRecordedData,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_empty_choices_with_usage_emits_usage_no_protocol_error() -> None:
    """空 choices + usage → 仅产出 usage 事件，无协议错误。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n',
        (
            b'data: {"choices":[],"usage":'
            b'{"prompt_tokens":5,"completion_tokens":1,"total_tokens":6}}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    protocol_errors = [
        e for e in events
        if e.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    ]
    assert protocol_errors == []
    usages = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_USAGE_RECORDED
    ]
    assert len(usages) == 1
    data = usages[0].data
    assert isinstance(data, RunnerUsageRecordedData)
    assert data.prompt_tokens == 5
    assert data.completion_tokens == 1
    assert data.total_tokens == 6
