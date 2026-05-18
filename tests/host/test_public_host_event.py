"""P10.5 Slice 4 public HostEvent contract 测试。"""

from __future__ import annotations

import dayu.host as host
import pytest

from dayu.host import HostEvent, HostEventKind, HostFinalAnswerView
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
        kind=HostEventKind.SUCCEEDED,
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
            kind=HostEventKind.SUCCEEDED,
            dedupe_key="event-2",
            terminal_status=HostTerminalStatus.SUCCEEDED,
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
            kind=HostEventKind.FAILED,
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
            kind=HostEventKind.CANCELLED,
            dedupe_key="event-cancelled",
            terminal_status=HostTerminalStatus.CANCELLED,
            final_answer=final_answer,
            error_message=None,
            cancel_reason="user_stop",
        )
