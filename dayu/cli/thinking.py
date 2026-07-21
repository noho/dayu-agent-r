"""CLI running thinking 渲染 helper。

本模块只消费 Service 层 ``EntrypointThinking`` DTO，并把运行态 thinking
增量投影到 stderr。它不读取 Host durable internals，不影响模型请求配置，
也不决定 terminal final answer 的 stdout/stderr 输出。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final, TextIO

from dayu.cli.runtime_display import (
    clear_open_rows,
    resolve_terminal_columns,
    terminal_row_count,
)
from dayu.service.entrypoint_runtime import EntrypointThinking

_THINKING_PREFIX: Final[str] = "Thinking"
_TEXT_MAX_CHARS: Final[int] = 160
_TRUNCATED_SUFFIX: Final[str] = "..."


@dataclass(frozen=True, slots=True)
class CliThinkingRendererOptions:
    """CLI thinking renderer 配置。

    :param enabled: 是否允许输出 live thinking。
    :param terminal_control: 是否允许输出 ANSI 清理控制符；``None`` 表示按
        stderr 是否 TTY 自动判断。
    :param terminal_columns: 运行态清理使用的终端列数；``None`` 表示读取当前
        终端或使用默认 fallback。
    """

    enabled: bool
    terminal_control: bool | None = None
    terminal_columns: int | None = None


class CliThinkingRenderer:
    """按 Service thinking DTO 渲染 CLI 运行态 thinking。"""

    _stderr: TextIO
    _enabled: bool
    _closed: bool
    _line_open: bool
    _supports_terminal_control: bool
    _terminal_columns: int
    _line_text: str
    _seen_dedupe_keys: set[str]
    _last_runtime_id: str | None
    _last_runtime_sequence: int | None

    def __init__(
        self,
        *,
        stderr: TextIO | None = None,
        options: CliThinkingRendererOptions | None = None,
    ) -> None:
        """初始化 renderer。

        :param stderr: thinking 输出流；``None`` 表示当前 ``sys.stderr``。
        :param options: renderer 配置；``None`` 时按 stderr 是否 TTY 自动启用。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._stderr = sys.stderr if stderr is None else stderr
        if options is None:
            options = CliThinkingRendererOptions(enabled=self._stderr.isatty())
        self._enabled = options.enabled
        self._closed = False
        self._line_open = False
        self._supports_terminal_control = (
            self._stderr.isatty()
            if options.terminal_control is None
            else options.terminal_control
        )
        self._terminal_columns = resolve_terminal_columns(options.terminal_columns)
        self._line_text = ""
        self._seen_dedupe_keys = set()
        self._last_runtime_id = None
        self._last_runtime_sequence = None

    def record(self, thinking: EntrypointThinking) -> None:
        """记录并输出一条 thinking 增量。

        :param thinking: Service thinking DTO。
        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层输出流透传。
        """

        if self._closed or not self._enabled:
            return
        if thinking.dedupe_key in self._seen_dedupe_keys:
            return
        if thinking.runtime_id != self._last_runtime_id:
            self._last_runtime_id = thinking.runtime_id
            self._last_runtime_sequence = None
        if self._last_runtime_sequence is not None and (thinking.runtime_sequence <= self._last_runtime_sequence):
            return
        self._seen_dedupe_keys.add(thinking.dedupe_key)
        self._last_runtime_sequence = thinking.runtime_sequence
        if self._line_open:
            delta_text = _single_line_delta_text(
                thinking.text_delta,
                trim_leading=False,
            )
            self._stderr.write(delta_text)
            self._line_text += delta_text
        else:
            self._line_text = format_cli_thinking_line(thinking)
            self._stderr.write(self._line_text)
            self._line_open = True
        self._stderr.flush()

    def finish_runtime_display(self) -> None:
        """结束当前 thinking 运行态展示，为 terminal result 输出让出干净位置。

        TTY 下清除当前 thinking 行，让最终回答成为屏幕上留下的内容；非 TTY
        或测试捕获流下只补一个换行，避免输出不可读 ANSI 控制符。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层输出流透传。
        """

        if self._closed or not self._enabled or not self._line_open:
            return
        if self._supports_terminal_control:
            clear_open_rows(
                self._stderr,
                row_count=terminal_row_count(
                    self._line_text,
                    columns=self._terminal_columns,
                ),
            )
        else:
            self._stderr.write("\n")
            self._stderr.flush()
        self._line_open = False
        self._line_text = ""

    def close(self) -> None:
        """关闭 renderer，后续 thinking 不再输出。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._closed = True


def format_cli_thinking_line(thinking: EntrypointThinking) -> str:
    """构造默认 CLI thinking 展示行。

    :param thinking: Service thinking DTO。
    :returns: 单行 thinking 展示文本。
    :raises Exception: 不主动抛出异常。
    """

    delta_text = _single_line_delta_text(thinking.text_delta, trim_leading=True)
    return f"{_THINKING_PREFIX}: {delta_text}"


def _single_line_delta_text(value: str, *, trim_leading: bool) -> str:
    """把 thinking delta 转为单行展示文本。

    :param value: 原始 thinking delta。
    :param trim_leading: 是否去掉首个 delta 的前导空格。
    :returns: 单行 delta 展示文本。
    :raises Exception: 不主动抛出异常。
    """

    normalized = _control_chars_to_spaces(value)
    if trim_leading:
        normalized = normalized.lstrip(" ")
    if len(normalized) <= _TEXT_MAX_CHARS:
        return normalized
    return normalized[: _TEXT_MAX_CHARS - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX


def _control_chars_to_spaces(value: str) -> str:
    """把换行和控制字符替换为空格，保留普通空格边界。

    :param value: 原始文本。
    :returns: 单行展示文本。
    :raises Exception: 不主动抛出异常。
    """

    characters: list[str] = []
    previous_was_control = False
    for character in value:
        if character.isprintable():
            characters.append(character)
            previous_was_control = False
        elif not previous_was_control:
            characters.append(" ")
            previous_was_control = True
        else:
            continue
    return "".join(characters)


__all__: tuple[str, ...] = (
    "CliThinkingRenderer",
    "CliThinkingRendererOptions",
    "format_cli_thinking_line",
)
