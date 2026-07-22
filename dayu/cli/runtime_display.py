"""CLI 运行态终端显示控制 helper。

本模块只提供 CLI UI adapter 层复用的终端行数估算和 ANSI 清理输出，不读取
Host / Service 状态，也不参与 logging handler 装配。
"""

from __future__ import annotations

import asyncio
import shutil
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Final, TextIO
from typing import Protocol

from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityCallback,
    EntrypointCallbackExecutionPort,
    EntrypointRunTerminalResult,
    EntrypointThinking,
    EntrypointThinkingCallback,
)

_CURSOR_UP_ONE_LINE: Final[str] = "\x1b[1A"
_CARRIAGE_RETURN: Final[str] = "\r"
_CLEAR_CURRENT_LINE: Final[str] = "\x1b[2K"
_DEFAULT_TERMINAL_COLUMNS: Final[int] = 80
_DEFAULT_TERMINAL_LINES: Final[int] = 24
_MIN_TERMINAL_COLUMNS: Final[int] = 1
_EAST_ASIAN_FULLWIDTH: Final[str] = "F"
_EAST_ASIAN_WIDE: Final[str] = "W"
_DISPLAY_EXECUTOR_THREAD_PREFIX: Final[str] = "dayu-cli-display"


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

    def toggle_runtime_display(self) -> None:
        """切换 activity-like 运行态展示模式。

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


class RuntimeDisplayController(EntrypointCallbackExecutionPort):
    """拥有单个 CLI display lifecycle 的私有串行执行域。

    每个实例恰好创建一个 ``max_workers=1`` executor 与一个 event-loop async
    serial gate。所有 renderer/callback 工作先取得 gate，再提交到该私有
    executor；实例不保存 Host event 或 Service observation result。
    """

    activity_display: RuntimeActivityDisplay | None
    thinking_display: RuntimeThinkingDisplay | None
    _executor: ThreadPoolExecutor
    _serial_gate: asyncio.Lock
    _closing: bool
    _close_started: bool
    _closed: bool
    _closed_event: asyncio.Event
    _close_error: BaseException | None

    def __init__(
        self,
        *,
        activity_display: RuntimeActivityDisplay | None,
        thinking_display: RuntimeThinkingDisplay | None,
    ) -> None:
        """创建 display controller 与私有单线程 executor。

        :param activity_display: activity-like 展示；``None`` 表示不输出。
        :param thinking_display: thinking 展示；``None`` 表示不输出。
        :returns: ``None``。
        :raises RuntimeError: executor 构造失败时透传。
        """

        self.activity_display = activity_display
        self.thinking_display = thinking_display
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=_DISPLAY_EXECUTOR_THREAD_PREFIX,
        )
        self._serial_gate = asyncio.Lock()
        self._closing = False
        self._close_started = False
        self._closed = False
        self._closed_event = asyncio.Event()
        self._close_error = None

    async def invoke_activity(
        self,
        callback: EntrypointActivityCallback,
        activity: EntrypointActivity,
    ) -> None:
        """在私有 executor 串行调用 activity callback。

        :param callback: Service 传入的同步 activity callback。
        :param activity: Service activity DTO。
        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: callback 原始失败时透传。
        """

        async with self._serial_gate:
            self._require_open()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, callback, activity)

    async def invoke_thinking(
        self,
        callback: EntrypointThinkingCallback,
        thinking: EntrypointThinking,
    ) -> None:
        """在私有 executor 串行调用 thinking callback。

        :param callback: Service 传入的同步 thinking callback。
        :param thinking: Service thinking DTO。
        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: callback 原始失败时透传。
        """

        async with self._serial_gate:
            self._require_open()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, callback, thinking)

    async def install_runtime_line_guard(self) -> None:
        """在私有 executor 安装 thinking-first 行收尾 guard。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._install_runtime_line_guard)

    async def clear_runtime_line_guard(self) -> None:
        """在私有 executor 移除 activity-like 行收尾 guard。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._clear_runtime_line_guard)

    async def finish_runtime_display(self) -> None:
        """按 thinking 优先顺序串行结束当前运行态展示。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._finish_runtime_display)

    async def finish_thinking_display(self) -> None:
        """在取消路径只结束 thinking 行，不提前关闭 renderer。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._finish_thinking_display)

    async def toggle_activity_display(self) -> None:
        """在私有 executor 切换 activity-like 展示。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._toggle_activity_display)

    async def render_cancel_requested(self) -> None:
        """在私有 executor 渲染用户取消请求。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._render_cancel_requested)

    async def render_local_exit_after_cancel(self) -> None:
        """在私有 executor 先结束 thinking，再渲染本地退出提示。

        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 失败时透传。
        """

        await self._run_display_job(self._render_local_exit_after_cancel)

    async def render_terminal_result(
        self,
        renderer: Callable[[EntrypointRunTerminalResult], int],
        result: EntrypointRunTerminalResult,
    ) -> int:
        """在私有 executor 串行调用 interactive terminal renderer。

        :param renderer: typed terminal renderer。
        :param result: Service terminal result。
        :returns: CLI exit code。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 原始失败时透传。
        """

        async with self._serial_gate:
            self._require_open()
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, renderer, result)

    async def aclose(self) -> None:
        """按固定顺序关闭 renderer 并 shutdown 私有 executor。

        :returns: ``None``。
        :raises BaseException: renderer close 或 executor shutdown 原始失败；
            两者都失败时 renderer close 保持 top-level。
        """

        if self._closed:
            if self._close_error is not None:
                raise self._close_error
            return
        if self._close_started:
            await self._closed_event.wait()
            if self._close_error is not None:
                raise self._close_error
            return
        self._closing = True
        self._close_started = True
        close_error: BaseException | None = None
        try:
            async with self._serial_gate:
                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(
                        self._executor,
                        self._close_displays,
                    )
                except BaseException as error:
                    close_error = error
        finally:
            try:
                self._executor.shutdown(wait=True, cancel_futures=False)
            except BaseException as shutdown_error:
                close_error = _combine_close_errors(close_error, shutdown_error)
            self._closed = True
            self._closed_event.set()
            self._close_error = close_error
        if close_error is not None:
            raise close_error

    def begin_closing(self) -> None:
        """在 event loop 上先标记 closing，拒绝后续新 display work。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._closing = True

    async def _run_display_job(self, job: Callable[[], None]) -> None:
        """取得 serial gate 后向私有 executor 提交单个 display job。

        :param job: 不接收参数的同步 display job。
        :returns: ``None``。
        :raises RuntimeError: controller closing/closed 或调度失败时抛出。
        :raises Exception: renderer 原始失败时透传。
        """

        async with self._serial_gate:
            self._require_open()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, job)

    def _require_open(self) -> None:
        """拒绝 closing/closed 后的新 display work。

        :returns: ``None``。
        :raises RuntimeError: controller 已进入 closing 或 closed 时抛出。
        """

        if self._closing or self._closed:
            raise RuntimeError("runtime display controller is closing")

    def _install_runtime_line_guard(self) -> None:
        """同步安装 renderer line guard。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.activity_display is None:
            return
        guard: Callable[[], None] | None = None
        if self.thinking_display is not None:
            guard = self.thinking_display.finish_runtime_display
        self.activity_display.set_runtime_line_guard(guard)

    def _clear_runtime_line_guard(self) -> None:
        """同步移除 renderer line guard。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.activity_display is not None:
            self.activity_display.set_runtime_line_guard(None)

    def _finish_runtime_display(self) -> None:
        """同步结束 thinking/activity 运行态展示。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.thinking_display is not None:
            self.thinking_display.finish_runtime_display()
        if self.activity_display is not None:
            self.activity_display.finish_runtime_display()

    def _finish_thinking_display(self) -> None:
        """同步结束 thinking 运行态展示。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.thinking_display is not None:
            self.thinking_display.finish_runtime_display()

    def _toggle_activity_display(self) -> None:
        """同步切换 activity-like 展示。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.activity_display is not None:
            self.activity_display.toggle_runtime_display()

    def _render_cancel_requested(self) -> None:
        """同步渲染取消请求。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.activity_display is not None:
            self.activity_display.render_cancel_requested()

    def _render_local_exit_after_cancel(self) -> None:
        """同步结束 thinking 并渲染本地退出。

        :returns: ``None``。
        :raises Exception: renderer 失败时透传。
        """

        if self.thinking_display is not None:
            self.thinking_display.finish_runtime_display()
        if self.activity_display is not None:
            self.activity_display.render_local_exit_after_cancel()

    def _close_displays(self) -> None:
        """在 executor worker 中精确一次关闭全部 renderer。

        :returns: ``None``。
        :raises BaseException: 首个 renderer cleanup failure 保持 top-level。
        """

        primary_error: BaseException | None = None
        if self.activity_display is not None:
            try:
                self.activity_display.set_runtime_line_guard(None)
            except BaseException as error:
                primary_error = _combine_close_errors(primary_error, error)
        if self.thinking_display is not None:
            try:
                self.thinking_display.close()
            except BaseException as error:
                primary_error = _combine_close_errors(primary_error, error)
        if self.activity_display is not None:
            try:
                self.activity_display.close()
            except BaseException as error:
                primary_error = _combine_close_errors(primary_error, error)
        if primary_error is not None:
            raise primary_error


def _combine_close_errors(
    primary_error: BaseException | None,
    later_error: BaseException,
) -> BaseException:
    """保持首个 cleanup failure，并把后续 failure 接为直接 cause。

    :param primary_error: 已有首个 cleanup failure；尚无失败时为 ``None``。
    :param later_error: 后续 cleanup failure。
    :returns: 应继续传播的首个 failure。
    :raises Exception: 不主动抛出异常。
    """

    if primary_error is None:
        return later_error
    _append_close_cause(primary_error, later_error)
    return primary_error


def _append_close_cause(
    primary_error: BaseException,
    later_error: BaseException,
) -> None:
    """把后续 cleanup failure 追加到既有 cause 链尾部。

    :param primary_error: 必须保持 top-level identity 的首个失败。
    :param later_error: 后续 cleanup failure。
    :returns: ``None``。
    :raises RuntimeError: 检测到既有 cause 环时抛出。
    """

    current = primary_error
    seen_ids: set[int] = set()
    while current.__cause__ is not None:
        current_id = id(current)
        if current_id in seen_ids:
            raise RuntimeError("runtime display cleanup cause chain contains a cycle")
        seen_ids.add(current_id)
        current = current.__cause__
    current.__cause__ = later_error


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
        shutil.get_terminal_size(fallback=(_DEFAULT_TERMINAL_COLUMNS, _DEFAULT_TERMINAL_LINES)).columns,
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
