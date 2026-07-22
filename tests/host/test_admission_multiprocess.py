"""Host Phase 3 admission 多进程一致性测试。

本模块只验证 durable store、EventLog、Session/Run/Attempt state index 与
admission / transition helper 在多个独立进程各自打开 SQLite connection 时的
并发语义；不启动 Engine、scheduler、lane、WorkerProxy 或 ToolRuntime。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from multiprocessing import Pipe, Process
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Generic, TypeVar
from unittest.mock import patch

import dayu.host.admission as host_admission
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host.admission import (
    CloseoutAttemptTerminalInput,
    HostAdmissionService,
    PendingDispatchRecord,
    SubmitFollowupQueueAdmissionInput,
    create_host_admission_service,
)
from dayu.host.api import (
    AttemptStatus,
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostInput,
    HostMetadataEntry,
    OrdinaryRunExecutionBaseline,
    OperationContext,
    RunStatus,
    StartRunRequest,
    SubmitFollowupRequest,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CancelQueuedRunInput,
    PromoteQueuedRunInput,
    StartGovernedRunInput,
    TerminalCloseoutInput,
    accept_worker_running_in_transaction,
    cancel_queued_in_transaction,
    promote_queued_run_in_transaction,
    start_governed_run_with_starting_attempt_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_SESSIONS,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_run_by_id,
)
from dayu.host.durable.transaction import (
    HostRow,
    HostTransaction,
    HostTransactionOperation,
    HostTransactionRunner,
)
from dayu.host.terminal_post_commit import TerminalPostCommitNotice


class _DiscardTerminalPort:
    """多进程 durable 测试的显式 no-local-delivery 最终端点。"""

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """消费 exact terminal notice。

        :param notice: 已提交通知。
        :returns: ``None``。
        """

        del notice

_PROCESS_COUNT = 4
_START_GATE_TIMEOUT_SECONDS = 5.0
_START_GATE_POLL_SECONDS = 0.005
_NOW = datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC)
_CALLER_DIGEST = sha256_digest_json({"caller": "admission-multiprocess"})
_SCOPE = "workspace"
_SLOT_KEY = "multiprocess"
_DEFAULT_TARGET = "target-default"
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class _QueuedRunSummary:
    """queued Run 的验证摘要。

    :param run_id: Run id。
    :param accepted_event_sequence: ``RUN_ACCEPTED`` event sequence。
    """

    run_id: str
    accepted_event_sequence: int


@dataclass(frozen=True, slots=True)
class _BarrierWriteOperation(Generic[T]):
    """在 operation 分类完成、transaction commit 前建立进程 barrier。

    :param operation: 原始 typed write operation。
    :param control: parent/child duplex control pipe。
    """

    operation: HostTransactionOperation[T]
    control: Connection

    def __call__(self, transaction: HostTransaction) -> T:
        """执行 operation 后等待 parent 允许 transaction commit。

        :param transaction: 当前已持有 SQLite write lock 的 transaction。
        :returns: 原始 operation result。
        :raises RuntimeError: parent 发送未知 barrier command 时抛出。
        :raises Exception: 原始 operation 失败时透传。
        """

        result = self.operation(transaction)
        self.control.send(("classified",))
        command = self.control.recv()
        if command != ("continue",):
            raise RuntimeError("unexpected cancel snapshot barrier command")
        return result


class _RecordingAdmissionWakeupPort:
    """记录 admission commit 后 typed wake 的测试端口。"""

    def __init__(self) -> None:
        """初始化空 wake 记录。

        :returns: ``None``。
        """

        self.dispatches: list[PendingDispatchRecord] = []
        self.promotions: list[str] = []
        self.watchdog_wake_count = 0

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """记录 matching dispatch wake。

        :param record: durable snapshot 派生的 pending dispatch。
        :returns: ``None``。
        """

        self.dispatches.append(record)

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 pre-start governance wake。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        """

        self.promotions.append(session_id)

    def wake_active_cancel_watchdog(self) -> None:
        """记录 active cancel watchdog wake。

        :returns: ``None``。
        """

        self.watchdog_wake_count += 1

    def clear(self) -> None:
        """清空全部 wake 记录。

        :returns: ``None``。
        """

        self.dispatches.clear()
        self.promotions.clear()
        self.watchdog_wake_count = 0


def test_multiprocess_same_slot_ensure_returns_one_bound_session(
    tmp_path: Path,
) -> None:
    """同一 slot 的多进程 ensure 只产生一个 durable Session binding。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    _bootstrap_store(db_path, artifact_root)

    processes = tuple(
        Process(
            target=_ensure_session_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                worker_index,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    _run_processes(processes, start_gate)

    session_ids = tuple(
        _read_worker_fields(result_dir, worker_index)[1]
        for worker_index in range(_PROCESS_COUNT)
    )
    assert len(frozenset(session_ids)) == 1

    with open_host_durable_store(_options(db_path, artifact_root)) as store:

        def operation(transaction: HostTransaction) -> tuple[int, int, str]:
            """读取 Session / slot durable 结果。

            :param transaction: Host transaction。
            :returns: Session row 数、slot row 数、slot 绑定 Session id。
            """

            row = _require_one(
                transaction,
                f"""
                SELECT session_id
                FROM {TABLE_HOST_SESSION_SLOTS}
                WHERE scope = ? AND slot_key = ?
                """,
                (_SCOPE, _SLOT_KEY),
            )
            return (
                _count_rows(transaction, TABLE_HOST_SESSIONS),
                _count_rows(transaction, TABLE_HOST_SESSION_SLOTS),
                _required_text(row, "session_id"),
            )

        session_count, slot_count, bound_session_id = (
            store.transaction_runner.run_write(operation)
        )
        assert session_count == 1
        assert slot_count == 1
        assert bound_session_id == session_ids[0]
        _assert_event_sequences_global_unique_and_increasing(store.transaction_runner)


def test_multiprocess_same_session_admission_keeps_one_active_run(
    tmp_path: Path,
) -> None:
    """同一 Session 的并发 start/follow-up 至多留下一个 active Run。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    session_id = _seed_session(db_path, artifact_root)

    processes = tuple(
        Process(
            target=_mixed_admission_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                session_id,
                worker_index,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    _run_processes(processes, start_gate)

    run_ids = tuple(
        _read_worker_fields(result_dir, worker_index)[2]
        for worker_index in range(_PROCESS_COUNT)
    )
    assert len(frozenset(run_ids)) == _PROCESS_COUNT

    with open_host_durable_store(_options(db_path, artifact_root)) as store:

        def operation(transaction: HostTransaction) -> tuple[int, int, int, int]:
            """读取 admission 后的 Run / Attempt 计数。

            :param transaction: Host transaction。
            :returns: total Run、accepted Run、queued Run、Attempt row 数。
            """

            return (
                _count_rows(transaction, TABLE_HOST_RUNS),
                _count_rows(
                    transaction,
                    TABLE_HOST_RUNS,
                    "WHERE session_id = ? AND status = ?",
                    (session_id, RunStatus.ACCEPTED.value),
                ),
                _count_rows(
                    transaction,
                    TABLE_HOST_RUNS,
                    "WHERE session_id = ? AND status = ?",
                    (session_id, RunStatus.QUEUED.value),
                ),
                _count_rows(transaction, TABLE_HOST_ATTEMPTS),
            )

        total_runs, accepted_runs, queued_runs, attempt_count = (
            store.transaction_runner.run_write(operation)
        )
        assert total_runs == _PROCESS_COUNT
        assert accepted_runs == 1
        assert queued_runs == _PROCESS_COUNT - 1
        assert attempt_count == 0
        _assert_event_sequences_global_unique_and_increasing(store.transaction_runner)


def test_multiprocess_duplicate_followup_idempotency_returns_one_result_and_conflicts(
    tmp_path: Path,
) -> None:
    """同 Session / client_request_id 跨进程重放返回同一 Run，变更 digest 冲突。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    session_id = _seed_session_with_active_run(db_path, artifact_root)

    processes = tuple(
        Process(
            target=_duplicate_followup_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                session_id,
                worker_index,
                "same input",
                "ok",
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    _run_processes(processes, start_gate)

    duplicated_run_ids = tuple(
        _read_worker_fields(result_dir, worker_index)[2]
        for worker_index in range(_PROCESS_COUNT)
    )
    assert len(frozenset(duplicated_run_ids)) == 1

    conflict_gate = tmp_path / "conflict-gate"
    conflict_process = Process(
        target=_duplicate_followup_worker,
        args=(
            str(db_path),
            str(artifact_root),
            str(result_dir),
            str(conflict_gate),
            session_id,
            _PROCESS_COUNT,
            "changed input",
            "conflict",
        ),
    )
    _run_processes((conflict_process,), conflict_gate)
    conflict_fields = _read_worker_fields(result_dir, _PROCESS_COUNT)
    assert conflict_fields == ("conflict", HostApiErrorCode.IDEMPOTENCY_CONFLICT.value)

    with open_host_durable_store(_options(db_path, artifact_root)) as store:

        def operation(transaction: HostTransaction) -> tuple[int, int]:
            """读取幂等场景下的 queued Run 与同 key row 数。

            :param transaction: Host transaction。
            :returns: queued Run 数、指定 client_request_id 的 Run 数。
            """

            return (
                _count_rows(
                    transaction,
                    TABLE_HOST_RUNS,
                    "WHERE status = ?",
                    (RunStatus.QUEUED.value,),
                ),
                _count_rows(
                    transaction,
                    TABLE_HOST_RUNS,
                    "WHERE client_request_id = ?",
                    ("follow-duplicate",),
                ),
            )

        queued_count, duplicate_key_run_count = store.transaction_runner.run_write(
            operation
        )
        assert queued_count == 1
        assert duplicate_key_run_count == 1
        _assert_event_sequences_global_unique_and_increasing(store.transaction_runner)


def test_multiprocess_queued_followups_promote_by_accepted_sequence(
    tmp_path: Path,
) -> None:
    """多进程 queued follow-up 释放 active 后按 accepted event_sequence FIFO promotion。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    active_run_id, active_attempt_id, session_id = _seed_active_run_tuple(
        db_path, artifact_root
    )

    processes = tuple(
        Process(
            target=_unique_followup_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                session_id,
                worker_index,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    _run_processes(processes, start_gate)

    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        queued_before = _read_queued_runs(store.transaction_runner, session_id)
        assert len(queued_before) == _PROCESS_COUNT
        first_queued = queued_before[0]

        service = _admission_service(store.transaction_runner)
        result = service.closeout_attempt_terminal(
            CloseoutAttemptTerminalInput(
                run_id=active_run_id,
                attempt_id=active_attempt_id,
                attempt_terminal_status=AttemptStatus.SUCCEEDED,
                run_terminal_status=RunStatus.SUCCEEDED,
                terminal_summary_ref=None,
                terminal_summary_digest=None,
            )
        )

        assert result.terminal_notice.wake_queue_promotion is True
        promotion = service.promote_next_queued_run(session_id)

        assert promotion.promoted_run is not None
        assert promotion.promoted_run.run_id == first_queued.run_id
        assert _read_run_status(store.transaction_runner, first_queued.run_id) == (
            RunStatus.RUNNING.value
        )
        _assert_accepted_sequences_are_sorted(queued_before)
        _assert_event_sequences_global_unique_and_increasing(store.transaction_runner)


def test_multiprocess_cancel_queued_vs_promotion_first_committer_wins(
    tmp_path: Path,
) -> None:
    """queued cancel 与 promotion 并发时只有先提交者能改写 queued Run。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    queued_run_id, session_id = _seed_single_eligible_queued_run(db_path, artifact_root)

    processes = (
        Process(
            target=_cancel_queued_transition_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                queued_run_id,
            ),
        ),
        Process(
            target=_promote_transition_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                session_id,
            ),
        ),
    )
    _run_processes(processes, start_gate)

    cancel_fields = _read_named_result(result_dir, "cancel")
    promote_fields = _read_named_result(result_dir, "promote")
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        final_status = _read_run_status(store.transaction_runner, queued_run_id)
        event_types = _event_types_for_run(store.transaction_runner, queued_run_id)

        if final_status == RunStatus.CANCELLED.value:
            assert cancel_fields[1] == "updated"
            assert promote_fields[1] == "not_found"
            assert "RUN_CANCELLED" in event_types
            assert "RUN_STARTED" not in event_types
            assert _count_rows_with_runner(
                store.transaction_runner, TABLE_HOST_ATTEMPTS
            ) == 1
        else:
            assert final_status == RunStatus.RUNNING.value
            assert promote_fields[1] == "updated"
            assert cancel_fields[1] == "invalid_state"
            assert "RUN_STARTED" in event_types
            assert "ATTEMPT_STARTED" in event_types
            assert "RUN_CANCELLED" not in event_types
            assert _count_rows_with_runner(
                store.transaction_runner, TABLE_HOST_ATTEMPTS
            ) == 2
        _assert_event_sequences_global_unique_and_increasing(store.transaction_runner)


def test_multiprocess_admission_event_sequence_is_global_unique_and_increasing(
    tmp_path: Path,
) -> None:
    """多进程 admission 写入后 EventLog event_sequence 全局唯一且无间隙乱序。"""

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    result_dir = tmp_path / "results"
    start_gate = tmp_path / "start-gate"
    result_dir.mkdir()
    session_id = _seed_session_with_active_run(db_path, artifact_root)

    processes = tuple(
        Process(
            target=_unique_followup_worker,
            args=(
                str(db_path),
                str(artifact_root),
                str(result_dir),
                str(start_gate),
                session_id,
                worker_index,
            ),
        )
        for worker_index in range(_PROCESS_COUNT)
    )
    _run_processes(processes, start_gate)

    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        _assert_event_sequences_global_unique_and_increasing(store.transaction_runner)


def test_multiprocess_cancel_error_uses_locked_write_snapshot(
    tmp_path: Path,
) -> None:
    """Attempt 状态在 write snapshot 前后改变时 cancel 只返回对应快照语义。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    before_db = tmp_path / "cancel-before.sqlite3"
    before_artifacts = tmp_path / "cancel-before-artifacts"
    before_run_id, before_attempt_id = _seed_deferred_cancel_snapshot(
        before_db,
        before_artifacts,
        suffix="before",
    )
    mutation_parent, mutation_child = Pipe(duplex=True)
    mutation = Process(
        target=_mark_attempt_running_worker,
        args=(
            str(before_db),
            str(before_artifacts),
            before_attempt_id,
            mutation_child,
        ),
    )
    mutation.start()
    assert mutation_parent.recv() == ("attempting",)
    assert mutation_parent.recv() == ("committed",)
    mutation.join()
    assert mutation.exitcode == 0

    with open_host_durable_store(_options(before_db, before_artifacts)) as store:
        supported = _admission_service(store.transaction_runner).cancel_run(
            before_run_id,
            _cancel_request("cancel-after-attempt-running"),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert supported.run.status is RunStatus.CANCELLING

    after_db = tmp_path / "cancel-after.sqlite3"
    after_artifacts = tmp_path / "cancel-after-artifacts"
    after_run_id, after_attempt_id = _seed_deferred_cancel_snapshot(
        after_db,
        after_artifacts,
        suffix="after",
    )
    cancel_parent, cancel_child = Pipe(duplex=True)
    cancel_process = Process(
        target=_cancel_with_commit_barrier_worker,
        args=(
            str(after_db),
            str(after_artifacts),
            after_run_id,
            cancel_child,
        ),
    )
    cancel_process.start()
    assert cancel_parent.recv() == ("classified",)

    after_mutation_parent, after_mutation_child = Pipe(duplex=True)
    after_mutation = Process(
        target=_mark_attempt_running_worker,
        args=(
            str(after_db),
            str(after_artifacts),
            after_attempt_id,
            after_mutation_child,
        ),
    )
    after_mutation.start()
    assert after_mutation_parent.recv() == ("attempting",)
    cancel_parent.send(("continue",))

    assert cancel_parent.recv() == (
        "error",
        HostApiErrorCode.UNSUPPORTED_OPERATION.value,
    )
    assert after_mutation_parent.recv() == ("committed",)
    cancel_process.join()
    after_mutation.join()
    assert cancel_process.exitcode == 0
    assert after_mutation.exitcode == 0
    assert _read_attempt_status(
        after_db,
        after_artifacts,
        after_attempt_id,
    ) == (
        AttemptStatus.RUNNING.value
    )


def test_idempotent_replay_derives_matching_wake_from_durable_snapshot(
    tmp_path: Path,
) -> None:
    """幂等 replay 对 ACCEPTED/PENDING 重唤醒且不误唤醒已取消记录。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    db_path = tmp_path / "durable.sqlite3"
    artifact_root = tmp_path / "artifacts"
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        wakeup = _RecordingAdmissionWakeupPort()
        service = create_host_admission_service(
            store.transaction_runner,
            terminal_post_commit_port=_DiscardTerminalPort(),
            ordinary_run_baseline=_ordinary_run_baseline(),
            wakeup_port=wakeup,
        )
        request = _start_request(
            session_id=session_id,
            client_request_id="idempotent-wake",
            display_text="idempotent wake",
        )

        accepted = service.start_run(
            request,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert accepted.run.status is RunStatus.ACCEPTED
        assert wakeup.promotions == [session_id]
        assert wakeup.dispatches == []

        wakeup.clear()
        accepted_replay = service.start_run(
            request,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert accepted_replay.idempotent_replay is True
        assert wakeup.promotions == [session_id]
        assert wakeup.dispatches == []

        attempt_id = _start_governed_pending(
            store.transaction_runner,
            run_id=accepted.run.run_id,
            expected_status=RunStatus.ACCEPTED,
            id_suffix="idempotent-wake",
        )
        wakeup.clear()
        pending_replay = service.start_run(
            request,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert pending_replay.idempotent_replay is True
        assert len(wakeup.dispatches) == 1
        pending = wakeup.dispatches[0]
        assert pending.run_id == accepted.run.run_id
        assert pending.attempt_id == attempt_id
        assert pending.dispatch_record_id == (
            pending_replay.dispatch_record.dispatch_record_id
            if pending_replay.dispatch_record is not None
            else ""
        )
        assert wakeup.promotions == []

        cancel_request = CancelRunRequest(
            context=_context(),
            client_request_id="cancel-idempotent-wake",
            reason="cancel_before_worker_accept",
            mode=CancelMode.GRACEFUL,
        )
        cancel_digest = sha256_digest_json(
            {"caller": "cancel-idempotent-wake"}
        )
        first_cancel = service.cancel_run(
            accepted.run.run_id,
            cancel_request,
            caller_semantic_digest=cancel_digest,
        )
        assert first_cancel.terminal_notice is not None
        assert first_cancel.terminal_notice.wake_queue_promotion is True

        wakeup.clear()
        cancel_replay = service.cancel_run(
            accepted.run.run_id,
            cancel_request,
            caller_semantic_digest=cancel_digest,
        )
        assert cancel_replay.idempotent_replay is True
        assert cancel_replay.terminal_notice is not None
        assert cancel_replay.terminal_notice.wake_queue_promotion is False
        assert wakeup.promotions == []

        terminal_loser = service.cancel_run(
            accepted.run.run_id,
            CancelRunRequest(
                context=_context(),
                client_request_id="cancel-terminal-loser",
                reason="cancel_after_terminal",
                mode=CancelMode.GRACEFUL,
            ),
            caller_semantic_digest=sha256_digest_json(
                {"caller": "cancel-terminal-loser"}
            ),
        )
        assert terminal_loser.run.status is RunStatus.CANCELLED
        assert terminal_loser.terminal_notice is not None
        assert terminal_loser.terminal_notice.wake_queue_promotion is False
        assert wakeup.promotions == []

        wakeup.clear()
        cancelled_replay = service.start_run(
            request,
            caller_semantic_digest=_CALLER_DIGEST,
        )
        assert cancelled_replay.run.status is RunStatus.CANCELLED
        assert wakeup.dispatches == []
        assert wakeup.promotions == []
        assert wakeup.watchdog_wake_count == 0


def _options(db_path: Path, artifact_root: Path) -> HostDurableStoreOptions:
    """构造多进程 Host durable store options。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=db_path,
        payload_policy=PayloadStoragePolicy(artifact_root=artifact_root),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=3.0,
            write_busy_retry_count=80,
            write_retry_initial_delay_seconds=0.002,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.03,
        ),
    )


def _admission_service(
    transaction_runner: HostTransactionRunner,
) -> HostAdmissionService:
    """构造带 ordinary baseline 的 admission service。

    :param transaction_runner: Host transaction runner。
    :returns: Host admission service。
    """

    return create_host_admission_service(
        transaction_runner,
        terminal_post_commit_port=_DiscardTerminalPort(),
        ordinary_run_baseline=_ordinary_run_baseline(),
    )


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 multiprocess cancel request。

    :param client_request_id: client request id。
    :returns: cancel request。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="cancel_snapshot_race",
        mode=CancelMode.GRACEFUL,
    )


def _seed_deferred_cancel_snapshot(
    db_path: Path,
    artifact_root: Path,
    *,
    suffix: str,
) -> tuple[str, str]:
    """创建 RUNNING/STARTING 且缺 dispatch 的 deferred cancel snapshot。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :param suffix: 测试 identity 后缀。
    :returns: Run id 与 Attempt id。
    """

    run_id = ""
    attempt_id = ""
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        accepted = _admission_service(store.transaction_runner).start_run(
            _start_request(
                session_id=session_id,
                client_request_id=f"start-cancel-snapshot-{suffix}",
                display_text="cancel snapshot",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        attempt_id = _start_governed_pending(
            store.transaction_runner,
            run_id=accepted.run.run_id,
            expected_status=RunStatus.ACCEPTED,
            id_suffix=f"cancel-snapshot-{suffix}",
        )

        def delete_dispatch(transaction: HostTransaction) -> None:
            """删除 current Attempt 的 child dispatch row。

            :param transaction: 当前 Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                f"""
                DELETE FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            )

        store.transaction_runner.run_write(delete_dispatch)
        run_id = accepted.run.run_id
    assert run_id != ""
    assert attempt_id != ""
    return run_id, attempt_id


def _cancel_with_commit_barrier_worker(
    db_path_text: str,
    artifact_root_text: str,
    run_id: str,
    control: Connection,
) -> None:
    """子进程：在 cancel 分类完成、commit 前持锁等待 parent。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param run_id: 目标 Run id。
    :param control: parent/child control pipe。
    :returns: ``None``。
    """

    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:
        original_run_write = HostTransactionRunner.run_write

        def run_write_with_barrier(
            self: HostTransactionRunner,
            operation: HostTransactionOperation[T],
        ) -> T:
            """把 service write operation 包装为 commit barrier。

            :param self: transaction runner。
            :param operation: typed write operation。
            :returns: 原始 operation result。
            :raises Exception: transaction 或 barrier 失败时透传。
            """

            return original_run_write(
                self,
                _BarrierWriteOperation(operation=operation, control=control),
            )

        with patch.object(
            HostTransactionRunner,
            "run_write",
            run_write_with_barrier,
        ):
            try:
                result = _admission_service(store.transaction_runner).cancel_run(
                    run_id,
                    _cancel_request("cancel-held-snapshot"),
                    caller_semantic_digest=_CALLER_DIGEST,
                )
            except HostApiError as exc:
                control.send(("error", exc.code.value))
            else:
                control.send(("result", result.run.status.value))


def _mark_attempt_running_worker(
    db_path_text: str,
    artifact_root_text: str,
    attempt_id: str,
    control: Connection,
) -> None:
    """子进程：尝试把 deferred STARTING Attempt 改为 RUNNING。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param attempt_id: 目标 Attempt id。
    :param control: parent/child control pipe。
    :returns: ``None``。
    """

    control.send(("attempting",))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:

        def operation(transaction: HostTransaction) -> None:
            """在独立 write transaction 更新 Attempt 状态。

            :param transaction: 当前 Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_ATTEMPTS}
                SET status = ?, updated_at = ?
                WHERE attempt_id = ? AND status = ?
                """,
                (
                    AttemptStatus.RUNNING.value,
                    _NOW.isoformat(),
                    attempt_id,
                    AttemptStatus.STARTING.value,
                ),
            )

        store.transaction_runner.run_write(operation)
    control.send(("committed",))


def _read_attempt_status(
    db_path: Path,
    artifact_root: Path,
    attempt_id: str,
) -> str:
    """读取 Attempt status 文本。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :param attempt_id: 目标 Attempt id。
    :returns: durable status 文本。
    :raises AssertionError: Attempt 缺失时抛出。
    """

    status = ""
    with open_host_durable_store(_options(db_path, artifact_root)) as store:

        def operation(transaction: HostTransaction) -> str:
            """读取目标 Attempt status。

            :param transaction: 当前 Host transaction。
            :returns: status 文本。
            :raises AssertionError: row 缺失时抛出。
            """

            row = transaction.fetchone(
                f"""
                SELECT status
                FROM {TABLE_HOST_ATTEMPTS}
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            )
            assert row is not None
            return _required_text(row, "status")

        status = store.transaction_runner.run_read(operation)
    assert status != ""
    return status


def _ordinary_run_baseline() -> OrdinaryRunExecutionBaseline:
    """构造多进程 follow-up 测试用 ordinary Run 执行基线。

    :returns: OrdinaryRunExecutionBaseline。
    """

    return OrdinaryRunExecutionBaseline(
        runner_spec=RunnerSpec(
            provider="test",
            model="multiprocess-baseline",
            endpoint="https://example.invalid",
            api_key_ref="secret:multiprocess",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=1.0,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
    )


def _bootstrap_store(db_path: Path, artifact_root: Path) -> None:
    """初始化测试 DB schema。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(db_path, artifact_root)):
        return


def _seed_session(db_path: Path, artifact_root: Path) -> str:
    """创建一个测试 Session。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: Session id。
    """

    session_id = ""
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
    assert session_id != ""
    return session_id


def _seed_session_with_active_run(db_path: Path, artifact_root: Path) -> str:
    """创建一个带 active Run 的测试 Session。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: Session id。
    """

    active_run_id, _active_attempt_id, session_id = _seed_active_run_tuple(
        db_path, artifact_root
    )
    assert active_run_id != ""
    return session_id


def _seed_active_run_tuple(
    db_path: Path, artifact_root: Path
) -> tuple[str, str, str]:
    """创建 Session 与 active Run。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: active Run id、Attempt id、Session id。
    """

    active_run_id = ""
    active_attempt_id = ""
    session_id = ""
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _admission_service(store.transaction_runner)
        active = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-active",
                display_text="active input",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        active_run_id = active.run.run_id
        active_attempt_id = _start_governed_active(
            store.transaction_runner,
            run_id=active_run_id,
            expected_status=RunStatus.ACCEPTED,
            id_suffix="active",
        )
    assert active_run_id != ""
    assert active_attempt_id != ""
    assert session_id != ""
    return active_run_id, active_attempt_id, session_id


def _seed_single_eligible_queued_run(
    db_path: Path, artifact_root: Path
) -> tuple[str, str]:
    """创建一个已释放 active slot 且可被 cancel/promotion 竞争的 queued Run。

    :param db_path: SQLite DB 路径。
    :param artifact_root: artifact 根目录。
    :returns: queued Run id、Session id。
    """

    queued_run_id = ""
    session_id = ""
    with open_host_durable_store(_options(db_path, artifact_root)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        service = _admission_service(store.transaction_runner)
        active = service.start_run(
            _start_request(
                session_id=session_id,
                client_request_id="start-active",
                display_text="active input",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        queued = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id="follow-race",
                    display_text="race queued",
                ),
                resolved_execution_target=_DEFAULT_TARGET,
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        active_attempt_id = _start_governed_active(
            store.transaction_runner,
            run_id=active.run.run_id,
            expected_status=RunStatus.ACCEPTED,
            id_suffix="race-active",
        )

        def closeout(transaction: HostTransaction) -> None:
            """只释放 active slot，不执行 admission 层自动 promotion。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=active.run.run_id,
                    attempt_id=active_attempt_id,
                    attempt_terminal_event_id="event-active-attempt-succeeded",
                    run_terminal_event_id="event-active-run-succeeded",
                    attempt_terminal_status=AttemptStatus.SUCCEEDED,
                    run_terminal_status=RunStatus.SUCCEEDED,
                    occurred_at=_NOW,
                    actor="host",
                    source="multiprocess-test",
                    reason="seed_release_active",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )

        store.transaction_runner.run_write(closeout)
        queued_run_id = queued.run.run_id
    assert queued_run_id != ""
    assert session_id != ""
    return queued_run_id, session_id


def _start_governed_active(
    transaction_runner: HostTransactionRunner,
    *,
    run_id: str,
    expected_status: RunStatus,
    id_suffix: str,
) -> str:
    """把 accepted/queued Run 启动为 active Attempt。

    :param transaction_runner: Host transaction runner。
    :param run_id: 目标 Run id。
    :param expected_status: 启动前期望 Run 状态。
    :param id_suffix: 测试 id 后缀。
    :returns: 新建 Attempt id。
    :raises AssertionError: transition 未创建 Attempt 时抛出。
    """

    attempt_id = f"attempt-{id_suffix}"

    def operation(transaction: HostTransaction) -> str:
        """执行 governed start transition。

        :param transaction: Host transaction。
        :returns: 新建 Attempt id。
        """

        result = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            StartGovernedRunInput(
                run_id=run_id,
                expected_status=expected_status,
                run_started_event_id=f"event-run-started-{id_suffix}",
                attempt_started_event_id=f"event-attempt-started-{id_suffix}",
                attempt_id=attempt_id,
                execution_id=f"execution-{id_suffix}",
                dispatch_record_id=f"dispatch-{id_suffix}",
                occurred_at=_NOW,
                actor="host.dispatch",
                source="multiprocess-test",
                start_reason=(
                    RunStartReason.INITIAL
                    if expected_status is RunStatus.ACCEPTED
                    else RunStartReason.QUEUE_PROMOTION
                ),
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
            ),
        )
        assert result.attempt is not None
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-admission-multiprocess",
                pid=os.getpid(),
                process_start_token="admission-multiprocess-test",
                boot_id=None,
            ),
        )
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-admission-multiprocess",
            lane_name="llm",
            waiting_for_lane_at="2026-05-14T10:00:00.000000Z",
        )
        assert waiting.status == StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-admission-multiprocess",
            lane_name="llm",
            lane_claim_id=f"claim-{id_suffix}",
            lane_owner_id="owner-admission-multiprocess",
            lane_acquired_at="2026-05-14T10:00:00.000000Z",
            dispatching_at="2026-05-14T10:00:00.000000Z",
        )
        assert dispatching.status == StateMutationStatus.UPDATED
        accepted = accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=run_id,
                attempt_id=attempt_id,
                attempt_running_event_id=f"event-attempt-running-{id_suffix}",
                occurred_at=_NOW,
                actor="host.dispatch",
                source="multiprocess-test",
                worker_accept_reason="local_worker_accepted",
                local_worker_id=f"local-worker-{id_suffix}",
            ),
        )
        assert accepted.status == StateMutationStatus.UPDATED
        return result.attempt.attempt_id

    return transaction_runner.run_write(operation)


def _start_governed_pending(
    transaction_runner: HostTransactionRunner,
    *,
    run_id: str,
    expected_status: RunStatus,
    id_suffix: str,
) -> str:
    """把 Run 启动到尚未消费 wake 的 PENDING dispatch snapshot。

    :param transaction_runner: Host transaction runner。
    :param run_id: 目标 Run id。
    :param expected_status: 启动前 Run 状态。
    :param id_suffix: 稳定测试 id 后缀。
    :returns: 新建 current Attempt id。
    :raises AssertionError: transition 未创建完整 pending snapshot 时抛出。
    """

    attempt_id = f"attempt-{id_suffix}"

    def operation(transaction: HostTransaction) -> str:
        """在单事务创建 PENDING dispatch snapshot。

        :param transaction: 当前 Host transaction。
        :returns: 新建 Attempt id。
        :raises AssertionError: transition row 不完整时抛出。
        """

        result = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            StartGovernedRunInput(
                run_id=run_id,
                expected_status=expected_status,
                run_started_event_id=f"event-run-started-{id_suffix}",
                attempt_started_event_id=f"event-attempt-started-{id_suffix}",
                attempt_id=attempt_id,
                execution_id=f"execution-{id_suffix}",
                dispatch_record_id=f"dispatch-{id_suffix}",
                occurred_at=_NOW,
                actor="host.dispatch",
                source="multiprocess-test",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
            ),
        )
        assert result.attempt is not None
        assert result.dispatch_record is not None
        return result.attempt.attempt_id

    return transaction_runner.run_write(operation)


def _run_processes(processes: tuple[Process, ...], start_gate: Path) -> None:
    """启动进程、打开 start gate 并校验退出码。

    :param processes: 待运行进程。
    :param start_gate: 文件 gate 路径。
    :returns: ``None``。
    """

    for process in processes:
        process.start()
    start_gate.write_text("start", encoding="utf-8")
    for process in processes:
        process.join()
        assert process.exitcode == 0


def _wait_for_start_gate(start_gate: Path) -> None:
    """等待父进程打开文件 gate。

    :param start_gate: 文件 gate 路径。
    :returns: ``None``。
    :raises TimeoutError: 等待超时时抛出。
    """

    deadline = time.monotonic() + _START_GATE_TIMEOUT_SECONDS
    while not start_gate.exists():
        if time.monotonic() > deadline:
            raise TimeoutError("multiprocess test start gate timeout")
        time.sleep(_START_GATE_POLL_SECONDS)


def _ensure_session_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    worker_index: int,
) -> None:
    """子进程：ensure 同一 Session slot。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param start_gate_text: start gate 路径文本。
    :param worker_index: worker 序号。
    :returns: ``None``。
    """

    _wait_for_start_gate(Path(start_gate_text))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:
        result = ensure_session(store.transaction_runner, _ensure_request())
        _write_worker_result(
            Path(result_dir_text),
            worker_index,
            ("ok", result.snapshot.session_id),
        )


def _mixed_admission_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    session_id: str,
    worker_index: int,
) -> None:
    """子进程：并发执行 start_run 或 submit_followup(queue)。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param start_gate_text: start gate 路径文本。
    :param session_id: 目标 Session id。
    :param worker_index: worker 序号。
    :returns: ``None``。
    """

    _wait_for_start_gate(Path(start_gate_text))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:
        service = _admission_service(store.transaction_runner)
        if worker_index % 2 == 0:
            result = service.start_run(
                _start_request(
                    session_id=session_id,
                    client_request_id=f"start-{worker_index}",
                    display_text=f"start input {worker_index}",
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )
            kind = "start"
        else:
            result = service.submit_followup_queue(
                SubmitFollowupQueueAdmissionInput(
                    request=_followup_request(
                        session_id=session_id,
                        client_request_id=f"follow-{worker_index}",
                        display_text=f"follow input {worker_index}",
                    ),
                    resolved_execution_target=_DEFAULT_TARGET,
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )
            kind = "follow"
        _write_worker_result(
            Path(result_dir_text),
            worker_index,
            (kind, result.run.status.value, result.run.run_id),
        )


def _duplicate_followup_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    session_id: str,
    worker_index: int,
    display_text: str,
    mode: str,
) -> None:
    """子进程：执行同一 follow-up 幂等 key 的重放或冲突请求。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param start_gate_text: start gate 路径文本。
    :param session_id: 目标 Session id。
    :param worker_index: worker 序号。
    :param display_text: follow-up 输入文本。
    :param mode: ``ok`` 或 ``conflict``。
    :returns: ``None``。
    :raises AssertionError: mode 不合法或冲突错误码不符合预期时抛出。
    """

    _wait_for_start_gate(Path(start_gate_text))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:
        service = _admission_service(store.transaction_runner)
        try:
            result = service.submit_followup_queue(
                SubmitFollowupQueueAdmissionInput(
                    request=_followup_request(
                        session_id=session_id,
                        client_request_id="follow-duplicate",
                        display_text=display_text,
                    ),
                    resolved_execution_target=_DEFAULT_TARGET,
                ),
                caller_semantic_digest=_CALLER_DIGEST,
            )
        except HostApiError as exc:
            if mode != "conflict" or exc.code != HostApiErrorCode.IDEMPOTENCY_CONFLICT:
                raise
            _write_worker_result(
                Path(result_dir_text),
                worker_index,
                ("conflict", exc.code.value),
            )
            return
        if mode != "ok":
            raise AssertionError("duplicate follow-up conflict was not raised")
        _write_worker_result(
            Path(result_dir_text),
            worker_index,
            ("ok", result.run.status.value, result.run.run_id),
        )


def _unique_followup_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    session_id: str,
    worker_index: int,
) -> None:
    """子进程：提交唯一 client_request_id 的 follow-up queue。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param start_gate_text: start gate 路径文本。
    :param session_id: 目标 Session id。
    :param worker_index: worker 序号。
    :returns: ``None``。
    """

    _wait_for_start_gate(Path(start_gate_text))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:
        service = _admission_service(store.transaction_runner)
        result = service.submit_followup_queue(
            SubmitFollowupQueueAdmissionInput(
                request=_followup_request(
                    session_id=session_id,
                    client_request_id=f"follow-unique-{worker_index}",
                    display_text=f"queued input {worker_index}",
                ),
                resolved_execution_target=f"target-{worker_index}",
            ),
            caller_semantic_digest=_CALLER_DIGEST,
        )
        _write_worker_result(
            Path(result_dir_text),
            worker_index,
            ("ok", result.run.status.value, result.run.run_id),
        )


def _cancel_queued_transition_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    run_id: str,
) -> None:
    """子进程：用低层 transition 尝试取消 queued Run。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param start_gate_text: start gate 路径文本。
    :param run_id: queued Run id。
    :returns: ``None``。
    """

    _wait_for_start_gate(Path(start_gate_text))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:

        def operation(transaction: HostTransaction) -> str:
            """执行 queued cancel transition。

            :param transaction: Host transaction。
            :returns: transition status。
            """

            result = cancel_queued_in_transaction(
                transaction,
                EventLogStore(),
                CancelQueuedRunInput(
                    run_id=run_id,
                    cancel_request_event_id="event-cancel-requested",
                    run_cancelled_event_id="event-run-cancelled",
                    occurred_at=_NOW,
                    actor="analyst",
                    source="multiprocess-test",
                    client_request_id="cancel-race",
                    idempotency_key="cancel-race",
                    reason="race_cancel",
                    mode=CancelMode.GRACEFUL,
                    call_context_digest=sha256_digest_json({"context": "cancel"}),
                ),
            )
            return result.status.value

        status = store.transaction_runner.run_write(operation)
        _write_named_result(Path(result_dir_text), "cancel", ("cancel", status))


def _promote_transition_worker(
    db_path_text: str,
    artifact_root_text: str,
    result_dir_text: str,
    start_gate_text: str,
    session_id: str,
) -> None:
    """子进程：用低层 transition 尝试 promotion 最早 queued Run。

    :param db_path_text: SQLite DB 路径文本。
    :param artifact_root_text: artifact 根目录文本。
    :param result_dir_text: 结果目录文本。
    :param start_gate_text: start gate 路径文本。
    :param session_id: Session id。
    :returns: ``None``。
    """

    _wait_for_start_gate(Path(start_gate_text))
    with open_host_durable_store(
        _options(Path(db_path_text), Path(artifact_root_text))
    ) as store:

        def operation(transaction: HostTransaction) -> str:
            """执行 queued promotion transition。

            :param transaction: Host transaction。
            :returns: transition status。
            """

            result = promote_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                PromoteQueuedRunInput(
                    session_id=session_id,
                    run_started_event_id="event-race-run-started",
                    attempt_started_event_id="event-race-attempt-started",
                    attempt_id="attempt-race-promoted",
                    execution_id="execution-race-promoted",
                    dispatch_record_id="dispatch-race-promoted",
                    occurred_at=_NOW,
                    actor="host",
                    source="multiprocess-test",
                    worker_kind=WorkerKind.LOCAL,
                    owner_host_instance_id=None,
                ),
            )
            return result.status.value

        status = store.transaction_runner.run_write(operation)
        _write_named_result(Path(result_dir_text), "promote", ("promote", status))


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """创建或读取固定 slot 的 Session id。

    :param transaction_runner: Host transaction runner。
    :returns: Session id。
    """

    result = ensure_session(transaction_runner, _ensure_request())
    return result.snapshot.session_id


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(
        scope=_SCOPE,
        slot_key=_SLOT_KEY,
        metadata=(HostMetadataEntry(key="case", value="admission-multiprocess"),),
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
            operation_name="admission_multiprocess_test",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase3",
            correlation_id="corr-admission-multiprocess",
        ),
    )


def _start_request(
    *,
    session_id: str,
    client_request_id: str,
    display_text: str,
) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param display_text: 输入展示文本。
    :returns: StartRunRequest。
    """

    return StartRunRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=HostInput(display_text=display_text, payload_ref=None, payload_digest=None),
        execution_target=_DEFAULT_TARGET,
        queue_policy="queue",
    )


def _followup_request(
    *,
    session_id: str,
    client_request_id: str,
    display_text: str,
) -> SubmitFollowupRequest:
    """构造 follow-up queue 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param display_text: 输入展示文本。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt=display_text,
        tool_names=None,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _write_worker_result(
    result_dir: Path, worker_index: int, fields: tuple[str, ...]
) -> None:
    """写入 worker 结果文件。

    :param result_dir: 结果目录。
    :param worker_index: worker 序号。
    :param fields: 结果字段。
    :returns: ``None``。
    """

    _write_named_result(result_dir, f"worker-{worker_index}", fields)


def _write_named_result(result_dir: Path, name: str, fields: tuple[str, ...]) -> None:
    """写入命名结果文件。

    :param result_dir: 结果目录。
    :param name: 文件名 stem。
    :param fields: 结果字段。
    :returns: ``None``。
    """

    (result_dir / f"{name}.txt").write_text("|".join(fields), encoding="utf-8")


def _read_worker_fields(result_dir: Path, worker_index: int) -> tuple[str, ...]:
    """读取 worker 结果字段。

    :param result_dir: 结果目录。
    :param worker_index: worker 序号。
    :returns: 结果字段。
    """

    return _read_named_result(result_dir, f"worker-{worker_index}")


def _read_named_result(result_dir: Path, name: str) -> tuple[str, ...]:
    """读取命名结果字段。

    :param result_dir: 结果目录。
    :param name: 文件名 stem。
    :returns: 结果字段。
    """

    return tuple((result_dir / f"{name}.txt").read_text(encoding="utf-8").split("|"))


def _count_rows(
    transaction: HostTransaction,
    table_name: str,
    where_sql: str = "",
    parameters: tuple[None | int | float | str | bytes, ...] = (),
) -> int:
    """读取指定表的 row count。

    :param transaction: Host transaction。
    :param table_name: 表名。
    :param where_sql: 可选 WHERE 子句。
    :param parameters: WHERE 参数。
    :returns: row count。
    """

    row = _require_one(
        transaction,
        f"SELECT COUNT(*) AS total FROM {table_name} {where_sql}",
        parameters,
    )
    return _required_int(row, "total")


def _count_rows_with_runner(
    transaction_runner: HostTransactionRunner, table_name: str
) -> int:
    """通过 transaction runner 读取指定表 row count。

    :param transaction_runner: Host transaction runner。
    :param table_name: 表名。
    :returns: row count。
    """

    def operation(transaction: HostTransaction) -> int:
        """读取指定表 row count。

        :param transaction: Host transaction。
        :returns: row count。
        """

        return _count_rows(transaction, table_name)

    return transaction_runner.run_write(operation)


def _read_run_status(transaction_runner: HostTransactionRunner, run_id: str) -> str:
    """读取 Run 当前状态。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run status 文本。
    """

    def operation(transaction: HostTransaction) -> str:
        """读取 Run 状态。

        :param transaction: Host transaction。
        :returns: Run status 文本。
        """

        run = read_run_by_id(transaction, run_id)
        assert run is not None
        return run.status.value

    return transaction_runner.run_write(operation)


def _read_queued_runs(
    transaction_runner: HostTransactionRunner, session_id: str
) -> tuple[_QueuedRunSummary, ...]:
    """按 accepted event sequence 读取 queued Run 摘要。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :returns: queued Run 摘要元组。
    """

    def operation(transaction: HostTransaction) -> tuple[_QueuedRunSummary, ...]:
        """读取 queued Run rows。

        :param transaction: Host transaction。
        :returns: queued Run 摘要元组。
        """

        rows = transaction.fetchall(
            f"""
            SELECT run_id, accepted_event_sequence
            FROM {TABLE_HOST_RUNS}
            WHERE session_id = ? AND status = ?
            ORDER BY accepted_event_sequence ASC, run_id ASC
            """,
            (session_id, RunStatus.QUEUED.value),
        )
        return tuple(
            _QueuedRunSummary(
                run_id=_required_text(row, "run_id"),
                accepted_event_sequence=_required_int(row, "accepted_event_sequence"),
            )
            for row in rows
        )

    return transaction_runner.run_write(operation)


def _event_types_for_run(
    transaction_runner: HostTransactionRunner, run_id: str
) -> tuple[str, ...]:
    """读取某个 Run 的 EventLog event_type 序列。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: event_type 元组。
    """

    def operation(transaction: HostTransaction) -> tuple[str, ...]:
        """读取 EventLog 事件类型。

        :param transaction: Host transaction。
        :returns: event_type 元组。
        """

        rows = transaction.fetchall(
            f"""
            SELECT event_type
            FROM {TABLE_EVENT_LOG}
            WHERE run_id = ?
            ORDER BY event_sequence ASC
            """,
            (run_id,),
        )
        return tuple(_required_text(row, "event_type") for row in rows)

    return transaction_runner.run_write(operation)


def _assert_event_sequences_global_unique_and_increasing(
    transaction_runner: HostTransactionRunner,
) -> None:
    """断言 EventLog sequence 全局唯一且递增连续。

    :param transaction_runner: Host transaction runner。
    :returns: ``None``。
    """

    def operation(transaction: HostTransaction) -> tuple[int, ...]:
        """读取所有 EventLog sequence。

        :param transaction: Host transaction。
        :returns: event_sequence 元组。
        """

        rows = transaction.fetchall(
            f"""
            SELECT event_sequence
            FROM {TABLE_EVENT_LOG}
            ORDER BY event_sequence ASC
            """
        )
        return tuple(_required_int(row, "event_sequence") for row in rows)

    sequences = transaction_runner.run_write(operation)
    assert len(sequences) > 0
    assert len(frozenset(sequences)) == len(sequences)
    assert sequences == tuple(sorted(sequences))
    assert sequences == tuple(range(1, len(sequences) + 1))


def _assert_accepted_sequences_are_sorted(
    queued_runs: tuple[_QueuedRunSummary, ...],
) -> None:
    """断言 queued Run 摘要已按 accepted event sequence 排序。

    :param queued_runs: queued Run 摘要。
    :returns: ``None``。
    """

    sequences = tuple(row.accepted_event_sequence for row in queued_runs)
    assert sequences == tuple(sorted(sequences))
    assert len(frozenset(sequences)) == len(sequences)


def _require_one(
    transaction: HostTransaction,
    sql: str,
    parameters: tuple[None | int | float | str | bytes, ...] = (),
) -> HostRow:
    """执行查询并要求返回一行。

    :param transaction: Host transaction。
    :param sql: SQL query。
    :param parameters: SQL 参数。
    :returns: HostRow。
    :raises AssertionError: 查询无结果时抛出。
    """

    row = transaction.fetchone(sql, parameters)
    assert row is not None
    return row


def _required_text(row: HostRow, column: str) -> str:
    """读取必填文本列。

    :param row: Host row。
    :param column: 列名。
    :returns: 文本值。
    :raises AssertionError: 列值不是 str 时抛出。
    """

    value = row.get(column)
    assert isinstance(value, str)
    return value


def _required_int(row: HostRow, column: str) -> int:
    """读取必填整数列。

    :param row: Host row。
    :param column: 列名。
    :returns: 整数值。
    :raises AssertionError: 列值不是 int 时抛出。
    """

    value = row.get(column)
    assert isinstance(value, int)
    return value
