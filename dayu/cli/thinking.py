"""CLI running thinking 渲染 helper。

本模块只消费 Service 层 ``EntrypointThinking`` DTO，并把运行态 thinking
增量投影到 stderr。它不读取 Host durable internals，不影响模型请求配置，
也不决定 terminal final answer 的 stdout/stderr 输出。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final, TextIO

from dayu.service.entrypoint_runtime import EntrypointThinking

_THINKING_PREFIX: Final[str] = "Thinking"
_TEXT_MAX_CHARS: Final[int] = 160
_TRUNCATED_SUFFIX: Final[str] = "..."


@dataclass(frozen=True, slots=True)
class CliThinkingRendererOptions:
    """CLI thinking renderer 配置。

    :param enabled: 是否允许输出 live thinking。
    """

    enabled: bool


class CliThinkingRenderer:
    """按 Service thinking DTO 渲染 CLI 运行态 thinking。"""

    _stderr: TextIO
    _enabled: bool
    _closed: bool
    _seen_dedupe_keys: set[str]
    _last_event_sequence: int | None

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
        self._seen_dedupe_keys = set()
        self._last_event_sequence = None

    def record(self, thinking: EntrypointThinking) -> None:
        """记录并输出一条 thinking 增量。

        :param thinking: Service thinking DTO。
        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        if thinking.dedupe_key in self._seen_dedupe_keys:
            return
        if (
            self._last_event_sequence is not None
            and thinking.event_sequence < self._last_event_sequence
        ):
            return
        self._seen_dedupe_keys.add(thinking.dedupe_key)
        self._last_event_sequence = thinking.event_sequence
        print(format_cli_thinking_line(thinking), file=self._stderr)

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

    return f"{_THINKING_PREFIX}: {_single_line_text(thinking.text_delta)}"


def _single_line_text(value: str) -> str:
    """把 thinking 文本压缩为单行字符串。

    :param value: 原始 thinking 文本。
    :returns: 单行文本。
    :raises Exception: 不主动抛出异常。
    """

    normalized = " ".join(value.split())
    if len(normalized) <= _TEXT_MAX_CHARS:
        return normalized
    return normalized[: _TEXT_MAX_CHARS - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX


__all__: tuple[str, ...] = (
    "CliThinkingRenderer",
    "CliThinkingRendererOptions",
    "format_cli_thinking_line",
)
