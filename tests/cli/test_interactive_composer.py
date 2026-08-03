"""interactive typed composer 与真实终端解析 owner tests。"""

from __future__ import annotations

import asyncio
import io
import os
import shlex
import sys
from collections.abc import Awaitable, Callable
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, TextIO, cast

import pytest
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_input
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.key_binding.key_bindings import KeyBindings, KeyHandlerCallable
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput

import dayu.cli.composer as composer_module

if os.name == "posix":
    import pty
    import termios

from dayu.cli.composer import (
    InteractiveComposerEvent,
    InteractiveComposerEventKind,
    InteractiveComposerPhase,
    PromptToolkitInteractiveComposer,
    XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER,
    build_interactive_key_bindings,
    new_interactive_composer,
)
from dayu.cli.run_keys import ESCAPE_SEQUENCE_AMBIGUITY_SECONDS, RunningKeyAction

_PTY_READINESS_TIMEOUT_SECONDS = 2.0
_PTY_READINESS_POLL_SECONDS = 0.005


class _EditorBindingBuffer:
    """记录 editor binding 对 public buffer seam 的调用。"""

    document: Document
    open_calls: list[bool]
    open_tasks: list[asyncio.Task[None]]

    def __init__(self, document: Document) -> None:
        """初始化带精确草稿与光标的 buffer 替身。

        :param document: 初始 public document。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.document = document
        self.open_calls = []
        self.open_tasks = []

    def open_in_editor(
        self,
        *,
        validate_and_handle: bool,
    ) -> asyncio.Task[None]:
        """记录 system fallback public API 调用。

        :param validate_and_handle: 必须为 ``False`` 的 editor 参数。
        :returns: 模拟 public API 返回的 system editor task。
        :raises Exception: 不主动抛出异常。
        """

        self.open_calls.append(validate_and_handle)
        task = asyncio.create_task(asyncio.sleep(0))
        self.open_tasks.append(task)
        return task


class _EditorBindingApp:
    """外部编辑器 binding 测试的 application 替身。"""

    current_buffer: _EditorBindingBuffer

    def __init__(self, buffer: _EditorBindingBuffer) -> None:
        """初始化 fake application。

        :param buffer: 待暴露为 current buffer 的替身。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.current_buffer = buffer


class _EditorBindingEvent:
    """外部编辑器 binding 测试的 key event 替身。"""

    app: _EditorBindingApp

    def __init__(self, buffer: _EditorBindingBuffer) -> None:
        """初始化 fake key event。

        :param buffer: application 暴露的 current buffer。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.app = _EditorBindingApp(buffer)


class _EditorProcessMode(StrEnum):
    """测试 editor process 的封闭结果模式。"""

    SUCCESS = "success"
    NONZERO = "nonzero"
    SPAWN_ERROR = "spawn_error"
    INVALID_UTF8 = "invalid_utf8"


class _InvalidEditorConfigurationCase(StrEnum):
    """显式 editor 配置拒绝矩阵。"""

    BLANK = "blank"
    INVALID_SYNTAX = "invalid_syntax"
    MISSING = "missing"
    DIRECTORY = "directory"
    NON_EXECUTABLE = "non_executable"


class _EditorProcessScript:
    """记录 exact argv 并模拟 editor 修改或失败。"""

    mode: _EditorProcessMode
    calls: list[tuple[str, ...]]
    updated_bytes: bytes

    def __init__(
        self,
        mode: _EditorProcessMode,
        *,
        updated_bytes: bytes = b"edited\n",
    ) -> None:
        """初始化进程脚本。

        :param mode: 模拟的进程结果。
        :param updated_bytes: success 时写回 tempfile 的 bytes。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.mode = mode
        self.calls = []
        self.updated_bytes = updated_bytes

    def __call__(self, argv: tuple[str, ...]) -> int:
        """记录 argv 并模拟同步 editor 进程。

        :param argv: production 生成的 exact argv。
        :returns: success/readback 模式返回零，nonzero 返回七。
        :raises OSError: spawn-error 模式模拟启动失败。
        """

        self.calls.append(argv)
        if self.mode is _EditorProcessMode.SPAWN_ERROR:
            raise OSError("secret spawn payload")
        if self.mode is _EditorProcessMode.NONZERO:
            return 7
        temporary_path = Path(argv[-1])
        if self.mode is _EditorProcessMode.INVALID_UTF8:
            temporary_path.write_bytes(b"\xff")
        else:
            temporary_path.write_bytes(self.updated_bytes)
        return 0


class _ImmediateTerminalRunner:
    """同步调用 callback 的 public run_in_terminal 测试替身。"""

    calls: list[tuple[bool, bool]]

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []

    def __call__(
        self,
        function: Callable[[], int],
        render_cli_done: bool = False,
        in_executor: bool = False,
    ) -> Awaitable[int]:
        """返回立即运行 callback 的 awaitable。

        :param function: production 传入的同步进程 callback。
        :param render_cli_done: 是否先渲染 done 状态。
        :param in_executor: 是否要求 executor；production 必须为 ``True``。
        :returns: 产生 callback return code 的 awaitable。
        :raises Exception: callback 失败时由 awaitable 向上透传。
        """

        self.calls.append((render_cli_done, in_executor))
        return self._run(function)

    async def _run(self, function: Callable[[], int]) -> int:
        """执行同步 callback。

        :param function: 待运行 callback。
        :returns: callback return code。
        :raises Exception: callback 失败时向上透传。
        """

        return function()


class _PendingTerminalRunner(_ImmediateTerminalRunner):
    """运行 callback 后保持 pending，供 teardown 取消测试使用。"""

    entered: asyncio.Event
    cancelled: asyncio.Event

    def __init__(self) -> None:
        """初始化 pending/cancel barriers。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def _run(self, function: Callable[[], int]) -> int:
        """先运行 callback，再等待 task cancellation。

        :param function: 待运行 callback。
        :returns: 正常路径不会返回。
        :raises asyncio.CancelledError: teardown 取消 awaitable 时抛出。
        """

        function()
        self.entered.set()
        try:
            await asyncio.Future[None]()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("pending terminal runner completed without cancellation")


class _BlockedTerminalRunner(_ImmediateTerminalRunner):
    """在 release barrier 前保持 editor round trip pending。"""

    entered: asyncio.Event
    release: asyncio.Event

    def __init__(self) -> None:
        """初始化进入与释放 barrier。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def _run(self, function: Callable[[], int]) -> int:
        """等待显式释放后执行唯一 editor process callback。

        :param function: 待运行 callback。
        :returns: callback return code。
        :raises asyncio.CancelledError: task 在释放前被 teardown 取消时抛出。
        """

        self.entered.set()
        await self.release.wait()
        return function()


class _EditorRoundTripRecorder:
    """记录 async round trip 收到的同步 original document snapshot。"""

    calls: list[
        tuple[Buffer, composer_module._ExplicitEditorCommand, Document]
    ]

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []

    async def __call__(
        self,
        *,
        buffer: Buffer,
        command: composer_module._ExplicitEditorCommand,
        original_document: Document,
    ) -> composer_module._EditorProcessOutcome:
        """记录显式传入的 snapshot 并结束模拟 round trip。

        :param buffer: 当前 public buffer。
        :param command: 已验证的显式 editor 命令。
        :param original_document: 同步 call path 冻结的 document。
        :returns: ``CANCELLED``，避免测试替身修改 buffer。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append((buffer, command, original_document))
        return composer_module._EditorProcessOutcome.CANCELLED


class _EditorTempfileCleanupFailure:
    """记录 tempfile cleanup 尝试并稳定抛出 ``OSError``。"""

    calls: ClassVar[list[tuple[Path, bool]]] = []

    @staticmethod
    def unlink(path: Path, missing_ok: bool = False) -> None:
        """记录 unlink 参数并模拟 cleanup filesystem failure。

        :param path: 待删除 tempfile。
        :param missing_ok: production 传入的缺失容忍标记。
        :returns: 正常路径不返回。
        :raises OSError: 始终模拟 cleanup 失败。
        """

        _EditorTempfileCleanupFailure.calls.append((path, missing_ok))
        raise OSError("secret cleanup payload")


class _BufferChangeRecorder:
    """记录 public Buffer document 原子回填触发次数。"""

    calls: list[Document]

    def __init__(self) -> None:
        """初始化记录。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []

    def __call__(self, buffer: Buffer) -> None:
        """记录变更后的 public document。

        :param buffer: 触发 on_text_changed 的 public buffer。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls.append(buffer.document)


def test_composer_event_rejects_open_field_combinations() -> None:
    """typed event 必须拒绝缺 draft、额外 draft 与缺 running action。

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
    with pytest.raises(ValueError, match="requires action"):
        InteractiveComposerEvent(kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION)
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
async def test_ordinary_enter_records_submit_intent_until_repl_accepts() -> None:
    """普通 Enter 的非空提交意图必须持续到 REPL 明确认领。

    :returns: ``None``。
    :raises AssertionError: typed intent 生命周期早于 acceptance 被清除时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        read_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("ordinary\r")
        event = await asyncio.wait_for(read_task, timeout=2.0)

        assert event.kind is InteractiveComposerEventKind.SUBMIT
        assert composer.has_pending_submit_intent()

        composer.accept_submit(record_history=True)

    assert not composer.has_pending_submit_intent()


@pytest.mark.asyncio
async def test_reject_submit_delivery_clears_only_intent_and_restores_exact_draft() -> None:
    """拒绝 submit delivery 只能清 intent，并允许 exact document 原样重提。

    :returns: ``None``。
    :raises AssertionError: draft、cursor、revision、history 或 pending 状态漂移时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        with pytest.raises(RuntimeError, match="no pending submit"):
            composer.reject_submit_delivery()

        first_read = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("abc\x1b[D\r")
        first_event = await asyncio.wait_for(first_read, timeout=2.0)
        draft_before = composer._draft
        cursor_before = composer._cursor_position
        revision_before = composer._input_revision

        composer.reject_submit_delivery()

        assert not composer.has_pending_submit_intent()
        assert composer._pending_submit
        assert composer._draft == draft_before == "abc"
        assert composer._cursor_position == cursor_before == 2
        assert composer._input_revision == revision_before == first_event.input_revision
        assert composer._history.get_strings() == []

        retry_read = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("\r")
        retry_event = await asyncio.wait_for(retry_read, timeout=2.0)

        assert retry_event.draft == "abc"
        assert retry_event.input_revision == revision_before
        assert composer._cursor_position == cursor_before
        composer.reject_submit_delivery()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prefix",
    (
        "\x1b[A",
        "\x1b[H",
        "\x1b[3~",
        "\x1bx",
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
    assert event.running_key_action is None
    assert event.draft is not None
    assert "问题" in event.draft


@pytest.mark.asyncio
@pytest.mark.parametrize("split_chunks", (False, True))
async def test_exact_alt_x_is_resolved_before_standalone_escape(
    split_chunks: bool,
) -> None:
    """exact Alt+X 同 chunk 或歧义期内跨 chunk 都不得误发 cancel。

    :param split_chunks: 是否把 ESC prefix 与 ``x`` 分两次写入。
    :returns: ``None``。
    :raises AssertionError: 完整 Alt chord 被误分类为 standalone Escape 时抛出。
    """

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        composer.set_phase(InteractiveComposerPhase.RUNNING)
        task = asyncio.create_task(composer.read_event("dayu> "))
        if split_chunks:
            pipe_input.send_text("\x1b")
            await asyncio.sleep(ESCAPE_SEQUENCE_AMBIGUITY_SECONDS / 2)
            pipe_input.send_text("x")
        else:
            pipe_input.send_text("\x1bx")
        await asyncio.sleep(ESCAPE_SEQUENCE_AMBIGUITY_SECONDS * 2)
        assert not task.done()
        pipe_input.send_text("问题\r")
        event = await asyncio.wait_for(task, timeout=2.0)

    assert event.kind is InteractiveComposerEventKind.SUBMIT
    assert event.running_key_action is None
    assert event.draft == "问题"


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

        assert cancel_event.kind is InteractiveComposerEventKind.RUNNING_KEY_ACTION
        assert cancel_event.running_key_action is RunningKeyAction.CANCEL_RUN

        submit_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("X\r")
        submit_event = await asyncio.wait_for(submit_task, timeout=2.0)

    assert submit_event.kind is InteractiveComposerEventKind.SUBMIT
    assert submit_event.draft == "aXb"


@pytest.mark.asyncio
async def test_ctrl_c_phase_matrix_uses_sigint_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl+C 应清 idle draft，并只通过唯一 SIGINT seam 通知 driver。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises AssertionError: phase 或 submit acknowledgement 语义不符时抛出。
    """

    signal_count = 0

    def record_sigint() -> None:
        """记录 composer 转交给 SIGINT owner 的一次 Ctrl+C。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        nonlocal signal_count
        signal_count += 1

    monkeypatch.setattr(composer_module, "_raise_sigint", record_sigint)

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        idle_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("   \x03\x03\r")
        idle_event = await asyncio.wait_for(idle_task, timeout=2.0)
        assert idle_event.kind is InteractiveComposerEventKind.SUBMIT
        assert idle_event.draft == ""
        assert signal_count == 1

        composer.set_phase(InteractiveComposerPhase.RUNNING)
        cancel_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("type-ahead\x03\x1b")
        cancel_event = await asyncio.wait_for(cancel_task, timeout=2.0)
        assert cancel_event.running_key_action is RunningKeyAction.CANCEL_RUN
        assert signal_count == 2

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
async def test_ctrl_c_idle_draft_clears_before_sigint(
    draft: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """idle 非空 draft 的首次 Ctrl+C 清空，下一次才交给 SIGINT owner。

    :param draft: 待清空的非空或纯空白草稿。
    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises Exception: composer 未按期返回 typed event 时向上透传。
    """

    signal_count = 0

    def record_sigint() -> None:
        """记录一次转交给 SIGINT owner 的 Ctrl+C。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        nonlocal signal_count
        signal_count += 1

    monkeypatch.setattr(composer_module, "_raise_sigint", record_sigint)

    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            input=pipe_input,
            output=DummyOutput(),
        )
        task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text(f"{draft}\x03")
        await asyncio.sleep(0.05)
        assert not task.done()
        pipe_input.send_text("\x03\r")
        event = await asyncio.wait_for(task, timeout=2.0)

    assert event.kind is InteractiveComposerEventKind.SUBMIT
    assert event.draft == ""
    assert signal_count == 1
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


def test_editor_environment_selection_is_typed_and_visual_key_has_priority(
    tmp_path: Path,
) -> None:
    """VISUAL key 存在即优先，EDITOR 只在 VISUAL 缺失时生效。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: key 优先级或 typed command 投影漂移时抛出。
    """

    editor_path = tmp_path / "editor"
    editor_path.write_text("editor", encoding="utf-8")
    editor_path.chmod(0o700)

    editor_only = composer_module._resolve_explicit_editor_command(
        {"EDITOR": f"{shlex.quote(str(editor_path))} --wait"}
    )
    assert editor_only is not None
    assert editor_only.source is composer_module._EditorEnvironmentVariable.EDITOR
    assert editor_only.argv == (str(editor_path), "--wait")
    assert editor_only.resolved_executable == editor_path.resolve()

    with pytest.raises(composer_module._EditorConfigurationError) as raised:
        composer_module._resolve_explicit_editor_command(
            {
                "VISUAL": "   ",
                "EDITOR": str(editor_path),
            }
        )
    assert raised.value.source is composer_module._EditorEnvironmentVariable.VISUAL
    assert (
        raised.value.reason
        is composer_module._EditorConfigurationErrorReason.EMPTY_COMMAND
    )
    assert composer_module._resolve_explicit_editor_command({}) is None


@pytest.mark.parametrize("case", tuple(_InvalidEditorConfigurationCase))
def test_invalid_explicit_editor_is_actionable_without_fallback_or_process(
    case: _InvalidEditorConfigurationCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空白、非法语法、missing、目录与 nonexec 都必须 fail before launch。

    :param case: 配置拒绝矩阵 case。
    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: actionable/no-fallback/draft contract 漂移时抛出。
    """

    configured_value = _invalid_editor_configuration_value(case, tmp_path=tmp_path)
    monkeypatch.setenv("VISUAL", configured_value)
    monkeypatch.setenv("EDITOR", sys.executable)
    terminal_runner = _ImmediateTerminalRunner()
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    original_document = Document("sensitive draft", cursor_position=4)
    buffer = _EditorBindingBuffer(original_document)
    stderr = io.StringIO()
    bindings = build_interactive_key_bindings(stderr=stderr)
    handler = _handler_for(bindings, (Keys.ControlX, Keys.ControlE))

    handler(cast(KeyPressEvent, _EditorBindingEvent(buffer)))

    diagnostic = stderr.getvalue()
    assert "VISUAL" in diagnostic
    assert "取消 VISUAL/EDITOR" in diagnostic
    assert "Traceback" not in diagnostic
    assert "sensitive draft" not in diagnostic
    assert configured_value not in diagnostic
    assert buffer.document == original_document
    assert buffer.open_calls == []
    assert terminal_runner.calls == []


@pytest.mark.asyncio
async def test_unset_editor_uses_only_public_system_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个 key 真正不存在时只调用 public Buffer.open_in_editor(False)。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: unset 路径进入 CLI launcher 或参数漂移时抛出。
    """

    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    terminal_runner = _ImmediateTerminalRunner()
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    buffer = _EditorBindingBuffer(Document("draft", cursor_position=2))
    stderr = io.StringIO()
    handler = _handler_for(
        build_interactive_key_bindings(stderr=stderr),
        (Keys.ControlX, Keys.ControlE),
    )

    handler(cast(KeyPressEvent, _EditorBindingEvent(buffer)))
    await buffer.open_tasks[0]
    await asyncio.sleep(0)

    assert buffer.open_calls == [False]
    assert len(buffer.open_tasks) == 1
    assert terminal_runner.calls == []
    assert stderr.getvalue() == ""


@pytest.mark.asyncio
async def test_explicit_editor_zero_uses_exact_argv_and_one_public_document_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """return code zero 才读取 UTF-8、移除至多一个 LF 并原子回填一次。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: exact argv、tempfile 或回填 contract 漂移时抛出。
    """

    command = composer_module._resolve_explicit_editor_command(
        {"VISUAL": f"{shlex.quote(sys.executable)} --editor-flag"}
    )
    assert command is not None
    process_script = _EditorProcessScript(
        _EditorProcessMode.SUCCESS,
        updated_bytes="编辑结果\r\n\n".encode(),
    )
    terminal_runner = _ImmediateTerminalRunner()
    monkeypatch.setattr(composer_module, "_run_editor_process", process_script)
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    recorder = _BufferChangeRecorder()
    buffer = Buffer(
        document=Document("原草稿", cursor_position=1),
        on_text_changed=recorder,
    )

    outcome = await composer_module._open_explicit_editor(buffer, command)

    assert outcome is composer_module._EditorProcessOutcome.UPDATED
    assert terminal_runner.calls == [(False, True)]
    assert len(process_script.calls) == 1
    exact_argv = process_script.calls[0]
    assert exact_argv[:-1] == (str(command.resolved_executable), "--editor-flag")
    assert not Path(exact_argv[-1]).exists()
    expected_text = "编辑结果\r\n"
    assert buffer.document == Document(expected_text, cursor_position=len(expected_text))
    assert recorder.calls == [buffer.document]


@pytest.mark.asyncio
async def test_explicit_editor_freezes_original_document_before_task_scheduling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同步 launcher 必须先冻结完整 public document 再创建 async task。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: task 首调度前 buffer 变化污染 snapshot 时抛出。
    """

    command = composer_module._resolve_explicit_editor_command(
        {"VISUAL": sys.executable}
    )
    assert command is not None
    round_trip = _EditorRoundTripRecorder()
    monkeypatch.setattr(
        composer_module,
        "_run_explicit_editor_round_trip",
        round_trip,
    )
    original_document = Document("original draft", cursor_position=3)
    buffer = Buffer(document=original_document)

    task = composer_module._open_explicit_editor(buffer, command)
    buffer.document = Document("changed before scheduling", cursor_position=7)
    outcome = await task

    assert outcome is composer_module._EditorProcessOutcome.CANCELLED
    assert round_trip.calls == [(buffer, command, original_document)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_fragment"),
    (
        (_EditorProcessMode.SPAWN_ERROR, "无法启动"),
        (_EditorProcessMode.INVALID_UTF8, "无法读取"),
    ),
)
async def test_primary_editor_failure_survives_cleanup_failure(
    mode: _EditorProcessMode,
    expected_fragment: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spawn/readback 与 cleanup 双故障时必须保留 primary error。

    :param mode: primary failure 模式。
    :param expected_fragment: primary diagnostic 的稳定片段。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: cleanup 未尝试或覆盖 primary error 时抛出。
    """

    monkeypatch.setenv("VISUAL", sys.executable)
    monkeypatch.delenv("EDITOR", raising=False)
    process_script = _EditorProcessScript(mode)
    terminal_runner = _ImmediateTerminalRunner()
    monkeypatch.setattr(composer_module, "_run_editor_process", process_script)
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    original_unlink = Path.unlink
    _EditorTempfileCleanupFailure.calls.clear()
    monkeypatch.setattr(Path, "unlink", _EditorTempfileCleanupFailure.unlink)
    stderr = io.StringIO()
    buffer = _EditorBindingBuffer(Document("primary draft", cursor_position=2))
    handler = _handler_for(
        build_interactive_key_bindings(stderr=stderr),
        (Keys.ControlX, Keys.ControlE),
    )

    handler(cast(KeyPressEvent, _EditorBindingEvent(buffer)))
    await _wait_for_editor_task_callbacks()
    assert len(process_script.calls) == 1
    temporary_path = Path(process_script.calls[0][-1])
    try:
        assert _EditorTempfileCleanupFailure.calls == [(temporary_path, True)]
        diagnostic = stderr.getvalue()
        assert diagnostic.count(expected_fragment) == 1
        assert "无法清理" not in diagnostic
        assert "secret" not in diagnostic
        assert buffer.document == Document("primary draft", cursor_position=2)
    finally:
        original_unlink(temporary_path, missing_ok=True)
        _EditorTempfileCleanupFailure.calls.clear()


@pytest.mark.asyncio
async def test_editor_cancellation_survives_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """task cancellation 与 cleanup 双故障时必须原样传播取消身份。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: cleanup 未尝试或覆盖 ``CancelledError`` 时抛出。
    """

    command = composer_module._resolve_explicit_editor_command(
        {"VISUAL": sys.executable}
    )
    assert command is not None
    terminal_runner = _BlockedTerminalRunner()
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    original_unlink = Path.unlink
    _EditorTempfileCleanupFailure.calls.clear()
    monkeypatch.setattr(Path, "unlink", _EditorTempfileCleanupFailure.unlink)
    buffer = Buffer(document=Document("cancel draft", cursor_position=4))

    task = composer_module._open_explicit_editor(buffer, command)
    await asyncio.wait_for(terminal_runner.entered.wait(), timeout=2.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(_EditorTempfileCleanupFailure.calls) == 1
    temporary_path, missing_ok = _EditorTempfileCleanupFailure.calls[0]
    try:
        assert missing_ok
        assert temporary_path.exists()
        assert buffer.document == Document("cancel draft", cursor_position=4)
    finally:
        original_unlink(temporary_path, missing_ok=True)
        _EditorTempfileCleanupFailure.calls.clear()


@pytest.mark.asyncio
async def test_repeated_editor_shortcut_while_pending_launches_one_task_and_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EDITOR_PENDING 时重复快捷键不得启动第二 task/process 或回填。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 单一 pending invariant 漂移时抛出。
    """

    monkeypatch.setenv("VISUAL", sys.executable)
    monkeypatch.delenv("EDITOR", raising=False)
    process_script = _EditorProcessScript(_EditorProcessMode.SUCCESS)
    terminal_runner = _BlockedTerminalRunner()
    monkeypatch.setattr(composer_module, "_run_editor_process", process_script)
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    recorder = _BufferChangeRecorder()
    buffer = Buffer(
        document=Document("original", cursor_position=3),
        on_text_changed=recorder,
    )
    handler = _handler_for(
        build_interactive_key_bindings(stderr=io.StringIO()),
        (Keys.ControlX, Keys.ControlE),
    )
    event = cast(
        KeyPressEvent,
        _EditorBindingEvent(cast(_EditorBindingBuffer, buffer)),
    )

    handler(event)
    handler(event)
    pending_round_trips = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task()
        and task.get_coro().__qualname__.endswith("_run_explicit_editor_round_trip")
    ]
    assert len(pending_round_trips) == 1
    await asyncio.wait_for(terminal_runner.entered.wait(), timeout=2.0)
    await asyncio.sleep(0)
    assert terminal_runner.calls == [(False, True)]

    terminal_runner.release.set()
    await _wait_for_editor_task_callbacks()

    assert len(process_script.calls) == 1
    expected_document = Document("edited", cursor_position=len("edited"))
    assert buffer.document == expected_document
    assert recorder.calls == [expected_document]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_fragment", "silent"),
    (
        (_EditorProcessMode.SPAWN_ERROR, "无法启动", False),
        (_EditorProcessMode.NONZERO, "", True),
        (_EditorProcessMode.INVALID_UTF8, "无法读取", False),
    ),
)
async def test_explicit_editor_failure_matrix_preserves_document_and_cleans_tempfile(
    mode: _EditorProcessMode,
    expected_fragment: str,
    silent: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spawn/readback 失败 actionable，nonzero 静默，三者均保留 document。

    :param mode: process failure/cancel 模式。
    :param expected_fragment: actionable 路径预期诊断片段。
    :param silent: 是否要求 stderr 完全静默。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: outcome、诊断、fallback 或 cleanup 漂移时抛出。
    """

    monkeypatch.setenv("VISUAL", sys.executable)
    monkeypatch.setenv("EDITOR", "/must/not/fallback")
    process_script = _EditorProcessScript(mode)
    terminal_runner = _ImmediateTerminalRunner()
    monkeypatch.setattr(composer_module, "_run_editor_process", process_script)
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    original_document = Document("原草稿", cursor_position=1)
    buffer = _EditorBindingBuffer(original_document)
    stderr = io.StringIO()
    handler = _handler_for(
        build_interactive_key_bindings(stderr=stderr),
        (Keys.ControlX, Keys.ControlE),
    )

    handler(cast(KeyPressEvent, _EditorBindingEvent(buffer)))
    await _wait_for_editor_task_callbacks()

    assert terminal_runner.calls == [(False, True)]
    assert len(process_script.calls) == 1
    assert not Path(process_script.calls[0][-1]).exists()
    assert buffer.document == original_document
    assert buffer.open_calls == []
    if silent:
        assert stderr.getvalue() == ""
    else:
        diagnostic = stderr.getvalue()
        assert diagnostic.count(expected_fragment) == 1
        assert "VISUAL" in diagnostic
        assert "Traceback" not in diagnostic
        assert "secret" not in diagnostic
        assert process_script.calls[0][-1] not in diagnostic


@pytest.mark.asyncio
async def test_composer_teardown_cancels_editor_task_consumes_exception_and_cleans_tempfile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EDITOR_PENDING teardown 必须取消/消费 task 并删除 secure tempfile。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: task 强引用、取消、异常消费或 cleanup 漂移时抛出。
    """

    monkeypatch.setenv("VISUAL", sys.executable)
    monkeypatch.delenv("EDITOR", raising=False)
    process_script = _EditorProcessScript(_EditorProcessMode.NONZERO)
    terminal_runner = _PendingTerminalRunner()
    monkeypatch.setattr(composer_module, "_run_editor_process", process_script)
    monkeypatch.setattr(composer_module, "run_in_terminal", terminal_runner)
    stderr = io.StringIO()
    with create_pipe_input() as pipe_input:
        composer = PromptToolkitInteractiveComposer(
            stderr=stderr,
            input=pipe_input,
            output=DummyOutput(),
        )
        read_task = asyncio.create_task(composer.read_event("dayu> "))
        pipe_input.send_text("draft\x18\x05")
        await asyncio.wait_for(terminal_runner.entered.wait(), timeout=2.0)
        assert len(composer._editor_tasks) == 1
        assert len(process_script.calls) == 1
        temporary_path = Path(process_script.calls[0][-1])
        assert temporary_path.exists()

        read_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await read_task

    await asyncio.wait_for(terminal_runner.cancelled.wait(), timeout=2.0)
    assert composer._editor_tasks == set()
    assert not temporary_path.exists()
    assert stderr.getvalue() == ""


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
            (b"first\x1b[27;2;13~second\x1b[A\x1bx\x1b[200~paste\nbody\x1b[201~\r"),
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
    assert "first" in submitted.draft
    assert "second" in submitted.draft
    assert "paste\nbody" in submitted.draft
    assert ordinary_enter.kind is InteractiveComposerEventKind.SUBMIT
    assert ordinary_enter.draft == "ordinary"
    assert cancelled.running_key_action is RunningKeyAction.CANCEL_RUN
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


def _invalid_editor_configuration_value(
    case: _InvalidEditorConfigurationCase,
    *,
    tmp_path: Path,
) -> str:
    """构造 editor 配置拒绝矩阵的精确环境值。

    :param case: 拒绝矩阵 case。
    :param tmp_path: pytest 临时目录。
    :returns: 对应的显式环境变量值。
    :raises AssertionError: 收到未支持 case 时抛出。
    """

    if case is _InvalidEditorConfigurationCase.BLANK:
        return "   "
    if case is _InvalidEditorConfigurationCase.INVALID_SYNTAX:
        return "'unterminated"
    if case is _InvalidEditorConfigurationCase.MISSING:
        return str(tmp_path / "missing-editor")
    if case is _InvalidEditorConfigurationCase.DIRECTORY:
        directory = tmp_path / "editor-directory"
        directory.mkdir()
        return str(directory)
    if case is _InvalidEditorConfigurationCase.NON_EXECUTABLE:
        non_executable = tmp_path / "non-executable-editor"
        non_executable.write_text("not executable", encoding="utf-8")
        non_executable.chmod(0o600)
        return str(non_executable)
    raise AssertionError(f"unsupported invalid editor case: {case}")


async def _wait_for_editor_task_callbacks() -> None:
    """等待 create_task 与 done callback 完成一个有界调度轮次。

    :returns: ``None``。
    :raises AssertionError: editor callback 未在有界调度轮次内完成时抛出。
    """

    for _attempt in range(100):
        await asyncio.sleep(0)
        pending = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
            and task.get_coro().__qualname__.endswith("_run_explicit_editor_round_trip")
        ]
        if not pending:
            await asyncio.sleep(0)
            return
    raise AssertionError("editor task callback did not complete")


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
