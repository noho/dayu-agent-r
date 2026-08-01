"""interactive typed composer 与真实终端解析 owner tests。"""

from __future__ import annotations

import asyncio
import io
import os
from contextlib import suppress
from typing import TextIO, cast

import pytest
from prompt_toolkit.input import create_input
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.key_binding.key_bindings import KeyBindings, KeyHandlerCallable
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput

if os.name == "posix":
    import pty
    import termios

from dayu.cli.composer import (
    InteractiveCancelSource,
    InteractiveComposerEvent,
    InteractiveComposerEventKind,
    InteractiveComposerPhase,
    PromptToolkitInteractiveComposer,
    XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER,
    build_interactive_key_bindings,
    new_interactive_composer,
)

_PTY_READINESS_TIMEOUT_SECONDS = 2.0
_PTY_READINESS_POLL_SECONDS = 0.005


class _EditorFailureBuffer:
    """只实现外部编辑器失败路径的 prompt_toolkit buffer 替身。"""

    def open_in_editor(self, *, validate_and_handle: bool) -> None:
        """抛出包含敏感文本的固定编辑器错误。

        :param validate_and_handle: 必须为 ``False`` 的 editor 参数。
        :returns: 正常路径不返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        assert not validate_and_handle
        raise RuntimeError("secret-editor-command --token hidden")


class _EditorFailureApp:
    """外部编辑器失败测试的 application 替身。"""

    current_buffer: _EditorFailureBuffer

    def __init__(self) -> None:
        """初始化 fake application。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.current_buffer = _EditorFailureBuffer()


class _EditorFailureEvent:
    """外部编辑器失败测试的 key event 替身。"""

    app: _EditorFailureApp

    def __init__(self) -> None:
        """初始化 fake key event。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.app = _EditorFailureApp()


def test_composer_event_rejects_open_field_combinations() -> None:
    """typed event 必须拒绝缺 draft、额外 draft 与缺 cancel source。

    :returns: ``None``。
    :raises AssertionError: 非法事件组合未在构造期拒绝时抛出。
    """

    with pytest.raises(ValueError, match="requires draft"):
        InteractiveComposerEvent(kind=InteractiveComposerEventKind.SUBMIT)
    with pytest.raises(ValueError, match="must not carry draft"):
        InteractiveComposerEvent(
            kind=InteractiveComposerEventKind.EOF,
            draft="unexpected",
        )
    with pytest.raises(ValueError, match="requires cancel source"):
        InteractiveComposerEvent(kind=InteractiveComposerEventKind.CANCEL_ACTIVE)
    with pytest.raises(ValueError, match="non-negative"):
        InteractiveComposerEvent(
            kind=InteractiveComposerEventKind.EOF,
            input_revision=-1,
        )


def test_new_interactive_composer_has_no_non_tty_adapter_seam() -> None:
    """composer factory 必须只产生 prompt_toolkit TTY owner。

    :returns: ``None``。
    :raises AssertionError: factory 仍产生非 TTY adapter 时抛出。
    """

    assert isinstance(new_interactive_composer(), PromptToolkitInteractiveComposer)


@pytest.mark.asyncio
async def test_ctrl_j_and_exact_xterm_shift_enter_insert_lf_before_submit() -> None:
    """Ctrl+J 与 exact modifyOtherKeys Shift+Enter 都只插入 LF。

    :returns: ``None``。
    :raises AssertionError: 任一序列未插入 exact LF 时抛出。
    """

    ctrl_j = await _read_pipe_event(
        phase=InteractiveComposerPhase.IDLE,
        text="甲\x0a乙\r",
    )
    shifted = await _read_pipe_event(
        phase=InteractiveComposerPhase.IDLE,
        text=f"甲{XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER}乙\r",
    )

    assert ctrl_j.kind is InteractiveComposerEventKind.SUBMIT
    assert ctrl_j.draft == "甲\n乙"
    assert shifted.kind is InteractiveComposerEventKind.SUBMIT
    assert shifted.draft == "甲\n乙"


@pytest.mark.asyncio
async def test_ordinary_enter_submits_without_inserting_lf() -> None:
    """普通 CR/Enter 必须提交 exact draft，不能误判为 Shift+Enter。

    :returns: ``None``。
    :raises AssertionError: 普通 Enter 被解释为换行时抛出。
    """

    event = await _read_pipe_event(
        phase=InteractiveComposerPhase.IDLE,
        text="ordinary\r",
    )

    assert event.kind is InteractiveComposerEventKind.SUBMIT
    assert event.draft == "ordinary"
    assert event.input_revision > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prefix",
    (
        "\x1b[A",
        "\x1bf",
        "\x1b[200~粘贴\n内容\x1b[201~",
    ),
)
async def test_complete_csi_alt_and_bracketed_paste_do_not_emit_cancel(
    prefix: str,
) -> None:
    """完整 CSI、Alt 与 bracketed paste 必须进入默认编辑语义而非 Escape。

    :param prefix: 写入 parser 的完整 ESC-prefixed 序列。
    :returns: ``None``。
    :raises AssertionError: 完整序列被误投影为 cancel 时抛出。
    """

    event = await _read_pipe_event(
        phase=InteractiveComposerPhase.RUNNING,
        text=f"{prefix}问题\r",
    )

    assert event.kind is InteractiveComposerEventKind.SUBMIT
    assert event.cancel_source is None
    assert event.draft is not None
    assert "问题" in event.draft


@pytest.mark.asyncio
async def test_standalone_escape_waits_for_sequence_resolution_and_restores_draft() -> None:
    """standalone Escape 只在解析器 timeout 后发 cancel，并保留 draft/cursor。

    :returns: ``None``。
    :raises AssertionError: Escape 解析或草稿恢复不符合契约时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        composer.set_phase(InteractiveComposerPhase.RUNNING)
        cancel_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("ab\x1b[D\x1b")
        cancel_event = await asyncio.wait_for(cancel_task, timeout=2.0)

        assert cancel_event.kind is InteractiveComposerEventKind.CANCEL_ACTIVE
        assert cancel_event.cancel_source is InteractiveCancelSource.ESCAPE

        submit_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("X\r")
        submit_event = await asyncio.wait_for(submit_task, timeout=2.0)

    assert submit_event.kind is InteractiveComposerEventKind.SUBMIT
    assert submit_event.draft == "aXb"


@pytest.mark.asyncio
async def test_ctrl_c_phase_matrix_and_submit_acknowledgement() -> None:
    """Ctrl+C 应清 idle draft、active cancel，并只在确认后清草稿/history。

    :returns: ``None``。
    :raises AssertionError: phase 或 submit acknowledgement 语义不符时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        idle_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("   \x03\x03")
        idle_event = await asyncio.wait_for(idle_task, timeout=2.0)
        assert idle_event.kind is InteractiveComposerEventKind.IDLE_INTERRUPT
        assert idle_event.input_revision > 0

        composer.set_phase(InteractiveComposerPhase.RUNNING)
        cancel_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("type-ahead\x03")
        cancel_event = await asyncio.wait_for(cancel_task, timeout=2.0)
        assert cancel_event.cancel_source is InteractiveCancelSource.CTRL_C

        submit_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("\r")
        submit_event = await asyncio.wait_for(submit_task, timeout=2.0)
        assert submit_event.draft == "type-ahead"
        assert composer._history.get_strings() == []
        composer.accept_submit(record_history=True)

    assert composer._history.get_strings() == ["type-ahead"]
    assert composer._draft == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("draft", ("非空草稿", "   "))
async def test_ctrl_c_idle_draft_clears_before_idle_interrupt(draft: str) -> None:
    """idle 非空或纯空白 draft 的首次 Ctrl+C 都只能清空并重绘。

    :param draft: 待清空的非空或纯空白草稿。
    :returns: ``None``。
    :raises Exception: composer 未按期返回 typed event 时向上透传。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text(f"{draft}\x03")
        await asyncio.sleep(0.05)
        assert not task.done()
        pipe_input.send_text("\x03")
        event = await asyncio.wait_for(task, timeout=2.0)

    assert event.kind is InteractiveComposerEventKind.IDLE_INTERRUPT
    assert composer._draft == ""


@pytest.mark.asyncio
async def test_active_typeahead_survives_terminal_phase_change() -> None:
    """active Unicode、paste 与编辑后的 draft 应跨 terminal phase 保留。

    :returns: ``None``。
    :raises AssertionError: phase 变化导致 draft 丢失或改写时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        composer.set_phase(InteractiveComposerPhase.RUNNING)
        task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("前缀中文\x1b[200~粘贴\n内容\x1b[201~\x1b[DZ")
        await asyncio.sleep(0.05)
        assert not task.done()
        composer.set_phase(InteractiveComposerPhase.IDLE)
        pipe_input.send_text("\r")
        event = await asyncio.wait_for(task, timeout=2.0)

    assert event.kind is InteractiveComposerEventKind.SUBMIT
    assert event.draft == "前缀中文粘贴\n内Z容"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase",
    (InteractiveComposerPhase.RUNNING, InteractiveComposerPhase.CANCELLING),
)
async def test_ctrl_d_is_noop_in_active_phases(
    phase: InteractiveComposerPhase,
) -> None:
    """active/cancelling 的一次或连续 Ctrl+D 都不得 cancel 或退出。

    :param phase: 待验证的 active composer phase。
    :returns: ``None``。
    :raises AssertionError: Ctrl+D 结束输入或改写 draft 时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        composer.set_phase(phase)
        task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("\x04\x04")
        await asyncio.sleep(0.05)
        assert not task.done()
        pipe_input.send_text("保留\r")
        event = await asyncio.wait_for(task, timeout=2.0)

    assert event.kind is InteractiveComposerEventKind.SUBMIT
    assert event.draft == "保留"


@pytest.mark.asyncio
async def test_ctrl_d_idle_empty_is_eof_and_nonempty_deletes_under_cursor() -> None:
    """idle 空 buffer Ctrl+D 为 EOF，非空只删除光标下字符。

    :returns: ``None``。
    :raises AssertionError: idle Ctrl+D 未按 buffer 状态分流时抛出。
    """

    empty = await _read_pipe_event(
        phase=InteractiveComposerPhase.IDLE,
        text="\x04",
    )
    edited = await _read_pipe_event(
        phase=InteractiveComposerPhase.IDLE,
        text="ab\x1b[D\x04\r",
    )

    assert empty.kind is InteractiveComposerEventKind.EOF
    assert edited.draft == "a"


def test_editor_failure_is_stable_and_does_not_echo_exception_payload() -> None:
    """外部编辑器失败诊断必须稳定脱敏。

    :returns: ``None``。
    :raises AssertionError: diagnostic 泄漏异常 payload 时抛出。
    """

    stderr = io.StringIO()
    bindings = build_interactive_key_bindings(stderr=stderr)
    handler = _handler_for(bindings, (Keys.ControlX, Keys.ControlE))

    handler(cast(KeyPressEvent, _EditorFailureEvent()))

    assert stderr.getvalue() == "Interactive editor failed\n"
    assert "secret" not in stderr.getvalue()
    assert "RuntimeError" not in stderr.getvalue()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY contract")
async def test_real_posix_pty_exact_sequences_and_terminal_mode_restore() -> None:
    """真实 PTY 应解析 exact 序列并恢复 echo/canonical flags。

    :returns: ``None``。
    :raises AssertionError: bytes 解析或 terminal mode 恢复不符合契约时抛出。
    """

    master_fd, slave_fd = pty.openpty()
    slave_stream = cast(
        TextIO,
        os.fdopen(os.dup(slave_fd), "r", encoding="utf-8", buffering=1),
    )
    original_lflag = termios.tcgetattr(slave_fd)[3]
    prompt_input = create_input(stdin=slave_stream)
    try:
        composer = PromptToolkitInteractiveComposer(
            input=prompt_input,
            output=DummyOutput(),
        )
        composer.set_phase(InteractiveComposerPhase.RUNNING)
        submit_task = asyncio.create_task(composer.read_event("dayu> "))
        await _wait_for_pty_raw_mode(slave_fd)
        os.write(
            master_fd,
            (b"first\x1b[27;2;13~second\x1b[A\x1bf\x1b[200~paste\nbody\x1b[201~\r"),
        )
        submitted = await asyncio.wait_for(submit_task, timeout=2.0)
        restored_after_submit = termios.tcgetattr(slave_fd)[3]
        composer.accept_submit(record_history=True)

        ordinary_enter_task = asyncio.create_task(composer.read_event("dayu> "))
        await _wait_for_pty_raw_mode(slave_fd)
        os.write(master_fd, b"ordinary\r")
        ordinary_enter = await asyncio.wait_for(ordinary_enter_task, timeout=2.0)
        restored_after_ordinary_enter = termios.tcgetattr(slave_fd)[3]
        composer.accept_submit(record_history=True)

        cancel_task = asyncio.create_task(composer.read_event("dayu> "))
        await _wait_for_pty_raw_mode(slave_fd)
        os.write(master_fd, b"draft\x1b")
        cancelled = await asyncio.wait_for(cancel_task, timeout=2.0)
        restored_after_escape = termios.tcgetattr(slave_fd)[3]
    finally:
        prompt_input.close()
        slave_stream.close()
        os.close(slave_fd)
        with suppress(OSError):
            os.close(master_fd)

    assert submitted.kind is InteractiveComposerEventKind.SUBMIT
    assert submitted.draft is not None
    assert submitted.draft.startswith("first\nsecond")
    assert "paste\nbody" in submitted.draft
    assert ordinary_enter.kind is InteractiveComposerEventKind.SUBMIT
    assert ordinary_enter.draft == "ordinary"
    assert cancelled.cancel_source is InteractiveCancelSource.ESCAPE
    assert _terminal_lflag_controls(restored_after_submit) == _terminal_lflag_controls(original_lflag)
    assert _terminal_lflag_controls(restored_after_ordinary_enter) == _terminal_lflag_controls(original_lflag)
    assert _terminal_lflag_controls(restored_after_escape) == _terminal_lflag_controls(original_lflag)


async def _read_pipe_event(
    *,
    phase: InteractiveComposerPhase,
    text: str,
) -> InteractiveComposerEvent:
    """用 prompt_toolkit pipe input 读取一份 typed event。

    :param phase: composer phase。
    :param text: 写入 input parser 的原始字符序列。
    :returns: composer typed event。
    :raises Exception: composer 未在两秒内返回时向上透传。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        composer.set_phase(phase)
        task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text(text)
        return await asyncio.wait_for(task, timeout=2.0)


def _handler_for(
    bindings: KeyBindings,
    keys: tuple[Keys, ...],
) -> KeyHandlerCallable:
    """按 key sequence 取得绑定 handler。

    :param bindings: prompt_toolkit KeyBindings；测试边界使用具体实现。
    :param keys: key sequence。
    :returns: 对应 handler。
    :raises AssertionError: 未找到 handler 时抛出。
    """

    for binding in bindings.bindings:
        if binding.keys == keys:
            return binding.handler
    raise AssertionError(f"missing binding for {keys}")


def _terminal_lflag_controls(lflag: int) -> tuple[bool, bool, bool, bool]:
    """提取 PTY 测试关心的 echo/canonical/signal/extension flags。

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


async def _wait_for_pty_raw_mode(slave_fd: int) -> int:
    """等待真实 PTY slave 进入 prompt_toolkit raw mode。

    :param slave_fd: PTY slave 文件描述符。
    :returns: 观察到四项 local control flags 均关闭时的 ``lflag``。
    :raises AssertionError: 有界时间内未观察到 raw mode 时抛出。
    """

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _PTY_READINESS_TIMEOUT_SECONDS
    while loop.time() < deadline:
        lflag = termios.tcgetattr(slave_fd)[3]
        if _terminal_lflag_controls(lflag) == (False, False, False, False):
            return lflag
        await asyncio.sleep(_PTY_READINESS_POLL_SECONDS)
    raise AssertionError("PTY did not enter prompt_toolkit raw mode")
