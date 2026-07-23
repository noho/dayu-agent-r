"""CLI activity renderer 测试。"""

from __future__ import annotations

from io import StringIO

from dayu.cli.activity import CliActivityRenderer, CliActivityRendererOptions
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityCounts,
    EntrypointActivityKind,
    EntrypointActivitySeverity,
    EntrypointActivityStatus,
    EntrypointContextEstimateMethod,
    EntrypointContextPressureLevel,
    EntrypointContextUsage,
)


def test_activity_renderer_outputs_visible_activity_to_stderr() -> None:
    """visible renderer 应输出单行 activity。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=True),
    )

    renderer.record(_activity(dedupe_key="activity-1", event_sequence=1))

    output = stderr.getvalue()
    assert "Activity:" in output
    assert "completed" in output
    assert "工具批次完成" in output
    assert "tool=记录烟测事实" in output


def test_activity_renderer_deduplicates_and_ignores_older_sequences() -> None:
    """renderer 应按 dedupe key 去重并忽略旧 sequence。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=True),
    )

    renderer.record(_activity(dedupe_key="activity-1", event_sequence=2))
    renderer.record(_activity(dedupe_key="activity-1", event_sequence=3))
    renderer.record(_activity(dedupe_key="activity-old", event_sequence=1))

    assert stderr.getvalue().count("Activity:") == 1


def test_activity_renderer_suppresses_when_disabled() -> None:
    """disabled renderer 不应输出 live activity。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=False),
    )

    renderer.record(_activity(dedupe_key="activity-1", event_sequence=1))

    assert stderr.getvalue() == ""


def test_activity_renderer_hidden_keeps_terminal_area_clean() -> None:
    """hidden renderer 不输出 activity，重新可见后只输出新 activity。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=False, enabled=True),
    )

    renderer.record(_activity(dedupe_key="activity-hidden", event_sequence=1))
    renderer.toggle_runtime_display()
    renderer.record(_activity(dedupe_key="activity-visible", event_sequence=2))

    output = stderr.getvalue()
    assert "activity-hidden" not in output
    assert output.count("Activity:") == 1
    assert "工具批次完成" in output


def test_activity_renderer_toggle_hidden_reports_latest_visible_activity() -> None:
    """可见 activity 后切到 hidden 应展示最新 activity 标题。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=True),
    )

    renderer.record(_activity(dedupe_key="activity-visible", event_sequence=1))
    renderer.toggle_runtime_display()

    output = stderr.getvalue()
    assert "Activity:" in output
    assert "Activity hidden: 工具批次完成" in output


def test_activity_renderer_cancel_messages() -> None:
    """renderer 应输出取消请求和本地退出提示。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=True),
    )

    renderer.render_cancel_requested()
    renderer.render_local_exit_after_cancel()

    output = stderr.getvalue()
    assert "cancel requested" in output
    assert "local process exiting" in output


def test_activity_renderer_finish_non_tty_keeps_readable_activity() -> None:
    """非 TTY 收尾应保留可读 activity 且不输出 ANSI 控制符。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=True),
    )

    renderer.record(_activity(dedupe_key="activity-1", event_sequence=1))
    renderer.finish_runtime_display()

    output = stderr.getvalue()
    assert "Activity:" in output
    assert "工具批次完成" in output
    assert "\x1b[" not in output


def test_activity_renderer_finish_tty_clears_rendered_activity_lines() -> None:
    """TTY 收尾应清除已输出的 activity 行。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(
            visible=True,
            enabled=True,
            terminal_control=True,
            terminal_columns=1000,
        ),
    )

    renderer.record(_activity(dedupe_key="activity-1", event_sequence=1))
    renderer.finish_runtime_display()

    output = stderr.getvalue()
    assert "Activity:" in output
    assert output.endswith("\x1b[1A\r\x1b[2K")


def test_activity_renderer_accepts_typed_context_usage_activity() -> None:
    """renderer 应直接展示 typed context usage activity 标题。"""

    stderr = StringIO()
    renderer = CliActivityRenderer(
        stderr=stderr,
        options=CliActivityRendererOptions(visible=True, enabled=True),
    )

    renderer.record(_context_usage_activity())

    output = stderr.getvalue()
    assert "Activity:" in output
    assert "上下文预算已评估" in output
    assert "tool=" not in output


def _activity(*, dedupe_key: str, event_sequence: int) -> EntrypointActivity:
    """构造测试 activity。

    :param dedupe_key: activity dedupe key。
    :param event_sequence: Host event sequence。
    :returns: Service entrypoint activity。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointActivity(
        kind=EntrypointActivityKind.TOOL_BATCH,
        status=EntrypointActivityStatus.COMPLETED,
        run_id="run-1",
        event_sequence=event_sequence,
        dedupe_key=dedupe_key,
        title="工具批次完成",
        summary="完成 1 个工具调用。",
        severity=EntrypointActivitySeverity.INFO,
        tool_name="record_smoke_fact",
        tool_display_name="记录烟测事实",
        counts=EntrypointActivityCounts(total=1, completed=1, failed=0, cancelled=0),
    )


def _context_usage_activity() -> EntrypointActivity:
    """构造 typed context usage activity。

    :returns: Service entrypoint context usage activity。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointActivity(
        kind=EntrypointActivityKind.CONTEXT_USAGE,
        status=EntrypointActivityStatus.INFO,
        run_id="run-1",
        event_sequence=2,
        dedupe_key="context-budget-fact",
        title="上下文预算已评估",
        summary=None,
        severity=EntrypointActivitySeverity.INFO,
        tool_name=None,
        tool_display_name=None,
        counts=None,
        context_usage=EntrypointContextUsage(
            predicted_input_tokens=1_200,
            context_window_size=1_000,
            utilization_basis_points=12_000,
            soft_threshold_tokens=800,
            hard_threshold_tokens=900,
            estimate_method=(
                EntrypointContextEstimateMethod.CONSERVATIVE_FALLBACK
            ),
            pressure_level=(
                EntrypointContextPressureLevel.HARD_THRESHOLD_EXCEEDED
            ),
        ),
    )
