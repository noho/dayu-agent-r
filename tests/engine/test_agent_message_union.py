"""AgentMessage 联合契约测试。

使用具体 dataclass 元组进行 ``isinstance`` 检查；不依赖
:data:`AgentMessage` TypeAlias 的运行时 isinstance 行为（PEP 604 union
在运行时是 ``types.UnionType``，不直接用于 isinstance）。
"""

from __future__ import annotations

import dataclasses

from dayu.engine.contracts.messages import (
    AgentMessageRole,
    AssistantMessage,
    AssistantToolCall,
    SystemMessage,
    ToolMessage,
    UserMessage,
)

_CONCRETE_AGENT_MESSAGE_TYPES = (
    SystemMessage,
    UserMessage,
    AssistantMessage,
    ToolMessage,
)


def test_each_concrete_message_instance_is_recognized() -> None:
    """每个具体消息实例必须落在四元 dataclass 元组之内。"""

    s = SystemMessage(role=AgentMessageRole.SYSTEM, content="x")
    u = UserMessage(role=AgentMessageRole.USER, content="x")
    a = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content="x",
        reasoning_content=None,
        tool_calls=(),
    )
    t = ToolMessage(role=AgentMessageRole.TOOL, tool_call_id="id", content="x")
    for instance in (s, u, a, t):
        assert isinstance(instance, _CONCRETE_AGENT_MESSAGE_TYPES)


def test_system_message_field_set() -> None:
    """``SystemMessage`` 字段集合必须为 ``{role, content}``。"""

    fields = {f.name for f in dataclasses.fields(SystemMessage)}
    assert fields == {"role", "content"}


def test_user_message_field_set() -> None:
    """``UserMessage`` 字段集合必须为 ``{role, content}``。"""

    fields = {f.name for f in dataclasses.fields(UserMessage)}
    assert fields == {"role", "content"}


def test_assistant_message_field_set() -> None:
    """``AssistantMessage`` 字段集合必须精确符合契约。"""

    fields = {f.name for f in dataclasses.fields(AssistantMessage)}
    assert fields == {"role", "content", "reasoning_content", "tool_calls"}


def test_tool_message_field_set() -> None:
    """``ToolMessage`` 字段集合必须为 ``{role, tool_call_id, content}``。"""

    fields = {f.name for f in dataclasses.fields(ToolMessage)}
    assert fields == {"role", "tool_call_id", "content"}


def test_assistant_tool_call_field_set() -> None:
    """``AssistantToolCall`` 字段集合必须包含 ``provider_state``。"""

    fields = {f.name for f in dataclasses.fields(AssistantToolCall)}
    assert fields == {"id", "name", "arguments", "provider_state"}
