"""Phase 11 Slice 3 startup recovery dispatch 测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import EnsureSessionRequest, HostMetadataEntry, RunStatus
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventClass, EventLogAppendRequest, EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.run_transition import (
    CreateRunningRunInput,
    RunTransitionResult,
    StartRecoveryRunInput,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.engine_ingest import (
    EngineEventCandidate,
    EngineIngestStatus,
    EngineEventIngestor,
    LocalEngineEnvelope,
)
from dayu.host.recovery import (
    StartupRecoveryDecision,
    StartupRecoveryPolicy,
    StartupRecoveryScanner,
)
from dayu.host.recovery_process import ProcessEvidence

_NOW = datetime(2026, 5, 19, 4, 5, 6, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "recovery-dispatch-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "recovery"})


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试用旧 Attempt 引用。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


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
    """记录 recovery commit 后的 dispatch wakeup。"""

    def __init__(self) -> None:
        """初始化记录器。

        :returns: ``None``。
        """

        self.dispatches: list[PendingDispatchRecord] = []
        self.promoted_sessions: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 pending dispatch。

        :param record: 已持久化的 pending dispatch 摘要。
        :returns: ``None``。
        """

        self.dispatches.append(record)

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        self.promoted_sessions.append(session_id)


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


def test_recovering_scan_creates_new_attempt_dispatch_and_wakes_scheduler(
    tmp_path: Path,
) -> None:
    """positive orphan startup scan 创建新 Attempt / execution / dispatch 并唤醒。"""

    wakeup = _RecordingWakeup()
    with open_host_durable_store(_options(tmp_path)) as store:
        old = _seed_running_dispatching_run(store.transaction_runner)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
            recovery_owner_host_instance_id="host-instance-new",
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RECOVERY_DISPATCHED,
        )
        assert len(result.pending_dispatches) == 1
        assert wakeup.dispatches == list(result.pending_dispatches)

        observation = _recovery_observation(store.transaction_runner, old)
        assert observation.current_attempt_id != old.attempt_id
        assert observation.current_execution_id != old.execution_id
        assert observation.current_dispatch_record_id != old.dispatch_record_id
        assert observation.dispatch_status is DispatchRecordStatus.PENDING
        assert observation.dispatch_owner_host_instance_id == "host-instance-new"
        assert observation.event_suffix == (
            "ATTEMPT_LOST",
            "RUN_RECOVERING",
            "RUN_STARTED",
            "ATTEMPT_STARTED",
        )


def test_late_old_execution_event_after_recovery_dispatch_is_rejected(
    tmp_path: Path,
) -> None:
    """new Attempt 创建后旧 execution_id 的 late terminal event 不进入 canonical facts。"""

    wakeup = _RecordingWakeup()
    with open_host_durable_store(_options(tmp_path)) as store:
        old = _seed_running_dispatching_run(store.transaction_runner)
        StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
            recovery_owner_host_instance_id="host-instance-new",
        ).scan(_policy())

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(_old_final_answer_candidate(old))

        assert result.status is EngineIngestStatus.REJECTED
        assert result.events[0].event_type == "ENGINE_EVENT_REJECTED"
        assert _event_count(store.transaction_runner, "RUN_SUCCEEDED") == 0
        assert _run_status(store.transaction_runner, old.run_id) is RunStatus.RUNNING


def test_orphan_closeout_dispatch_invalid_state_reports_recovering_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """orphan closeout 成功后 dispatch INVALID_STATE 返回 recovering ready。"""

    wakeup = _RecordingWakeup()
    monkeypatch.setattr(
        "dayu.host.recovery.start_recovery_run_with_starting_attempt_in_transaction",
        _return_invalid_recovery_dispatch,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        old = _seed_running_dispatching_run(store.transaction_runner)

        result = StartupRecoveryScanner(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            process_probe=_PidMissingProbe(),
            dispatch_wakeup_port=wakeup,
            recovery_owner_host_instance_id="host-instance-new",
        ).scan(_policy())

        assert tuple(action.decision for action in result.actions) == (
            StartupRecoveryDecision.RECOVERING_READY,
        )
        assert result.actions[0].status is RunStatus.RECOVERING
        assert result.pending_dispatches == ()
        assert wakeup.dispatches == []
        assert _run_status(store.transaction_runner, old.run_id) is RunStatus.RECOVERING
        assert _event_count(store.transaction_runner, "ATTEMPT_LOST") == 1
        assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 1
        assert _event_count(store.transaction_runner, "RUN_STARTED") == 1


@dataclass(frozen=True, slots=True)
class _RecoveryObservation:
    """recovery dispatch 后的 durable 观察结果。"""

    current_attempt_id: str
    current_execution_id: str
    current_dispatch_record_id: str
    dispatch_status: DispatchRecordStatus
    dispatch_owner_host_instance_id: str | None
    event_suffix: tuple[str, str, str, str]


def _return_invalid_recovery_dispatch(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: StartRecoveryRunInput,
) -> RunTransitionResult:
    """模拟 recovery dispatch 创建因 durable precondition 返回 INVALID_STATE。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive；本测试替身不写入事件。
    :param request: recovery dispatch 创建输入。
    :returns: ``INVALID_STATE`` transition 结果。
    """

    return RunTransitionResult(
        status=StateMutationStatus.INVALID_STATE,
        run=read_run_by_id(transaction, request.run_id),
        attempt=None,
        dispatch_record=None,
    )


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


def _policy() -> StartupRecoveryPolicy:
    """构造测试 recovery policy。

    :returns: startup recovery policy。
    """

    return StartupRecoveryPolicy(
        now=_NOW,
        stale_after=timedelta(seconds=30),
        recovery_dispatch_limit=1,
    )


def _seed_running_dispatching_run(
    transaction_runner: HostTransactionRunner,
) -> _SeededRun:
    """写入 running Run 与 stale owner dispatch record。

    :param transaction_runner: Host transaction runner。
    :returns: seeded Run 引用。
    """

    session_id = _ensure_session_id(transaction_runner)

    def operation(transaction: HostTransaction) -> _SeededRun:
        """写入测试数据。

        :param transaction: Host transaction。
        :returns: seeded Run 引用。
        """

        input_event = EventLogStore().append_event(
            transaction,
            _event(
                event_id="event-input-recovery-dispatch",
                session_id=session_id,
                run_id="run-recovery-dispatch",
                event_type="USER_INPUT_ACCEPTED",
                payload={
                    "input_ref": None,
                    "input_digest": _INPUT_DIGEST,
                    "display_text": "recover this prompt",
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
            CreateRunningRunInput(
                session_id=session_id,
                run_id="run-recovery-dispatch",
                client_request_id="request-recovery-dispatch",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-recovery-dispatch",
                run_started_event_id="event-run-started-recovery-dispatch",
                attempt_started_event_id="event-attempt-started-recovery-dispatch",
                attempt_id="attempt-recovery-dispatch-old",
                execution_id="execution-recovery-dispatch-old",
                dispatch_record_id="dispatch-recovery-dispatch-old",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                idempotency_key="request-recovery-dispatch",
                execution_target="local-default",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        _insert_stale_host_instance(transaction)
        _insert_new_host_instance(transaction)
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id="attempt-recovery-dispatch-old",
            owner_host_instance_id="host-instance-old",
            lane_name="llm",
            waiting_for_lane_at="2026-05-19T04:04:00.000000Z",
        )
        assert waiting.status is StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id="attempt-recovery-dispatch-old",
            owner_host_instance_id="host-instance-old",
            lane_name="llm",
            lane_claim_id="lane-claim-old",
            lane_owner_id="lane-owner-old",
            lane_acquired_at="2026-05-19T04:04:01.000000Z",
            dispatching_at="2026-05-19T04:04:02.000000Z",
        )
        assert dispatching.status is StateMutationStatus.UPDATED
        return _SeededRun(
            session_id=session_id,
            run_id="run-recovery-dispatch",
            attempt_id="attempt-recovery-dispatch-old",
            execution_id="execution-recovery-dispatch-old",
            dispatch_record_id="dispatch-recovery-dispatch-old",
        )

    return transaction_runner.run_write(operation)


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建测试 Session。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="recovery-dispatch",
            metadata=(HostMetadataEntry(key="case", value="recovery-dispatch"),),
        ),
    )
    return result.snapshot.session_id


def _recovery_observation(
    transaction_runner: HostTransactionRunner, old: _SeededRun
) -> _RecoveryObservation:
    """读取 recovery dispatch 后的 durable 状态。

    :param transaction_runner: Host transaction runner。
    :param old: 旧 Attempt 引用。
    :returns: recovery durable 观察结果。
    """

    def operation(transaction: HostTransaction) -> _RecoveryObservation:
        """读取状态。

        :param transaction: Host transaction。
        :returns: recovery durable 观察结果。
        """

        run = read_run_by_id(transaction, old.run_id)
        assert run is not None
        assert run.current_attempt_id is not None
        attempt = read_attempt_by_id(transaction, run.current_attempt_id)
        assert attempt is not None
        dispatch = read_dispatch_record_by_attempt_id(
            transaction, run.current_attempt_id
        )
        assert dispatch is not None
        return _RecoveryObservation(
            current_attempt_id=attempt.attempt_id,
            current_execution_id=attempt.execution_id,
            current_dispatch_record_id=dispatch.dispatch_record_id,
            dispatch_status=dispatch.status,
            dispatch_owner_host_instance_id=dispatch.owner_host_instance_id,
            event_suffix=_event_type_suffix(transaction),
        )

    return transaction_runner.run_read(operation)


def _event_type_suffix(transaction: HostTransaction) -> tuple[str, str, str, str]:
    """读取最后四个 EventLog event_type。

    :param transaction: Host transaction。
    :returns: 最后四个 event type。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_type
        FROM {TABLE_EVENT_LOG}
        ORDER BY event_sequence DESC
        LIMIT 4
        """,
        (),
    )
    event_types = tuple(reversed(tuple(_row_text(row, "event_type") for row in rows)))
    assert len(event_types) == 4
    return (event_types[0], event_types[1], event_types[2], event_types[3])


def _old_final_answer_candidate(old: _SeededRun) -> EngineEventCandidate:
    """构造旧 execution_id 的 late final answer candidate。

    :param old: 旧 Attempt 引用。
    :returns: Engine event candidate。
    """

    token: CancellationToken = _OpenCancellationToken()
    return EngineEventCandidate(
        envelope=LocalEngineEnvelope(
            session_id=old.session_id,
            run_id=old.run_id,
            attempt_id=old.attempt_id,
            execution_id=old.execution_id,
            dispatch_record_id=old.dispatch_record_id,
            worker_kind=WorkerKind.LOCAL,
            execution_target="local-default",
            local_worker_id="old-worker",
            cancellation_token=token,
        ),
        worker_event_index=1,
        engine_event=EngineEvent(
            occurred_at=_NOW,
            session_id=old.session_id,
            run_id=old.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="late old answer",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        ),
        observed_at=_NOW,
    )


def _run_status(transaction_runner: HostTransactionRunner, run_id: str) -> RunStatus:
    """读取 Run 状态。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run 状态。
    """

    def operation(transaction: HostTransaction) -> RunStatus:
        """读取状态。

        :param transaction: Host transaction。
        :returns: Run 状态。
        """

        run = read_run_by_id(transaction, run_id)
        assert run is not None
        return run.status

    return transaction_runner.run_read(operation)


def _event_count(transaction_runner: HostTransactionRunner, event_type: str) -> int:
    """统计指定 event type 数量。

    :param transaction_runner: Host transaction runner。
    :param event_type: event type。
    :returns: 事件数量。
    """

    def operation(transaction: HostTransaction) -> int:
        """统计事件。

        :param transaction: Host transaction。
        :returns: 事件数量。
        """

        row = transaction.fetchone(
            f"SELECT COUNT(*) AS count FROM {TABLE_EVENT_LOG} WHERE event_type = ?",
            (event_type,),
        )
        assert row is not None
        return _row_int(row, "count")

    return transaction_runner.run_read(operation)


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
            "2026-05-19T04:00:00.000000Z",
            "2026-05-19T04:00:00.000000Z",
            "running",
        ),
    )


def _insert_new_host_instance(transaction: HostTransaction) -> None:
    """写入当前 recovery opener host instance。

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
            "host-instance-new",
            1,
            "process-start-token-new",
            None,
            "2026-05-19T04:05:00.000000Z",
            "2026-05-19T04:05:00.000000Z",
            "running",
        ),
    )


def _row_text(row: HostRow, field_name: str) -> str:
    """读取文本字段。

    :param row: Host row。
    :param field_name: 字段名。
    :returns: 文本字段值。
    """

    value = row.get(field_name)
    assert isinstance(value, str)
    return value


def _row_int(row: HostRow, field_name: str) -> int:
    """读取整数字段。

    :param row: Host row。
    :param field_name: 字段名。
    :returns: 整数字段值。
    """

    value = row.get(field_name)
    assert isinstance(value, int)
    return value
