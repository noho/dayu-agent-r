"""stream / non-stream 终态语义一致性守卫测试。

按 ``docs/code_review.md`` §6 与 ``docs/engine/phase1-plan.md`` §6.4 / §12：
两条解析路径在「最终事件语义」上必须一致——同样的 provider 协议事实，
不论是流式还是非流式响应，最终的 :class:`RunnerContentCompletedData`
``content`` / ``reasoning_content`` 必须相同；终态
:class:`RunnerDoneData.finish_reason` 必须相同。

本测试以 Gemini ``<thought>`` 协议为测试场景：两条路径都应剥离
``<thought>`` 到 ``reasoning_content``，且终态 finish_reason 一致。
"""

from __future__ import annotations

import json

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventType,
    RunnerProtocolErrorData,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)

from tests.engine.runners.openai._sse_helpers import (
    make_no_thought_hook,
    make_thought_hook,
    parse_sse,
)


def _extract_completed_and_done(
    events: list[RunnerEvent],
) -> tuple[RunnerContentCompletedData, RunnerDoneData]:
    """从事件列表中抽取 ``content_completed`` 与 ``done`` 数据。

    :param events: :class:`RunnerEvent` 列表。
    :returns: ``(completed_data, done_data)`` 二元组。
    """

    completed: RunnerContentCompletedData | None = None
    done: RunnerDoneData | None = None
    for ev in events:
        if ev.type is RunnerEventType.RUNNER_CONTENT_COMPLETED:
            assert isinstance(ev.data, RunnerContentCompletedData)
            completed = ev.data
        elif ev.type is RunnerEventType.RUNNER_DONE:
            assert isinstance(ev.data, RunnerDoneData)
            done = ev.data
    assert completed is not None, "RUNNER_CONTENT_COMPLETED missing"
    assert done is not None, "RUNNER_DONE missing"
    return completed, done


def _extract_protocol_error_and_done(
    events: list[RunnerEvent],
) -> tuple[RunnerProtocolErrorData, RunnerDoneData]:
    """从事件列表中抽取协议错误与 ``done`` 数据。

    :param events: :class:`RunnerEvent` 列表。
    :returns: ``(protocol_error_data, done_data)`` 二元组。
    :raises AssertionError: 缺少目标事件时由 pytest 抛出。
    """

    protocol_error: RunnerProtocolErrorData | None = None
    done: RunnerDoneData | None = None
    for ev in events:
        if ev.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR:
            assert isinstance(ev.data, RunnerProtocolErrorData)
            protocol_error = ev.data
        elif ev.type is RunnerEventType.RUNNER_DONE:
            assert isinstance(ev.data, RunnerDoneData)
            done = ev.data
    assert protocol_error is not None, "PROVIDER_PROTOCOL_ERROR missing"
    assert done is not None, "RUNNER_DONE missing"
    return protocol_error, done


def _sse_chunk(payload: dict[str, JsonValue]) -> bytes:
    """把 JSON object 包装为单条 SSE data chunk。

    :param payload: 要序列化的 provider JSON object。
    :returns: UTF-8 编码后的 SSE chunk。
    :raises Exception: 不主动抛出异常。
    """

    payload_json = json.dumps(payload, separators=(",", ":"))
    return f"data: {payload_json}\n\n".encode("utf-8")


async def _stream_terminal_events(
    *,
    has_tool_calls: bool,
    finish_reason_field: dict[str, JsonValue],
) -> list[RunnerEvent]:
    """构造指定 terminal shape 的 SSE 事件。

    :param has_tool_calls: 是否发送 tool-call delta。
    :param finish_reason_field: terminal choice 的 finish_reason 字段。
    :returns: parser 产出的 Runner 事件列表。
    :raises Exception: parser 异常时向上传播。
    """

    delta: dict[str, JsonValue]
    if has_tool_calls:
        delta = {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call-a",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{}"},
                }
            ]
        }
    else:
        delta = {"content": "answer"}
    initial_choice: dict[str, JsonValue] = {"delta": delta}
    raw_finish_reason = finish_reason_field.get("finish_reason")
    chunks = [_sse_chunk({"choices": [initial_choice]})]
    if isinstance(raw_finish_reason, str):
        terminal_choice: dict[str, JsonValue] = {
            **finish_reason_field,
            "delta": {},
        }
        chunks.append(_sse_chunk({"choices": [terminal_choice]}))
    else:
        initial_choice.update(finish_reason_field)
        chunks[0] = _sse_chunk({"choices": [initial_choice]})
    chunks.append(b"data: [DONE]\n\n")
    return await parse_sse(
        chunks,
        hook=make_no_thought_hook(),
    )


def _non_stream_terminal_events(
    *,
    has_tool_calls: bool,
    finish_reason_field: dict[str, JsonValue],
) -> list[RunnerEvent]:
    """构造指定 terminal shape 的 non-stream 事件。

    :param has_tool_calls: assistant message 是否带 tool calls。
    :param finish_reason_field: choice 的 finish_reason 字段。
    :returns: parser 产出的 Runner 事件列表。
    :raises Exception: parser 异常时向上传播。
    """

    message: dict[str, JsonValue] = {
        "role": "assistant",
        "content": None if has_tool_calls else "answer",
    }
    if has_tool_calls:
        message["tool_calls"] = [
            {
                "id": "call-a",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }
        ]
    choice: dict[str, JsonValue] = {
        **finish_reason_field,
        "message": message,
    }
    payload = json.dumps({"choices": [choice]}).encode("utf-8")
    return list(
        parse_non_stream_response(
            payload,
            hook=make_no_thought_hook(),
            provider_request_id=None,
        )
    )


@pytest.mark.asyncio
async def test_stream_and_non_stream_thought_strip_terminal_parity() -> None:
    """Gemini ``<thought>...</thought>answer`` 在两条路径终态一致。"""

    # 流式路径：单 chunk 携带完整 ``<thought>...</thought>ans``。
    stream_chunks = [
        (
            b'data: {"choices":[{"delta":'
            b'{"content":"<thought>plan</thought>ans"}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    stream_events = await parse_sse(stream_chunks, hook=make_thought_hook())
    stream_completed, stream_done = _extract_completed_and_done(
        list(stream_events)
    )

    # 非流式路径：等价的 chat completion JSON。
    non_stream_payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "<thought>plan</thought>ans",
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
    ns_completed, ns_done = _extract_completed_and_done(non_stream_events)

    # 终态语义必须一致
    assert stream_completed.content == ns_completed.content == "ans"
    assert (
        stream_completed.reasoning_content
        == ns_completed.reasoning_content
        == "plan"
    )
    assert (
        stream_done.finish_reason
        is ns_done.finish_reason
        is FinishReason.STOP
    )


@pytest.mark.parametrize(
    "provider_finish_reason, expected",
    (
        ("stop", FinishReason.STOP),
        ("length", FinishReason.LENGTH),
        ("content_filter", FinishReason.CONTENT_FILTER),
    ),
)
@pytest.mark.asyncio
async def test_stream_and_non_stream_done_finish_reason_parity(
    provider_finish_reason: str,
    expected: FinishReason,
) -> None:
    """Runner done finish_reason 在流式与非流式路径中保持一致。

    :param provider_finish_reason: provider 返回的 finish_reason 字符串。
    :param expected: 期望映射到的 Runner finish reason。
    :returns: 无返回值。
    :raises AssertionError: 两条解析路径不一致时由 pytest 抛出。
    """

    stream_chunks = [
        b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
        (
            b'data: {"choices":[{"finish_reason":"'
            + provider_finish_reason.encode("utf-8")
            + b'","delta":{}}]}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]
    stream_events = await parse_sse(stream_chunks, hook=make_no_thought_hook())
    stream_completed, stream_done = _extract_completed_and_done(
        list(stream_events)
    )

    non_stream_payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": provider_finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": "answer",
                    },
                }
            ]
        }
    ).encode("utf-8")
    non_stream_events = list(
        parse_non_stream_response(
            non_stream_payload,
            hook=make_no_thought_hook(),
            provider_request_id=None,
        )
    )
    ns_completed, ns_done = _extract_completed_and_done(non_stream_events)

    assert stream_completed.content == ns_completed.content == "answer"
    assert stream_done.finish_reason is ns_done.finish_reason
    assert stream_done.finish_reason is expected


@pytest.mark.asyncio
async def test_stream_and_non_stream_provider_error_object_parity() -> None:
    """stream / non-stream provider error object 的诊断核心字段一致。"""

    provider_error_payload = {
        "error": {
            "code": "context_length_exceeded",
            "type": "invalid_request_error",
            "message": "too long",
        }
    }
    stream_payload_json = json.dumps(
        provider_error_payload,
        separators=(",", ":"),
    )
    stream_events = await parse_sse(
        [f"data: {stream_payload_json}\n\n".encode("utf-8")],
        hook=make_no_thought_hook(),
        provider_request_id="req_stream",
    )
    stream_error, stream_done = _extract_protocol_error_and_done(
        list(stream_events)
    )

    non_stream_payload = json.dumps(
        provider_error_payload,
        separators=(",", ":"),
    ).encode("utf-8")
    non_stream_events = list(
        parse_non_stream_response(
            non_stream_payload,
            hook=make_no_thought_hook(),
            provider_request_id="req_non_stream",
        )
    )
    ns_error, ns_done = _extract_protocol_error_and_done(non_stream_events)

    assert [event.type for event in stream_events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert [event.type for event in non_stream_events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert stream_error.error_code == "sse_provider_error"
    assert ns_error.error_code == "non_stream_provider_error"
    assert stream_error.message == ns_error.message == "too long"
    assert stream_error.provider_request_id == "req_stream"
    assert ns_error.provider_request_id == "req_non_stream"
    assert stream_done.finish_reason is ns_done.finish_reason is FinishReason.ERROR
    assert isinstance(stream_error.raw_payload, dict)
    assert isinstance(ns_error.raw_payload, dict)
    assert (
        stream_error.raw_payload["canonical_byte_size"]
        == ns_error.raw_payload["canonical_byte_size"]
    )
    assert (
        stream_error.raw_payload["sha256_digest"]
        == ns_error.raw_payload["sha256_digest"]
    )
    assert (
        stream_error.raw_payload["provider_error"]
        == ns_error.raw_payload["provider_error"]
        == {
            "code": "context_length_exceeded",
            "type": "invalid_request_error",
        }
    )


@pytest.mark.parametrize(
    "raw_finish_reason",
    (
        "safety_stop",
        "",
        1,
        True,
        ["stop"],
        {"kind": "stop"},
    ),
)
@pytest.mark.asyncio
async def test_stream_and_non_stream_invalid_finish_reason_fail_closed(
    raw_finish_reason: JsonValue,
) -> None:
    """非法 finish_reason 在 stream / non-stream 路径都必须 fatal。

    :param raw_finish_reason: provider wire finish_reason 原始值。
    :returns: 无返回值。
    :raises AssertionError: 任一路径未 fail closed 时由 pytest 抛出。
    """

    stream_choice: dict[str, JsonValue] = {
        "finish_reason": raw_finish_reason,
        "delta": {},
    }
    stream_events = await parse_sse(
        [
            b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
            _sse_chunk({"choices": [stream_choice]}),
            b"data: [DONE]\n\n",
        ],
        hook=make_no_thought_hook(),
    )
    stream_error, stream_done = _extract_protocol_error_and_done(stream_events)

    non_stream_choice: dict[str, JsonValue] = {
        "finish_reason": raw_finish_reason,
        "message": {"role": "assistant", "content": "answer"},
    }
    non_stream_events = list(
        parse_non_stream_response(
            json.dumps({"choices": [non_stream_choice]}).encode("utf-8"),
            hook=make_no_thought_hook(),
            provider_request_id=None,
        )
    )
    ns_error, ns_done = _extract_protocol_error_and_done(non_stream_events)

    assert stream_error.error_code == "sse_invalid_finish_reason"
    assert ns_error.error_code == "non_stream_invalid_finish_reason"
    assert stream_done.finish_reason is ns_done.finish_reason is FinishReason.ERROR
    assert RunnerEventType.RUNNER_CONTENT_COMPLETED not in {
        event.type for event in stream_events
    }
    assert RunnerEventType.RUNNER_CONTENT_COMPLETED not in {
        event.type for event in non_stream_events
    }


@pytest.mark.asyncio
async def test_stream_and_non_stream_multi_choice_fail_closed() -> None:
    """stream / non-stream 多个 assistant choices 都必须 fatal。"""

    stream_events = await parse_sse(
        [
            (
                b'data: {"choices":[{"delta":{"content":"a"}},'
                b'{"delta":{"content":"b"}}]}\n\n'
            ),
            b"data: [DONE]\n\n",
        ],
        hook=make_no_thought_hook(),
    )
    stream_error, stream_done = _extract_protocol_error_and_done(stream_events)

    non_stream_payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "a"},
                },
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "b"},
                },
            ]
        }
    ).encode("utf-8")
    non_stream_events = list(
        parse_non_stream_response(
            non_stream_payload,
            hook=make_no_thought_hook(),
            provider_request_id=None,
        )
    )
    ns_error, ns_done = _extract_protocol_error_and_done(non_stream_events)

    assert [event.type for event in stream_events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert stream_error.error_code == "sse_multiple_valid_choices"
    assert ns_error.error_code == "non_stream_multiple_choices"
    assert stream_done.finish_reason is ns_done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_stream_and_non_stream_explicit_non_zero_index_fail_closed() -> None:
    """显式非零 choice index 在 stream / non-stream 路径都必须 fatal。"""

    stream_events = await parse_sse(
        [
            b'data: {"choices":[{"index":1,"delta":{"content":"a"}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
        hook=make_no_thought_hook(),
    )
    stream_error, stream_done = _extract_protocol_error_and_done(stream_events)

    non_stream_payload = json.dumps(
        {
            "choices": [
                {
                    "index": 1,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "a"},
                }
            ]
        }
    ).encode("utf-8")
    non_stream_events = list(
        parse_non_stream_response(
            non_stream_payload,
            hook=make_no_thought_hook(),
            provider_request_id=None,
        )
    )
    ns_error, ns_done = _extract_protocol_error_and_done(non_stream_events)

    assert stream_error.error_code == "sse_choice_index_non_zero"
    assert ns_error.error_code == "non_stream_choice_index_non_zero"
    assert stream_done.finish_reason is ns_done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_empty_delta_plus_one_valid_choice_uses_only_valid_choice() -> None:
    """empty delta choice 不算 valid assistant choice，也不制造多 choice。"""

    events = await parse_sse(
        [
            (
                b'data: {"choices":[{"index":0,"delta":{}},'
                b'{"delta":{"content":"ok"}}]}\n\n'
            ),
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
        hook=make_no_thought_hook(),
    )

    completed, done = _extract_completed_and_done(events)
    assert completed.content == "ok"
    assert done.finish_reason is FinishReason.STOP


@pytest.mark.asyncio
async def test_sse_conflicting_terminal_finish_reason_fail_closed() -> None:
    """跨 chunk 终态 finish_reason 冲突必须 fatal。"""

    events = await parse_sse(
        [
            b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
            b'data: {"choices":[{"finish_reason":"length","delta":{}}]}\n\n',
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
        hook=make_no_thought_hook(),
    )

    error, done = _extract_protocol_error_and_done(events)
    assert error.error_code == "sse_conflicting_finish_reason"
    assert done.finish_reason is FinishReason.ERROR
    assert RunnerEventType.RUNNER_CONTENT_COMPLETED not in {
        event.type for event in events
    }


@pytest.mark.asyncio
async def test_sse_content_without_terminal_finish_reason_fail_closed() -> None:
    """SSE content-only 成功路径缺 terminal finish_reason 必须 fatal。"""

    events = await parse_sse(
        [
            b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
            b"data: [DONE]\n\n",
        ],
        hook=make_no_thought_hook(),
    )

    error, done = _extract_protocol_error_and_done(events)
    assert error.error_code == "sse_missing_finish_reason"
    assert done.finish_reason is FinishReason.ERROR
    assert RunnerEventType.RUNNER_CONTENT_COMPLETED not in {
        event.type for event in events
    }


@pytest.mark.parametrize(
    ("has_tool_calls", "finish_reason"),
    (
        (True, "stop"),
        (True, "length"),
        (True, "content_filter"),
        (False, "tool_calls"),
    ),
)
@pytest.mark.asyncio
async def test_stream_and_non_stream_terminal_shape_mismatch_fail_closed(
    has_tool_calls: bool,
    finish_reason: str,
) -> None:
    """tool presence 与显式 finish reason 不一致时两路都必须 fatal。

    :param has_tool_calls: response 是否携带 tool calls。
    :param finish_reason: 与 response shape 冲突的显式终态。
    :returns: 无返回值。
    :raises AssertionError: 任一路径先产出成功 completed 时由 pytest 抛出。
    """

    finish_reason_field: dict[str, JsonValue] = {
        "finish_reason": finish_reason
    }
    stream_events = await _stream_terminal_events(
        has_tool_calls=has_tool_calls,
        finish_reason_field=finish_reason_field,
    )
    non_stream_events = _non_stream_terminal_events(
        has_tool_calls=has_tool_calls,
        finish_reason_field=finish_reason_field,
    )

    stream_error, stream_done = _extract_protocol_error_and_done(stream_events)
    ns_error, ns_done = _extract_protocol_error_and_done(non_stream_events)
    assert stream_error.error_code == "sse_tool_calls_finish_reason_mismatch"
    assert (
        ns_error.error_code
        == "non_stream_tool_calls_finish_reason_mismatch"
    )
    assert stream_done.finish_reason is ns_done.finish_reason is FinishReason.ERROR
    completed_types = {
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
    }
    assert completed_types.isdisjoint(event.type for event in stream_events)
    assert completed_types.isdisjoint(event.type for event in non_stream_events)


@pytest.mark.parametrize("has_tool_calls", (False, True))
@pytest.mark.parametrize(
    "finish_reason_field",
    (
        {},
        {"finish_reason": None},
    ),
)
@pytest.mark.asyncio
async def test_stream_and_non_stream_missing_terminal_reason_fail_closed(
    has_tool_calls: bool,
    finish_reason_field: dict[str, JsonValue],
) -> None:
    """missing/null finish reason 对 content/tool-call 两种 shape 均 fatal。

    :param has_tool_calls: response 是否携带 tool calls。
    :param finish_reason_field: 缺失或显式 null 的 terminal 字段。
    :returns: 无返回值。
    :raises AssertionError: 任一路径默认终态时由 pytest 抛出。
    """

    stream_events = await _stream_terminal_events(
        has_tool_calls=has_tool_calls,
        finish_reason_field=finish_reason_field,
    )
    non_stream_events = _non_stream_terminal_events(
        has_tool_calls=has_tool_calls,
        finish_reason_field=finish_reason_field,
    )

    stream_error, stream_done = _extract_protocol_error_and_done(stream_events)
    ns_error, ns_done = _extract_protocol_error_and_done(non_stream_events)
    assert stream_error.error_code == "sse_missing_finish_reason"
    assert ns_error.error_code == "non_stream_missing_finish_reason"
    assert stream_done.finish_reason is ns_done.finish_reason is FinishReason.ERROR
    completed_types = {
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
    }
    assert completed_types.isdisjoint(event.type for event in stream_events)
    assert completed_types.isdisjoint(event.type for event in non_stream_events)
