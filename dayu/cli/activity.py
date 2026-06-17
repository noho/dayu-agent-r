"""CLI entrypoint activity 渲染 helper。

本模块只消费 Service 层 ``EntrypointActivity`` DTO，并把运行态 activity
投影到 stderr。它不读取 Host durable internals，不解析 EventLog payload，
也不决定 terminal final answer 的 stdout/stderr 输出。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Final, TextIO

from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityCounts,
    EntrypointActivitySeverity,
)

_ACTIVITY_PREFIX: Final[str] = "Activity"
_ACTIVITY_HIDDEN_PREFIX: Final[str] = "Activity hidden"
_ACTIVITY_CANCEL_REQUESTED_MESSAGE: Final[str] = "Activity: cancel requested"
_ACTIVITY_LOCAL_EXIT_MESSAGE: Final[str] = "Activity: cancelling; local process exiting"
_TEXT_MAX_CHARS: Final[int] = 160
_TRUNCATED_SUFFIX: Final[str] = "..."


@dataclass(frozen=True, slots=True)
class CliActivityRendererOptions:
    """CLI activity renderer 配置。

    :param visible: 初始是否展示 activity。
    :param enabled: 是否允许输出 live activity；通常仅 TTY stderr 启用。
    """

    visible: bool
    enabled: bool


class CliActivityRenderer:
    """按 Service activity DTO 渲染 CLI 运行态 activity。

    renderer 维护本地 dedupe key 和 event sequence 状态，避免 watch replay 或
    同一事件重复回调造成重复输出。
    """

    _stderr: TextIO
    _visible: bool
    _enabled: bool
    _closed: bool
    _seen_dedupe_keys: set[str]
    _last_event_sequence: int | None
    _last_hidden_title: str | None

    def __init__(
        self,
        *,
        stderr: TextIO | None = None,
        options: CliActivityRendererOptions | None = None,
    ) -> None:
        """初始化 renderer。

        :param stderr: activity 输出流；``None`` 表示当前 ``sys.stderr``。
        :param options: renderer 配置；``None`` 时按 stderr 是否 TTY 自动启用。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._stderr = sys.stderr if stderr is None else stderr
        if options is None:
            options = CliActivityRendererOptions(
                visible=True,
                enabled=self._stderr.isatty(),
            )
        self._visible = options.visible
        self._enabled = options.enabled
        self._closed = False
        self._seen_dedupe_keys = set()
        self._last_event_sequence = None
        self._last_hidden_title = None

    @property
    def visible(self) -> bool:
        """返回当前 activity 是否可见。

        :returns: 可见返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self._visible

    def record(self, activity: EntrypointActivity) -> None:
        """记录并按当前可见性输出一条 activity。

        :param activity: Service activity DTO。
        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        if activity.dedupe_key in self._seen_dedupe_keys:
            return
        if (
            activity.event_sequence is not None
            and self._last_event_sequence is not None
            and activity.event_sequence < self._last_event_sequence
        ):
            return
        self._seen_dedupe_keys.add(activity.dedupe_key)
        if activity.event_sequence is not None:
            self._last_event_sequence = activity.event_sequence
        self._last_hidden_title = activity.title
        if not self._visible:
            return
        print(_activity_line(_ACTIVITY_PREFIX, activity), file=self._stderr)

    def toggle_visible(self) -> None:
        """切换 activity 可见性。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed:
            return
        self._visible = not self._visible
        if self._enabled and not self._visible and self._last_hidden_title is not None:
            print(
                f"{_ACTIVITY_HIDDEN_PREFIX}: {_bounded_text(self._last_hidden_title)}",
                file=self._stderr,
            )

    def render_cancel_requested(self) -> None:
        """输出用户已请求取消的运行态提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        print(_ACTIVITY_CANCEL_REQUESTED_MESSAGE, file=self._stderr)

    def render_local_exit_after_cancel(self) -> None:
        """输出二次中断导致本地退出的运行态提示。

        :returns: ``None``。
        :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
        """

        if self._closed or not self._enabled:
            return
        print(_ACTIVITY_LOCAL_EXIT_MESSAGE, file=self._stderr)

    def close(self) -> None:
        """关闭 renderer，后续 activity 不再输出。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._closed = True


def new_cli_activity_renderer(*, stderr: TextIO | None = None) -> CliActivityRenderer:
    """按默认 TTY policy 创建 CLI activity renderer。

    :param stderr: activity 输出流；``None`` 表示当前 ``sys.stderr``。
    :returns: CLI activity renderer。
    :raises Exception: 不主动抛出异常。
    """

    return CliActivityRenderer(stderr=stderr)


def _activity_line(prefix: str, activity: EntrypointActivity) -> str:
    """构造单行 activity 展示文本。

    :param prefix: 行前缀。
    :param activity: Service activity DTO。
    :returns: 有界单行展示文本。
    :raises Exception: 不主动抛出异常。
    """

    parts = [
        f"{prefix}:",
        activity.status.value,
        _bounded_text(activity.title),
    ]
    if activity.tool_display_name is not None:
        parts.append(f"tool={_bounded_text(activity.tool_display_name)}")
    elif activity.tool_name is not None:
        parts.append(f"tool={_bounded_text(activity.tool_name)}")
    if activity.summary is not None:
        parts.append(_bounded_text(activity.summary))
    if activity.counts is not None:
        parts.append(_counts_text(activity.counts))
    if activity.severity is not EntrypointActivitySeverity.INFO:
        parts.append(f"severity={activity.severity.value}")
    return " ".join(parts)


def _counts_text(counts: EntrypointActivityCounts) -> str:
    """构造 activity counts 展示片段。

    :param counts: Service activity counts。
    :returns: counts 展示文本。
    :raises Exception: 不主动抛出异常。
    """

    return f"total={counts.total} completed={counts.completed} " f"failed={counts.failed} cancelled={counts.cancelled}"


def _bounded_text(value: str) -> str:
    """把展示文本压缩为单行有界字符串。

    :param value: 原始文本。
    :returns: 单行有界文本。
    :raises Exception: 不主动抛出异常。
    """

    normalized = " ".join(value.split())
    if len(normalized) <= _TEXT_MAX_CHARS:
        return normalized
    return normalized[: _TEXT_MAX_CHARS - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX


__all__: tuple[str, ...] = (
    "CliActivityRenderer",
    "CliActivityRendererOptions",
    "new_cli_activity_renderer",
)
