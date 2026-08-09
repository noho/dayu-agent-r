"""``build_request_payload`` 投影测试。

覆盖 OpenAI-compatible Runner 当前消费的 ProviderRequestExtension：

- :class:`OpenAIReasoningExtension` → 顶层 ``reasoning_effort``。
- :class:`AnthropicThinkingExtension` → 顶层 ``thinking``。
- :class:`DeepSeekThinkingExtension` → 顶层 ``thinking``。
- :class:`MimoThinkingExtension` → 顶层 ``thinking``。
- :class:`GeminiThinkingExtension` → ``extra_body.google.thinking_config``。
- :class:`QwenThinkingExtension` → 顶层 ``enable_thinking``。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
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
    DeepSeekReasoningEffort,
    DeepSeekThinkingExtension,
    GeminiThinkingLevel,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    QwenThinkingExtension,
)
from dayu.engine.contracts.structured_output import (
    JsonObjectStructuredOutputRequest,
    JsonSchemaStructuredOutputRequest,
    StructuredOutputCapability,
)
from dayu.engine.runners.openai.payload import build_request_payload

from tests.engine.runners.openai._factories import make_options, make_spec


def _basic_messages() -> list[SystemMessage | UserMessage]:
    """构造最小消息序列。"""

    return [
        SystemMessage(role=AgentMessageRole.SYSTEM, content="sys"),
        UserMessage(role=AgentMessageRole.USER, content="hi"),
    ]


def _canonical_schema_digest(schema: Mapping[str, JsonValue]) -> str:
    """计算 owner test 使用的 canonical schema bytes digest。

    :param schema: canonical JSON Schema mapping。
    :returns: canonical JSON bytes 的 SHA-256 十六进制文本。
    :raises TypeError: schema 不能序列化为 JSON 时抛出。
    :raises ValueError: schema 含非有限 JSON number 时抛出。
    """

    canonical_bytes = json.dumps(
        schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def test_none_structured_output_omits_response_format() -> None:
    """``None`` request 不得写入 ``response_format``。"""

    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(
            structured_output_capability=StructuredOutputCapability.JSON_SCHEMA
        ),
        structured_output=None,
    )

    assert "response_format" not in payload


def test_json_object_structured_output_exact_payload() -> None:
    """JSON object request 必须投影 exact provider-native payload。"""

    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(
            structured_output_capability=StructuredOutputCapability.JSON_OBJECT
        ),
        structured_output=JsonObjectStructuredOutputRequest(),
    )

    response_format = payload.get("response_format")
    assert response_format == {"type": "json_object"}
    assert "extra_body" not in payload


def test_json_schema_structured_output_preserves_owner_schema_identity() -> None:
    """JSON Schema name、schema bytes identity 与 transport 必须同源。"""

    canonical_schema: Mapping[str, JsonValue] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    expected_digest = _canonical_schema_digest(canonical_schema)
    request = JsonSchemaStructuredOutputRequest(
        name="owner_schema",
        schema=canonical_schema,
        strict=True,
    )

    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=make_spec(
            structured_output_capability=StructuredOutputCapability.JSON_SCHEMA
        ),
        structured_output=request,
    )

    raw_response_format = payload.get("response_format")
    assert raw_response_format is not None
    response_format = cast(Mapping[str, JsonValue], raw_response_format)
    schema_definition = cast(
        Mapping[str, JsonValue], response_format["json_schema"]
    )
    transported_schema = cast(
        Mapping[str, JsonValue], schema_definition["schema"]
    )
    assert response_format["type"] == "json_schema"
    assert schema_definition["name"] == request.name
    assert schema_definition["strict"] is request.strict
    assert transported_schema is canonical_schema
    assert _canonical_schema_digest(transported_schema) == expected_digest
    assert "extra_body" not in payload


@pytest.mark.parametrize(
    ("capability", "structured_request"),
    (
        (
            StructuredOutputCapability.NONE,
            JsonObjectStructuredOutputRequest(),
        ),
        (
            StructuredOutputCapability.NONE,
            JsonSchemaStructuredOutputRequest(
                name="owner_schema",
                schema={"type": "object"},
                strict=True,
            ),
        ),
        (
            StructuredOutputCapability.JSON_OBJECT,
            JsonSchemaStructuredOutputRequest(
                name="owner_schema",
                schema={"type": "object"},
                strict=True,
            ),
        ),
    ),
)
def test_payload_rejects_invalid_capability_request_matrix(
    capability: StructuredOutputCapability,
    structured_request: (
        JsonObjectStructuredOutputRequest | JsonSchemaStructuredOutputRequest
    ),
) -> None:
    """Payload builder 在 outbound materialization 前拒绝非法组合。

    :param capability: 被测 capability。
    :param structured_request: 被测 request。
    """

    with pytest.raises(ValueError, match="does not support"):
        build_request_payload(
            messages=_basic_messages(),
            options=make_options(stream=False),
            tools=[],
            spec=make_spec(structured_output_capability=capability),
            structured_output=structured_request,
        )


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
        structured_output=None,
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
        structured_output=None,
    )
    assert payload.get("reasoning_effort") == "none"


def test_openai_reasoning_new_effort_values_serialized() -> None:
    """OpenAI 新增 effort 档位必须可投影为官方字面量。"""

    for effort, expected in (
        (OpenAIReasoningEffort.MINIMAL, "minimal"),
        (OpenAIReasoningEffort.XHIGH, "xhigh"),
    ):
        spec = make_spec(
            provider_request=OpenAIReasoningExtension(
                reasoning_effort=effort
            )
        )
        payload = build_request_payload(
            messages=_basic_messages(),
            options=make_options(stream=False),
            tools=[],
            spec=spec,
            structured_output=None,
        )
        assert payload.get("reasoning_effort") == expected


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
        structured_output=None,
    )
    thinking = payload.get("thinking")
    assert thinking == {"type": "enabled", "budget_tokens": 2048}
    assert "extra_body" not in payload


def test_anthropic_thinking_disabled_branch() -> None:
    """``enabled=False`` 只投影 ``type='disabled'``，不带预算字段。"""

    spec = make_spec(
        provider_request=AnthropicThinkingExtension(enabled=False)
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("thinking") == {"type": "disabled"}


def test_deepseek_thinking_projection_to_top_level_without_budget() -> None:
    """DeepSeek thinking 只写顶层 ``thinking.type``，不带预算字段。"""

    spec = make_spec(provider_request=DeepSeekThinkingExtension(enabled=True))
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("thinking") == {"type": "enabled"}
    assert "extra_body" not in payload


def test_deepseek_thinking_effort_projection_to_top_level() -> None:
    """DeepSeek thinking effort 应投影为顶层 ``reasoning_effort``。"""

    spec = make_spec(
        provider_request=DeepSeekThinkingExtension(
            enabled=True,
            reasoning_effort=DeepSeekReasoningEffort.MAX,
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("thinking") == {"type": "enabled"}
    assert payload.get("reasoning_effort") == "max"


def test_deepseek_disabled_thinking_projection_has_no_effort() -> None:
    """DeepSeek 关闭 thinking 时只写 ``thinking.type``。"""

    spec = make_spec(provider_request=DeepSeekThinkingExtension(enabled=False))
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("thinking") == {"type": "disabled"}
    assert "reasoning_effort" not in payload


def test_mimo_thinking_projection_to_top_level_without_budget() -> None:
    """MiMo thinking 只写顶层 ``thinking.type``，不带预算字段。"""

    spec = make_spec(provider_request=MimoThinkingExtension(enabled=True))
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("thinking") == {"type": "enabled"}
    assert "extra_body" not in payload


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
        structured_output=None,
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


def test_gemini_thinking_level_projection_to_extra_body_google() -> None:
    """Gemini thinking level 应投影到 ``thinking_config``。"""

    spec = make_spec(
        provider_request=GeminiThinkingExtension(
            thinking_level=GeminiThinkingLevel.MINIMAL,
            include_thoughts=False,
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("extra_body") == {
        "google": {
            "thinking_config": {
                "thinking_level": "minimal",
                "include_thoughts": False,
            }
        }
    }


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
        structured_output=None,
    )
    assert payload.get("enable_thinking") is True
    assert "extra_body" not in payload


def test_qwen_thinking_budget_projection_to_top_level() -> None:
    """Qwen thinking budget 应投影到顶层 ``thinking_budget``。"""

    spec = make_spec(
        provider_request=QwenThinkingExtension(
            enable_thinking=True,
            thinking_budget=50,
        )
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("enable_thinking") is True
    assert payload.get("thinking_budget") == 50


def test_qwen_disabled_thinking_projection_has_no_budget() -> None:
    """Qwen 关闭 thinking 时只写 ``enable_thinking``。"""

    spec = make_spec(
        provider_request=QwenThinkingExtension(enable_thinking=False)
    )
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    assert payload.get("enable_thinking") is False
    assert "thinking_budget" not in payload


def test_provider_request_none_no_extension_fields() -> None:
    """``provider_request=None`` 不写入任何 provider 私有字段。"""

    spec = make_spec(provider_request=None)
    payload = build_request_payload(
        messages=_basic_messages(),
        options=make_options(stream=False),
        tools=[],
        spec=spec,
        structured_output=None,
    )
    for key in (
        "reasoning_effort",
        "thinking",
        "enable_thinking",
        "thinking_budget",
        "extra_body",
    ):
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
        structured_output=None,
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
        structured_output=None,
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
        structured_output=None,
    )
    assert "tools" not in payload
    assert "tool_choice" not in payload
