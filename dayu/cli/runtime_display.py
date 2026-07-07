"""CLI 运行态终端显示控制 helper。

本模块只提供 CLI UI adapter 层复用的终端行数估算和 ANSI 清理输出，不读取
Host / Service 状态，也不参与 logging handler 装配。
"""

from __future__ import annotations

import shutil
import unicodedata
from typing import Final, TextIO

_CURSOR_UP_ONE_LINE: Final[str] = "\x1b[1A"
_CARRIAGE_RETURN: Final[str] = "\r"
_CLEAR_CURRENT_LINE: Final[str] = "\x1b[2K"
_DEFAULT_TERMINAL_COLUMNS: Final[int] = 80
_DEFAULT_TERMINAL_LINES: Final[int] = 24
_MIN_TERMINAL_COLUMNS: Final[int] = 1
_EAST_ASIAN_FULLWIDTH: Final[str] = "F"
_EAST_ASIAN_WIDE: Final[str] = "W"


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
    "clear_completed_rows",
    "clear_open_rows",
    "resolve_terminal_columns",
    "terminal_row_count",
)
