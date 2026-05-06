"""Host 公共入口。

P1 仅暴露最小 Run harness 契约与 :func:`start_run` 测试入口。Host 内部的
``EngineWorker``、``LocalProxy`` 与 ``ToolExecutor`` 代持不属于 public
surface。
"""

from __future__ import annotations

from dayu.host._run_harness import start_run
from dayu.host.contracts import (
    RunCancelledResult,
    RunEvent,
    RunEventCursor,
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
    "RunCancelledResult",
    "RunEvent",
    "RunEventCursor",
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
    "start_run",
]
