"""``dayu.contracts`` 包根导出白名单测试。

按 ``docs/engine/phase0-plan.md`` §1.1 锁定的层间共享契约符号集合，
断言 :data:`dayu.contracts.__all__` 严格等于该集合，并明确禁止取消
异常名（如 ``CancelledError``）出现在导出与属性访问中。
"""

from __future__ import annotations

import dayu.contracts as contracts

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "CancellationToken",
        "GeminiToolCallState",
        "JsonValue",
        "ToolAwaitKind",
        "ToolAwaitSnapshot",
        "ToolAwaitSpec",
        "ToolAwaitingOutcome",
        "ToolBundle",
        "ToolCallProviderState",
        "ToolCallRequest",
        "ToolCompletedOutcome",
        "ToolDefinition",
        "ToolDisplayInfo",
        "ToolExecutionContext",
        "ToolExecutionOutcome",
        "ToolExecutionRequest",
        "ToolExecutor",
        "ToolFailedOutcome",
        "ToolFunctionCallable",
        "ToolFunctionSchema",
        "ToolParametersSchema",
        "ToolResultEnvelope",
        "ToolResultFailure",
        "ToolResultMeta",
        "ToolResultSuccess",
        "ToolSchema",
        "ToolTruncateSpec",
        "ToolTruncationStrategy",
        "FunctionToolExecutor",
        "tool",
    }
)


FORBIDDEN_EXPORTS: frozenset[str] = frozenset(
    {"CancelledError", "ToolTruncationInfo"}
)


def test_contracts_all_matches_expected_set() -> None:
    """``dayu.contracts.__all__`` 必须与 §1.1 锁定白名单严格相等。"""

    actual = frozenset(contracts.__all__)
    assert actual == EXPECTED_EXPORTS, (
        f"missing={EXPECTED_EXPORTS - actual}; extra={actual - EXPECTED_EXPORTS}"
    )


def test_forbidden_symbols_not_exported() -> None:
    """``CancelledError`` 等取消异常不得出现在 ``__all__`` 中。"""

    actual = frozenset(contracts.__all__)
    assert actual.isdisjoint(FORBIDDEN_EXPORTS), (
        f"forbidden symbols leaked: {actual & FORBIDDEN_EXPORTS}"
    )


def test_forbidden_symbols_not_attribute_accessible() -> None:
    """禁止导出的取消异常名也不得作为模块属性可访问。"""

    for name in FORBIDDEN_EXPORTS:
        assert not hasattr(contracts, name), (
            f"{name} unexpectedly accessible on dayu.contracts"
        )
