"""interactive TTY 输入态 composer。

本模块是 interactive 终端输入、草稿、光标和历史记录的唯一 owner。它把
``prompt_toolkit`` 的按键与 buffer 语义投影为严格类型事件，CLI REPL 不接触
``prompt_toolkit`` 类型，Service / Host / Engine 也不依赖终端解析实现。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol, TextIO

from prompt_toolkit import PromptSession
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import Output

XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER: Final[str] = "\x1b[27;2;13~"
"""xterm modifyOtherKeys 协议中 Shift+Enter 的完整字节序列。"""

_EDITOR_FAILURE_MESSAGE: Final[str] = "Interactive editor failed"


class InteractiveComposerPhase(StrEnum):
    """interactive composer 当前输入阶段。"""

    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"


class InteractiveComposerEventKind(StrEnum):
    """interactive composer 对 REPL 暴露的封闭事件种类。"""

    SUBMIT = "submit"
    CANCEL_ACTIVE = "cancel_active"
    TOGGLE_ACTIVITY = "toggle_activity"
    IDLE_INTERRUPT = "idle_interrupt"
    EOF = "eof"


class InteractiveCancelSource(StrEnum):
    """composer cancel event 的本地输入来源。"""

    ESCAPE = "escape"
    CTRL_C = "ctrl_c"


@dataclass(frozen=True, slots=True)
class InteractiveComposerEvent:
    """interactive composer 产生的一次类型化事件。

    :param kind: 事件种类。
    :param draft: ``SUBMIT`` 的原始草稿；其它事件必须为 ``None``。
    :param input_revision: composer 已观察到的用户编辑版本，用于判定两次
        idle Ctrl+C 之间是否发生过正常编辑。
    :param cancel_source: ``CANCEL_ACTIVE`` 的输入来源；其它事件必须为
        ``None``。
    """

    kind: InteractiveComposerEventKind
    draft: str | None = None
    input_revision: int = 0
    cancel_source: InteractiveCancelSource | None = None

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
            if self.cancel_source is not None:
                raise ValueError("submit event must not carry cancel source")
            return
        if self.draft is not None:
            raise ValueError("non-submit event must not carry draft")
        if self.kind is InteractiveComposerEventKind.CANCEL_ACTIVE:
            if self.cancel_source is None:
                raise ValueError("cancel event requires cancel source")
            return
        if self.cancel_source is not None:
            raise ValueError("non-cancel event must not carry cancel source")


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
        self._session = PromptSession(
            history=self._history,
            key_bindings=build_interactive_key_bindings(
                stderr=sys.stderr if stderr is None else stderr,
                phase_provider=self._current_phase,
                revision_provider=self._current_input_revision,
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

    effective_stderr = sys.stderr if stderr is None else stderr
    effective_phase_provider = _idle_phase if phase_provider is None else phase_provider
    effective_revision_provider = _zero_revision if revision_provider is None else revision_provider
    bindings = KeyBindings()
    active_phase = Condition(lambda: effective_phase_provider() is not InteractiveComposerPhase.IDLE)

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
            revision=effective_revision_provider(),
        )

    @bindings.add("c-c")
    def _clear_or_interrupt(event: KeyPressEvent) -> None:
        """按 phase 清空 idle draft 或投影 Ctrl+C typed event。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: buffer reset 或 application 退出失败时向上透传。
        """

        buffer = event.app.current_buffer
        if effective_phase_provider() is InteractiveComposerPhase.IDLE:
            if buffer.text != "":
                buffer.reset()
                return
            _exit_with_composer_event(
                event,
                kind=InteractiveComposerEventKind.IDLE_INTERRUPT,
                revision=effective_revision_provider(),
            )
            return
        _exit_with_composer_event(
            event,
            kind=InteractiveComposerEventKind.CANCEL_ACTIVE,
            revision=effective_revision_provider(),
            cancel_source=InteractiveCancelSource.CTRL_C,
        )

    @bindings.add("c-d")
    def _delete_or_eof(event: KeyPressEvent) -> None:
        """按 phase 删除字符、报告 EOF 或忽略 active Ctrl+D。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises Exception: buffer 删除或 application 退出失败时向上透传。
        """

        if effective_phase_provider() is not InteractiveComposerPhase.IDLE:
            return
        buffer = event.app.current_buffer
        if buffer.text == "":
            _exit_with_composer_event(
                event,
                kind=InteractiveComposerEventKind.EOF,
                revision=effective_revision_provider(),
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
            kind=InteractiveComposerEventKind.CANCEL_ACTIVE,
            revision=effective_revision_provider(),
            cancel_source=InteractiveCancelSource.ESCAPE,
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
            kind=InteractiveComposerEventKind.TOGGLE_ACTIVITY,
            revision=effective_revision_provider(),
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
        """Ctrl+X Ctrl+E 使用外部编辑器并稳定投影失败诊断。

        :param event: prompt_toolkit 当前按键事件。
        :returns: ``None``。
        :raises OSError: 稳定诊断无法写入 stderr 时抛出。
        """

        try:
            event.app.current_buffer.open_in_editor(validate_and_handle=False)
        except Exception:
            print(_EDITOR_FAILURE_MESSAGE, file=effective_stderr)

    return bindings


def _exit_with_composer_event(
    event: KeyPressEvent,
    *,
    kind: InteractiveComposerEventKind,
    revision: int,
    cancel_source: InteractiveCancelSource | None = None,
) -> None:
    """保存 exact buffer/cursor 并退出当前 prompt_toolkit application。

    :param event: prompt_toolkit 按键事件。
    :param kind: 待投影的 composer event kind。
    :param revision: 当前用户编辑版本。
    :param cancel_source: cancel event 的本地输入来源。
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
                cancel_source=cancel_source,
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
    "InteractiveCancelSource",
    "InteractiveComposerEvent",
    "InteractiveComposerEventKind",
    "InteractiveComposerPhase",
    "PromptToolkitInteractiveComposer",
    "XTERM_MODIFY_OTHER_KEYS_SHIFT_ENTER",
    "build_interactive_key_bindings",
    "new_interactive_composer",
)
