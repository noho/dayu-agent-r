"""interactive composer 测试。"""

from __future__ import annotations

from io import StringIO
from typing import cast

from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.key_binding.key_bindings import KeyBindings, KeyHandlerCallable
from prompt_toolkit.keys import Keys

from dayu.cli.composer import (
    InputReaderComposer,
    build_interactive_key_bindings,
    new_interactive_composer,
)


class _FakeBuffer:
    """测试用 prompt_toolkit buffer 替身。"""

    text: str
    inserted_text: list[str]
    reset_count: int
    history_search_count: int
    editor_open_count: int
    editor_error: RuntimeError | None

    def __init__(self, *, text: str = "", editor_error: RuntimeError | None = None) -> None:
        """初始化 fake buffer。

        :param text: 当前 buffer 文本。
        :param editor_error: open editor 时抛出的测试异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.text = text
        self.inserted_text = []
        self.reset_count = 0
        self.history_search_count = 0
        self.editor_open_count = 0
        self.editor_error = editor_error

    def insert_text(self, text: str) -> None:
        """记录插入文本。

        :param text: 插入文本。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.inserted_text.append(text)

    def reset(self) -> None:
        """记录 reset 调用。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.reset_count += 1

    def start_history_lines_completion(self) -> None:
        """记录历史搜索启动。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.history_search_count += 1

    def open_in_editor(self, *, validate_and_handle: bool) -> None:
        """记录外部编辑器调用。

        :param validate_and_handle: prompt_toolkit open editor 参数。
        :returns: ``None``。
        :raises RuntimeError: 配置了 editor_error 时抛出。
        """

        if validate_and_handle:
            raise AssertionError("validate_and_handle must be False")
        self.editor_open_count += 1
        if self.editor_error is not None:
            raise self.editor_error


class _FakeApp:
    """测试用 prompt_toolkit app 替身。"""

    current_buffer: _FakeBuffer
    exit_exception: type[BaseException] | None

    def __init__(self, buffer: _FakeBuffer) -> None:
        """初始化 fake app。

        :param buffer: fake buffer。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.current_buffer = buffer
        self.exit_exception = None

    def exit(self, *, exception: type[BaseException]) -> None:
        """记录 app exit 异常类型。

        :param exception: prompt_toolkit exit 异常类型。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.exit_exception = exception


class _FakeKeyEvent:
    """测试用 key event 替身。"""

    app: _FakeApp

    def __init__(self, app: _FakeApp) -> None:
        """初始化 fake key event。

        :param app: fake app。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.app = app


def test_new_interactive_composer_uses_input_reader_for_non_tty() -> None:
    """非 TTY 输入应保留 input reader adapter。"""

    composer = new_interactive_composer(
        input_reader=lambda _prompt: "用户输入",
        stdin=StringIO(),
    )

    assert isinstance(composer, InputReaderComposer)
    assert composer.read("dayu> ") == "用户输入"


def test_interactive_key_bindings_cover_multiline_history_and_editor() -> None:
    """composer key bindings 应覆盖 Ctrl+J、Ctrl+R、Ctrl+X Ctrl+E。"""

    key_sets = {binding.keys for binding in build_interactive_key_bindings().bindings}

    assert (Keys.ControlJ,) in key_sets
    assert (Keys.ControlR,) in key_sets
    assert (Keys.ControlX, Keys.ControlE) in key_sets


def test_ctrl_j_inserts_newline_and_ctrl_r_starts_history_search() -> None:
    """Ctrl+J 应插入换行，Ctrl+R 应启动历史搜索。"""

    bindings = build_interactive_key_bindings()
    buffer = _FakeBuffer(text="draft")
    event = cast(KeyPressEvent, _FakeKeyEvent(_FakeApp(buffer)))

    _handler_for(bindings, (Keys.ControlJ,))(event)
    _handler_for(bindings, (Keys.ControlR,))(event)

    assert buffer.inserted_text == ["\n"]
    assert buffer.history_search_count == 1


def test_ctrl_c_clears_non_empty_draft_and_empty_draft_exits() -> None:
    """Ctrl+C 在非空 draft 清空，在空 draft 请求 KeyboardInterrupt。"""

    bindings = build_interactive_key_bindings()
    non_empty_buffer = _FakeBuffer(text="draft")
    non_empty_app = _FakeApp(non_empty_buffer)
    empty_buffer = _FakeBuffer(text="")
    empty_app = _FakeApp(empty_buffer)

    _handler_for(bindings, (Keys.ControlC,))(cast(KeyPressEvent, _FakeKeyEvent(non_empty_app)))
    _handler_for(bindings, (Keys.ControlC,))(cast(KeyPressEvent, _FakeKeyEvent(empty_app)))

    assert non_empty_buffer.reset_count == 1
    assert non_empty_app.exit_exception is None
    assert empty_buffer.reset_count == 0
    assert empty_app.exit_exception is KeyboardInterrupt


def test_ctrl_x_ctrl_e_opens_editor_and_reports_startup_failure() -> None:
    """Ctrl+X Ctrl+E 应调用外部编辑器，启动失败时写入 stderr 诊断。"""

    stderr = StringIO()
    bindings = build_interactive_key_bindings(stderr=stderr)
    success_buffer = _FakeBuffer(text="draft")
    failed_buffer = _FakeBuffer(
        text="draft",
        editor_error=RuntimeError("editor unavailable"),
    )

    _handler_for(bindings, (Keys.ControlX, Keys.ControlE))(cast(KeyPressEvent, _FakeKeyEvent(_FakeApp(success_buffer))))
    _handler_for(bindings, (Keys.ControlX, Keys.ControlE))(cast(KeyPressEvent, _FakeKeyEvent(_FakeApp(failed_buffer))))

    assert success_buffer.editor_open_count == 1
    assert failed_buffer.editor_open_count == 1
    assert "Editor failed: RuntimeError: editor unavailable" in stderr.getvalue()


def _handler_for(bindings: KeyBindings, keys: tuple[Keys, ...]) -> KeyHandlerCallable:
    """按 key sequence 取得绑定 handler。

    :param bindings: key bindings。
    :param keys: key sequence。
    :returns: 对应 handler。
    :raises AssertionError: 未找到 handler 时抛出。
    """

    for binding in bindings.bindings:
        if binding.keys == keys:
            return binding.handler
    raise AssertionError(f"missing binding for {keys}")
