"""Host WAITING cancel 与 late result diagnostic 测试。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host import (
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    HostApiError,
    HostApiErrorCode,
    ResolveWaitCompletedOutcome,
    RunStatus,
    cancel_run,
    cancel_session_runs,
    create_host_command_handle,
    resolve_wait,
)
from dayu.host.durable.event_log import EventLogRow
from dayu.host.durable.state import WaitRecordStatus
from tests.host.test_resolve_wait_command import (
    _completed_request,
    _context,
    _events,
    _failed_request,
    _options,
    _read_wait,
    _seed_waiting_run,
)


def test_cancel_run_cancels_waiting_run_without_resume_attempt(
    tmp_path: Path,
) -> None:
    """cancel_run 取消 WAITING Run 和 active wait，不创建 resume Attempt。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        snapshot = cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("cancel-waiting"),
                client_request_id="cancel-waiting",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        event_types = [event.event_type for event in _events(host._transaction_runner())]
        assert snapshot.status is RunStatus.CANCELLED
        assert snapshot.current_attempt_id == seeded.attempt_id
        assert wait_record.status is WaitRecordStatus.CANCELLED
        assert "RESUME_REQUESTED" not in event_types
        assert "ATTEMPT_STARTED" not in event_types[-2:]
    finally:
        host.close()


def test_cancel_session_runs_cancels_waiting_run(
    tmp_path: Path,
) -> None:
    """cancel_session_runs 复用 WAITING cancel transition。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        snapshot = cancel_session_runs(
            host,
            seeded.session_id,
            CancelSessionRunsRequest(
                context=_context("cancel-session-waiting"),
                client_request_id="cancel-session-waiting",
                reason="user_cancel_all",
                mode=CancelMode.GRACEFUL,
            ),
        )

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert snapshot.active_run_id is None
        assert snapshot.queued_run_ids == ()
        assert wait_record.status is WaitRecordStatus.CANCELLED
    finally:
        host.close()


def test_late_result_after_cancel_writes_bounded_diagnostic(
    tmp_path: Path,
) -> None:
    """取消后的 late result 只写 diagnostic，重复不追加，冲突不追加。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("cancel-before-late"),
                client_request_id="cancel-before-late",
                reason="user_cancel",
                mode=CancelMode.GRACEFUL,
            ),
        )
        request = _completed_request("late-result")

        with pytest.raises(HostApiError) as first_error:
            resolve_wait(host, seeded.wait_id, request)
        after_first = _events(host._transaction_runner())
        with pytest.raises(HostApiError) as replay_error:
            resolve_wait(host, seeded.wait_id, request)
        after_replay = _events(host._transaction_runner())
        conflict = replace(
            request,
            outcome=ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(ok=True, value={"answer": "changed"}, meta=None),
                payload_ref=None,
            ),
        )
        with pytest.raises(HostApiError) as conflict_error:
            resolve_wait(host, seeded.wait_id, conflict)

        diagnostics = _events_by_type(after_first, "WAIT_LATE_RESULT_REJECTED")
        assert first_error.value.code is HostApiErrorCode.INVALID_STATE
        assert replay_error.value.code is HostApiErrorCode.INVALID_STATE
        assert conflict_error.value.code is HostApiErrorCode.IDEMPOTENCY_CONFLICT
        assert len(diagnostics) == 1
        assert diagnostics[0].reason_json == '{"reason_code":"wait_cancelled"}'
        assert after_replay == after_first
        assert _events(host._transaction_runner()) == after_first
    finally:
        host.close()


def test_different_key_after_resolved_or_failed_does_not_write_late_diagnostic(
    tmp_path: Path,
) -> None:
    """resolved / failed 终态不同 key 请求只拒绝，不写 late diagnostic。"""

    resolved_host = create_host_command_handle(_options(tmp_path / "resolved"))
    failed_host = create_host_command_handle(_options(tmp_path / "failed"))
    try:
        resolved_seeded = _seed_waiting_run(resolved_host)
        failed_seeded = _seed_waiting_run(failed_host)
        resolve_wait(
            resolved_host,
            resolved_seeded.wait_id,
            _completed_request("resolve-original"),
        )
        resolve_wait(
            failed_host,
            failed_seeded.wait_id,
            _failed_request("failed-original"),
        )
        resolved_before = _events(resolved_host._transaction_runner())
        failed_before = _events(failed_host._transaction_runner())

        with pytest.raises(HostApiError) as resolved_error:
            resolve_wait(
                resolved_host,
                resolved_seeded.wait_id,
                _completed_request("resolve-other-key"),
            )
        with pytest.raises(HostApiError) as failed_error:
            resolve_wait(
                failed_host,
                failed_seeded.wait_id,
                _failed_request("failed-other-key"),
            )

        assert resolved_error.value.code is HostApiErrorCode.INVALID_STATE
        assert failed_error.value.code is HostApiErrorCode.INVALID_STATE
        assert _events(resolved_host._transaction_runner()) == resolved_before
        assert _events(failed_host._transaction_runner()) == failed_before
    finally:
        resolved_host.close()
        failed_host.close()


def _events_by_type(
    events: tuple[EventLogRow, ...], event_type: str
) -> tuple[EventLogRow, ...]:
    """按 event type 过滤事件。

    :param events: EventLog rows。
    :param event_type: 目标 event type。
    :returns: 匹配事件元组。
    """

    return tuple(event for event in events if event.event_type == event_type)
