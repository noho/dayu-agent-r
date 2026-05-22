"""工具 schema 截断声明契约测试。"""

from __future__ import annotations

from typing import cast

import pytest

from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
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
