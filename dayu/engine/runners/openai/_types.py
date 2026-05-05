"""OpenAI Runner 私有 adapter 类型。

本模块定义 Runner 内部使用的强类型 ``TypedDict`` / dataclass / 枚举，
**不**出包。所有外部消费方应使用
:mod:`dayu.engine.contracts` / :mod:`dayu.contracts` 公共契约。

类型设计原则：

- 用 ``TypedDict(total=False)`` 表达 OpenAI 协议字段集合，避免裸
  ``dict[str, Any]`` 充当协议载体。
- ``provider_request_id`` / ``raw_payload`` 等错误诊断字段允许 ``None``；
  解析失败一律降级 ``None``。
- ``extra_content`` 在 outbound / inbound 两侧都按 provider namespace
  字典分桶（``Mapping[str, Mapping[str, JsonValue]]``），不允许扁平化。

弱类型守卫白名单：

:class:`_OpenAIToolCallDelta` / :class:`_OpenAIToolCallFinal` 中的
``arguments`` 字段允许接收 ``str | None``，与 OpenAI 流式协议事实一致。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypedDict

from dayu.contracts.json_value import JsonValue


class _OpenAIStreamOptions(TypedDict, total=False):
    """OpenAI ``stream_options`` 字段。"""

    include_usage: bool


class _OpenAIExtraBody(TypedDict, total=False):
    """OpenAI ``extra_body`` 字段。

    Phase 1 仅承载 Gemini ``google`` namespace 的 ``thinking_config``。
    其它 provider（Anthropic / Qwen / OpenAI）私有字段位于请求顶层，
    不进入本结构。
    """

    google: Mapping[str, JsonValue]


class _OpenAIToolCallFunction(TypedDict, total=False):
    """OpenAI tool call ``function`` 字段。"""

    name: str
    arguments: str


class _OpenAIOutboundToolCall(TypedDict, total=False):
    """outbound assistant tool call 序列化形态。

    :ivar id: 工具调用 id。
    :ivar type: 固定为 ``"function"``。
    :ivar function: 工具函数名 + 序列化参数。
    :ivar extra_content: provider namespace 续航字段；当
        :class:`~dayu.contracts.tool_call.GeminiToolCallState` 存在时写入
        ``{"google": {"thought_signature": ...}}``。
    """

    id: str
    type: str
    function: _OpenAIToolCallFunction
    extra_content: Mapping[str, Mapping[str, JsonValue]]


class _OpenAIChatMessage(TypedDict, total=False):
    """outbound chat message 序列化形态。

    覆盖 ``system`` / ``user`` / ``assistant`` / ``tool`` 四角色字段。
    ``role`` 必填，其它字段视具体角色出现。
    """

    role: str
    content: str | None
    reasoning_content: str
    tool_calls: list[_OpenAIOutboundToolCall]
    tool_call_id: str
    name: str


class _OpenAIToolFunctionSchema(TypedDict, total=False):
    """outbound tool 函数 schema。"""

    name: str
    description: str
    parameters: Mapping[str, JsonValue]


class _OpenAIToolSchema(TypedDict, total=False):
    """outbound tool schema 顶层包装。"""

    type: str
    function: _OpenAIToolFunctionSchema


class _OpenAIThinkingTopLevel(TypedDict, total=False):
    """OpenAI-compatible 顶层 ``thinking`` 字段。"""

    type: str
    budget_tokens: int


class _OpenAIRequestPayload(TypedDict, total=False):
    """OpenAI 兼容 chat completion 请求 payload。

    本 TypedDict 只声明本 Runner 实际写入的字段；构造时一律使用本
    类型，禁止透传 ``dict[str, Any]``。
    """

    model: str
    messages: list[_OpenAIChatMessage]
    temperature: float
    max_tokens: int
    top_p: float
    stream: bool
    stream_options: _OpenAIStreamOptions
    tools: list[_OpenAIToolSchema]
    tool_choice: str
    reasoning_effort: str
    thinking: _OpenAIThinkingTopLevel
    enable_thinking: bool
    thinking_budget: int
    extra_body: _OpenAIExtraBody


class _OpenAIToolCallDelta(TypedDict, total=False):
    """流式 tool call delta（按 OpenAI 协议）。"""

    index: int
    id: str
    type: str
    function: _OpenAIToolCallFunction
    extra_content: Mapping[str, Mapping[str, JsonValue]]


class _OpenAIToolCallFinal(TypedDict, total=False):
    """非流式 tool call 最终态。"""

    id: str
    type: str
    function: _OpenAIToolCallFunction
    extra_content: Mapping[str, Mapping[str, JsonValue]]


class _OpenAIUsage(TypedDict, total=False):
    """OpenAI usage 字段。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class _OpenAIChoiceFinalMessage(TypedDict, total=False):
    """non-stream choice ``message`` 字段。"""

    role: str
    content: str | None
    reasoning_content: str | None
    tool_calls: list[_OpenAIToolCallFinal]


class _OpenAIChoiceFinal(TypedDict, total=False):
    """non-stream choice 整体形态。"""

    index: int
    finish_reason: str | None
    message: _OpenAIChoiceFinalMessage


@dataclass(frozen=True, slots=True)
class _RetryDecision:
    """重试决策结果。

    :param should_retry: 是否应该再次尝试。
    :param sleep_seconds: 下次尝试前需要 sleep 的秒数；当
        ``should_retry`` 为 ``False`` 时无意义。
    :param attempt: 本决策对应的「已尝试次数」（首次失败时为 1）。
    """

    should_retry: bool
    sleep_seconds: float
    attempt: int


@dataclass(frozen=True, slots=True)
class _ReasoningProtocolHook:
    """provider 私有 reasoning 协议钩子。

    :param tag_name: 需剥离的 XML 标签名；为 ``None`` 表示当前 provider
        无私有 reasoning 协议（直接走 ``delta.reasoning_content`` 通道）。
    """

    tag_name: str | None


class _ChunkAggregationKind(StrEnum):
    """tool call 聚合键的来源。

    :cvar BY_INDEX: 按 ``delta.index`` 归属。
    :cvar BY_ID: ``index`` 缺失时按 ``id`` 归属（review §5.3 OLD 兼容点）。
    """

    BY_INDEX = "by_index"
    BY_ID = "by_id"


__all__ = [
    "_OpenAIStreamOptions",
    "_OpenAIExtraBody",
    "_OpenAIToolCallFunction",
    "_OpenAIOutboundToolCall",
    "_OpenAIChatMessage",
    "_OpenAIToolFunctionSchema",
    "_OpenAIToolSchema",
    "_OpenAIThinkingTopLevel",
    "_OpenAIRequestPayload",
    "_OpenAIToolCallDelta",
    "_OpenAIToolCallFinal",
    "_OpenAIUsage",
    "_OpenAIChoiceFinalMessage",
    "_OpenAIChoiceFinal",
    "_RetryDecision",
    "_ReasoningProtocolHook",
    "_ChunkAggregationKind",
]
