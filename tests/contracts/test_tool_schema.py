"""工具 schema 截断声明契约测试。"""

from __future__ import annotations

from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts import tool_schema as tool_schema_module
from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
    truncate_limit_key_for_strategy,
)


def test_tool_parameters_schema_requires_fields_inside_properties() -> None:
    """required 字段必须属于 properties，避免发布非法 LLM schema。"""

    with pytest.raises(ValueError, match="required"):
        ToolParametersSchema(
            type="object",
            properties={"known": {"type": "string"}},
            required=("missing",),
            additional_properties=False,
        )


def test_tool_parameters_schema_rejects_blank_property_key() -> None:
    """properties 字段名为空白时必须在构造期拒绝。"""

    with pytest.raises(ValueError, match="properties keys"):
        ToolParametersSchema(
            type="object",
            properties={" ": {"type": "string"}},
            required=(),
            additional_properties=False,
        )


@pytest.mark.parametrize(
    "bound_name",
    ("minLength", "maxLength", "minItems", "maxItems"),
)
@pytest.mark.parametrize("invalid_bound", (True, 1.5, "1"))
def test_tool_parameters_schema_rejects_non_integer_count_bounds(
    bound_name: str,
    invalid_bound: JsonValue,
) -> None:
    """字段 count bound 的 bool、float 与 string 必须在构造期拒绝。

    :param bound_name: 要校验的 JSON Schema count keyword。
    :param invalid_bound: 非法的非整数边界值。
    :returns: 无返回值。
    :raises AssertionError: schema 未抛出 ``TypeError`` 时由 pytest 抛出。
    """

    field_type = "string" if bound_name.endswith("Length") else "array"
    field_schema: dict[str, JsonValue] = {
        "type": field_type,
        bound_name: invalid_bound,
    }

    with pytest.raises(TypeError, match=bound_name):
        ToolParametersSchema(
            type="object",
            properties={"value": field_schema},
            required=(),
            additional_properties=False,
        )


@pytest.mark.parametrize(
    "bound_name",
    ("minLength", "maxLength", "minItems", "maxItems"),
)
def test_tool_parameters_schema_rejects_negative_count_bounds(
    bound_name: str,
) -> None:
    """字段 count bound 为负数时必须在构造期抛 ``ValueError``。

    :param bound_name: 要校验的 JSON Schema count keyword。
    :returns: 无返回值。
    :raises AssertionError: schema 未抛出 ``ValueError`` 时由 pytest 抛出。
    """

    field_type = "string" if bound_name.endswith("Length") else "array"
    field_schema: dict[str, JsonValue] = {
        "type": field_type,
        bound_name: -1,
    }

    with pytest.raises(ValueError, match=bound_name):
        ToolParametersSchema(
            type="object",
            properties={"value": field_schema},
            required=(),
            additional_properties=False,
        )


@pytest.mark.parametrize("bound_name", ("minLength", "maxLength"))
@pytest.mark.parametrize("invalid_bound", (True, 1.5, "1"))
def test_tool_parameters_schema_rejects_non_integer_array_item_bounds(
    bound_name: str,
    invalid_bound: JsonValue,
) -> None:
    """array items 的 string count bound 同样必须在构造期拒绝。

    :param bound_name: items string schema 的长度关键字。
    :param invalid_bound: 非法的非整数边界值。
    :returns: 无返回值。
    :raises AssertionError: schema 未抛出 ``TypeError`` 时由 pytest 抛出。
    """

    with pytest.raises(TypeError, match=f"items.{bound_name}"):
        ToolParametersSchema(
            type="object",
            properties={
                "values": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        bound_name: invalid_bound,
                    },
                }
            },
            required=(),
            additional_properties=False,
        )


@pytest.mark.parametrize("bound_name", ("minLength", "maxLength"))
def test_tool_parameters_schema_rejects_negative_array_item_bounds(
    bound_name: str,
) -> None:
    """array items 的负 string count bound 必须在构造期拒绝。

    :param bound_name: items string schema 的长度关键字。
    :returns: 无返回值。
    :raises AssertionError: schema 未抛出 ``ValueError`` 时由 pytest 抛出。
    """

    with pytest.raises(ValueError, match=f"items.{bound_name}"):
        ToolParametersSchema(
            type="object",
            properties={
                "values": {
                    "type": "array",
                    "items": {"type": "string", bound_name: -1},
                }
            },
            required=(),
            additional_properties=False,
        )


def test_tool_parameters_schema_accepts_zero_count_bounds() -> None:
    """四类 count bound 与 array item string bounds 都允许零。"""

    schema = ToolParametersSchema(
        type="object",
        properties={
            "text": {"type": "string", "minLength": 0, "maxLength": 0},
            "values": {
                "type": "array",
                "minItems": 0,
                "maxItems": 0,
                "items": {
                    "type": "string",
                    "minLength": 0,
                    "maxLength": 0,
                },
            },
        },
        required=(),
        additional_properties=False,
    )

    assert schema.properties["text"] == {
        "type": "string",
        "minLength": 0,
        "maxLength": 0,
    }


def test_enabled_truncate_spec_requires_enum_strategy_and_matching_limit() -> None:
    """启用截断时必须使用枚举策略与对应正整数 limit。"""

    spec = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": 8},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )

    assert spec.strategy is ToolTruncationStrategy.TEXT_CHARS


def test_truncate_limit_key_mapping_covers_all_strategies() -> None:
    """所有截断策略都必须有稳定 limit key 映射。"""

    assert {
        strategy: truncate_limit_key_for_strategy(strategy)
        for strategy in ToolTruncationStrategy
    } == {
        ToolTruncationStrategy.TEXT_CHARS: "max_chars",
        ToolTruncationStrategy.TEXT_LINES: "max_lines",
        ToolTruncationStrategy.LIST_ITEMS: "max_items",
        ToolTruncationStrategy.BINARY_BYTES: "max_bytes",
    }


def test_truncate_limit_key_rejects_missing_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """枚举成员缺少 limit key 映射时抛 ValueError 而不是 KeyError。"""

    monkeypatch.setattr(
        tool_schema_module,
        "_TRUNCATE_LIMIT_KEYS_BY_STRATEGY",
        {
            ToolTruncationStrategy.TEXT_LINES: "max_lines",
            ToolTruncationStrategy.LIST_ITEMS: "max_items",
            ToolTruncationStrategy.BINARY_BYTES: "max_bytes",
        },
    )

    with pytest.raises(ValueError, match="limit key mapping"):
        truncate_limit_key_for_strategy(ToolTruncationStrategy.TEXT_CHARS)


def test_enabled_truncate_spec_allows_empty_limits_for_runtime_policy_fill() -> None:
    """启用截断可省略 limit，由 runtime assembly policy 默认值补齐。"""

    spec = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )

    assert spec.limits == {}


def test_truncate_spec_rejects_raw_string_strategy() -> None:
    """截断策略不得用历史字符串绕过枚举契约。"""

    with pytest.raises(TypeError, match="strategy"):
        ToolTruncateSpec(
            enabled=True,
            strategy=cast(ToolTruncationStrategy, "text_chars"),
            limits={"max_chars": 8},
            target_field=None,
            field_path=None,
            ttl_seconds=None,
        )


@pytest.mark.parametrize(
    ("enabled", "strategy", "limits"),
    (
        (True, None, {"max_chars": 8}),
        (True, ToolTruncationStrategy.TEXT_CHARS, {"max_lines": 8}),
        (True, ToolTruncationStrategy.TEXT_CHARS, {"max_chars": 0}),
        (False, ToolTruncationStrategy.TEXT_CHARS, {}),
        (False, None, {"max_chars": 8}),
    ),
)
def test_truncate_spec_rejects_inconsistent_enabled_strategy_limits(
    enabled: bool,
    strategy: ToolTruncationStrategy | None,
    limits: dict[str, int],
) -> None:
    """``enabled`` / ``strategy`` / ``limits`` 不一致时必须构造失败。"""

    with pytest.raises(ValueError):
        ToolTruncateSpec(
            enabled=enabled,
            strategy=strategy,
            limits=limits,
            target_field=None,
            field_path=None,
            ttl_seconds=None,
        )


@pytest.mark.parametrize(
    ("target_field", "field_path", "ttl_seconds"),
    (
        ("content", None, None),
        (None, ("items",), None),
        (None, None, 60),
    ),
)
def test_disabled_truncate_spec_rejects_target_or_ttl_fields(
    target_field: str | None,
    field_path: tuple[str, ...] | None,
    ttl_seconds: int | None,
) -> None:
    """禁用截断时不得携带 target / TTL 字段。"""

    with pytest.raises(ValueError, match="disabled ToolTruncateSpec"):
        ToolTruncateSpec(
            enabled=False,
            strategy=None,
            limits={},
            target_field=target_field,
            field_path=field_path,
            ttl_seconds=ttl_seconds,
        )
