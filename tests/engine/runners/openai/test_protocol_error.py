"""SSE / 非流式协议错误归一为 :class:`RunnerProtocolErrorData` 测试。"""

from __future__ import annotations

import hashlib
import json
import logging

import pytest

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
from dayu.engine.runners.openai.tool_call_aggregator import (
    PARTIAL_TOOL_CALL_NAME_FRAGMENT_MAX_CHARS,
    PARTIAL_TOOL_CALL_SUMMARY_MAX_ITEMS,
)

from tests.engine.runners.openai._sse_helpers import (
    make_no_thought_hook,
    parse_sse,
)


def _sse_json_chunk(payload_json: str) -> bytes:
    """把 JSON 字符串包装为单条 SSE data chunk。

    :param payload_json: 已序列化的 JSON 字符串。
    :returns: UTF-8 编码后的 SSE chunk。
    :raises Exception: 不主动抛出异常。
    """

    return f"data: {payload_json}\n\n".encode("utf-8")


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
    assert completed.finish_reason is FinishReason.STOP
    assert any(
        "usage_field_malformed" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_sse_non_object_choice_logs_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SSE ``choices`` 内非 object 成员只记录诊断，不改变协议行为。"""

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

    assert any(
        "code=sse_choice_not_object" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        event.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
        for event in events
    )


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
