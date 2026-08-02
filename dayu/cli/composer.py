"""interactive TTY 输入态 composer。

本模块是 interactive 终端输入、草稿、光标和历史记录的唯一 owner。它把
``prompt_toolkit`` 的按键与 buffer 语义投影为严格类型事件，CLI REPL 不接触
``prompt_toolkit`` 类型，Service / Host / Engine 也不依赖终端解析实现。
"""

from __future__ import annotations

import asyncio
import os
import signal
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Final, Protocol, TextIO, TypeAlias

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import Output

from dayu.cli.run_keys import RunningKeyAction

XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER: Final[str] = "\x1b[27;2;13~"
"""xterm modifyOtherKeys 协议中 Shift+Enter 的完整字节序列。"""

_EDITOR_RECOVERY_ACTION: Final[str] = (
    "请修正 {source}，或取消 VISUAL/EDITOR 以启用系统默认编辑器。"
)
_SYSTEM_EDITOR_FAILURE_MESSAGE: Final[str] = "系统默认编辑器无法启动，草稿已保留。"
_EXPLICIT_EDITOR_TEMPFILE_PREFIX: Final[str] = "dayu-editor-"
_EXPLICIT_EDITOR_TEMPFILE_SUFFIX: Final[str] = ".txt"


class _EditorEnvironmentVariable(StrEnum):
    """CLI 支持的外部编辑器环境变量。"""

    VISUAL = "VISUAL"
    EDITOR = "EDITOR"


class _EditorConfigurationErrorReason(StrEnum):
    """显式编辑器配置失败的封闭原因。"""

    EMPTY_COMMAND = "empty_command"
    INVALID_SYNTAX = "invalid_syntax"
    EXECUTABLE_NOT_FOUND = "executable_not_found"
    NOT_EXECUTABLE = "not_executable"


class _EditorActionFailureReason(StrEnum):
    """显式编辑器 round trip 失败的封闭原因。"""

    TEMPFILE_UNAVAILABLE = "tempfile_unavailable"
    SPAWN_FAILED = "spawn_failed"
    READBACK_FAILED = "readback_failed"
    CLEANUP_FAILED = "cleanup_failed"


class _EditorProcessOutcome(StrEnum):
    """显式编辑器进程完成后的封闭结果。"""

    UPDATED = "updated"
    CANCELLED = "cancelled"


_EditorTask: TypeAlias = (
    asyncio.Task[_EditorProcessOutcome] | asyncio.Task[None]
)
"""单个 composer 持有的显式或系统 editor task。"""


@dataclass(frozen=True, slots=True)
class _ExplicitEditorCommand:
    """一份完成安全解析与可执行性校验的显式编辑器命令。

    :param source: 命令来自哪个受支持环境变量。
    :param argv: 经 ``shlex`` 解析的原始参数，不含后续 tempfile 路径。
    :param resolved_executable: 已解析并验证的可执行普通文件路径。
    """

    source: _EditorEnvironmentVariable
    argv: tuple[str, ...]
    resolved_executable: Path


class _EditorConfigurationError(ValueError):
    """显式编辑器配置在进程启动前不可执行。"""

    reason: _EditorConfigurationErrorReason
    source: _EditorEnvironmentVariable
    display_name: str

    def __init__(
        self,
        *,
        reason: _EditorConfigurationErrorReason,
        source: _EditorEnvironmentVariable,
    ) -> None:
        """保存安全、封闭的配置失败信息。

        :param reason: 配置失败原因。
        :param source: 失败配置所属的环境变量。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(reason.value)
        self.reason = reason
        self.source = source
        self.display_name = source.value


class _EditorActionError(RuntimeError):
    """显式编辑器 round trip 的安全内部失败。"""

    reason: _EditorActionFailureReason
    source: _EditorEnvironmentVariable

    def __init__(
        self,
        *,
        reason: _EditorActionFailureReason,
        source: _EditorEnvironmentVariable,
    ) -> None:
        """保存不含命令、异常正文或 tempfile 路径的失败信息。

        :param reason: round trip 失败原因。
        :param source: 显式命令所属的环境变量。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(reason.value)
        self.reason = reason
        self.source = source


class InteractiveComposerPhase(StrEnum):
    """interactive composer 当前输入阶段。"""

    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"


class InteractiveComposerEventKind(StrEnum):
    """interactive composer 对 REPL 暴露的封闭事件种类。"""

    SUBMIT = "submit"
    RUNNING_KEY_ACTION = "running_key_action"
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class InteractiveComposerEvent:
    """interactive composer 产生的一次类型化事件。

    :param kind: 事件种类。
    :param draft: ``SUBMIT`` 的原始草稿；其它事件必须为 ``None``。
    :param input_revision: composer 已观察到的用户编辑版本，用于判定两次
        idle Ctrl+C 之间是否发生过正常编辑。
    :param running_key_action: active phase 的唯一 typed key action；其它事件
        必须为 ``None``。
    """

    kind: InteractiveComposerEventKind
    draft: str | None = None
    input_revision: int = 0
    running_key_action: RunningKeyAction | None = None

    def __post_init__(self) -> None:
        """校验事件字段组合。

        :returns: ``None``。
        :raises ValueError: event kind、draft 或输入版本组合非法时抛出。
        """

        if self.input_revision < 0:
            raise ValueError("input_revision must be non-negative")
        if self.kind is InteractiveComposerEventKind.SUBMIT:
            if self.draft is None:
                raise ValueError("submit event requires draft")
            if self.running_key_action is not None:
                raise ValueError("submit event must not carry running key action")
            return
        if self.draft is not None:
            raise ValueError("non-submit event must not carry draft")
        if self.kind is InteractiveComposerEventKind.RUNNING_KEY_ACTION:
            if self.running_key_action is None:
                raise ValueError("running key event requires action")
            return
        if self.running_key_action is not None:
            raise ValueError("non-running-key event must not carry action")


class InteractiveComposer(Protocol):
    """interactive TTY composer 窄协议。"""

    def set_phase(self, phase: InteractiveComposerPhase) -> None:
        """更新当前按键阶段。

        :param phase: REPL 当前阶段。
        :returns: ``None``。
        :raises Exception: phase 更新失败时向上透传。
        """

        ...

    def accept_submit(self, *, record_history: bool) -> None:
        """确认上一份 ``SUBMIT`` 已由 REPL 消费。

        :param record_history: 是否把 exact draft 写入 composer history；真实
            Run submit 为 ``True``，空白 no-op 为 ``False``。
        :returns: ``None``。
        :raises RuntimeError: 当前没有待确认 ``SUBMIT`` 时抛出。
        """

        ...

    async def read_event(self, prompt: str) -> InteractiveComposerEvent:
        """读取下一次类型化 composer 事件。

        :param prompt: 输入提示文本。
        :returns: 下一次 composer 事件。
        :raises Exception: ``prompt_toolkit`` 初始化或运行失败时向上透传。
        """

        ...


class _ComposerEventSignal(Exception):
    """把 prompt_toolkit application exit 投影为 typed composer event。"""

    event: InteractiveComposerEvent
    document: Document

    def __init__(
        self,
        *,
        event: InteractiveComposerEvent,
        document: Document,
    ) -> None:
        """保存事件与退出时的精确文档状态。

        :param event: 待投影给 REPL 的 typed event。
        :param document: 退出 application 时的精确 buffer 文档。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(event.kind.value)
        self.event = event
        self.document = document


_PhaseProvider = Callable[[], InteractiveComposerPhase]
_RevisionProvider = Callable[[], int]


class PromptToolkitInteractiveComposer:
    """基于 prompt_toolkit 的唯一 interactive TTY composer。"""

    _session: PromptSession[str]
    _history: InMemoryHistory
    _phase: InteractiveComposerPhase
    _draft: str
    _cursor_position: int
    _input_revision: int
    _pending_submit: bool
    _tracking_user_edits: bool
    _editor_tasks: set[_EditorTask]

    def __init__(
        self,
        *,
        stderr: TextIO | None = None,
        input: Input | None = None,
        output: Output | None = None,
    ) -> None:
        """初始化 prompt_toolkit composer。

        :param stderr: diagnostic 输出流；``None`` 表示当前 ``sys.stderr``。
        :param input: 可选 prompt_toolkit 输入；生产默认使用标准 TTY。
        :param output: 可选 prompt_toolkit 输出；生产默认使用标准 TTY。
        :returns: ``None``。
        :raises Exception: prompt_toolkit 初始化失败时向上抛出。
        """

        self._history = InMemoryHistory()
        self._phase = InteractiveComposerPhase.IDLE
        self._draft = ""
        self._cursor_position = 0
        self._input_revision = 0
        self._pending_submit = False
        self._tracking_user_edits = False
        self._editor_tasks = set()
        self._session = PromptSession(
            history=self._history,
            key_bindings=_build_interactive_key_bindings(
                stderr=sys.stderr if stderr is None else stderr,
                phase_provider=self._current_phase,
                revision_provider=self._current_input_revision,
                editor_tasks=self._editor_tasks,
            ),
            enable_history_search=True,
            enable_open_in_editor=True,
            input=input,
            output=output,
        )
        self._session.default_buffer.on_text_changed += self._record_text_change

    def set_phase(self, phase: InteractiveComposerPhase) -> None:
        """更新按键阶段。

        :param phase: REPL 当前阶段。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._phase = phase

    def accept_submit(self, *, record_history: bool) -> None:
        """确认并清空上一份已由 REPL 消费的草稿。

        若 sole queued slot 已占用，REPL 不调用本方法，下一次
        ``read_event`` 会恢复原草稿与光标。

        :param record_history: 是否把 exact draft 写入 history。
        :returns: ``None``。
        :raises RuntimeError: 当前没有待确认 ``SUBMIT`` 时抛出。
        """

        if not self._pending_submit:
            raise RuntimeError("interactive composer has no pending submit")
        if record_history:
            self._history.append_string(self._draft)
        self._draft = ""
        self._cursor_position = 0
        self._pending_submit = False

    async def read_event(self, prompt: str) -> InteractiveComposerEvent:
        """读取下一次 interactive typed event。

        :param prompt: 输入提示文本。
        :returns: 下一次 composer 事件。
        :raises Exception: prompt_toolkit 运行失败时向上透传。
        """

        if self._pending_submit:
            # 上一份 SUBMIT 未被 REPL 确认，保留 exact draft/cursor，但允许
            # 用户继续编辑并重新提交。
            self._pending_submit = False
        document = Document(
            text=self._draft,
            cursor_position=self._cursor_position,
        )
        self._tracking_user_edits = False
        try:
            submitted_text = await self._session.prompt_async(
                prompt,
                multiline=False,
                handle_sigint=False,
                default=document,
                pre_run=self._begin_tracking_user_edits,
            )
        except _ComposerEventSignal as signal:
            self._remember_document(signal.document)
            self._pending_submit = signal.event.kind is InteractiveComposerEventKind.SUBMIT
            return signal.event
        finally:
            self._tracking_user_edits = False
            await _cancel_editor_tasks(self._editor_tasks)
        self._remember_document(Document(submitted_text))
        self._pending_submit = True
        return InteractiveComposerEvent(
            kind=InteractiveComposerEventKind.SUBMIT,
            draft=submitted_text,
            input_revision=self._input_revision,
        )

    def _current_phase(self) -> InteractiveComposerPhase:
        """返回当前 composer phase。

        :returns: 当前 phase。
        :raises Exception: 不主动抛出异常。
        """

        return self._phase

    def _current_input_revision(self) -> int:
        """返回当前用户编辑版本。

        :returns: 非负编辑版本。
        :raises Exception: 不主动抛出异常。
        """

        return self._input_revision

    def _begin_tracking_user_edits(self) -> None:
        """在 prompt_toolkit 完成默认文档恢复后开始记录用户编辑。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._tracking_user_edits = True

    def _record_text_change(self, _buffer: Buffer) -> None:
        """记录 application 运行期间的真实 buffer 文本变化。

        :param _buffer: prompt_toolkit 当前 default buffer。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._tracking_user_edits:
            self._input_revision += 1

    def _remember_document(self, document: Document) -> None:
        """保存精确草稿与光标供下一次 application 恢复。

        :param document: prompt_toolkit 文档快照。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._draft = document.text
        self._cursor_position = document.cursor_position


def build_interactive_key_bindings(
    *,
    stderr: TextIO | None = None,
    phase_provider: _PhaseProvider | None = None,
    revision_provider: _RevisionProvider | None = None,
) -> KeyBindings:
    """构造 interactive composer key bindings。

    :param stderr: 外部编辑器失败诊断输出流；``None`` 表示当前 ``sys.stderr``。
    :param phase_provider: 当前 composer phase provider；省略时固定为 idle。
    :param revision_provider: 当前用户编辑版本 provider；省略时固定为零。
    :returns: prompt_toolkit key bindings。
    :raises Exception: 不主动抛出异常。
    """

    return _build_interactive_key_bindings(
        stderr=sys.stderr if stderr is None else stderr,
        phase_provider=_idle_phase if phase_provider is None else phase_provider,
        revision_provider=_zero_revision if revision_provider is None else revision_provider,
        editor_tasks=set(),
    )


def _build_interactive_key_bindings(
    *,
    stderr: TextIO,
    phase_provider: _PhaseProvider,
    revision_provider: _RevisionProvider,
    editor_tasks: set[_EditorTask],
) -> KeyBindings:
    """构造绑定并接入当前 composer 持有的 editor task 集合。

    :param stderr: 安全 editor diagnostic 输出流。
    :param phase_provider: 当前 composer phase provider。
    :param revision_provider: 当前用户编辑版本 provider。
    :param editor_tasks: composer 强引用并在 teardown 清理的唯一 pending editor task。
    :returns: prompt_toolkit key bindings。
    :raises Exception: KeyBindings 构造失败时向上透传。
    """

    bindings = KeyBindings()
    active_phase = Condition(lambda: phase_provider() is not InteractiveComposerPhase.IDLE)

    @bindings.add("c-j")
    def _insert_newline(event: KeyPressEvent) -> None:
        """Ctrl+J 在当前 draft 中插入换行。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: buffer 写入失败时向上透传。
        """

        event.app.current_buffer.insert_text("\n")

    @bindings.add("c-m")
    def _submit_or_insert_xterm_shift_enter(event: KeyPressEvent) -> None:
        """只把 xterm exact Shift+Enter 序列解释为换行。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: buffer 写入或 application 退出失败时向上透传。
        """

        if _is_exact_xterm_shift_enter(event):
            event.app.current_buffer.insert_text("\n")
            return
        _exit_with_composer_event(
            event,
            kind=InteractiveComposerEventKind.SUBMIT,
            revision=revision_provider(),
        )

    @bindings.add("c-c")
    def _clear_or_interrupt(event: KeyPressEvent) -> None:
        """idle 有草稿时清空，否则把 Ctrl+C 交给唯一 SIGINT monitor。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: buffer reset 或 application 退出失败时向上透传。
        """

        buffer = event.app.current_buffer
        if phase_provider() is InteractiveComposerPhase.IDLE:
            if buffer.text != "":
                buffer.reset()
                return
        _raise_sigint()

    @bindings.add("c-d")
    def _delete_or_eof(event: KeyPressEvent) -> None:
        """按 phase 删除字符、报告 EOF 或忽略 active Ctrl+D。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: buffer 删除或 application 退出失败时向上透传。
        """

        if phase_provider() is not InteractiveComposerPhase.IDLE:
            return
        buffer = event.app.current_buffer
        if buffer.text == "":
            _exit_with_composer_event(
                event,
                kind=InteractiveComposerEventKind.EOF,
                revision=revision_provider(),
            )
            return
        buffer.delete(count=event.arg)

    @bindings.add("escape", filter=active_phase)
    def _cancel_active_with_escape(event: KeyPressEvent) -> None:
        """只在完整解析出 standalone Escape 后请求取消 active Run。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: application 退出失败时向上透传。
        """

        _exit_with_composer_event(
            event,
            kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION,
            revision=revision_provider(),
            running_key_action=RunningKeyAction.CANCEL_RUN,
        )

    @bindings.add("c-t", filter=active_phase)
    def _toggle_activity(event: KeyPressEvent) -> None:
        """active phase 的 Ctrl+T 请求切换 activity view。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: application 退出失败时向上透传。
        """

        _exit_with_composer_event(
            event,
            kind=InteractiveComposerEventKind.RUNNING_KEY_ACTION,
            revision=revision_provider(),
            running_key_action=RunningKeyAction.TOGGLE_ACTIVITY,
        )

    @bindings.add("c-r")
    def _start_history_search(event: KeyPressEvent) -> None:
        """Ctrl+R 进入当前 buffer 的历史搜索。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: history completion 启动失败时向上透传。
        """

        event.app.current_buffer.start_history_lines_completion()

    @bindings.add("c-x", "c-e")
    def _open_external_editor(event: KeyPressEvent) -> None:
        """Ctrl+X Ctrl+E 严格分流显式命令与系统 fallback。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises RuntimeError: 有效显式命令在无运行 event loop 时抛出。
        """

        if editor_tasks:
            return

        try:
            command = _resolve_explicit_editor_command(os.environ)
        except _EditorConfigurationError as error:
            _write_editor_diagnostic(
                _editor_configuration_error_message(error),
                stderr=stderr,
            )
            return

        buffer = event.app.current_buffer
        if command is None:
            try:
                task = buffer.open_in_editor(validate_and_handle=False)
            except Exception:
                _write_editor_diagnostic(
                    _SYSTEM_EDITOR_FAILURE_MESSAGE,
                    stderr=stderr,
                )
                return
            editor_tasks.add(task)
            task.add_done_callback(
                partial(
                    _consume_system_editor_task,
                    stderr=stderr,
                    editor_tasks=editor_tasks,
                )
            )
            return

        task = _open_explicit_editor(buffer, command)
        editor_tasks.add(task)
        task.add_done_callback(
            partial(
                _consume_explicit_editor_task,
                command=command,
                stderr=stderr,
                editor_tasks=editor_tasks,
            )
        )

    return bindings


def _resolve_explicit_editor_command(
    environ: Mapping[str, str],
) -> _ExplicitEditorCommand | None:
    """解析显式 editor 环境并验证唯一可执行目标。

    ``VISUAL`` 的 key 存在即拥有优先级，包括空白或非法值；只有两个 key
    都不存在时才返回 ``None``，交由 prompt_toolkit 的系统 fallback。

    :param environ: 当前进程环境快照。
    :returns: 已验证的显式命令；两个 editor key 均不存在时返回 ``None``。
    :raises _EditorConfigurationError: 命令为空、语法非法、目标不存在或不可执行。
    """

    source: _EditorEnvironmentVariable
    if _EditorEnvironmentVariable.VISUAL.value in environ:
        source = _EditorEnvironmentVariable.VISUAL
    elif _EditorEnvironmentVariable.EDITOR.value in environ:
        source = _EditorEnvironmentVariable.EDITOR
    else:
        return None

    raw_command = environ[source.value]
    if raw_command.strip() == "":
        raise _EditorConfigurationError(
            reason=_EditorConfigurationErrorReason.EMPTY_COMMAND,
            source=source,
        )
    try:
        argv = tuple(shlex.split(raw_command))
    except ValueError:
        raise _EditorConfigurationError(
            reason=_EditorConfigurationErrorReason.INVALID_SYNTAX,
            source=source,
        ) from None
    if not argv or argv[0] == "":
        raise _EditorConfigurationError(
            reason=_EditorConfigurationErrorReason.EMPTY_COMMAND,
            source=source,
        )

    executable = argv[0]
    try:
        resolved_executable = _resolve_editor_executable(executable)
    except OSError:
        resolved_executable = None
    if resolved_executable is None or not resolved_executable.exists():
        raise _EditorConfigurationError(
            reason=_EditorConfigurationErrorReason.EXECUTABLE_NOT_FOUND,
            source=source,
        )
    if not resolved_executable.is_file() or not os.access(resolved_executable, os.X_OK):
        raise _EditorConfigurationError(
            reason=_EditorConfigurationErrorReason.NOT_EXECUTABLE,
            source=source,
        )
    return _ExplicitEditorCommand(
        source=source,
        argv=argv,
        resolved_executable=resolved_executable,
    )


def _resolve_editor_executable(executable: str) -> Path | None:
    """按是否含路径分隔符解析 editor executable。

    :param executable: ``argv[0]`` 原始值。
    :returns: 规范化路径；PATH 中找不到无分隔符命令时返回 ``None``。
    :raises OSError: 路径规范化读取文件系统失败时抛出。
    """

    separators = (os.sep,) if os.altsep is None else (os.sep, os.altsep)
    if any(separator in executable for separator in separators):
        return Path(executable).expanduser().resolve()
    discovered = shutil.which(executable)
    if discovered is None:
        return None
    return Path(discovered).resolve()


def _open_explicit_editor(
    buffer: Buffer,
    command: _ExplicitEditorCommand,
) -> asyncio.Task[_EditorProcessOutcome]:
    """启动 CLI-owned 显式 editor round trip task。

    :param buffer: 当前 prompt_toolkit public buffer。
    :param command: 已验证的显式 editor 命令。
    :returns: 由 composer 强引用并消费异常的 editor task。
    :raises RuntimeError: 当前线程没有运行中的 event loop 时抛出。
    """

    original_document = buffer.document
    return asyncio.create_task(
        _run_explicit_editor_round_trip(
            buffer=buffer,
            command=command,
            original_document=original_document,
        )
    )


async def _run_explicit_editor_round_trip(
    *,
    buffer: Buffer,
    command: _ExplicitEditorCommand,
    original_document: Document,
) -> _EditorProcessOutcome:
    """执行 secure tempfile、单次进程与 zero-only 原子回填。

    :param buffer: 当前 prompt_toolkit public buffer。
    :param command: 已验证的显式 editor 命令。
    :param original_document: 同步按键处理路径冻结的原始 public document。
    :returns: 进程非零时为 ``CANCELLED``；成功读取并回填时为 ``UPDATED``。
    :raises _EditorActionError: tempfile、spawn、readback 或 cleanup 失败时抛出。
    :raises asyncio.CancelledError: composer teardown 取消 task 时抛出。
    """

    temporary_path: Path | None = None
    updated_text: str
    primary_failure = False
    try:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=_EXPLICIT_EDITOR_TEMPFILE_PREFIX,
                suffix=_EXPLICIT_EDITOR_TEMPFILE_SUFFIX,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(original_document.text)
        except OSError:
            raise _EditorActionError(
                reason=_EditorActionFailureReason.TEMPFILE_UNAVAILABLE,
                source=command.source,
            ) from None

        exact_argv = (
            str(command.resolved_executable),
            *command.argv[1:],
            str(temporary_path),
        )
        try:
            return_code = await run_in_terminal(
                partial(_run_editor_process, exact_argv),
                in_executor=True,
            )
        except OSError:
            raise _EditorActionError(
                reason=_EditorActionFailureReason.SPAWN_FAILED,
                source=command.source,
            ) from None
        if return_code != 0:
            return _EditorProcessOutcome.CANCELLED

        try:
            # 先按原始 bytes 解码，避免 text mode 隐式改写 CRLF；CLI 只拥有
            # “最多移除一个末尾 LF”这一条 frozen success 规则。
            updated_text = temporary_path.read_bytes().decode("utf-8")
        except (OSError, UnicodeError):
            raise _EditorActionError(
                reason=_EditorActionFailureReason.READBACK_FAILED,
                source=command.source,
            ) from None
        if updated_text.endswith("\n"):
            updated_text = updated_text[:-1]
    except BaseException:
        # round trip 的任何在途异常都是 primary；这里只记录控制流并原样重抛，
        # 让 finally 始终尝试 cleanup，但禁止 cleanup 改写失败或取消身份。
        primary_failure = True
        raise
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                if not primary_failure:
                    raise _EditorActionError(
                        reason=_EditorActionFailureReason.CLEANUP_FAILED,
                        source=command.source,
                    ) from None
    buffer.document = Document(
        text=updated_text,
        cursor_position=len(updated_text),
    )
    return _EditorProcessOutcome.UPDATED


def _run_editor_process(argv: tuple[str, ...]) -> int:
    """不用 shell，以 exact argv 同步运行显式 editor。

    :param argv: executable、显式参数与唯一 tempfile 路径。
    :returns: 子进程原始 return code。
    :raises OSError: 子进程无法 spawn 时抛出。
    """

    return subprocess.run(argv, check=False).returncode


def _consume_explicit_editor_task(
    task: asyncio.Task[_EditorProcessOutcome],
    *,
    command: _ExplicitEditorCommand,
    stderr: TextIO,
    editor_tasks: set[_EditorTask],
) -> None:
    """消费显式 editor task 结果并安全投影一次诊断。

    :param task: 已完成或取消的 editor task。
    :param command: task 对应的显式 editor 命令。
    :param stderr: 安全 diagnostic 输出流。
    :param editor_tasks: composer 持有 task 的强引用集合。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    editor_tasks.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except _EditorActionError as error:
        _write_editor_diagnostic(
            _editor_action_error_message(error),
            stderr=stderr,
        )
    except Exception:
        _write_editor_diagnostic(
            _unexpected_editor_error_message(command.source),
            stderr=stderr,
        )


def _consume_system_editor_task(
    task: asyncio.Task[None],
    *,
    stderr: TextIO,
    editor_tasks: set[_EditorTask],
) -> None:
    """消费系统 editor task，并释放 composer 的唯一 pending slot。

    :param task: public ``Buffer.open_in_editor`` 返回的 task。
    :param stderr: 安全 diagnostic 输出流。
    :param editor_tasks: composer 持有的唯一 editor pending task 集合。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    editor_tasks.discard(task)
    if task.cancelled():
        return
    try:
        task.result()
    except Exception:
        _write_editor_diagnostic(
            _SYSTEM_EDITOR_FAILURE_MESSAGE,
            stderr=stderr,
        )


async def _cancel_editor_tasks(
    editor_tasks: set[_EditorTask],
) -> None:
    """在 composer application teardown 取消并消费 editor tasks。

    :param editor_tasks: 当前 composer 仍强引用的唯一 pending editor task。
    :returns: ``None``。
    :raises asyncio.CancelledError: 当前 teardown task 自身被再次取消时抛出。
    """

    pending_tasks = tuple(editor_tasks)
    for task in pending_tasks:
        task.cancel()
    for task in pending_tasks:
        try:
            await task
        except asyncio.CancelledError:
            continue
        except Exception:
            # done callback 是唯一 LLM/user-facing diagnostic owner；此处只保证
            # teardown 已观察异常，不在第二处重复投影。
            continue
    editor_tasks.clear()


def _editor_configuration_error_message(error: _EditorConfigurationError) -> str:
    """把封闭配置错误投影为稳定且可执行的用户提示。

    :param error: 显式 editor 配置错误。
    :returns: 不含命令正文、路径或环境内容的中文提示。
    :raises Exception: 不主动抛出异常。
    """

    description_by_reason: dict[_EditorConfigurationErrorReason, str] = {
        _EditorConfigurationErrorReason.EMPTY_COMMAND: "编辑器命令为空",
        _EditorConfigurationErrorReason.INVALID_SYNTAX: "编辑器命令语法无效",
        _EditorConfigurationErrorReason.EXECUTABLE_NOT_FOUND: "编辑器不存在",
        _EditorConfigurationErrorReason.NOT_EXECUTABLE: "编辑器不可执行",
    }
    description = description_by_reason[error.reason]
    return (
        f"{error.display_name} 指定的{description}；"
        f"{_EDITOR_RECOVERY_ACTION.format(source=error.display_name)}"
    )


def _editor_action_error_message(error: _EditorActionError) -> str:
    """把 editor round trip 错误投影为稳定且可执行的用户提示。

    :param error: 显式 editor action 错误。
    :returns: 不含异常正文、argv 或 tempfile 路径的中文提示。
    :raises Exception: 不主动抛出异常。
    """

    description_by_reason: dict[_EditorActionFailureReason, str] = {
        _EditorActionFailureReason.TEMPFILE_UNAVAILABLE: "无法准备编辑文件，草稿已保留",
        _EditorActionFailureReason.SPAWN_FAILED: "指定编辑器无法启动，草稿已保留",
        _EditorActionFailureReason.READBACK_FAILED: "无法读取编辑结果，草稿已保留",
        _EditorActionFailureReason.CLEANUP_FAILED: "无法清理编辑文件，草稿已保留",
    }
    source = error.source.value
    return (
        f"{source} {description_by_reason[error.reason]}；"
        f"{_EDITOR_RECOVERY_ACTION.format(source=source)}"
    )


def _unexpected_editor_error_message(source: _EditorEnvironmentVariable) -> str:
    """生成未知显式 editor 失败的脱敏提示。

    :param source: 显式命令所属环境变量。
    :returns: 不含底层异常内容的稳定提示。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"{source.value} 指定的编辑器操作失败，草稿已保留；"
        f"{_EDITOR_RECOVERY_ACTION.format(source=source.value)}"
    )


def _write_editor_diagnostic(message: str, *, stderr: TextIO) -> None:
    """写入 editor diagnostic，避免输出通道错误形成 callback traceback。

    :param message: 已脱敏的稳定提示。
    :param stderr: diagnostic 输出流。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    try:
        print(message, file=stderr)
    except Exception:
        # diagnostic sink 已不可用时无法再给出用户提示；吞掉 sink 错误可避免
        # prompt_toolkit background callback 产生第二个 traceback。
        return


def _raise_sigint() -> None:
    """把 prompt_toolkit 读取到的 Ctrl+C 重新交给进程 SIGINT owner。

    :returns: ``None``。
    :raises KeyboardInterrupt: invocation 尚未安装 SIGINT monitor 时由 Python
        默认 handler 抛出。
    """

    signal.raise_signal(signal.SIGINT)


def _exit_with_composer_event(
    event: KeyPressEvent,
    *,
    kind: InteractiveComposerEventKind,
    revision: int,
    running_key_action: RunningKeyAction | None = None,
) -> None:
    """保存 exact buffer/cursor 并退出当前 prompt_toolkit application。

    :param event: prompt_toolkit 按键事件。
    :param kind: 待投影的 composer event kind。
    :param revision: 当前用户编辑版本。
    :param running_key_action: active phase 的唯一 typed key action。
    :returns: ``None``。
    :raises Exception: application 无法退出时向上透传。
    """

    buffer = event.app.current_buffer
    draft = buffer.text if kind is InteractiveComposerEventKind.SUBMIT else None
    event.app.exit(
        exception=_ComposerEventSignal(
            event=InteractiveComposerEvent(
                kind=kind,
                draft=draft,
                input_revision=revision,
                running_key_action=running_key_action,
            ),
            document=buffer.document,
        )
    )


def _is_exact_xterm_shift_enter(event: KeyPressEvent) -> bool:
    """判断当前 Control-M 是否来自 exact xterm Shift+Enter 序列。

    :param event: prompt_toolkit 按键事件。
    :returns: 仅 exact 单个原始序列匹配时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        len(event.key_sequence) == 1
        and event.key_sequence[0].key is Keys.ControlM
        and event.key_sequence[0].data == XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER
    )


def _idle_phase() -> InteractiveComposerPhase:
    """返回默认 key-binding 测试使用的 idle phase。

    :returns: ``InteractiveComposerPhase.IDLE``。
    :raises Exception: 不主动抛出异常。
    """

    return InteractiveComposerPhase.IDLE


def _zero_revision() -> int:
    """返回默认 key-binding 测试使用的零编辑版本。

    :returns: ``0``。
    :raises Exception: 不主动抛出异常。
    """

    return 0


def new_interactive_composer(
    *,
    stderr: TextIO | None = None,
) -> InteractiveComposer:
    """创建唯一 prompt_toolkit interactive TTY composer。

    :param stderr: diagnostic 输出流；``None`` 表示当前 ``sys.stderr``。
    :returns: prompt_toolkit interactive composer。
    :raises Exception: prompt_toolkit 初始化失败时向上抛出。
    """

    return PromptToolkitInteractiveComposer(stderr=stderr)


__all__: tuple[str, ...] = (
    "InteractiveComposer",
    "InteractiveComposerEvent",
    "InteractiveComposerEventKind",
    "InteractiveComposerPhase",
    "PromptToolkitInteractiveComposer",
    "XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER",
    "build_interactive_key_bindings",
    "new_interactive_composer",
)
