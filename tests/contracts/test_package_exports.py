"""``dayu.contracts`` 包根导出白名单测试。

断言 :data:`dayu.contracts.__all__` 严格等于当前层间共享契约集合，并明确
禁止取消异常名（如 ``CancelledError``）出现在导出与属性访问中。
"""

from __future__ import annotations

import dayu.contracts as contracts

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "ALLOWED_TOOL_CANCELLED_REASONS",
        "AGENT_FALLBACK_MODES",
        "AgentFallbackMode",
        "AsyncDirectToolExecutionCapability",
        "BatchToolExecutionContext",
        "BatchToolExecutionOutcome",
        "BatchToolExecutionRecord",
        "BatchToolExecutionRequest",
        "CancellationToken",
        "GeminiToolCallState",
        "JsonValue",
        "PROCESS_TOOL_ENVELOPE_COMPLETED_STATUS",
        "PROCESS_TOOL_ENVELOPE_COMPLETED_VALUE_FIELD",
        "PROCESS_TOOL_ENVELOPE_FAILED_ERROR_TYPE_FIELD",
        "PROCESS_TOOL_ENVELOPE_FAILED_HINT_FIELD",
        "PROCESS_TOOL_ENVELOPE_FAILED_MESSAGE_FIELD",
        "PROCESS_TOOL_ENVELOPE_FAILED_STATUS",
        "PROCESS_TOOL_ENVELOPE_RESERVED_STATUSES",
        "PROCESS_TOOL_ENVELOPE_STATUS_FIELD",
        "TOOL_CANCELLED_REASON_APPROVAL_DENIED",
        "TOOL_CANCELLED_REASON_HOST_CANCELLED",
        "TOOL_CANCELLED_REASON_TIMEOUT",
        "ToolAwaitKind",
        "ToolAwaitSnapshot",
        "ToolAwaitSpec",
        "ToolAwaitingOutcome",
        "ToolBundle",
        "ToolBundleSourceKind",
        "ToolBundleSourceRef",
        "ToolCallProviderState",
        "ToolCallRequest",
        "ToolCallable",
        "ToolCancelledOutcome",
        "ToolCancelledReason",
        "ToolCompletedOutcome",
        "ToolDefinition",
        "ToolDisplayInfo",
        "ToolExecutionCapability",
        "ToolExecutionMode",
        "ToolExecutionOutcome",
        "ToolExecutor",
        "ToolFailedOutcome",
        "ToolFunctionSchema",
        "ToolParametersSchema",
        "ProcessBackedToolContext",
        "ProcessBackedToolExecutionCapability",
        "ProcessBackedToolTarget",
        "ProcessBackedToolTargetFactory",
        "ProcessToolCompletedEnvelope",
        "ProcessToolEnvelopeParseResult",
        "ProcessToolFailedEnvelope",
        "ProcessToolMalformedEnvelope",
        "ProcessToolUnsupportedEnvelope",
        "ToolResultEnvelope",
        "ToolResultFailure",
        "ToolResultMeta",
        "ToolResultSuccess",
        "ToolSchema",
        "ToolTruncateSpec",
        "ToolTruncationStrategy",
        "ThreadBackedToolExecutionCapability",
        "parse_process_tool_envelope",
        "process_tool_completed_envelope",
        "process_tool_failed_envelope",
        "tool",
        "truncate_limit_key_for_strategy",
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
