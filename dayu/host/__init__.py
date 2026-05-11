"""Host 公共入口。

P8 阶段包根只导出 ``dayu.host.contracts`` 中的强类型契约，避免把当前
仍在迁移中的 harness / runtime 装配细节提前固定为 public API。

durable harness 装配入口仍位于 ``dayu.host._durable_harness``；
``LocalRunHarness`` 与 ``HostToolRuntime`` 仍是 Host 内部实现 / 子模块测试入口，
不属于 ``dayu.host`` 包根导出面。P9/P16 前不得通过包根新增兼容 re-export。
"""

from __future__ import annotations

from dayu.host.contracts import (
    ContextCompactFailureReason,
    HostContextAttemptRetryData,
    HostContextCompactCompletedData,
    HostContextCompactEventData,
    HostContextCompactFailedData,
    HostContextCompactRequestedData,
    HostContextOverflowObservedData,
    HostRunFailedData,
    RunCancelledResult,
    RunEvent,
    RunEventCursor,
    RunEventData,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunFailedResult,
    RunHandle,
    RunInput,
    RunInputContextMeta,
    RunInputContextSnapshotBuiltData,
    RunInputMessageSummary,
    RunInputToolSchemaSummary,
    RunOptions,
    RunResult,
    RunState,
    RunStream,
    RunSucceededResult,
    RunSuspendedResult,
    StartRunRequest,
    ToolValueSizeSummary,
    UserInputAcceptedData,
    UserInputScope,
)

__all__ = [
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
    "RunInputContextMeta",
    "RunInputContextSnapshotBuiltData",
    "RunInputMessageSummary",
    "RunInputToolSchemaSummary",
    "RunOptions",
    "RunResult",
    "RunState",
    "RunStream",
    "RunSucceededResult",
    "RunSuspendedResult",
    "StartRunRequest",
    "ToolValueSizeSummary",
    "UserInputAcceptedData",
    "UserInputScope",
]
