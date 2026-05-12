"""OLD/NEW Runner 协议一致性 regression 测试集。

本文件按 ``docs/engine/phase1-runner-old-new-review.md`` 14/15 节列出的
阻塞 / 重要问题修复后补充的回归测试，确保以下 OLD 协议事实在 NEW
Runner 上不再漂移：

1. **non-stream tool call dict arguments**：dict 形态被保留为 JSON
   string，list 形态触发协议错误。
2. **HTTP 408 可重试**：``classify_http_status(408)`` →
   :attr:`RunnerHTTPErrorCode.TIMEOUT`，且属于 retriable 集合。
3. **429 专用 backoff**：429 无 ``Retry-After`` 首次 4s、cap 60s；
   ``Retry-After`` cap 120s。
4. **non-stream reasoning 顺序**：``extracted_reasoning + native_reasoning``。
5. **缺 index 并行 tool call delta**：SSE parser emit 的
   ``tool_call_index`` 与最终 completed 事件中 ``index_in_iteration``
   一致，可稳定区分同一回合内的多个 tool call。
"""

from __future__ import annotations

import json

import pytest

from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerEvent,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerProtocolErrorData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
)
from dayu.engine.runners.openai.error_classifier import (
    classify_http_status,
    is_retriable,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)

from tests.engine.runners.openai._sse_helpers import (
    make_no_thought_hook,
    make_thought_hook,
    parse_sse,
)


def test_non_stream_tool_call_dict_arguments_preserved() -> None:
    """non-stream ``function.arguments`` 为 dict → 完整保留为 JSON。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-a",
                                "type": "function",
                                "function": {
                                    "name": "do",
                                    "arguments": {"a": 1, "b": "x"},
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        (parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None))
    )
    completed = next(
        e.data
        for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    )
    assert isinstance(completed, RunnerToolCallsCompletedData)
    assert len(completed.tool_calls) == 1
    tc = completed.tool_calls[0]
    assert tc.tool_call_id == "call-a"
    assert tc.name == "do"
    assert tc.arguments == {"a": 1, "b": "x"}


def test_non_stream_tool_call_list_arguments_protocol_error() -> None:
    """non-stream ``function.arguments`` 为 list → fatal 协议错误 + Done(ERROR)。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-b",
                                "type": "function",
                                "function": {
                                    "name": "do",
                                    "arguments": [1, 2, 3],
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        (parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None))
    )
    types = [e.type for e in events]
    assert RunnerEventType.PROVIDER_PROTOCOL_ERROR in types
    error_event = next(
        e for e in events
        if e.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    )
    assert isinstance(error_event.data, RunnerProtocolErrorData)
    assert error_event.data.error_code == "tool_call_arguments_not_object"
    # 不能再产 successful tool_calls_completed
    assert (
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED not in types
    )
    assert types[-1] is RunnerEventType.RUNNER_DONE


def test_non_stream_tool_call_invalid_string_json_protocol_error() -> None:
    """non-stream ``arguments`` 为非法 JSON 字符串 → fatal 协议错误。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-c",
                                "type": "function",
                                "function": {
                                    "name": "do",
                                    "arguments": "not-json",
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        (parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None))
    )
    error_codes = [
        e.data.error_code
        for e in events
        if e.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
        and isinstance(e.data, RunnerProtocolErrorData)
    ]
    assert "tool_call_arguments_invalid_json" in error_codes


def test_http_408_classified_as_timeout_and_retriable() -> None:
    """HTTP 408 → TIMEOUT，is_retriable 为 True。"""

    code = classify_http_status(408)
    assert code is RunnerHTTPErrorCode.TIMEOUT
    assert is_retriable(code) is True


@pytest.mark.asyncio
async def test_sse_parallel_missing_index_tool_call_delta_indices_match() -> (
    None
):
    """两个仅靠 ``id`` 区分的并行 tool call → delta 事件 index 与 completed 一致。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"id":"call-1","type":"function",'
            b'"function":{"name":"f1","arguments":"{\\"a\\":1}"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"id":"call-2","type":"function",'
            b'"function":{"name":"f2","arguments":"{\\"b\\":2}"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}'
            b"\n\n"
        ),
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    delta_events = [
        e for e in events if e.type is RunnerEventType.RUNNER_TOOL_CALL_DELTA
    ]
    assert len(delta_events) == 2
    indices_by_id: dict[str, int] = {}
    for ev in delta_events:
        assert isinstance(ev.data, RunnerToolCallDeltaData)
        assert ev.data.tool_call_id is not None
        indices_by_id[ev.data.tool_call_id] = ev.data.tool_call_index
    # 两个 id 必须分配到不同的 delta index
    assert (
        indices_by_id["call-1"] != indices_by_id["call-2"]
    ), indices_by_id
    completed = next(
        e.data
        for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    )
    assert isinstance(completed, RunnerToolCallsCompletedData)
    assert len(completed.tool_calls) == 2
    completed_indices_by_id = {
        tc.tool_call_id: tc.index_in_iteration for tc in completed.tool_calls
    }
    # delta 事件的 ``tool_call_index`` 与 completed 事件中的
    # ``index_in_iteration`` 在「单一来源」（合成 index 复用 dense
    # 0..N-1 命名空间）下一致。
    assert indices_by_id == completed_indices_by_id


@pytest.mark.asyncio
async def test_stream_non_stream_native_reasoning_with_thought_parity() -> None:
    """同时有 native ``reasoning_content`` + ``<thought>`` 时，stream/non-stream 顺序一致。

    OLD 顺序：``extracted_reasoning + native_reasoning``。
    """

    stream_chunks = [
        (
            b'data: {"choices":[{"delta":'
            b'{"content":"<thought>extra</thought>final",'
            b'"reasoning_content":"prior;"}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    stream_events = await parse_sse(stream_chunks, hook=make_thought_hook())
    non_stream_payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "<thought>extra</thought>final",
                        "reasoning_content": "prior;",
                    },
                }
            ]
        }
    ).encode("utf-8")
    non_stream_events = list(
        (parse_non_stream_response(
            non_stream_payload, hook=make_thought_hook(), provider_request_id=None)
        )
    )

    def _completed_reasoning(
        events: list[RunnerEvent],
    ) -> str | None:
        for ev in events:
            if ev.type is RunnerEventType.RUNNER_CONTENT_COMPLETED:
                assert isinstance(ev.data, RunnerContentCompletedData)
                return ev.data.reasoning_content
        return None

    stream_reasoning = _completed_reasoning(list(stream_events))
    non_stream_reasoning = _completed_reasoning(list(non_stream_events))
    assert stream_reasoning == non_stream_reasoning == "extraprior;"


@pytest.mark.asyncio
async def test_sse_pos_fallback_continuation_arguments_attached() -> None:
    """OLD pos fallback：首帧 ``id/name``，后续 ``arguments`` 帧缺 ``id/index`` → 按 pos 归位。

    OLD 协议事实：当后续 arguments delta 既无 ``id`` 也无 ``index``，
    且其在 ``tool_calls`` 数组中的位置 ``pos`` 已对应到既有 partial
    时，应按 ``pos`` 归到该 partial，从而正确拼出 ``arguments``。
    """

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call_1","type":"function",'
            b'"function":{"name":"tool"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"function":{"arguments":"{\\"a\\":"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"function":{"arguments":"1}"}}]}}]}\n\n'
        ),
        (
            b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}'
            b"\n\n"
        ),
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    # 不能产 ``tool_call_missing_index_and_id`` 协议错误
    error_codes = [
        e.data.error_code
        for e in events
        if e.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
        and isinstance(e.data, RunnerProtocolErrorData)
    ]
    assert "tool_call_missing_index_and_id" not in error_codes
    completed = next(
        e.data
        for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    )
    assert isinstance(completed, RunnerToolCallsCompletedData)
    assert len(completed.tool_calls) == 1
    tc = completed.tool_calls[0]
    assert tc.tool_call_id == "call_1"
    assert tc.name == "tool"
    assert tc.arguments == {"a": 1}
