"""Host public API 边界测试。"""

from __future__ import annotations

import dayu.host as host

EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "ContextCompactFailureReason",
        "HostContextAttemptRetryData",
        "HostContextCompactCompletedData",
        "HostContextCompactEventData",
        "HostContextCompactFailedData",
        "HostContextCompactRequestedData",
        "HostContextOverflowObservedData",
        "HostRunFailedData",
        "RunCancelledResult",
        "RunEventData",
        "RunEvent",
        "RunEventCursor",
        "RunEventKind",
        "RunEventSource",
        "RunEventType",
        "RunFailedResult",
        "RunHandle",
        "RunInput",
        "RunOptions",
        "RunResult",
        "RunState",
        "RunStream",
        "RunSucceededResult",
        "RunSuspendedResult",
        "StartRunRequest",
        "ToolCursorDeniedData",
        "ToolCursorExpiredData",
        "ToolCursorIssuedData",
        "ToolFetchMoreCompletedData",
        "ToolFetchMoreFailedData",
        "ToolFetchMoreFailedResult",
        "ToolFetchMoreRequest",
        "ToolFetchMoreRequestedData",
        "ToolFetchMoreResult",
        "ToolFetchMoreSucceededResult",
        "ToolResultTruncatedData",
        "ToolRuntimeCursor",
        "ToolRuntimeEventData",
        "ToolValueSizeSummary",
        "UserInputAcceptedData",
        "UserInputScope",
    }
)

FORBIDDEN_EXPORTS: frozenset[str] = frozenset(
    {
        "EngineWorker",
        "LocalProxy",
        "ToolExecutor",
        "InMemoryToolRuntime",
        "ToolRuntimeToolExecutor",
        "run_agent_messages",
        "fetch_more_tool_result",
        "get_run_result",
        "get_tool_fetch_more_handle",
        "start_run",
        "stream_run_events",
    }
)


def test_host_all_matches_expected_p1_surface() -> None:
    """``dayu.host.__all__`` 只暴露当前最小 public surface。"""

    actual = frozenset(host.__all__)
    assert actual == EXPECTED_EXPORTS, (
        f"missing={EXPECTED_EXPORTS - actual}; extra={actual - EXPECTED_EXPORTS}"
    )


def test_internal_symbols_not_exported_or_attribute_accessible() -> None:
    """EngineWorker / ToolExecutor 等内部符号不得从包根访问。"""

    actual = frozenset(host.__all__)
    assert actual.isdisjoint(FORBIDDEN_EXPORTS), (
        f"forbidden symbols leaked: {actual & FORBIDDEN_EXPORTS}"
    )
    for name in FORBIDDEN_EXPORTS:
        assert not hasattr(host, name), f"{name} unexpectedly accessible"
