"""非流式 JSON 响应解析测试。"""

from __future__ import annotations

import json
import logging

import pytest

from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEventType,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)
from tests.engine.runners.openai._sse_helpers import make_no_thought_hook


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
    events = list((parse_non_stream_response(payload, hook=make_no_thought_hook(), provider_request_id=None)))
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
    assert completed.finish_reason is FinishReason.STOP

    usage = events[1].data
    assert isinstance(usage, RunnerUsageRecordedData)
    assert usage.total_tokens == 9

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

    assert [
        event.type for event in events
    ] == [
        RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerEventType.RUNNER_DONE,
    ]
    done = events[-1].data
    assert isinstance(done, RunnerDoneData)
    assert done.finish_reason is FinishReason.STOP
    assert any(
        "usage_field_malformed" in record.getMessage()
        and "prompt_tokens_type=bool" in record.getMessage()
        for record in caplog.records
    )


def test_non_stream_unknown_finish_reason_logs_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """非流式未知 finish_reason 保留 STOP 回落，同时记录诊断日志。"""

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

    completed = events[0].data
    assert isinstance(completed, RunnerContentCompletedData)
    assert completed.finish_reason is FinishReason.STOP
    assert any(
        "unknown_finish_reason" in record.getMessage()
        for record in caplog.records
    )


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
