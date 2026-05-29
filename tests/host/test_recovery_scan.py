"""Host startup recovery scan 测试。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    EnsureSessionRequest,
    HostMetadataEntry,
    RunStatus,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventClass, EventLogAppendRequest, EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    CreateAcceptedRunInput,
    CreateQueuedRunInput,
    CreateRunningRunInput,
    create_accepted_run_in_transaction,
    create_queued_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_SESSION_SLOTS,
)
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.recovery import (
    StartupRecoveryDecision,
    StartupRecoveryPolicy,
    StartupRecoveryScanner,
)
from dayu.host.recovery_process import ProcessEvidence

_NOW = datetime(2026, 5, 19, 3, 4, 5, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "recovery-scan-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "hello"})
_REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST = "cancel_in_flight_attempt_lost"
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"


@dataclass(frozen=True, slots=True)
class _PidMissingProbe:
    """测试用 pid missing probe。"""

    def collect(self, pid: int) -> ProcessEvidence:
        """返回 pid 不存在证据。

        :param pid: 目标 pid。
        :returns: pid missing 证据。
        """

        return ProcessEvidence(
            pid=pid,
            exists=False,
            observed_start_token=None,
            observed_boot_id=None,
            probe_error_code=None,
        )


class _RecordingWakeup:
    """记录 startup scan commit 后的 scheduler wakeup。"""

    def __init__(self) -> None:
        """初始化 wakeup 记录器。

        :returns: ``None``。
        """

        self.dispatches: list[PendingDispatchRecord] = []
        self.promoted_sessions: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 dispatch wakeup。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        """

        self.dispatches.append(record)

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        self.promoted_sessions.append(session_id)


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 durable options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def test_scan_running_positive_orphan_moves_to_recovering_without_projection(
    tmp_path: Path,
) -> None:
    """RUNNING positive orphan 基于 durable truth 进入 RECOVERING，不依赖 projection。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _insert_projection_lag_marker(store.transaction_runner)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_RECOVERING,
        )

        def verify(transaction: HostTransaction) -> str:
            """读取 Run 状态。

            :param transaction: Host transaction。
            :returns: Run 状态。
            """

            run = read_run_by_id(transaction, "run-1")
            assert run is not None
            return run.status.value

        assert store.transaction_runner.run_write(verify) == RunStatus.RECOVERING.value


def test_scan_waiting_uses_diagnostic_only_fallback(tmp_path: Path) -> None:
    """WAITING startup scan 不创建 Attempt、不推进状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_run_status(store.transaction_runner, "run-1", RunStatus.WAITING)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.WAITING_DIAGNOSTIC_ONLY,
        )
        assert _count_rows(store.transaction_runner, "host_attempts") == 1
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.WAITING.value


def test_scan_cancelling_positive_orphan_loses_attempt_then_run(
    tmp_path: Path,
) -> None:
    """CANCELLING positive orphan 写 ATTEMPT_LOST 后写 RUN_LOST，不恢复执行。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_run_status(store.transaction_runner, "run-1", RunStatus.CANCELLING)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_LOST,
        )
        assert tuple(action.reason for action in result.actions) == (
            _REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST,
        )

        def verify(
            transaction: HostTransaction,
        ) -> tuple[str, tuple[str, ...], JsonValue]:
            """读取 closeout 后的状态、事件序列与 RUN_LOST reason。

            :param transaction: Host transaction。
            :returns: Run 状态、event type 序列与 RUN_LOST reason。
            """

            run = read_run_by_id(transaction, "run-1")
            assert run is not None
            run_lost_payload = _event_payload_by_type(
                transaction,
                event_type=_EVENT_TYPE_RUN_LOST,
            )
            return (
                run.status.value,
                _event_types(transaction),
                run_lost_payload["reason"],
            )

        run_status, event_types, run_lost_reason = store.transaction_runner.run_write(
            verify
        )
        assert run_status == RunStatus.LOST.value
        assert event_types[-2:] == (_EVENT_TYPE_ATTEMPT_LOST, _EVENT_TYPE_RUN_LOST)
        assert _EVENT_TYPE_RUN_RECOVERING not in event_types
        assert run_lost_reason == _REASON_CANCEL_IN_FLIGHT_ATTEMPT_LOST


def test_scan_accepted_does_not_mutate_or_create_attempt(tmp_path: Path) -> None:
    """ACCEPTED startup classification 不写 recovery fact、不改状态、不建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_unstarted_run(store.transaction_runner, "run-1", RunStatus.ACCEPTED)
        before = _unstarted_scan_observation(store.transaction_runner, "run-1")
        wakeup = _RecordingWakeup()

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
        ).scan(_policy())

        after = _unstarted_scan_observation(store.transaction_runner, "run-1")
        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.ACCEPTED_WAKE,
        )
        assert len(result.queue_promotion_sessions) == 1
        assert wakeup.dispatches == []
        assert wakeup.promoted_sessions == list(result.queue_promotion_sessions)
        assert after == before


def test_scan_queued_does_not_mutate_or_create_attempt(tmp_path: Path) -> None:
    """QUEUED startup classification 不写 recovery fact、不改状态、不建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_unstarted_run(store.transaction_runner, "run-1", RunStatus.QUEUED)
        before = _unstarted_scan_observation(store.transaction_runner, "run-1")
        wakeup = _RecordingWakeup()

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
        ).scan(_policy())

        after = _unstarted_scan_observation(store.transaction_runner, "run-1")
        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.QUEUE_PROMOTION_CHECK,
        )
        assert len(result.queue_promotion_sessions) == 1
        assert wakeup.dispatches == []
        assert wakeup.promoted_sessions == list(result.queue_promotion_sessions)
        assert after == before


def test_scan_recovering_loses_when_eventlog_recovery_limit_reached_despite_projection_lag(
    tmp_path: Path,
) -> None:
    """RECOVERING limit 只看 canonical EventLog，projection lag 不影响 LOST 决策。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
        _mark_run_status(store.transaction_runner, "run-1", RunStatus.RECOVERING)
        _append_recovery_started_event(store.transaction_runner, "run-1")
        _insert_projection_lag_marker(store.transaction_runner)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RUN_LOST,
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.LOST.value


def test_scan_skips_non_terminal_run_when_session_row_is_missing(
    tmp_path: Path,
) -> None:
    """验证 Session row 缺失时 recovery 不根据残留 Run row 创建恢复事实。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: recovery 写入恢复事实或改变残留 Run 状态时由断言抛出。
    """

    options = _options(tmp_path)
    with open_host_durable_store(options) as store:
        _seed_running_dispatching_run(store.transaction_runner, "run-1")
    _delete_session_rows_without_foreign_keys(options.db_path)

    with open_host_durable_store(options) as store:
        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.NOT_FOUND,
        )
        assert tuple(action.reason for action in result.actions) == (
            "session_missing",
        )
        assert _run_status(store.transaction_runner, "run-1") == RunStatus.RUNNING.value
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_ATTEMPT_LOST) == 0
        assert _event_type_count(store.transaction_runner, _EVENT_TYPE_RUN_RECOVERING) == 0


def _policy() -> StartupRecoveryPolicy:
    """构造测试 recovery policy。

    :returns: startup recovery policy。
    """

    return StartupRecoveryPolicy(
        now=_NOW,
        stale_after=timedelta(seconds=30),
        recovery_dispatch_limit=1,
    )


def _delete_session_rows_without_foreign_keys(db_path: Path) -> None:
    """删除 Session row 以模拟 purge/missing Session 的残留 Run 防御场景。

    :param db_path: Host durable SQLite 路径。
    :returns: ``None``。
    :raises sqlite3.Error: SQLite 打开或执行删除语句失败时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(f"DELETE FROM {TABLE_HOST_SESSION_SLOTS}")
        connection.execute(f"DELETE FROM {TABLE_HOST_SESSIONS}")


def _seed_running_dispatching_run(
    transaction_runner: HostTransactionRunner, run_id: str
) -> None:
    """写入 running Run 与 stale owner dispatch record。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: ``None``。
    """

    session_id = _ensure_session_id(transaction_runner)

    def operation(transaction: HostTransaction) -> None:
        """写入测试数据。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        input_event = EventLogStore().append_event(
            transaction,
            _event(
                event_id=f"event-input-{run_id}",
                session_id=session_id,
                run_id=run_id,
                event_type="USER_INPUT_ACCEPTED",
                payload={
                    "input_ref": None,
                    "input_digest": _INPUT_DIGEST,
                    "display_text": "hello",
                    "payload_ref": None,
                    "payload_digest": None,
                    "operation_kind": "start_run",
                    "call_context_digest": _CALL_CONTEXT_DIGEST,
                },
            ),
        ).row
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            _create_running_input(
                session_id=session_id,
                run_id=run_id,
                input_event_sequence=input_event.event_sequence,
            ),
        )
        _insert_stale_host_instance(transaction)
        attempt_id = f"attempt-{run_id}"
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-instance-old",
            lane_name="llm",
            waiting_for_lane_at="2026-05-19T03:03:00.000000Z",
        )
        assert waiting.status is StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-instance-old",
            lane_name="llm",
            lane_claim_id="lane-claim-old",
            lane_owner_id="lane-owner-old",
            lane_acquired_at="2026-05-19T03:03:01.000000Z",
            dispatching_at="2026-05-19T03:03:02.000000Z",
        )
        assert dispatching.status is StateMutationStatus.UPDATED

    transaction_runner.run_write(operation)


def _seed_unstarted_run(
    transaction_runner: HostTransactionRunner, run_id: str, status: RunStatus
) -> None:
    """写入 ACCEPTED 或 QUEUED 测试 Run。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :param status: 目标非启动状态。
    :returns: ``None``。
    :raises AssertionError: status 不是 ACCEPTED 或 QUEUED 时抛出。
    """

    session_id = _ensure_session_id(transaction_runner)

    def operation(transaction: HostTransaction) -> None:
        """写入测试数据。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        input_event = EventLogStore().append_event(
            transaction,
            _event(
                event_id=f"event-input-{run_id}",
                session_id=session_id,
                run_id=run_id,
                event_type="USER_INPUT_ACCEPTED",
                payload={
                    "input_ref": None,
                    "input_digest": _INPUT_DIGEST,
                    "display_text": "hello",
                    "payload_ref": None,
                    "payload_digest": None,
                    "operation_kind": "start_run",
                    "call_context_digest": _CALL_CONTEXT_DIGEST,
                },
            ),
        ).row
        if status is RunStatus.ACCEPTED:
            create_accepted_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_accepted_input(
                    session_id=session_id,
                    run_id=run_id,
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            return
        if status is RunStatus.QUEUED:
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id=run_id,
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            return
        raise AssertionError("status must be ACCEPTED or QUEUED")

    transaction_runner.run_write(operation)


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建测试 Session。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="recovery-scan",
            metadata=(HostMetadataEntry(key="case", value="recovery-scan"),),
        ),
    )
    return result.snapshot.session_id


def _create_accepted_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateAcceptedRunInput:
    """构造 accepted Run 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateAcceptedRunInput。
    """

    return CreateAcceptedRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{run_id}",
        input_event_id=f"event-input-{run_id}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{run_id}",
        execution_target="local-default",
        queue_policy="queue",
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _create_queued_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateQueuedRunInput:
    """构造 queued Run 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateQueuedRunInput。
    """

    return CreateQueuedRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{run_id}",
        input_event_id=f"event-input-{run_id}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{run_id}",
        run_queued_event_id=f"event-run-queued-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{run_id}",
        execution_target="local-default",
        queue_policy="queue",
        queue_reason="active_run_exists",
        active_run_id="run-active",
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _create_running_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateRunningRunInput:
    """构造 running Run 输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateRunningRunInput。
    """

    return CreateRunningRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{run_id}",
        input_event_id=f"event-input-{run_id}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{run_id}",
        run_started_event_id=f"event-run-started-{run_id}",
        attempt_started_event_id=f"event-attempt-started-{run_id}",
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
        dispatch_record_id=f"dispatch-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{run_id}",
        execution_target="local-default",
        queue_policy="queue",
        start_reason=RunStartReason.INITIAL,
        worker_kind=WorkerKind.LOCAL,
        owner_host_instance_id=None,
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _event(
    *,
    event_id: str,
    session_id: str,
    run_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试 EventLog append request。

    :param event_id: event id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: event type。
    :param payload: inline payload。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id=run_id,
        attempt_id=None,
        execution_id=None,
        event_type=event_type,
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        client_request_id="client-request",
        idempotency_key="client-request",
        policy_decision=None,
        reason=None,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _insert_stale_host_instance(transaction: HostTransaction) -> None:
    """写入 stale owner host instance。

    :param transaction: Host transaction。
    :returns: ``None``。
    """

    transaction.execute(
        """
        INSERT INTO host_instances (
          host_instance_id,
          pid,
          process_start_token,
          boot_id,
          created_at,
          heartbeat_at,
          status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "host-instance-old",
            999_999,
            "process-start-token-old",
            None,
            "2026-05-19T03:00:00.000000Z",
            "2026-05-19T03:00:00.000000Z",
            "running",
        ),
    )


def _insert_projection_lag_marker(transaction_runner: HostTransactionRunner) -> None:
    """写入 projection checkpoint lag 标记。

    :param transaction_runner: Host transaction runner。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """写入 checkpoint。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            """
            INSERT OR REPLACE INTO host_projection_checkpoints (
              consumer_id,
              checkpoint_event_sequence,
              checkpoint_event_id,
              last_success_at,
              updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "lagging-test-projection",
                0,
                None,
                None,
                "2026-05-19T03:00:00.000000Z",
            ),
        )

    transaction_runner.run_write(operation)


def _mark_run_status(
    transaction_runner: HostTransactionRunner, run_id: str, status: RunStatus
) -> None:
    """直接设置测试 Run 状态。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :param status: 目标状态。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """更新测试 Run 状态。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            "UPDATE host_runs SET status = ?, updated_at = ? WHERE run_id = ?",
            (status.value, "2026-05-19T03:04:00.000000Z", run_id),
        )

    transaction_runner.run_write(operation)


def _append_recovery_started_event(
    transaction_runner: HostTransactionRunner, run_id: str
) -> None:
    """追加 canonical recovery ``RUN_STARTED`` event。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> None:
        """追加 recovery start 事件。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        session_row = transaction.fetchone(
            "SELECT session_id FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        assert session_row is not None
        EventLogStore().append_event(
            transaction,
            _event(
                event_id=f"event-recovery-started-{run_id}",
                session_id=_required_text(session_row, "session_id"),
                run_id=run_id,
                event_type="RUN_STARTED",
                payload={
                    "run_id": run_id,
                    "start_reason": "recovery",
                    "source_attempt_id": f"attempt-{run_id}",
                    "attempt_id": f"attempt-recovery-{run_id}",
                    "dispatch_record_id": f"dispatch-recovery-{run_id}",
                },
            ),
        )

    transaction_runner.run_write(operation)


def _run_status(transaction_runner: HostTransactionRunner, run_id: str) -> str:
    """读取 Run status。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run status 文本。
    """

    def operation(transaction: HostTransaction) -> str:
        """读取 Run 状态。

        :param transaction: Host transaction。
        :returns: Run status 文本。
        """

        row = transaction.fetchone("SELECT status FROM host_runs WHERE run_id = ?", (run_id,))
        assert row is not None
        return _required_text(row, "status")

    return transaction_runner.run_write(operation)


def _unstarted_scan_observation(
    transaction_runner: HostTransactionRunner, run_id: str
) -> tuple[str, str, int, tuple[str, ...]]:
    """读取 unstarted Run scan 前后应保持不变的观测值。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run 状态、updated_at、Attempt row 数与 EventLog 序列。
    """

    def operation(transaction: HostTransaction) -> tuple[str, str, int, tuple[str, ...]]:
        """读取测试观测值。

        :param transaction: Host transaction。
        :returns: Run 状态、updated_at、Attempt row 数与 EventLog 序列。
        """

        row = transaction.fetchone(
            "SELECT status, updated_at FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        assert row is not None
        return (
            _required_text(row, "status"),
            _required_text(row, "updated_at"),
            _count_rows_in_transaction(transaction, "host_attempts"),
            _event_types(transaction),
        )

    return transaction_runner.run_write(operation)


def _event_types(transaction: HostTransaction) -> tuple[str, ...]:
    """读取全部 EventLog event type。

    :param transaction: Host transaction。
    :returns: event type 序列。
    """

    rows = transaction.fetchall(
        "SELECT event_type FROM event_log ORDER BY event_sequence ASC"
    )
    return tuple(_required_text(row, "event_type") for row in rows)


def _event_type_count(
    transaction_runner: HostTransactionRunner, event_type: str
) -> int:
    """统计指定 EventLog event type 数量。

    :param transaction_runner: Host transaction runner。
    :param event_type: 目标 event type。
    :returns: 匹配 row 数量。
    :raises AssertionError: count 查询未返回 row 或 row 类型不符合预期时抛出。
    """

    def operation(transaction: HostTransaction) -> int:
        """执行 event type 计数。

        :param transaction: Host transaction。
        :returns: 匹配 row 数量。
        :raises AssertionError: count 查询未返回 row 或 row 类型不符合预期时抛出。
        """

        row = transaction.fetchone(
            f"""
            SELECT COUNT(*) AS count
            FROM {TABLE_EVENT_LOG}
            WHERE event_type = ?
            """,
            (event_type,),
        )
        assert row is not None
        return _required_int(row, "count")

    return transaction_runner.run_read(operation)


def _event_payload_by_type(
    transaction: HostTransaction, *, event_type: str
) -> dict[str, JsonValue]:
    """读取指定类型最后一条 EventLog payload。

    :param transaction: Host transaction。
    :param event_type: event type。
    :returns: payload JSON object。
    """

    row = transaction.fetchone(
        """
        SELECT payload_json
        FROM event_log
        WHERE event_type = ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (event_type,),
    )
    assert row is not None
    payload = json.loads(_required_text(row, "payload_json"))
    assert isinstance(payload, dict)
    return cast(dict[str, JsonValue], payload)


def _count_rows(transaction_runner: HostTransactionRunner, table_name: str) -> int:
    """统计表行数。

    :param transaction_runner: Host transaction runner。
    :param table_name: 表名。
    :returns: 行数。
    """

    def operation(transaction: HostTransaction) -> int:
        """执行统计。

        :param transaction: Host transaction。
        :returns: 行数。
        """

        return _count_rows_in_transaction(transaction, table_name)

    return transaction_runner.run_write(operation)


def _count_rows_in_transaction(transaction: HostTransaction, table_name: str) -> int:
    """在现有 transaction 内统计表行数。

    :param transaction: Host transaction。
    :param table_name: 表名。
    :returns: 行数。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    return _required_int(row, "total")


def _required_text(row: HostRow, column: str) -> str:
    """读取必填文本列。

    :param row: Host row。
    :param column: 列名。
    :returns: 文本值。
    """

    value = row.get(column)
    assert isinstance(value, str)
    return value


def _required_int(row: HostRow, column: str) -> int:
    """读取必填整数列。

    :param row: Host row。
    :param column: 列名。
    :returns: 整数值。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value
