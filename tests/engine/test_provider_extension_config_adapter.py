"""provider extension JSON DSL 到 Engine typed contract 的解析测试。"""

from __future__ import annotations

import pytest

import dayu.engine.provider_extensions as provider_extensions
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
from dayu.engine.provider_extensions import (
    ProviderExtensionConfigError,
    provider_request_extension_from_json,
)
from dayu.runtime.config_loader import load_runtime_config


def _raise_openai_contract_error(
    *, reasoning_effort: OpenAIReasoningEffort
) -> OpenAIReasoningExtension:
    """模拟未来 OpenAI reasoning contract 在初始化时拒绝字段组合。

    :param reasoning_effort: 已解析的 OpenAI reasoning effort。
    :returns: 不返回；仅用于测试异常转换路径。
    :raises ValueError: 始终抛出以模拟 contract 校验失败。
    """

    raise ValueError(f"future OpenAI invariant rejected {reasoning_effort.value}")


def _raise_mimo_contract_error(*, enabled: bool) -> MimoThinkingExtension:
    """模拟未来 MiMo thinking contract 在初始化时拒绝字段组合。

    :param enabled: 已解析的 enabled 字段。
    :returns: 不返回；仅用于测试异常转换路径。
    :raises ValueError: 始终抛出以模拟 contract 校验失败。
    """

    raise ValueError(f"future MiMo invariant rejected {enabled}")


def test_provider_extension_dsl_supports_all_known_types() -> None:
    """所有已知 provider extension DSL 都能映射到当前 Engine typed union。"""

    assert provider_request_extension_from_json(
        {"type": "openai_reasoning", "reasoning_effort": "high"}
    ) == OpenAIReasoningExtension(
        reasoning_effort=OpenAIReasoningEffort.HIGH
    )
    assert provider_request_extension_from_json(
        {"type": "anthropic_thinking", "enabled": True, "budget_tokens": 8000}
    ) == AnthropicThinkingExtension(enabled=True, budget_tokens=8000)
    assert provider_request_extension_from_json(
        {
            "type": "deepseek_thinking",
            "enabled": True,
            "reasoning_effort": "max",
        }
    ) == DeepSeekThinkingExtension(
        enabled=True,
        reasoning_effort=DeepSeekReasoningEffort.MAX,
    )
    assert provider_request_extension_from_json(
        {"type": "mimo_thinking", "enabled": True}
    ) == MimoThinkingExtension(enabled=True)
    assert provider_request_extension_from_json(
        {
            "type": "gemini_thinking",
            "thinking_level": "high",
            "include_thoughts": True,
        }
    ) == GeminiThinkingExtension(
        include_thoughts=True,
        thinking_level=GeminiThinkingLevel.HIGH,
    )
    assert provider_request_extension_from_json(
        {
            "type": "qwen_thinking",
            "enable_thinking": True,
            "thinking_budget": 1024,
        }
    ) == QwenThinkingExtension(enable_thinking=True, thinking_budget=1024)


def test_provider_extension_dsl_parses_default_model_catalog() -> None:
    """默认模型目录中的 provider extension DSL 均可被 Engine helper 解析。"""

    config = load_runtime_config()
    parsed = {
        model_id: provider_request_extension_from_json(
            model.provider_request_extension
        )
        for model_id, model in config.models.models.items()
    }

    assert isinstance(parsed["deepseek-v4-flash"], DeepSeekThinkingExtension)
    assert isinstance(parsed["gpt-5.4-thinking"], OpenAIReasoningExtension)
    assert isinstance(parsed["claude-sonnet-4-6-thinking"], AnthropicThinkingExtension)
    assert isinstance(parsed["gemini-3.1-pro-preview-thinking"], GeminiThinkingExtension)
    assert isinstance(parsed["mimo-v2.5-pro-thinking"], MimoThinkingExtension)
    assert isinstance(parsed["qwen-plus-thinking"], QwenThinkingExtension)
    assert parsed["ollama"] is None


def test_provider_extension_dsl_fails_closed_for_unknown_type() -> None:
    """未知 provider extension type 必须 fail closed。"""

    with pytest.raises(ProviderExtensionConfigError, match="unsupported type"):
        provider_request_extension_from_json({"type": "future_extension"})


def test_provider_extension_dsl_fails_closed_for_unknown_fields() -> None:
    """已知 DSL 内出现未知字段必须 fail closed。"""

    with pytest.raises(ProviderExtensionConfigError, match="unknown fields"):
        provider_request_extension_from_json(
            {
                "type": "openai_reasoning",
                "reasoning_effort": "high",
                "temperature": 0.2,
            }
        )


def test_provider_extension_dsl_fails_closed_for_invalid_enum() -> None:
    """非法枚举值必须 fail closed。"""

    with pytest.raises(ProviderExtensionConfigError, match="unsupported value"):
        provider_request_extension_from_json(
            {"type": "gemini_thinking", "thinking_level": "extreme"}
        )


def test_provider_extension_dsl_fails_closed_for_invalid_combination() -> None:
    """Engine contract 拒绝的字段组合必须转换为 DSL 错误。"""

    with pytest.raises(ProviderExtensionConfigError, match="invalid field combination"):
        provider_request_extension_from_json(
            {"type": "qwen_thinking", "enable_thinking": False, "thinking_budget": 1}
        )


def test_provider_extension_dsl_wraps_openai_and_mimo_contract_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI 与 MiMo contract 校验失败也必须统一转换为 DSL 错误。"""

    monkeypatch.setattr(
        provider_extensions,
        "OpenAIReasoningExtension",
        _raise_openai_contract_error,
    )
    monkeypatch.setattr(
        provider_extensions,
        "MimoThinkingExtension",
        _raise_mimo_contract_error,
    )

    with pytest.raises(ProviderExtensionConfigError, match="invalid field combination"):
        provider_request_extension_from_json(
            {"type": "openai_reasoning", "reasoning_effort": "high"}
        )
    with pytest.raises(ProviderExtensionConfigError, match="invalid field combination"):
        provider_request_extension_from_json({"type": "mimo_thinking", "enabled": True})
