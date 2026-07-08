"""CLI 运行态显示 controller 测试。"""

from __future__ import annotations

from collections.abc import Callable

from dayu.cli.runtime_display import RuntimeDisplayController


class _FakeActivityDisplay:
    """记录 activity-like display 调用顺序的测试替身。"""

    events: list[str]
    _guard: Callable[[], None] | None

    def __init__(self, events: list[str]) -> None:
        """初始化测试替身。

        :param events: 共享事件记录列表。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events = events
        self._guard = None

    def set_runtime_line_guard(self, guard: Callable[[], None] | None) -> None:
        """记录 guard 安装或移除。

        :param guard: 输出运行态行前执行的回调；``None`` 表示不执行。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._guard = guard
        self.events.append(
            "activity:set-guard:on" if guard is not None else "activity:set-guard:off"
        )

    def emit_runtime_line(self) -> None:
        """模拟 activity-like display 输出一条运行态行。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._guard is not None:
            self._guard()
        self.events.append("activity:line")

    def finish_runtime_display(self) -> None:
        """记录 activity-like display 收尾。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:finish")

    def render_cancel_requested(self) -> None:
        """记录取消请求提示。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:cancel")

    def render_local_exit_after_cancel(self) -> None:
        """记录二次中断本地退出提示。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:local-exit")

    def close(self) -> None:
        """记录 activity-like display 关闭。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("activity:close")


class _FakeThinkingDisplay:
    """记录 thinking display 调用顺序的测试替身。"""

    events: list[str]

    def __init__(self, events: list[str]) -> None:
        """初始化测试替身。

        :param events: 共享事件记录列表。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events = events

    def finish_runtime_display(self) -> None:
        """记录 thinking display 收尾。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("thinking:finish")

    def close(self) -> None:
        """记录 thinking display 关闭。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.events.append("thinking:close")


def test_runtime_display_controller_installs_thinking_guard_for_activity_line() -> None:
    """controller 应让 activity-like 输出前先清理 thinking 行。"""

    events: list[str] = []
    activity = _FakeActivityDisplay(events)
    thinking = _FakeThinkingDisplay(events)
    controller = RuntimeDisplayController(
        activity_display=activity,
        thinking_display=thinking,
    )

    controller.install_runtime_line_guard()
    activity.emit_runtime_line()
    controller.clear_runtime_line_guard()

    assert events == [
        "activity:set-guard:on",
        "thinking:finish",
        "activity:line",
        "activity:set-guard:off",
    ]


def test_runtime_display_controller_finishes_thinking_before_activity_for_terminal() -> None:
    """terminal 输出前 controller 应先收 thinking，再收 activity-like display。"""

    events: list[str] = []
    controller = RuntimeDisplayController(
        activity_display=_FakeActivityDisplay(events),
        thinking_display=_FakeThinkingDisplay(events),
    )

    controller.finish_runtime_display()

    assert events == ["thinking:finish", "activity:finish"]


def test_runtime_display_controller_cancel_cleanup_is_centralized_and_idempotent() -> None:
    """取消路径 controller 应集中处理 thinking 关闭与 activity-like 提示。"""

    events: list[str] = []
    controller = RuntimeDisplayController(
        activity_display=_FakeActivityDisplay(events),
        thinking_display=_FakeThinkingDisplay(events),
    )

    controller.finish_and_close_thinking()
    controller.render_cancel_requested()
    controller.close_thinking()

    assert events == [
        "thinking:finish",
        "thinking:close",
        "activity:set-guard:off",
        "activity:cancel",
    ]


def test_runtime_display_controller_clears_guard_after_closing_thinking() -> None:
    """controller 关闭 thinking 后应移除 activity-like display guard。"""

    events: list[str] = []
    activity = _FakeActivityDisplay(events)
    controller = RuntimeDisplayController(
        activity_display=activity,
        thinking_display=_FakeThinkingDisplay(events),
    )

    controller.install_runtime_line_guard()
    controller.finish_and_close_thinking()
    activity.emit_runtime_line()

    assert events == [
        "activity:set-guard:on",
        "thinking:finish",
        "thinking:close",
        "activity:set-guard:off",
        "activity:line",
    ]


def test_runtime_display_controller_cleans_thinking_before_local_exit_prompt() -> None:
    """二次中断本地退出提示前应先清理未关闭的 thinking 展示。"""

    events: list[str] = []
    controller = RuntimeDisplayController(
        activity_display=_FakeActivityDisplay(events),
        thinking_display=_FakeThinkingDisplay(events),
    )

    controller.render_local_exit_after_cancel()

    assert events == ["thinking:finish", "activity:local-exit"]


def test_runtime_display_controller_closes_all_managed_displays() -> None:
    """controller close 应统一关闭 thinking 与 activity-like display。"""

    events: list[str] = []
    controller = RuntimeDisplayController(
        activity_display=_FakeActivityDisplay(events),
        thinking_display=_FakeThinkingDisplay(events),
    )

    controller.install_runtime_line_guard()
    controller.close()
    controller.render_cancel_requested()
    controller.close()

    assert events == [
        "activity:set-guard:on",
        "thinking:close",
        "activity:set-guard:off",
        "activity:set-guard:off",
        "activity:close",
    ]


def test_runtime_display_controller_handles_missing_activity_display() -> None:
    """activity display 缺失时 controller 应只处理 thinking display。"""

    events: list[str] = []
    controller = RuntimeDisplayController(
        activity_display=None,
        thinking_display=_FakeThinkingDisplay(events),
    )

    controller.install_runtime_line_guard()
    controller.finish_runtime_display()
    controller.finish_and_close_thinking()
    controller.render_cancel_requested()
    controller.render_local_exit_after_cancel()
    controller.close()

    assert events == ["thinking:finish", "thinking:finish", "thinking:close"]


def test_runtime_display_controller_handles_missing_thinking_display() -> None:
    """thinking display 缺失时 controller 应只处理 activity-like display。"""

    events: list[str] = []
    controller = RuntimeDisplayController(
        activity_display=_FakeActivityDisplay(events),
        thinking_display=None,
    )

    controller.install_runtime_line_guard()
    controller.finish_runtime_display()
    controller.finish_and_close_thinking()
    controller.render_cancel_requested()
    controller.render_local_exit_after_cancel()
    controller.close()

    assert events == [
        "activity:set-guard:off",
        "activity:finish",
        "activity:cancel",
        "activity:local-exit",
        "activity:set-guard:off",
        "activity:close",
    ]


def test_runtime_display_controller_handles_missing_displays() -> None:
    """activity 与 thinking 都缺失时 controller 所有方法应为 no-op。"""

    controller = RuntimeDisplayController(
        activity_display=None,
        thinking_display=None,
    )

    controller.install_runtime_line_guard()
    controller.finish_runtime_display()
    controller.finish_and_close_thinking()
    controller.render_cancel_requested()
    controller.render_local_exit_after_cancel()
    controller.close()
