"""stream / non-stream 终态语义一致性守卫测试。

按 ``docs/code_review.md`` §6 与 ``docs/engine/phase1-plan.md`` §6.4 / §12：
两条解析路径在「最终事件语义」上必须一致——同样的 provider 协议事实，
不论是流式还是非流式响应，最终的 :class:`RunnerContentCompletedData`
``content`` / ``reasoning_content`` / ``finish_reason`` 必须相同；终态
``RunnerDoneData.finish_reason`` 必须相同。

本测试以 Gemini ``<thought>`` 协议为测试场景：两条路径都应剥离
``<thought>`` 到 ``reasoning_content``，且终态 finish_reason 一致。
"""

from __future__ import annotations

import json

import pytest

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
        stream_completed.finish_reason
        is ns_completed.finish_reason
        is FinishReason.STOP
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
async def test_stream_and_non_stream_content_finish_reason_parity(
    provider_finish_reason: str,
    expected: FinishReason,
) -> None:
    """正文完成 finish_reason 在流式与非流式路径中保持一致。

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
    assert stream_completed.finish_reason is ns_completed.finish_reason
    assert stream_completed.finish_reason is expected
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
