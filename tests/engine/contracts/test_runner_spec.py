"""``RunnerSpec`` / ``OpenAIReasoningEffort`` 契约补丁测试。

覆盖 Phase 1 contract 补丁（``docs/engine/phase1-plan.md`` §0.1）：

- ``OpenAIReasoningEffort`` 包含 ``NONE = "none"`` 成员。
- ``RunnerSpec`` 字段集合包含 ``supports_stream_usage``。
- ``RunnerSpec`` 可在 ``supports_stream_usage`` 双值下完整构造。
- Phase 1.5 流空闲字段 ``stream_idle_timeout_seconds`` /
  ``stream_idle_heartbeat_seconds`` 的语义校验。
"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import (
    JsonObjectStructuredOutputRequest,
    JsonSchemaStructuredOutputRequest,
    StructuredOutputCapability,
    validate_structured_output_request,
)

import dataclasses
from typing import TypeAlias

import pytest

from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    ClientCorrelationPolicy,
    DeepSeekReasoningEffort,
    DeepSeekThinkingExtension,
    GeminiThinkingExtension,
    GeminiThinkingLevel,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
    RunnerSpec,
)

_BaseSpecKwargValue: TypeAlias = (
    str
    | bool
    | float
    | int
    | dict[str, str]
    | ProviderRequestExtension
    | ClientCorrelationPolicy
    | StructuredOutputCapability
    | None
)


def _base_spec_kwargs() -> dict[str, _BaseSpecKwargValue]:
    """构造一份基础合法的 RunnerSpec 关键字参数。"""

    return {
        "provider": "openai",
        "model": "gpt-x",
        "endpoint": "https://example.com",
        "api_key_ref": "key",
        "headers": {},
        "client_correlation_policy": ClientCorrelationPolicy.DISABLED,
        "supports_tool_calling": False,
        "supports_streaming": True,
        "supports_stream_usage": False,
        "structured_output_capability": StructuredOutputCapability.NONE,
        "default_timeout_seconds": 30.0,
        "max_retries": 0,
        "provider_request": None,
    }


def test_openai_reasoning_effort_includes_none() -> None:
    """``OpenAIReasoningEffort`` 必须覆盖当前官方 reasoning 档位。"""

    assert OpenAIReasoningEffort.NONE.value == "none"
    assert {m.value for m in OpenAIReasoningEffort} == {
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "none",
    }


def test_deepseek_reasoning_effort_values() -> None:
    """DeepSeek thinking effort 仅表达当前官方高强度档位。"""

    assert {m.value for m in DeepSeekReasoningEffort} == {"high", "max"}


def test_gemini_thinking_level_values() -> None:
    """Gemini thinking level 必须覆盖 Gemini 3 当前官方档位。"""

    assert {m.value for m in GeminiThinkingLevel} == {
        "minimal",
        "low",
        "medium",
        "high",
    }


def test_client_correlation_policy_values() -> None:
    """客户端关联策略只表达 provider 协议 outbound 映射。"""

    assert {m.value for m in ClientCorrelationPolicy} == {
        "disabled",
        "openai_x_client_request_id",
    }


def test_anthropic_disabled_thinking_omits_budget() -> None:
    """Anthropic disabled thinking 用 ``None`` 表达不传 ``budget_tokens``。"""

    extension = AnthropicThinkingExtension(enabled=False)
    assert extension.budget_tokens is None


def test_anthropic_enabled_thinking_requires_budget() -> None:
    """Anthropic manual enabled thinking 必须显式提供正数预算。"""

    with pytest.raises(ValueError, match="requires"):
        AnthropicThinkingExtension(enabled=True)
    with pytest.raises(ValueError, match="must be > 0"):
        AnthropicThinkingExtension(enabled=True, budget_tokens=0)


def test_anthropic_disabled_thinking_rejects_budget() -> None:
    """Anthropic disabled thinking 不允许携带预算。"""

    with pytest.raises(ValueError, match="must not set"):
        AnthropicThinkingExtension(enabled=False, budget_tokens=1)


def test_deepseek_thinking_effort_defaults_to_omitted() -> None:
    """DeepSeek reasoning effort 默认 ``None``，表示不传字段。"""

    extension = DeepSeekThinkingExtension(enabled=True)
    assert extension.reasoning_effort is None


def test_deepseek_disabled_thinking_rejects_effort() -> None:
    """DeepSeek 关闭 thinking 时不允许携带 effort。"""

    with pytest.raises(ValueError, match="must not set"):
        DeepSeekThinkingExtension(
            enabled=False,
            reasoning_effort=DeepSeekReasoningEffort.HIGH,
        )


def test_gemini_thinking_extension_requires_some_field() -> None:
    """Gemini thinking extension 不能构造空 thinking_config。"""

    with pytest.raises(ValueError, match="requires"):
        GeminiThinkingExtension()


def test_gemini_thinking_budget_and_level_are_mutually_exclusive() -> None:
    """Gemini ``thinking_budget`` 与 ``thinking_level`` 不得同时设置。"""

    with pytest.raises(ValueError, match="cannot set both"):
        GeminiThinkingExtension(
            thinking_budget=1024,
            thinking_level=GeminiThinkingLevel.HIGH,
        )


def test_qwen_thinking_budget_defaults_to_omitted_and_must_be_positive() -> None:
    """Qwen ``thinking_budget`` 默认不传，显式传入时必须为正数。"""

    extension = QwenThinkingExtension(enable_thinking=True)
    assert extension.thinking_budget is None
    with pytest.raises(ValueError, match="must be > 0"):
        QwenThinkingExtension(enable_thinking=True, thinking_budget=0)


def test_qwen_disabled_thinking_rejects_budget() -> None:
    """Qwen 关闭 thinking 时不允许携带预算。"""

    with pytest.raises(ValueError, match="must not set"):
        QwenThinkingExtension(enable_thinking=False, thinking_budget=1)


def test_runner_spec_field_set_includes_supports_stream_usage() -> None:
    """``RunnerSpec`` 字段集合必须包含 ``supports_stream_usage`` 与 stream idle 字段。"""

    fields = {f.name for f in dataclasses.fields(RunnerSpec)}
    assert fields == {
        "provider",
        "model",
        "endpoint",
        "api_key_ref",
        "headers",
        "client_correlation_policy",
        "supports_tool_calling",
        "supports_streaming",
        "supports_stream_usage",
        "structured_output_capability",
        "default_timeout_seconds",
        "max_retries",
        "provider_request",
        "stream_idle_timeout_seconds",
        "stream_idle_heartbeat_seconds",
    }


def test_runner_spec_structured_output_capability_is_required() -> None:
    """RunnerSpec capability 必须是无 default 的 required 字段。"""

    field = next(
        item
        for item in dataclasses.fields(RunnerSpec)
        if item.name == "structured_output_capability"
    )

    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_structured_output_capability_values_are_closed() -> None:
    """StructuredOutputCapability 必须保持三值封闭枚举。"""

    assert {member.value for member in StructuredOutputCapability} == {
        "none",
        "json_object",
        "json_schema",
    }


@pytest.mark.parametrize(
    ("capability", "structured_request"),
    (
        (StructuredOutputCapability.NONE, None),
        (StructuredOutputCapability.JSON_OBJECT, None),
        (
            StructuredOutputCapability.JSON_OBJECT,
            JsonObjectStructuredOutputRequest(),
        ),
        (StructuredOutputCapability.JSON_SCHEMA, None),
        (
            StructuredOutputCapability.JSON_SCHEMA,
            JsonObjectStructuredOutputRequest(),
        ),
        (
            StructuredOutputCapability.JSON_SCHEMA,
            JsonSchemaStructuredOutputRequest(
                name="owner_schema",
                schema={"type": "object"},
                strict=True,
            ),
        ),
    ),
)
def test_structured_output_capability_matrix_accepts_valid_combinations(
    capability: StructuredOutputCapability,
    structured_request: (
        JsonObjectStructuredOutputRequest
        | JsonSchemaStructuredOutputRequest
        | None
    ),
) -> None:
    """Capability matrix 接受全部合法组合。

    :param capability: 被测 capability。
    :param structured_request: 被测 request。
    """

    validate_structured_output_request(
        capability=capability,
        request=structured_request,
    )


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
def test_structured_output_capability_matrix_rejects_invalid_combinations(
    capability: StructuredOutputCapability,
    structured_request: (
        JsonObjectStructuredOutputRequest | JsonSchemaStructuredOutputRequest
    ),
) -> None:
    """Capability matrix 在 transport 前拒绝全部非法组合。

    :param capability: 被测 capability。
    :param structured_request: 被测 request。
    """

    with pytest.raises(ValueError, match="does not support"):
        validate_structured_output_request(
            capability=capability,
            request=structured_request,
        )


@pytest.mark.parametrize("name", ("", " schema", "schema "))
def test_json_schema_request_rejects_invalid_name(name: str) -> None:
    """JSON Schema request 拒绝空名称与首尾空白。

    :param name: 被测 schema name。
    """

    with pytest.raises(ValueError, match="name"):
        JsonSchemaStructuredOutputRequest(
            name=name,
            schema={"type": "object"},
            strict=True,
        )


def test_json_schema_request_rejects_non_finite_json_number() -> None:
    """JSON Schema request 拒绝非有限 JSON number。"""

    with pytest.raises(ValueError, match="finite"):
        JsonSchemaStructuredOutputRequest(
            name="owner_schema",
            schema={"multipleOf": float("nan")},
            strict=True,
        )


def test_runner_spec_supports_stream_usage_true_construction() -> None:
    """``supports_stream_usage=True`` 时 ``RunnerSpec`` 完整构造合法。"""

    spec = RunnerSpec(
        provider="openai",
        model="gpt-x",
        endpoint="https://example.com",
        api_key_ref="key",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=True,
        structured_output_capability=StructuredOutputCapability.NONE,
        default_timeout_seconds=30.0,
        max_retries=2,
        provider_request=OpenAIReasoningExtension(
            reasoning_effort=OpenAIReasoningEffort.NONE
        ),
    )
    assert spec.supports_stream_usage is True
    assert spec.provider_request is not None


def test_runner_spec_supports_stream_usage_false_construction() -> None:
    """``supports_stream_usage=False`` 时 ``RunnerSpec`` 完整构造合法。"""

    spec = RunnerSpec(
        provider="openai",
        model="gpt-x",
        endpoint="https://example.com",
        api_key_ref="key",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        structured_output_capability=StructuredOutputCapability.NONE,
        default_timeout_seconds=30.0,
        max_retries=0,
        provider_request=None,
    )
    assert spec.supports_stream_usage is False


def test_runner_spec_rejects_static_openai_client_request_id_conflict() -> None:
    """policy 开启时 RunnerSpec 边界拒绝静态客户端关联 header。"""

    kwargs = _base_spec_kwargs()
    kwargs["client_correlation_policy"] = (
        ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
    )
    kwargs["headers"] = {"x-client-request-id": "static"}

    with pytest.raises(ValueError, match="X-Client-Request-Id"):
        RunnerSpec(**kwargs)  # type: ignore[arg-type]


def test_runner_spec_allows_static_openai_client_request_id_when_policy_disabled() -> None:
    """policy 关闭时静态 header 不与 per-call identity 发生语义冲突。"""

    kwargs = _base_spec_kwargs()
    kwargs["headers"] = {"X-Client-Request-Id": "static"}

    spec = RunnerSpec(**kwargs)  # type: ignore[arg-type]

    assert spec.headers["X-Client-Request-Id"] == "static"


def test_runner_spec_allows_none_api_key_ref_for_local_provider() -> None:
    """本地或免鉴权 provider 可用 ``None`` 表达不需要 API key。"""

    spec = RunnerSpec(
        provider="ollama",
        model="llama-local",
        endpoint="http://localhost:11434/v1/chat/completions",
        api_key_ref=None,
        headers={"Content-Type": "application/json"},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=True,
        structured_output_capability=StructuredOutputCapability.NONE,
        default_timeout_seconds=30.0,
        max_retries=0,
        provider_request=None,
    )
    assert spec.api_key_ref is None


def test_runner_spec_default_timeout_seconds_must_be_positive() -> None:
    """``default_timeout_seconds`` 非正数必须报错。"""

    for value in (0.0, -1.0):
        kwargs = _base_spec_kwargs()
        kwargs["default_timeout_seconds"] = value
        with pytest.raises(ValueError, match="default_timeout_seconds must be > 0"):
            RunnerSpec(**kwargs)  # type: ignore[arg-type]


def test_runner_spec_max_retries_must_be_non_negative() -> None:
    """``max_retries`` 为负数必须报错。"""

    kwargs = _base_spec_kwargs()
    kwargs["max_retries"] = -1
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        RunnerSpec(**kwargs)  # type: ignore[arg-type]


def test_runner_spec_stream_idle_defaults_to_none() -> None:
    """两个 stream idle 字段默认 ``None``。"""

    spec = RunnerSpec(**_base_spec_kwargs())  # type: ignore[arg-type]
    assert spec.stream_idle_timeout_seconds is None
    assert spec.stream_idle_heartbeat_seconds is None


def test_runner_spec_stream_idle_timeout_only_is_legal() -> None:
    """仅设置 timeout、不设置 heartbeat 合法。"""

    spec = RunnerSpec(
        **_base_spec_kwargs(),  # type: ignore[arg-type]
        stream_idle_timeout_seconds=10.0,
    )
    assert spec.stream_idle_timeout_seconds == 10.0
    assert spec.stream_idle_heartbeat_seconds is None


def test_runner_spec_stream_idle_heartbeat_without_timeout_raises() -> None:
    """只设置 heartbeat、不设置 timeout 必须报错。"""

    with pytest.raises(ValueError, match="requires"):
        RunnerSpec(
            **_base_spec_kwargs(),  # type: ignore[arg-type]
            stream_idle_heartbeat_seconds=1.0,
        )


def test_runner_spec_stream_idle_timeout_must_be_positive() -> None:
    """``stream_idle_timeout_seconds`` 非正数必须报错。"""

    for value in (0.0, -1.0):
        with pytest.raises(ValueError, match="must be > 0"):
            RunnerSpec(
                **_base_spec_kwargs(),  # type: ignore[arg-type]
                stream_idle_timeout_seconds=value,
            )


def test_runner_spec_stream_idle_heartbeat_must_be_positive() -> None:
    """``stream_idle_heartbeat_seconds`` 非正数必须报错。"""

    for value in (0.0, -0.1):
        with pytest.raises(ValueError, match="must be > 0"):
            RunnerSpec(
                **_base_spec_kwargs(),  # type: ignore[arg-type]
                stream_idle_timeout_seconds=10.0,
                stream_idle_heartbeat_seconds=value,
            )


def test_runner_spec_stream_idle_heartbeat_must_not_exceed_timeout() -> None:
    """heartbeat > timeout 必须报错；heartbeat == timeout 合法。"""

    with pytest.raises(ValueError, match="<= "):
        RunnerSpec(
            **_base_spec_kwargs(),  # type: ignore[arg-type]
            stream_idle_timeout_seconds=10.0,
            stream_idle_heartbeat_seconds=11.0,
        )
    # heartbeat == timeout 合法（plan 允许）
    spec = RunnerSpec(
        **_base_spec_kwargs(),  # type: ignore[arg-type]
        stream_idle_timeout_seconds=10.0,
        stream_idle_heartbeat_seconds=10.0,
    )
    assert spec.stream_idle_heartbeat_seconds == 10.0


def test_runner_spec_stream_idle_full_construction_legal() -> None:
    """合法 (timeout, heartbeat) 组合可构造。"""

    spec = RunnerSpec(
        **_base_spec_kwargs(),  # type: ignore[arg-type]
        stream_idle_timeout_seconds=10.0,
        stream_idle_heartbeat_seconds=2.0,
    )
    assert spec.stream_idle_timeout_seconds == 10.0
    assert spec.stream_idle_heartbeat_seconds == 2.0
