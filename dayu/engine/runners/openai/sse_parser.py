"""SSE 流解析与事件归一。

本模块把 OpenAI 兼容 chat completion 流式协议（SSE）的字节流归一
为 :class:`RunnerEvent` 序列，承载以下职责：

- 行级 SSE 缓冲：累积 ``\\n`` 边界，处理多行 ``data:`` 聚合，识别
  ``[DONE]`` 终止符与尾部无换行残留。
- 增量分发：``content`` / ``reasoning_content`` / ``tool_calls``。
- ``<thought>`` 标签剥离（由
  :class:`StreamingXMLTagExtractor` 钩子驱动）。
- ``tool_calls`` 增量聚合（委派
  :class:`~dayu.engine.runners.openai.tool_call_aggregator.ToolCallAggregator`）。
- ``usage`` 字段归一（仅当出现时产出
  :class:`RunnerUsageRecordedData`）。
- 终态收口：成功 → :class:`RunnerContentCompletedData` /
  :class:`RunnerToolCallsCompletedData` + :class:`RunnerDoneData`；
  协议错误 / 非法 UTF-8 → :class:`RunnerProtocolErrorData` +
  :class:`RunnerDoneData(ERROR)`。

Phase 1 不引入会话级状态：本类对单次 :meth:`AsyncRunner.call` 调用
新建一次实例。
"""

from __future__ import annotations

import base64
import codecs
import json
import logging
from collections.abc import AsyncIterable, AsyncIterator
from datetime import datetime, timezone

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerProtocolErrorData,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.runners.openai._types import (
    _OpenAIToolCallDelta,
    _OpenAIToolCallFunction,
    _ReasoningProtocolHook,
)
from dayu.engine.runners.openai.tool_call_aggregator import (
    ToolCallAggregator,
    _is_tool_call_index,
)
from dayu.engine.runners.openai.usage import coerce_usage
from dayu.engine.runners.openai.xml_tag_extractor import (
    StreamingXMLTagExtractor,
)

_DONE_TOKEN: str = "[DONE]"
_DATA_PREFIX: str = "data:"
_LOGGER: logging.Logger = logging.getLogger(__name__)
_ERROR_FIELD: str = "error"
_ERROR_MESSAGE_FIELD: str = "message"
_MISSING_CHOICES_CODE: str = "sse_missing_choices"
_PROVIDER_ERROR_CODE: str = "sse_provider_error"
_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "content_filter": FinishReason.CONTENT_FILTER,
}


def _make_event(data: RunnerEventData) -> RunnerEvent:
    """把事件 data 包装为 :class:`RunnerEvent`。

    :param data: Runner 事件载荷。
    :returns: 带当前 UTC 时间戳的 :class:`RunnerEvent`。
    :raises AssertionError: 当 ``data`` 不是 SSE parser 支持的事件载荷时抛出。
    """

    occurred_at = datetime.now(tz=timezone.utc)
    type_ = _event_type_for(data)
    return RunnerEvent(type=type_, data=data, occurred_at=occurred_at)


def _event_type_for(data: RunnerEventData) -> RunnerEventType:
    """根据 data 类型返回对应的 :class:`RunnerEventType`。

    :param data: Runner 事件载荷。
    :returns: 对应的 :class:`RunnerEventType`。
    :raises AssertionError: 当 ``data`` 不属于 SSE parser 可产出的载荷类型时抛出。
    """

    match data:
        case RunnerContentDeltaData():
            return RunnerEventType.RUNNER_CONTENT_DELTA
        case RunnerReasoningDeltaData():
            return RunnerEventType.RUNNER_REASONING_DELTA
        case RunnerToolCallDeltaData():
            return RunnerEventType.RUNNER_TOOL_CALL_DELTA
        case RunnerToolCallsCompletedData():
            return RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED
        case RunnerContentCompletedData():
            return RunnerEventType.RUNNER_CONTENT_COMPLETED
        case RunnerUsageRecordedData():
            return RunnerEventType.RUNNER_USAGE_RECORDED
        case RunnerProtocolErrorData():
            return RunnerEventType.PROVIDER_PROTOCOL_ERROR
        case RunnerDoneData():
            return RunnerEventType.RUNNER_DONE
        # RunnerHTTPErrorData 由 runner.py 层产生，不会进本路径。
        case _:
            # 不应发生：上方已穷尽 SSE parser 可产出的类型。
            raise AssertionError(f"unexpected event data type for SSE parser: {type(data)!r}")


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
    return "SSE provider returned an error object"


class SSEParser:
    """SSE 流解析器。

    :param hook: provider 私有 reasoning 协议钩子。
    :param provider_request_id: 当前 response header 提供的 request id。
    """

    def __init__(
        self,
        *,
        hook: _ReasoningProtocolHook,
        provider_request_id: str | None,
    ) -> None:
        self._extractor = StreamingXMLTagExtractor(tag_name=hook.tag_name)
        self._provider_request_id: str | None = provider_request_id
        self._aggregator = ToolCallAggregator(provider_request_id=provider_request_id)
        self._content_buffer: list[str] = []
        self._reasoning_buffer: list[str] = []
        self._finish_reason: FinishReason | None = None
        self._line_carry: str = ""
        self._data_lines: list[str] = []
        self._terminated: bool = False
        self._tool_calls_seen: bool = False
        self._utf8_decoder: codecs.IncrementalDecoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")

    async def parse(self, byte_stream: AsyncIterable[bytes]) -> AsyncIterator[RunnerEvent]:
        """解析 ``byte_stream``，产出 :class:`RunnerEvent` 序列。

        :param byte_stream: SSE 字节流（每次 yield 一个 chunk）。
        :returns: :class:`RunnerEvent` 异步迭代器。
        """

        async for chunk in byte_stream:
            if self._terminated:
                break
            try:
                text = self._utf8_decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                async for event in self._handle_invalid_utf8(chunk, final_decode=False):
                    yield event
                return
            self._line_carry += text
            while True:
                newline_index = self._line_carry.find("\n")
                if newline_index == -1:
                    break
                line = self._line_carry[:newline_index]
                self._line_carry = self._line_carry[newline_index + 1 :]
                async for event in self._consume_line(line):
                    yield event
                if self._terminated:
                    break
        if self._terminated:
            return
        try:
            tail = self._utf8_decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            async for event in self._handle_invalid_utf8(b"", final_decode=True):
                yield event
            return
        if tail:
            self._line_carry += tail
        if self._line_carry:
            async for event in self._consume_line(self._line_carry):
                yield event
            self._line_carry = ""
            if self._terminated:
                return
        if self._data_lines:
            async for event in self._dispatch_event_payload():
                yield event
            if self._terminated:
                return
        async for event in self._finalize_success():
            yield event

    async def _handle_invalid_utf8(self, chunk: bytes, *, final_decode: bool) -> AsyncIterator[RunnerEvent]:
        """非法 UTF-8 chunk → 协议错误 + Done(ERROR) 收口。

        :param chunk: 触发解码失败的当前字节片段；final flush 失败时为空。
        :param final_decode: 是否发生在流尾 flush 阶段。
        :returns: 协议错误与 Done(ERROR) 事件。
        """

        error_code = "truncated_utf8_tail" if final_decode else "invalid_utf8"
        message = (
            "SSE stream ended with an incomplete UTF-8 sequence"
            if final_decode
            else "failed to decode SSE chunk as UTF-8"
        )
        _LOGGER.warning(
            "sse.protocol_error code=%s chunk_len=%d",
            error_code,
            len(chunk),
        )
        encoded = base64.b64encode(chunk).decode("ascii")
        raw_payload: JsonValue = {"chunk_base64": encoded, "final_decode": final_decode}
        yield _make_event(
            RunnerProtocolErrorData(
                error_code=error_code,
                message=message,
                provider_request_id=self._provider_request_id,
                raw_payload=raw_payload,
                partial_tool_calls=self._aggregator.partial_summaries(),
            )
        )
        self._terminated = True
        yield _make_event(
            RunnerDoneData(
                finish_reason=FinishReason.ERROR,
                provider_request_id=self._provider_request_id,
            )
        )

    async def _consume_line(self, line: str) -> AsyncIterator[RunnerEvent]:
        """处理一条 SSE 行。"""

        stripped = line.rstrip("\r")
        if stripped == "":
            if self._data_lines:
                async for event in self._dispatch_event_payload():
                    yield event
            return
        if stripped.startswith(_DATA_PREFIX):
            payload = stripped[len(_DATA_PREFIX) :].lstrip(" ")
            self._data_lines.append(payload)
            return
        # 其它字段（``event:`` / ``id:`` / 注释 ``:`` 等）忽略。

    async def _dispatch_event_payload(self) -> AsyncIterator[RunnerEvent]:
        """组装多行 ``data:`` 为单一 JSON 对象，分发到具体 handler。"""

        joined = "\n".join(self._data_lines)
        self._data_lines.clear()
        if joined.strip() == _DONE_TOKEN:
            _LOGGER.debug("sse.done_token received")
            async for event in self._finalize_success():
                yield event
            return
        try:
            parsed = json.loads(joined)
        except json.JSONDecodeError as exc:
            _LOGGER.warning(
                "sse.protocol_error code=sse_invalid_json detail=%s",
                exc.__class__.__name__,
            )
            yield _make_event(
                RunnerProtocolErrorData(
                    error_code="sse_invalid_json",
                    message=f"SSE data line is not valid JSON: {exc}",
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self._aggregator.partial_summaries(),
                )
            )
            self._terminated = True
            yield _make_event(
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id=self._provider_request_id,
                )
            )
            return
        if not isinstance(parsed, dict):
            yield _make_event(
                RunnerProtocolErrorData(
                    error_code="sse_payload_not_object",
                    message="SSE data line is not a JSON object",
                    provider_request_id=self._provider_request_id,
                    raw_payload=None,
                    partial_tool_calls=self._aggregator.partial_summaries(),
                )
            )
            self._terminated = True
            yield _make_event(
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id=self._provider_request_id,
                )
            )
            return
        async for event in self._handle_chunk_object(parsed):
            yield event

    async def _handle_chunk_object(self, parsed: dict[str, JsonValue]) -> AsyncIterator[RunnerEvent]:
        """处理单个解析后的 SSE chunk JSON 对象。

        :param parsed: 已解析的 SSE JSON object。
        :returns: 归一化后的 Runner 事件异步迭代器。
        :raises Exception: 不主动抛出异常。
        """

        if _ERROR_FIELD in parsed:
            _LOGGER.warning("sse.protocol_error code=%s", _PROVIDER_ERROR_CODE)
            self._terminated = True
            yield _make_event(
                RunnerProtocolErrorData(
                    error_code=_PROVIDER_ERROR_CODE,
                    message=_provider_error_message(parsed[_ERROR_FIELD]),
                    provider_request_id=self._provider_request_id,
                    raw_payload=dict(parsed),
                    partial_tool_calls=self._aggregator.partial_summaries(),
                )
            )
            yield _make_event(
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id=self._provider_request_id,
                )
            )
            return

        choices = parsed.get("choices")
        usage = parsed.get("usage")
        has_valid_choices = isinstance(choices, list) and len(choices) > 0
        has_valid_usage = isinstance(usage, dict)
        if not has_valid_choices and not has_valid_usage:
            _LOGGER.warning(
                "sse.protocol_error code=%s choices_type=%s usage_type=%s",
                _MISSING_CHOICES_CODE,
                type(choices).__name__,
                type(usage).__name__,
            )
            self._terminated = True
            yield _make_event(
                RunnerProtocolErrorData(
                    error_code=_MISSING_CHOICES_CODE,
                    message=("SSE data line must contain non-empty choices or " "valid usage"),
                    provider_request_id=self._provider_request_id,
                    raw_payload=dict(parsed),
                    partial_tool_calls=self._aggregator.partial_summaries(),
                )
            )
            yield _make_event(
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id=self._provider_request_id,
                )
            )
            return
        if isinstance(choices, list) and choices:
            handled_choice = False
            for index, choice in enumerate(choices):
                if not isinstance(choice, dict):
                    _LOGGER.warning(
                        "sse.protocol_diagnostic " "code=sse_choice_not_object index=%d type=%s",
                        index,
                        type(choice).__name__,
                    )
                    continue
                handled_choice = True
                async for event in self._handle_choice(choice):
                    yield event
            if not handled_choice:
                _LOGGER.warning(
                    "sse.protocol_error code=%s choices_type=list " "valid_choice_count=0",
                    _MISSING_CHOICES_CODE,
                )
                self._terminated = True
                yield _make_event(
                    RunnerProtocolErrorData(
                        error_code=_MISSING_CHOICES_CODE,
                        message="SSE data line choices must contain an object choice",
                        provider_request_id=self._provider_request_id,
                        raw_payload=dict(parsed),
                        partial_tool_calls=self._aggregator.partial_summaries(),
                    )
                )
                yield _make_event(
                    RunnerDoneData(
                        finish_reason=FinishReason.ERROR,
                        provider_request_id=self._provider_request_id,
                    )
                )
                return
        if usage is not None and isinstance(usage, dict):
            async for event in self._handle_usage(usage):
                yield event

    async def _handle_choice(self, choice: dict[str, JsonValue]) -> AsyncIterator[RunnerEvent]:
        """处理单个 choice 对象。"""

        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str) and content:
                extraction = self._extractor.feed(content)
                if extraction.outside_text:
                    self._content_buffer.append(extraction.outside_text)
                    yield _make_event(RunnerContentDeltaData(delta=extraction.outside_text))
                if extraction.inside_text:
                    self._reasoning_buffer.append(extraction.inside_text)
                    yield _make_event(RunnerReasoningDeltaData(delta=extraction.inside_text))
            reasoning = delta.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                self._reasoning_buffer.append(reasoning)
                yield _make_event(RunnerReasoningDeltaData(delta=reasoning))
            tool_calls_delta = delta.get("tool_calls")
            if isinstance(tool_calls_delta, list):
                self._tool_calls_seen = True
                position = 0
                for raw in tool_calls_delta:
                    if not isinstance(raw, dict):
                        continue
                    typed_delta = self._coerce_tool_call_delta(raw)
                    resolved_index = self._aggregator.feed(typed_delta, position=position)
                    position += 1
                    event_data = self._tool_call_delta_event(typed_delta, resolved_index=resolved_index)
                    if event_data is not None:
                        yield _make_event(event_data)
        finish_reason = choice.get("finish_reason")
        if isinstance(finish_reason, str):
            mapped = _FINISH_REASON_MAP.get(finish_reason)
            if mapped is not None:
                self._finish_reason = mapped
            else:
                _LOGGER.warning(
                    "sse.protocol_diagnostic code=unknown_finish_reason " "finish_reason=%s",
                    finish_reason,
                )

    def _coerce_tool_call_delta(self, raw: dict[str, JsonValue]) -> _OpenAIToolCallDelta:
        """把原始 dict 转成强类型 :class:`_OpenAIToolCallDelta`。

        非 schema 字段一律忽略；类型不匹配的字段不写入。
        """

        delta: _OpenAIToolCallDelta = {}
        index = raw.get("index")
        if _is_tool_call_index(index):
            delta["index"] = index
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
            cleaned: dict[str, dict[str, JsonValue]] = {}
            for namespace, inner in extra_content.items():
                if isinstance(inner, dict):
                    cleaned[namespace] = dict(inner)
            if cleaned:
                delta["extra_content"] = cleaned
        return delta

    def _tool_call_delta_event(
        self,
        delta: _OpenAIToolCallDelta,
        *,
        resolved_index: int | None,
    ) -> RunnerToolCallDeltaData | None:
        """把强类型 delta 投影为 RunnerEvent data。

        :param delta: 流式 tool call 增量。
        :param resolved_index: :meth:`ToolCallAggregator.feed` 返回的
            归属 index；若 delta 无法归属（既缺 ``index`` 又缺 ``id``）
            为 ``None``，此时返回 ``None`` 丢弃该条无法归属的 delta。
        :returns: 可归属的 tool call delta；无法归属时返回 ``None``。
        """

        if resolved_index is not None:
            tool_call_index = resolved_index
        else:
            raw_index = delta.get("index")
            if _is_tool_call_index(raw_index):
                tool_call_index = raw_index
            else:
                _LOGGER.warning(
                    "sse.protocol_diagnostic code=tool_call_delta_unowned " "provider_request_id=%s",
                    self._provider_request_id,
                )
                return None
        delta_id = delta.get("id")
        tool_call_id = delta_id if isinstance(delta_id, str) else None
        function = delta.get("function")
        name_delta: str | None = None
        arguments_delta: str | None = None
        if function is not None:
            name = function.get("name")
            if isinstance(name, str):
                name_delta = name
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                arguments_delta = arguments
        return RunnerToolCallDeltaData(
            tool_call_index=tool_call_index,
            tool_call_id=tool_call_id,
            name_delta=name_delta,
            arguments_delta=arguments_delta,
        )

    async def _handle_usage(self, usage: dict[str, JsonValue]) -> AsyncIterator[RunnerEvent]:
        """处理 ``usage`` 字段。

        :param usage: provider 返回的 usage object。
        :returns: usage 字段完整时产出 token 统计事件；字段格式错误时只记录
            warning 并忽略该 usage，不终止 SSE 主事件流。
        :raises Exception: 不主动抛出异常。
        """

        normalized = coerce_usage(usage)
        if normalized is None:
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
            _LOGGER.warning(
                "sse.protocol_diagnostic code=usage_field_malformed "
                "prompt_tokens_type=%s completion_tokens_type=%s "
                "total_tokens_type=%s",
                type(prompt_tokens).__name__,
                type(completion_tokens).__name__,
                type(total_tokens).__name__,
            )
            return
        yield _make_event(
            RunnerUsageRecordedData(
                prompt_tokens=normalized.prompt_tokens,
                completion_tokens=normalized.completion_tokens,
                total_tokens=normalized.total_tokens,
            )
        )

    async def _finalize_success(self) -> AsyncIterator[RunnerEvent]:
        """流自然结束时收口。"""

        if self._terminated:
            return
        flush = self._extractor.flush()
        if flush.outside_text:
            self._content_buffer.append(flush.outside_text)
            yield _make_event(RunnerContentDeltaData(delta=flush.outside_text))
        if flush.inside_text:
            self._reasoning_buffer.append(flush.inside_text)
            yield _make_event(RunnerReasoningDeltaData(delta=flush.inside_text))
        if self._tool_calls_seen:
            result = self._aggregator.finalize()
            for warning in result.warnings:
                yield _make_event(warning)
            if result.fatal_errors:
                for fatal in result.fatal_errors:
                    yield _make_event(fatal)
                self._terminated = True
                yield _make_event(
                    RunnerDoneData(
                        finish_reason=FinishReason.ERROR,
                        provider_request_id=self._provider_request_id,
                    )
                )
                return
            yield _make_event(
                RunnerToolCallsCompletedData(
                    tool_calls=result.tool_calls,
                    content="".join(self._content_buffer) or None,
                    reasoning_content="".join(self._reasoning_buffer) or None,
                )
            )
        else:
            content = "".join(self._content_buffer) or None
            reasoning = "".join(self._reasoning_buffer) or None
            yield _make_event(
                RunnerContentCompletedData(
                    content=content,
                    reasoning_content=reasoning,
                    finish_reason=self._finish_reason or FinishReason.STOP,
                )
            )
        finish = FinishReason.TOOL_CALLS if self._tool_calls_seen else self._finish_reason or FinishReason.STOP
        self._terminated = True
        yield _make_event(
            RunnerDoneData(
                finish_reason=finish,
                provider_request_id=self._provider_request_id,
            )
        )


__all__ = ["SSEParser"]
