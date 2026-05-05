"""SSE parser 测试通用辅助。"""

from __future__ import annotations

from collections.abc import Sequence

from dayu.engine.contracts.runner_events import RunnerEvent
from dayu.engine.runners.openai._types import _ReasoningProtocolHook
from dayu.engine.runners.openai.sse_parser import SSEParser

from tests.engine.runners.openai._fakes import AsyncByteIter


def make_no_thought_hook() -> _ReasoningProtocolHook:
    """返回不剥离任何 XML 标签的 hook。"""

    return _ReasoningProtocolHook(tag_name=None)


def make_thought_hook() -> _ReasoningProtocolHook:
    """返回剥离 ``<thought>`` 的 hook。"""

    return _ReasoningProtocolHook(tag_name="thought")


async def parse_sse(
    chunks: Sequence[bytes],
    *,
    hook: _ReasoningProtocolHook | None = None,
) -> list[RunnerEvent]:
    """运行 SSE parser 并收集所有事件。

    :param chunks: 输入字节切片序列。
    :param hook: reasoning 协议钩子；为 ``None`` 默认无标签。
    :returns: 事件列表。
    """

    parser = SSEParser(hook=hook or make_no_thought_hook())
    events: list[RunnerEvent] = []
    async for event in parser.parse(AsyncByteIter(list(chunks))):
        events.append(event)
    return events


__all__ = ["parse_sse", "make_no_thought_hook", "make_thought_hook"]
