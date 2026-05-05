"""SSE 非法 UTF-8 chunk 测试。

非法 UTF-8 chunk 应触发 :class:`RunnerProtocolErrorData` (
``error_code='invalid_utf8'``) 后立即以
:class:`RunnerDoneData(FinishReason.ERROR)` 收口；不再继续读流。
"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEventType,
    RunnerProtocolErrorData,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_invalid_utf8_emits_protocol_error_then_done_error() -> None:
    """非法 UTF-8 → 协议错误 + Done(ERROR)，且后续 chunk 不再被消费。"""

    chunks = [
        b"data: {",
        b"\xff\xfe\xfd",  # 非法 UTF-8 序列
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    err = events[0].data
    assert isinstance(err, RunnerProtocolErrorData)
    assert err.error_code == "invalid_utf8"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
