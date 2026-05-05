"""默认模型配置的 Engine 边界测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue


def _load_llm_models() -> dict[str, JsonValue]:
    """读取默认模型配置。

    :returns: 默认模型配置 JSON 对象。
    :raises FileNotFoundError: 配置文件不存在时抛出。
    :raises json.JSONDecodeError: 配置不是合法 JSON 时抛出。
    """

    payload = json.loads(
        Path("dayu/config/llm_models.json").read_text(encoding="utf-8")
    )
    return cast(dict[str, JsonValue], payload)


def test_default_llm_models_do_not_use_extra_payloads_bag() -> None:
    """默认模型配置不得重新引入 ``extra_payloads`` 弱类型配置袋。"""

    data = _load_llm_models()
    model_entries = {
        key: value
        for key, value in data.items()
        if not key.startswith("_") and isinstance(value, dict)
    }

    assert model_entries
    for name, model_config in model_entries.items():
        assert "extra_payloads" not in model_config, name
        assert "supports_usage" not in model_config, name


def test_default_llm_models_use_known_provider_request_schema() -> None:
    """默认模型配置中的 provider request 必须使用受控 schema。"""

    allowed_types = {
        "openai_reasoning",
        "anthropic_thinking",
        "deepseek_thinking",
        "mimo_thinking",
        "gemini_thinking",
        "qwen_thinking",
    }
    data = _load_llm_models()
    model_entries = {
        key: value
        for key, value in data.items()
        if not key.startswith("_") and isinstance(value, dict)
    }

    for name, model_config in model_entries.items():
        provider_request = model_config.get("provider_request")
        if provider_request is None:
            continue
        assert isinstance(provider_request, dict), name
        request_type = provider_request.get("type")
        assert request_type in allowed_types, name
