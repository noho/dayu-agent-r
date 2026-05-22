"""Tool truncation declaration 到 effective spec 的层中立装配 helper。

本模块只消费 ``dayu.contracts`` 中的工具截断契约和调用方提供的 policy
默认值，不导入 Host、Engine、Service、UI 或 Fins。它负责把允许缺省
limit / TTL 的声明补齐为 ToolRuntime 可直接消费的 effective spec。
"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.tool_schema import (
    ToolTruncateSpec,
    ToolTruncationStrategy,
    truncate_limit_key_for_strategy,
)


def effective_tool_truncate_spec(
    declaration: ToolTruncateSpec,
    *,
    default_limits_by_strategy: Mapping[ToolTruncationStrategy, int],
    default_ttl_seconds: int,
) -> ToolTruncateSpec:
    """补齐截断声明，返回 complete effective spec。

    :param declaration: 工具发布方声明的截断 spec。
    :param default_limits_by_strategy: policy 提供的各策略默认 limit。
    :param default_ttl_seconds: policy 提供的默认 cursor TTL 秒数。
    :returns: 已补齐 limit 与 TTL 的 effective spec；disabled spec 原样返回。
    :raises TypeError: 输入类型或默认值类型非法时抛出。
    :raises ValueError: enabled 声明缺少策略默认 limit 或默认值非法时抛出。
    """

    if not isinstance(declaration, ToolTruncateSpec):
        raise TypeError("declaration must be ToolTruncateSpec")
    _require_non_negative_int(
        default_ttl_seconds, field_name="default_ttl_seconds"
    )
    if not declaration.enabled:
        return declaration
    strategy = declaration.strategy
    if strategy is None:
        raise ValueError("enabled declaration requires strategy")
    limit_key = truncate_limit_key_for_strategy(strategy)
    limits = dict(declaration.limits)
    if limit_key not in limits:
        default_limit = _default_limit(
            default_limits_by_strategy, strategy=strategy
        )
        limits[limit_key] = default_limit
    ttl_seconds = (
        declaration.ttl_seconds
        if declaration.ttl_seconds is not None
        else default_ttl_seconds
    )
    return ToolTruncateSpec(
        enabled=declaration.enabled,
        strategy=strategy,
        limits=limits,
        target_field=declaration.target_field,
        field_path=declaration.field_path,
        ttl_seconds=ttl_seconds,
    )


def _default_limit(
    default_limits_by_strategy: Mapping[ToolTruncationStrategy, int],
    *,
    strategy: ToolTruncationStrategy,
) -> int:
    """读取并校验指定策略的默认 limit。

    :param default_limits_by_strategy: policy 默认 limit 映射。
    :param strategy: 截断策略。
    :returns: 正整数默认 limit。
    :raises ValueError: 默认 limit 缺失或非法时抛出。
    """

    limit = default_limits_by_strategy.get(strategy)
    if limit is None:
        raise ValueError(f"default limit missing for strategy {strategy.value}")
    _require_positive_int(
        limit, field_name=f"default_limits_by_strategy.{strategy.value}"
    )
    return limit


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验正整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是整数或为 bool 时抛出。
    :raises ValueError: 值小于 1 时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验非负整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是整数或为 bool 时抛出。
    :raises ValueError: 值小于 0 时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


__all__ = ["effective_tool_truncate_spec"]
