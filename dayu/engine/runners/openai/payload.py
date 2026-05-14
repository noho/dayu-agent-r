"""请求 payload 构建。

本模块提供 :func:`build_request_payload` 纯函数，把
:class:`AgentMessage` 序列、:class:`RunnerCallOptions`、:class:`ToolSchema`
序列与 :class:`RunnerSpec` 投影为
:class:`~dayu.engine.runners.openai._types._OpenAIRequestPayload`。

设计要点：

- 每个 :class:`ProviderRequestExtension` 成员有固定投影位置
  （顶层字段 vs ``extra_body.google``），由 ``match`` + ``assert_never``
  穷尽守护（详见 phase1-plan.md §6.3）。
- ``stream_options.include_usage`` 受 ``RunnerSpec.supports_stream_usage``
  capability 门控：仅当 ``stream=True`` 且 ``supports_stream_usage=True``
  时写入；其它情形不写。
- :class:`AssistantMessage.reasoning_content is not None` 时 outbound
  message 必须保留 ``reasoning_content`` 键，与 OLD 真源一致。
- :class:`AssistantToolCall.provider_state == GeminiToolCallState(s)` 时
  outbound tool call 写入 ``extra_content = {"google":
  {"thought_signature": s}}``，保留 ``google`` namespace。
- 显式参数（``temperature`` / ``max_tokens`` / ``top_p`` / ``stream``）
  不进入 ``provider_request`` / ``extra_body``。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import assert_never

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import GeminiToolCallState, ToolCallProviderState
from dayu.contracts.tool_schema import ToolSchema
from dayu.engine.contracts.messages import (
    AgentMessage,
    AssistantMessage,
    AssistantToolCall,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    DeepSeekReasoningEffort,
    DeepSeekThinkingExtension,
    GeminiThinkingLevel,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.engine.runners.openai._types import (
    _OpenAIChatMessage,
    _OpenAIExtraBody,
    _OpenAIOutboundToolCall,
    _OpenAIRequestPayload,
    _OpenAIStreamOptions,
    _OpenAIThinkingTopLevel,
    _OpenAIToolCallFunction,
    _OpenAIToolFunctionSchema,
    _OpenAIToolSchema,
)


def _serialize_arguments(arguments: Mapping[str, JsonValue]) -> str:
    """把 tool call 参数序列化为 JSON 字符串。

    :param arguments: 工具调用参数。
    :returns: JSON 字符串。
    :raises TypeError: 当 ``arguments`` 违反 JSON 值契约、无法序列化时抛出。
    """

    return json.dumps(dict(arguments), ensure_ascii=False)


def _serialize_provider_state(
    provider_state: ToolCallProviderState | None,
) -> Mapping[str, Mapping[str, JsonValue]] | None:
    """把 provider_state 投影为 outbound ``extra_content`` 字段。

    :param provider_state: 强类型 provider 续航状态；为 ``None`` 表示
        不写 ``extra_content``。
    :returns: ``{"google": {"thought_signature": ...}}`` 或 ``None``。
    :raises AssertionError: 当封闭联合出现未处理成员时抛出。
    """

    if provider_state is None:
        return None
    match provider_state:
        case GeminiToolCallState(thought_signature=signature):
            inner: Mapping[str, JsonValue] = {"thought_signature": signature}
            return {"google": inner}
    assert_never(provider_state)


def _serialize_assistant_tool_call(
    tool_call: AssistantToolCall,
) -> _OpenAIOutboundToolCall:
    """序列化 assistant 消息中的单个工具调用记录。

    :param tool_call: assistant 消息内的工具调用。
    :returns: outbound 序列化形态。
    """

    function: _OpenAIToolCallFunction = {
        "name": tool_call.name,
        "arguments": _serialize_arguments(tool_call.arguments),
    }
    payload: _OpenAIOutboundToolCall = {
        "id": tool_call.id,
        "type": "function",
        "function": function,
    }
    extra_content = _serialize_provider_state(tool_call.provider_state)
    if extra_content is not None:
        payload["extra_content"] = extra_content
    return payload


def _serialize_message(message: AgentMessage) -> _OpenAIChatMessage:
    """把单条 :class:`AgentMessage` 序列化为 outbound chat message。

    :param message: 任一具体消息。
    :returns: outbound 序列化形态。
    :raises AssertionError: 当封闭联合出现未处理消息成员时抛出。
    """

    match message:
        case SystemMessage(content=content):
            payload: _OpenAIChatMessage = {
                "role": "system",
                "content": content,
            }
            return payload
        case UserMessage(content=content):
            return {"role": "user", "content": content}
        case AssistantMessage(
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
        ):
            assistant_payload: _OpenAIChatMessage = {
                "role": "assistant",
                "content": content,
            }
            if reasoning_content is not None:
                assistant_payload["reasoning_content"] = reasoning_content
            if tool_calls:
                assistant_payload["tool_calls"] = [
                    _serialize_assistant_tool_call(tc) for tc in tool_calls
                ]
            return assistant_payload
        case ToolMessage(tool_call_id=tool_call_id, content=content):
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
    assert_never(message)


def _serialize_tool_schema(schema: ToolSchema) -> _OpenAIToolSchema:
    """序列化工具 schema 顶层包装。

    :param schema: 工具 schema。
    :returns: outbound 序列化形态。
    """

    parameters: Mapping[str, JsonValue] = {
        "type": schema.function.parameters.type,
        "properties": schema.function.parameters.properties,
        "required": list(schema.function.parameters.required),
    }
    if schema.function.parameters.additional_properties is not None:
        # 维持 JSON Schema 风格 ``additionalProperties`` 命名。
        parameters = {
            **parameters,
            "additionalProperties": (
                schema.function.parameters.additional_properties
            ),
        }
    function_payload: _OpenAIToolFunctionSchema = {
        "name": schema.function.name,
        "description": schema.function.description,
        "parameters": parameters,
    }
    return {"type": schema.type, "function": function_payload}


def _apply_provider_request(
    payload: _OpenAIRequestPayload,
    provider_request: ProviderRequestExtension | None,
) -> None:
    """把 provider 请求扩展投影到对应位置。

    :param payload: 待写入的请求 payload。
    :param provider_request: provider 请求扩展或 ``None``。
    :returns: 无返回值；原地修改 ``payload``。
    :raises AssertionError: 当封闭联合出现未处理 provider 扩展成员时抛出。
    """

    if provider_request is None:
        return
    match provider_request:
        case OpenAIReasoningExtension(reasoning_effort=effort):
            payload["reasoning_effort"] = _reasoning_effort_value(effort)
        case AnthropicThinkingExtension(
            enabled=enabled, budget_tokens=budget_tokens
        ):
            thinking: _OpenAIThinkingTopLevel = {
                "type": "enabled" if enabled else "disabled",
            }
            if budget_tokens is not None:
                thinking["budget_tokens"] = budget_tokens
            payload["thinking"] = thinking
        case DeepSeekThinkingExtension(
            enabled=enabled, reasoning_effort=reasoning_effort
        ):
            payload["thinking"] = _top_level_thinking_enabled(enabled)
            if reasoning_effort is not None:
                payload["reasoning_effort"] = _deepseek_reasoning_effort_value(
                    reasoning_effort
                )
        case MimoThinkingExtension(enabled=enabled):
            payload["thinking"] = _top_level_thinking_enabled(enabled)
        case GeminiThinkingExtension(
            thinking_budget=thinking_budget,
            include_thoughts=include_thoughts,
            thinking_level=thinking_level,
        ):
            thinking_config: dict[str, JsonValue] = {}
            if thinking_budget is not None:
                thinking_config["thinking_budget"] = thinking_budget
            if thinking_level is not None:
                thinking_config["thinking_level"] = _gemini_thinking_level_value(
                    thinking_level
                )
            if include_thoughts is not None:
                thinking_config["include_thoughts"] = include_thoughts
            inner: Mapping[str, JsonValue] = {"thinking_config": thinking_config}
            extra_body: _OpenAIExtraBody = {"google": inner}
            payload["extra_body"] = extra_body
        case QwenThinkingExtension(
            enable_thinking=enable_thinking, thinking_budget=thinking_budget
        ):
            payload["enable_thinking"] = enable_thinking
            if thinking_budget is not None:
                payload["thinking_budget"] = thinking_budget
        case _:
            assert_never(provider_request)


def _top_level_thinking_enabled(enabled: bool) -> _OpenAIThinkingTopLevel:
    """构造无预算字段的顶层 ``thinking`` 开关。

    :param enabled: 是否启用 thinking。
    :returns: 仅包含 ``type`` 的顶层 ``thinking`` 字段。
    """

    return {"type": "enabled" if enabled else "disabled"}


def _reasoning_effort_value(effort: OpenAIReasoningEffort) -> str:
    """把 :class:`OpenAIReasoningEffort` 投影为字符串字面量。

    :param effort: 推理强度枚举。
    :returns: 字符串字面量。
    :raises AssertionError: 当枚举出现未处理成员时抛出。
    """

    match effort:
        case OpenAIReasoningEffort.MINIMAL:
            return "minimal"
        case OpenAIReasoningEffort.LOW:
            return "low"
        case OpenAIReasoningEffort.MEDIUM:
            return "medium"
        case OpenAIReasoningEffort.HIGH:
            return "high"
        case OpenAIReasoningEffort.XHIGH:
            return "xhigh"
        case OpenAIReasoningEffort.NONE:
            return "none"
    assert_never(effort)


def _deepseek_reasoning_effort_value(effort: DeepSeekReasoningEffort) -> str:
    """把 :class:`DeepSeekReasoningEffort` 投影为字符串字面量。

    :param effort: DeepSeek 推理强度枚举。
    :returns: 字符串字面量。
    :raises AssertionError: 当枚举出现未处理成员时抛出。
    """

    match effort:
        case DeepSeekReasoningEffort.HIGH:
            return "high"
        case DeepSeekReasoningEffort.MAX:
            return "max"
    assert_never(effort)


def _gemini_thinking_level_value(level: GeminiThinkingLevel) -> str:
    """把 :class:`GeminiThinkingLevel` 投影为字符串字面量。

    :param level: Gemini thinking level 枚举。
    :returns: 字符串字面量。
    :raises AssertionError: 当枚举出现未处理成员时抛出。
    """

    match level:
        case GeminiThinkingLevel.MINIMAL:
            return "minimal"
        case GeminiThinkingLevel.LOW:
            return "low"
        case GeminiThinkingLevel.MEDIUM:
            return "medium"
        case GeminiThinkingLevel.HIGH:
            return "high"
    assert_never(level)


def build_request_payload(
    *,
    messages: Sequence[AgentMessage],
    options: RunnerCallOptions,
    tools: Sequence[ToolSchema],
    spec: RunnerSpec,
) -> _OpenAIRequestPayload:
    """构建 OpenAI 兼容 chat completion 请求 payload。

    :param messages: 消息序列。
    :param options: 单次调用参数。
    :param tools: 工具 schema 序列。
    :param spec: Runner 规约。
    :returns: 强类型 :class:`_OpenAIRequestPayload`。
    """

    payload: _OpenAIRequestPayload = {
        "model": spec.model,
        "messages": [_serialize_message(m) for m in messages],
        "stream": options.stream,
    }
    if options.temperature is not None:
        payload["temperature"] = options.temperature
    if options.max_tokens is not None:
        payload["max_tokens"] = options.max_tokens
    if options.top_p is not None:
        payload["top_p"] = options.top_p
    if tools:
        payload["tools"] = [_serialize_tool_schema(t) for t in tools]
        payload["tool_choice"] = "auto"
    if options.stream and spec.supports_stream_usage:
        stream_options: _OpenAIStreamOptions = {"include_usage": True}
        payload["stream_options"] = stream_options
    _apply_provider_request(payload, spec.provider_request)
    return payload


__all__ = ["build_request_payload"]
