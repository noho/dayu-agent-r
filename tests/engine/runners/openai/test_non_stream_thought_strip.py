"""非流式响应 ``<thought>`` 标签剥离测试。

Gemini ``include_thoughts=True`` 协议下，``content`` 中的
``<thought>...</thought>`` 段必须由 reasoning hook 剥离到
``reasoning_content``。
"""

from __future__ import annotations

import json

from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerEventType,
)
from dayu.engine.runners.openai.non_stream_parser import (
    parse_non_stream_response,
)

from tests.engine.runners.openai._sse_helpers import make_thought_hook


def test_non_stream_strips_leading_thought_into_reasoning() -> None:
    """``<thought>...</thought>`` 出现在 ``content`` 开头 → 剥离到 reasoning。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "<thought>plan</thought>answer",
                    },
                }
            ]
        }
    ).encode("utf-8")
    events = list(
        parse_non_stream_response(payload, hook=make_thought_hook())
    )
    completed_events = [
        e for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
    ]
    assert len(completed_events) == 1
    completed = completed_events[0].data
    assert isinstance(completed, RunnerContentCompletedData)
    assert completed.content == "answer"
    assert completed.reasoning_content == "plan"


def test_non_stream_thought_preserves_existing_reasoning_content() -> None:
    """已有 ``reasoning_content`` 字段时，剥离结果应在前。

    OLD ``async_openai_runner.py`` 中 non-stream 合并顺序固定为
    ``extracted_reasoning + native_reasoning``，以与 SSE 路径
    （先处理 content 中的 ``<thought>`` 增量，再处理 ``reasoning_content``
    增量）保持等价。本测试守护该顺序。
    """

    payload = json.dumps(
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
    events = list(
        parse_non_stream_response(payload, hook=make_thought_hook())
    )
    completed = next(
        e.data for e in events
        if e.type is RunnerEventType.RUNNER_CONTENT_COMPLETED
    )
    assert isinstance(completed, RunnerContentCompletedData)
    assert completed.content == "final"
    assert completed.reasoning_content == "extraprior;"
