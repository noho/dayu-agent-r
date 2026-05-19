"""Host 内部 execution config JSON 投影辅助函数。

本模块统一维护 Host 在 admission、command semantic digest 与 dispatch
之间共享的 RunnerSpec、RunnerCallOptions、AgentPolicy、provider request
JSON 投影与还原逻辑。它不定义 public API，也不改变 EventLog payload
shape、digest 语义或 durable schema。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    DeepSeekReasoningEffort,
    DeepSeekThinkingExtension,
    GeminiThinkingExtension,
    GeminiThinkingLevel,
    MimoThinkingExtension,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host.durable.codec import sha256_digest_json

_POLICY_SNAPSHOT_REF_PREFIX = "policy:"


@dataclass(frozen=True, slots=True)
class EffectiveExecutionSnapshot:
    """从冻结 execution config 还原出的 policy snapshot 字段。

    :param runner_spec: 冻结的 RunnerSpec。
    :param runner_options: 冻结的 RunnerCallOptions。
    :param agent_policy: 冻结的 AgentPolicy。
    :param policy_snapshot_ref: admission 写入的 policy snapshot ref。
    """

    runner_spec: RunnerSpec
    runner_options: RunnerCallOptions
    agent_policy: AgentPolicy
    policy_snapshot_ref: str


def effective_execution_config_json(
    *,
    runner_spec: RunnerSpec,
    runner_options: RunnerCallOptions,
    agent_policy: AgentPolicy,
    runner_spec_source: str,
    runner_options_source: str,
    agent_policy_source: str,
) -> JsonValue:
    """构造 effective execution config 冻结 JSON。

    :param runner_spec: effective RunnerSpec。
    :param runner_options: effective RunnerCallOptions。
    :param agent_policy: effective AgentPolicy。
    :param runner_spec_source: RunnerSpec 来源。
    :param runner_options_source: RunnerCallOptions 来源。
    :param agent_policy_source: AgentPolicy 来源。
    :returns: 可写入 ``USER_INPUT_ACCEPTED`` payload 的 JSON mapping。
    :raises TypeError: RunnerSpec 中包含未知 provider request extension 时抛出。
    """

    config: JsonValue = {
        "runner_spec": runner_spec_json(runner_spec),
        "runner_options": runner_options_json(runner_options),
        "agent_policy": agent_policy_json(agent_policy),
        "sources": {
            "runner_spec": runner_spec_source,
            "runner_options": runner_options_source,
            "agent_policy": agent_policy_source,
        },
    }
    digest = sha256_digest_json(config)
    return {
        "policy_snapshot_ref": _POLICY_SNAPSHOT_REF_PREFIX + digest,
        "policy_snapshot_digest": digest,
        "config": config,
    }


def effective_execution_snapshot_from_json(
    value: JsonValue,
) -> EffectiveExecutionSnapshot:
    """从冻结 execution config JSON 还原 dispatch policy snapshot 字段。

    :param value: ``effective_execution_config`` JSON。
    :returns: 还原后的 execution snapshot 字段。
    :raises RuntimeError: JSON shape 非法时抛出。
    """

    root = required_json_mapping(value, field_name="effective_execution_config")
    policy_snapshot_ref = required_json_text(root, field_name="policy_snapshot_ref")
    config = required_json_mapping(root.get("config"), field_name="config")
    return EffectiveExecutionSnapshot(
        runner_spec=runner_spec_from_json(
            required_json_mapping(config.get("runner_spec"), field_name="runner_spec")
        ),
        runner_options=runner_options_from_json(
            required_json_mapping(
                config.get("runner_options"), field_name="runner_options"
            )
        ),
        agent_policy=agent_policy_from_json(
            required_json_mapping(config.get("agent_policy"), field_name="agent_policy")
        ),
        policy_snapshot_ref=policy_snapshot_ref,
    )


def optional_runner_spec_json(runner_spec: RunnerSpec | None) -> JsonValue:
    """把可选 RunnerSpec 投影为 JSON digest 输入。

    :param runner_spec: 可选 RunnerSpec。
    :returns: JSON digest 输入值。
    :raises TypeError: RunnerSpec 中包含未知 provider request extension 时抛出。
    """

    if runner_spec is None:
        return None
    return runner_spec_json(runner_spec)


def runner_spec_json(runner_spec: RunnerSpec) -> JsonValue:
    """把 RunnerSpec 投影为冻结 JSON。

    :param runner_spec: RunnerSpec。
    :returns: JSON mapping。
    :raises TypeError: RunnerSpec 中包含未知 provider request extension 时抛出。
    """

    return {
        "provider": runner_spec.provider,
        "model": runner_spec.model,
        "endpoint": runner_spec.endpoint,
        "api_key_ref": runner_spec.api_key_ref,
        "headers": dict(sorted(runner_spec.headers.items())),
        "supports_tool_calling": runner_spec.supports_tool_calling,
        "supports_streaming": runner_spec.supports_streaming,
        "supports_stream_usage": runner_spec.supports_stream_usage,
        "default_timeout_seconds": runner_spec.default_timeout_seconds,
        "max_retries": runner_spec.max_retries,
        "provider_request": provider_request_json(runner_spec.provider_request),
        "stream_idle_timeout_seconds": runner_spec.stream_idle_timeout_seconds,
        "stream_idle_heartbeat_seconds": runner_spec.stream_idle_heartbeat_seconds,
    }


def runner_spec_from_json(value: Mapping[str, JsonValue]) -> RunnerSpec:
    """从冻结 JSON 还原 RunnerSpec。

    :param value: RunnerSpec JSON mapping。
    :returns: RunnerSpec。
    :raises RuntimeError: JSON shape 或字段类型非法时抛出。
    :raises ValueError: provider 枚举值或 RunnerSpec 字段语义非法时抛出。
    """

    return RunnerSpec(
        provider=required_json_text(value, field_name="provider"),
        model=required_json_text(value, field_name="model"),
        endpoint=required_json_text(value, field_name="endpoint"),
        api_key_ref=required_json_text(value, field_name="api_key_ref"),
        headers=_headers_from_json(value.get("headers")),
        supports_tool_calling=required_json_bool(
            value, field_name="supports_tool_calling"
        ),
        supports_streaming=required_json_bool(
            value, field_name="supports_streaming"
        ),
        supports_stream_usage=required_json_bool(
            value, field_name="supports_stream_usage"
        ),
        default_timeout_seconds=required_json_float(
            value, field_name="default_timeout_seconds"
        ),
        max_retries=required_json_int(value, field_name="max_retries"),
        provider_request=provider_request_from_json(value.get("provider_request")),
        stream_idle_timeout_seconds=optional_json_float(
            value, field_name="stream_idle_timeout_seconds"
        ),
        stream_idle_heartbeat_seconds=optional_json_float(
            value, field_name="stream_idle_heartbeat_seconds"
        ),
    )


def provider_request_json(
    provider_request: ProviderRequestExtension | None,
) -> JsonValue:
    """把 provider request extension 投影为冻结 JSON。

    :param provider_request: provider extension 或 ``None``。
    :returns: JSON mapping 或 ``None``。
    :raises TypeError: 遇到未知 extension 类型时抛出。
    """

    if provider_request is None:
        return None
    if isinstance(provider_request, OpenAIReasoningExtension):
        return {
            "kind": "openai_reasoning",
            "reasoning_effort": provider_request.reasoning_effort.value,
        }
    if isinstance(provider_request, AnthropicThinkingExtension):
        return {
            "kind": "anthropic_thinking",
            "enabled": provider_request.enabled,
            "budget_tokens": provider_request.budget_tokens,
        }
    if isinstance(provider_request, DeepSeekThinkingExtension):
        return {
            "kind": "deepseek_thinking",
            "enabled": provider_request.enabled,
            "reasoning_effort": (
                None
                if provider_request.reasoning_effort is None
                else provider_request.reasoning_effort.value
            ),
        }
    if isinstance(provider_request, MimoThinkingExtension):
        return {"kind": "mimo_thinking", "enabled": provider_request.enabled}
    if isinstance(provider_request, GeminiThinkingExtension):
        return {
            "kind": "gemini_thinking",
            "thinking_budget": provider_request.thinking_budget,
            "include_thoughts": provider_request.include_thoughts,
            "thinking_level": (
                None
                if provider_request.thinking_level is None
                else provider_request.thinking_level.value
            ),
        }
    if isinstance(provider_request, QwenThinkingExtension):
        return {
            "kind": "qwen_thinking",
            "enable_thinking": provider_request.enable_thinking,
            "thinking_budget": provider_request.thinking_budget,
        }
    raise TypeError("unsupported provider request extension")


def provider_request_from_json(value: JsonValue) -> ProviderRequestExtension | None:
    """从冻结 JSON 还原 provider request extension。

    :param value: provider extension JSON。
    :returns: provider extension 或 ``None``。
    :raises RuntimeError: kind 未知或字段非法时抛出。
    :raises ValueError: provider 枚举值或 extension 字段组合非法时抛出。
    """

    if value is None:
        return None
    root = required_json_mapping(value, field_name="provider_request")
    kind = required_json_text(root, field_name="kind")
    if kind == "openai_reasoning":
        return OpenAIReasoningExtension(
            reasoning_effort=OpenAIReasoningEffort(
                required_json_text(root, field_name="reasoning_effort")
            )
        )
    if kind == "anthropic_thinking":
        return AnthropicThinkingExtension(
            enabled=required_json_bool(root, field_name="enabled"),
            budget_tokens=optional_json_int(root, field_name="budget_tokens"),
        )
    if kind == "deepseek_thinking":
        effort = optional_json_text(root, field_name="reasoning_effort")
        return DeepSeekThinkingExtension(
            enabled=required_json_bool(root, field_name="enabled"),
            reasoning_effort=(
                None if effort is None else DeepSeekReasoningEffort(effort)
            ),
        )
    if kind == "mimo_thinking":
        return MimoThinkingExtension(
            enabled=required_json_bool(root, field_name="enabled")
        )
    if kind == "gemini_thinking":
        level = optional_json_text(root, field_name="thinking_level")
        return GeminiThinkingExtension(
            thinking_budget=optional_json_int(root, field_name="thinking_budget"),
            include_thoughts=optional_json_bool(root, field_name="include_thoughts"),
            thinking_level=None if level is None else GeminiThinkingLevel(level),
        )
    if kind == "qwen_thinking":
        return QwenThinkingExtension(
            enable_thinking=required_json_bool(root, field_name="enable_thinking"),
            thinking_budget=optional_json_int(root, field_name="thinking_budget"),
        )
    raise RuntimeError(f"unknown provider_request kind: {kind}")


def optional_runner_options_json(
    runner_options: RunnerCallOptions | None,
) -> JsonValue:
    """把可选 RunnerCallOptions 投影为 JSON digest 输入。

    :param runner_options: 可选 RunnerCallOptions。
    :returns: JSON digest 输入值。
    :raises: 无主动抛出。
    """

    if runner_options is None:
        return None
    return runner_options_json(runner_options)


def runner_options_json(runner_options: RunnerCallOptions) -> JsonValue:
    """把 RunnerCallOptions 投影为冻结 JSON。

    :param runner_options: RunnerCallOptions。
    :returns: JSON mapping。
    :raises: 无主动抛出。
    """

    return {
        "temperature": runner_options.temperature,
        "max_tokens": runner_options.max_tokens,
        "top_p": runner_options.top_p,
        "stream": runner_options.stream,
    }


def runner_options_from_json(value: Mapping[str, JsonValue]) -> RunnerCallOptions:
    """从冻结 JSON 还原 RunnerCallOptions。

    :param value: RunnerCallOptions JSON mapping。
    :returns: RunnerCallOptions。
    :raises RuntimeError: JSON shape 或字段类型非法时抛出。
    """

    return RunnerCallOptions(
        temperature=optional_json_float(value, field_name="temperature"),
        max_tokens=optional_json_int(value, field_name="max_tokens"),
        top_p=optional_json_float(value, field_name="top_p"),
        stream=required_json_bool(value, field_name="stream"),
    )


def optional_agent_policy_json(agent_policy: AgentPolicy | None) -> JsonValue:
    """把可选 AgentPolicy 投影为 JSON digest 输入。

    :param agent_policy: 可选 AgentPolicy。
    :returns: JSON digest 输入值。
    :raises: 无主动抛出。
    """

    if agent_policy is None:
        return None
    return agent_policy_json(agent_policy)


def agent_policy_json(agent_policy: AgentPolicy) -> JsonValue:
    """把 AgentPolicy 投影为冻结 JSON。

    :param agent_policy: AgentPolicy。
    :returns: JSON mapping。
    :raises: 无主动抛出。
    """

    return {
        "max_iterations": agent_policy.max_iterations,
        "continuation_max_attempts": agent_policy.continuation_max_attempts,
        "allow_tool_calls": agent_policy.allow_tool_calls,
        "tool_execution_timeout_seconds": (
            agent_policy.tool_execution_timeout_seconds
        ),
        "fallback_mode": agent_policy.fallback_mode.value,
        "fallback_prompt": agent_policy.fallback_prompt,
        "continuation_prompt": agent_policy.continuation_prompt,
        "max_consecutive_failed_tool_batches": (
            agent_policy.max_consecutive_failed_tool_batches
        ),
    }


def agent_policy_from_json(value: Mapping[str, JsonValue]) -> AgentPolicy:
    """从冻结 JSON 还原 AgentPolicy。

    :param value: AgentPolicy JSON mapping。
    :returns: AgentPolicy。
    :raises RuntimeError: JSON shape 或字段类型非法时抛出。
    :raises ValueError: fallback mode 枚举值或 AgentPolicy 字段语义非法时抛出。
    """

    return AgentPolicy(
        max_iterations=required_json_int(value, field_name="max_iterations"),
        continuation_max_attempts=required_json_int(
            value, field_name="continuation_max_attempts"
        ),
        allow_tool_calls=required_json_bool(value, field_name="allow_tool_calls"),
        tool_execution_timeout_seconds=required_json_float(
            value, field_name="tool_execution_timeout_seconds"
        ),
        fallback_mode=AgentFallbackMode(
            required_json_text(value, field_name="fallback_mode")
        ),
        fallback_prompt=required_json_text(value, field_name="fallback_prompt"),
        continuation_prompt=required_json_text(
            value, field_name="continuation_prompt"
        ),
        max_consecutive_failed_tool_batches=required_json_int(
            value, field_name="max_consecutive_failed_tool_batches"
        ),
    )


def required_json_mapping(
    value: JsonValue, *, field_name: str
) -> Mapping[str, JsonValue]:
    """读取必填 JSON object。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON mapping。
    :raises RuntimeError: 值不是 mapping 时抛出。
    """

    if not isinstance(value, Mapping):
        raise RuntimeError(f"{field_name} must be JSON object")
    return cast(Mapping[str, JsonValue], value)


def required_json_text(value: Mapping[str, JsonValue], *, field_name: str) -> str:
    """读取必填 JSON 文本字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises RuntimeError: 字段缺失、非字符串或为空时抛出。
    """

    item = value.get(field_name)
    if not isinstance(item, str) or item.strip() == "":
        raise RuntimeError(f"{field_name} must be non-empty text")
    return item


def optional_json_text(
    value: Mapping[str, JsonValue], *, field_name: str
) -> str | None:
    """读取可选 JSON 文本字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises RuntimeError: 字段非字符串或为空时抛出。
    """

    item = value.get(field_name)
    if item is None:
        return None
    if isinstance(item, str) and item.strip() != "":
        return item
    raise RuntimeError(f"{field_name} must be non-empty text")


def required_json_bool(value: Mapping[str, JsonValue], *, field_name: str) -> bool:
    """读取必填 JSON bool 字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: bool 值。
    :raises RuntimeError: 字段不是 bool 时抛出。
    """

    item = value.get(field_name)
    if not isinstance(item, bool):
        raise RuntimeError(f"{field_name} must be bool")
    return item


def optional_json_bool(
    value: Mapping[str, JsonValue], *, field_name: str
) -> bool | None:
    """读取可选 JSON bool 字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: bool 值或 ``None``。
    :raises RuntimeError: 字段不是 bool 时抛出。
    """

    item = value.get(field_name)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise RuntimeError(f"{field_name} must be bool")
    return item


def required_json_int(value: Mapping[str, JsonValue], *, field_name: str) -> int:
    """读取必填 JSON int 字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: int 值。
    :raises RuntimeError: 字段不是严格 int 时抛出。
    """

    item = value.get(field_name)
    if isinstance(item, bool) or not isinstance(item, int):
        raise RuntimeError(f"{field_name} must be int")
    return item


def optional_json_int(
    value: Mapping[str, JsonValue], *, field_name: str
) -> int | None:
    """读取可选 JSON int 字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: int 值或 ``None``。
    :raises RuntimeError: 字段不是严格 int 时抛出。
    """

    item = value.get(field_name)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int):
        raise RuntimeError(f"{field_name} must be int")
    return item


def required_json_float(value: Mapping[str, JsonValue], *, field_name: str) -> float:
    """读取必填 JSON 数值字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: float 值。
    :raises RuntimeError: 字段不是数值时抛出。
    """

    item = value.get(field_name)
    if isinstance(item, bool) or not isinstance(item, int | float):
        raise RuntimeError(f"{field_name} must be number")
    return float(item)


def optional_json_float(
    value: Mapping[str, JsonValue], *, field_name: str
) -> float | None:
    """读取可选 JSON 数值字段。

    :param value: JSON mapping。
    :param field_name: 字段名。
    :returns: float 值或 ``None``。
    :raises RuntimeError: 字段不是数值时抛出。
    """

    item = value.get(field_name)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int | float):
        raise RuntimeError(f"{field_name} must be number")
    return float(item)


def _headers_from_json(value: JsonValue) -> Mapping[str, str]:
    """从冻结 JSON 还原 header 映射。

    :param value: headers JSON。
    :returns: 字符串 header 映射。
    :raises RuntimeError: 字段非法时抛出。
    """

    root = required_json_mapping(value, field_name="headers")
    result: dict[str, str] = {}
    for key, item in root.items():
        if not isinstance(item, str):
            raise RuntimeError("RunnerSpec.headers values must be text")
        result[key] = item
    return result
