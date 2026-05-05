"""Agent 消息封闭联合契约。

本模块定义 Engine 公共契约中的消息类型。四种 dataclass 形成一个封闭
联合 :data:`AgentMessage`，用于在 Agent / Runner / 工具调用闭环内承载
对话消息。

设计要点：

- 四种消息均为 ``frozen=True, slots=True`` dataclass，强类型字段必填。
- ``role`` 字段使用 :class:`AgentMessageRole` 的 ``Literal`` 收窄，确保
  联合在静态类型上可被穷尽匹配。
- ``AssistantMessage.tool_calls`` 使用 ``tuple`` 而非 ``list``，与
  ``frozen`` 语义一致。
- 联合是封闭的：本 Phase 仅承诺四种消息形态；新增消息类型必须经过
  Engine 设计评审。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import ToolCallProviderState


class AgentMessageRole(StrEnum):
    """Agent 消息角色枚举。

    成员：

    - ``SYSTEM``：系统提示。
    - ``USER``：用户输入。
    - ``ASSISTANT``：助手输出。
    - ``TOOL``：工具结果消息。
    """

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class SystemMessage:
    """系统消息。

    :param role: 必须为 :attr:`AgentMessageRole.SYSTEM`。
    :param content: 系统提示正文。
    """

    role: Literal[AgentMessageRole.SYSTEM]
    content: str


@dataclass(frozen=True, slots=True)
class UserMessage:
    """用户消息。

    :param role: 必须为 :attr:`AgentMessageRole.USER`。
    :param content: 用户输入正文。
    """

    role: Literal[AgentMessageRole.USER]
    content: str


@dataclass(frozen=True, slots=True)
class AssistantToolCall:
    """助手消息中携带的工具调用记录。

    :param id: 工具调用唯一 id（与 :class:`ToolMessage.tool_call_id` 配对）。
    :param name: 工具名称。
    :param arguments: 工具参数，强类型 JSON 映射。
    :param provider_state: provider 私有续航状态；为 ``None`` 表示当前
        provider 不需要在 tool call roundtrip 中携带额外签名 / 上下文。
        典型用法：Gemini 的 ``thought_signature`` 在多轮 roundtrip 中由
        :class:`~dayu.contracts.tool_call.ToolCallRequest.provider_state`
        透传至本字段，回写到 outbound assistant message 时再以
        ``extra_content.google.thought_signature`` 形态发回 provider。
    """

    id: str
    name: str
    arguments: Mapping[str, JsonValue]
    provider_state: ToolCallProviderState | None


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    """助手消息。

    :param role: 必须为 :attr:`AgentMessageRole.ASSISTANT`。
    :param content: 助手回复正文，可为空（流式中间态或仅触发工具调用时）。
    :param reasoning_content: 推理链文本，可为空。
    :param tool_calls: 助手在本轮请求触发的工具调用元组，可为空元组。
    """

    role: Literal[AgentMessageRole.ASSISTANT]
    content: str | None
    reasoning_content: str | None
    tool_calls: tuple[AssistantToolCall, ...]


@dataclass(frozen=True, slots=True)
class ToolMessage:
    """工具结果消息。

    :param role: 必须为 :attr:`AgentMessageRole.TOOL`。
    :param tool_call_id: 与 :class:`AssistantToolCall.id` 对应的工具调用 id。
    :param content: 工具结果正文（一般为序列化后的字符串）。
    """

    role: Literal[AgentMessageRole.TOOL]
    tool_call_id: str
    content: str


AgentMessage: TypeAlias = SystemMessage | UserMessage | AssistantMessage | ToolMessage
"""Agent 消息封闭联合。

包含 :class:`SystemMessage` / :class:`UserMessage` /
:class:`AssistantMessage` / :class:`ToolMessage` 四个成员。
"""

__all__ = [
    "AgentMessageRole",
    "SystemMessage",
    "UserMessage",
    "AssistantToolCall",
    "AssistantMessage",
    "ToolMessage",
    "AgentMessage",
]
