"""P10.5 Slice 4 public HostEvent contract 测试。"""

from __future__ import annotations

import dayu.host as host
import pytest

from dayu.host import (
    HostActivityCounts,
    HostActivityKind,
    HostActivitySeverity,
    HostActivityStatus,
    HostActivityView,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostFinalAnswerView,
)
from dayu.host.api import HostTerminalStatus


def test_internal_event_view_and_run_stream_are_not_host_root_exports() -> None:
    """包根不导出 run-level diagnostic stream 与 HostEventView。"""

    assert "HostEventView" not in vars(host)
    assert "HostEventStream" not in vars(host)
    assert "stream_run_events" not in vars(host)
    assert not hasattr(host, "HostEventView")
    assert not hasattr(host, "HostEventStream")
    assert not hasattr(host, "stream_run_events")


def test_succeeded_event_requires_inline_final_answer_view() -> None:
    """SUCCEEDED terminal HostEvent 必须内联 HostFinalAnswerView。"""

    final_answer = HostFinalAnswerView(
        content="answer",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )
    event = HostEvent(
        event_id="event-1",
        event_sequence=1,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.CANONICAL_FACT,
        event_type="RUN_SUCCEEDED",
        kind=HostEventKind.SUCCEEDED,
        activity=None,
        dedupe_key="event-1",
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=final_answer,
        error_message=None,
        cancel_reason=None,
    )

    assert event.final_answer is final_answer

    with pytest.raises(ValueError, match="requires final_answer"):
        HostEvent(
            event_id="event-2",
            event_sequence=2,
            session_id="session-1",
            run_id="run-1",
            event_class=HostEventClass.CANONICAL_FACT,
            event_type="RUN_SUCCEEDED",
            kind=HostEventKind.SUCCEEDED,
            activity=None,
            dedupe_key="event-2",
            terminal_status=HostTerminalStatus.SUCCEEDED,
            final_answer=None,
            error_message=None,
            cancel_reason=None,
        )


def test_activity_counts_require_non_negative_ints() -> None:
    """HostActivityCounts 只接受非负严格整数。"""

    counts = HostActivityCounts(total=3, completed=2, failed=1, cancelled=0)

    assert counts.total == 3
    with pytest.raises(TypeError, match="must be int"):
        HostActivityCounts(
            total=True,
            completed=0,
            failed=0,
            cancelled=0,
        )
    with pytest.raises(ValueError, match="must be non-negative"):
        HostActivityCounts(
            total=1,
            completed=-1,
            failed=0,
            cancelled=0,
        )


def test_progress_event_can_carry_safe_activity_without_terminal_payload() -> None:
    """PROGRESS HostEvent 可携带安全 activity，但仍不能携带 terminal payload。"""

    activity = HostActivityView(
        kind=HostActivityKind.TOOL_CALL,
        status=HostActivityStatus.STARTED,
        title="调用工具：查财报",
        summary="参数字段数：1",
        severity=HostActivitySeverity.INFO,
        tool_name="lookup_filing",
        tool_display_name="查财报",
        counts=None,
    )
    event = HostEvent(
        event_id="event-progress",
        event_sequence=7,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.PREVIEW,
        event_type="TOOL_CALL_REQUESTED",
        kind=HostEventKind.PROGRESS,
        activity=activity,
        dedupe_key="event-progress",
        terminal_status=None,
        final_answer=None,
        error_message=None,
        cancel_reason=None,
    )

    assert event.activity is activity
    with pytest.raises(ValueError, match="progress kind"):
        HostEvent(
            event_id="event-progress-terminal",
            event_sequence=8,
            session_id="session-1",
            run_id="run-1",
            event_class=HostEventClass.PREVIEW,
            event_type="TOOL_CALL_REQUESTED",
            kind=HostEventKind.PROGRESS,
            activity=activity,
            dedupe_key="event-progress-terminal",
            terminal_status=HostTerminalStatus.FAILED,
            final_answer=None,
            error_message=None,
            cancel_reason=None,
        )


def test_failed_and_cancelled_events_reject_final_answer_payload() -> None:
    """FAILED / CANCELLED terminal HostEvent 不携带 final answer。"""

    final_answer = HostFinalAnswerView(
        content="answer",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )

    with pytest.raises(ValueError, match="must not include final_answer"):
        HostEvent(
            event_id="event-failed",
            event_sequence=3,
            session_id="session-1",
            run_id="run-1",
            event_class=HostEventClass.CANONICAL_FACT,
            event_type="RUN_FAILED",
            kind=HostEventKind.FAILED,
            activity=None,
            dedupe_key="event-failed",
            terminal_status=HostTerminalStatus.FAILED,
            final_answer=final_answer,
            error_message="provider failed safely",
            cancel_reason=None,
        )

    with pytest.raises(ValueError, match="must not include final_answer"):
        HostEvent(
            event_id="event-cancelled",
            event_sequence=4,
            session_id="session-1",
            run_id="run-1",
            event_class=HostEventClass.CANONICAL_FACT,
            event_type="RUN_CANCELLED",
            kind=HostEventKind.CANCELLED,
            activity=None,
            dedupe_key="event-cancelled",
            terminal_status=HostTerminalStatus.CANCELLED,
            final_answer=final_answer,
            error_message=None,
            cancel_reason="user_stop",
        )


def test_lost_event_rejects_final_answer_payload() -> None:
    """LOST terminal HostEvent 不携带 final answer。"""

    final_answer = HostFinalAnswerView(
        content="answer",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )
    event = HostEvent(
        event_id="event-lost",
        event_sequence=5,
        session_id="session-1",
        run_id="run-1",
        event_class=HostEventClass.CANONICAL_FACT,
        event_type="RUN_LOST",
        kind=HostEventKind.LOST,
        activity=None,
        dedupe_key="event-lost",
        terminal_status=HostTerminalStatus.LOST,
        final_answer=None,
        error_message="worker lost",
        cancel_reason=None,
    )

    assert event.terminal_status is HostTerminalStatus.LOST

    with pytest.raises(ValueError, match="must not include final_answer"):
        HostEvent(
            event_id="event-lost-with-answer",
            event_sequence=6,
            session_id="session-1",
            run_id="run-1",
            event_class=HostEventClass.CANONICAL_FACT,
            event_type="RUN_LOST",
            kind=HostEventKind.LOST,
            activity=None,
            dedupe_key="event-lost-with-answer",
            terminal_status=HostTerminalStatus.LOST,
            final_answer=final_answer,
            error_message="worker lost",
            cancel_reason=None,
        )
