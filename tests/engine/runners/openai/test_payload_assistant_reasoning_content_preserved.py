"""``AssistantMessage.reasoning_content`` provider roundtrip 测试。"""

from __future__ import annotations

from dayu.contracts.tool_call import GeminiToolCallState
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    AssistantMessage,
    AssistantToolCall,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import (
    DeepSeekThinkingExtension,
    MimoThinkingExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
)
from dayu.engine.runners.openai.payload import build_request_payload

from tests.engine.runners.openai._factories import make_options, make_spec


def test_reasoning_content_roundtrips_when_present() -> None:
    """``reasoning_content`` 非空时 outbound 必须原样保留。

    MiMo、DeepSeek、Qwen 等 thinking + tool-call provider 要求把上一轮
    assistant ``reasoning_content`` 随历史消息送回；payload builder 只保留
    已存在的 Engine 消息事实，不自行生成该字段。
    """

    msg = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content="hello",
        reasoning_content="some thinking",
        tool_calls=(),
    )
    payload = build_request_payload(
        messages=[msg],
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(),
    )
    messages = payload.get("messages")
    assert messages is not None
    assert messages[0].get("reasoning_content") == "some thinking"


def test_reasoning_content_roundtrips_for_thinking_tool_call_providers() -> None:
    """thinking tool-call provider 的 ``reasoning_content`` 必须可回传。"""

    provider_requests: tuple[ProviderRequestExtension, ...] = (
        MimoThinkingExtension(enabled=True),
        DeepSeekThinkingExtension(enabled=True),
        QwenThinkingExtension(enable_thinking=True),
    )
    msg = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content="hello",
        reasoning_content="provider thinking",
        tool_calls=(),
    )
    for provider_request in provider_requests:
        payload = build_request_payload(
            messages=[msg],
            options=make_options(stream=False),
            tools=[],
            spec=make_spec(provider_request=provider_request),
        )
        messages = payload.get("messages")
        assert messages is not None
        assert messages[0].get("reasoning_content") == "provider thinking"


def test_reasoning_content_absent_when_none() -> None:
    """``reasoning_content=None`` 时 outbound 不应包含该键。"""

    msg = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content="hello",
        reasoning_content=None,
        tool_calls=(),
    )
    payload = build_request_payload(
        messages=[msg],
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(),
    )
    messages = payload.get("messages")
    assert messages is not None
    assert "reasoning_content" not in messages[0]


def test_assistant_tool_calls_extra_content_roundtrip() -> None:
    """``GeminiToolCallState`` 应回写到 ``extra_content.google``。"""

    tc = AssistantToolCall(
        id="call-1",
        name="ping",
        arguments={"x": 1},
        provider_state=GeminiToolCallState(thought_signature="sig-abc"),
    )
    msg = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content=None,
        reasoning_content=None,
        tool_calls=(tc,),
    )
    payload = build_request_payload(
        messages=[msg],
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(),
    )
    messages = payload.get("messages")
    assert messages is not None
    out = messages[0]
    out_calls = out.get("tool_calls")
    assert out_calls is not None
    extra = out_calls[0].get("extra_content")
    assert extra == {"google": {"thought_signature": "sig-abc"}}


def test_assistant_tool_calls_no_extra_content_when_state_none() -> None:
    """``provider_state=None`` 时 outbound tool call 不应包含 ``extra_content``。"""

    tc = AssistantToolCall(
        id="call-1",
        name="ping",
        arguments={},
        provider_state=None,
    )
    msg = AssistantMessage(
        role=AgentMessageRole.ASSISTANT,
        content=None,
        reasoning_content=None,
        tool_calls=(tc,),
    )
    payload = build_request_payload(
        messages=[msg],
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(),
    )
    messages = payload.get("messages")
    assert messages is not None
    out_calls = messages[0].get("tool_calls")
    assert out_calls is not None
    assert "extra_content" not in out_calls[0]


def test_user_message_serialization() -> None:
    """user 消息只有 ``role`` / ``content``。"""

    msg = UserMessage(role=AgentMessageRole.USER, content="hi")
    payload = build_request_payload(
        messages=[msg],
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(),
    )
    messages = payload.get("messages")
    assert messages is not None
    out = messages[0]
    assert out.get("role") == "user"
    assert out.get("content") == "hi"
    assert "reasoning_content" not in out
    assert "tool_calls" not in out
