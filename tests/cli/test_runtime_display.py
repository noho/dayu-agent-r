"""CLI 私有串行 display execution domain 测试。"""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import Callable

import pytest

import dayu.cli.session_execution as session_execution
from dayu.cli.agent_entrypoint import CliSigintMonitor
from dayu.cli.run_keys import RunningKeyAction
from dayu.cli.runtime_display import (
    RuntimeDisplayController,
    clear_completed_rows,
    clear_open_rows,
    resolve_terminal_columns,
    terminal_row_count,
)
from dayu.host.api import HostTerminalStatus
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityKind,
    EntrypointActivitySeverity,
    EntrypointActivityStatus,
    EntrypointRunTerminalResult,
    EntrypointTerminalSource,
    EntrypointThinking,
)


class _FakeActivityDisplay:
    """记录 activity-like renderer 调用与关闭次数。"""

    def __init__(self, events: list[str], *, close_error: Exception | None = None) -> None:
        """初始化 fake。

        :param events: 共享顺序记录。
        :param close_error: 可选 close 原始失败。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events = events
        self.guard: Callable[[], None] | None = None
        self.close_count = 0
        self.close_error = close_error

    def set_runtime_line_guard(self, guard: Callable[[], None] | None) -> None:
        """记录 guard 设置。

        :param guard: thinking line guard。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.guard = guard
        self.events.append("activity:guard:on" if guard else "activity:guard:off")

    def emit_runtime_line(self) -> None:
        """模拟 activity renderer 输出一行。

        :returns: None。
        :raises Exception: guard 失败时透传。
        """

        if self.guard is not None:
            self.guard()
        self.events.append("activity:line")

    def finish_runtime_display(self) -> None:
        """记录 finish。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:finish")

    def toggle_runtime_display(self) -> None:
        """记录 toggle。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:toggle")

    def render_cancel_requested(self) -> None:
        """记录 cancel render。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:cancel")

    def render_local_exit_after_cancel(self) -> None:
        """记录 local-exit render。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:local-exit")

    def close(self) -> None:
        """记录 close 并可抛原始失败。

        :returns: None。
        :raises Exception: 配置 close failure 时抛出。
        """

        self.close_count += 1
        self.events.append("activity:close")
        if self.close_error is not None:
            raise self.close_error


class _FakeThinkingDisplay:
    """记录 thinking renderer 调用与关闭次数。"""

    def __init__(self, events: list[str]) -> None:
        """初始化 fake。

        :param events: 共享顺序记录。
        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events = events
        self.close_count = 0

    def finish_runtime_display(self) -> None:
        """记录 finish。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("thinking:finish")

    def close(self) -> None:
        """记录 close。

        :returns: None。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1
        self.events.append("thinking:close")


class _OrderingActivityDisplay(_FakeActivityDisplay):
    """为 caller lifecycle 记录 renderer close 起止边界。"""

    def close(self) -> None:
        """记录 renderer close 的精确起止顺序。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1
        self.events.append("renderer_close_started")
        self.events.append("renderer_close_finished")


class _OrderingRuntimeDisplayController(RuntimeDisplayController):
    """在真实 controller 上增加 closing 请求观测点。"""

    def __init__(
        self,
        *,
        activity_display: _OrderingActivityDisplay,
        events: list[str],
    ) -> None:
        """初始化顺序观测 controller。

        :param activity_display: 顺序观测 renderer。
        :param events: 共享顺序记录。
        :returns: ``None``。
        :raises RuntimeError: 私有 executor 构造失败时透传。
        """

        super().__init__(
            activity_display=activity_display,
            thinking_display=None,
        )
        self._events = events

    def begin_closing(self) -> None:
        """记录 caller 在 event loop 发出的 closing 请求。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._events.append("close_requested")
        super().begin_closing()


class _OrderingRunningKeyMonitor:
    """只记录 caller-local close 的按键 monitor fake。"""

    def __init__(self, events: list[str]) -> None:
        """初始化 monitor。

        :param events: 共享顺序记录。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._events = events

    def start(self) -> None:
        """满足运行态 monitor 协议。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        return

    async def wait_next(self) -> RunningKeyAction:
        """等待直到测试 task 被取消。

        :returns: 正常路径不返回。
        :raises asyncio.CancelledError: task 被取消时透传。
        """

        await asyncio.Event().wait()
        return RunningKeyAction.CANCEL_RUN

    def close(self) -> None:
        """记录 caller-local 按键资源释放。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._events.append("caller_local_release:key")


class _OrderingSigintMonitor(CliSigintMonitor):
    """只记录 caller-local close 的 SIGINT monitor fake。"""

    def close(self) -> None:
        """记录 caller-local SIGINT 资源释放。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._events.append("caller_local_release:sigint")

    def __init__(self, events: list[str]) -> None:
        """初始化 monitor。

        :param events: 共享顺序记录。
        :returns: ``None``。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        super().__init__()
        self._events = events


def test_session_execution_skips_display_domain_without_callbacks() -> None:
    """activity/thinking consumer 都不存在时不得构造 execution domain。

    :returns: ``None``。
    :raises Exception: owner contract 断言失败时由 pytest 抛出。
    """

    assert (
        session_execution._new_runtime_display_controller(
            activity_display=None,
            thinking_display=None,
        )
        is None
    )


@pytest.mark.asyncio
async def test_runtime_display_controller_serializes_all_renderer_work() -> None:
    """callback、toggle、finish、cancel、local-exit 与 close 应在同一私有线程串行。

    :returns: ``None``。
    :raises Exception: 串行执行契约断言失败时由 pytest 抛出。
    """

    events: list[str] = []
    worker_ids: list[int] = []
    activity = _FakeActivityDisplay(events)
    thinking = _FakeThinkingDisplay(events)
    controller = RuntimeDisplayController(activity_display=activity, thinking_display=thinking)

    def record_activity(_activity_value: EntrypointActivity) -> None:
        """记录 activity callback worker identity。

        :param _activity_value: Service activity DTO。
        :returns: ``None``。
        :raises Exception: renderer fake 失败时透传。
        """

        worker_ids.append(threading.get_ident())
        activity.emit_runtime_line()

    def record_thinking(_thinking_value: EntrypointThinking) -> None:
        """记录 thinking callback worker identity。

        :param _thinking_value: Service thinking DTO。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        worker_ids.append(threading.get_ident())
        events.append("thinking:record")

    def render_terminal(_result: EntrypointRunTerminalResult) -> int:
        """记录 terminal renderer worker identity 并返回固定退出码。

        :param _result: Service terminal DTO。
        :returns: 固定测试退出码 7。
        :raises Exception: 不主动抛出异常。
        """

        worker_ids.append(threading.get_ident())
        events.append("terminal:render")
        return 7

    await controller.install_runtime_line_guard()
    await controller.invoke_activity(record_activity, _activity())
    await controller.invoke_thinking(record_thinking, _thinking())
    await controller.clear_runtime_line_guard()
    await controller.install_runtime_line_guard()
    await controller.finish_thinking_display()
    await controller.toggle_activity_display()
    await controller.finish_runtime_display()
    await controller.render_cancel_requested()
    await controller.render_local_exit_after_cancel()
    terminal_exit_code = await controller.render_terminal_result(
        render_terminal,
        _terminal_result(),
    )
    await controller.aclose()
    await controller.aclose()

    assert len(set(worker_ids)) == 1
    assert worker_ids[0] != threading.get_ident()
    assert terminal_exit_code == 7
    assert events == [
        "activity:guard:on",
        "thinking:finish",
        "activity:line",
        "thinking:record",
        "activity:guard:off",
        "activity:guard:on",
        "thinking:finish",
        "activity:toggle",
        "thinking:finish",
        "activity:finish",
        "activity:cancel",
        "thinking:finish",
        "activity:local-exit",
        "terminal:render",
        "activity:guard:off",
        "thinking:close",
        "activity:close",
    ]
    assert activity.close_count == 1
    assert thinking.close_count == 1


@pytest.mark.asyncio
async def test_runtime_display_close_waits_for_current_callback_before_renderer_close() -> None:
    """closing 应等待已提交 callback 真正结束，再关闭 renderer/executor。

    :returns: ``None``。
    :raises Exception: close barrier 契约断言失败时由 pytest 抛出。
    """

    events: list[str] = []
    started = threading.Event()
    release = threading.Event()
    controller = RuntimeDisplayController(activity_display=_FakeActivityDisplay(events), thinking_display=None)

    def blocking_callback(_activity_value: EntrypointActivity) -> None:
        """用可释放 barrier 模拟违反快速约束的 renderer。

        :param _activity_value: Service activity DTO。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        events.append("callback:started")
        started.set()
        release.wait()
        events.append("callback:finished")

    callback_task = asyncio.create_task(controller.invoke_activity(blocking_callback, _activity()))
    while not started.is_set():
        await asyncio.sleep(0)
    controller.begin_closing()
    close_task = asyncio.create_task(controller.aclose())
    await asyncio.sleep(0)

    assert events == ["callback:started"]
    release.set()
    await callback_task
    await close_task
    assert events == ["callback:started", "callback:finished", "activity:guard:off", "activity:close"]


@pytest.mark.asyncio
async def test_runtime_display_callback_and_close_failures_preserve_identity() -> None:
    """callback 与 renderer close failure 都应保留原异常 identity。

    :returns: ``None``。
    :raises Exception: failure identity 断言失败时由 pytest 抛出。
    """

    callback_error = RuntimeError("callback failed")
    close_error = RuntimeError("close failed")
    activity = _FakeActivityDisplay([], close_error=close_error)
    controller = RuntimeDisplayController(activity_display=activity, thinking_display=None)

    def fail_callback(_activity_value: EntrypointActivity) -> None:
        """抛出固定 callback failure。

        :param _activity_value: 未消费的 Service activity DTO。
        :returns: 本函数不返回。
        :raises RuntimeError: 始终抛出固定 callback failure。
        """

        raise callback_error

    with pytest.raises(RuntimeError, match="callback failed") as callback_info:
        await controller.invoke_activity(fail_callback, _activity())
    assert callback_info.value is callback_error

    with pytest.raises(RuntimeError, match="close failed") as close_info:
        await controller.aclose()
    assert close_info.value is close_error
    assert activity.close_count == 1


@pytest.mark.asyncio
async def test_runtime_display_close_and_shutdown_failures_keep_exact_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """renderer close + executor shutdown 应保持 close→shutdown 精确链且只执行一次。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises Exception: cleanup chain 断言失败时由 pytest 抛出。
    """

    close_error = RuntimeError("renderer close failed")
    shutdown_error = RuntimeError("executor shutdown failed")
    activity = _FakeActivityDisplay([], close_error=close_error)
    controller = RuntimeDisplayController(
        activity_display=activity,
        thinking_display=None,
    )
    original_shutdown = controller._executor.shutdown
    shutdown_count = 0

    def fail_after_shutdown(
        wait: bool = True,
        *,
        cancel_futures: bool = False,
    ) -> None:
        """执行真实 shutdown 后抛出固定 failure。

        :param wait: 是否等待 worker 完成。
        :param cancel_futures: 是否取消尚未执行的 future。
        :returns: 本函数不返回。
        :raises RuntimeError: 始终抛出固定 shutdown failure。
        """

        nonlocal shutdown_count
        shutdown_count += 1
        original_shutdown(wait=wait, cancel_futures=cancel_futures)
        raise shutdown_error

    monkeypatch.setattr(controller._executor, "shutdown", fail_after_shutdown)

    with pytest.raises(RuntimeError, match="renderer close failed") as first_info:
        await controller.aclose()
    with pytest.raises(RuntimeError, match="renderer close failed") as second_info:
        await controller.aclose()

    assert first_info.value is close_error
    assert second_info.value is close_error
    assert close_error.__cause__ is shutdown_error
    assert activity.close_count == 1
    assert shutdown_count == 1


@pytest.mark.asyncio
async def test_runtime_display_rejects_new_work_after_closing() -> None:
    """closing 标记后不得再向 executor 提交新 display work。

    :returns: ``None``。
    :raises Exception: closing gate 断言失败时由 pytest 抛出。
    """

    controller = RuntimeDisplayController(activity_display=None, thinking_display=None)
    controller.begin_closing()
    with pytest.raises(RuntimeError, match="closing"):
        await controller.finish_runtime_display()
    await controller.aclose()


@pytest.mark.asyncio
async def test_prompt_caller_lifecycle_waits_callback_then_closes_display_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """prompt caller 应按 frozen 顺序关闭 callback、renderer、executor 与本地资源。

    :param monkeypatch: pytest 属性替换夹具。
    :returns: ``None``。
    :raises Exception: lifecycle ordering 断言失败时由 pytest 抛出。
    """

    events: list[str] = []
    callback_started = threading.Event()
    callback_release = threading.Event()
    activity_display = _OrderingActivityDisplay(events)
    controller = _OrderingRuntimeDisplayController(
        activity_display=activity_display,
        events=events,
    )
    original_shutdown = controller._executor.shutdown

    def recording_shutdown(
        wait: bool = True,
        *,
        cancel_futures: bool = False,
    ) -> None:
        """记录 executor shutdown 后调用真实实现。

        :param wait: 是否等待 worker 完成。
        :param cancel_futures: 是否取消尚未执行的 future。
        :returns: ``None``。
        :raises RuntimeError: 真实 executor shutdown 失败时透传。
        """

        events.append("executor_shutdown")
        original_shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(controller._executor, "shutdown", recording_shutdown)

    def blocking_callback(_activity_value: EntrypointActivity) -> None:
        """记录 callback barrier 的起止顺序。

        :param _activity_value: Service activity DTO。
        :returns: ``None``。
        :raises Exception: 本 callback 不主动抛出异常。
        """

        events.append("callback_started")
        callback_started.set()
        callback_release.wait()
        events.append("callback_finished")

    async def service_submit_task() -> EntrypointRunTerminalResult:
        """模拟持有当前 callback job 的 Service submit task。

        :returns: 正常路径不返回 terminal。
        :raises asyncio.CancelledError: caller lifecycle 取消时透传。
        :raises AssertionError: 未被 caller lifecycle 取消时抛出。
        """

        await controller.invoke_activity(blocking_callback, _activity())
        raise AssertionError("caller lifecycle did not cancel Service submit task")

    submit_task = asyncio.create_task(service_submit_task())
    while not callback_started.is_set():
        await asyncio.sleep(0)
    close_task = asyncio.create_task(
        session_execution._close_prompt_lifecycle(
            runtime_display=controller,
            monitor=_OrderingRunningKeyMonitor(events),
            sigint_monitor=_OrderingSigintMonitor(events),
            submit_task=submit_task,
            sigint_task=None,
            key_task=None,
        )
    )
    await _wait_for_recorded_event(events, "close_requested")
    events.append("callback_released")
    callback_release.set()

    cleanup_error = await close_task

    assert cleanup_error is None
    assert events == [
        "callback_started",
        "close_requested",
        "callback_released",
        "callback_finished",
        "activity:guard:off",
        "renderer_close_started",
        "renderer_close_finished",
        "executor_shutdown",
        "caller_local_release:key",
        "caller_local_release:sigint",
    ]
    assert activity_display.close_count == 1


def test_runtime_display_terminal_size_and_row_count_helpers() -> None:
    """终端宽度与显示行数 helper 应处理下限、宽字符和组合字符。

    :returns: ``None``。
    :raises Exception: helper contract 断言失败时由 pytest 抛出。
    """

    assert resolve_terminal_columns(0) == 1
    assert resolve_terminal_columns(12) == 12
    assert terminal_row_count("", columns=0) == 1
    assert terminal_row_count("A你e\u0301", columns=2) == 2


def test_runtime_display_clear_helpers_emit_exact_ansi_sequences() -> None:
    """已完成行与开放行清理 helper 应输出精确 ANSI 序列并处理空操作。

    :returns: ``None``。
    :raises Exception: ANSI sequence 断言失败时由 pytest 抛出。
    """

    completed_stream = io.StringIO()
    clear_completed_rows(completed_stream, row_count=0)
    clear_completed_rows(completed_stream, row_count=2)
    assert completed_stream.getvalue() == "\x1b[1A\r\x1b[2K\x1b[1A\r\x1b[2K"

    open_stream = io.StringIO()
    clear_open_rows(open_stream, row_count=0)
    clear_open_rows(open_stream, row_count=2)
    assert open_stream.getvalue() == "\r\x1b[2K\x1b[1A\r\x1b[2K"


def _activity() -> EntrypointActivity:
    """构造固定测试 activity DTO。

    :returns: 固定 activity DTO。
    :raises Exception: DTO contract 非法时由构造函数抛出。
    """

    return EntrypointActivity(
        kind=EntrypointActivityKind.RUN_LIFECYCLE,
        status=EntrypointActivityStatus.IN_PROGRESS,
        run_id="run-1",
        event_sequence=1,
        dedupe_key="activity-1",
        title="运行中",
        summary=None,
        severity=EntrypointActivitySeverity.INFO,
        tool_name=None,
        tool_display_name=None,
        counts=None,
    )


def _thinking() -> EntrypointThinking:
    """构造固定测试 thinking DTO。

    :returns: 固定 thinking DTO。
    :raises Exception: DTO contract 非法时由构造函数抛出。
    """

    return EntrypointThinking(
        run_id="run-1",
        runtime_id="runtime-1",
        runtime_sequence=1,
        dedupe_key="thinking-1",
        text_delta="分析",
    )


def _terminal_result() -> EntrypointRunTerminalResult:
    """构造 terminal renderer 测试使用的 Service 终态。

    :returns: 固定取消终态。
    :raises Exception: DTO contract 非法时由构造函数抛出。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        session_id="session-1",
        run_id="run-1",
        terminal_event_id="terminal-run-1-2",
        event_sequence=2,
        terminal_status=HostTerminalStatus.CANCELLED,
        dedupe_key="terminal-run-1-2",
        final_answer=None,
        error_message=None,
        cancel_reason="cli_sigint",
        watcher_failure_message=None,
    )


async def _wait_for_recorded_event(events: list[str], expected: str) -> None:
    """等待共享顺序记录出现指定事件。

    :param events: 共享顺序记录。
    :param expected: 待等待的事件。
    :returns: ``None``。
    :raises AssertionError: bounded tick 内未出现事件时抛出。
    """

    for _attempt in range(1_000):
        if expected in events:
            return
        await asyncio.sleep(0)
    raise AssertionError(f"event was not recorded: {expected}")
