"""非流式 JSON 响应解析测试。"""

from __future__ import annotations

import json

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
    events = list(parse_non_stream_response(payload, hook=make_no_thought_hook()))
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


def test_non_stream_tool_calls_emitted() -> None:
    """非流式响应中的 tool_calls 应转为 ToolCallsCompleted。"""

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
    events = list(parse_non_stream_response(payload, hook=make_no_thought_hook()))
    completed = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
    ]
    assert len(completed) == 1
    data = completed[0].data
    assert isinstance(data, RunnerToolCallsCompletedData)
    assert data.tool_calls[0].name == "ping"
    assert data.tool_calls[0].arguments == {"a": 1}
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
