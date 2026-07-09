"""interactive 运行态 transcript/activity view。

本模块是 CLI UI adapter 的运行态边界，只消费 Service entrypoint DTO 并
维护本地 transcript/activity buffer。它不读取 Host durable internals，也
不参与 logging handler 装配。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from typing import Final, Protocol, TextIO

from dayu.cli.activity import format_cli_activity_line
from dayu.cli.output import render_interactive_terminal_result
from dayu.cli.runtime_display import (
    clear_completed_rows,
    resolve_terminal_columns,
    terminal_row_count,
)
from dayu.service.entrypoint_runtime import EntrypointActivity, EntrypointRunTerminalResult

_TRANSCRIPT_HEADER: Final[str] = "Interactive transcript"
_ACTIVITY_HEADER: Final[str] = "Interactive activity"
_EMPTY_VIEW_MESSAGE: Final[str] = "(empty)"
_CANCEL_REQUESTED_MESSAGE: Final[str] = "Interactive: cancel requested"
_LOCAL_EXIT_AFTER_CANCEL_MESSAGE: Final[str] = "Interactive: cancelling; local process exiting"


class InteractiveRunViewMode(StrEnum):
    """interactive 运行态 view mode。"""

    TRANSCRIPT = "transcript"
    ACTIVITY = "activity"


class ActivitySink(Protocol):
    """interactive 运行态 activity sink 窄协议。"""

    def record_activity(self, activity: EntrypointActivity) -> None:
        """记录一条运行态 activity。

        :param activity: Service activity DTO。
        :returns: ``None``。
        :raises OSError: 实现写 UI 输出失败时可透传。
        """


class InteractiveRunView(Protocol):
    """interactive 运行态 view 窄协议。"""

    def activity_sink(self) -> ActivitySink:
        """返回 activity sink。

        :returns: 当前 view 使用的 activity sink。
        :raises Exception: 不主动抛出异常。
        """
        ...

    def render_terminal_result(self, result: EntrypointRunTerminalResult) -> int:
        """渲染单轮 terminal result。

        :param result: Service helper 返回的 Host terminal result。
        :returns: CLI exit code 语义。
        :raises OSError: 输出流写入失败时由实现透传。
        """
        ...

    def finish_runtime_display(self) -> None:
        """结束当前运行态展示，为 terminal result 输出让出干净位置。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """
        ...

    def set_runtime_line_guard(self, guard: Callable[[], None] | None) -> None:
        """设置运行态输出前需要执行的行收尾回调。

        :param guard: 输出运行态行前执行的回调；``None`` 表示不执行。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """
        ...

    def toggle_view(self) -> None:
        """切换 transcript/activity view。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """

    def render_cancel_requested(self) -> None:
        """渲染用户已请求取消的运行态提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """

    def render_local_exit_after_cancel(self) -> None:
        """渲染二次中断导致本地退出的提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """

    def close(self) -> None:
        """关闭 view。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """


@dataclass(frozen=True, slots=True)
class InteractiveRunViewOptions:
    """interactive run view 配置。

    :param enabled: 是否启用 view 切换与 activity 展示。
    :param initial_mode: 初始展示模式。
    :param terminal_control: 是否允许输出 ANSI 清理控制符；``None`` 表示按
        stderr 是否 TTY 自动判断。
    :param terminal_columns: 运行态清理使用的终端列数；``None`` 表示读取当前
        终端或使用默认 fallback。
    """

    enabled: bool
    initial_mode: InteractiveRunViewMode = InteractiveRunViewMode.TRANSCRIPT
    terminal_control: bool | None = None
    terminal_columns: int | None = None


@dataclass(frozen=True, slots=True)
class _InteractiveRunViewActivitySink:
    """把 Service activity 转发给 run view 的 sink。"""

    view: TerminalInteractiveRunView

    def record_activity(self, activity: EntrypointActivity) -> None:
        """记录一条运行态 activity。

        :param activity: Service activity DTO。
        :returns: ``None``。
        :raises OSError: 输出流写入失败时由 view 透传。
        """

        self.view.record_activity(activity)


class TerminalInteractiveRunView:
    """非 full-screen 的 interactive transcript/activity run view。

    默认处于 transcript view，也可由 CLI display option 初始打开 activity
    view。activity 到达时总是进入 activity buffer；只有在 activity view
    已打开时才实时写 UI stderr。terminal result 始终进入 transcript
    buffer，并写入 stdout/stderr 用户通道。
    """

    _stdout: TextIO
    _stderr: TextIO
    _enabled: bool
    _closed: bool
    _supports_terminal_control: bool
    _terminal_columns: int
    _default_mode: InteractiveRunViewMode
    _mode: InteractiveRunViewMode
    _activity_sink: ActivitySink
    _transcript_lines: list[str]
    _activity_lines: list[str]
    _rendered_activity_row_count: int
    _runtime_line_guard: Callable[[], None] | None
    _seen_activity_dedupe_keys: set[str]
    _last_activity_event_sequence: int | None

    def __init__(
        self,
        *,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        options: InteractiveRunViewOptions | None = None,
    ) -> None:
        """初始化 run view。

        :param stdout: transcript 用户结果输出流；``None`` 表示当前 ``sys.stdout``。
        :param stderr: UI / 错误输出流；``None`` 表示当前 ``sys.stderr``。
        :param options: view 配置；``None`` 时按 stderr 是否 TTY 启用 view。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._stdout = sys.stdout if stdout is None else stdout
        self._stderr = sys.stderr if stderr is None else stderr
        self._enabled = self._stderr.isatty() if options is None else options.enabled
        self._closed = False
        terminal_control = None if options is None else options.terminal_control
        self._supports_terminal_control = (
            self._stderr.isatty() if terminal_control is None else terminal_control
        )
        terminal_columns = None if options is None else options.terminal_columns
        self._terminal_columns = resolve_terminal_columns(terminal_columns)
        initial_mode = (
            InteractiveRunViewMode.TRANSCRIPT if options is None else options.initial_mode
        )
        self._default_mode = (
            initial_mode if self._enabled else InteractiveRunViewMode.TRANSCRIPT
        )
        self._mode = self._default_mode
        self._activity_sink = _InteractiveRunViewActivitySink(view=self)
        self._transcript_lines = []
        self._activity_lines = []
        self._rendered_activity_row_count = 0
        self._runtime_line_guard = None
        self._seen_activity_dedupe_keys = set()
        self._last_activity_event_sequence = None

    @property
    def mode(self) -> InteractiveRunViewMode:
        """返回当前 view mode。

        :returns: 当前 view mode。
        :raises Exception: 不主动抛出异常。
        """

        return self._mode

    @property
    def transcript_lines(self) -> tuple[str, ...]:
        """返回 transcript buffer 快照。

        :returns: transcript 行快照。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._transcript_lines)

    @property
    def activity_lines(self) -> tuple[str, ...]:
        """返回 activity buffer 快照。

        :returns: activity 行快照。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._activity_lines)

    def activity_sink(self) -> ActivitySink:
        """返回 activity sink。

        :returns: 当前 view 使用的 activity sink。
        :raises Exception: 不主动抛出异常。
        """

        return self._activity_sink

    def set_runtime_line_guard(self, guard: Callable[[], None] | None) -> None:
        """设置运行态输出前需要执行的行收尾回调。

        :param guard: 输出运行态行前执行的回调；``None`` 表示不执行。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._runtime_line_guard = guard

    def record_activity(self, activity: EntrypointActivity) -> None:
        """记录并按当前 view mode 渲染 activity。

        :param activity: Service activity DTO。
        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed:
            return
        if activity.dedupe_key in self._seen_activity_dedupe_keys:
            return
        if (
            activity.event_sequence is not None
            and self._last_activity_event_sequence is not None
            and activity.event_sequence < self._last_activity_event_sequence
        ):
            return
        self._seen_activity_dedupe_keys.add(activity.dedupe_key)
        if activity.event_sequence is not None:
            self._last_activity_event_sequence = activity.event_sequence
        line = format_cli_activity_line(activity)
        self._activity_lines.append(line)
        if self._enabled and self._mode is InteractiveRunViewMode.ACTIVITY:
            self._render_runtime_line(line)

    def render_terminal_result(self, result: EntrypointRunTerminalResult) -> int:
        """渲染单轮 terminal result。

        :param result: Service helper 返回的 Host terminal result。
        :returns: CLI exit code 语义。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed:
            return render_interactive_terminal_result(
                result,
                stdout=self._stdout,
                stderr=self._stderr,
            )
        self.finish_runtime_display()
        stdout_buffer = StringIO()
        stderr_buffer = StringIO()
        exit_code = render_interactive_terminal_result(
            result,
            stdout=stdout_buffer,
            stderr=stderr_buffer,
        )
        stdout_lines = _split_buffer_lines(stdout_buffer.getvalue())
        stderr_lines = _split_buffer_lines(stderr_buffer.getvalue())
        self._transcript_lines.extend(stdout_lines)
        self._transcript_lines.extend(stderr_lines)
        _write_lines(stdout_lines, self._stdout)
        _write_lines(stderr_lines, self._stderr)
        self._mode = self._default_mode
        return exit_code

    def toggle_view(self) -> None:
        """切换 transcript/activity view 并渲染当前 buffer 快照。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        if self._mode is InteractiveRunViewMode.TRANSCRIPT:
            self._mode = InteractiveRunViewMode.ACTIVITY
            rendered_count = _render_view_snapshot(
                header=_ACTIVITY_HEADER,
                lines=self._activity_lines,
                stderr=self._stderr,
                line_guard=self._runtime_line_guard,
                terminal_columns=self._terminal_columns,
            )
            self._rendered_activity_row_count += rendered_count
            return
        self._mode = InteractiveRunViewMode.TRANSCRIPT
        rendered_count = _render_view_snapshot(
            header=_TRANSCRIPT_HEADER,
            lines=self._transcript_lines,
            stderr=self._stderr,
            line_guard=self._runtime_line_guard,
            terminal_columns=self._terminal_columns,
        )
        self._rendered_activity_row_count += rendered_count

    def render_cancel_requested(self) -> None:
        """渲染用户已请求取消的运行态提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        self._render_runtime_line(_CANCEL_REQUESTED_MESSAGE)

    def render_local_exit_after_cancel(self) -> None:
        """渲染二次中断导致本地退出的提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        self._render_runtime_line(_LOCAL_EXIT_AFTER_CANCEL_MESSAGE)

    def _render_runtime_line(self, line: str) -> None:
        """输出一条 interactive 运行态行并记录其屏幕行数。

        :param line: 已格式化的单行展示文本。
        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._runtime_line_guard is not None:
            self._runtime_line_guard()
        print(line, file=self._stderr)
        self._rendered_activity_row_count += terminal_row_count(
            line,
            columns=self._terminal_columns,
        )

    def finish_runtime_display(self) -> None:
        """结束当前运行态展示，为 terminal result 输出让出干净位置。

        TTY 下清除当前 turn 的 activity/view 快照行；非 TTY 或测试捕获流下
        保留可读输出，不写 ANSI 控制符。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层输出流透传。
        """

        if (
            self._closed
            or not self._enabled
            or not self._supports_terminal_control
            or self._rendered_activity_row_count == 0
        ):
            return
        clear_completed_rows(self._stderr, row_count=self._rendered_activity_row_count)
        self._rendered_activity_row_count = 0

    def close(self) -> None:
        """关闭 view，后续 activity 不再写入 buffer。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._closed = True


def new_interactive_run_view(
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    show_activity: bool = False,
) -> InteractiveRunView:
    """按当前 stderr TTY 能力创建 interactive run view。

    :param stdout: transcript 用户结果输出流；``None`` 表示当前 ``sys.stdout``。
    :param stderr: UI / 错误输出流；``None`` 表示当前 ``sys.stderr``。
    :param show_activity: 初始是否展示运行态 activity。
    :returns: interactive run view。
    :raises Exception: 不主动抛出异常。
    """

    options = (
        InteractiveRunViewOptions(enabled=True, initial_mode=InteractiveRunViewMode.ACTIVITY)
        if show_activity
        else None
    )
    return TerminalInteractiveRunView(stdout=stdout, stderr=stderr, options=options)


def _split_buffer_lines(value: str) -> list[str]:
    """把捕获输出拆为行。

    :param value: 捕获到的输出文本。
    :returns: 输出行列表。
    :raises Exception: 不主动抛出异常。
    """

    if value == "":
        return []
    return value.rstrip("\n").splitlines()


def _write_lines(lines: Sequence[str], stream: TextIO) -> None:
    """把行列表写入指定流。

    :param lines: 待写入的行。
    :param stream: 输出流。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    for line in lines:
        print(line, file=stream)


def _render_view_snapshot(
    *,
    header: str,
    lines: Sequence[str],
    stderr: TextIO,
    line_guard: Callable[[], None] | None,
    terminal_columns: int,
) -> int:
    """渲染当前 view buffer 快照。

    :param header: 快照标题。
    :param lines: buffer 行。
    :param stderr: UI 输出流。
    :param line_guard: 输出快照前执行的运行态行收尾回调。
    :param terminal_columns: 运行态清理使用的终端列数。
    :returns: 写出的屏幕行数。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    if line_guard is not None:
        line_guard()
    print(f"[{header}]", file=stderr)
    row_count = terminal_row_count(f"[{header}]", columns=terminal_columns)
    if not lines:
        print(_EMPTY_VIEW_MESSAGE, file=stderr)
        return row_count + terminal_row_count(
            _EMPTY_VIEW_MESSAGE,
            columns=terminal_columns,
        )
    _write_lines(lines, stderr)
    for line in lines:
        row_count += terminal_row_count(line, columns=terminal_columns)
    return row_count


__all__: tuple[str, ...] = (
    "ActivitySink",
    "InteractiveRunView",
    "InteractiveRunViewMode",
    "InteractiveRunViewOptions",
    "TerminalInteractiveRunView",
    "new_interactive_run_view",
)
