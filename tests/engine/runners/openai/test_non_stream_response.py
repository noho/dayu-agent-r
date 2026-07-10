"""非流式 JSON 响应解析测试。"""

from __future__ import annotations

import json
import logging

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEventType,
    RunnerProviderDiagnosticData,
    RunnerProtocolErrorData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)
from tests.engine.runners.openai._sse_helpers import make_no_thought_hook


def _diagnostic_payload(raw_payload: JsonValue | None) -> dict[str, JsonValue]:
    """把协议错误 raw payload 收窄为诊断 JSON object。

    :param raw_payload: 协议错误携带的 raw payload 字段。
    :returns: 诊断 JSON object。
    :raises AssertionError: ``raw_payload`` 不是 JSON object 时由 pytest 抛出。
    """

    assert isinstance(raw_payload, dict)
    return raw_payload


def test_non_stream_content_completed_and_usage_and_done() -> None:
    """非流式响应 → ContentCompleted + Usage + Done(STOP)。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "answer",
                        "reasoning_content": "thoughts",
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 2,
                "total_tokens": 9,
            },
        }
    ).encode("utf-8")
    events = list(
        (
            parse_non_stream_response(
                payload,
                hook=make_no_thought_hook(),
                provider_request_id="req-usage",
            )
        )
    )
    types = [e.type for e in events]
    assert types == [
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_USAGE_RECORDED,
        RunnerEventType.RUNNER_DONE,
    ]
    completed = events[0].data
    assert isinstance(completed, RunnerContentCompletedData)
    assert completed.content == "answer"
    assert completed.reasoning_content == "thoughts"

    usage = events[1].data
    assert isinstance(usage, RunnerUsageRecordedData)
    assert usage.total_tokens == 9
    assert usage.provider_request_id == "req-usage"

    done = events[2].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.STOP


def test_non_stream_bool_usage_logs_warning_and_omits_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """非流式 usage 的 bool token 计数必须视为 malformed。

    :param caplog: pytest 日志捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 行为不符合预期时由 pytest 抛出。
    """

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.non_stream_parser"
    )
    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "answer"},
                }
            ],
            "usage": {
                "prompt_tokens": True,
                "completion_tokens": 2,
                "total_tokens": 3,
            },
        }
    ).encode("utf-8")

    events = list(
        parse_non_stream_response(
            payload, hook=make_no_thought_hook(), provider_request_id=None
        )
    )

    assert [event.type for event in events] == [
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.PROVIDER_DIAGNOSTIC,
        RunnerEventType.RUNNER_DONE,
    ]
    diagnostic = events[1].data
    assert isinstance(diagnostic, RunnerProviderDiagnosticData)
    assert diagnostic.diagnostic_code == "usage_field_malformed"
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.STOP
    assert RunnerEventType.RUNNER_USAGE_RECORDED not in {
        event.type for event in events
    }
    assert any(
        "usage_field_malformed" in record.getMessage()
        and "prompt_tokens_type=bool" in record.getMessage()
        for record in caplog.records
    )


def test_non_stream_negative_usage_logs_warning_and_omits_usage(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """usage token 计数必须非负，负数按 malformed usage 处理。"""

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.non_stream_parser"
    )
    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "answer"},
                }
            ],
            "usage": {
                "prompt_tokens": -1,
                "completion_tokens": 2,
                "total_tokens": 1,
            },
        }
    ).encode("utf-8")

    events = list(
        parse_non_stream_response(
            payload, hook=make_no_thought_hook(), provider_request_id=None
        )
    )

    assert [event.type for event in events] == [
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.PROVIDER_DIAGNOSTIC,
        RunnerEventType.RUNNER_DONE,
    ]
    diagnostic = events[1].data
    assert isinstance(diagnostic, RunnerProviderDiagnosticData)
    assert diagnostic.diagnostic_code == "usage_field_malformed"
    assert "usage_field_malformed" in caplog.text
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.STOP
    assert RunnerEventType.RUNNER_USAGE_RECORDED not in {
        event.type for event in events
    }
    assert any(
        "usage_field_malformed" in record.getMessage()
        and "prompt_tokens_type=int" in record.getMessage()
        for record in caplog.records
    )


def test_non_stream_invalid_finish_reason_fails_closed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """非流式未知 finish_reason 必须 fatal，不得回落 STOP。"""

    caplog.set_level(
        logging.WARNING, logger="dayu.engine.runners.openai.non_stream_parser"
    )
    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "safety_stop",
                    "message": {"role": "assistant", "content": "answer"},
                }
            ]
        }
    ).encode("utf-8")

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
    assert error.error_code == "non_stream_invalid_finish_reason"
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
    assert any(
        "non_stream_invalid_finish_reason" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "finish_reason_field",
    (
        {},
        {"finish_reason": None},
    ),
)
def test_non_stream_content_missing_or_null_finish_reason_fails_closed(
    finish_reason_field: dict[str, JsonValue],
) -> None:
    """content-only 非流式响应缺失或 null finish_reason 不得默认 STOP。

    :param finish_reason_field: 要合入 choice 的 finish_reason 字段片段。
    :returns: 无返回值。
    :raises AssertionError: 未按协议错误收口时由 pytest 抛出。
    """

    choice = {
        **finish_reason_field,
        "message": {"role": "assistant", "content": "answer"},
    }
    payload = json.dumps({"choices": [choice]}).encode("utf-8")

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
    assert error.error_code == "non_stream_missing_finish_reason"
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


def test_non_stream_choice_without_message_or_finish_reason_fails_closed() -> None:
    """单 choice 同时缺 message 与 finish_reason 时必须协议错误收口。"""

    payload = json.dumps({"choices": [{}]}).encode("utf-8")

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
    assert error.error_code == "non_stream_invalid_choice_shape"
    diagnostic = _diagnostic_payload(error.raw_payload)
    assert diagnostic["reason"] == "message_missing"
    done = events[1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR


def test_non_stream_tool_calls_emitted() -> None:
    """非流式响应中的 tool_calls 应转为 ToolCallsCompleted。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "I will call a tool.",
                        "reasoning_content": "tool thoughts",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "ping",
                                    "arguments": "{\"a\":1}",
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list((parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None)))
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert data.tool_calls[0].name == "ping"
    assert data.tool_calls[0].arguments == {"a": 1}
    assert data.content == "I will call a tool."
    assert data.reasoning_content == "tool thoughts"
    # 不应同时发出 ContentCompleted
    content_completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
    ]
    assert content_completed == []
    # Done 终态为 TOOL_CALLS
    done = [e for e in events if e.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.TOOL_CALLS


def test_non_stream_tool_calls_without_finish_reason_done_as_tool_calls() -> None:
    """非流式 tool_calls 缺 finish_reason 时与 SSE 路径一致收口为 TOOL_CALLS。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I will call a tool.",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "ping",
                                    "arguments": "{\"a\":1}",
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        parse_non_stream_response(
            payload, hook=make_no_thought_hook(), provider_request_id=None
        )
    )

    done = [event for event in events if event.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.TOOL_CALLS


def test_non_stream_tool_calls_with_stop_finish_reason_done_as_tool_calls() -> None:
    """provider 返回 tool_calls 但 finish_reason=stop 时 Done 仍为 TOOL_CALLS。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "I will call a tool.",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "ping",
                                    "arguments": "{\"a\":1}",
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        parse_non_stream_response(
            payload, hook=make_no_thought_hook(), provider_request_id=None
        )
    )

    done = [event for event in events if event.type is RunnerEventType.RUNNER_DONE]
    assert len(done) == 1
    assert isinstance(done[0].data, RunnerDoneData)
    assert done[0].data.finish_reason is FinishReason.TOOL_CALLS


def test_non_stream_tool_call_index_ignores_non_dict_elements() -> None:
    """非流式 tool_calls 的 index fallback 只按有效对象计数。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            None,
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "ping",
                                    "arguments": "{}",
                                },
                            },
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        parse_non_stream_response(
            payload, hook=make_no_thought_hook(), provider_request_id=None
        )
    )

    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert data.tool_calls[0].index_in_iteration == 0


def test_non_stream_all_non_dict_tool_calls_emit_protocol_error() -> None:
    """非流式 tool_calls 全部非法时逐项诊断，空结果仍 fatal。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [None, "bad"],
                    },
                }
            ]
        }
    ).encode("utf-8")

    events = list(
        parse_non_stream_response(
            payload,
            hook=make_no_thought_hook(),
            provider_request_id="req_bad_tool_calls",
        )
    )

    diagnostics: list[RunnerProviderDiagnosticData] = []
    protocol_errors: list[RunnerProtocolErrorData] = []
    for event in events:
        if event.type is RunnerEventType.PROVIDER_DIAGNOSTIC:
            diagnostic = event.data
            assert isinstance(diagnostic, RunnerProviderDiagnosticData)
            diagnostics.append(diagnostic)
        if event.type is RunnerEventType.PROVIDER_PROTOCOL_ERROR:
            data = event.data
            assert isinstance(data, RunnerProtocolErrorData)
            protocol_errors.append(data)
    assert len(diagnostics) == 2
    for diagnostic in diagnostics:
        assert diagnostic.provider_request_id == "req_bad_tool_calls"
        assert diagnostic.diagnostic_code == "non_stream_tool_call_not_object"
    assert len(protocol_errors) == 1
    for error in protocol_errors:
        assert error.provider_request_id == "req_bad_tool_calls"
    assert protocol_errors[0].error_code == "non_stream_tool_calls_empty_after_filter"
    assert events[-1].type is RunnerEventType.RUNNER_DONE
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.ERROR
