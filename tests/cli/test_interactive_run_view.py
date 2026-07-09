"""interactive run view 测试。"""

from __future__ import annotations

import io

from dayu.cli.exit_codes import EXIT_SUCCESS
from dayu.cli.run_view import (
    InteractiveRunViewMode,
    InteractiveRunViewOptions,
    TerminalInteractiveRunView,
)
from dayu.host.api import HostFinalAnswerView, HostTerminalStatus
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityCounts,
    EntrypointActivityKind,
    EntrypointActivitySeverity,
    EntrypointActivityStatus,
    EntrypointRunTerminalResult,
    EntrypointTerminalSource,
)


def test_run_view_records_activity_without_transcript_output() -> None:
    """默认 transcript view 下 activity 只进入 activity buffer。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )

    view.activity_sink().record_activity(_activity())

    assert view.activity_lines == (
        "Activity: completed 工具批次完成 tool=记录烟测事实 total=1 completed=1 failed=0 cancelled=0",
    )
    assert view.transcript_lines == ()
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_run_view_deduplicates_and_filters_out_of_order_activity() -> None:
    """run view 应过滤重复 dedupe key 和乱序 activity。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )

    view.activity_sink().record_activity(_activity(dedupe_key="activity-1", event_sequence=2))
    view.activity_sink().record_activity(_activity(dedupe_key="activity-1", event_sequence=3))
    view.activity_sink().record_activity(_activity(dedupe_key="activity-0", event_sequence=1))
    view.activity_sink().record_activity(_activity(dedupe_key="activity-3", event_sequence=3))

    assert len(view.activity_lines) == 2
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""


def test_run_view_renders_terminal_result_to_transcript() -> None:
    """terminal success 应写 stdout 并进入 transcript buffer。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )

    exit_code = view.render_terminal_result(_terminal_answer("answer"))

    assert exit_code == EXIT_SUCCESS
    assert stdout.getvalue() == "answer\n"
    assert stderr.getvalue() == ""
    assert view.transcript_lines == ("answer",)


def test_run_view_toggle_switches_activity_and_transcript_snapshots() -> None:
    """Ctrl+T 语义应在 activity/transcript view 间切换且不输出旧 hidden 文本。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )
    view.activity_sink().record_activity(_activity())
    view.render_terminal_result(_terminal_answer("answer"))

    view.toggle_view()
    view.toggle_view()

    assert view.mode is InteractiveRunViewMode.TRANSCRIPT
    stderr_text = stderr.getvalue()
    assert "[Interactive activity]" in stderr_text
    assert "[Interactive transcript]" in stderr_text
    assert "Activity: completed 工具批次完成" in stderr_text
    assert "answer" in stderr_text
    assert "Activity hidden" not in stderr_text


def test_run_view_activity_mode_outputs_terminal_and_returns_to_default_mode() -> None:
    """terminal result 应输出 final answer 并回到配置默认 mode。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(enabled=True),
    )

    view.toggle_view()
    exit_code = view.render_terminal_result(_terminal_answer("answer"))

    assert exit_code == EXIT_SUCCESS
    assert stdout.getvalue() == "answer\n"
    assert view.mode is InteractiveRunViewMode.TRANSCRIPT
    assert view.transcript_lines == ("answer",)
    assert "answer" not in stderr.getvalue()


def test_run_view_detail_mode_keeps_activity_after_terminal_result() -> None:
    """detail 初始 activity mode 不应在一轮结束后静默降级。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(
            enabled=True,
            initial_mode=InteractiveRunViewMode.ACTIVITY,
        ),
    )

    exit_code = view.render_terminal_result(_terminal_answer("answer"))
    view.activity_sink().record_activity(_activity(dedupe_key="activity-next"))

    assert exit_code == EXIT_SUCCESS
    assert view.mode is InteractiveRunViewMode.ACTIVITY
    assert stdout.getvalue() == "answer\n"
    assert "Activity: completed 工具批次完成" in stderr.getvalue()


def test_run_view_can_start_in_activity_mode() -> None:
    """CLI detail display 可让 run view 初始处于 activity mode。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(
            enabled=True,
            initial_mode=InteractiveRunViewMode.ACTIVITY,
        ),
    )

    view.activity_sink().record_activity(_activity())

    assert view.mode is InteractiveRunViewMode.ACTIVITY
    assert "Activity: completed 工具批次完成" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_run_view_finish_non_tty_keeps_readable_activity_snapshot() -> None:
    """非 TTY 收尾应保留可读 activity view 输出。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(
            enabled=True,
            initial_mode=InteractiveRunViewMode.ACTIVITY,
        ),
    )

    view.activity_sink().record_activity(_activity())
    view.finish_runtime_display()

    assert "Activity: completed 工具批次完成" in stderr.getvalue()
    assert "\x1b[" not in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_run_view_finish_tty_clears_rendered_activity_lines() -> None:
    """TTY 收尾应清除当前 activity view 输出。"""

    stdout = io.StringIO()
    stderr = io.StringIO()
    view = TerminalInteractiveRunView(
        stdout=stdout,
        stderr=stderr,
        options=InteractiveRunViewOptions(
            enabled=True,
            initial_mode=InteractiveRunViewMode.ACTIVITY,
            terminal_control=True,
            terminal_columns=1000,
        ),
    )

    view.activity_sink().record_activity(_activity())
    view.finish_runtime_display()

    assert stderr.getvalue().endswith("\x1b[1A\r\x1b[2K")
    assert stdout.getvalue() == ""


def _activity(
    *,
    dedupe_key: str = "activity-1",
    event_sequence: int = 1,
) -> EntrypointActivity:
    """构造测试 activity。

    :param dedupe_key: activity dedupe key。
    :param event_sequence: Host event sequence。
    :returns: Service activity DTO。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointActivity(
        kind=EntrypointActivityKind.TOOL_BATCH,
        status=EntrypointActivityStatus.COMPLETED,
        run_id="run-1",
        event_sequence=event_sequence,
        dedupe_key=dedupe_key,
        title="工具批次完成",
        summary=None,
        severity=EntrypointActivitySeverity.INFO,
        tool_name="record_fact",
        tool_display_name="记录烟测事实",
        counts=EntrypointActivityCounts(total=1, completed=1, failed=0, cancelled=0),
    )


def _terminal_answer(content: str) -> EntrypointRunTerminalResult:
    """构造成功 terminal result。

    :param content: final answer 文本。
    :returns: Service terminal result DTO。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        run_id="run-1",
        session_id="session-1",
        event_sequence=2,
        dedupe_key="terminal-1",
        terminal_event_id="terminal-1",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=HostFinalAnswerView(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason="stop",
            terminal_status=HostTerminalStatus.SUCCEEDED,
        ),
        error_message=None,
        cancel_reason=None,
        watcher_failure_message=None,
    )
