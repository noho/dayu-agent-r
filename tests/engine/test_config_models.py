"""默认模型配置的 Engine 边界测试。"""

from __future__ import annotations

from dataclasses import fields

from dayu.runtime.config_loader import ModelConfig, load_runtime_config


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

    assert config.models.models["deepseek-chat"].provider_request_extension == {
        "type": "deepseek_thinking",
        "enabled": False,
    }
