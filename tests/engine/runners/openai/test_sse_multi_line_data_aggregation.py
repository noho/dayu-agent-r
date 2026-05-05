"""SSE 多行 ``data:`` 聚合测试（OLD 兼容点）。

同一事件的 JSON 可能跨多个 ``data:`` 行；parser 必须用 ``\n`` 拼接后
作为单一 JSON 解析。
"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerContentDeltaData,
    RunnerEventType,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_multi_line_data_aggregated_as_single_json() -> None:
    """多行 ``data:`` 应聚合为单一 JSON 对象。"""

    # JSON 写成两行：第一行 `{` 第二行 `"choices": ...}`
    payload_line_1 = b'data: {\n'
    payload_line_2 = b'data: "choices":[{"delta":{"content":"hi"}}]}\n\n'
    chunks = [
        payload_line_1 + payload_line_2,
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    deltas = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_DELTA
    ]
    assert len(deltas) == 1
    data = deltas[0].data
    assert isinstance(data, RunnerContentDeltaData)
    assert data.delta == "hi"
