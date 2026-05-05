"""SSE byte stream 跨 chunk UTF-8 多字节字符解码测试。

OpenAI / Gemini 兼容服务在长 token 边界上会把 UTF-8 多字节字符拆到
两个 SSE chunk。SSE parser 必须用增量解码器跨 chunk 缓存待续字节，
否则会把合法 UTF-8 误判为 ``invalid_utf8`` 协议错误。
"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerContentDeltaData,
    RunnerEventType,
)

from tests.engine.runners.openai._sse_helpers import parse_sse


@pytest.mark.asyncio
async def test_multibyte_char_split_across_chunks_decodes_cleanly() -> None:
    """``中`` 字（UTF-8 三字节 ``E4 B8 AD``）拆到两个 chunk 仍可解码。"""

    line = (
        b'data: {"choices":[{"delta":{"content":"\xe4\xb8\xad"}}]}\n\n'
    )
    # 在 \xe4 与 \xb8\xad 之间硬切。
    split_index = line.index(b"\xe4") + 1
    chunk_a = line[:split_index]
    chunk_b = line[split_index:]
    chunks = [chunk_a, chunk_b, b"data: [DONE]\n\n"]

    events = await parse_sse(chunks)
    deltas = [
        e.data.delta
        for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_DELTA
        and isinstance(e.data, RunnerContentDeltaData)
    ]
    assert "".join(deltas) == "中"
    # 不应触发 invalid_utf8。
    assert not any(
        getattr(e.data, "error_code", None) == "invalid_utf8"
        for e in events
    )
