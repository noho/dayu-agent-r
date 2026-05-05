"""``AssistantToolCall.provider_state`` 与 roundtrip 透传一致性测试。

覆盖 Phase 1 contract 补丁（``docs/engine/phase1-plan.md`` §0.1）：

- ``AssistantToolCall.provider_state`` 字段构造（``None`` 与 Gemini
  续航状态两路）。
- ``ToolCallRequest`` → ``AssistantToolCall`` provider_state 透传一致性
  （Runner / Agent 在工具调用 roundtrip 中必须按字段直接搬运，不能
  扁平化或丢失 namespace 语义）。
"""

from __future__ import annotations

import dataclasses

from dayu.contracts.tool_call import (
    GeminiToolCallState,
    ToolCallRequest,
)
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    AssistantMessage,
    AssistantToolCall,
)


def test_assistant_tool_call_field_set_includes_provider_state() -> None:
    """``AssistantToolCall`` 字段集合必须包含 ``provider_state``。"""

    fields = {f.name for f in dataclasses.fields(AssistantToolCall)}
    assert fields == {"id", "name", "arguments", "provider_state"}


def test_assistant_tool_call_with_none_provider_state() -> None:
    """``provider_state=None`` 合法，等值正常。"""

    a = AssistantToolCall(id="1", name="t", arguments={}, provider_state=None)
    b = AssistantToolCall(id="1", name="t", arguments={}, provider_state=None)
    assert a == b
    assert a.provider_state is None


def test_assistant_tool_call_with_gemini_provider_state() -> None:
    """``provider_state=GeminiToolCallState(...)`` 等值正常。"""

    state = GeminiToolCallState(thought_signature="sig")
    a = AssistantToolCall(id="1", name="t", arguments={}, provider_state=state)
    b = AssistantToolCall(
        id="1",
        name="t",
        arguments={},
        provider_state=GeminiToolCallState(thought_signature="sig"),
    )
    assert a == b


def test_assistant_message_carries_assistant_tool_call_with_provider_state() -> None:
    """``AssistantMessage.tool_calls`` 元组中可承载 provider_state。"""

    state = GeminiToolCallState(thought_signature="sig")
    message = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content=None,
        reasoning_content=None,
        tool_calls=(
            AssistantToolCall(
                id="1", name="t", arguments={}, provider_state=state
            ),
        ),
    )
    assert message.tool_calls[0].provider_state == state


def test_tool_call_request_to_assistant_tool_call_provider_state_passthrough() -> None:
    """``ToolCallRequest`` → ``AssistantToolCall`` 透传 provider_state 一致性。

    模拟 Runner / Agent 在 roundtrip 边界把 :class:`ToolCallRequest`
    的 ``provider_state`` 直接复制到 :class:`AssistantToolCall`：字段值
    必须严格相等（同实例语义即可，dataclass frozen 等值即同义）。
    """

    state = GeminiToolCallState(thought_signature="sig-roundtrip")
    request = ToolCallRequest(
        tool_call_id="call-1",
        name="get_value",
        arguments={"k": "v"},
        index_in_iteration=0,
        provider_state=state,
    )
    assistant_tool_call = AssistantToolCall(
        id=request.tool_call_id,
        name=request.name,
        arguments=request.arguments,
        provider_state=request.provider_state,
    )
    assert assistant_tool_call.provider_state == request.provider_state
    assert assistant_tool_call.provider_state == GeminiToolCallState(
        thought_signature="sig-roundtrip"
    )
