"""CLI prompt one-shot 运行态按键监听。

本模块只服务 prompt one-shot，把 ``Ctrl+T`` 和 ``Esc`` 映射为运行态控制
动作。interactive 的整个 invocation 由 composer 独占 stdin，不使用本模块。
本模块不访问 Host / Service / Engine，也不改变 stdout 结果通道。
"""

from __future__ import annotations

import asyncio
import codecs
import os
import select
import sys
import threading
import time
from enum import StrEnum
from typing import Final, Protocol, TextIO, cast

from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.key_binding import KeyPress
from prompt_toolkit.keys import Keys

if os.name == "posix":
    import termios
    import tty

_ESC: Final[bytes] = b"\x1b"
_ESC_TEXT: Final[str] = "\x1b"
_READ_SIZE_BYTES: Final[int] = 1024
_POLL_INTERVAL_SECONDS: Final[float] = 0.05
_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1
_THREAD_JOIN_TIMEOUT_SECONDS: Final[float] = 0.2
_POSIX_TERMINAL_CONTROL_AVAILABLE: Final[bool] = os.name == "posix"
_TerminalAttribute = int | list[bytes | int]
_TerminalAttributes = list[_TerminalAttribute]


class RunningKeyAction(StrEnum):
    """prompt one-shot 运行态按键动作。"""

    TOGGLE_ACTIVITY = "toggle_activity"
    CANCEL_RUN = "cancel_run"


class RunningKeyMonitor(Protocol):
    """prompt one-shot 运行态按键 monitor 协议。"""

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
    """prompt 非 TTY 或测试路径使用的空运行态按键 monitor。"""

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
    """prompt one-shot TTY 运行态按键 monitor。

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
        if not _POSIX_TERMINAL_CONTROL_AVAILABLE:
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
        """在后台线程内增量解析 TTY 输入并投递完整按键动作。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        fd = self._fd
        loop = self._loop
        if fd is None or loop is None:
            return
        callback_collector: list[KeyPress] = []
        parser = Vt100Parser(callback_collector.append)
        decoder: codecs.IncrementalDecoder = codecs.getincrementaldecoder("utf-8")(
            errors="strict"
        )
        escape_deadline: float | None = None
        while not self._stop_event.is_set():
            wait_seconds = self._poll_interval_seconds
            if escape_deadline is not None:
                wait_seconds = min(
                    wait_seconds,
                    max(0.0, escape_deadline - time.monotonic()),
                )
            try:
                readable, _writeable, _errored = select.select(
                    (fd,),
                    (),
                    (),
                    wait_seconds,
                )
            except (OSError, ValueError):
                return
            if self._stop_event.is_set():
                return
            if readable:
                try:
                    data = os.read(fd, _READ_SIZE_BYTES)
                    if not data:
                        return
                    decoded = decoder.decode(data, final=False)
                except (OSError, UnicodeDecodeError):
                    return
                feed_time = time.monotonic()
                if _ESC in data or escape_deadline is not None:
                    escape_deadline = feed_time + _ESCAPE_SEQUENCE_AMBIGUITY_SECONDS
                if decoded:
                    batch = _feed_parser_resolution(
                        parser=parser,
                        collector=callback_collector,
                        decoded_text=decoded,
                    )
                    self._publish_actions(
                        loop=loop,
                        actions=_classify_running_key_batch(
                            batch,
                            is_ambiguity_flush=False,
                        ),
                    )
                continue
            if escape_deadline is None or time.monotonic() < escape_deadline:
                continue
            batch = _flush_parser_resolution(
                parser=parser,
                collector=callback_collector,
            )
            escape_deadline = None
            self._publish_actions(
                loop=loop,
                actions=_classify_running_key_batch(
                    batch,
                    is_ambiguity_flush=True,
                ),
            )

    def _publish_actions(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        actions: tuple[RunningKeyAction, ...],
    ) -> None:
        """把完整 parser resolution batch 的动作投递到事件循环。

        :param loop: monitor 启动时所在的事件循环。
        :param actions: 已完成 batch 分类的运行态动作。
        :returns: ``None``。
        :raises RuntimeError: 事件循环拒绝线程安全回调时向上透传。
        """

        for action in actions:
            loop.call_soon_threadsafe(self._queue.put_nowait, action)


def new_running_key_monitor(*, stdin: TextIO | None = None) -> RunningKeyMonitor:
    """按默认 TTY policy 创建 prompt one-shot 按键 monitor。

    :param stdin: 按键读取来源；``None`` 表示当前 ``sys.stdin``。
    :returns: POSIX TTY monitor 或 no-op monitor；非 POSIX 固定为 no-op。
    :raises Exception: 不主动抛出异常。
    """

    effective_stdin = sys.stdin if stdin is None else stdin
    if not _POSIX_TERMINAL_CONTROL_AVAILABLE or not effective_stdin.isatty():
        return NoopRunningKeyMonitor()
    return TtyRunningKeyMonitor(stdin=effective_stdin)


def _feed_parser_resolution(
    *,
    parser: Vt100Parser,
    collector: list[KeyPress],
    decoded_text: str,
) -> tuple[KeyPress, ...]:
    """执行一次 public parser feed 并冻结其同步 callback batch。

    :param parser: reader thread 唯一 public VT100 parser。
    :param collector: reader thread 唯一 callback collector。
    :param decoded_text: 唯一 incremental decoder 产生的非空文本。
    :returns: 本次 ``feed`` 同步产生的完整 callback batch。
    :raises RuntimeError: 上一次 resolution 的 callback 尚未清空时抛出。
    """

    if collector:
        raise RuntimeError("VT100 callback collector is not empty before feed")
    parser.feed(decoded_text)
    return _freeze_parser_resolution(collector)


def _flush_parser_resolution(
    *,
    parser: Vt100Parser,
    collector: list[KeyPress],
) -> tuple[KeyPress, ...]:
    """执行一次 public parser flush 并冻结其同步 callback batch。

    :param parser: reader thread 唯一 public VT100 parser。
    :param collector: reader thread 唯一 callback collector。
    :returns: 本次 ``flush`` 同步产生的完整 callback batch。
    :raises RuntimeError: 上一次 resolution 的 callback 尚未清空时抛出。
    """

    if collector:
        raise RuntimeError("VT100 callback collector is not empty before flush")
    parser.flush()
    return _freeze_parser_resolution(collector)


def _freeze_parser_resolution(collector: list[KeyPress]) -> tuple[KeyPress, ...]:
    """冻结并清空一次同步 parser callback resolution。

    :param collector: reader thread 唯一 callback collector。
    :returns: 不再受 collector 后续写入影响的 callback tuple。
    :raises Exception: 不主动抛出异常。
    """

    batch = tuple(collector)
    collector.clear()
    return batch


def _classify_running_key_batch(
    batch: tuple[KeyPress, ...],
    *,
    is_ambiguity_flush: bool,
) -> tuple[RunningKeyAction, ...]:
    """把完整 parser resolution batch 投影为运行态动作。

    Escape callback 始终先视为 provisional。只有 ambiguity deadline 触发的
    flush 精确解析出单一 standalone Escape 时才取消；其它 callback 只按自身
    语义分类，因此同 batch 的 Ctrl+T 不会被 Escape 或 paste 吞掉。

    :param batch: 一次 public ``feed`` 或 ``flush`` 的完整同步 callback batch。
    :param is_ambiguity_flush: 本 batch 是否来自 ambiguity deadline 的 flush。
    :returns: 按 callback 顺序投影的运行态动作。
    :raises Exception: 不主动抛出异常。
    """

    actions = tuple(
        RunningKeyAction.TOGGLE_ACTIVITY
        for key_press in batch
        if key_press.key is Keys.ControlT
    )
    if not is_ambiguity_flush or len(batch) != 1:
        return actions
    standalone = batch[0]
    if standalone.key is Keys.Escape and standalone.data == _ESC_TEXT:
        return (RunningKeyAction.CANCEL_RUN, *actions)
    return actions


def _restore_terminal_attrs(fd: int, attrs: _TerminalAttributes) -> None:
    """恢复 TTY 原始终端属性。

    :param fd: TTY 文件描述符。
    :param attrs: ``termios.tcgetattr`` 返回的原始属性。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if not _POSIX_TERMINAL_CONTROL_AVAILABLE:
        return
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
)
