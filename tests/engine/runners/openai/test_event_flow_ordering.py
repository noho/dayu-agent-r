"""Runner 事件流顺序不变量守卫测试。

按 ``docs/code_review.md`` §6 / §7 与 ``docs/engine/phase1-plan.md``
§6.4：Runner 事件序列必须能被后续 Engine loop 无歧义消费，关键不变量：

1. **唯一终态**：当事件流以 :class:`RunnerDoneData` 收口时，``RUNNER_DONE``
   有且仅出现一次，且必须是序列最后一个事件。
2. **delta → completed → done 单调推进**：

   - ``RUNNER_CONTENT_DELTA`` / ``RUNNER_REASONING_DELTA`` 必须在
     ``RUNNER_CONTENT_COMPLETED`` 之前出现。
   - ``RUNNER_TOOL_CALL_DELTA`` 必须在
     ``RUNNER_TOOL_CALLS_COMPLETED`` 之前出现。
   - 任何 completed / usage / 错误事件之后**不**得再出现 delta。
3. **错误与 Done(ERROR) 配对**：``RUNNER_HTTP_ERROR`` /
   ``PROVIDER_PROTOCOL_ERROR`` 出现时，紧随其后的 ``RUNNER_DONE`` 必须
   ``finish_reason=ERROR``，且不得再出现成功的 completed 事件。
4. **content / tool_calls 完成事件互斥**：单次调用要么走 content
   路径产 ``RUNNER_CONTENT_COMPLETED``，要么走 tool_calls 路径产
   ``RUNNER_TOOL_CALLS_COMPLETED``，两者不应同时存在。

本测试通过既有 :mod:`tests.engine.runners.openai._sse_helpers` 走 SSE
parser 主路径，断言上述顺序不变量。
"""

from __future__ import annotations

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
)

from tests.engine.runners.openai._sse_helpers import (
    make_thought_hook,
    parse_sse,
)


_DELTA_TYPES: frozenset[RunnerEventType] = frozenset(
    {
        RunnerEventType.RUNNER_CONTENT_DELTA,
        RunnerEventType.RUNNER_REASONING_DELTA,
        RunnerEventType.RUNNER_TOOL_CALL_DELTA,
    }
)

_COMPLETED_TYPES: frozenset[RunnerEventType] = frozenset(
    {
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
    }
)

_ERROR_TYPES: frozenset[RunnerEventType] = frozenset(
    {
        RunnerEventType.RUNNER_HTTP_ERROR,
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
    }
)


def _assert_ordering_invariants(events: list[RunnerEvent]) -> None:
    """对事件序列断言所有顺序不变量。

    :param events: Runner 事件序列。
    """

    types = [e.type for e in events]
    # 1. 终态唯一且在末尾（如果存在 Done）。
    done_indices = [
        i for i, t in enumerate(types) if t is RunnerEventType.RUNNER_DONE
    ]
    if done_indices:
        assert len(done_indices) == 1, (
            f"RUNNER_DONE must appear at most once: {done_indices}"
        )
        assert done_indices[0] == len(types) - 1, (
            f"RUNNER_DONE must be last; got types={types}"
        )

    # 2. delta 单调推进：所有 delta 必须在第一个 completed / error 之前。
    first_completed_or_error: int | None = None
    for i, t in enumerate(types):
        if t in _COMPLETED_TYPES or t in _ERROR_TYPES:
            first_completed_or_error = i
            break
    if first_completed_or_error is not None:
        for i, t in enumerate(types):
            if t in _DELTA_TYPES:
                assert i < first_completed_or_error, (
                    f"delta {t.value} at {i} appears after completed/error "
                    f"at {first_completed_or_error}; types={types}"
                )

    # 3. 错误后必须 Done(ERROR) 收口（如果有 Done）。
    error_indices = [i for i, t in enumerate(types) if t in _ERROR_TYPES]
    if error_indices and done_indices:
        done_event = events[done_indices[0]]
        assert isinstance(done_event.data, RunnerDoneData)
        assert done_event.data.finish_reason is FinishReason.ERROR, (
            "error event present but Done.finish_reason != ERROR"
        )
        # 错误后不得再出现成功 completed
        last_error = error_indices[-1]
        for i in range(last_error + 1, len(types)):
            assert types[i] not in _COMPLETED_TYPES, (
                f"completed event {types[i].value} appears after error"
            )

    # 4. content / tool_calls 完成事件互斥
    has_content_completed = (
        RunnerEventType.RUNNER_CONTENT_COMPLETED in types
    )
    has_tool_calls_completed = (
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED in types
    )
    assert not (has_content_completed and has_tool_calls_completed), (
        "content_completed and tool_calls_completed must be mutually "
        f"exclusive in a single call: {types}"
    )


@pytest.mark.asyncio
async def test_ordering_content_only_stream() -> None:
    """content-only 主路径满足全部顺序不变量。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    _assert_ordering_invariants(events)


@pytest.mark.asyncio
async def test_ordering_reasoning_then_content_stream() -> None:
    """reasoning + content 路径满足全部顺序不变量。"""

    chunks = [
        b'data: {"choices":[{"delta":{"reasoning_content":"plan"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    _assert_ordering_invariants(events)


@pytest.mark.asyncio
async def test_ordering_tool_call_streaming() -> None:
    """tool_call 流式路径：所有 tool_call_delta 必须在 tool_calls_completed 前。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"c1","type":"function",'
            b'"function":{"name":"f"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"function":{"arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    _assert_ordering_invariants(events)
    types = [e.type for e in events]
    last_delta = max(
        i for i, t in enumerate(types)
        if t is RunnerEventType.RUNNER_TOOL_CALL_DELTA
    )
    completed = types.index(
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    )
    assert last_delta < completed


@pytest.mark.asyncio
async def test_ordering_usage_only_chunk_does_not_break_terminal() -> None:
    """``empty choices + usage`` 不破坏终态：仍以唯一 Done 收口。"""

    chunks = [
        b'data: {"choices":[{"delta":{"content":"x"}}]}\n\n',
        (
            b'data: {"choices":[],'
            b'"usage":{"prompt_tokens":1,"completion_tokens":1,'
            b'"total_tokens":2}}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    _assert_ordering_invariants(events)
    # 单次 Done
    assert sum(
        1 for e in events if e.type is RunnerEventType.RUNNER_DONE
    ) == 1


@pytest.mark.asyncio
async def test_ordering_invalid_utf8_no_subsequent_completed() -> None:
    """非法 UTF-8 后**不**得再出现成功 completed 事件，必须 Done(ERROR) 收口。"""

    chunks = [
        # 非法 UTF-8：单独的 0x80 起始字节。
        b"data: {\"choices\":[{\"delta\":{\"content\":\"\x80\"}}]}\n\n",
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    _assert_ordering_invariants(events)


@pytest.mark.asyncio
async def test_ordering_thought_strip_stream_invariants() -> None:
    """Gemini ``<thought>`` 剥离路径仍满足全部顺序不变量。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":'
            b'{"content":"<thought>plan</thought>ans"}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks, hook=make_thought_hook())
    _assert_ordering_invariants(events)
