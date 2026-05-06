"""Host 公共入口。

P1.5 暴露最小 Run 级入口与事件事实读取接口。Host 内部的 ``EngineWorker``、
``LocalProxy``、``WorkerProxy`` 与 ``ToolExecutor`` 代持不属于 public surface。
"""

from __future__ import annotations

from dayu.host._run_harness import get_run_result, start_run, stream_run_events
from dayu.host.contracts import (
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
    RunOptions,
    RunResult,
    RunState,
    RunStream,
    RunSucceededResult,
    RunSuspendedResult,
    StartRunRequest,
)

__all__ = [
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
    "get_run_result",
    "start_run",
    "stream_run_events",
]
