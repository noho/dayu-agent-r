"""Host context budget policy typed contract。

本模块只定义 Host Context Governance 需要的预算策略输入与 provider
边界。预算窗口与输出预留 token 必须由 Service / composition root 显式
装配进 Host policy；本模块不读取 Engine spec、metadata、extra payload
或 provider overflow 诊断信息。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from dayu.host._public_validation import require_non_empty as _require_non_empty
from dayu.host._public_validation import (
    require_non_negative_int as _require_non_negative_int,
)
from dayu.host._public_validation import require_positive_int as _require_positive_int

DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO = 0.2
DEFAULT_MINIMUM_PROTECTION_TOKENS = 256
DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN = 1
DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 1
DEFAULT_CONTEXT_BUDGET_POLICY_REF = "host-context-budget-policy:default"


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
    :param reserved_output_tokens: Service / composition root 显式传入的输出预留 token 数。
    :param safety_margin_ratio: 输入预算安全余量比例。
    :param hard_threshold_tokens: 显式 hard threshold；``None`` 时由输入预算扣除最小保护量得到。
    :param minimum_protection_tokens: 未显式给出 hard threshold 时保留的最小保护 token 数。
    :param max_proactive_compactions_per_run: 单个 Run 允许的 proactive compact 次数。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :param policy_ref: policy snapshot / composition ref。
    """

    context_window_size: int
    reserved_output_tokens: int
    safety_margin_ratio: float
    hard_threshold_tokens: int | None
    minimum_protection_tokens: int
    max_proactive_compactions_per_run: int
    max_reactive_compactions_per_run: int
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
        _require_positive_int(
            self.reserved_output_tokens,
            field_name="ContextBudgetPolicy.reserved_output_tokens",
        )
        if self.reserved_output_tokens >= self.context_window_size:
            raise ValueError(
                "ContextBudgetPolicy.reserved_output_tokens must be smaller "
                "than context_window_size"
            )
        _require_ratio(
            self.safety_margin_ratio,
            field_name="ContextBudgetPolicy.safety_margin_ratio",
        )
        _require_non_negative_int(
            self.minimum_protection_tokens,
            field_name="ContextBudgetPolicy.minimum_protection_tokens",
        )
        input_budget_tokens = (
            self.context_window_size - self.reserved_output_tokens
        )
        if self.minimum_protection_tokens >= input_budget_tokens:
            raise ValueError(
                "ContextBudgetPolicy.minimum_protection_tokens must be smaller "
                "than input budget"
            )
        if self.hard_threshold_tokens is not None:
            _require_positive_int(
                self.hard_threshold_tokens,
                field_name="ContextBudgetPolicy.hard_threshold_tokens",
            )
            if self.hard_threshold_tokens > input_budget_tokens:
                raise ValueError(
                    "ContextBudgetPolicy.hard_threshold_tokens must not exceed "
                    "input budget"
                )
        _require_positive_int(
            self.max_proactive_compactions_per_run,
            field_name="ContextBudgetPolicy.max_proactive_compactions_per_run",
        )
        _require_positive_int(
            self.max_reactive_compactions_per_run,
            field_name="ContextBudgetPolicy.max_reactive_compactions_per_run",
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
    reserved_output_tokens: int,
    policy_ref: str = DEFAULT_CONTEXT_BUDGET_POLICY_REF,
    hard_threshold_tokens: int | None = None,
    safety_margin_ratio: float = DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO,
    minimum_protection_tokens: int = DEFAULT_MINIMUM_PROTECTION_TOKENS,
    max_proactive_compactions_per_run: int = (
        DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN
    ),
    max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
) -> ContextBudgetPolicy:
    """构造默认 context budget policy。

    :param context_window_size: Service / composition root 显式传入的上下文窗口 token 数。
    :param reserved_output_tokens: Service / composition root 显式传入的输出预留 token 数。
    :param policy_ref: policy snapshot / composition ref。
    :param hard_threshold_tokens: 显式 hard threshold；``None`` 时由预算函数计算。
    :param safety_margin_ratio: 输入预算安全余量比例，默认 20%。
    :param minimum_protection_tokens: 未显式给出 hard threshold 时的最小保护 token 数。
    :param max_proactive_compactions_per_run: 单个 Run 允许的 proactive compact 次数。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :returns: 已校验的 ContextBudgetPolicy。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    return ContextBudgetPolicy(
        context_window_size=context_window_size,
        reserved_output_tokens=reserved_output_tokens,
        safety_margin_ratio=safety_margin_ratio,
        hard_threshold_tokens=hard_threshold_tokens,
        minimum_protection_tokens=minimum_protection_tokens,
        max_proactive_compactions_per_run=max_proactive_compactions_per_run,
        max_reactive_compactions_per_run=max_reactive_compactions_per_run,
        policy_ref=policy_ref,
    )


def _require_ratio(value: float, *, field_name: str) -> None:
    """校验比例值位于 ``[0, 1)``。

    :param value: 待校验比例。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是数值时抛出。
    :raises ValueError: ``value`` 不在允许范围时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be float")
    if value < 0 or value >= 1:
        raise ValueError(f"{field_name} must be in [0, 1)")


__all__ = [
    "ContextBudgetPolicy",
    "ContextBudgetProvider",
    "ContextCompactionTriggerSource",
    "DEFAULT_CONTEXT_BUDGET_POLICY_REF",
    "DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO",
    "DEFAULT_MAX_PROACTIVE_COMPACTIONS_PER_RUN",
    "DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN",
    "DEFAULT_MINIMUM_PROTECTION_TOKENS",
    "StaticContextBudgetProvider",
    "default_context_budget_policy",
]
