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
import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeAlias, assert_never

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallRequest
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
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
from dayu.engine.runners.openai.diagnostic_payload import (
    provider_error_diagnostic_payload,
)
from dayu.engine.runners.openai.tool_call_aggregator import ToolCallAggregator
from dayu.engine.runners.openai.usage import coerce_usage
from dayu.engine.runners.openai.xml_tag_extractor import (
    StreamingXMLTagExtractor,
)

_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
}

_LOGGER: logging.Logger = logging.getLogger(__name__)
_ERROR_FIELD: str = "error"
_ERROR_MESSAGE_FIELD: str = "message"
_INVALID_UTF8_CODE: str = "invalid_utf8"
_INVALID_JSON_CODE: str = "non_stream_invalid_json"
_PAYLOAD_NOT_OBJECT_CODE: str = "non_stream_payload_not_object"
_MISSING_CHOICES_CODE: str = "non_stream_missing_choices"
_CHOICE_NOT_OBJECT_CODE: str = "non_stream_choice_not_object"
_PROVIDER_ERROR_CODE: str = "non_stream_provider_error"
_TOOL_CALL_NOT_OBJECT_CODE: str = "non_stream_tool_call_not_object"
_TOOL_CALLS_EMPTY_AFTER_FILTER_CODE: str = "non_stream_tool_calls_empty_after_filter"
_TOOL_CALL_ARGUMENTS_NOT_OBJECT_CODE: str = "tool_call_arguments_not_object"

_NonStreamRunnerEventData: TypeAlias = (
    RunnerContentCompletedData
    | RunnerToolCallsCompletedData
    | RunnerUsageRecordedData
    | RunnerProtocolErrorData
    | RunnerDoneData
)


def _make_event(data: _NonStreamRunnerEventData) -> RunnerEvent:
    """包装为 :class:`RunnerEvent`。

    :param data: Runner 事件载荷。
    :returns: 带当前 UTC 时间戳的 :class:`RunnerEvent`。
    """

    occurred_at = datetime.now(tz=timezone.utc)
    match data:
        case RunnerContentCompletedData():
            event_type = RunnerEventType.RUNNER_CONTENT_COMPLETED
        case RunnerToolCallsCompletedData():
            event_type = RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
        case RunnerUsageRecordedData():
            event_type = RunnerEventType.RUNNER_USAGE_RECORDED
        case RunnerProtocolErrorData():
            event_type = RunnerEventType.PROVIDER_PROTOCOL_ERROR
        case RunnerDoneData():
            event_type = RunnerEventType.RUNNER_DONE
        case _:
            assert_never(data)
    return RunnerEvent(type=event_type, data=data, occurred_at=occurred_at)


def parse_non_stream_response(
    payload: bytes,
    *,
    hook: _ReasoningProtocolHook,
    provider_request_id: str | None,
) -> Iterator[RunnerEvent]:
    """解析非流式 JSON 响应字节串。

    :param payload: 完整响应字节串。
    :param hook: provider 私有 reasoning 协议钩子；用于决定是否需要
        从 ``content`` 中剥离 ``<thought>`` 标签到 ``reasoning_content``。
    :param provider_request_id: 当前 response header 提供的 request id。
    :returns: :class:`RunnerEvent` 同步迭代器（由 Runner 包装为
        异步流）。
    """

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        _LOGGER.warning(
            "non_stream.protocol_error code=%s detail=%s",
            _INVALID_UTF8_CODE,
            exc.__class__.__name__,
        )
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=_INVALID_UTF8_CODE,
                message=f"non-stream response not utf-8: {exc}",
                provider_request_id=provider_request_id,
                raw_payload=None,
            )
        )
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=provider_request_id,
            )
        )
        return
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        _LOGGER.warning(
            "non_stream.protocol_error code=%s detail=%s",
            _INVALID_JSON_CODE,
            exc.__class__.__name__,
        )
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=_INVALID_JSON_CODE,
                message=f"non-stream response is not valid JSON: {exc}",
                provider_request_id=provider_request_id,
                raw_payload=None,
            )
        )
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=provider_request_id,
            )
        )
        return
    if not isinstance(parsed, dict):
        _LOGGER.warning(
            "non_stream.protocol_error code=%s",
            _PAYLOAD_NOT_OBJECT_CODE,
        )
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=_PAYLOAD_NOT_OBJECT_CODE,
                message="non-stream response top-level is not a JSON object",
                provider_request_id=provider_request_id,
                raw_payload=None,
            )
        )
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=provider_request_id,
            )
        )
        return
    yield from _emit_from_dict(
        parsed, hook=hook, provider_request_id=provider_request_id
    )


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
    parsed: dict[str, JsonValue],
    *,
    hook: _ReasoningProtocolHook,
    provider_request_id: str | None,
) -> Iterator[RunnerEvent]:
    """从顶层 JSON 对象产出事件序列。

    :param parsed: 已解析的非流式响应 JSON object。
    :param hook: provider 私有 reasoning 协议钩子。
    :param provider_request_id: 当前 response header 提供的 request id。
    :returns: 归一化后的 Runner 事件迭代器。
    :raises Exception: 不主动抛出异常。
    """

    if _ERROR_FIELD in parsed:
        _LOGGER.warning(
            "non_stream.protocol_error code=%s", _PROVIDER_ERROR_CODE
        )
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=_PROVIDER_ERROR_CODE,
                message=_provider_error_message(parsed[_ERROR_FIELD]),
                provider_request_id=provider_request_id,
                raw_payload=provider_error_diagnostic_payload(
                    parsed,
                    source=_PROVIDER_ERROR_CODE,
                ),
            )
        )
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=provider_request_id,
            )
        )
        return

    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=_MISSING_CHOICES_CODE,
                message="non-stream response missing choices",
                provider_request_id=provider_request_id,
                raw_payload=None,
            )
        )
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=provider_request_id,
            )
        )
        return
    choice = choices[0]
    if not isinstance(choice, dict):
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=_CHOICE_NOT_OBJECT_CODE,
                message="non-stream choice is not a JSON object",
                provider_request_id=provider_request_id,
                raw_payload=None,
            )
        )
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=provider_request_id,
            )
        )
        return
    finish_reason = _resolve_finish_reason(choice)
    message = choice.get("message")
    tool_calls_emitted = False
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
                # OLD `extracted_reasoning + native_reasoning` 顺序：
                # 剥离的 ``<thought>`` 在前，provider 原生 reasoning 在后，
                # 与 SSE 路径（先处理 content 流再处理 reasoning_content
                # 流）保持等价。
                reasoning = inside + (reasoning or "")
        raw_tool_calls = message.get("tool_calls")
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            tool_calls_request = _build_tool_calls(
                raw_tool_calls, provider_request_id=provider_request_id
            )
            for warning in tool_calls_request.warnings:
                yield _make_event(warning)
            if tool_calls_request.fatal_errors:
                for fatal in tool_calls_request.fatal_errors:
                    yield _make_event(fatal)
                yield _make_event(
                    RunnerDoneData(
                        finish_reason=FinishReason.ERROR,
                        provider_request_id=provider_request_id,
                    )
                )
                return
            yield _make_event(
                RunnerToolCallsCompletedData(
                    tool_calls=tool_calls_request.tool_calls,
                    content=content,
                    reasoning_content=reasoning,
                )
            )
            tool_calls_emitted = True
    if not tool_calls_emitted:
        yield _make_event(
            RunnerContentCompletedData(
                content=content,
                reasoning_content=reasoning,
                finish_reason=finish_reason,
            )
        )
    usage = parsed.get("usage")
    if isinstance(usage, dict):
        normalized = coerce_usage(usage)
        if normalized is None:
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
            _LOGGER.warning(
                "non_stream.protocol_diagnostic code=usage_field_malformed "
                "prompt_tokens_type=%s completion_tokens_type=%s "
                "total_tokens_type=%s",
                type(prompt_tokens).__name__,
                type(completion_tokens).__name__,
                type(total_tokens).__name__,
            )
        else:
            yield _make_event(
                RunnerUsageRecordedData(
                    prompt_tokens=normalized.prompt_tokens,
                    completion_tokens=normalized.completion_tokens,
                    total_tokens=normalized.total_tokens,
                )
            )
    if tool_calls_emitted:
        finish_reason = FinishReason.TOOL_CALLS
    yield _make_event(
        RunnerDoneData(
            finish_reason=finish_reason,
            provider_request_id=provider_request_id,
        )
    )


def _provider_error_message(error_payload: JsonValue) -> str:
    """从 provider error payload 中提取有界错误摘要。

    :param error_payload: provider 返回的 ``error`` 字段。
    :returns: 人类可读错误摘要。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(error_payload, str) and error_payload.strip() != "":
        return error_payload
    if isinstance(error_payload, dict):
        message = error_payload.get(_ERROR_MESSAGE_FIELD)
        if isinstance(message, str) and message.strip() != "":
            return message
    return "non-stream provider returned an error object"


def _resolve_finish_reason(choice: dict[str, JsonValue]) -> FinishReason:
    """把 choice 的 ``finish_reason`` 字段映射为枚举。

    :param choice: 非流式响应中的单个 choice object。
    :returns: 映射后的 :class:`FinishReason`；缺失或未知时返回 ``STOP``。
    :raises Exception: 不主动抛出异常。
    """

    raw = choice.get("finish_reason")
    if isinstance(raw, str):
        mapped = _FINISH_REASON_MAP.get(raw)
        if mapped is not None:
            return mapped
        _LOGGER.warning(
            "non_stream.protocol_diagnostic code=unknown_finish_reason "
            "finish_reason=%s",
            raw,
        )
    return FinishReason.STOP


@dataclass(frozen=True, slots=True)
class _NonStreamToolCallsResult:
    """non-stream tool calls 解析结果。

    :param tool_calls: 成功归一化的工具调用元组。
    :param fatal_errors: 阻止成功收口的 fatal 协议错误。
    :param warnings: 可恢复的协议告警事件。
    """

    tool_calls: tuple[ToolCallRequest, ...]
    fatal_errors: tuple[RunnerProtocolErrorData, ...]
    warnings: tuple[RunnerProtocolErrorData, ...]


def _build_tool_calls(
    raw_tool_calls: list[JsonValue],
    *,
    provider_request_id: str | None,
) -> _NonStreamToolCallsResult:
    """非流式 tool_calls 转 :class:`ToolCallRequest` 元组。

    复用 :class:`ToolCallAggregator`：把每个 tool call 当作一次
    完整的 delta 投喂，再调用 finalize。

    OLD 兼容点：non-stream ``function.arguments`` 既可能是 JSON string
    也可能是 dict 形态。OLD 直接接受 dict；NEW 在喂入 aggregator
    （只接受字符串 buffer）前先把 Mapping 序列化为 JSON string。
    其它非法类型（list / number / bool）→ ``tool_call_arguments_not_object``
    fatal 错误。

    :param raw_tool_calls: provider 返回的原始 tool_calls 列表。
    :param provider_request_id: 当前 response header 提供的 request id。
    :returns: 工具调用解析结果、fatal 错误与 warning。
    :raises Exception: 不主动抛出异常。
    """

    aggregator = ToolCallAggregator(provider_request_id=provider_request_id)
    fatal_errors: list[RunnerProtocolErrorData] = []
    warnings: list[RunnerProtocolErrorData] = []
    index = 0
    valid_raw_count = 0
    for position, raw in enumerate(raw_tool_calls):
        if not isinstance(raw, dict):
            warnings.append(
                RunnerProtocolErrorData(
                    error_code=_TOOL_CALL_NOT_OBJECT_CODE,
                    message=f"non-stream tool_calls[{position}] is not a JSON object",
                    provider_request_id=provider_request_id,
                    raw_payload=None,
                )
            )
            continue
        valid_raw_count += 1
        delta, pre_error = _coerce_final_tool_call(
            raw, index=index, provider_request_id=provider_request_id
        )
        index += 1
        if pre_error is not None:
            fatal_errors.append(pre_error)
            continue
        aggregator.feed(delta)
    result = aggregator.finalize()
    combined_fatals: tuple[RunnerProtocolErrorData, ...] = (
        tuple(fatal_errors) + result.fatal_errors
    )
    if valid_raw_count == 0:
        combined_fatals = combined_fatals + (
            RunnerProtocolErrorData(
                error_code=_TOOL_CALLS_EMPTY_AFTER_FILTER_CODE,
                message="non-stream tool_calls contained no JSON object entries",
                provider_request_id=provider_request_id,
                raw_payload=None,
            ),
        )
    return _NonStreamToolCallsResult(
        tool_calls=result.tool_calls,
        fatal_errors=combined_fatals,
        warnings=tuple(warnings) + result.warnings,
    )


def _coerce_final_tool_call(
    raw: dict[str, JsonValue],
    *,
    index: int,
    provider_request_id: str | None,
) -> tuple[_OpenAIToolCallDelta, RunnerProtocolErrorData | None]:
    """把非流式 tool call dict 转成可被聚合器消费的 delta 形态。

    本函数返回 ``(delta, pre_error)``：

    - ``delta``：投喂 :class:`ToolCallAggregator` 的强类型形态；
    - ``pre_error``：若发现 ``function.arguments`` 既不是字符串也不是
      JSON object，返回 ``tool_call_arguments_not_object`` fatal 协议
      错误；否则为 ``None``。

    OLD 兼容：``function.arguments`` 为 :class:`Mapping` 时序列化为
    JSON 字符串，避免参数被静默清空。

    :param raw: provider 返回的单个 tool call object。
    :param index: 当前 tool call 在列表中的位置。
    :param provider_request_id: 当前 response header 提供的 request id。
    :returns: 可投喂聚合器的 delta，以及预解析阶段发现的 fatal 错误。
    :raises Exception: 不主动抛出异常。
    """

    delta: _OpenAIToolCallDelta = {"index": index}
    delta_id = raw.get("id")
    if isinstance(delta_id, str):
        delta["id"] = delta_id
    delta_type = raw.get("type")
    if isinstance(delta_type, str):
        delta["type"] = delta_type
    pre_error: RunnerProtocolErrorData | None = None
    function = raw.get("function")
    if isinstance(function, dict):
        func_payload: _OpenAIToolCallFunction = {}
        name = function.get("name")
        if isinstance(name, str):
            func_payload["name"] = name
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            func_payload["arguments"] = arguments
        elif isinstance(arguments, Mapping):
            # OLD 行为：dict 形态参数直接保留；序列化为 JSON 字符串
            # 后让 aggregator 沿用统一字符串 buffer 入口。
            func_payload["arguments"] = json.dumps(dict(arguments))
        elif arguments is not None:
            tool_id_for_msg = (
                delta_id if isinstance(delta_id, str) else f"#{index}"
            )
            pre_error = RunnerProtocolErrorData(
                error_code=_TOOL_CALL_ARGUMENTS_NOT_OBJECT_CODE,
                message=(
                    f"tool call {tool_id_for_msg} arguments is neither a "
                    "JSON string nor a JSON object"
                ),
                provider_request_id=provider_request_id,
                raw_payload=None,
            )
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
    return delta, pre_error


__all__ = ["parse_non_stream_response"]
