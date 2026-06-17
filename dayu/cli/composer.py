"""interactive 输入态 composer。

本模块把 prompt_toolkit 封装在 CLI 层，向 command 模块只暴露窄协议。
Service / Host / Engine 不依赖 prompt_toolkit 类型。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Final, Protocol, TextIO

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent

_EDITOR_FAILURE_PREFIX: Final[str] = "Editor failed"


class InteractiveComposer(Protocol):
    """interactive 输入态 composer 窄协议。"""

    def read(self, prompt: str) -> str:
        """读取一次用户输入。

        :param prompt: 输入提示文本。
        :returns: 用户输入文本。
        :raises EOFError: 用户请求 EOF 时抛出。
        :raises KeyboardInterrupt: 用户在空 draft 中请求中断时抛出。
        """

        ...


class InputReaderComposer:
    """把旧式 input reader 包装成 composer。"""

    _input_reader: Callable[[str], str]

    def __init__(self, input_reader: Callable[[str], str]) -> None:
        """初始化 input reader adapter。

        :param input_reader: 旧式输入读取函数。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._input_reader = input_reader

    def read(self, prompt: str) -> str:
        """读取一次用户输入。

        :param prompt: 输入提示文本。
        :returns: 用户输入文本。
        :raises EOFError: input reader 抛出 EOF 时透传。
        :raises KeyboardInterrupt: input reader 抛出中断时透传。
        """

        return self._input_reader(prompt)


class PromptToolkitInteractiveComposer:
    """基于 prompt_toolkit 的 interactive composer。"""

    _session: PromptSession[str]

    def __init__(self, *, stderr: TextIO | None = None) -> None:
        """初始化 prompt_toolkit composer。

        :param stderr: diagnostic 输出流；``None`` 表示当前 ``sys.stderr``。
        :returns: ``None``。
        :raises Exception: prompt_toolkit 初始化失败时向上抛出。
        """

        self._session = PromptSession(
            history=InMemoryHistory(),
            key_bindings=build_interactive_key_bindings(stderr=sys.stderr if stderr is None else stderr),
            enable_history_search=True,
            enable_open_in_editor=True,
        )

    def read(self, prompt: str) -> str:
        """读取一次 interactive 用户输入。

        :param prompt: 输入提示文本。
        :returns: 用户输入文本。
        :raises EOFError: 用户请求 EOF 时抛出。
        :raises KeyboardInterrupt: 用户在空 draft 中请求中断时抛出。
        """

        return self._session.prompt(prompt, multiline=False, handle_sigint=False)


def build_interactive_key_bindings(*, stderr: TextIO | None = None) -> KeyBindings:
    """构造 interactive composer key bindings。

    :param stderr: 外部编辑器失败诊断输出流；``None`` 表示当前 ``sys.stderr``。
    :returns: prompt_toolkit key bindings。
    :raises Exception: 不主动抛出异常。
    """

    effective_stderr = sys.stderr if stderr is None else stderr
    bindings = KeyBindings()

    @bindings.add("c-j")
    def _insert_newline(event: KeyPressEvent) -> None:
        """Ctrl+J 在当前 draft 中插入换行。"""

        event.app.current_buffer.insert_text("\n")

    @bindings.add("c-c")
    def _clear_or_interrupt(event: KeyPressEvent) -> None:
        """Ctrl+C 在非空 draft 中清空，空 draft 中退出输入态。"""

        buffer = event.app.current_buffer
        if buffer.text.strip() != "":
            buffer.reset()
            return
        event.app.exit(exception=KeyboardInterrupt)

    @bindings.add("c-r")
    def _start_history_search(event: KeyPressEvent) -> None:
        """Ctrl+R 进入当前 buffer 的历史搜索。"""

        event.app.current_buffer.start_history_lines_completion()

    @bindings.add("c-x", "c-e")
    def _open_external_editor(event: KeyPressEvent) -> None:
        """Ctrl+X Ctrl+E 使用 prompt_toolkit 外部编辑器编辑当前 draft。"""

        try:
            event.app.current_buffer.open_in_editor(validate_and_handle=False)
        except Exception as exc:
            print(f"{_EDITOR_FAILURE_PREFIX}: {type(exc).__name__}: {exc}", file=effective_stderr)

    return bindings


def new_interactive_composer(
    *,
    input_reader: Callable[[str], str],
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
) -> InteractiveComposer:
    """按输入流能力创建 interactive composer。

    :param input_reader: 非 TTY 或测试路径使用的旧式输入读取函数。
    :param stdin: 输入流；``None`` 表示当前 ``sys.stdin``。
    :param stderr: diagnostic 输出流；``None`` 表示当前 ``sys.stderr``。
    :returns: interactive composer。
    :raises Exception: prompt_toolkit 初始化失败时向上抛出。
    """

    effective_stdin = sys.stdin if stdin is None else stdin
    if not effective_stdin.isatty():
        return InputReaderComposer(input_reader)
    return PromptToolkitInteractiveComposer(stderr=stderr)


__all__: tuple[str, ...] = (
    "InputReaderComposer",
    "InteractiveComposer",
    "PromptToolkitInteractiveComposer",
    "build_interactive_key_bindings",
    "new_interactive_composer",
)
