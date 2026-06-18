"""CLI Agent 运行态按键监听。

本模块只处理本地 TTY 控制键，把 ``Ctrl+T`` 和 ``Esc`` 映射为 CLI
运行态控制动作。它不访问 Host / Service / Engine，也不改变 stdout
结果通道。
"""

from __future__ import annotations

import asyncio
import os
import select
import sys
import termios
import threading
import tty
from enum import StrEnum
from typing import Final, Protocol, TextIO, cast

_CTRL_T: Final[bytes] = b"\x14"
_ESC: Final[bytes] = b"\x1b"
_READ_SIZE_BYTES: Final[int] = 1
_POLL_INTERVAL_SECONDS: Final[float] = 0.05
_THREAD_JOIN_TIMEOUT_SECONDS: Final[float] = 0.2
_TerminalAttribute = int | list[bytes | int]
_TerminalAttributes = list[_TerminalAttribute]


class RunningKeyAction(StrEnum):
    """CLI 运行态按键动作。"""

    TOGGLE_ACTIVITY = "toggle_activity"
    CANCEL_RUN = "cancel_run"


class RunningKeyMonitor(Protocol):
    """CLI 运行态按键 monitor 协议。"""

    def start(self) -> None:
        """启动按键监听。

        :returns: ``None``。
        :raises Exception: 实现层启动失败时向上透传。
        """

    async def wait_next(self) -> RunningKeyAction:
        """等待下一次运行态按键动作。

        :returns: 运行态按键动作。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        ...

    def close(self) -> None:
        """关闭 monitor 并恢复本地终端状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """


class NoopRunningKeyMonitor:
    """非 TTY 或测试路径使用的空运行态按键 monitor。"""

    def start(self) -> None:
        """启动 no-op monitor。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return

    async def wait_next(self) -> RunningKeyAction:
        """一直等待，直到调用方取消任务。

        :returns: 正常路径不会返回。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        await asyncio.Event().wait()
        return RunningKeyAction.CANCEL_RUN

    def close(self) -> None:
        """关闭 no-op monitor。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return


class TtyRunningKeyMonitor:
    """TTY 运行态按键 monitor。

    monitor 在当前事件循环外用后台线程读取 stdin 单字节输入，并通过
    ``asyncio.Queue`` 投递到运行态状态机。关闭时必须恢复原始终端模式。
    """

    _stdin: TextIO
    _poll_interval_seconds: float
    _queue: asyncio.Queue[RunningKeyAction]
    _stop_event: threading.Event
    _loop: asyncio.AbstractEventLoop | None
    _thread: threading.Thread | None
    _fd: int | None
    _original_attrs: _TerminalAttributes | None
    _started: bool
    _closed: bool

    def __init__(
        self,
        *,
        stdin: TextIO | None = None,
        poll_interval_seconds: float = _POLL_INTERVAL_SECONDS,
    ) -> None:
        """初始化 TTY monitor。

        :param stdin: 按键读取来源；``None`` 表示当前 ``sys.stdin``。
        :param poll_interval_seconds: 后台读取线程轮询间隔秒数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._stdin = sys.stdin if stdin is None else stdin
        self._poll_interval_seconds = poll_interval_seconds
        self._queue = asyncio.Queue()
        self._stop_event = threading.Event()
        self._loop = None
        self._thread = None
        self._fd = None
        self._original_attrs = None
        self._started = False
        self._closed = False

    def start(self) -> None:
        """启动 TTY 按键监听。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常；无法启用 TTY 监听时静默降级为
            no-op，避免破坏非标准终端环境。
        """

        if self._started or self._closed:
            return
        if not self._stdin.isatty():
            return
        loop = asyncio.get_running_loop()
        fd: int | None = None
        original_attrs: _TerminalAttributes | None = None
        try:
            fd = self._stdin.fileno()
            original_attrs = cast(_TerminalAttributes, termios.tcgetattr(fd))
            tty.setcbreak(fd)
        except (OSError, ValueError, termios.error):
            if fd is not None and original_attrs is not None:
                _restore_terminal_attrs(fd, original_attrs)
            return
        self._fd = fd
        self._original_attrs = original_attrs
        self._loop = loop
        self._started = True
        thread = threading.Thread(
            target=self._read_loop,
            name="dayu-cli-running-key-monitor",
            daemon=True,
        )
        self._thread = thread
        try:
            thread.start()
        except RuntimeError:
            _restore_terminal_attrs(fd, original_attrs)
            self._thread = None
            self._loop = None
            self._fd = None
            self._original_attrs = None
            self._started = False
            return

    async def wait_next(self) -> RunningKeyAction:
        """等待下一次 TTY 运行态按键动作。

        :returns: 运行态按键动作。
        :raises asyncio.CancelledError: 等待任务被取消时透传。
        """

        return await self._queue.get()

    def close(self) -> None:
        """关闭按键监听并恢复终端模式。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._closed:
            return
        self._closed = True
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=_THREAD_JOIN_TIMEOUT_SECONDS)
        if self._fd is not None and self._original_attrs is not None:
            _restore_terminal_attrs(self._fd, self._original_attrs)
        self._thread = None
        self._loop = None
        self._fd = None
        self._original_attrs = None
        self._started = False

    def _read_loop(self) -> None:
        """后台线程读取 TTY 单字节输入。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        fd = self._fd
        loop = self._loop
        if fd is None or loop is None:
            return
        while not self._stop_event.is_set():
            try:
                readable, _writeable, _errored = select.select(
                    (fd,),
                    (),
                    (),
                    self._poll_interval_seconds,
                )
                if not readable:
                    continue
                data = os.read(fd, _READ_SIZE_BYTES)
            except OSError:
                return
            action = running_key_action_from_bytes(data)
            if action is not None:
                loop.call_soon_threadsafe(self._queue.put_nowait, action)


def new_running_key_monitor(*, stdin: TextIO | None = None) -> RunningKeyMonitor:
    """按默认 TTY policy 创建运行态按键 monitor。

    :param stdin: 按键读取来源；``None`` 表示当前 ``sys.stdin``。
    :returns: TTY monitor 或 no-op monitor。
    :raises Exception: 不主动抛出异常。
    """

    effective_stdin = sys.stdin if stdin is None else stdin
    if not effective_stdin.isatty():
        return NoopRunningKeyMonitor()
    return TtyRunningKeyMonitor(stdin=effective_stdin)


def running_key_action_from_bytes(data: bytes) -> RunningKeyAction | None:
    """把 TTY 输入字节映射为运行态按键动作。

    :param data: 从 TTY 读取的单字节数据。
    :returns: 可识别动作；未知字节返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if data == _CTRL_T:
        return RunningKeyAction.TOGGLE_ACTIVITY
    if data == _ESC:
        return RunningKeyAction.CANCEL_RUN
    return None


def _restore_terminal_attrs(fd: int, attrs: _TerminalAttributes) -> None:
    """恢复 TTY 原始终端属性。

    :param fd: TTY 文件描述符。
    :param attrs: ``termios.tcgetattr`` 返回的原始属性。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    try:
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except (OSError, termios.error):
        return


__all__: tuple[str, ...] = (
    "NoopRunningKeyMonitor",
    "RunningKeyAction",
    "RunningKeyMonitor",
    "TtyRunningKeyMonitor",
    "new_running_key_monitor",
    "running_key_action_from_bytes",
)
