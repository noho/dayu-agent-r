"""CLI 运行态终端显示控制 helper。

本模块只提供 CLI UI adapter 层复用的终端行数估算和 ANSI 清理输出，不读取
Host / Service 状态，也不参与 logging handler 装配。
"""

from __future__ import annotations

import shutil
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TextIO
from typing import Protocol

_CURSOR_UP_ONE_LINE: Final[str] = "\x1b[1A"
_CARRIAGE_RETURN: Final[str] = "\r"
_CLEAR_CURRENT_LINE: Final[str] = "\x1b[2K"
_DEFAULT_TERMINAL_COLUMNS: Final[int] = 80
_DEFAULT_TERMINAL_LINES: Final[int] = 24
_MIN_TERMINAL_COLUMNS: Final[int] = 1
_EAST_ASIAN_FULLWIDTH: Final[str] = "F"
_EAST_ASIAN_WIDE: Final[str] = "W"


class RuntimeActivityDisplay(Protocol):
    """CLI 运行态 activity-like 展示协议。

    该协议只描述 prompt activity renderer 与 interactive run view 在运行态
    清理时共享的 UI 能力，不包含二者各自的业务输入、view 切换或 terminal
    result 渲染差异。
    """

    def set_runtime_line_guard(self, guard: Callable[[], None] | None) -> None:
        """设置运行态输出前执行的行收尾回调。

        :param guard: 输出运行态行前执行的回调；``None`` 表示不执行。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """
        ...

    def finish_runtime_display(self) -> None:
        """结束当前运行态展示，为 terminal result 输出让出干净位置。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """
        ...

    def render_cancel_requested(self) -> None:
        """渲染用户已请求取消的运行态提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """
        ...

    def render_local_exit_after_cancel(self) -> None:
        """渲染二次中断导致本地退出的提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """
        ...

    def close(self) -> None:
        """关闭 activity-like 展示，后续运行态行不再输出。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """
        ...


class RuntimeThinkingDisplay(Protocol):
    """CLI 运行态 thinking 展示协议。"""

    def finish_runtime_display(self) -> None:
        """结束当前 thinking 运行态展示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由实现透传。
        """
        ...

    def close(self) -> None:
        """关闭 thinking 展示，后续增量不再输出。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """
        ...


@dataclass(slots=True)
class RuntimeDisplayController:
    """协调 CLI activity-like 展示与 thinking 展示的运行态清理时序。

    :param activity_display: activity-like 展示；``None`` 表示不输出 activity。
    :param thinking_display: thinking 展示；``None`` 表示不输出 thinking。
    """

    activity_display: RuntimeActivityDisplay | None
    thinking_display: RuntimeThinkingDisplay | None
    _thinking_closed: bool = False
    _activity_closed: bool = False

    def install_runtime_line_guard(self) -> None:
        """安装 activity-like 输出前的 thinking 行收尾 guard。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self.activity_display is None or self._activity_closed:
            return
        guard: Callable[[], None] | None = None
        if self.thinking_display is not None and not self._thinking_closed:
            guard = self.thinking_display.finish_runtime_display
        self.activity_display.set_runtime_line_guard(guard)

    def clear_runtime_line_guard(self) -> None:
        """移除 activity-like 输出前的运行态行收尾 guard。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self.activity_display is not None and not self._activity_closed:
            self.activity_display.set_runtime_line_guard(None)

    def finish_runtime_display(self) -> None:
        """按 thinking 优先顺序结束本轮运行态展示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 renderer 透传。
        """

        if self.thinking_display is not None and not self._thinking_closed:
            self.thinking_display.finish_runtime_display()
        if self.activity_display is not None and not self._activity_closed:
            self.activity_display.finish_runtime_display()

    def finish_and_close_thinking(self) -> None:
        """在进入取消路径前结束并关闭 thinking 展示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 renderer 透传。
        """

        if self.thinking_display is None or self._thinking_closed:
            return
        self.thinking_display.finish_runtime_display()
        self.thinking_display.close()
        self._thinking_closed = True
        self.clear_runtime_line_guard()

    def close_thinking(self) -> None:
        """关闭 thinking 展示，幂等处理取消路径已关闭的情况。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self.thinking_display is None or self._thinking_closed:
            return
        self.thinking_display.close()
        self._thinking_closed = True
        self.clear_runtime_line_guard()

    def close_activity(self) -> None:
        """关闭 activity-like 展示，幂等处理已关闭的情况。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self.activity_display is None or self._activity_closed:
            return
        self.clear_runtime_line_guard()
        self.activity_display.close()
        self._activity_closed = True

    def close(self) -> None:
        """关闭 controller 管理的所有运行态展示。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_thinking()
        self.close_activity()

    def render_cancel_requested(self) -> None:
        """渲染用户已请求取消的 activity-like 提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 renderer 透传。
        """

        if self.activity_display is not None and not self._activity_closed:
            self.activity_display.render_cancel_requested()

    def render_local_exit_after_cancel(self) -> None:
        """二次中断本地退出前先清理 thinking，再渲染本地退出提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 renderer 透传。
        """

        if self.thinking_display is not None and not self._thinking_closed:
            self.thinking_display.finish_runtime_display()
        if self.activity_display is not None and not self._activity_closed:
            self.activity_display.render_local_exit_after_cancel()


def resolve_terminal_columns(explicit_columns: int | None) -> int:
    """解析用于运行态清理的终端列数。

    :param explicit_columns: 调用方显式指定的列数；``None`` 表示读取当前终端。
    :returns: 至少为 1 的终端列数。
    :raises Exception: 不主动抛出异常。
    """

    if explicit_columns is not None:
        return max(_MIN_TERMINAL_COLUMNS, explicit_columns)
    return max(
        _MIN_TERMINAL_COLUMNS,
        shutil.get_terminal_size(
            fallback=(_DEFAULT_TERMINAL_COLUMNS, _DEFAULT_TERMINAL_LINES)
        ).columns,
    )


def terminal_row_count(text: str, *, columns: int) -> int:
    """估算单行文本在终端中占用的屏幕行数。

    :param text: 不含末尾换行的展示文本。
    :param columns: 终端列数。
    :returns: 至少为 1 的屏幕行数。
    :raises Exception: 不主动抛出异常。
    """

    safe_columns = max(_MIN_TERMINAL_COLUMNS, columns)
    cell_count = _display_cell_count(text)
    return max(_MIN_TERMINAL_COLUMNS, (cell_count + safe_columns - 1) // safe_columns)


def _display_cell_count(text: str) -> int:
    """估算文本在终端中的显示列宽。

    :param text: 不含末尾换行的展示文本。
    :returns: 至少为 0 的显示列宽。
    :raises Exception: 不主动抛出异常。
    """

    cell_count = 0
    for character in text:
        if unicodedata.combining(character) != 0:
            continue
        if unicodedata.east_asian_width(character) in (
            _EAST_ASIAN_FULLWIDTH,
            _EAST_ASIAN_WIDE,
        ):
            cell_count += 2
        else:
            cell_count += 1
    return cell_count


def clear_completed_rows(stream: TextIO, *, row_count: int) -> None:
    """清除已经以换行结束的运行态屏幕行。

    :param stream: 终端输出流。
    :param row_count: 需要清理的屏幕行数。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层输出流透传。
    """

    if row_count <= 0:
        return
    for _ in range(row_count):
        stream.write(f"{_CURSOR_UP_ONE_LINE}{_CARRIAGE_RETURN}{_CLEAR_CURRENT_LINE}")
    stream.flush()


def clear_open_rows(stream: TextIO, *, row_count: int) -> None:
    """清除当前未以换行结束的运行态屏幕行。

    :param stream: 终端输出流。
    :param row_count: 当前打开行占用的屏幕行数。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层输出流透传。
    """

    if row_count <= 0:
        return
    stream.write(f"{_CARRIAGE_RETURN}{_CLEAR_CURRENT_LINE}")
    for _ in range(row_count - 1):
        stream.write(f"{_CURSOR_UP_ONE_LINE}{_CARRIAGE_RETURN}{_CLEAR_CURRENT_LINE}")
    stream.flush()


__all__: tuple[str, ...] = (
    "RuntimeActivityDisplay",
    "RuntimeDisplayController",
    "RuntimeThinkingDisplay",
    "clear_completed_rows",
    "clear_open_rows",
    "resolve_terminal_columns",
    "terminal_row_count",
)
