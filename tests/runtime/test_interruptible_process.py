"""interruptible process runtime helper 测试。"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.runtime.interruptible_process import (
    InterruptibleProcessCompleted,
    InterruptibleProcessHandle,
)


@dataclass(frozen=True, slots=True)
class _ReturnTarget:
    """立即返回 JSON-like 结果的子进程目标。"""

    value: JsonValue

    def __call__(self) -> JsonValue:
        """返回预设值。

        :returns: JSON-like 结果。
        """

        return self.value


@dataclass(frozen=True, slots=True)
class _SleepTarget:
    """默认响应 SIGTERM 的阻塞目标。"""

    seconds: float

    def __call__(self) -> JsonValue:
        """阻塞指定秒数后返回。

        :returns: JSON-like 结果。
        """

        time.sleep(self.seconds)
        return {"completed": True}


@dataclass(frozen=True, slots=True)
class _IgnoreTerminateTarget:
    """忽略 SIGTERM 的阻塞目标。"""

    seconds: float

    def __call__(self) -> JsonValue:
        """忽略 SIGTERM 并阻塞指定秒数。

        :returns: JSON-like 结果。
        """

        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(self.seconds)
        return {"completed": True}


@pytest.mark.asyncio
async def test_interruptible_process_returns_completed_value() -> None:
    """子进程正常完成时返回 JSON-like 值。"""

    handle = InterruptibleProcessHandle(_ReturnTarget({"ok": True}))
    try:
        handle.start()
        result = await handle.wait(timeout_seconds=2.0)
    finally:
        await handle.close()

    assert isinstance(result, InterruptibleProcessCompleted)
    assert result.value == {"ok": True}


@pytest.mark.asyncio
async def test_interruptible_process_terminate_exits_before_kill() -> None:
    """默认阻塞子进程可由 terminate 在 kill 前中止。"""

    handle = InterruptibleProcessHandle(_SleepTarget(seconds=10.0))
    try:
        handle.start()
        result = await handle.terminate(grace_seconds=1.0)
    finally:
        await handle.close()

    assert result.supported
    assert result.exited


@pytest.mark.asyncio
async def test_interruptible_process_hard_kill_exits_when_terminate_is_ignored() -> None:
    """忽略 SIGTERM 的子进程会走 hard kill 收口。"""

    handle = InterruptibleProcessHandle(_IgnoreTerminateTarget(seconds=10.0))
    try:
        handle.start()
        await asyncio.sleep(0.5)
        terminate = await handle.terminate(grace_seconds=0.2)
        kill = await handle.kill(grace_seconds=1.0)
    finally:
        await handle.close()

    assert terminate.supported
    assert not terminate.exited
    assert kill.supported
    assert kill.exited
