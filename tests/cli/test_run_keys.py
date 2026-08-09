"""CLI 运行态按键监听测试。"""

from __future__ import annotations

import asyncio
import codecs
import io
import os
import threading
from collections.abc import Callable
from contextlib import suppress
from typing import TextIO, cast

import pytest
from prompt_toolkit.input.vt100_parser import Vt100Parser
from prompt_toolkit.key_binding import KeyPress
from prompt_toolkit.keys import Keys

if os.name == "posix":
    import pty
    import termios

import dayu.cli.run_keys as run_keys
from dayu.cli.run_keys import (
    NoopRunningKeyMonitor,
    RunningKeyAction,
    TtyRunningKeyMonitor,
    new_running_key_monitor,
)

_UTF8_DECODER_CLASS = codecs.getincrementaldecoder("utf-8")


class _FailingThread:
    """测试用启动失败线程。"""

    def start(self) -> None:
        """模拟线程启动失败。

        :returns: 正常路径不会返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("thread start failed")


class _ReportedTty(io.StringIO):
    """报告为 TTY 的平台能力测试输入。"""

    def isatty(self) -> bool:
        """声明该输入是 TTY。

        :returns: 恒为 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True


class _RecordingEventLoop:
    """同步执行 reader-thread queue callback 的最小测试 event loop。"""

    callback_thread_ids: list[int]

    def __init__(self) -> None:
        """初始化空 callback thread 记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.callback_thread_ids = []

    def call_soon_threadsafe(
        self,
        callback: Callable[[RunningKeyAction], None],
        action: RunningKeyAction,
    ) -> None:
        """记录调用线程并同步执行 queue callback。

        :param callback: ``asyncio.Queue.put_nowait`` callback。
        :param action: 已完成 batch 分类的 typed action。
        :returns: ``None``。
        :raises Exception: callback 失败时向上透传。
        """

        self.callback_thread_ids.append(threading.get_ident())
        callback(action)


class _ScriptedSelectClock:
    """同时控制 ``select`` readiness 与 monotonic clock 的确定性 seam。"""

    steps: list[tuple[bool, float, bool]]
    now: float
    stop_event: threading.Event | None

    def __init__(self, steps: tuple[tuple[bool, float, bool], ...]) -> None:
        """初始化 readiness、时间推进与 stop 脚本。

        :param steps: 每轮的 readable、时间增量、是否同步 close。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.steps = list(steps)
        self.now = 0.0
        self.stop_event = None

    def monotonic(self) -> float:
        """返回当前可控 monotonic 时间。

        :returns: 当前秒数。
        :raises Exception: 不主动抛出异常。
        """

        return self.now

    def select(
        self,
        read_fds: tuple[int, ...],
        write_fds: tuple[()],
        error_fds: tuple[()],
        timeout: float,
    ) -> tuple[tuple[int, ...], tuple[()], tuple[()]]:
        """消费一轮 readiness 脚本并推进 clock。

        :param read_fds: reader 监听的文件描述符。
        :param write_fds: 固定空 write 集合。
        :param error_fds: 固定空 error 集合。
        :param timeout: production 计算出的 select timeout。
        :returns: 与 ``select.select`` 相同形状的三元组。
        :raises AssertionError: 脚本耗尽或传入非预期集合时抛出。
        """

        assert write_fds == ()
        assert error_fds == ()
        assert timeout >= 0.0
        if not self.steps:
            raise AssertionError("select script exhausted")
        readable, advance, stop = self.steps.pop(0)
        self.now += advance
        if stop:
            if self.stop_event is None:
                raise AssertionError("stop event missing")
            self.stop_event.set()
        return (read_fds if readable else ()), (), ()


class _ScriptedRead:
    """按顺序返回 raw TTY chunks 的确定性 ``os.read`` seam。"""

    chunks: list[bytes]

    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        """初始化 raw chunk 脚本。

        :param chunks: 每次 readable 后返回的 raw bytes。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.chunks = list(chunks)

    def read(self, fd: int, read_size: int) -> bytes:
        """消费并返回下一 raw chunk。

        :param fd: production reader fd。
        :param read_size: production 非语义 chunk size。
        :returns: 下一 raw chunk。
        :raises AssertionError: chunk 脚本耗尽时抛出。
        """

        assert fd == 7
        assert read_size > 0
        if not self.chunks:
            raise AssertionError("read script exhausted")
        return self.chunks.pop(0)


class _RecordingVt100Parser:
    """记录 public parser 构造与 resolution 调用线程的测试代理。"""

    constructor_thread_ids: list[int] = []
    resolution_thread_ids: list[int] = []
    resolution_kinds: list[str] = []
    _parser: Vt100Parser

    def __init__(self, callback: Callable[[KeyPress], None]) -> None:
        """记录构造线程并创建真实 public parser。

        :param callback: production callback collector 的 append callable。
        :returns: ``None``。
        :raises Exception: public parser 构造失败时向上透传。
        """

        self.constructor_thread_ids.append(threading.get_ident())
        self._parser = Vt100Parser(callback)

    def feed(self, data: str) -> None:
        """记录并委托一次 public feed。

        :param data: incremental decoder 产生的文本。
        :returns: ``None``。
        :raises Exception: public parser feed 失败时向上透传。
        """

        self.resolution_thread_ids.append(threading.get_ident())
        self.resolution_kinds.append("feed")
        self._parser.feed(data)

    def flush(self) -> None:
        """记录并委托一次 public flush。

        :returns: ``None``。
        :raises Exception: public parser flush 失败时向上透传。
        """

        self.resolution_thread_ids.append(threading.get_ident())
        self.resolution_kinds.append("flush")
        self._parser.flush()


class _RecordingUtf8Decoder:
    """记录唯一 UTF-8 incremental decoder 构造与 decode 线程。"""

    constructor_thread_ids: list[int] = []
    decode_thread_ids: list[int] = []
    _decoder: codecs.IncrementalDecoder

    def __init__(self, errors: str = "strict") -> None:
        """记录构造线程并创建真实 UTF-8 decoder。

        :param errors: 标准库 decoder error policy。
        :returns: ``None``。
        :raises Exception: decoder 构造失败时向上透传。
        """

        self.constructor_thread_ids.append(threading.get_ident())
        self._decoder = _UTF8_DECODER_CLASS(errors=errors)

    def decode(self, input: bytes, final: bool = False) -> str:
        """记录并委托一次 incremental decode。

        :param input: 当前 raw TTY bytes chunk。
        :param final: 是否为输入终点；reader 正常 chunk 固定为 ``False``。
        :returns: 当前可完整解码的 Unicode 文本。
        :raises UnicodeDecodeError: raw bytes 不是合法 UTF-8 时抛出。
        """

        self.decode_thread_ids.append(threading.get_ident())
        return self._decoder.decode(input, final)


def _recording_incremental_decoder_factory(
    encoding: str,
) -> type[codecs.IncrementalDecoder]:
    """为 UTF-8 codec lookup 返回记录型 decoder class。

    :param encoding: production 请求的 codec 名称。
    :returns: 记录型 incremental decoder class。
    :raises AssertionError: production 请求非 UTF-8 codec 时抛出。
    """

    assert encoding == "utf-8"
    return cast(type[codecs.IncrementalDecoder], _RecordingUtf8Decoder)


def _run_scripted_reader(
    *,
    monkeypatch: pytest.MonkeyPatch,
    chunks: tuple[bytes, ...],
    select_steps: tuple[tuple[bool, float, bool], ...],
) -> tuple[RunningKeyAction, ...]:
    """用可控 clock/select/raw chunks 同步执行一次 reader owner。

    :param monkeypatch: pytest 属性替换夹具。
    :param chunks: 每次 readable 后的 raw bytes；末项通常为空表示 EOF。
    :param select_steps: readable、monotonic 增量与 close 标志脚本。
    :returns: reader 投递到 asyncio queue 的全部 typed actions。
    :raises Exception: reader seam 或脚本不满足 contract 时向上透传。
    """

    monitor = TtyRunningKeyMonitor(stdin=io.StringIO())
    recording_loop = _RecordingEventLoop()
    clock = _ScriptedSelectClock(select_steps)
    scripted_read = _ScriptedRead(chunks)
    clock.stop_event = monitor._stop_event
    monitor._fd = 7
    monitor._loop = cast(asyncio.AbstractEventLoop, recording_loop)
    monkeypatch.setattr(run_keys.select, "select", clock.select)
    monkeypatch.setattr(run_keys.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(run_keys.os, "read", scripted_read.read)

    monitor._read_loop()

    actions: list[RunningKeyAction] = []
    while not monitor._queue.empty():
        actions.append(monitor._queue.get_nowait())
    assert all(
        thread_id == threading.get_ident()
        for thread_id in recording_loop.callback_thread_ids
    )
    return tuple(actions)


def test_public_vt100_parser_resolution_seam_matches_frozen_contract() -> None:
    """public parser 的 feed/flush batch 必须匹配冻结的 3.0.52 seam。"""

    collector: list[KeyPress] = []
    parser = Vt100Parser(collector.append)

    assert (
        run_keys._feed_parser_resolution(
            parser=parser,
            collector=collector,
            decoded_text="\x1b",
        )
        == ()
    )
    assert run_keys._flush_parser_resolution(
        parser=parser,
        collector=collector,
    ) == (KeyPress(Keys.Escape, "\x1b"),)

    same_chunk_collector: list[KeyPress] = []
    same_chunk_parser = Vt100Parser(same_chunk_collector.append)
    assert run_keys._feed_parser_resolution(
        parser=same_chunk_parser,
        collector=same_chunk_collector,
        decoded_text="\x1bx",
    ) == (KeyPress(Keys.Escape, "\x1b"), KeyPress("x", "x"))

    split_collector: list[KeyPress] = []
    split_parser = Vt100Parser(split_collector.append)
    assert (
        run_keys._feed_parser_resolution(
            parser=split_parser,
            collector=split_collector,
            decoded_text="\x1b",
        )
        == ()
    )
    assert run_keys._feed_parser_resolution(
        parser=split_parser,
        collector=split_collector,
        decoded_text="x",
    ) == (KeyPress(Keys.Escape, "\x1b"), KeyPress("x", "x"))


def test_running_key_batch_classifier_requires_flush_key_and_data() -> None:
    """standalone Escape 必须同时满足 flush、单 member、key 与 data。"""

    standalone = (KeyPress(Keys.Escape, "\x1b"),)

    assert run_keys._classify_running_key_batch(
        standalone,
        is_ambiguity_flush=True,
    ) == (RunningKeyAction.CANCEL_RUN,)
    assert (
        run_keys._classify_running_key_batch(
            standalone,
            is_ambiguity_flush=False,
        )
        == ()
    )
    assert (
        run_keys._classify_running_key_batch(
            (KeyPress(Keys.Escape, "\x1b[D"),),
            is_ambiguity_flush=True,
        )
        == ()
    )
    assert (
        run_keys._classify_running_key_batch(
            (KeyPress("x", "\x1b"),),
            is_ambiguity_flush=True,
        )
        == ()
    )


@pytest.mark.parametrize("is_ambiguity_flush", [False, True])
def test_running_key_batch_suppresses_escape_without_swallowing_ctrl_t(
    is_ambiguity_flush: bool,
) -> None:
    """provisional Escape 只能被抑制，不能吞掉同 batch 的 Ctrl+T。

    :param is_ambiguity_flush: 是否按 deadline flush batch 分类。
    """

    assert run_keys._classify_running_key_batch(
        (KeyPress(Keys.Escape, "\x1b"), KeyPress(Keys.ControlT, "\x14")),
        is_ambiguity_flush=is_ambiguity_flush,
    ) == (RunningKeyAction.TOGGLE_ACTIVITY,)
    assert run_keys._classify_running_key_batch(
        (
            KeyPress(Keys.Escape, "\x1b"),
            KeyPress("x", "x"),
            KeyPress(Keys.ControlT, "\x14"),
        ),
        is_ambiguity_flush=is_ambiguity_flush,
    ) == (RunningKeyAction.TOGGLE_ACTIVITY,)
    assert run_keys._classify_running_key_batch(
        (
            KeyPress(Keys.BracketedPaste, "payload\x14"),
            KeyPress(Keys.ControlT, "\x14"),
        ),
        is_ambiguity_flush=is_ambiguity_flush,
    ) == (RunningKeyAction.TOGGLE_ACTIVITY,)


@pytest.mark.parametrize(
    "sequence",
    [
        "\x1b[A",
        "\x1b[D",
        "\x1bOH",
        "\x1b[3~",
        "\x1b[1;3D",
        "\x1b[200~paste\x14\x1b[201~",
        "\x1bé",
        "\x03",
    ],
)
def test_complete_sequences_and_ctrl_c_do_not_create_cancel(sequence: str) -> None:
    """完整序列、paste、Alt Unicode 与 Ctrl+C byte 都不得产生取消。

    :param sequence: 交给唯一 public parser 的完整输入序列。
    """

    collector: list[KeyPress] = []
    parser = Vt100Parser(collector.append)
    batch = run_keys._feed_parser_resolution(
        parser=parser,
        collector=collector,
        decoded_text=sequence,
    )

    assert RunningKeyAction.CANCEL_RUN not in run_keys._classify_running_key_batch(
        batch,
        is_ambiguity_flush=False,
    )


@pytest.mark.parametrize(
    ("chunks", "select_steps", "expected"),
    (
        (
            (b"\x1b", b""),
            (
                (True, 0.0, False),
                (False, 0.05, False),
                (False, 0.05, False),
                (True, 0.0, False),
            ),
            (RunningKeyAction.CANCEL_RUN,),
        ),
        (
            (b"\x1b", b"[A", b""),
            (
                (True, 0.0, False),
                (True, 0.1, False),
                (False, 0.05, False),
                (False, 0.05, False),
                (True, 0.0, False),
            ),
            (),
        ),
        (
            (b"\x1b\xc3", b"\xa9", b""),
            (
                (True, 0.0, False),
                (True, 0.1, False),
                (False, 0.1, False),
                (True, 0.0, False),
            ),
            (),
        ),
        (
            (b"x\x1b", b""),
            (
                (True, 0.0, False),
                (False, 0.1, False),
                (True, 0.0, False),
            ),
            (RunningKeyAction.CANCEL_RUN,),
        ),
        (
            (b"\x1bx\x14", b""),
            (
                (True, 0.0, False),
                (False, 0.1, False),
                (True, 0.0, False),
            ),
            (RunningKeyAction.TOGGLE_ACTIVITY,),
        ),
    ),
)
def test_reader_uses_conservative_deadline_and_readable_priority(
    chunks: tuple[bytes, ...],
    select_steps: tuple[tuple[bool, float, bool], ...],
    expected: tuple[RunningKeyAction, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """reader 必须在 0.1s 边界先 feed readable，并只 flush 一次。

    :param chunks: raw input 与 EOF 脚本。
    :param select_steps: 可控 readiness/clock 脚本。
    :param expected: 精确 typed action 序列。
    :param monkeypatch: pytest 属性替换夹具。
    """

    assert _run_scripted_reader(
        monkeypatch=monkeypatch,
        chunks=chunks,
        select_steps=select_steps,
    ) == expected


def test_reader_close_wins_over_pending_escape_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close 与 deadline 同轮发生时不得 flush 或合成 cancel。

    :param monkeypatch: pytest 属性替换夹具。
    """

    assert (
        _run_scripted_reader(
            monkeypatch=monkeypatch,
            chunks=(b"\x1b",),
            select_steps=(
                (True, 0.0, False),
                (False, 0.1, True),
            ),
        )
        == ()
    )


def test_reader_readable_eof_wins_over_armed_deadline_without_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """deadline 已 armed 时 readable EOF 仍不得 flush 或合成 action。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises Exception: reader 违反 EOF owner contract 时由断言抛出。
    """

    _RecordingVt100Parser.constructor_thread_ids = []
    _RecordingVt100Parser.resolution_thread_ids = []
    _RecordingVt100Parser.resolution_kinds = []
    monkeypatch.setattr(run_keys, "Vt100Parser", _RecordingVt100Parser)

    actions = _run_scripted_reader(
        monkeypatch=monkeypatch,
        chunks=(b"\x1b", b""),
        select_steps=(
            (True, 0.0, False),
            (True, 0.1, False),
        ),
    )

    assert actions == ()
    assert _RecordingVt100Parser.resolution_kinds == ["feed"]


def test_reader_constructs_single_parser_and_decoder_on_owner_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """parser、decoder、resolution 与 queue publish 必须同属 reader thread。

    :param monkeypatch: pytest 属性替换夹具。
    """

    _RecordingVt100Parser.constructor_thread_ids = []
    _RecordingVt100Parser.resolution_thread_ids = []
    _RecordingVt100Parser.resolution_kinds = []
    _RecordingUtf8Decoder.constructor_thread_ids = []
    _RecordingUtf8Decoder.decode_thread_ids = []
    owner_thread_id = threading.get_ident()
    monkeypatch.setattr(run_keys, "Vt100Parser", _RecordingVt100Parser)
    monkeypatch.setattr(
        run_keys.codecs,
        "getincrementaldecoder",
        _recording_incremental_decoder_factory,
    )

    actions = _run_scripted_reader(
        monkeypatch=monkeypatch,
        chunks=(b"\x1b\xc3", b"\xa9\x14", b""),
        select_steps=(
            (True, 0.0, False),
            (True, 0.05, False),
            (False, 0.1, False),
            (True, 0.0, False),
        ),
    )

    assert actions == (RunningKeyAction.TOGGLE_ACTIVITY,)
    assert _RecordingVt100Parser.constructor_thread_ids == [owner_thread_id]
    assert _RecordingUtf8Decoder.constructor_thread_ids == [owner_thread_id]
    assert set(_RecordingVt100Parser.resolution_thread_ids) == {owner_thread_id}
    assert set(_RecordingUtf8Decoder.decode_thread_ids) == {owner_thread_id}


def test_new_running_key_monitor_uses_noop_for_non_tty() -> None:
    """非 TTY 输入应保持 no-op，不改变原有 CLI 行为。"""

    monitor = new_running_key_monitor(stdin=io.StringIO())

    assert isinstance(monitor, NoopRunningKeyMonitor)


def test_new_running_key_monitor_uses_noop_for_non_posix_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 POSIX 即使输入报告为 TTY 也必须使用 no-op owner boundary。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 非 POSIX 仍创建 POSIX monitor 时抛出。
    """

    monkeypatch.setattr(run_keys, "_POSIX_TERMINAL_CONTROL_AVAILABLE", False)

    monitor = new_running_key_monitor(stdin=_ReportedTty())

    assert isinstance(monitor, NoopRunningKeyMonitor)
    direct_monitor = TtyRunningKeyMonitor(stdin=_ReportedTty())
    direct_monitor.start()
    direct_monitor.close()


@pytest.mark.asyncio
async def test_noop_running_key_monitor_wait_is_cancellable() -> None:
    """no-op monitor 的等待应只由调用方取消。"""

    monitor = NoopRunningKeyMonitor()
    wait_task = asyncio.create_task(monitor.wait_next())

    wait_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await wait_task


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY contract")
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
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY contract")
async def test_tty_running_key_monitor_preserves_prestart_standalone_escape() -> None:
    """monitor 安装不得清空 invocation 启动后已到达的 standalone Escape。

    :returns: ``None``。
    :raises AssertionError: prestart byte 被 flush、误分类或 terminal mode 未恢复时抛出。
    """

    master_fd, slave_fd = pty.openpty()
    slave_stream = cast(TextIO, os.fdopen(slave_fd, "r", encoding="utf-8", buffering=1))
    original_lflag = termios.tcgetattr(slave_fd)[3]
    monitor = TtyRunningKeyMonitor(stdin=slave_stream, poll_interval_seconds=0.01)
    try:
        os.write(master_fd, b"\x1b")
        monitor.start()

        action = await asyncio.wait_for(monitor.wait_next(), timeout=1.0)

        assert action is RunningKeyAction.CANCEL_RUN
    finally:
        monitor.close()
        restored_lflag = termios.tcgetattr(slave_fd)[3]
        slave_stream.close()
        with suppress(OSError):
            os.close(master_fd)
    assert _terminal_lflag_controls(restored_lflag) == _terminal_lflag_controls(original_lflag)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY contract")
@pytest.mark.parametrize(
    "sequence",
    (
        b"\x1bx",
        b"\x1b[H\x1b[3~",
        b"\x1b[200~paste\nbody\x1b[201~",
    ),
)
async def test_tty_running_key_monitor_preserves_prestart_complete_sequences(
    sequence: bytes,
) -> None:
    """prestart Alt/CSI/paste 必须保留且不得降级为 standalone Escape。

    :param sequence: monitor 安装前已到达的完整 ESC-prefixed bytes。
    :returns: ``None``。
    :raises AssertionError: 序列被 flush、误取消或 terminal mode 未恢复时抛出。
    """

    master_fd, slave_fd = pty.openpty()
    slave_stream = cast(TextIO, os.fdopen(slave_fd, "r", encoding="utf-8", buffering=1))
    original_lflag = termios.tcgetattr(slave_fd)[3]
    monitor = TtyRunningKeyMonitor(stdin=slave_stream, poll_interval_seconds=0.01)
    try:
        os.write(master_fd, sequence)
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
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY contract")
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
