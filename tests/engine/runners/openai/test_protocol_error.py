"""SSE / 非流式协议错误归一为 :class:`RunnerProtocolErrorData` 测试。"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEventType,
    RunnerProtocolErrorData,
    RunnerToolCallsCompletedData,
)
from dayu.engine.contracts.partial_tool_call import (
    PARTIAL_TOOL_CALL_ID_MAX_CHARS,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)
from dayu.engine.runners.openai.diagnostic_payload import (
    _DIAGNOSTIC_PAYLOAD_MAX_BYTES,
    _PREVIEW_FIELD,
    _TOP_LEVEL_KEYS_FIELD,
)
from dayu.engine.runners.openai.tool_call_aggregator import (
    PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS,
    PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS,
)

from tests.engine.runners.openai._sse_helpers import (
    make_no_thought_hook,
    parse_sse,
)
from tests.engine.runners.openai._diagnostic_helpers import (
    leaf_strings,
    serialized_size,
)


def _sse_json_chunk(payload_json: str) -> bytes:
    """把 JSON 字符串包装为单条 SSE data chunk。

    :param payload_json: 已序列化的 JSON 字符串。
    :returns: UTF-8 编码后的 SSE chunk。
    :raises Exception: 不主动抛出异常。
    """

    return f"data: {payload_json}\n\n".encode("utf-8")


def _diagnostic_payload(raw_payload: JsonValue | None) -> dict[str, JsonValue]:
    """把协议错误 raw payload 收窄为诊断 JSON object。

    :param raw_payload: 协议错误携带的 raw payload 字段。
    :returns: 诊断 JSON object。
    :raises AssertionError: ``raw_payload`` 不是 JSON object 时由 pytest 抛出。
    """

    assert isinstance(raw_payload, dict)
    return raw_payload


@pytest.mark.asyncio
async def test_sse_accepts_utf8_bom_before_first_data_line() -> None:
    """SSE parser 必须接受流开头 UTF-8 BOM。"""

    payload_json = json.dumps(
        {"choices": [{"finish_reason": "stop", "delta": {"content": "ok"}}]},
        separators=(",", ":"),
    )
    events = await parse_sse(
        [b"\xef\xbb\xbf" + _sse_json_chunk(payload_json), b"data: [DONE]\n\n"],
        provider_request_id="req_bom",
    )

    assert events[0].type is RunnerEventType.RUNNER_CONTENT_DELTA
    assert events[-1].type is RunnerEventType.RUNNER_DONE


@pytest.mark.asyncio
async def test_sse_incomplete_utf8_tail_reports_truncated_tail() -> None:
    """流尾残缺 UTF-8 要给出比普通 chunk 解码失败更准确的诊断。"""

    events = await parse_sse([b"data: \xe4"], provider_request_id="req_tail")

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "truncated_utf8_tail"


@pytest.mark.asyncio
async def test_sse_invalid_json_emits_protocol_error() -> None:
    """SSE ``data:`` 行非合法 JSON → 立即 Done(ERROR)，不再处理后续 chunk。"""

    chunks = [
        b"data: not-a-json\n\n",
        b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks, provider_request_id="req_sse")
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "sse_invalid_json"
    assert events[0].data.provider_request_id == "req_sse"
    assert isinstance(events[1].data, RunnerDoneData)
    assert events[1].data.finish_reason is FinishReason.ERROR
    assert events[1].data.provider_request_id == "req_sse"


@pytest.mark.asyncio
async def test_sse_line_buffer_limit_emits_protocol_error() -> None:
    """SSE 单行缓冲超过上限时必须协议错误收口。"""

    events = await parse_sse(
        [b"data: " + (b"x" * (1024 * 1024 + 1))],
        provider_request_id="req_sse_line_limit",
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_line_too_long"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_data_line_count_limit_emits_protocol_error() -> None:
    """单个 SSE event 的 data 行数超过上限时必须协议错误收口。"""

    events = await parse_sse(
        [b"".join(b"data: {}\n" for _index in range(257))],
        provider_request_id="req_sse_data_line_limit",
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_data_lines_too_many"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_provider_error_object_emits_protocol_error() -> None:
    """SSE 200 流内 provider error object 必须失败收口。"""

    payload_json = json.dumps(
        {
            "api_key": "sse-secret-value",
            "error": {
                "message": "bad upstream",
                "type": "server_error",
                "code": "bad_request",
            },
        },
        separators=(",", ":"),
    )
    events = await parse_sse(
        [_sse_json_chunk(payload_json), b"data: [DONE]\n\n"],
        provider_request_id="req_provider_error",
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_provider_error"
    assert error.message == "bad upstream"
    assert error.provider_request_id == "req_provider_error"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["source"] == "sse_provider_error"
    assert diagnostic["kind"] == "provider_error"
    assert isinstance(diagnostic["canonical_byte_size"], int)
    assert isinstance(diagnostic["sha256_digest"], str)
    assert diagnostic["provider_error"] == {
        "code": "bad_request",
        "type": "server_error",
    }
    assert "sse-secret-value" not in tuple(leaf_strings(diagnostic))
    assert serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


def test_non_stream_provider_error_object_emits_protocol_error() -> None:
    """非流式 200 顶层 provider error object 必须产出有界诊断载荷。"""

    payload = json.dumps(
        {
            "token": "non-stream-secret-value",
            "error": {
                "code": "context_length_exceeded",
                "message": "too long",
                "type": "invalid_request_error",
            }
        },
        separators=(",", ":"),
    ).encode("utf-8")

    events = list(
        parse_non_stream_response(
            payload,
            hook=make_no_thought_hook(),
            provider_request_id="req_non_stream_provider_error",
        )
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "non_stream_provider_error"
    assert error.message == "too long"
    assert error.provider_request_id == "req_non_stream_provider_error"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["source"] == "non_stream_provider_error"
    assert diagnostic["kind"] == "provider_error"
    assert isinstance(diagnostic["canonical_byte_size"], int)
    assert isinstance(diagnostic["sha256_digest"], str)
    assert diagnostic["provider_error"] == {
        "code": "context_length_exceeded",
        "type": "invalid_request_error",
    }
    assert "non-stream-secret-value" not in tuple(leaf_strings(diagnostic))
    assert serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


def test_non_stream_large_provider_error_raw_payload_is_bounded() -> None:
    """非流式 provider error 的诊断载荷不得随 provider payload 无界增长。"""

    payload = json.dumps(
        {
            f"key_{index}_{'x' * 512}": "value"
            for index in range(32)
        }
        | {
            "error": {
                "code": "bad_request",
                "message": "too long",
                "type": "invalid_request_error",
            }
        },
        separators=(",", ":"),
    ).encode("utf-8")

    events = list(
        parse_non_stream_response(
            payload,
            hook=make_no_thought_hook(),
            provider_request_id="req_large_provider_error",
        )
    )

    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES
    assert diagnostic["source"] == "non_stream_provider_error"
    assert diagnostic["kind"] == "provider_error"
    assert _PREVIEW_FIELD not in diagnostic
    assert _TOP_LEVEL_KEYS_FIELD not in diagnostic


@pytest.mark.asyncio
async def test_sse_missing_choices_without_usage_emits_protocol_error() -> None:
    """既无有效 choices 也无有效 usage 的 SSE object 必须失败收口。"""

    events = await parse_sse(
        [_sse_json_chunk('{"id":"chunk-without-choices"}'), b"data: [DONE]\n\n"]
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_missing_choices"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["source"] == "sse_missing_choices"
    assert diagnostic["kind"] == "protocol_object"
    assert diagnostic["reason"] == "choices_missing"
    assert serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_empty_choices_without_usage_emits_protocol_error() -> None:
    """SSE ``choices=[]`` 但无 usage 时必须协议错误收口。"""

    events = await parse_sse(
        [_sse_json_chunk('{"choices":[]}'), b"data: [DONE]\n\n"]
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_missing_choices"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["source"] == "sse_missing_choices"
    assert diagnostic["kind"] == "protocol_object"
    assert diagnostic["reason"] == "choices_empty_without_usage"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_usage_only_chunk_does_not_protocol_error() -> None:
    """usage-only chunk 是合法诊断 chunk，不应被 missing choices 误伤。"""

    payload_json = json.dumps(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 0,
                "total_tokens": 5,
            }
        },
        separators=(",", ":"),
    )
    events = await parse_sse(
        [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
            _sse_json_chunk(payload_json),
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    assert not any(
        event.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
        for event in events
    )
    assert any(
        event.type is RunnerEventType.RUNNER_USAGE_RECORDED for event in events
    )


@pytest.mark.asyncio
async def test_sse_invalid_finish_reason_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SSE 未知 finish_reason 必须 fatal，不得回落 STOP。"""

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.sse_parser"
    )
    events = await parse_sse(
        [
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
            b'data: {"choices":[{"finish_reason":"safety_stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    assert [event.type for event in events] == [
        RunnerEventType.RUNNER_CONTENT_DELTA,
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[1].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_invalid_finish_reason"
    done = events[2].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
    assert any(
        "sse_invalid_finish_reason" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_sse_finish_reason_without_delta_emits_invalid_choice_shape() -> None:
    """SSE choice 有 finish_reason 但缺 delta object 时必须 fatal。"""

    events = await parse_sse(
        [
            b'data: {"choices":[{"finish_reason":"stop"}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_invalid_choice_shape"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["reason"] == "delta_missing"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
    assert RunnerEventType.RUNNER_CONTENT_COMPLETED not in {
        event.type for event in events
    }


@pytest.mark.asyncio
async def test_sse_invalid_json_reports_bounded_partial_tool_call() -> None:
    """SSE 中途失败时协议错误携带 partial tool call 摘要且不含 raw arguments。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"call-1","type":"function",'
            b'"function":{"name":"lookup","arguments":"{\\"ticker\\":"}}]}}]}\n\n'
        ),
        b"data: not-a-json\n\n",
    ]
    events = await parse_sse(chunks)
    assert isinstance(events[1].data, RunnerProtocolErrorData)
    partials = events[1].data.partial_tool_calls
    assert len(partials) == 1
    assert partials[0].tool_call_index == 0
    assert partials[0].tool_call_id == "call-1"
    assert partials[0].name_fragment == "lookup"
    assert partials[0].arguments_byte_size > 0
    assert partials[0].arguments_sha256 is not None


@pytest.mark.asyncio
async def test_sse_partial_tool_call_summary_bounds_tool_call_id() -> None:
    """provider 控制的超长 tool_call_id 不得原样进入 partial 摘要。"""

    long_id = "call-" + ("x" * (PARTIAL_TOOL_CALL_ID_MAX_CHARS + 100))
    payload_json = json.dumps(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": long_id,
                                "type": "function",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"ticker":',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        separators=(",", ":"),
    )

    events = await parse_sse([_sse_json_chunk(payload_json), b"data: nope\n\n"])

    protocol_errors = [
        e.data for e in events if isinstance(e.data, RunnerProtocolErrorData)
    ]
    assert len(protocol_errors) == 1
    partial = protocol_errors[0].partial_tool_calls[0]
    assert partial.tool_call_id == long_id[:PARTIAL_TOOL_CALL_ID_MAX_CHARS]
    assert partial.tool_call_id != long_id


@pytest.mark.asyncio
async def test_sse_partial_tool_call_summary_has_hard_bounds() -> None:
    """partial tool call 摘要限制条数与工具名片段长度且不含 raw arguments。"""

    long_name = "lookup_" + (
        "x" * (PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS + 50)
    )
    argument_fragment = '{"secret":"should-not-appear"'
    tool_calls = [
        {
            "index": index,
            "id": f"call-{index}",
            "type": "function",
            "function": {
                "name": long_name,
                "arguments": argument_fragment,
            },
        }
        for index in range(PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS + 7)
    ]
    payload_json = json.dumps(
        {"choices": [{"delta": {"tool_calls": tool_calls}}]},
        separators=(",", ":"),
    )
    events = await parse_sse(
        [_sse_json_chunk(payload_json), b"data: nope\n\n"]
    )

    protocol_errors = [
        e.data for e in events if isinstance(e.data, RunnerProtocolErrorData)
    ]
    assert len(protocol_errors) == 1
    partials = protocol_errors[0].partial_tool_calls
    assert len(partials) == PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS
    assert tuple(p.tool_call_index for p in partials) == tuple(
        range(PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS)
    )
    expected_sha256 = hashlib.sha256(
        argument_fragment.encode("utf-8")
    ).hexdigest()
    for partial in partials:
        name_fragment = partial.name_fragment
        assert name_fragment is not None
        assert name_fragment == long_name[
            :PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS
        ]
        assert len(name_fragment) <= PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS
        assert partial.arguments_byte_size == len(
            argument_fragment.encode("utf-8")
        )
        assert partial.arguments_sha256 == expected_sha256
    assert "should-not-appear" not in repr(partials)


@pytest.mark.asyncio
async def test_sse_usage_malformed_after_tool_delta_logs_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """tool call delta 后 malformed usage 只记日志，后续仍可 completed。"""

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.sse_parser"
    )
    tool_payload = json.dumps(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "lookup",
                                    "arguments": "{}",
                                },
                            }
                        ]
                    }
                }
            ]
        },
        separators=(",", ":"),
    )
    malformed_usage_payload = json.dumps(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": "bad",
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        },
        separators=(",", ":"),
    )
    events = await parse_sse(
        [
            _sse_json_chunk(tool_payload),
            _sse_json_chunk(malformed_usage_payload),
            (
                b'data: {"choices":[{"finish_reason":"tool_calls",'
                b'"delta":{}}]}\n\n'
            ),
            b"data: [DONE]\n\n",
        ]
    )
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.RUNNER_TOOL_CALL_DELTA,
        RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
        RunnerEventType.RUNNER_DONE,
    ]
    completed = events[1].data
    assert isinstance(completed, RunnerToolCallsCompletedData)
    assert len(completed.tool_calls) == 1
    assert completed.tool_calls[0].tool_call_id == "call-1"
    assert completed.tool_calls[0].name == "lookup"
    done = events[2].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.TOOL_CALLS
    assert RunnerEventType.PROVIDER_PROTOCOL_ERROR not in types
    assert any(
        "usage_field_malformed" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_sse_usage_malformed_before_content_completion_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """malformed usage 后继续收到 content 时仍按正常内容完成。"""

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.sse_parser"
    )
    malformed_usage_payload = json.dumps(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": "bad",
                "total_tokens": 2,
            },
        },
        separators=(",", ":"),
    )
    events = await parse_sse(
        [
            _sse_json_chunk(malformed_usage_payload),
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    types = [event.type for event in events]
    assert RunnerEventType.PROVIDER_PROTOCOL_ERROR not in types
    assert RunnerEventType.RUNNER_CONTENT_COMPLETED in types
    completed_events = [
        event for event in events
        if event.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
    ]
    assert len(completed_events) == 1
    completed = completed_events[0].data
    assert isinstance(completed, RunnerContentCompletedData)
    assert completed.content == "ok"
    done_events = [
        event for event in events if event.type is RunnerEventType.RUNNER_DONE
    ]
    assert len(done_events) == 1
    done = done_events[0].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.STOP
    assert any(
        "usage_field_malformed" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_sse_bool_usage_logs_warning_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SSE usage 的 bool token 计数必须视为 malformed 且不阻断内容收口。

    :param caplog: pytest 日志捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 行为不符合预期时由 pytest 抛出。
    """

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.sse_parser"
    )
    malformed_usage_payload = json.dumps(
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": False,
                "total_tokens": 1,
            },
        },
        separators=(",", ":"),
    )
    events = await parse_sse(
        [
            _sse_json_chunk(malformed_usage_payload),
            b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n',
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    assert not any(
        event.type is RunnerEventType.RUNNER_USAGE_RECORDED
        for event in events
    )
    completed_events = [
        event for event in events
        if event.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
    ]
    assert len(completed_events) == 1
    completed = completed_events[0].data
    assert isinstance(completed, RunnerContentCompletedData)
    assert completed.content == "ok"
    assert any(
        "usage_field_malformed" in record.getMessage()
        and "completion_tokens_type=bool" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_sse_non_object_choice_logs_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SSE ``choices`` 内非 object 成员必须 fatal，不得合并其它 choice。"""

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.sse_parser"
    )
    payload_json = json.dumps(
        {"choices": ["bad-choice", {"delta": {"content": "ok"}}]},
        separators=(",", ":"),
    )

    events = await parse_sse(
        [
            _sse_json_chunk(payload_json),
            b'data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n',
            b"data: [DONE]\n\n",
        ]
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_invalid_choice_shape"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
    assert any(
        "sse_invalid_choice_shape" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_sse_all_non_object_choices_end_with_protocol_error() -> None:
    """SSE ``choices`` 全部不是 object 时必须协议错误收口。"""

    events = await parse_sse(
        [
            _sse_json_chunk('{"choices":["bad-choice",1]}'),
            b"data: [DONE]\n\n",
        ]
    )

    errors = [
        event.data
        for event in events
        if event.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    ]
    assert len(errors) == 1
    assert isinstance(errors[0], RunnerProtocolErrorData)
    assert errors[0].error_code == "sse_invalid_choice_shape"
    diagnostic = _diagnostic_payload(errors[0].raw_payload)
    assert diagnostic["reason"] == "choice_not_object"
    done = [event for event in events if event.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1


@pytest.mark.asyncio
async def test_sse_all_non_object_choices_with_usage_protocol_error() -> None:
    """非空 choices 全不可解析时，即使 usage 合法也必须协议错误收口。"""

    payload_json = json.dumps(
        {
            "choices": ["bad-choice", None],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 0,
                "total_tokens": 5,
            },
        },
        separators=(",", ":"),
    )
    events = await parse_sse([_sse_json_chunk(payload_json), b"data: [DONE]\n\n"])

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "sse_invalid_choice_shape"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["reason"] == "choice_not_object"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_tool_call_missing_id_emits_missing_id_error() -> None:
    """tool_call 始终缺失 ``id`` → fatal 错误 + Done(ERROR)，无 ToolCallsCompleted。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"function":{"name":"f","arguments":"{}"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    codes = {
        e.data.error_code
        for e in events
        if isinstance(e.data, RunnerProtocolErrorData)
    }
    assert "tool_call_missing_id" in codes
    # 不得产出成功的 ToolCallsCompleted
    assert not any(
        e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED for e in events
    )
    # Done 终态必须是 ERROR
    done_events = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done_events) == 1
    assert isinstance(done_events[0].data, RunnerDoneData)
    assert done_events[0].data.finish_reason is FinishReason.ERROR


@pytest.mark.asyncio
async def test_sse_tool_call_arguments_not_object_error() -> None:
    """tool_call 参数非对象 → fatal 错误 + Done(ERROR)，无 ToolCallsCompleted。"""

    chunks = [
        (
            b'data: {"choices":[{"delta":{"tool_calls":'
            b'[{"index":0,"id":"c1","type":"function",'
            b'"function":{"name":"f","arguments":"[1,2,3]"}}]}}]}\n\n'
        ),
        b'data: {"choices":[{"finish_reason":"tool_calls","delta":{}}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    events = await parse_sse(chunks)
    codes = {
        e.data.error_code
        for e in events
        if isinstance(e.data, RunnerProtocolErrorData)
    }
    assert "tool_call_arguments_not_object" in codes
    assert not any(
        e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED for e in events
    )
    done_events = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done_events) == 1
    assert isinstance(done_events[0].data, RunnerDoneData)
    assert done_events[0].data.finish_reason is FinishReason.ERROR


def test_non_stream_invalid_json_error_then_done() -> None:
    """非流式响应非 JSON → ``non_stream_invalid_json`` + Done(ERROR)。"""

    events = list(
        (
            parse_non_stream_response(
                b"not-json",
                hook=make_no_thought_hook(),
                provider_request_id="req_json",
            )
        )
    )
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "non_stream_invalid_json"
    assert events[0].data.provider_request_id == "req_json"
    assert isinstance(events[1].data, RunnerDoneData)
    assert events[1].data.finish_reason is FinishReason.ERROR
    assert events[1].data.provider_request_id == "req_json"


def test_non_stream_payload_not_object_error() -> None:
    """非流式响应顶层不是 object → ``non_stream_payload_not_object``。"""

    payload = json.dumps([1, 2, 3]).encode("utf-8")
    events = list(
        (parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None))
    )
    assert events[0].type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "non_stream_payload_not_object"


def test_non_stream_missing_choices_error() -> None:
    """非流式响应缺 ``choices`` → ``non_stream_missing_choices``。"""

    payload = json.dumps({}).encode("utf-8")
    events = list(
        (parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None))
    )
    assert events[0].type is RunnerEventType.PROVIDER_PROTOCOL_ERROR
    assert isinstance(events[0].data, RunnerProtocolErrorData)
    assert events[0].data.error_code == "non_stream_missing_choices"


@pytest.mark.parametrize(
    "choices_value",
    (
        [],
        {"0": {"message": {"content": "answer"}}},
    ),
)
def test_non_stream_empty_or_non_list_choices_error(
    choices_value: JsonValue,
) -> None:
    """非流式 ``choices`` 为空或非数组时必须协议错误收口。

    :param choices_value: provider 返回的 choices 原始值。
    :returns: 无返回值。
    :raises AssertionError: 未按协议错误收口时由 pytest 抛出。
    """

    payload = json.dumps({"choices": choices_value}).encode("utf-8")

    events = list(
        parse_non_stream_response(
            payload, hook=make_no_thought_hook(), provider_request_id=None
        )
    )

    assert [event.type for event in events] == [
        RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerEventType.RUNNER_DONE,
    ]
    error = events[0].data
    assert isinstance(error, RunnerProtocolErrorData)
    assert error.error_code == "non_stream_missing_choices"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
