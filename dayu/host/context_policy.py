"""Host context budget policy typed contract。

本模块只定义 Host Context Governance 需要的预算策略输入与 provider
边界。预算窗口必须由 Service / composition root 显式装配进 Host policy；
soft / hard 阈值由 Host 按 context window ratio 派生。本模块不读取
Engine spec、metadata、extra payload 或 provider overflow 诊断信息。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from dayu.host._public_validation import require_non_empty as _require_non_empty
from dayu.host._public_validation import require_positive_int as _require_positive_int

DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO = 0.8
DEFAULT_HARD_THRESHOLD_CONTEXT_RATIO = 0.9
DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN = 1
DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 2
DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = 5
DEFAULT_CONTEXT_BUDGET_POLICY_REF = "host-context-budget-policy:default"
MIN_CONTEXT_HARD_THRESHOLD_TOKENS = 2


class ContextCompactionTriggerSource(StrEnum):
    """Context compaction 触发来源。

    成员：

    - ``PROACTIVE``：Host dispatch 前预算治理触发。
    - ``REACTIVE``：Engine provider overflow fallback 触发。
    """

    PROACTIVE = "proactive"
    REACTIVE = "reactive"


@dataclass(frozen=True, slots=True)
class ContextBudgetPolicy:
    """Host context budget policy。

    :param context_window_size: Service / composition root 显式传入的上下文窗口 token 数。
    :param soft_threshold_context_ratio: soft threshold 占上下文窗口比例。
    :param hard_threshold_context_ratio: hard threshold 占上下文窗口比例。
    :param max_proactive_compactions_per_run: 单个 Run 允许的 proactive compact 次数。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :param max_compaction_attempts_per_operation: 单次 compaction operation 内
        Host semantic proposal attempt 上限，包含首次 proposal 与后续 repair attempt。
    :param policy_ref: policy snapshot / composition ref。
    """

    context_window_size: int
    soft_threshold_context_ratio: float
    hard_threshold_context_ratio: float
    max_proactive_compactions_per_run: int
    max_reactive_compactions_per_run: int
    max_compaction_attempts_per_operation: int
    policy_ref: str

    def __post_init__(self) -> None:
        """校验预算 policy 字段。

        :returns: ``None``。
        :raises TypeError: 整数或浮点字段类型非法时抛出。
        :raises ValueError: 预算窗口、阈值或 policy ref 非法时抛出。
        """

        _require_positive_int(
            self.context_window_size,
            field_name="ContextBudgetPolicy.context_window_size",
        )
        _require_threshold_ratio(
            self.soft_threshold_context_ratio,
            field_name="ContextBudgetPolicy.soft_threshold_context_ratio",
        )
        _require_threshold_ratio(
            self.hard_threshold_context_ratio,
            field_name="ContextBudgetPolicy.hard_threshold_context_ratio",
        )
        soft_threshold_tokens = _threshold_tokens(
            self.context_window_size, self.soft_threshold_context_ratio
        )
        hard_threshold_tokens = _threshold_tokens(
            self.context_window_size, self.hard_threshold_context_ratio
        )
        if hard_threshold_tokens < MIN_CONTEXT_HARD_THRESHOLD_TOKENS:
            raise ValueError(
                "ContextBudgetPolicy.hard_threshold_context_ratio must leave "
                "hard_threshold_tokens >= "
                f"{MIN_CONTEXT_HARD_THRESHOLD_TOKENS}"
            )
        if soft_threshold_tokens >= hard_threshold_tokens:
            raise ValueError(
                "ContextBudgetPolicy.soft_threshold_context_ratio must derive "
                "a threshold smaller than hard_threshold_context_ratio"
            )
        _require_positive_int(
            self.max_proactive_compactions_per_run,
            field_name="ContextBudgetPolicy.max_proactive_compactions_per_run",
        )
        _require_positive_int(
            self.max_reactive_compactions_per_run,
            field_name="ContextBudgetPolicy.max_reactive_compactions_per_run",
        )
        _require_positive_int(
            self.max_compaction_attempts_per_operation,
            field_name=(
                "ContextBudgetPolicy.max_compaction_attempts_per_operation"
            ),
        )
        _require_non_empty(
            self.policy_ref, field_name="ContextBudgetPolicy.policy_ref"
        )


class ContextBudgetProvider(Protocol):
    """Host context budget policy provider 协议。"""

    def context_budget_policy(self) -> ContextBudgetPolicy:
        """返回当前 Host 装配的 context budget policy。

        :returns: Context budget policy。
        :raises RuntimeError: provider 无法返回 policy 时可抛出运行时错误。
        """

        ...


@dataclass(frozen=True, slots=True)
class StaticContextBudgetProvider:
    """静态 context budget policy provider。

    :param policy: composition root 显式装配的 Host context budget policy。
    """

    policy: ContextBudgetPolicy

    def __post_init__(self) -> None:
        """校验静态 provider 输入。

        :returns: ``None``。
        :raises TypeError: ``policy`` 不是 ContextBudgetPolicy 时抛出。
        """

        if not isinstance(self.policy, ContextBudgetPolicy):
            raise TypeError("StaticContextBudgetProvider.policy must be ContextBudgetPolicy")

    def context_budget_policy(self) -> ContextBudgetPolicy:
        """返回静态 policy。

        :returns: Context budget policy。
        """

        return self.policy


def default_context_budget_policy(
    *,
    context_window_size: int,
    policy_ref: str = DEFAULT_CONTEXT_BUDGET_POLICY_REF,
    soft_threshold_context_ratio: float = DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO,
    hard_threshold_context_ratio: float = DEFAULT_HARD_THRESHOLD_CONTEXT_RATIO,
    max_proactive_compactions_per_run: int = (
        DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN
    ),
    max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
    max_compaction_attempts_per_operation: int = (
        DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION
    ),
) -> ContextBudgetPolicy:
    """构造默认 context budget policy。

    :param context_window_size: Service / composition root 显式传入的上下文窗口 token 数。
    :param policy_ref: policy snapshot / composition ref。
    :param soft_threshold_context_ratio: soft threshold 占上下文窗口比例。
    :param hard_threshold_context_ratio: hard threshold 占上下文窗口比例。
    :param max_proactive_compactions_per_run: 单个 Run 允许的 proactive compact 次数。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :param max_compaction_attempts_per_operation: 单次 compaction operation 内
        Host semantic proposal attempt 上限，包含首次 proposal 与后续 repair attempt。
    :returns: 已校验的 ContextBudgetPolicy。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    return ContextBudgetPolicy(
        context_window_size=context_window_size,
        soft_threshold_context_ratio=soft_threshold_context_ratio,
        hard_threshold_context_ratio=hard_threshold_context_ratio,
        max_proactive_compactions_per_run=max_proactive_compactions_per_run,
        max_reactive_compactions_per_run=max_reactive_compactions_per_run,
        max_compaction_attempts_per_operation=(
            max_compaction_attempts_per_operation
        ),
        policy_ref=policy_ref,
    )


def context_budget_policy_from_threshold_tokens(
    *,
    context_window_size: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
    policy_ref: str = DEFAULT_CONTEXT_BUDGET_POLICY_REF,
    max_proactive_compactions_per_run: int = (
        DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN
    ),
    max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
    max_compaction_attempts_per_operation: int = (
        DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION
    ),
) -> ContextBudgetPolicy:
    """用已计算的阈值 token 构造 ratio-first policy。

    该 helper 只服务于已有 Host opener / command option 字段到 ratio-first
    policy 的边界映射；生成的 public policy 仍只携带 ratio typed shape。

    :param context_window_size: 上下文窗口 token 数。
    :param soft_threshold_tokens: 已计算的 soft threshold token 数。
    :param hard_threshold_tokens: 已计算的 hard threshold token 数。
    :param policy_ref: policy snapshot / composition ref。
    :param max_proactive_compactions_per_run: 单个 Run 允许的 proactive compact 次数。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :param max_compaction_attempts_per_operation: 单次 compaction operation 内 proposal 上限。
    :returns: 已校验的 ContextBudgetPolicy。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 阈值非法时抛出。
    """

    _require_positive_int(
        context_window_size,
        field_name="ContextBudgetPolicy.context_window_size",
    )
    _require_positive_int(
        soft_threshold_tokens,
        field_name="soft_threshold_tokens",
    )
    _require_positive_int(
        hard_threshold_tokens,
        field_name="hard_threshold_tokens",
    )
    if hard_threshold_tokens < MIN_CONTEXT_HARD_THRESHOLD_TOKENS:
        raise ValueError(
            "hard_threshold_tokens must be >= "
            f"{MIN_CONTEXT_HARD_THRESHOLD_TOKENS}"
        )
    if soft_threshold_tokens >= hard_threshold_tokens:
        raise ValueError("soft_threshold_tokens must be smaller than hard_threshold_tokens")
    if hard_threshold_tokens > context_window_size:
        raise ValueError("hard_threshold_tokens must not exceed context_window_size")
    return ContextBudgetPolicy(
        context_window_size=context_window_size,
        soft_threshold_context_ratio=soft_threshold_tokens / context_window_size,
        hard_threshold_context_ratio=hard_threshold_tokens / context_window_size,
        max_proactive_compactions_per_run=max_proactive_compactions_per_run,
        max_reactive_compactions_per_run=max_reactive_compactions_per_run,
        max_compaction_attempts_per_operation=(
            max_compaction_attempts_per_operation
        ),
        policy_ref=policy_ref,
    )


def _threshold_tokens(context_window_size: int, ratio: float) -> int:
    """按上下文窗口比例派生阈值 token 数。

    :param context_window_size: 上下文窗口 token 数。
    :param ratio: 阈值比例。
    :returns: floor 后的阈值 token 数，最小为 1。
    """

    return max(1, int(context_window_size * ratio))


def _require_threshold_ratio(value: float, *, field_name: str) -> None:
    """校验阈值比例值位于 ``(0, 1]``。

    :param value: 待校验比例。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是数值时抛出。
    :raises ValueError: ``value`` 不在允许范围时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be float")
    if value <= 0 or value > 1:
        raise ValueError(f"{field_name} must be in (0, 1]")


__all__ = [
    "ContextBudgetPolicy",
    "ContextBudgetProvider",
    "ContextCompactionTriggerSource",
    "DEFAULT_CONTEXT_BUDGET_POLICY_REF",
    "DEFAULT_HARD_THRESHOLD_CONTEXT_RATIO",
    "DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION",
    "DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN",
    "DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN",
    "DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO",
    "MIN_CONTEXT_HARD_THRESHOLD_TOKENS",
    "StaticContextBudgetProvider",
    "context_budget_policy_from_threshold_tokens",
    "default_context_budget_policy",
]
