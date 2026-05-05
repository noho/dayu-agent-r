"""SSE 尾部无换行残留测试（OLD 兼容点）。"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerContentDeltaData,
    RunnerEventType,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_trailing_data_without_final_newline() -> None:
    """流末 ``data:`` 行无 ``\\n\\n`` 时仍应正常落库。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n',
        # 最后一行无双换行，仅以单换行结尾
        b'data: {"choices":[{"finish_reason":"stop","delta":{"content":"b"}}]}',
    ]
    events = await parse_sse(chunks)
    deltas = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_DELTA
    ]
    assert len(deltas) == 2
    assert isinstance(deltas[0].data, RunnerContentDeltaData)
    assert isinstance(deltas[1].data, RunnerContentDeltaData)
    assert deltas[0].data.delta == "a"
    assert deltas[1].data.delta == "b"
    # 仍然 emit Done
    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
