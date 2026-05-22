"""默认模型配置的 Engine 边界测试。"""

from __future__ import annotations

from dataclasses import fields

from dayu.runtime.config_loader import (
    ModelConfig,
    RunnerOptionHintConfig,
    load_runtime_config,
)


def test_default_models_do_not_use_extra_payloads_bag() -> None:
    """默认模型配置不得重新引入旧弱类型配置袋。"""

    config = load_runtime_config()
    model_fields = {field.name for field in fields(ModelConfig)}

    assert config.models.models
    assert "extra_payloads" not in model_fields
    assert "provider_request_extension" in model_fields


def test_default_models_keep_provider_extension_raw() -> None:
    """默认模型配置的 provider extension 由 ConfigLoader 原样保留。"""

    config = load_runtime_config()

    assert config.models.models["deepseek-v4-flash"].provider_request_extension == {
        "type": "deepseek_thinking",
        "enabled": False,
    }


def test_default_models_catalog_contains_migrated_legacy_records() -> None:
    """默认模型目录必须包含旧 llm_models.json 的全量模型 id。"""

    config = load_runtime_config()
    expected_model_ids = {
        "deepseek-v4-flash",
        "deepseek-v4-flash-thinking",
        "deepseek-v4-pro",
        "deepseek-v4-pro-thinking",
        "gpt-5.4",
        "gpt-5.4-thinking",
        "claude-sonnet-4-6",
        "claude-sonnet-4-6-thinking",
        "gemini-2.5-flash",
        "gemini-2.5-flash-thinking",
        "gemini-2.5-pro",
        "gemini-2.5-pro-thinking",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-lite-thinking",
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-thinking",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-flash-lite-preview-thinking",
        "mimo-v2.5-pro",
        "mimo-v2.5-pro-thinking",
        "mimo-v2.5-pro-plan",
        "mimo-v2.5-pro-thinking-plan",
        "mimo-v2.5-pro-plan-sg",
        "mimo-v2.5-pro-thinking-plan-sg",
        "qwen-plus",
        "qwen-plus-thinking",
        "ollama",
    }

    assert set(config.models.models) == expected_model_ids


def test_default_models_expose_runner_option_hints_without_output_cap() -> None:
    """默认模型目录不得通过 runner option hint 配置输出 token cap。"""

    config = load_runtime_config()
    model = config.models.models["qwen-plus"]
    hint = model.runtime_hints.runner_option_hints["conversation_compaction"]

    assert hint.temperature == 0.1
    assert hint.stream is False
    assert "max_tokens" not in {field.name for field in fields(RunnerOptionHintConfig)}
