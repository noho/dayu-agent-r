"""Host WAITING cancel 与 late result diagnostic 测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    resolve_wait,
)
from dayu.host.command import create_host_command_handle
from dayu.host.admission import create_host_admission_service
from dayu.host.durable.event_log import EventLogRow
from dayu.host.durable.schema import TABLE_HOST_WAIT_RECORDS
from dayu.host.durable.state import WaitRecordStatus
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.projection import ProjectionCatchupPort
from tests.host.test_resolve_wait_command import (
    _completed_request,
    _context,
    _events,
    _failed_request,
    _options,
    _read_wait,
    _seed_waiting_run,
)

_ATTEMPT_COUNT_SQL = "SELECT COUNT(*) AS total FROM host_attempts"


@dataclass(slots=True)
class _CountingProjectionCatchup(ProjectionCatchupPort):
    """测试用 projection catch-up 调用计数器。"""

    calls: int = 0

    def catch_up_projection(self) -> None:
        """记录 catch-up 调用次数。

        :returns: ``None``。
        """

        self.calls += 1


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


def test_cancel_run_allows_resolved_wait_record_while_run_still_waiting(
    tmp_path: Path,
) -> None:
    """wait record 已 resolved 但 Run 仍 WAITING 时，cancel_run 仍可取消 Run。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        _mark_wait_record_resolved_without_resume(
            host._transaction_runner(), seeded.wait_id
        )

        snapshot = cancel_run(
            host,
            seeded.run_id,
            CancelRunRequest(
                context=_context("cancel-waiting-resolved-record"),
                client_request_id="cancel-waiting-resolved-record",
                reason="user_cancel_after_resolve",
                mode=CancelMode.GRACEFUL,
            ),
        )

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert snapshot.status is RunStatus.CANCELLED
        assert wait_record.status is WaitRecordStatus.RESOLVED
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
        event_types = [event.event_type for event in _events(host._transaction_runner())]
        assert snapshot.active_run_id is None
        assert snapshot.queued_run_ids == ()
        assert wait_record.status is WaitRecordStatus.CANCELLED
        assert "RUN_CANCELLED" in event_types
    finally:
        host.close()


def test_late_result_after_cancel_writes_bounded_diagnostic(
    tmp_path: Path,
) -> None:
    """取消后的 late result 只写 diagnostic，重复不追加，冲突不追加。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    host = create_host_command_handle(_options(tmp_path))
    projection = _CountingProjectionCatchup()
    host._admission_service = create_host_admission_service(
        host._transaction_runner(),
        terminal_post_commit_port=host._terminal_post_commit_port,
        projection_catchup_port=projection,
    )
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
        attempt_count_before_late = _attempt_count(host._transaction_runner())
        events_before_late = _events(host._transaction_runner())

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
        assert projection.calls == 2
        assert _attempt_count(host._transaction_runner()) == attempt_count_before_late
        late_event_types = [
            event.event_type for event in after_first[len(events_before_late) :]
        ]
        assert "RESUME_REQUESTED" not in late_event_types
        assert "ATTEMPT_STARTED" not in late_event_types
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


def _mark_wait_record_resolved_without_resume(
    transaction_runner: HostTransactionRunner, wait_id: str
) -> None:
    """只把 wait record 标记为 RESOLVED，不推进 Run resume。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait record id。
    :returns: ``None``。
    """

    wait_record = _read_wait(transaction_runner, wait_id)

    def operation(transaction: HostTransaction) -> None:
        """执行测试专用 wait record 状态更新。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_WAIT_RECORDS}
            SET status = ?,
                resolve_idempotency_key = ?,
                resolve_semantic_digest = ?,
                updated_event_id = ?,
                updated_event_sequence = ?,
                updated_at = ?,
                terminal_at = ?
            WHERE wait_id = ?
            """,
            (
                WaitRecordStatus.RESOLVED.value,
                "resolve-without-resume",
                "sha256:" + "3" * 64,
                wait_record.created_event_id,
                wait_record.created_event_sequence,
                wait_record.updated_at,
                wait_record.updated_at,
                wait_id,
            ),
        )

    transaction_runner.run_write(operation)


def _attempt_count(transaction_runner: HostTransactionRunner) -> int:
    """统计当前 durable store 中的 Attempt 行数。

    :param transaction_runner: Host transaction runner。
    :returns: Attempt row count。
    """

    def operation(transaction: HostTransaction) -> int:
        """读取 Attempt 行数。

        :param transaction: Host transaction。
        :returns: Attempt row count。
        """

        row = transaction.fetchone(_ATTEMPT_COUNT_SQL)
        assert row is not None
        total = row.get("total")
        assert isinstance(total, int)
        return total

    return transaction_runner.run_read(operation)
