"""Provider request extension 配置 DSL 解析 helper。

本模块位于 Engine 层，因为解析目标是 Engine 专属的
``ProviderRequestExtension`` 封闭联合。它只负责把 runtime config 原样保留
的 JSON DSL 转为 Engine typed contract；未知 type、未知字段与非法枚举值
均 fail closed。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Protocol, TypeVar, cast

from dayu.contracts import JsonValue
from dayu.engine.contracts.runner_spec import (
    AnthropicThinkingExtension,
    DeepSeekReasoningEffort,
    DeepSeekThinkingExtension,
    GeminiThinkingLevel,
    GeminiThinkingExtension,
    MimoThinkingExtension,
    OpenAIReasoningEffort,
    OpenAIReasoningExtension,
    ProviderRequestExtension,
    QwenThinkingExtension,
)

_FIELD_TYPE: Final[str] = "type"
_FIELD_REASONING_EFFORT: Final[str] = "reasoning_effort"
_FIELD_ENABLED: Final[str] = "enabled"
_FIELD_BUDGET_TOKENS: Final[str] = "budget_tokens"
_FIELD_THINKING_BUDGET: Final[str] = "thinking_budget"
_FIELD_INCLUDE_THOUGHTS: Final[str] = "include_thoughts"
_FIELD_THINKING_LEVEL: Final[str] = "thinking_level"
_FIELD_ENABLE_THINKING: Final[str] = "enable_thinking"
_TYPE_OPENAI_REASONING: Final[str] = "openai_reasoning"
_TYPE_ANTHROPIC_THINKING: Final[str] = "anthropic_thinking"
_TYPE_DEEPSEEK_THINKING: Final[str] = "deepseek_thinking"
_TYPE_MIMO_THINKING: Final[str] = "mimo_thinking"
_TYPE_GEMINI_THINKING: Final[str] = "gemini_thinking"
_TYPE_QWEN_THINKING: Final[str] = "qwen_thinking"
_EnumT = TypeVar("_EnumT", bound=StrEnum)
_ExtensionT = TypeVar(
    "_ExtensionT",
    OpenAIReasoningExtension,
    AnthropicThinkingExtension,
    DeepSeekThinkingExtension,
    MimoThinkingExtension,
    GeminiThinkingExtension,
    QwenThinkingExtension,
    covariant=True,
)


class ProviderExtensionConfigError(ValueError):
    """provider request extension DSL 非法时抛出的错误。"""


def provider_request_extension_from_json(
    value: JsonValue,
) -> ProviderRequestExtension | None:
    """把 JSON DSL 解析为 Engine provider request extension。

    :param value: ConfigLoader 原样保留的 provider extension JSON 值。
    :returns: Engine typed provider request extension；``null`` 返回 ``None``。
    :raises ProviderExtensionConfigError: DSL 不是 object、未知 type、未知字段、
        字段类型非法、枚举值非法或字段组合非法时抛出。
    """

    if value is None:
        return None
    record = _require_json_object(value, context="provider_request_extension")
    extension_type = _require_str_field(
        record,
        field_name=_FIELD_TYPE,
        context="provider_request_extension",
    )
    if extension_type == _TYPE_OPENAI_REASONING:
        return _parse_openai_reasoning(record)
    if extension_type == _TYPE_ANTHROPIC_THINKING:
        return _parse_anthropic_thinking(record)
    if extension_type == _TYPE_DEEPSEEK_THINKING:
        return _parse_deepseek_thinking(record)
    if extension_type == _TYPE_MIMO_THINKING:
        return _parse_mimo_thinking(record)
    if extension_type == _TYPE_GEMINI_THINKING:
        return _parse_gemini_thinking(record)
    if extension_type == _TYPE_QWEN_THINKING:
        return _parse_qwen_thinking(record)
    raise ProviderExtensionConfigError(
        f"provider_request_extension has unsupported type: {extension_type}"
    )


def _parse_openai_reasoning(record: Mapping[str, JsonValue]) -> OpenAIReasoningExtension:
    """解析 OpenAI reasoning DSL。

    :param record: provider extension JSON object。
    :returns: OpenAI reasoning extension。
    :raises ProviderExtensionConfigError: 字段未知或枚举非法时抛出。
    """

    context = "provider_request_extension.openai_reasoning"
    _require_exact_fields(
        record,
        allowed=frozenset({_FIELD_TYPE, _FIELD_REASONING_EFFORT}),
        context=context,
    )
    effort = _parse_enum(
        OpenAIReasoningEffort,
        _require_str_field(record, field_name=_FIELD_REASONING_EFFORT, context=context),
        context=f"{context}.{_FIELD_REASONING_EFFORT}",
    )
    return _wrap_contract_error(
        lambda: OpenAIReasoningExtension(reasoning_effort=effort),
        context=context,
    )


def _parse_anthropic_thinking(
    record: Mapping[str, JsonValue],
) -> AnthropicThinkingExtension:
    """解析 Anthropic thinking DSL。

    :param record: provider extension JSON object。
    :returns: Anthropic thinking extension。
    :raises ProviderExtensionConfigError: 字段未知、类型非法或组合非法时抛出。
    """

    context = "provider_request_extension.anthropic_thinking"
    _require_exact_fields(
        record,
        allowed=frozenset({_FIELD_TYPE, _FIELD_ENABLED, _FIELD_BUDGET_TOKENS}),
        context=context,
    )
    return _wrap_contract_error(
        lambda: AnthropicThinkingExtension(
            enabled=_require_bool_field(
                record,
                field_name=_FIELD_ENABLED,
                context=context,
            ),
            budget_tokens=_optional_positive_int_field(
                record,
                field_name=_FIELD_BUDGET_TOKENS,
                context=context,
            ),
        ),
        context=context,
    )


def _parse_deepseek_thinking(
    record: Mapping[str, JsonValue],
) -> DeepSeekThinkingExtension:
    """解析 DeepSeek thinking DSL。

    :param record: provider extension JSON object。
    :returns: DeepSeek thinking extension。
    :raises ProviderExtensionConfigError: 字段未知、类型非法或组合非法时抛出。
    """

    context = "provider_request_extension.deepseek_thinking"
    _require_exact_fields(
        record,
        allowed=frozenset({_FIELD_TYPE, _FIELD_ENABLED, _FIELD_REASONING_EFFORT}),
        context=context,
    )
    effort_value = _optional_str_field(
        record,
        field_name=_FIELD_REASONING_EFFORT,
        context=context,
    )
    effort = (
        None
        if effort_value is None
        else _parse_enum(
            DeepSeekReasoningEffort,
            effort_value,
            context=f"{context}.{_FIELD_REASONING_EFFORT}",
        )
    )
    return _wrap_contract_error(
        lambda: DeepSeekThinkingExtension(
            enabled=_require_bool_field(
                record,
                field_name=_FIELD_ENABLED,
                context=context,
            ),
            reasoning_effort=effort,
        ),
        context=context,
    )


def _parse_mimo_thinking(record: Mapping[str, JsonValue]) -> MimoThinkingExtension:
    """解析 MiMo thinking DSL。

    :param record: provider extension JSON object。
    :returns: MiMo thinking extension。
    :raises ProviderExtensionConfigError: 字段未知或类型非法时抛出。
    """

    context = "provider_request_extension.mimo_thinking"
    _require_exact_fields(
        record,
        allowed=frozenset({_FIELD_TYPE, _FIELD_ENABLED}),
        context=context,
    )
    return _wrap_contract_error(
        lambda: MimoThinkingExtension(
            enabled=_require_bool_field(
                record,
                field_name=_FIELD_ENABLED,
                context=context,
            )
        ),
        context=context,
    )


def _parse_gemini_thinking(record: Mapping[str, JsonValue]) -> GeminiThinkingExtension:
    """解析 Gemini thinking DSL。

    :param record: provider extension JSON object。
    :returns: Gemini thinking extension。
    :raises ProviderExtensionConfigError: 字段未知、类型非法、枚举非法或组合非法时抛出。
    """

    context = "provider_request_extension.gemini_thinking"
    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                _FIELD_TYPE,
                _FIELD_THINKING_BUDGET,
                _FIELD_INCLUDE_THOUGHTS,
                _FIELD_THINKING_LEVEL,
            }
        ),
        context=context,
    )
    level_value = _optional_str_field(
        record,
        field_name=_FIELD_THINKING_LEVEL,
        context=context,
    )
    thinking_level = (
        None
        if level_value is None
        else _parse_enum(
            GeminiThinkingLevel,
            level_value,
            context=f"{context}.{_FIELD_THINKING_LEVEL}",
        )
    )
    return _wrap_contract_error(
        lambda: GeminiThinkingExtension(
            thinking_budget=_optional_int_field(
                record,
                field_name=_FIELD_THINKING_BUDGET,
                context=context,
            ),
            include_thoughts=_optional_bool_field(
                record,
                field_name=_FIELD_INCLUDE_THOUGHTS,
                context=context,
            ),
            thinking_level=thinking_level,
        ),
        context=context,
    )


def _parse_qwen_thinking(record: Mapping[str, JsonValue]) -> QwenThinkingExtension:
    """解析 Qwen thinking DSL。

    :param record: provider extension JSON object。
    :returns: Qwen thinking extension。
    :raises ProviderExtensionConfigError: 字段未知、类型非法或组合非法时抛出。
    """

    context = "provider_request_extension.qwen_thinking"
    _require_exact_fields(
        record,
        allowed=frozenset({_FIELD_TYPE, _FIELD_ENABLE_THINKING, _FIELD_THINKING_BUDGET}),
        context=context,
    )
    return _wrap_contract_error(
        lambda: QwenThinkingExtension(
            enable_thinking=_require_bool_field(
                record,
                field_name=_FIELD_ENABLE_THINKING,
                context=context,
            ),
            thinking_budget=_optional_positive_int_field(
                record,
                field_name=_FIELD_THINKING_BUDGET,
                context=context,
            ),
        ),
        context=context,
    )


def _require_json_object(value: JsonValue, *, context: str) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param context: 错误消息上下文。
    :returns: JSON object 映射。
    :raises ProviderExtensionConfigError: 值不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise ProviderExtensionConfigError(f"{context} must be an object or null")
    for key in value:
        if not isinstance(key, str):
            raise ProviderExtensionConfigError(f"{context} keys must be strings")
    return cast(Mapping[str, JsonValue], value)


def _require_exact_fields(
    record: Mapping[str, JsonValue], *, allowed: frozenset[str], context: str
) -> None:
    """校验 JSON object 字段集合。

    :param record: JSON object。
    :param allowed: 允许字段集合。
    :param context: 错误消息上下文。
    :returns: ``None``。
    :raises ProviderExtensionConfigError: 出现未知字段时抛出。
    """

    unknown = set(record) - allowed
    if unknown:
        raise ProviderExtensionConfigError(
            f"{context} has unknown fields: {sorted(unknown)}"
        )


def _require_str_field(
    record: Mapping[str, JsonValue], *, field_name: str, context: str
) -> str:
    """读取必填字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串字段。
    :raises ProviderExtensionConfigError: 字段缺失、为 null 或不是字符串时抛出。
    """

    value = record.get(field_name)
    if not isinstance(value, str):
        raise ProviderExtensionConfigError(f"{context}.{field_name} must be a string")
    if not value.strip():
        raise ProviderExtensionConfigError(
            f"{context}.{field_name} must be non-empty"
        )
    return value


def _optional_str_field(
    record: Mapping[str, JsonValue], *, field_name: str, context: str
) -> str | None:
    """读取可选字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串字段；缺失或 ``null`` 时返回 ``None``。
    :raises ProviderExtensionConfigError: 字段存在但不是字符串或为空时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = _require_str_field(record, field_name=field_name, context=context)
    return value


def _require_bool_field(
    record: Mapping[str, JsonValue], *, field_name: str, context: str
) -> bool:
    """读取必填 bool 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: bool 字段。
    :raises ProviderExtensionConfigError: 字段缺失或不是 bool 时抛出。
    """

    value = record.get(field_name)
    if not isinstance(value, bool):
        raise ProviderExtensionConfigError(f"{context}.{field_name} must be a boolean")
    return value


def _optional_bool_field(
    record: Mapping[str, JsonValue], *, field_name: str, context: str
) -> bool | None:
    """读取可选 bool 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: bool 字段；缺失或 ``null`` 时返回 ``None``。
    :raises ProviderExtensionConfigError: 字段存在但不是 bool 时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    return _require_bool_field(record, field_name=field_name, context=context)


def _optional_int_field(
    record: Mapping[str, JsonValue], *, field_name: str, context: str
) -> int | None:
    """读取可选整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 整数字段；缺失或 ``null`` 时返回 ``None``。
    :raises ProviderExtensionConfigError: 字段存在但不是整数时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProviderExtensionConfigError(f"{context}.{field_name} must be an integer")
    return value


def _optional_positive_int_field(
    record: Mapping[str, JsonValue], *, field_name: str, context: str
) -> int | None:
    """读取可选正整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正整数字段；缺失或 ``null`` 时返回 ``None``。
    :raises ProviderExtensionConfigError: 字段存在但不是正整数时抛出。
    """

    value = _optional_int_field(record, field_name=field_name, context=context)
    if value is not None and value <= 0:
        raise ProviderExtensionConfigError(f"{context}.{field_name} must be > 0")
    return value


def _parse_enum(
    enum_type: type[_EnumT],
    value: str,
    *,
    context: str,
) -> _EnumT:
    """解析 provider extension 枚举。

    :param enum_type: 目标 StrEnum 类型。
    :param value: JSON 字符串值。
    :param context: 错误消息上下文。
    :returns: 枚举成员。
    :raises ProviderExtensionConfigError: 值不属于目标枚举时抛出。
    """

    try:
        return enum_type(value)
    except ValueError as exc:
        raise ProviderExtensionConfigError(
            f"{context} has unsupported value: {value}"
        ) from exc


def _wrap_contract_error(
    factory: _ProviderExtensionFactory[_ExtensionT],
    *,
    context: str,
) -> _ExtensionT:
    """把 Engine contract 构造错误统一转换为 DSL 错误。

    :param factory: 构造 provider extension 的零参函数。
    :param context: 错误消息上下文。
    :returns: provider request extension。
    :raises ProviderExtensionConfigError: contract dataclass 拒绝字段组合时抛出。
    """

    try:
        return factory()
    except ValueError as exc:
        raise ProviderExtensionConfigError(f"{context} invalid field combination") from exc


class _ProviderExtensionFactory(Protocol[_ExtensionT]):
    """provider extension 工厂协议。

    :returns: provider request extension。
    """

    def __call__(self) -> _ExtensionT:
        """创建 provider request extension。

        :returns: provider request extension。
        """
        ...


__all__ = [
    "ProviderExtensionConfigError",
    "provider_request_extension_from_json",
]
