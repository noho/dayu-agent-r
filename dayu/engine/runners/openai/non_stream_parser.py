"""非流式 JSON 响应解析。

部分 provider 在 ``stream=False`` / 不支持流式时会以
``Content-Type: application/json`` 一次性返回完整 chat completion。
本模块把该 JSON 响应归一为 :class:`RunnerEvent` 序列：

- ``choices[0].message.content`` 与 ``reasoning_content`` 合并为
  :class:`RunnerContentCompletedData`（无 tool_calls 时）。
  Gemini ``include_thoughts`` 协议下，``content`` 中的
  ``<thought>...</thought>`` 段会被剥离并并入 ``reasoning_content``。
- ``choices[0].message.tool_calls`` 解析为
  :class:`RunnerToolCallsCompletedData`（含 ``provider_state`` 还原）；
  fatal tool call 协议错误（缺 id / 缺 name / 非合法 JSON 对象 args）→
  :class:`RunnerProtocolErrorData` + :class:`RunnerDoneData(ERROR)`。
- ``usage`` 字段产出 :class:`RunnerUsageRecordedData`。
- 顶层无法解析或缺字段 → :class:`RunnerProtocolErrorData` +
  :class:`RunnerDoneData(ERROR)`。
- 终态以 :class:`RunnerDoneData(finish_reason)` 收口。
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallRequest
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerProtocolErrorData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.runners.openai._types import (
    _OpenAIToolCallDelta,
    _OpenAIToolCallFunction,
    _ReasoningProtocolHook,
)
from dayu.engine.runners.openai.tool_call_aggregator import ToolCallAggregator
from dayu.engine.runners.openai.xml_tag_extractor import (
    StreamingXMLTagExtractor,
)

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
}


def _make_event(data: RunnerEventData) -> RunnerEvent:
    """包装为 :class:`RunnerEvent`。"""

    occurred_at = datetime.now(tz=timezone.utc)
    type_map: dict[type, RunnerEventType] = {
        RunnerContentCompletedData: RunnerEventType.RUNNER_CONTENT_COMPLETED,
        RunnerToolCallsCompletedData: RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
        RunnerUsageRecordedData: RunnerEventType.RUNNER_USAGE_RECORDED,
        RunnerProtocolErrorData: RunnerEventType.PROVIDER_PROTOCOL_ERROR,
        RunnerDoneData: RunnerEventType.RUNNER_DONE,
    }
    return RunnerEvent(
        type=type_map[type(data)], data=data, occurred_at=occurred_at
    )


def parse_non_stream_response(
    payload: bytes, *, hook: _ReasoningProtocolHook
) -> Iterator[RunnerEvent]:
    """解析非流式 JSON 响应字节串。

    :param payload: 完整响应字节串。
    :param hook: provider 私有 reasoning 协议钩子；用于决定是否需要
        从 ``content`` 中剥离 ``<thought>`` 标签到 ``reasoning_content``。
    :returns: :class:`RunnerEvent` 同步迭代器（由 Runner 包装为
        异步流）。
    """

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        yield _make_event(
            RunnerProtocolErrorData(
                error_code="invalid_utf8",
                message=f"non-stream response not utf-8: {exc}",
                provider_request_id=None,
                raw_payload=None,
            )
        )
        yield _make_event(RunnerDoneData(finish_reason=FinishReason.ERROR))
        return
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        yield _make_event(
            RunnerProtocolErrorData(
                error_code="non_stream_invalid_json",
                message=f"non-stream response is not valid JSON: {exc}",
                provider_request_id=None,
                raw_payload=None,
            )
        )
        yield _make_event(RunnerDoneData(finish_reason=FinishReason.ERROR))
        return
    if not isinstance(parsed, dict):
        yield _make_event(
            RunnerProtocolErrorData(
                error_code="non_stream_payload_not_object",
                message="non-stream response top-level is not a JSON object",
                provider_request_id=None,
                raw_payload=None,
            )
        )
        yield _make_event(RunnerDoneData(finish_reason=FinishReason.ERROR))
        return
    yield from _emit_from_dict(parsed, hook=hook)


def _split_thought(
    content: str, *, hook: _ReasoningProtocolHook
) -> tuple[str, str]:
    """根据 hook 把 ``content`` 切分为标签外正文 / 标签内 reasoning。

    :param content: 完整字符串。
    :param hook: provider 私有 reasoning 协议钩子。
    :returns: ``(outside, inside)``。
    """

    extractor = StreamingXMLTagExtractor(tag_name=hook.tag_name)
    delta = extractor.feed(content)
    flush = extractor.flush()
    outside = delta.outside_text + flush.outside_text
    inside = delta.inside_text + flush.inside_text
    return outside, inside


def _emit_from_dict(
    parsed: dict[str, JsonValue], *, hook: _ReasoningProtocolHook
) -> Iterator[RunnerEvent]:
    """从顶层 JSON 对象产出事件序列。"""

    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        yield _make_event(
            RunnerProtocolErrorData(
                error_code="non_stream_missing_choices",
                message="non-stream response missing choices",
                provider_request_id=None,
                raw_payload=None,
            )
        )
        yield _make_event(RunnerDoneData(finish_reason=FinishReason.ERROR))
        return
    choice = choices[0]
    if not isinstance(choice, dict):
        yield _make_event(
            RunnerProtocolErrorData(
                error_code="non_stream_choice_not_object",
                message="non-stream choice is not a JSON object",
                provider_request_id=None,
                raw_payload=None,
            )
        )
        yield _make_event(RunnerDoneData(finish_reason=FinishReason.ERROR))
        return
    finish_reason = _resolve_finish_reason(choice)
    message = choice.get("message")
    tool_calls_emitted = False
    fatal_emitted = False
    content: str | None = None
    reasoning: str | None = None
    if isinstance(message, dict):
        raw_content = message.get("content")
        if isinstance(raw_content, str):
            content = raw_content
        raw_reasoning = message.get("reasoning_content")
        if isinstance(raw_reasoning, str):
            reasoning = raw_reasoning
        if content is not None:
            outside, inside = _split_thought(content, hook=hook)
            content = outside or None
            if inside:
                reasoning = (reasoning or "") + inside
        raw_tool_calls = message.get("tool_calls")
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            tool_calls_request = _build_tool_calls(raw_tool_calls)
            for warning in tool_calls_request.warnings:
                yield _make_event(warning)
            if tool_calls_request.fatal_errors:
                for fatal in tool_calls_request.fatal_errors:
                    yield _make_event(fatal)
                yield _make_event(
                    RunnerDoneData(finish_reason=FinishReason.ERROR)
                )
                return
            yield _make_event(
                RunnerToolCallsCompletedData(
                    tool_calls=tool_calls_request.tool_calls
                )
            )
            tool_calls_emitted = True
    if not tool_calls_emitted and not fatal_emitted:
        yield _make_event(
            RunnerContentCompletedData(
                content=content,
                reasoning_content=reasoning,
                finish_reason=finish_reason,
            )
        )
    usage = parsed.get("usage")
    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if (
            isinstance(prompt_tokens, int)
            and isinstance(completion_tokens, int)
            and isinstance(total_tokens, int)
        ):
            yield _make_event(
                RunnerUsageRecordedData(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            )
    yield _make_event(RunnerDoneData(finish_reason=finish_reason))


def _resolve_finish_reason(choice: dict[str, JsonValue]) -> FinishReason:
    """把 choice 的 ``finish_reason`` 字段映射为枚举。"""

    raw = choice.get("finish_reason")
    if isinstance(raw, str):
        mapped = _FINISH_REASON_MAP.get(raw)
        if mapped is not None:
            return mapped
    return FinishReason.STOP


@dataclass(frozen=True, slots=True)
class _NonStreamToolCallsResult:
    """non-stream tool calls 解析结果。"""

    tool_calls: tuple[ToolCallRequest, ...]
    fatal_errors: tuple[RunnerProtocolErrorData, ...]
    warnings: tuple[RunnerProtocolErrorData, ...]


def _build_tool_calls(
    raw_tool_calls: list[JsonValue],
) -> _NonStreamToolCallsResult:
    """非流式 tool_calls 转 :class:`ToolCallRequest` 元组。

    复用 :class:`ToolCallAggregator`：把每个 tool call 当作一次
    完整的 delta 投喂，再调用 finalize。
    """

    aggregator = ToolCallAggregator()
    for index, raw in enumerate(raw_tool_calls):
        if not isinstance(raw, dict):
            continue
        delta = _coerce_final_tool_call(raw, index=index)
        aggregator.feed(delta)
    result = aggregator.finalize()
    return _NonStreamToolCallsResult(
        tool_calls=result.tool_calls,
        fatal_errors=result.fatal_errors,
        warnings=result.warnings,
    )


def _coerce_final_tool_call(
    raw: dict[str, JsonValue], *, index: int
) -> _OpenAIToolCallDelta:
    """把非流式 tool call dict 转成可被聚合器消费的 delta 形态。

    本函数返回 :class:`_OpenAIToolCallDelta`（与
    :class:`_OpenAIToolCallFinal` 在 aggregator 入口共享同一字段子集），
    并强制写入 ``index``，使 :class:`ToolCallAggregator` 可按顺序聚合。
    """

    delta: _OpenAIToolCallDelta = {"index": index}
    delta_id = raw.get("id")
    if isinstance(delta_id, str):
        delta["id"] = delta_id
    delta_type = raw.get("type")
    if isinstance(delta_type, str):
        delta["type"] = delta_type
    function = raw.get("function")
    if isinstance(function, dict):
        func_payload: _OpenAIToolCallFunction = {}
        name = function.get("name")
        if isinstance(name, str):
            func_payload["name"] = name
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            func_payload["arguments"] = arguments
        if func_payload:
            delta["function"] = func_payload
    extra_content = raw.get("extra_content")
    if isinstance(extra_content, dict):
        cleaned: dict[str, Mapping[str, JsonValue]] = {}
        for namespace, inner in extra_content.items():
            if isinstance(inner, dict):
                cleaned[namespace] = dict(inner)
        if cleaned:
            delta["extra_content"] = cleaned
    return delta


__all__ = ["parse_non_stream_response"]
