"""runtime tool truncation effective spec 测试。"""

from __future__ import annotations

from typing import cast

import pytest

from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.runtime.tool_truncation import effective_tool_truncate_spec

_DEFAULT_TEXT_CHARS_LIMIT = 8
_DEFAULT_TTL_SECONDS = 30


def _disabled_spec() -> ToolTruncateSpec:
    """构造禁用截断声明。

    :returns: disabled truncate spec。
    """

    return ToolTruncateSpec(
        enabled=False,
        strategy=None,
        limits={},
        target_field=None,
        field_path=None,
        ttl_seconds=None,
    )


def _enabled_spec(
    *,
    limits: dict[str, int],
    ttl_seconds: int | None = None,
) -> ToolTruncateSpec:
    """构造 text_chars 截断声明。

    :param limits: 截断 limit 映射。
    :param ttl_seconds: cursor TTL 秒数。
    :returns: enabled truncate spec。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits=limits,
        target_field=None,
        field_path=None,
        ttl_seconds=ttl_seconds,
    )


def test_no_truncation_disabled_spec_returns_original() -> None:
    """disabled spec 表示不截断，effective helper 原样返回。"""

    declaration = _disabled_spec()

    effective = effective_tool_truncate_spec(
        declaration,
        default_limits_by_strategy={
            ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_LIMIT,
        },
        default_ttl_seconds=_DEFAULT_TTL_SECONDS,
    )

    assert effective is declaration


def test_exact_declared_threshold_is_preserved() -> None:
    """声明已给出精确阈值时，不被 policy default 覆盖。"""

    declaration = _enabled_spec(limits={"max_chars": 4}, ttl_seconds=12)

    effective = effective_tool_truncate_spec(
        declaration,
        default_limits_by_strategy={
            ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_LIMIT,
        },
        default_ttl_seconds=_DEFAULT_TTL_SECONDS,
    )

    assert effective.limits == {"max_chars": 4}
    assert effective.ttl_seconds == 12


def test_truncation_missing_limit_uses_policy_default() -> None:
    """启用截断且声明缺 limit 时，由 policy default 补齐。"""

    declaration = _enabled_spec(limits={})

    effective = effective_tool_truncate_spec(
        declaration,
        default_limits_by_strategy={
            ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_LIMIT,
        },
        default_ttl_seconds=_DEFAULT_TTL_SECONDS,
    )

    assert effective.limits == {"max_chars": _DEFAULT_TEXT_CHARS_LIMIT}
    assert effective.ttl_seconds == _DEFAULT_TTL_SECONDS


def test_empty_policy_defaults_reject_enabled_truncation() -> None:
    """启用截断但 policy 缺少默认 limit 时必须拒绝。"""

    declaration = _enabled_spec(limits={})

    with pytest.raises(ValueError, match="default limit missing"):
        effective_tool_truncate_spec(
            declaration,
            default_limits_by_strategy={},
            default_ttl_seconds=_DEFAULT_TTL_SECONDS,
        )


def test_multibyte_target_path_is_preserved_as_typed_spec() -> None:
    """多字节 target path 作为普通字段名保留，不按字节截断或改写。"""

    declaration = ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={},
        target_field=None,
        field_path=("正文",),
        ttl_seconds=None,
    )

    effective = effective_tool_truncate_spec(
        declaration,
        default_limits_by_strategy={
            ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_LIMIT,
        },
        default_ttl_seconds=_DEFAULT_TTL_SECONDS,
    )

    assert effective.field_path == ("正文",)
    assert effective.limits == {"max_chars": _DEFAULT_TEXT_CHARS_LIMIT}


def test_default_values_must_be_strict_ints() -> None:
    """默认 TTL 与 limit 必须是严格整数边界。"""

    declaration = _enabled_spec(limits={})

    with pytest.raises(TypeError, match="default_ttl_seconds"):
        effective_tool_truncate_spec(
            declaration,
            default_limits_by_strategy={
                ToolTruncationStrategy.TEXT_CHARS: _DEFAULT_TEXT_CHARS_LIMIT,
            },
            default_ttl_seconds=cast(int, True),
        )
    with pytest.raises(TypeError, match="text_chars"):
        effective_tool_truncate_spec(
            declaration,
            default_limits_by_strategy={
                ToolTruncationStrategy.TEXT_CHARS: cast(int, True),
            },
            default_ttl_seconds=_DEFAULT_TTL_SECONDS,
        )
