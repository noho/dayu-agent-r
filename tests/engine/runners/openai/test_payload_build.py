"""``build_request_payload`` 投影测试。

覆盖 phase1-plan.md §6.3 表格中的四种 ProviderRequestExtension：

- :class:`OpenAIReasoningExtension` → 顶层 ``reasoning_effort``。
- :class:`AnthropicThinkingExtension` → 顶层 ``thinking``。
- :class:`GeminiThinkingExtension` → ``extra_body.google.thinking_config``。
- :class:`QwenThinkingExtension` → 顶层 ``enable_thinking``。
"""

from __future__ import annotations

from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.messages import (
    AgentMessageRole,
    SystemMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    GeminiThinkingExtension,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    QwenThinkingExtension,
)
from dayu.engine.runners.openai.payload import build_request_payload

from tests.engine.runners.openai._factories import make_options, make_spec


def _basic_messages() -> list[SystemMessage | UserMessage]:
    """构造最小消息序列。"""

    return [
        SystemMessage(role=AgentMessageRole.SYSTEM, content="sys"),
        UserMessage(role=AgentMessageRole.USER, content="hi"),
    ]


def test_openai_reasoning_projection_to_top_level() -> None:
    """OpenAI reasoning 应投影到顶层 ``reasoning_effort``。"""

    spec = make_spec(
        provider_request=OpenAIReasoningExtension(
            reasoning_effort=OpenAIReasoningEffort.HIGH
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    assert payload.get("reasoning_effort") == "high"
    assert "extra_body" not in payload
    assert "thinking" not in payload
    assert "enable_thinking" not in payload


def test_openai_reasoning_none_value_serialized() -> None:
    """``OpenAIReasoningEffort.NONE`` 必须投影为字面量 ``"none"``。"""

    spec = make_spec(
        provider_request=OpenAIReasoningExtension(
            reasoning_effort=OpenAIReasoningEffort.NONE
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    assert payload.get("reasoning_effort") == "none"


def test_anthropic_thinking_projection_to_top_level() -> None:
    """Anthropic thinking 应投影到顶层 ``thinking``，不进 ``extra_body``。"""

    spec = make_spec(
        provider_request=AnthropicThinkingExtension(
            enabled=True, budget_tokens=2048
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    thinking = payload.get("thinking")
    assert thinking == {"type": "enabled", "budget_tokens": 2048}
    assert "extra_body" not in payload


def test_anthropic_thinking_disabled_branch() -> None:
    """``enabled=False`` 应投影为 ``type='disabled'``。"""

    spec = make_spec(
        provider_request=AnthropicThinkingExtension(
            enabled=False, budget_tokens=0
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    assert payload.get("thinking") == {
        "type": "disabled",
        "budget_tokens": 0,
    }


def test_gemini_thinking_projection_to_extra_body_google() -> None:
    """Gemini thinking 应投影到 ``extra_body.google.thinking_config``。"""

    spec = make_spec(
        provider_request=GeminiThinkingExtension(
            thinking_budget=1024, include_thoughts=True
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    extra_body = payload.get("extra_body")
    assert extra_body == {
        "google": {
            "thinking_config": {
                "thinking_budget": 1024,
                "include_thoughts": True,
            }
        }
    }
    assert "thinking" not in payload
    assert "reasoning_effort" not in payload


def test_qwen_thinking_projection_to_top_level() -> None:
    """Qwen thinking 应投影到顶层 ``enable_thinking``。"""

    spec = make_spec(
        provider_request=QwenThinkingExtension(enable_thinking=True)
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    assert payload.get("enable_thinking") is True
    assert "extra_body" not in payload


def test_provider_request_none_no_extension_fields() -> None:
    """``provider_request=None`` 不写入任何 provider 私有字段。"""

    spec = make_spec(provider_request=None)
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    for key in ("reasoning_effort", "thinking", "enable_thinking", "extra_body"):
        assert key not in payload, f"unexpected provider field: {key}"


def test_explicit_options_do_not_leak_into_extra_body() -> None:
    """显式参数只进入顶层；不污染 ``extra_body`` / ``provider_request``。"""

    spec = make_spec(
        provider_request=GeminiThinkingExtension(
            thinking_budget=512, include_thoughts=False
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(
            temperature=0.7, max_tokens=100, top_p=0.9, stream=False
        ),
        tools=[],
        spec=spec,
    )
    assert payload.get("temperature") == 0.7
    assert payload.get("max_tokens") == 100
    assert payload.get("top_p") == 0.9
    assert payload.get("stream") is False
    extra_body = payload.get("extra_body")
    assert extra_body is not None
    inner = dict(extra_body).get("google")
    assert isinstance(inner, dict)
    # 显式参数不能渗入 extra_body
    for k in ("temperature", "max_tokens", "top_p", "stream"):
        assert k not in inner


def test_tool_schema_serialized() -> None:
    """``tools`` 序列存在时应写入 ``tools`` 与 ``tool_choice='auto'``。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="ping",
            description="ping",
            parameters=ToolParametersSchema(
                type="object",
                properties={},
                required=(),
                additional_properties=None,
            ),
        ),
    )
    spec = make_spec()
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[schema],
        spec=spec,
    )
    tools = payload.get("tools")
    assert tools is not None
    assert len(tools) == 1
    assert tools[0].get("type") == "function"
    assert payload.get("tool_choice") == "auto"


def test_no_tools_no_tool_choice() -> None:
    """tools 为空时不写 ``tool_choice``。"""

    spec = make_spec()
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
    )
    assert "tools" not in payload
    assert "tool_choice" not in payload
