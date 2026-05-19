"""Host context budget policy contract tests。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from dayu.host.context_policy import (
    DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION,
    ContextBudgetPolicy,
    default_context_budget_policy,
)


def test_default_context_budget_policy_sets_compaction_attempt_budget() -> None:
    """默认 policy 带正整数 compaction operation attempt 上限。"""

    policy = default_context_budget_policy(
        context_window_size=1000,
        reserved_output_tokens=100,
    )

    assert (
        policy.max_compaction_attempts_per_operation
        == DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION
    )


def test_context_budget_policy_validates_compaction_attempt_budget() -> None:
    """compaction operation attempt 上限必须是正整数且不是 bool。"""

    policy = default_context_budget_policy(
        context_window_size=1000,
        reserved_output_tokens=100,
        max_compaction_attempts_per_operation=2,
    )
    assert policy.max_compaction_attempts_per_operation == 2

    with pytest.raises(ValueError, match="max_compaction_attempts_per_operation"):
        replace(policy, max_compaction_attempts_per_operation=0)
    with pytest.raises(ValueError, match="max_compaction_attempts_per_operation"):
        replace(policy, max_compaction_attempts_per_operation=-1)
    with pytest.raises(TypeError, match="max_compaction_attempts_per_operation"):
        replace(policy, max_compaction_attempts_per_operation=cast(int, True))
    with pytest.raises(TypeError, match="max_compaction_attempts_per_operation"):
        replace(policy, max_compaction_attempts_per_operation=cast(int, "bad"))


def test_context_budget_policy_rejects_non_dispatchable_hard_threshold() -> None:
    """hard threshold 必须给 compact 后正预算留下空间。"""

    policy = default_context_budget_policy(
        context_window_size=1000,
        reserved_output_tokens=100,
        hard_threshold_tokens=2,
    )
    assert policy.hard_threshold_tokens == 2

    with pytest.raises(ValueError, match="hard_threshold_tokens"):
        replace(policy, hard_threshold_tokens=1)
    with pytest.raises(ValueError, match="hard_threshold_tokens"):
        default_context_budget_policy(
            context_window_size=3,
            reserved_output_tokens=1,
            minimum_protection_tokens=1,
        )


def test_context_budget_policy_direct_constructor_requires_attempt_budget() -> None:
    """直接构造 ContextBudgetPolicy 时 attempt budget 是显式 typed 字段。"""

    policy = ContextBudgetPolicy(
        context_window_size=1000,
        reserved_output_tokens=100,
        safety_margin_ratio=0.2,
        hard_threshold_tokens=None,
        minimum_protection_tokens=256,
        max_proactive_compactions_per_run=1,
        max_reactive_compactions_per_run=1,
        max_compaction_attempts_per_operation=3,
        policy_ref="policy:test",
    )

    assert policy.max_compaction_attempts_per_operation == 3
