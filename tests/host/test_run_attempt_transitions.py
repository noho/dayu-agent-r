"""Host Phase 3 Run / Attempt transition primitive 测试。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.api import (
    AttemptStatus,
    AuthorizationClaim,
    CancelMode,
    EnsureSessionRequest,
    HostCallContext,
    HostMetadataEntry,
    OperationContext,
    RunStatus,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable import run_transition as run_transition_module
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CancelActiveAttemptInput,
    CancelPredispatchStartingInput,
    CancelQueuedRunInput,
    CreateQueuedRunInput,
    CreateRunningRunInput,
    PromoteQueuedRunInput,
    TerminalCloseoutInput,
    accept_worker_running_in_transaction,
    cancel_predispatch_starting_in_transaction,
    cancel_queued_in_transaction,
    create_queued_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    promote_queued_run_in_transaction,
    request_active_attempt_cancel_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    RunMutationResult,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    cancel_starting_dispatch_record_row,
    mark_attempt_running_row,
    mark_dispatch_worker_accepted_row,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
    terminal_run_row,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner

_NOW = datetime(2026, 5, 14, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "run-transition-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "hello"})


@dataclass(frozen=True, slots=True)
class _SeededRunningRun:
    """测试中创建的 running Run 组合。"""

    session_id: str
    run_id: str
    attempt_id: str


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试用 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
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


def _context() -> HostCallContext:
    """构造标准 Host call context。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="request-trace",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="run_transition_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase3",
            correlation_id="corr-run-transition",
        ),
    )


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建测试 Session 并返回 id。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(
        transaction_runner,
        EnsureSessionRequest(
            scope="workspace",
            slot_key="run-transition",
            metadata=(HostMetadataEntry(key="case", value="run-transition"),),
        ),
    )
    return result.snapshot.session_id


def test_create_running_run_creates_attempt_and_pending_dispatch(
    tmp_path: Path,
) -> None:
    """创建 running Run 会同事务创建 Run、Attempt、dispatch 与事件。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def operation(transaction: HostTransaction) -> tuple[str, str, str]:
            """执行 running Run 创建。

            :param transaction: Host transaction。
            :returns: Run、Attempt、dispatch 状态。
            """

            input_event = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-1",
                event_id="event-input-1",
            )
            result = create_running_run_with_starting_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _create_running_input(
                    session_id=session_id,
                    run_id="run-1",
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            assert result.status == StateMutationStatus.UPDATED
            assert result.run is not None
            assert result.attempt is not None
            assert result.dispatch_record is not None
            return (
                result.run.status.value,
                result.attempt.status.value,
                result.dispatch_record.status.value,
            )

        assert store.transaction_runner.run_write(operation) == (
            RunStatus.RUNNING.value,
            AttemptStatus.STARTING.value,
            DispatchRecordStatus.PENDING.value,
        )

        def verify(transaction: HostTransaction) -> tuple[str, ...]:
            """读取 canonical event type 序列。

            :param transaction: Host transaction。
            :returns: event type 序列。
            """

            return _event_types(transaction)

        event_types = store.transaction_runner.run_write(verify)
        assert _EVENT_TYPE_RUN_ACCEPTED in event_types
        assert _EVENT_TYPE_RUN_STARTED in event_types
        assert _EVENT_TYPE_ATTEMPT_STARTED in event_types


def test_create_queued_run_creates_no_attempt_or_dispatch(tmp_path: Path) -> None:
    """创建 queued Run 只写 Run 与 queue 事件，不创建 Attempt/dispatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def operation(transaction: HostTransaction) -> tuple[str, int, int]:
            """执行 queued Run 创建并读取关联 row 数。

            :param transaction: Host transaction。
            :returns: Run 状态、Attempt row 数、dispatch row 数。
            """

            input_event = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-queued",
                event_id="event-input-queued",
            )
            result = create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id="run-queued",
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            assert result.run is not None
            return (
                result.run.status.value,
                _count_rows(transaction, "host_attempts"),
                _count_rows(transaction, "host_attempt_dispatch_records"),
            )

        assert store.transaction_runner.run_write(operation) == (
            RunStatus.QUEUED.value,
            0,
            0,
        )

        def event_types(transaction: HostTransaction) -> tuple[str, ...]:
            """读取 event type 序列。

            :param transaction: Host transaction。
            :returns: event type 序列。
            """

            return _event_types(transaction)

        types = store.transaction_runner.run_write(event_types)
        assert _EVENT_TYPE_RUN_ACCEPTED in types
        assert _EVENT_TYPE_RUN_QUEUED in types
        assert _EVENT_TYPE_ATTEMPT_STARTED not in types


def test_promote_queued_run_uses_earliest_accepted_sequence(
    tmp_path: Path,
) -> None:
    """promotion 选择 accepted_event_sequence 最早的 queued Run。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def seed(transaction: HostTransaction) -> None:
            """按非字典序 run id 写入两个 queued Run。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            first_input = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-b",
                event_id="event-input-b",
            )
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id="run-b",
                    input_event_sequence=first_input.event_sequence,
                    request_index="b",
                ),
            )
            second_input = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-a",
                event_id="event-input-a",
            )
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id="run-a",
                    input_event_sequence=second_input.event_sequence,
                    request_index="a",
                ),
            )

        store.transaction_runner.run_write(seed)

        def promote(transaction: HostTransaction) -> str:
            """执行一次 promotion。

            :param transaction: Host transaction。
            :returns: 被 promotion 的 Run id。
            """

            result = promote_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _promote_input(session_id=session_id),
            )
            assert result.status == StateMutationStatus.UPDATED
            assert result.promoted_run is not None
            assert result.attempt is not None
            assert result.dispatch_record is not None
            return result.promoted_run.run_id

        assert store.transaction_runner.run_write(promote) == "run-b"


def test_terminal_closeout_appends_concrete_terminal_events(
    tmp_path: Path,
) -> None:
    """terminal helper 写具体 terminal event type 并关闭 Run/Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> tuple[str, str]:
            """执行 terminal closeout。

            :param transaction: Host transaction。
            :returns: Run 与 Attempt 状态。
            """

            result = terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-succeeded",
                    run_terminal_event_id="event-run-succeeded",
                    attempt_terminal_status=AttemptStatus.SUCCEEDED,
                    run_terminal_status=RunStatus.SUCCEEDED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="phase3_internal_closeout",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            assert result.status == StateMutationStatus.UPDATED
            assert result.run is not None
            assert result.attempt is not None
            return result.run.status.value, result.attempt.status.value

        assert store.transaction_runner.run_write(closeout) == (
            RunStatus.SUCCEEDED.value,
            AttemptStatus.SUCCEEDED.value,
        )

        def verify(transaction: HostTransaction) -> tuple[str, ...]:
            """读取 event type 序列。

            :param transaction: Host transaction。
            :returns: event type 序列。
            """

            run = read_run_by_id(transaction, seeded.run_id)
            attempt = read_attempt_by_id(transaction, seeded.attempt_id)
            assert run is not None
            assert attempt is not None
            assert run.terminal_event_id == "event-run-succeeded"
            assert attempt.terminal_event_id == "event-attempt-succeeded"
            return _event_types(transaction)

        event_types = store.transaction_runner.run_write(verify)
        assert _EVENT_TYPE_ATTEMPT_SUCCEEDED in event_types
        assert _EVENT_TYPE_RUN_SUCCEEDED in event_types
        assert "RUN_TERMINAL" not in event_types


@pytest.mark.parametrize(
    ("attempt_status", "run_status", "attempt_event_type", "run_event_type"),
    (
        (
            AttemptStatus.FAILED,
            RunStatus.FAILED,
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ),
        (
            AttemptStatus.LOST,
            RunStatus.LOST,
            "ATTEMPT_LOST",
            "RUN_LOST",
        ),
    ),
)
def test_terminal_closeout_supports_failure_and_lost_facts(
    tmp_path: Path,
    attempt_status: AttemptStatus,
    run_status: RunStatus,
    attempt_event_type: str,
    run_event_type: str,
) -> None:
    """terminal helper 支持 failed/lost 具体 terminal facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> tuple[str, str, tuple[str, ...]]:
            """按参数执行 terminal closeout。

            :param transaction: Host transaction。
            :returns: Run 状态、Attempt 状态与事件类型序列。
            """

            result = terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id=f"event-attempt-{attempt_status.value}",
                    run_terminal_event_id=f"event-run-{run_status.value}",
                    attempt_terminal_status=attempt_status,
                    run_terminal_status=run_status,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="phase3_internal_closeout",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            assert result.run is not None
            assert result.attempt is not None
            return (
                result.run.status.value,
                result.attempt.status.value,
                _event_types(transaction),
            )

        run_value, attempt_value, event_types = store.transaction_runner.run_write(
            closeout
        )
        assert run_value == run_status.value
        assert attempt_value == attempt_status.value
        assert attempt_event_type in event_types
        assert run_event_type in event_types


def test_terminal_closeout_accepts_attempt_running_in_phase5(
    tmp_path: Path,
) -> None:
    """Attempt RUNNING terminal closeout 在 Phase 5 收口为对应终态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def force_running(transaction: HostTransaction) -> None:
            """强制 Attempt 进入 RUNNING 构造后续 phase 才支持的状态。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                "UPDATE host_attempts SET status = ? WHERE attempt_id = ?",
                (AttemptStatus.RUNNING.value, seeded.attempt_id),
            )

        store.transaction_runner.run_write(force_running)

        def closeout(transaction: HostTransaction) -> tuple[str, str]:
            """尝试关闭 Attempt RUNNING。

            :param transaction: Host transaction。
            :returns: transition status 与 Attempt 当前状态。
            """

            result = terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-running-terminal",
                    run_terminal_event_id="event-run-running-terminal",
                    attempt_terminal_status=AttemptStatus.SUCCEEDED,
                    run_terminal_status=RunStatus.SUCCEEDED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="phase3_internal_closeout",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            assert result.attempt is not None
            return result.status.value, result.attempt.status.value

        assert store.transaction_runner.run_write(closeout) == (
            StateMutationStatus.UPDATED.value,
            AttemptStatus.SUCCEEDED.value,
        )


def test_promote_cas_loser_keeps_queued_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """promotion CAS 失败时回滚已 append 的 RUN_STARTED event。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def seed(transaction: HostTransaction) -> None:
            """写入 queued Run。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            queued_input = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-queued",
                event_id="event-input-queued",
            )
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id="run-queued",
                    input_event_sequence=queued_input.event_sequence,
                ),
            )

        store.transaction_runner.run_write(seed)

        def cas_lost_promote_queued_run_row(
            transaction: HostTransaction,
            *,
            session_id: str,
            run_id: str,
            started_event_id: str,
            started_event_sequence: int,
            current_attempt_id: str,
            updated_at: str,
        ) -> RunMutationResult:
            """模拟 append RUN_STARTED 后低层 CAS 竞争失败。

            :param transaction: Host transaction。
            :param session_id: Session id。
            :param run_id: Run id。
            :param started_event_id: 已 append 的 RUN_STARTED event id。
            :param started_event_sequence: 已 append 的 RUN_STARTED event sequence。
            :param current_attempt_id: 待写入的 Attempt id。
            :param updated_at: 更新时间。
            :returns: ``CAS_LOST`` mutation 结果。
            """

            del session_id, started_event_id, started_event_sequence
            del current_attempt_id, updated_at
            latest = read_run_by_id(transaction, run_id)
            assert latest is not None
            return RunMutationResult(
                status=StateMutationStatus.CAS_LOST,
                row=latest,
            )

        monkeypatch.setattr(
            run_transition_module,
            "promote_queued_run_row",
            cas_lost_promote_queued_run_row,
        )

        def promote(transaction: HostTransaction) -> None:
            """执行必然 CAS_LOST 的 promotion。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: append 后 CAS 失败必须中止事务。
            """

            promote_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _promote_input(session_id=session_id),
            )

        with pytest.raises(HostDurableError):
            store.transaction_runner.run_write(promote)

        def verify(transaction: HostTransaction) -> tuple[str, int]:
            """确认 queued state 保留且无 orphan RUN_STARTED event。

            :param transaction: Host transaction。
            :returns: queued Run 状态与 queued Run 的 RUN_STARTED event 数。
            """

            latest = read_run_by_id(transaction, "run-queued")
            assert latest is not None
            return (
                latest.status.value,
                _count_run_events(
                    transaction,
                    run_id="run-queued",
                    event_type=_EVENT_TYPE_RUN_STARTED,
                ),
            )

        assert store.transaction_runner.run_write(verify) == (
            RunStatus.QUEUED.value,
            0,
        )


def test_promote_active_run_skip_does_not_append_queued_started_event(
    tmp_path: Path,
) -> None:
    """active Run 存在时 promotion skip 不追加 queued Run 的 RUN_STARTED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def seed(transaction: HostTransaction) -> None:
            """写入 active Run 与 queued Run。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            active_input = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-active",
                event_id="event-input-active",
            )
            create_running_run_with_starting_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _create_running_input(
                    session_id=session_id,
                    run_id="run-active",
                    input_event_sequence=active_input.event_sequence,
                ),
            )
            queued_input = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-queued",
                event_id="event-input-queued",
            )
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id="run-queued",
                    input_event_sequence=queued_input.event_sequence,
                ),
            )

        store.transaction_runner.run_write(seed)

        def promote(transaction: HostTransaction) -> tuple[str, str | None, str, int]:
            """在 active Run 存在时尝试 promotion。

            :param transaction: Host transaction。
            :returns: 结果状态、skip 原因、queued Run 状态与 queued RUN_STARTED 数。
            """

            result = promote_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _promote_input(session_id=session_id),
            )
            latest = read_run_by_id(transaction, "run-queued")
            assert latest is not None
            return (
                result.status.value,
                result.skip_reason,
                latest.status.value,
                _count_run_events(
                    transaction,
                    run_id="run-queued",
                    event_type=_EVENT_TYPE_RUN_STARTED,
                ),
            )

        assert store.transaction_runner.run_write(promote) == (
            StateMutationStatus.INVALID_STATE.value,
            "active_run_exists",
            RunStatus.QUEUED.value,
            0,
        )


def test_cancel_predispatch_starting_updates_dispatch_attempt_and_run(
    tmp_path: Path,
) -> None:
    """pre-dispatch cancel 同事务取消 dispatch、Attempt 与 Run。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def cancel(transaction: HostTransaction) -> tuple[str, str, str]:
            """执行 pre-dispatch cancel。

            :param transaction: Host transaction。
            :returns: Run、Attempt、dispatch 状态。
            """

            result = cancel_predispatch_starting_in_transaction(
                transaction,
                EventLogStore(),
                CancelPredispatchStartingInput(
                    run_id=seeded.run_id,
                    cancel_request_event_id="event-cancel-requested",
                    attempt_cancelled_event_id="event-attempt-cancelled",
                    run_cancelled_event_id="event-run-cancelled",
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    client_request_id="cancel-1",
                    idempotency_key="cancel-1",
                    reason="user_cancel",
                    mode=CancelMode.GRACEFUL,
                    call_context_digest=_CALL_CONTEXT_DIGEST,
                ),
            )
            assert result.status == StateMutationStatus.UPDATED
            assert result.run is not None
            assert result.attempt is not None
            assert result.dispatch_record is not None
            return (
                result.run.status.value,
                result.attempt.status.value,
                result.dispatch_record.status.value,
            )

        assert store.transaction_runner.run_write(cancel) == (
            RunStatus.CANCELLED.value,
            AttemptStatus.CANCELLED.value,
            DispatchRecordStatus.CANCELLED.value,
        )


def test_dispatch_record_waiting_dispatching_and_worker_accept_refs(
    tmp_path: Path,
) -> None:
    """dispatch record 按 waiting -> dispatching -> accepted refs 推进。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, bool]:
            """推进 dispatch record 并执行 worker accept。

            :param transaction: Host transaction。
            :returns: Attempt 状态、dispatch 状态与 worker accept refs 是否存在。
            """

            _ensure_host_instance_tx(transaction)
            waiting = mark_dispatch_waiting_for_lane_row(
                transaction,
                attempt_id=seeded.attempt_id,
                owner_host_instance_id="host-instance-1",
                lane_name="llm",
                waiting_for_lane_at="2026-05-14T01:02:04Z",
            )
            assert waiting.status == StateMutationStatus.UPDATED
            dispatching = mark_dispatching_after_lane_row(
                transaction,
                attempt_id=seeded.attempt_id,
                owner_host_instance_id="host-instance-1",
                lane_name="llm",
                lane_claim_id="lane-claim-1",
                lane_owner_id="lane-owner-1",
                lane_acquired_at="2026-05-14T01:02:05Z",
                dispatching_at="2026-05-14T01:02:06Z",
            )
            assert dispatching.status == StateMutationStatus.UPDATED
            accepted = accept_worker_running_in_transaction(
                transaction,
                EventLogStore(),
                AcceptWorkerRunningInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_running_event_id="event-attempt-running",
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    worker_accept_reason="worker_accepted",
                ),
            )
            assert accepted.attempt is not None
            assert accepted.dispatch_record is not None
            dispatch_record = accepted.dispatch_record
            return (
                accepted.attempt.status.value,
                dispatch_record.status.value,
                dispatch_record.worker_accept_event_id is not None
                and dispatch_record.worker_accept_event_sequence is not None
                and dispatch_record.worker_accepted_at is not None,
            )

        assert store.transaction_runner.run_write(operation) == (
            AttemptStatus.RUNNING.value,
            DispatchRecordStatus.DISPATCHING.value,
            True,
        )


def test_dispatching_supports_pending_direct_lane_recheck(tmp_path: Path) -> None:
    """pending dispatch record 可在 lane acquired recheck 后直跳 dispatching。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(
            transaction: HostTransaction,
        ) -> tuple[str, str, str | None, str | None, str | None]:
            """对 pending dispatch record 执行 direct dispatching mutation。

            :param transaction: Host transaction。
            :returns: mutation 状态、dispatch 状态与关键诊断字段。
            """

            _ensure_host_instance_tx(transaction)
            result = mark_dispatching_after_lane_row(
                transaction,
                attempt_id=seeded.attempt_id,
                owner_host_instance_id="host-instance-1",
                lane_name="llm",
                lane_claim_id="lane-claim-1",
                lane_owner_id="lane-owner-1",
                lane_acquired_at="2026-05-14T01:02:05Z",
                dispatching_at="2026-05-14T01:02:06Z",
            )
            assert result.row is not None
            return (
                result.status.value,
                result.row.status.value,
                result.row.waiting_for_lane_at,
                result.row.lane_name,
                result.row.owner_host_instance_id,
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            DispatchRecordStatus.DISPATCHING.value,
            "2026-05-14T01:02:05Z",
            "llm",
            "host-instance-1",
        )


@pytest.mark.parametrize(
    "source_status",
    (
        DispatchRecordStatus.PENDING,
        DispatchRecordStatus.WAITING_FOR_LANE,
        DispatchRecordStatus.DISPATCHING,
    ),
)
def test_cancel_predispatch_starting_supports_all_pre_accept_dispatch_statuses(
    tmp_path: Path, source_status: DispatchRecordStatus
) -> None:
    """pending / waiting_for_lane / pre-accept dispatching 都可 direct cancel。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def cancel(transaction: HostTransaction) -> tuple[str, str, str]:
            """按参数构造 dispatch source 状态并执行 direct cancel。

            :param transaction: Host transaction。
            :returns: Run、Attempt、dispatch 状态。
            """

            if source_status == DispatchRecordStatus.WAITING_FOR_LANE:
                _mark_waiting_tx(transaction, seeded.attempt_id)
            elif source_status == DispatchRecordStatus.DISPATCHING:
                _mark_dispatching_tx(transaction, seeded.attempt_id)
            result = cancel_predispatch_starting_in_transaction(
                transaction,
                EventLogStore(),
                _cancel_predispatch_input(
                    run_id=seeded.run_id,
                    event_suffix=source_status.value,
                ),
            )
            assert result.run is not None
            assert result.attempt is not None
            assert result.dispatch_record is not None
            return (
                result.run.status.value,
                result.attempt.status.value,
                result.dispatch_record.status.value,
            )

        assert store.transaction_runner.run_write(cancel) == (
            RunStatus.CANCELLED.value,
            AttemptStatus.CANCELLED.value,
            DispatchRecordStatus.CANCELLED.value,
        )


def test_cancel_starting_dispatch_record_absorbs_already_cancelled(
    tmp_path: Path,
) -> None:
    """底层 dispatch cancel CAS 对已 CANCELLED row 返回 CAS_LOST。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str]:
            """先完成 pre-dispatch cancel，再重放底层 dispatch cancel。

            :param transaction: Host transaction。
            :returns: mutation 状态与 dispatch row 状态。
            """

            cancelled = cancel_predispatch_starting_in_transaction(
                transaction,
                EventLogStore(),
                _cancel_predispatch_input(
                    run_id=seeded.run_id,
                    event_suffix="first",
                ),
            )
            assert cancelled.status == StateMutationStatus.UPDATED
            event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-dispatch-cancel-replay",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="ATTEMPT_CANCELLED",
                    payload={"attempt_id": seeded.attempt_id},
                ),
            ).row
            result = cancel_starting_dispatch_record_row(
                transaction,
                attempt_id=seeded.attempt_id,
                cancelled_event_id=event.event_id,
                cancelled_event_sequence=event.event_sequence,
                cancelled_at="2026-05-14T01:02:09Z",
            )
            assert result.row is not None
            return result.status.value, result.row.status.value

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.CAS_LOST.value,
            DispatchRecordStatus.CANCELLED.value,
        )


@pytest.mark.parametrize(
    "active_status",
    (RunStatus.CANCELLING, RunStatus.RECOVERING),
)
def test_terminal_run_row_reports_cas_lost_for_deferred_active_statuses(
    tmp_path: Path, active_status: RunStatus
) -> None:
    """terminal Run CAS 看到 CANCELLING/RECOVERING 时归类为 CAS_LOST。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str]:
            """构造 deferred active 状态后执行 terminal Run CAS。

            :param transaction: Host transaction。
            :returns: mutation 状态与最新 Run 状态。
            """

            transaction.execute(
                "UPDATE host_runs SET status = ? WHERE run_id = ?",
                (active_status.value, seeded.run_id),
            )
            event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id=f"event-terminal-{active_status.value}",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "cas-test"},
                ),
            ).row
            result = terminal_run_row(
                transaction,
                run_id=seeded.run_id,
                current_attempt_id=seeded.attempt_id,
                terminal_status=RunStatus.FAILED,
                terminal_event_id=event.event_id,
                terminal_event_sequence=event.event_sequence,
                terminal_at="2026-05-14T01:02:10Z",
            )
            assert result.row is not None
            return result.status.value, result.row.status.value

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.CAS_LOST.value,
            active_status.value,
        )


def test_cancel_predispatch_rejects_dispatching_after_worker_accept_refs(
    tmp_path: Path,
) -> None:
    """dispatching 已有 worker accepted refs 时不能走 pre-worker direct cancel。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def cancel(transaction: HostTransaction) -> tuple[str, str, str]:
            """写入 worker accept refs 后尝试 direct cancel。

            :param transaction: Host transaction。
            :returns: transition 状态、Attempt 状态与 dispatch 状态。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-worker-accepted",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="ATTEMPT_RUNNING",
                    payload={"attempt_id": seeded.attempt_id},
                ),
            ).row
            accepted = mark_dispatch_worker_accepted_row(
                transaction,
                attempt_id=seeded.attempt_id,
                worker_accept_event_id=event.event_id,
                worker_accept_event_sequence=event.event_sequence,
                worker_accepted_at="2026-05-14T01:02:07Z",
            )
            assert accepted.status == StateMutationStatus.UPDATED
            result = cancel_predispatch_starting_in_transaction(
                transaction,
                EventLogStore(),
                _cancel_predispatch_input(
                    run_id=seeded.run_id,
                    event_suffix="accepted",
                ),
            )
            assert result.attempt is not None
            assert result.dispatch_record is not None
            return (
                result.status.value,
                result.attempt.status.value,
                result.dispatch_record.status.value,
            )

        assert store.transaction_runner.run_write(cancel) == (
            StateMutationStatus.INVALID_STATE.value,
            AttemptStatus.STARTING.value,
            DispatchRecordStatus.DISPATCHING.value,
        )


def test_mark_attempt_running_only_allows_starting_source(
    tmp_path: Path,
) -> None:
    """ATTEMPT_RUNNING CAS 只允许 STARTING -> RUNNING。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, str]:
            """执行两次 Attempt RUNNING CAS。

            :param transaction: Host transaction。
            :returns: 两次 mutation 状态与最终 Attempt 状态。
            """

            first = mark_attempt_running_row(
                transaction,
                attempt_id=seeded.attempt_id,
                updated_at="2026-05-14T01:02:08Z",
            )
            second = mark_attempt_running_row(
                transaction,
                attempt_id=seeded.attempt_id,
                updated_at="2026-05-14T01:02:09Z",
            )
            latest = read_attempt_by_id(transaction, seeded.attempt_id)
            assert latest is not None
            return first.status.value, second.status.value, latest.status.value

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            StateMutationStatus.INVALID_STATE.value,
            AttemptStatus.RUNNING.value,
        )


def test_active_cancel_appends_run_cancelling_once(tmp_path: Path) -> None:
    """active cancel 重复调用不重复追加 RUN_CANCELLING。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int]:
            """先接受 worker，再执行两次 active cancel。

            :param transaction: Host transaction。
            :returns: Run 状态与 RUN_CANCELLING 事件数。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            accepted = accept_worker_running_in_transaction(
                transaction,
                EventLogStore(),
                AcceptWorkerRunningInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_running_event_id="event-active-attempt-running",
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    worker_accept_reason="worker_accepted",
                ),
            )
            assert accepted.status == StateMutationStatus.UPDATED
            first = request_active_attempt_cancel_in_transaction(
                transaction,
                EventLogStore(),
                _cancel_active_input(run_id=seeded.run_id, event_suffix="first"),
            )
            second = request_active_attempt_cancel_in_transaction(
                transaction,
                EventLogStore(),
                _cancel_active_input(run_id=seeded.run_id, event_suffix="second"),
            )
            assert first.run is not None
            assert second.run is not None
            return (
                second.run.status.value,
                _count_events(transaction, _EVENT_TYPE_RUN_CANCELLING),
            )

        assert store.transaction_runner.run_write(operation) == (
            RunStatus.CANCELLING.value,
            1,
        )


def test_cancel_queued_terminal_run_returns_invalid_state(
    tmp_path: Path,
) -> None:
    """cancel queued helper 不能重写已经 terminal 的 Run。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> None:
            """先关闭 running Run。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-done",
                    run_terminal_event_id="event-run-done",
                    attempt_terminal_status=AttemptStatus.SUCCEEDED,
                    run_terminal_status=RunStatus.SUCCEEDED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="phase3_internal_closeout",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )

        store.transaction_runner.run_write(closeout)

        def cancel_terminal(transaction: HostTransaction) -> tuple[str, str]:
            """对 terminal Run 调用 queued cancel。

            :param transaction: Host transaction。
            :returns: transition status 与 Run 最新状态。
            """

            result = cancel_queued_in_transaction(
                transaction,
                EventLogStore(),
                CancelQueuedRunInput(
                    run_id=seeded.run_id,
                    cancel_request_event_id="event-cancel-terminal",
                    run_cancelled_event_id="event-run-cancel-terminal",
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    client_request_id="cancel-terminal",
                    idempotency_key="cancel-terminal",
                    reason="too_late",
                    mode=CancelMode.GRACEFUL,
                    call_context_digest=_CALL_CONTEXT_DIGEST,
                ),
            )
            assert result.run is not None
            return result.status.value, result.run.status.value

        assert store.transaction_runner.run_write(cancel_terminal) == (
            StateMutationStatus.INVALID_STATE.value,
            RunStatus.SUCCEEDED.value,
        )


def test_rollback_prevents_partial_event_and_state_persistence(
    tmp_path: Path,
) -> None:
    """transaction rollback 不留下 Run/Attempt/dispatch 或 transition events。"""

    class ExpectedRollback(RuntimeError):
        """测试用 rollback sentinel。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def failing_operation(transaction: HostTransaction) -> None:
            """写入 transition 后主动失败触发 rollback。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises ExpectedRollback: 总是抛出以触发 rollback。
            """

            input_event = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-rollback",
                event_id="event-input-rollback",
            )
            create_running_run_with_starting_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _create_running_input(
                    session_id=session_id,
                    run_id="run-rollback",
                    input_event_sequence=input_event.event_sequence,
                ),
            )
            raise ExpectedRollback("rollback")

        with pytest.raises(ExpectedRollback):
            store.transaction_runner.run_write(failing_operation)

        def verify(transaction: HostTransaction) -> tuple[int, int]:
            """确认 transition state 和 event 都被回滚。

            :param transaction: Host transaction。
            :returns: Run row 数、RUN_ACCEPTED event 数。
            """

            return (
                _count_rows(transaction, "host_runs"),
                _count_events(transaction, _EVENT_TYPE_RUN_ACCEPTED),
            )

        assert store.transaction_runner.run_write(verify) == (0, 0)


def _seed_running_run(
    store: HostDurableStore, tmp_path: Path
) -> _SeededRunningRun:
    """创建标准 running Run 测试组合。

    :param store: Host durable store。
    :param tmp_path: pytest 临时目录，保留签名稳定供调用方区分 fixture。
    :returns: running Run 组合。
    """

    del tmp_path
    session_id = _ensure_session_id(store.transaction_runner)

    def operation(transaction: HostTransaction) -> _SeededRunningRun:
        """创建 running Run。

        :param transaction: Host transaction。
        :returns: running Run 组合。
        """

        input_event = _append_user_input(
            transaction,
            session_id=session_id,
            run_id="run-1",
            event_id="event-input-1",
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            _create_running_input(
                session_id=session_id,
                run_id="run-1",
                input_event_sequence=input_event.event_sequence,
            ),
        )
        return _SeededRunningRun(
            session_id=session_id,
            run_id="run-1",
            attempt_id="attempt-run-1",
        )

    return store.transaction_runner.run_write(operation)


def _append_user_input(
    transaction: HostTransaction,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
) -> EventLogRow:
    """追加测试用 ``USER_INPUT_ACCEPTED`` event。

    :param transaction: Host transaction。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :returns: EventLog row。
    """

    return EventLogStore().append_event(
        transaction,
        _test_event(
            event_id=event_id,
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


def _test_event(
    *,
    event_id: str,
    session_id: str,
    run_id: str,
    event_type: str,
    payload: JsonValue,
) -> EventLogAppendRequest:
    """构造测试用 canonical fact event。

    :param event_id: event id。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_type: event type。
    :param payload: event payload。
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


def _create_running_input(
    *, session_id: str, run_id: str, input_event_sequence: int
) -> CreateRunningRunInput:
    """构造 running Run 创建输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :returns: CreateRunningRunInput。
    """

    suffix = run_id.removeprefix("run-")
    return CreateRunningRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{suffix}",
        input_event_id=f"event-input-{suffix}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{suffix}",
        run_started_event_id=f"event-run-started-{suffix}",
        attempt_started_event_id=f"event-attempt-started-{suffix}",
        attempt_id=f"attempt-{run_id}",
        execution_id=f"execution-{run_id}",
        dispatch_record_id=f"dispatch-{run_id}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{suffix}",
        execution_target="local-default",
        queue_policy="queue",
        start_reason=RunStartReason.INITIAL,
        worker_kind=WorkerKind.LOCAL,
        owner_host_instance_id=None,
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _create_queued_input(
    *,
    session_id: str,
    run_id: str,
    input_event_sequence: int,
    request_index: str = "queued",
) -> CreateQueuedRunInput:
    """构造 queued Run 创建输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param input_event_sequence: USER_INPUT_ACCEPTED event sequence。
    :param request_index: event id 后缀。
    :returns: CreateQueuedRunInput。
    """

    return CreateQueuedRunInput(
        session_id=session_id,
        run_id=run_id,
        client_request_id=f"request-{request_index}",
        input_event_id=f"event-input-{request_index}",
        input_event_sequence=input_event_sequence,
        run_accepted_event_id=f"event-run-accepted-{request_index}",
        run_queued_event_id=f"event-run-queued-{request_index}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        idempotency_key=f"request-{request_index}",
        execution_target="local-default",
        queue_policy="queue",
        queue_reason="active_run_exists",
        active_run_id="run-active",
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _promote_input(*, session_id: str) -> PromoteQueuedRunInput:
    """构造 promotion 输入。

    :param session_id: Session id。
    :returns: PromoteQueuedRunInput。
    """

    return PromoteQueuedRunInput(
        session_id=session_id,
        run_started_event_id="event-promotion-run-started",
        attempt_started_event_id="event-promotion-attempt-started",
        attempt_id="attempt-promotion",
        execution_id="execution-promotion",
        dispatch_record_id="dispatch-promotion",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        worker_kind=WorkerKind.LOCAL,
        owner_host_instance_id=None,
    )


def _cancel_predispatch_input(
    *, run_id: str, event_suffix: str
) -> CancelPredispatchStartingInput:
    """构造 pre-dispatch cancel 输入。

    :param run_id: Run id。
    :param event_suffix: event id 后缀。
    :returns: CancelPredispatchStartingInput。
    """

    return CancelPredispatchStartingInput(
        run_id=run_id,
        cancel_request_event_id=f"event-cancel-requested-{event_suffix}",
        attempt_cancelled_event_id=f"event-attempt-cancelled-{event_suffix}",
        run_cancelled_event_id=f"event-run-cancelled-{event_suffix}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        client_request_id=f"cancel-{event_suffix}",
        idempotency_key=f"cancel-{event_suffix}",
        reason="user_cancel",
        mode=CancelMode.GRACEFUL,
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _cancel_active_input(
    *, run_id: str, event_suffix: str
) -> CancelActiveAttemptInput:
    """构造 active cancel 输入。

    :param run_id: Run id。
    :param event_suffix: event id 后缀。
    :returns: CancelActiveAttemptInput。
    """

    return CancelActiveAttemptInput(
        run_id=run_id,
        cancel_request_event_id=f"event-active-cancel-requested-{event_suffix}",
        run_cancelling_event_id=f"event-run-cancelling-{event_suffix}",
        occurred_at=_NOW,
        actor="analyst",
        source="pytest",
        client_request_id=f"active-cancel-{event_suffix}",
        idempotency_key=f"active-cancel-{event_suffix}",
        reason="user_cancel",
        mode=CancelMode.GRACEFUL,
        call_context_digest=_CALL_CONTEXT_DIGEST,
    )


def _mark_waiting_tx(transaction: HostTransaction, attempt_id: str) -> None:
    """将测试 dispatch record 推进到 waiting_for_lane。

    :param transaction: Host transaction。
    :param attempt_id: Attempt id。
    :returns: ``None``。
    """

    _ensure_host_instance_tx(transaction)
    result = mark_dispatch_waiting_for_lane_row(
        transaction,
        attempt_id=attempt_id,
        owner_host_instance_id="host-instance-1",
        lane_name="llm",
        waiting_for_lane_at="2026-05-14T01:02:04Z",
    )
    assert result.status == StateMutationStatus.UPDATED


def _mark_dispatching_tx(transaction: HostTransaction, attempt_id: str) -> None:
    """将测试 dispatch record 推进到 pre-accept dispatching。

    :param transaction: Host transaction。
    :param attempt_id: Attempt id。
    :returns: ``None``。
    """

    _mark_waiting_tx(transaction, attempt_id)
    result = mark_dispatching_after_lane_row(
        transaction,
        attempt_id=attempt_id,
        owner_host_instance_id="host-instance-1",
        lane_name="llm",
        lane_claim_id="lane-claim-1",
        lane_owner_id="lane-owner-1",
        lane_acquired_at="2026-05-14T01:02:05Z",
        dispatching_at="2026-05-14T01:02:06Z",
    )
    assert result.status == StateMutationStatus.UPDATED


def _ensure_host_instance_tx(transaction: HostTransaction) -> None:
    """写入测试用 Host instance row。

    :param transaction: Host transaction。
    :returns: ``None``。
    """

    transaction.execute(
        """
        INSERT OR IGNORE INTO host_instances (
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
            "host-instance-1",
            1,
            "process-start-token",
            None,
            "2026-05-14T01:02:03Z",
            "2026-05-14T01:02:03Z",
            "running",
        ),
    )


def _event_types(transaction: HostTransaction) -> tuple[str, ...]:
    """读取全部 EventLog event type。

    :param transaction: Host transaction。
    :returns: event type 序列。
    """

    rows = transaction.fetchall(
        "SELECT event_type FROM event_log ORDER BY event_sequence ASC"
    )
    return tuple(_required_text(row, "event_type") for row in rows)


def _count_events(transaction: HostTransaction, event_type: str) -> int:
    """统计指定 event type 数量。

    :param transaction: Host transaction。
    :param event_type: event type。
    :returns: event 数。
    """

    row = transaction.fetchone(
        "SELECT COUNT(*) AS total FROM event_log WHERE event_type = ?",
        (event_type,),
    )
    assert row is not None
    return _required_int(row, "total")


def _count_run_events(
    transaction: HostTransaction, *, run_id: str, event_type: str
) -> int:
    """统计指定 Run 的指定 event type 数量。

    :param transaction: Host transaction。
    :param run_id: Run id。
    :param event_type: event type。
    :returns: event 数。
    """

    row = transaction.fetchone(
        "SELECT COUNT(*) AS total FROM event_log WHERE run_id = ? AND event_type = ?",
        (run_id, event_type),
    )
    assert row is not None
    return _required_int(row, "total")


def _count_rows(transaction: HostTransaction, table_name: str) -> int:
    """统计指定表 row 数。

    :param transaction: Host transaction。
    :param table_name: 表名。
    :returns: row 数。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS total FROM {table_name}")
    assert row is not None
    return _required_int(row, "total")


def _required_text(row: HostRow, column: str) -> str:
    """从 HostRow 读取必填字符串。

    :param row: Host row。
    :param column: 列名。
    :returns: 字符串值。
    """

    value = row.get(column)
    assert isinstance(value, str)
    return value


def _required_int(row: HostRow, column: str) -> int:
    """从 HostRow 读取必填整数。

    :param row: Host row。
    :param column: 列名。
    :returns: 整数值。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value


_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_QUEUED = "RUN_QUEUED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_ATTEMPT_STARTED = "ATTEMPT_STARTED"
_EVENT_TYPE_ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_CANCELLING = "RUN_CANCELLING"
