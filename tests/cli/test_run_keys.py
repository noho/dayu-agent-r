"""CLI 运行态按键监听测试。"""

from __future__ import annotations

import asyncio
import io
import os
import pty
import termios
from collections.abc import Callable
from contextlib import suppress
from typing import TextIO, cast

import pytest

import dayu.cli.run_keys as run_keys
from dayu.cli.run_keys import (
    NoopRunningKeyMonitor,
    RunningKeyAction,
    TtyRunningKeyMonitor,
    new_running_key_monitor,
    running_key_action_from_bytes,
)


class _FailingThread:
    """测试用启动失败线程。"""

    def start(self) -> None:
        """模拟线程启动失败。

        :returns: 正常路径不会返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("thread start failed")


def test_running_key_action_from_bytes_maps_supported_controls() -> None:
    """Ctrl+T 与 Esc 应映射为运行态控制动作。"""

    assert running_key_action_from_bytes(b"\x14") is RunningKeyAction.TOGGLE_ACTIVITY
    assert running_key_action_from_bytes(b"\x1b") is RunningKeyAction.CANCEL_RUN
    assert running_key_action_from_bytes(b"x") is None


def test_new_running_key_monitor_uses_noop_for_non_tty() -> None:
    """非 TTY 输入应保持 no-op，不改变原有 CLI 行为。"""

    monitor = new_running_key_monitor(stdin=io.StringIO())

    assert isinstance(monitor, NoopRunningKeyMonitor)


@pytest.mark.asyncio
async def test_noop_running_key_monitor_wait_is_cancellable() -> None:
    """no-op monitor 的等待应只由调用方取消。"""

    monitor = NoopRunningKeyMonitor()
    wait_task = asyncio.create_task(monitor.wait_next())

    wait_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await wait_task


@pytest.mark.asyncio
async def test_tty_running_key_monitor_reads_action_and_restores_terminal() -> None:
    """TTY monitor 应读取控制键，并在 close 时恢复终端属性。"""

    master_fd, slave_fd = pty.openpty()
    slave_stream = cast(TextIO, os.fdopen(slave_fd, "r", encoding="utf-8", buffering=1))
    original_lflag = termios.tcgetattr(slave_fd)[3]
    monitor = TtyRunningKeyMonitor(stdin=slave_stream, poll_interval_seconds=0.01)
    try:
        monitor.start()
        os.write(master_fd, b"\x14")

        action = await asyncio.wait_for(monitor.wait_next(), timeout=1.0)

        assert action is RunningKeyAction.TOGGLE_ACTIVITY
    finally:
        monitor.close()
        restored_lflag = termios.tcgetattr(slave_fd)[3]
        slave_stream.close()
        with suppress(OSError):
            os.close(master_fd)
    assert _terminal_lflag_controls(restored_lflag) == _terminal_lflag_controls(original_lflag)


@pytest.mark.asyncio
async def test_tty_running_key_monitor_close_is_idempotent() -> None:
    """TTY monitor close 应可重复调用，避免 finally 清理竞态。"""

    monitor = TtyRunningKeyMonitor(stdin=io.StringIO(), poll_interval_seconds=0.01)
    wait_task = asyncio.create_task(monitor.wait_next())

    monitor.start()
    monitor.close()
    monitor.close()
    wait_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await wait_task


@pytest.mark.asyncio
async def test_tty_running_key_monitor_restores_terminal_when_thread_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTY monitor 在线程启动失败时必须恢复终端属性。"""

    def failing_thread_factory(
        *,
        target: Callable[[], None],
        name: str,
        daemon: bool,
    ) -> _FailingThread:
        """返回启动失败线程。

        :param target: 原线程目标函数。
        :param name: 原线程名称。
        :param daemon: 原 daemon 配置。
        :returns: 启动失败线程。
        :raises Exception: 不主动抛出异常。
        """

        _ = (target, name, daemon)
        return _FailingThread()

    master_fd, slave_fd = pty.openpty()
    slave_stream = cast(TextIO, os.fdopen(slave_fd, "r", encoding="utf-8", buffering=1))
    original_lflag = termios.tcgetattr(slave_fd)[3]
    monkeypatch.setattr(run_keys.threading, "Thread", failing_thread_factory)
    try:
        monitor = TtyRunningKeyMonitor(stdin=slave_stream, poll_interval_seconds=0.01)
        monitor.start()
        restored_lflag = termios.tcgetattr(slave_fd)[3]
        monitor.close()
    finally:
        slave_stream.close()
        with suppress(OSError):
            os.close(master_fd)
    assert _terminal_lflag_controls(restored_lflag) == _terminal_lflag_controls(original_lflag)


def _terminal_lflag_controls(lflag: int) -> tuple[bool, bool, bool, bool]:
    """提取本测试关心的终端本地行为位。

    :param lflag: ``termios`` local flags。
    :returns: ECHO、ICANON、ISIG、IEXTEN 是否启用。
    :raises Exception: 不主动抛出异常。
    """

    return (
        bool(lflag & termios.ECHO),
        bool(lflag & termios.ICANON),
        bool(lflag & termios.ISIG),
        bool(lflag & termios.IEXTEN),
    )
