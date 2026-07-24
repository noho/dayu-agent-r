"""Host Phase 3 Run / Attempt transition primitive 测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

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
from dayu.host.queue_policy import RunQueuePolicy
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
from dayu.host.durable.errors import HostDurableError, HostRowDecodeError
from dayu.host.durable.liveness import HostInstanceStatus
from dayu.host.durable.schema import (
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    ActiveCancelCloseoutInput,
    ActiveCancelWatchdogCloseoutInput,
    CancelActiveAttemptInput,
    CancelPredispatchStartingInput,
    CancelQueuedRunInput,
    CreateQueuedRunInput,
    CreateRunningRunInput,
    ContextRecoveryCloseInput,
    OwnedAttemptCancelTarget,
    RunTransitionResult,
    StartupOrphanCloseInput,
    TerminalCloseoutInput,
    accept_worker_running_in_transaction,
    active_cancel_closeout_in_transaction,
    active_cancel_watchdog_closeout_in_transaction,
    cancel_predispatch_starting_in_transaction,
    cancel_queued_in_transaction,
    close_attempt_for_context_recovery_in_transaction,
    close_startup_orphan_attempt_in_transaction,
    create_queued_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    project_terminal_notice_from_exact_run_event,
    read_exact_owned_attempt_cancel_targets,
    request_active_attempt_cancel_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    AttemptExecutionIdentity,
    DispatchRecordStatus,
    RunMutationResult,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    cancel_queued_run_row,
    cancel_recovering_run_row,
    cancel_running_run_row,
    cancel_starting_dispatch_record_row,
    mark_attempt_running_row,
    mark_dispatch_worker_accepted_row,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_run_by_id,
    terminal_attempt_row,
    terminal_run_row,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host.lifecycle_events import (
    closeout_attempt_terminal_event_type_for_status,
    run_terminal_event_type_for_status,
)

_NOW = datetime(2026, 5, 14, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "run-transition-test"})
_INPUT_DIGEST = sha256_digest_json({"input": "hello"})
_EXACT_CANCEL_MULTI_BATCH_IDENTITY_COUNT = 205
_EXACT_CANCEL_WRONG_OWNER_INDEX = 1
_EXACT_CANCEL_STALE_CURRENT_ATTEMPT_INDEX = 202


class _StaticEventLogStore(EventLogStore):
    """为 strict linked-event 反例返回指定 EventLog row 的测试 store。"""

    def __init__(self, row: EventLogRow | None) -> None:
        """保存后续 read 返回值。

        :param row: 要返回的 EventLog row；``None`` 表示 linked row 缺失。
        :returns: ``None``。
        """

        self._row = row

    def read_event_by_id(
        self,
        transaction: HostTransaction,
        event_id: str,
    ) -> EventLogRow | None:
        """返回预先设置的 row。

        :param transaction: 当前 Host transaction。
        :param event_id: 调用方请求的 event id。
        :returns: 预先设置的 EventLog row。
        :raises Exception: 不主动抛出异常。
        """

        del transaction, event_id
        return self._row


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
            :returns: Run、Attempt、dispatch 状态与 Run cancel link。
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


def test_terminal_closeout_appends_concrete_terminal_events(
    tmp_path: Path,
) -> None:
    """terminal helper 写 exact event，并由 owner 投影同源 notice。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> RunTransitionResult:
            """执行 terminal closeout。

            :param transaction: Host transaction。
            :returns: 携带 stable Run ref 与 exact Run event 的 transition 结果。
            :raises HostDurableError: terminal durable 写入失败时抛出。
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
            assert result.run_event is not None
            return result

        transition = store.transaction_runner.run_write(closeout)
        assert transition.run is not None
        assert transition.attempt is not None
        assert transition.run_event is not None
        assert transition.run.status is RunStatus.SUCCEEDED
        assert transition.attempt.status is AttemptStatus.SUCCEEDED
        notice = project_terminal_notice_from_exact_run_event(
            transition.run,
            transition.run_event,
            wake_queue_promotion=True,
        )
        assert notice.session_id == transition.run.session_id
        assert (
            notice.terminal_event_sequence
            == transition.run_event.event_sequence
            == transition.run.terminal_event_sequence
        )
        assert notice.wake_queue_promotion is True

        with pytest.raises(
            HostDurableError,
            match="exact Run/Event projection is missing a row",
        ):
            project_terminal_notice_from_exact_run_event(
                None,
                transition.run_event,
                wake_queue_promotion=True,
            )
        with pytest.raises(
            HostDurableError,
            match="exact Run/Event projection is missing a row",
        ):
            project_terminal_notice_from_exact_run_event(
                transition.run,
                None,
                wake_queue_promotion=True,
            )
        inconsistent_rows = (
            (
                replace(transition.run, terminal_event_id="different-event"),
                transition.run_event,
            ),
            (
                replace(
                    transition.run,
                    terminal_event_sequence=transition.run_event.event_sequence + 1,
                ),
                transition.run_event,
            ),
            (
                transition.run,
                replace(transition.run_event, session_id="different-session"),
            ),
            (
                transition.run,
                replace(transition.run_event, run_id="different-run"),
            ),
        )
        for inconsistent_run, inconsistent_event in inconsistent_rows:
            with pytest.raises(
                HostDurableError,
                match="exact Run/Event projection rows are inconsistent",
            ):
                project_terminal_notice_from_exact_run_event(
                    inconsistent_run,
                    inconsistent_event,
                    wake_queue_promotion=True,
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


def test_terminal_closeout_status_pair_invariant_uses_lifecycle_owner() -> None:
    """terminal closeout status pair invariant 由 lifecycle owner helper 派生。"""

    expected = tuple(
        (attempt_status, RunStatus(attempt_status.value))
        for attempt_status in AttemptStatus
        if attempt_status
        in (
            AttemptStatus.SUCCEEDED,
            AttemptStatus.FAILED,
            AttemptStatus.CANCELLED,
            AttemptStatus.LOST,
        )
    )
    assert run_transition_module._TERMINAL_STATUS_PAIRS == expected
    for attempt_status, run_status in expected:
        assert run_transition_module._terminal_status_pair_is_compatible(
            attempt_status=attempt_status,
            run_status=run_status,
        )
        assert run_transition_module._attempt_terminal_event_type(
            attempt_status
        ) == closeout_attempt_terminal_event_type_for_status(attempt_status).value
        assert run_transition_module._run_terminal_event_type(
            run_status
        ) == run_terminal_event_type_for_status(run_status).value
    for durable_only_status in (AttemptStatus.SUSPENDED, AttemptStatus.STEERED):
        assert not run_transition_module._terminal_status_pair_is_compatible(
            attempt_status=durable_only_status,
            run_status=RunStatus.SUCCEEDED,
        )


def test_failed_terminal_closeout_payload_includes_client_correlation_id(
    tmp_path: Path,
) -> None:
    """FAILED terminal payload 在 provider request 边界暴露 client correlation。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> tuple[JsonValue, JsonValue]:
            """执行 failed terminal closeout 并读取 payload。

            :param transaction: Host transaction。
            :returns: Attempt 与 Run terminal payload。
            """

            result = terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-failed-provider",
                    run_terminal_event_id="event-run-failed-provider",
                    attempt_terminal_status=AttemptStatus.FAILED,
                    run_terminal_status=RunStatus.FAILED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="provider_error",
                    terminal_summary_ref="summary-ref",
                    terminal_summary_digest=(
                        "sha256:"
                        "0123456789abcdef0123456789abcdef"
                        "0123456789abcdef0123456789abcdef"
                    ),
                    provider_request_id="req-terminal",
                    client_correlation_id="client-terminal",
                    error_code="provider_error",
                    message="provider failed",
                    recoverable=False,
                ),
            )
            assert result.status == StateMutationStatus.UPDATED
            attempt_payload = _event_payload(
                transaction, event_id="event-attempt-failed-provider"
            )
            run_payload = _event_payload(
                transaction, event_id="event-run-failed-provider"
            )
            return (
                attempt_payload["client_correlation_id"],
                run_payload["client_correlation_id"],
            )

        assert store.transaction_runner.run_write(closeout) == (
            "client-terminal",
            "client-terminal",
        )


def test_terminal_closeout_replay_absorbs_same_terminal_status_without_new_events(
    tmp_path: Path,
) -> None:
    """同种 terminal closeout replay 不追加新 terminal event。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> tuple[str, tuple[str, ...]]:
            """执行 terminal closeout。

            :param transaction: Host transaction。
            :returns: transition 状态与 event type 序列。
            """

            result = terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-failed-original",
                    run_terminal_event_id="event-run-failed-original",
                    attempt_terminal_status=AttemptStatus.FAILED,
                    run_terminal_status=RunStatus.FAILED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="phase3_internal_closeout",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            return result.status.value, _event_types(transaction)

        def replay(transaction: HostTransaction) -> tuple[str, tuple[str, ...]]:
            """用不同 event id 重放同种 terminal closeout。

            :param transaction: Host transaction。
            :returns: transition 状态与 event type 序列。
            """

            result = terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-failed-replay",
                    run_terminal_event_id="event-run-failed-replay",
                    attempt_terminal_status=AttemptStatus.FAILED,
                    run_terminal_status=RunStatus.FAILED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="phase3_internal_closeout",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            return result.status.value, _event_types(transaction)

        first_status, first_event_types = store.transaction_runner.run_write(closeout)
        replay_status, replay_event_types = store.transaction_runner.run_write(replay)

        assert first_status == StateMutationStatus.UPDATED.value
        assert replay_status == StateMutationStatus.UPDATED.value
        assert first_event_types == replay_event_types
        assert replay_event_types.count("ATTEMPT_FAILED") == 1
        assert replay_event_types.count("RUN_FAILED") == 1


@pytest.mark.parametrize(
    ("attempt_status", "run_status", "attempt_event_type", "run_event_type"),
        (
            (
                AttemptStatus.SUCCEEDED,
                RunStatus.SUCCEEDED,
                "ATTEMPT_SUCCEEDED",
                "RUN_SUCCEEDED",
            ),
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
def test_terminal_closeout_accepts_compatible_terminal_status_pairs(
    tmp_path: Path,
    attempt_status: AttemptStatus,
    run_status: RunStatus,
    attempt_event_type: str,
    run_event_type: str,
) -> None:
    """terminal closeout 只接受 Attempt / Run 语义一致的终态配对。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)
        if attempt_status is AttemptStatus.CANCELLED:

            def mark_running(transaction: HostTransaction) -> None:
                """将 Attempt 推进到 RUNNING 以满足取消 CAS 源状态。

                :param transaction: Host transaction。
                :returns: ``None``。
                """

                result = mark_attempt_running_row(
                    transaction,
                    attempt_id=seeded.attempt_id,
                    updated_at="2026-05-14T01:02:03.000000Z",
                )
                assert result.status is StateMutationStatus.UPDATED

            store.transaction_runner.run_write(mark_running)

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
                    attempt_terminal_event_id=(
                        f"event-compatible-attempt-{attempt_status.value}"
                    ),
                    run_terminal_event_id=f"event-compatible-run-{run_status.value}",
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


@pytest.mark.parametrize(
    ("attempt_status", "run_status", "message"),
    (
        (
            AttemptStatus.SUCCEEDED,
            RunStatus.FAILED,
            "terminal Attempt and Run status pair is invalid",
        ),
        (
            AttemptStatus.SUSPENDED,
            RunStatus.SUCCEEDED,
            "unsupported closeout Attempt terminal status",
        ),
    ),
)
def test_terminal_closeout_wraps_terminal_event_type_errors(
    tmp_path: Path,
    attempt_status: AttemptStatus,
    run_status: RunStatus,
    message: str,
) -> None:
    """terminal closeout 输入非法终态时统一抛 HostDurableError。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def closeout(transaction: HostTransaction) -> None:
            """执行非法 terminal closeout。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: terminal 状态不受支持时抛出。
            """

            terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-invalid-terminal",
                    run_terminal_event_id="event-run-invalid-terminal",
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

        with pytest.raises(HostDurableError, match=message):
            store.transaction_runner.run_write(closeout)


def test_cancel_predispatch_starting_updates_dispatch_attempt_and_run(
    tmp_path: Path,
) -> None:
    """pre-dispatch cancel 同事务取消 dispatch、Attempt 与 Run。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def cancel(transaction: HostTransaction) -> tuple[str, str, str, str]:
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
            cancel_request_event_id = result.run.cancel_request_event_id
            assert cancel_request_event_id is not None
            return (
                result.run.status.value,
                result.attempt.status.value,
                result.dispatch_record.status.value,
                cancel_request_event_id,
            )

        assert store.transaction_runner.run_write(cancel) == (
            RunStatus.CANCELLED.value,
            AttemptStatus.CANCELLED.value,
            DispatchRecordStatus.CANCELLED.value,
            "event-cancel-requested",
        )


def test_dispatch_record_waiting_dispatching_and_worker_accept_refs(
    tmp_path: Path,
) -> None:
    """dispatch record 按 waiting -> dispatching -> accepted refs 推进。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(
            transaction: HostTransaction,
        ) -> tuple[str, str, bool, bool, bool, bool, bool]:
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
                    local_worker_id="local-worker-1",
                ),
            )
            assert accepted.attempt is not None
            assert accepted.dispatch_record is not None
            dispatch_record = accepted.dispatch_record
            event_payload = _event_payload(
                transaction,
                event_id="event-attempt-running",
            )
            return (
                accepted.attempt.status.value,
                dispatch_record.status.value,
                dispatch_record.worker_accept_event_id is not None
                and dispatch_record.worker_accept_event_sequence is not None
                and dispatch_record.worker_accepted_at is not None,
                event_payload["local_worker_id"] == "local-worker-1",
                event_payload["worker_accepted_at"]
                == dispatch_record.worker_accepted_at,
                event_payload["lane_name"] == dispatch_record.lane_name,
                event_payload["lane_claim_id"] == dispatch_record.lane_claim_id,
            )

        assert store.transaction_runner.run_write(operation) == (
            AttemptStatus.RUNNING.value,
            DispatchRecordStatus.DISPATCHING.value,
            True,
            True,
            True,
            True,
            True,
        )


def test_dispatching_rejects_pending_direct_lane_bypass(tmp_path: Path) -> None:
    """pending dispatch record 不能绕过 waiting_for_lane 直跳 dispatching。"""

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
            StateMutationStatus.INVALID_STATE.value,
            DispatchRecordStatus.PENDING.value,
            None,
            None,
            None,
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

            cancel_request_event_id: str | None = None
            if active_status is RunStatus.CANCELLING:
                cancel_request_event = EventLogStore().append_event(
                    transaction,
                    _test_event(
                        event_id="event-cancel-requested-cas-test",
                        session_id=seeded.session_id,
                        run_id=seeded.run_id,
                        event_type="CANCEL_REQUESTED",
                        payload={"reason": "cas-test"},
                    ),
                ).row
                cancel_request_event_id = cancel_request_event.event_id
            transaction.execute(
                "UPDATE host_runs SET status = ?, cancel_request_event_id = ? WHERE run_id = ?",
                (active_status.value, cancel_request_event_id, seeded.run_id),
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


def test_cancel_recovering_run_row_cas_requires_current_attempt(
    tmp_path: Path,
) -> None:
    """recovering cancel CAS 必须匹配 current Attempt id。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, str]:
            """构造 recovering Run 并验证 current Attempt CAS。

            :param transaction: Host transaction。
            :returns: 错误 attempt 的 mutation 状态、正确 attempt 的 mutation
                状态与最终 Run 状态。
            """

            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_RUNS}
                SET status = ?
                WHERE run_id = ?
                """,
                (RunStatus.RECOVERING.value, seeded.run_id),
            )
            EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-cancel-requested-correct",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="CANCEL_REQUESTED",
                    payload={"reason": "test_cancel"},
                ),
            )
            terminal_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-recovering-cancelled-correct",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_CANCELLED",
                    payload={"terminal_reason": "test_cancel"},
                ),
            )
            wrong = cancel_recovering_run_row(
                transaction,
                run_id=seeded.run_id,
                current_attempt_id="attempt-other",
                terminal_event_id="event-recovering-cancelled-wrong",
                terminal_event_sequence=101,
                cancel_request_event_id="event-cancel-requested-wrong",
                terminal_at="2026-05-14T01:02:09.000000Z",
            )
            correct = cancel_recovering_run_row(
                transaction,
                run_id=seeded.run_id,
                current_attempt_id=seeded.attempt_id,
                terminal_event_id="event-recovering-cancelled-correct",
                terminal_event_sequence=terminal_event.row.event_sequence,
                cancel_request_event_id="event-cancel-requested-correct",
                terminal_at="2026-05-14T01:02:10.000000Z",
            )
            latest = read_run_by_id(transaction, seeded.run_id)
            assert latest is not None
            return wrong.status.value, correct.status.value, latest.status.value

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.CAS_LOST.value,
            StateMutationStatus.UPDATED.value,
            RunStatus.CANCELLED.value,
        )


@pytest.mark.parametrize(
    ("terminal_status", "expected_mutation_status"),
    (
        (RunStatus.SUCCEEDED, StateMutationStatus.CAS_LOST),
        (RunStatus.FAILED, StateMutationStatus.UPDATED),
        (RunStatus.CANCELLED, StateMutationStatus.CAS_LOST),
        (RunStatus.LOST, StateMutationStatus.CAS_LOST),
    ),
)
def test_terminal_run_row_absorbs_only_same_terminal_ref_replay(
    tmp_path: Path,
    terminal_status: RunStatus,
    expected_mutation_status: StateMutationStatus,
) -> None:
    """terminal Run CAS 只吸收同终态且同 terminal event ref 的 replay。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str]:
            """构造 terminal 状态后执行 terminal Run CAS。

            :param transaction: Host transaction。
            :returns: mutation 状态与最新 Run 状态。
            """

            event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id=f"event-terminal-latest-{terminal_status.value}",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "cas-terminal-test"},
                ),
            ).row
            cancel_request_event_id: str | None = None
            if terminal_status is RunStatus.CANCELLED:
                cancel_request_event = EventLogStore().append_event(
                    transaction,
                    _test_event(
                        event_id="event-cancel-requested-terminal-replay",
                        session_id=seeded.session_id,
                        run_id=seeded.run_id,
                        event_type="CANCEL_REQUESTED",
                        payload={"reason": "cas-terminal-test"},
                    ),
                ).row
                cancel_request_event_id = cancel_request_event.event_id
            transaction.execute(
                "UPDATE host_runs "
                "SET status = ?, terminal_event_id = ?, "
                "terminal_event_sequence = ?, cancel_request_event_id = ?, terminal_at = ? "
                "WHERE run_id = ?",
                (
                    terminal_status.value,
                    event.event_id,
                    event.event_sequence,
                    cancel_request_event_id,
                    "2026-05-14T01:02:10Z",
                    seeded.run_id,
                ),
            )
            result = terminal_run_row(
                transaction,
                run_id=seeded.run_id,
                current_attempt_id=seeded.attempt_id,
                terminal_status=RunStatus.FAILED,
                terminal_event_id=event.event_id,
                terminal_event_sequence=event.event_sequence,
                terminal_at="2026-05-14T01:02:11Z",
            )
            assert result.row is not None
            return result.status.value, result.row.status.value

        assert store.transaction_runner.run_write(operation) == (
            expected_mutation_status.value,
            terminal_status.value,
        )


def test_terminal_run_row_rejects_same_terminal_status_with_different_ref(
    tmp_path: Path,
) -> None:
    """同种终态但 terminal event ref 不同仍不可幂等吸收。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str | None]:
            """构造 failed 终态后用不同 terminal ref 重放。

            :param transaction: Host transaction。
            :returns: mutation 状态与最新 terminal event id。
            """

            existing_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-terminal-existing-failed",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "existing"},
                ),
            ).row
            replay_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-terminal-replay-failed",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "replay"},
                ),
            ).row
            transaction.execute(
                "UPDATE host_runs "
                "SET status = ?, terminal_event_id = ?, "
                "terminal_event_sequence = ?, terminal_at = ? "
                "WHERE run_id = ?",
                (
                    RunStatus.FAILED.value,
                    existing_event.event_id,
                    existing_event.event_sequence,
                    "2026-05-14T01:02:10Z",
                    seeded.run_id,
                ),
            )
            result = terminal_run_row(
                transaction,
                run_id=seeded.run_id,
                current_attempt_id=seeded.attempt_id,
                terminal_status=RunStatus.FAILED,
                terminal_event_id=replay_event.event_id,
                terminal_event_sequence=replay_event.event_sequence,
                terminal_at="2026-05-14T01:02:11Z",
            )
            assert result.row is not None
            return result.status.value, result.row.terminal_event_id

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.CAS_LOST.value,
            "event-terminal-existing-failed",
        )


def test_terminal_run_row_reports_cas_lost_when_terminal_refs_already_set(
    tmp_path: Path,
) -> None:
    """terminal Run CAS 看到 terminal refs 已写入时归类为 CAS_LOST。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str | None]:
            """模拟损坏 running row 已有 terminal refs 后执行 terminal Run CAS。

            :param transaction: Host transaction。
            :returns: mutation 状态与最新 terminal event id。
            """

            existing_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-terminal-existing-ref",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "existing-terminal-ref"},
                ),
            ).row
            transaction.execute("PRAGMA ignore_check_constraints = ON")
            try:
                transaction.execute(
                    "UPDATE host_runs "
                    "SET terminal_event_id = ?, terminal_event_sequence = ?, terminal_at = ? "
                    "WHERE run_id = ?",
                    (
                        existing_event.event_id,
                        existing_event.event_sequence,
                        "2026-05-14T01:02:10Z",
                        seeded.run_id,
                    ),
                )
            finally:
                transaction.execute("PRAGMA ignore_check_constraints = OFF")
            new_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-terminal-new-ref",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "new-terminal-ref"},
                ),
            ).row
            try:
                terminal_run_row(
                    transaction,
                    run_id=seeded.run_id,
                    current_attempt_id=seeded.attempt_id,
                    terminal_status=RunStatus.FAILED,
                    terminal_event_id=new_event.event_id,
                    terminal_event_sequence=new_event.event_sequence,
                    terminal_at="2026-05-14T01:02:11Z",
                )
            except HostRowDecodeError:
                row = transaction.fetchone(
                    f"SELECT terminal_event_id FROM {TABLE_HOST_RUNS} WHERE run_id = ?",
                    (seeded.run_id,),
                )
                if row is None:
                    raise HostDurableError("run row missing after terminal CAS")
                terminal_event_id = row.get("terminal_event_id")
                if terminal_event_id is not None and not isinstance(
                    terminal_event_id, str
                ):
                    raise HostDurableError("terminal_event_id must be text")
                return StateMutationStatus.CAS_LOST.value, terminal_event_id
            raise AssertionError("terminal_run_row should reject corrupted terminal refs")

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.CAS_LOST.value,
            "event-terminal-existing-ref",
        )


def test_terminal_attempt_row_reports_cas_lost_when_terminal_refs_already_set(
    tmp_path: Path,
) -> None:
    """terminal Attempt CAS 看到 terminal refs 已写入时不得覆盖。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str | None]:
            """模拟损坏 active attempt 已有 terminal refs 后执行 terminal CAS。

            :param transaction: Host transaction。
            :returns: mutation 状态与最新 terminal event id。
            """

            existing_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-attempt-existing-ref",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="ATTEMPT_FAILED",
                    payload={"reason": "existing-terminal-ref"},
                ),
            ).row
            transaction.execute("PRAGMA ignore_check_constraints = ON")
            try:
                transaction.execute(
                    "UPDATE host_attempts "
                    "SET terminal_event_id = ?, terminal_event_sequence = ?, terminal_at = ? "
                    "WHERE attempt_id = ?",
                    (
                        existing_event.event_id,
                        existing_event.event_sequence,
                        "2026-05-14T01:02:10Z",
                        seeded.attempt_id,
                    ),
                )
            finally:
                transaction.execute("PRAGMA ignore_check_constraints = OFF")
            new_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-attempt-new-ref",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="ATTEMPT_FAILED",
                    payload={"reason": "new-terminal-ref"},
                ),
            ).row
            try:
                terminal_attempt_row(
                    transaction,
                    attempt_id=seeded.attempt_id,
                    terminal_status=AttemptStatus.FAILED,
                    terminal_event_id=new_event.event_id,
                    terminal_event_sequence=new_event.event_sequence,
                    terminal_at="2026-05-14T01:02:11Z",
                )
            except HostRowDecodeError:
                row = transaction.fetchone(
                    f"SELECT terminal_event_id FROM {TABLE_HOST_ATTEMPTS} "
                    "WHERE attempt_id = ?",
                    (seeded.attempt_id,),
                )
                if row is None:
                    raise HostDurableError("attempt row missing after terminal CAS")
                terminal_event_id = row.get("terminal_event_id")
                if terminal_event_id is not None and not isinstance(
                    terminal_event_id, str
                ):
                    raise HostDurableError("terminal_event_id must be text")
                return StateMutationStatus.CAS_LOST.value, terminal_event_id
            raise AssertionError(
                "terminal_attempt_row should reject corrupted terminal refs"
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.CAS_LOST.value,
            "event-attempt-existing-ref",
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

        def operation(transaction: HostTransaction) -> tuple[str, str, int]:
            """先接受 worker，再执行两次 active cancel。

            :param transaction: Host transaction。
            :returns: Run 状态、typed cancel link 与 RUN_CANCELLING 事件数。
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
                    local_worker_id="local-worker-active",
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
            assert second.run.cancel_request_event_id is not None
            return (
                second.run.status.value,
                second.run.cancel_request_event_id,
                _count_events(transaction, _EVENT_TYPE_RUN_CANCELLING),
            )

        assert store.transaction_runner.run_write(operation) == (
            RunStatus.CANCELLING.value,
            "event-active-cancel-requested-first",
            1,
        )


def test_exact_owned_cancel_query_keeps_terminal_control_truth_and_filters_stale(
    tmp_path: Path,
) -> None:
    """exact query 不按 terminal status 过滤，且 stale identity/owner 不误匹配。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)
        identity = AttemptExecutionIdentity(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=f"execution-{seeded.run_id}",
        )
        stale_identity = replace(identity, execution_id="execution-stale")

        def operation(
            transaction: HostTransaction,
        ) -> tuple[
            tuple[OwnedAttemptCancelTarget, ...],
            tuple[OwnedAttemptCancelTarget, ...],
            tuple[OwnedAttemptCancelTarget, ...],
        ]:
            """接受 cancel、terminal closeout 并重复读取 exact target。

            :param transaction: Host transaction。
            :returns: cancelling、terminal 与错误 owner 三次查询结果。
            """

            _accept_and_request_active_cancel(transaction, seeded)
            cancelling_targets = read_exact_owned_attempt_cancel_targets(
                transaction,
                EventLogStore(),
                owner_host_instance_id="host-instance-1",
                identities=(stale_identity, identity),
            )
            closeout = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(seeded),
            )
            assert closeout.status is StateMutationStatus.UPDATED
            terminal_targets = read_exact_owned_attempt_cancel_targets(
                transaction,
                EventLogStore(),
                owner_host_instance_id="host-instance-1",
                identities=(identity,),
            )
            wrong_owner_targets = read_exact_owned_attempt_cancel_targets(
                transaction,
                EventLogStore(),
                owner_host_instance_id="host-instance-other",
                identities=(identity,),
            )
            return cancelling_targets, terminal_targets, wrong_owner_targets

        expected = OwnedAttemptCancelTarget(
            identity=identity,
            cancel_request_event_id="event-active-cancel-requested-watchdog",
        )
        assert store.transaction_runner.run_write(operation) == (
            (expected,),
            (expected,),
            (),
        )

        with pytest.raises(
            HostDurableError,
            match="attempt execution identities must be unique",
        ):
            store.transaction_runner.run_read(
                lambda transaction: read_exact_owned_attempt_cancel_targets(
                    transaction,
                    EventLogStore(),
                    owner_host_instance_id="host-instance-1",
                    identities=(identity, identity),
                )
            )


@pytest.mark.parametrize(
    "stale_field",
    ("current_attempt", "dispatch_owner"),
)
def test_exact_owned_cancel_query_filters_durable_identity_change(
    tmp_path: Path,
    stale_field: str,
) -> None:
    """current Attempt 或 dispatch owner 变化均只过滤旧快照。

    :param tmp_path: pytest 临时目录。
    :param stale_field: 本 case 改写的 durable identity owner 字段。
    :returns: ``None``。
    :raises AssertionError: stale identity 仍被返回时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)
        identity = AttemptExecutionIdentity(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=f"execution-{seeded.run_id}",
        )

        def operation(
            transaction: HostTransaction,
        ) -> tuple[OwnedAttemptCancelTarget, ...]:
            """写入 cancel 后改写单个 durable identity owner 字段并查询。

            :param transaction: Host transaction。
            :returns: exact query 结果。
            """

            _accept_and_request_active_cancel(transaction, seeded)
            if stale_field == "current_attempt":
                transaction.execute(
                    f"UPDATE {TABLE_HOST_RUNS} SET current_attempt_id = NULL "
                    "WHERE run_id = ?",
                    (seeded.run_id,),
                )
            else:
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
                        2,
                        "process-start-token-new",
                        None,
                        "2026-05-14T01:02:03.000000Z",
                        "2026-05-14T01:02:03.000000Z",
                        "running",
                    ),
                )
                transaction.execute(
                    f"UPDATE {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} "
                    "SET owner_host_instance_id = ? WHERE attempt_id = ?",
                    ("host-instance-new", seeded.attempt_id),
                )
            return read_exact_owned_attempt_cancel_targets(
                transaction,
                EventLogStore(),
                owner_host_instance_id="host-instance-1",
                identities=(identity,),
            )

        assert store.transaction_runner.run_write(operation) == ()


def test_exact_owned_cancel_query_batches_preserve_global_order_and_filter_stale(
    tmp_path: Path,
) -> None:
    """超过单 batch 时仍保持输入顺序并精确过滤 owner/stale identity。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 分批顺序或 owner/stale 语义漂移时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        session_ids = _ensure_exact_cancel_batch_sessions(
            store.transaction_runner,
            count=_EXACT_CANCEL_MULTI_BATCH_IDENTITY_COUNT,
        )
        identities = store.transaction_runner.run_write(
            lambda transaction: _seed_exact_cancel_batch(
                transaction,
                session_ids=session_ids,
            )
        )
        reversed_identities = tuple(reversed(identities))
        targets = store.transaction_runner.run_read(
            lambda transaction: read_exact_owned_attempt_cancel_targets(
                transaction,
                EventLogStore(),
                owner_host_instance_id="host-instance-1",
                identities=reversed_identities,
            )
        )
        excluded = {
            identities[_EXACT_CANCEL_WRONG_OWNER_INDEX],
            identities[_EXACT_CANCEL_STALE_CURRENT_ATTEMPT_INDEX],
        }
        assert targets == tuple(
            OwnedAttemptCancelTarget(
                identity=identity,
                cancel_request_event_id=(
                    f"event-active-cancel-requested-batch-"
                    f"{identity.run_id.removeprefix('run-batch-')}"
                ),
            )
            for identity in reversed_identities
            if identity not in excluded
        )


@pytest.mark.parametrize(
    "corruption",
    (
        "missing",
        "event_class",
        "event_type",
        "session_id",
        "run_id",
        "attempt_id",
        "execution_id",
        "payload_ref",
        "event_body_digest",
        "payload_shape",
    ),
)
def test_exact_owned_cancel_query_fails_closed_for_bad_linked_fact(
    tmp_path: Path,
    corruption: str,
) -> None:
    """linked cancel row 缺失、错链、坏 shape 或坏 digest 均 fail closed。

    :param tmp_path: pytest 临时目录。
    :param corruption: 本 case 注入的 linked fact 损坏类型。
    :returns: ``None``。
    :raises AssertionError: strict query 未抛 durable invariant error 时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)
        identity = AttemptExecutionIdentity(
            session_id=seeded.session_id,
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=f"execution-{seeded.run_id}",
        )

        def seed_and_build_store(transaction: HostTransaction) -> EventLogStore:
            """写入合法 cancel，并构造指定 linked-event 读取替身。

            :param transaction: Host transaction。
            :returns: 返回指定损坏 row 的 EventLog store。
            """

            _accept_and_request_active_cancel(transaction, seeded)
            real_event = EventLogStore().read_event_by_id(
                transaction,
                "event-active-cancel-requested-watchdog",
            )
            assert real_event is not None
            if corruption == "missing":
                return _StaticEventLogStore(None)
            if corruption == "event_class":
                return _StaticEventLogStore(
                    replace(real_event, event_class=EventClass.DIAGNOSTIC)
                )
            if corruption == "event_type":
                return _StaticEventLogStore(
                    replace(real_event, event_type="RUN_CANCELLING")
                )
            if corruption == "session_id":
                return _StaticEventLogStore(
                    replace(real_event, session_id="session-wrong")
                )
            if corruption == "run_id":
                return _StaticEventLogStore(
                    replace(real_event, run_id="run-wrong")
                )
            if corruption == "attempt_id":
                return _StaticEventLogStore(
                    replace(real_event, attempt_id=seeded.attempt_id)
                )
            if corruption == "execution_id":
                return _StaticEventLogStore(
                    replace(real_event, execution_id=identity.execution_id)
                )
            if corruption == "payload_ref":
                return _StaticEventLogStore(
                    replace(real_event, payload_ref="payload-invalid")
                )
            if corruption == "event_body_digest":
                return _StaticEventLogStore(
                    replace(real_event, event_body_digest=_INPUT_DIGEST)
                )
            invalid_payload_event = EventLogStore().append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-invalid-cancel-payload",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="CANCEL_REQUESTED",
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    client_request_id="active-cancel-watchdog",
                    idempotency_key="active-cancel-watchdog",
                    policy_decision=None,
                    reason={"reason": "user_cancel", "mode": "graceful"},
                    payload_json={
                        "run_id": seeded.run_id,
                        "client_request_id": "active-cancel-watchdog",
                        "reason": "user_cancel",
                        "mode": "graceful",
                        "target_status_at_accept": "running",
                        "call_context_digest": _CALL_CONTEXT_DIGEST,
                        "unexpected": "field",
                    },
                    payload_ref=None,
                    payload_digest=None,
                ),
            ).row
            return _StaticEventLogStore(
                replace(
                    invalid_payload_event,
                    event_id=real_event.event_id,
                )
            )

        event_log_store = store.transaction_runner.run_write(seed_and_build_store)
        with pytest.raises(HostDurableError):
            store.transaction_runner.run_read(
                lambda transaction: read_exact_owned_attempt_cancel_targets(
                    transaction,
                    event_log_store,
                    owner_host_instance_id="host-instance-1",
                    identities=(identity,),
                )
            )


def test_active_cancel_watchdog_closeout_writes_cancelled_terminal_facts(
    tmp_path: Path,
) -> None:
    """accepted cancel watchdog 写入唯一 ATTEMPT/RUN CANCELLED terminal facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, str, str]:
            """执行 accepted cancel watchdog closeout 并校验 payload。

            :param transaction: Host transaction。
            :returns: 首次和重放 transition 状态，以及 Run 与 Attempt 最新状态。
            """

            _accept_and_request_active_cancel(transaction, seeded)
            result = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(
                    seeded,
                    last_observed_worker_event_index=7,
                    last_accepted_event_id="event-worker-delta-7",
                ),
            )
            assert result.status == StateMutationStatus.UPDATED
            assert result.run is not None
            assert result.attempt is not None
            replay = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(
                    seeded,
                    last_observed_worker_event_index=7,
                    last_accepted_event_id="event-worker-delta-7",
                ),
            )
            assert replay.status == StateMutationStatus.UPDATED
            assert _count_events(transaction, _EVENT_TYPE_ATTEMPT_CANCELLED) == 1
            assert _count_events(transaction, _EVENT_TYPE_RUN_CANCELLED) == 1
            attempt_payload = _event_payload(
                transaction, event_id="event-active-watchdog-attempt-cancelled"
            )
            run_payload = _event_payload(
                transaction, event_id="event-active-watchdog-run-cancelled"
            )
            for payload in (attempt_payload, run_payload):
                assert payload["dispatch_record_id"] == "dispatch-run-1"
                assert payload["cancel_request_event_id"] == (
                    "event-active-cancel-requested-watchdog"
                )
                assert "timeout_seconds" not in payload
                assert payload["cancel_requested_at"] == (
                    "2026-05-14T01:02:03.000000Z"
                )
                assert "timed_out_at" not in payload
                assert payload["closed_out_at"] == "2026-05-14T01:02:33.000000Z"
                assert payload["watchdog_owner"] == "host.active_cancel_watchdog"
                assert payload["worker_lifecycle_signal"] == (
                    "active_cancel_watchdog_closeout"
                )
                assert payload["last_observed_worker_event_index"] == 7
                assert payload["last_accepted_event_id"] == "event-worker-delta-7"
                assert payload["reason"] == "active_cancel_watchdog_closeout"
            assert run_payload["attempt_terminal_event_id"] == (
                "event-active-watchdog-attempt-cancelled"
            )
            return (
                result.status.value,
                replay.status.value,
                result.run.status.value,
                result.attempt.status.value,
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            StateMutationStatus.UPDATED.value,
            RunStatus.CANCELLED.value,
            AttemptStatus.CANCELLED.value,
        )


def test_active_cancel_watchdog_closeout_requires_cancelling_run(
    tmp_path: Path,
) -> None:
    """RUNNING 且没有 cancel fact 时 watchdog closeout 不写 terminal facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int, int]:
            """对 RUNNING Run 直接执行 watchdog closeout。

            :param transaction: Host transaction。
            :returns: transition 状态与 terminal fact 计数。
            """

            _accept_active_attempt(transaction, seeded)
            result = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(seeded),
            )
            return (
                result.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_CANCELLED),
                _count_events(transaction, _EVENT_TYPE_RUN_CANCELLED),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.INVALID_STATE.value,
            0,
            0,
        )


def test_active_cancel_watchdog_closeout_uses_typed_link_with_malformed_payload(
    tmp_path: Path,
) -> None:
    """RUN_CANCELLING payload 缺少 cancel request id 时仍使用 typed row link。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int, int]:
            """写入 malformed RUN_CANCELLING 后执行 watchdog closeout。

            :param transaction: Host transaction。
            :returns: transition 状态与 terminal fact 计数。
            """

            _accept_and_request_active_cancel(transaction, seeded)
            attempt = read_attempt_by_id(transaction, seeded.attempt_id)
            assert attempt is not None
            EventLogStore().append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-run-cancelling-watchdog-malformed",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=attempt.execution_id,
                    event_type=_EVENT_TYPE_RUN_CANCELLING,
                    occurred_at=_NOW + timedelta(microseconds=1),
                    actor="analyst",
                    source="pytest",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason="malformed",
                    payload_json={"reason": "malformed"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            result = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(seeded),
            )
            return (
                result.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_CANCELLED),
                _count_events(transaction, _EVENT_TYPE_RUN_CANCELLED),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            1,
            1,
        )


def test_active_cancel_watchdog_closeout_first_committer_wins_after_cooperative_cancel(
    tmp_path: Path,
) -> None:
    """cooperative cancel 先收口后 watchdog 不追加第二组 terminal facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int, int]:
            """先 cooperative cancel，再调用 watchdog closeout。

            :param transaction: Host transaction。
            :returns: watchdog 状态与 terminal fact 计数。
            """

            _accept_and_request_active_cancel(transaction, seeded)
            active_cancel_closeout_in_transaction(
                transaction,
                EventLogStore(),
                ActiveCancelCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_cancelled_event_id="event-coop-attempt-cancelled",
                    run_cancelled_event_id="event-coop-run-cancelled",
                    occurred_at=_NOW + timedelta(seconds=1),
                    actor="analyst",
                    source="pytest",
                    reason="user_cancel",
                    cancel_request_event_id=(
                        "event-active-cancel-requested-watchdog"
                    ),
                    engine_event_ref="event-engine-run-cancelled",
                    requested_at="2026-05-14T01:02:03Z",
                    accepted_at="2026-05-14T01:02:04Z",
                    finished_at="2026-05-14T01:02:05Z",
                ),
            )
            watchdog = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(seeded),
            )
            return (
                watchdog.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_CANCELLED),
                _count_events(transaction, _EVENT_TYPE_RUN_CANCELLED),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            1,
            1,
        )


def test_active_cancel_watchdog_closeout_rejects_after_succeeded_terminal(
    tmp_path: Path,
) -> None:
    """成功终态先提交后 watchdog closeout 不追加 cancel terminal facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int, int]:
            """先写 success terminal，再调用 watchdog closeout。

            :param transaction: Host transaction。
            :returns: watchdog 状态与 cancel terminal fact 计数。
            """

            _accept_active_attempt(transaction, seeded)
            terminal_closeout_in_transaction(
                transaction,
                EventLogStore(),
                TerminalCloseoutInput(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    attempt_terminal_event_id="event-attempt-success-before-watchdog",
                    run_terminal_event_id="event-run-success-before-watchdog",
                    attempt_terminal_status=AttemptStatus.SUCCEEDED,
                    run_terminal_status=RunStatus.SUCCEEDED,
                    occurred_at=_NOW,
                    actor="analyst",
                    source="pytest",
                    reason="final_answer",
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            watchdog = active_cancel_watchdog_closeout_in_transaction(
                transaction,
                EventLogStore(),
                _active_watchdog_input(seeded),
            )
            return (
                watchdog.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_CANCELLED),
                _count_events(transaction, _EVENT_TYPE_RUN_CANCELLED),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.INVALID_STATE.value,
            0,
            0,
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


def test_cancel_queued_run_row_requires_empty_terminal_refs(
    tmp_path: Path,
) -> None:
    """queued Run 行若已有 terminal refs，底层 cancel CAS 不得覆盖。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: CAS 覆盖 corrupted row 或错误边界不符合预期时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)

        def operation(transaction: HostTransaction) -> None:
            """构造带 terminal refs 的 queued 行并尝试 cancel。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostRowDecodeError: CAS 拒绝 corrupted row 后读取 row 时抛出。
            """

            input_event = _append_user_input(
                transaction,
                session_id=session_id,
                run_id="run-queued-guard",
                event_id="event-input-queued-guard",
            )
            create_queued_run_in_transaction(
                transaction,
                EventLogStore(),
                _create_queued_input(
                    session_id=session_id,
                    run_id="run-queued-guard",
                    input_event_sequence=input_event.event_sequence,
                    request_index="queued-guard",
                ),
            )
            terminal_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-terminal-queued-guard",
                    session_id=session_id,
                    run_id="run-queued-guard",
                    event_type="RUN_FAILED",
                    payload={"reason": "terminal-guard"},
                ),
            ).row
            transaction.execute("PRAGMA ignore_check_constraints = ON")
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_RUNS}
                SET terminal_event_id = ?,
                    terminal_event_sequence = ?,
                    terminal_at = ?
                WHERE run_id = ?
                """,
                (
                    terminal_event.event_id,
                    terminal_event.event_sequence,
                    "2026-05-14T01:02:09Z",
                    "run-queued-guard",
                ),
            )
            transaction.execute("PRAGMA ignore_check_constraints = OFF")
            cancel_queued_run_row(
                transaction,
                run_id="run-queued-guard",
                terminal_event_id="event-cancel-queued-guard",
                terminal_event_sequence=terminal_event.event_sequence + 1,
                cancel_request_event_id="event-cancel-request-queued-guard",
                terminal_at="2026-05-14T01:02:10Z",
            )

        with pytest.raises(HostRowDecodeError, match="non-terminal Run terminal refs"):
            store.transaction_runner.run_write(operation)


def test_cancel_running_run_row_requires_empty_terminal_refs(
    tmp_path: Path,
) -> None:
    """running Run 行若已有 terminal refs，底层 cancel CAS 不得覆盖。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: CAS 覆盖 corrupted row 或错误边界不符合预期时抛出。
    """

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> None:
            """构造带 terminal refs 的 running 行并尝试 cancel。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostRowDecodeError: CAS 拒绝 corrupted row 后读取 row 时抛出。
            """

            terminal_event = EventLogStore().append_event(
                transaction,
                _test_event(
                    event_id="event-terminal-running-guard",
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    event_type="RUN_FAILED",
                    payload={"reason": "terminal-guard"},
                ),
            ).row
            transaction.execute("PRAGMA ignore_check_constraints = ON")
            transaction.execute(
                f"""
                UPDATE {TABLE_HOST_RUNS}
                SET terminal_event_id = ?,
                    terminal_event_sequence = ?,
                    terminal_at = ?
                WHERE run_id = ?
                """,
                (
                    terminal_event.event_id,
                    terminal_event.event_sequence,
                    "2026-05-14T01:02:09Z",
                    seeded.run_id,
                ),
            )
            transaction.execute("PRAGMA ignore_check_constraints = OFF")
            cancel_running_run_row(
                transaction,
                run_id=seeded.run_id,
                current_attempt_id=seeded.attempt_id,
                terminal_event_id="event-cancel-running-guard",
                terminal_event_sequence=terminal_event.event_sequence + 1,
                cancel_request_event_id="event-cancel-request-running-guard",
                terminal_at="2026-05-14T01:02:10Z",
            )

        with pytest.raises(HostRowDecodeError, match="non-terminal Run terminal refs"):
            store.transaction_runner.run_write(operation)


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


def test_context_recovery_close_payload_includes_client_correlation_id(
    tmp_path: Path,
) -> None:
    """context recovery closeout payload 保留本地客户端关联 id。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(
            transaction: HostTransaction,
        ) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
            """执行 context recovery closeout 并读取 payload。

            :param transaction: Host transaction。
            :returns: ATTEMPT_FAILED 与 RUN_RECOVERING payload。
            """

            result = close_attempt_for_context_recovery_in_transaction(
                transaction,
                EventLogStore(),
                _context_recovery_input(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    client_correlation_id="client-recovery",
                ),
            )
            assert result.status == StateMutationStatus.UPDATED
            return (
                _event_payload(
                    transaction,
                    event_id="event-context-recovery-attempt-failed",
                ),
                _event_payload(
                    transaction,
                    event_id="event-context-recovery-run-recovering",
                ),
            )

        attempt_payload, run_payload = store.transaction_runner.run_write(operation)
        assert attempt_payload["client_correlation_id"] == "client-recovery"
        assert run_payload["client_correlation_id"] == "client-recovery"


def test_context_recovery_close_rejects_empty_client_correlation_id(
    tmp_path: Path,
) -> None:
    """context recovery closeout 拒绝空白客户端关联 id。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> None:
            """执行非法 context recovery closeout。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: client_correlation_id 空白时抛出。
            """

            close_attempt_for_context_recovery_in_transaction(
                transaction,
                EventLogStore(),
                _context_recovery_input(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    client_correlation_id=" ",
                ),
            )

        with pytest.raises(HostDurableError, match="client_correlation_id"):
            store.transaction_runner.run_write(operation)


def test_startup_orphan_closeout_marks_attempt_lost_then_run_recovering(
    tmp_path: Path,
) -> None:
    """startup orphan closeout 同事务按序写 ATTEMPT_LOST 与 RUN_RECOVERING。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, tuple[str, ...]]:
            """执行 startup orphan recoverable closeout。

            :param transaction: Host transaction。
            :returns: Run 状态、Attempt 状态、事件序列。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            _make_host_instance_stale_tx(transaction)
            result = close_startup_orphan_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _startup_orphan_input(
                    expected_run_status=RunStatus.RUNNING,
                    expected_attempt_status=AttemptStatus.STARTING,
                    recoverable=True,
                    reason="startup_orphan_attempt_lost",
                    owner_heartbeat_at="2026-05-14T01:01:00.000000Z",
                ),
            )
            assert result.run is not None
            assert result.attempt is not None
            return (
                result.run.status.value,
                result.attempt.status.value,
                _event_types(transaction),
            )

        run_status, attempt_status, event_types = store.transaction_runner.run_write(
            operation
        )
        assert run_status == RunStatus.RECOVERING.value
        assert attempt_status == AttemptStatus.LOST.value
        assert event_types[-2:] == (
            _EVENT_TYPE_ATTEMPT_LOST,
            _EVENT_TYPE_RUN_RECOVERING,
        )


def test_startup_orphan_recoverable_rejects_cancelling_expected_status(
    tmp_path: Path,
) -> None:
    """recoverable startup orphan closeout 不接受 CANCELLING 期望状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)
        before_attempt_lost_events = store.transaction_runner.run_read(
            lambda transaction: _count_events(transaction, _EVENT_TYPE_ATTEMPT_LOST)
        )

        def operation(transaction: HostTransaction) -> None:
            """执行非法 recoverable closeout 组合。

            :param transaction: Host transaction。
            :returns: ``None``。
            :raises HostDurableError: recoverable + CANCELLING 组合非法。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            _make_host_instance_stale_tx(transaction)
            close_startup_orphan_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _startup_orphan_input(
                    expected_run_status=RunStatus.CANCELLING,
                    expected_attempt_status=AttemptStatus.STARTING,
                    recoverable=True,
                    reason="startup_orphan_attempt_lost",
                    owner_heartbeat_at="2026-05-14T01:01:00.000000Z",
                ),
            )

        with pytest.raises(
            HostDurableError,
            match="only running orphan Run can become recovering",
        ):
            store.transaction_runner.run_write(operation)
        after_attempt_lost_events = store.transaction_runner.run_read(
            lambda transaction: _count_events(transaction, _EVENT_TYPE_ATTEMPT_LOST)
        )

        assert after_attempt_lost_events == before_attempt_lost_events


def test_startup_orphan_closeout_cas_rechecks_owner_heartbeat(
    tmp_path: Path,
) -> None:
    """owner heartbeat 不再 stale 时 startup orphan closeout 不写事件或状态。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int]:
            """用最新 heartbeat 验证 CAS recheck 失败。

            :param transaction: Host transaction。
            :returns: mutation 状态与 ATTEMPT_LOST 事件数。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            result = close_startup_orphan_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _startup_orphan_input(
                    expected_run_status=RunStatus.RUNNING,
                    expected_attempt_status=AttemptStatus.STARTING,
                    recoverable=True,
                    reason="startup_orphan_attempt_lost",
                    owner_heartbeat_at="2026-05-14T01:02:03.000000Z",
                ),
            )
            return (
                result.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_LOST),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.INVALID_STATE.value,
            0,
        )


def test_startup_orphan_closeout_accepts_stopped_owner_lifecycle_proof(
    tmp_path: Path,
) -> None:
    """owner 已 STOPPED 时 startup orphan closeout 不要求 heartbeat stale。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, int]:
            """用 STOPPED owner 验证 graceful close recovery CAS。

            :param transaction: Host transaction。
            :returns: mutation 状态、Run 状态与 ATTEMPT_LOST 事件数。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            _set_host_instance_status_tx(transaction, HostInstanceStatus.STOPPED)
            result = close_startup_orphan_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _startup_orphan_input(
                    expected_run_status=RunStatus.RUNNING,
                    expected_attempt_status=AttemptStatus.STARTING,
                    recoverable=True,
                    reason="startup_orphan_attempt_lost",
                    owner_heartbeat_at="2026-05-14T01:02:03.000000Z",
                ),
            )
            assert result.run is not None
            return (
                result.status.value,
                result.run.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_LOST),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            RunStatus.RECOVERING.value,
            1,
        )


def test_startup_orphan_closeout_accepts_stopping_owner_stale_proof(
    tmp_path: Path,
) -> None:
    """owner 为 STOPPING 时 startup orphan closeout 仍要求 heartbeat stale。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, str, int]:
            """用 STOPPING stale owner 验证 graceful close 中断 recovery CAS。

            :param transaction: Host transaction。
            :returns: mutation 状态、Run 状态与 ATTEMPT_LOST 事件数。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            _set_host_instance_status_tx(transaction, HostInstanceStatus.STOPPING)
            _make_host_instance_stale_tx(transaction)
            result = close_startup_orphan_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _startup_orphan_input(
                    expected_run_status=RunStatus.RUNNING,
                    expected_attempt_status=AttemptStatus.STARTING,
                    recoverable=True,
                    reason="startup_orphan_attempt_lost",
                    owner_heartbeat_at="2026-05-14T01:01:00.000000Z",
                ),
            )
            assert result.run is not None
            return (
                result.status.value,
                result.run.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_LOST),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.UPDATED.value,
            RunStatus.RECOVERING.value,
            1,
        )


def test_startup_orphan_closeout_preserves_fractional_stale_threshold(
    tmp_path: Path,
) -> None:
    """startup orphan CAS 使用与 classifier 一致的亚秒 stale 阈值。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_running_run(store, tmp_path)

        def operation(transaction: HostTransaction) -> tuple[str, int]:
            """用亚秒边界验证 stale threshold 不被取整。

            :param transaction: Host transaction。
            :returns: mutation 状态与 ATTEMPT_LOST 事件数。
            """

            _mark_dispatching_tx(transaction, seeded.attempt_id)
            _set_host_instance_heartbeat_tx(
                transaction,
                "2026-05-14T01:01:32.750000Z",
            )
            result = close_startup_orphan_attempt_in_transaction(
                transaction,
                EventLogStore(),
                _startup_orphan_input(
                    expected_run_status=RunStatus.RUNNING,
                    expected_attempt_status=AttemptStatus.STARTING,
                    recoverable=True,
                    reason="startup_orphan_attempt_lost",
                    owner_heartbeat_at="2026-05-14T01:01:32.750000Z",
                    stale_after=timedelta(seconds=30, milliseconds=500),
                ),
            )
            return (
                result.status.value,
                _count_events(transaction, _EVENT_TYPE_ATTEMPT_LOST),
            )

        assert store.transaction_runner.run_write(operation) == (
            StateMutationStatus.INVALID_STATE.value,
            0,
        )


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


def _ensure_exact_cancel_batch_sessions(
    transaction_runner: HostTransactionRunner,
    *,
    count: int,
) -> tuple[str, ...]:
    """为 multi-batch exact cancel case 创建互不冲突的 Sessions。

    :param transaction_runner: Host transaction runner。
    :param count: 需要创建的 Session 数量。
    :returns: 按创建顺序排列的 Session ids。
    :raises ValueError: ``count`` 非正数时抛出。
    :raises Exception: durable Session 创建失败时透传。
    """

    if count <= 0:
        raise ValueError("count must be positive")
    return tuple(
        ensure_session(
            transaction_runner,
            EnsureSessionRequest(
                scope="workspace",
                slot_key=f"run-transition-batch-{index:03d}",
                metadata=(),
            ),
        ).snapshot.session_id
        for index in range(count)
    )


def _seed_exact_cancel_batch(
    transaction: HostTransaction,
    *,
    session_ids: tuple[str, ...],
) -> tuple[AttemptExecutionIdentity, ...]:
    """在一个事务中构造跨 batch 的 exact owned cancel durable truth。

    :param transaction: 当前 Host write transaction。
    :param session_ids: 每个 target 对应的唯一 Session id。
    :returns: 按输入 Session 顺序排列的 exact identities。
    :raises AssertionError: 任一 transition 未按预期更新时抛出。
    :raises Exception: durable 写入失败时透传。
    """

    _ensure_host_instance_tx(transaction)
    _ensure_exact_cancel_other_owner_tx(transaction)
    identities: list[AttemptExecutionIdentity] = []
    for index, session_id in enumerate(session_ids):
        suffix = f"batch-{index:03d}"
        run_id = f"run-{suffix}"
        attempt_id = f"attempt-{run_id}"
        execution_id = f"execution-{run_id}"
        input_event = _append_user_input(
            transaction,
            session_id=session_id,
            run_id=run_id,
            event_id=f"event-input-{suffix}",
        )
        created = create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            _create_running_input(
                session_id=session_id,
                run_id=run_id,
                input_event_sequence=input_event.event_sequence,
            ),
        )
        assert created.status is StateMutationStatus.UPDATED
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-instance-1",
            lane_name="llm",
            waiting_for_lane_at="2026-05-14T01:02:04.000000Z",
        )
        assert waiting.status is StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-instance-1",
            lane_name="llm",
            lane_claim_id=f"lane-claim-{suffix}",
            lane_owner_id="lane-owner-1",
            lane_acquired_at="2026-05-14T01:02:05.000000Z",
            dispatching_at="2026-05-14T01:02:06.000000Z",
        )
        assert dispatching.status is StateMutationStatus.UPDATED
        accepted = accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=run_id,
                attempt_id=attempt_id,
                attempt_running_event_id=f"event-attempt-running-{suffix}",
                occurred_at=_NOW,
                actor="analyst",
                source="pytest",
                worker_accept_reason="worker_accepted",
                local_worker_id=f"local-worker-{suffix}",
            ),
        )
        assert accepted.status is StateMutationStatus.UPDATED
        cancelled = request_active_attempt_cancel_in_transaction(
            transaction,
            EventLogStore(),
            _cancel_active_input(run_id=run_id, event_suffix=suffix),
        )
        assert cancelled.status is StateMutationStatus.UPDATED
        identities.append(
            AttemptExecutionIdentity(
                session_id=session_id,
                run_id=run_id,
                attempt_id=attempt_id,
                execution_id=execution_id,
            )
        )

    wrong_owner_identity = identities[_EXACT_CANCEL_WRONG_OWNER_INDEX]
    transaction.execute(
        f"UPDATE {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS} "
        "SET owner_host_instance_id = ? WHERE attempt_id = ?",
        ("host-instance-other", wrong_owner_identity.attempt_id),
    )
    stale_identity = identities[_EXACT_CANCEL_STALE_CURRENT_ATTEMPT_INDEX]
    transaction.execute(
        f"UPDATE {TABLE_HOST_RUNS} SET current_attempt_id = NULL WHERE run_id = ?",
        (stale_identity.run_id,),
    )
    return tuple(identities)


def _ensure_exact_cancel_other_owner_tx(transaction: HostTransaction) -> None:
    """写入 multi-batch owner 过滤 case 使用的另一个 Host instance。

    :param transaction: 当前 Host transaction。
    :returns: ``None``。
    :raises Exception: SQLite 写入失败时透传。
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
            "host-instance-other",
            2,
            "process-start-token-other",
            None,
            "2026-05-14T01:02:03.000000Z",
            "2026-05-14T01:02:03.000000Z",
            "running",
        ),
    )


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
        queue_policy=RunQueuePolicy.QUEUE,
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
        queue_policy=RunQueuePolicy.QUEUE,
        queue_reason="active_run_exists",
        active_run_id="run-active",
        call_context_digest=_CALL_CONTEXT_DIGEST,
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


def _accept_active_attempt(
    transaction: HostTransaction, seeded: _SeededRunningRun
) -> None:
    """将 seeded Attempt 推进到 worker accepted RUNNING。

    :param transaction: Host transaction。
    :param seeded: seeded running Run。
    :returns: ``None``。
    """

    _mark_dispatching_tx(transaction, seeded.attempt_id)
    accepted = accept_worker_running_in_transaction(
        transaction,
        EventLogStore(),
        AcceptWorkerRunningInput(
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            attempt_running_event_id="event-active-watchdog-attempt-running",
            occurred_at=_NOW,
            actor="analyst",
            source="pytest",
            worker_accept_reason="worker_accepted",
            local_worker_id="local-worker-active",
        ),
    )
    assert accepted.status == StateMutationStatus.UPDATED


def _accept_and_request_active_cancel(
    transaction: HostTransaction, seeded: _SeededRunningRun
) -> None:
    """将 seeded Attempt 推进到 active cancelling。

    :param transaction: Host transaction。
    :param seeded: seeded running Run。
    :returns: ``None``。
    """

    _accept_active_attempt(transaction, seeded)
    cancelled = request_active_attempt_cancel_in_transaction(
        transaction,
        EventLogStore(),
        _cancel_active_input(run_id=seeded.run_id, event_suffix="watchdog"),
    )
    assert cancelled.status == StateMutationStatus.UPDATED


def _active_watchdog_input(
    seeded: _SeededRunningRun,
    *,
    last_observed_worker_event_index: int | None = None,
    last_accepted_event_id: str | None = None,
) -> ActiveCancelWatchdogCloseoutInput:
    """构造 accepted cancel watchdog closeout 输入。

    :param seeded: seeded running Run。
    :param last_observed_worker_event_index: 最后观察到的 worker event index。
    :param last_accepted_event_id: 最后已接受 EventLog id。
    :returns: accepted cancel watchdog closeout 输入。
    """

    return ActiveCancelWatchdogCloseoutInput(
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        attempt_cancelled_event_id="event-active-watchdog-attempt-cancelled",
        run_cancelled_event_id="event-active-watchdog-run-cancelled",
        occurred_at=_NOW + timedelta(seconds=30),
        actor="host.active_cancel_watchdog",
        source="pytest",
        cancel_requested_at="2026-05-14T01:02:03.000000Z",
        closed_out_at=_NOW + timedelta(seconds=30),
        watchdog_owner="host.active_cancel_watchdog",
        worker_lifecycle_signal="active_cancel_watchdog_closeout",
        last_observed_worker_event_index=last_observed_worker_event_index,
        last_accepted_event_id=last_accepted_event_id,
    )


def _context_recovery_input(
    *,
    run_id: str,
    attempt_id: str,
    client_correlation_id: str | None,
) -> ContextRecoveryCloseInput:
    """构造 context recovery closeout 输入。

    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param client_correlation_id: 本地客户端关联 id；无时为 ``None``。
    :returns: ContextRecoveryCloseInput。
    """

    return ContextRecoveryCloseInput(
        run_id=run_id,
        attempt_id=attempt_id,
        attempt_failed_event_id="event-context-recovery-attempt-failed",
        run_recovering_event_id="event-context-recovery-run-recovering",
        occurred_at=_NOW,
        actor="context_governance",
        source="pytest",
        reason="context_overflow",
        engine_event_ref="engine-event-context-overflow",
        provider_request_id="provider-recovery",
        message="context compaction required",
        client_correlation_id=client_correlation_id,
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
            "2026-05-14T01:02:03.000000Z",
            "2026-05-14T01:02:03.000000Z",
            "running",
        ),
    )


def _make_host_instance_stale_tx(transaction: HostTransaction) -> None:
    """将测试 Host instance heartbeat 改成 stale。

    :param transaction: Host transaction。
    :returns: ``None``。
    """

    _set_host_instance_heartbeat_tx(transaction, "2026-05-14T01:01:00.000000Z")


def _set_host_instance_heartbeat_tx(
    transaction: HostTransaction, heartbeat_at: str
) -> None:
    """设置测试 Host instance heartbeat。

    :param transaction: Host transaction。
    :param heartbeat_at: 目标 heartbeat timestamp。
    :returns: ``None``。
    """

    transaction.execute(
        """
        UPDATE host_instances
        SET heartbeat_at = ?
        WHERE host_instance_id = ?
        """,
        (heartbeat_at, "host-instance-1"),
    )


def _set_host_instance_status_tx(
    transaction: HostTransaction,
    status: HostInstanceStatus,
) -> None:
    """设置测试 Host instance lifecycle status。

    :param transaction: Host transaction。
    :param status: 目标 status。
    :returns: ``None``。
    """

    transaction.execute(
        """
        UPDATE host_instances
        SET status = ?
        WHERE host_instance_id = ?
        """,
        (status.value, "host-instance-1"),
    )


def _startup_orphan_input(
    *,
    expected_run_status: RunStatus,
    expected_attempt_status: AttemptStatus,
    recoverable: bool,
    reason: str,
    owner_heartbeat_at: str,
    stale_after: timedelta = timedelta(seconds=30),
) -> StartupOrphanCloseInput:
    """构造 startup orphan closeout 输入。

    :param expected_run_status: 期望 Run 状态。
    :param expected_attempt_status: 期望 Attempt 状态。
    :param recoverable: 是否进入 recovering。
    :param reason: closeout reason。
    :param owner_heartbeat_at: classifier 使用的 owner heartbeat timestamp。
    :param stale_after: classifier 使用的 stale 阈值。
    :returns: StartupOrphanCloseInput。
    """

    return StartupOrphanCloseInput(
        run_id="run-1",
        expected_run_status=expected_run_status,
        attempt_id="attempt-run-1",
        expected_attempt_status=expected_attempt_status,
        execution_id="execution-run-1",
        dispatch_record_id="dispatch-run-1",
        expected_dispatch_status=DispatchRecordStatus.DISPATCHING,
        owner_host_instance_id="host-instance-1",
        owner_heartbeat_at=owner_heartbeat_at,
        stale_after=stale_after,
        recoverable=recoverable,
        attempt_lost_event_id="event-attempt-lost-startup",
        run_close_event_id="event-run-close-startup",
        occurred_at=_NOW,
        actor="host_recovery",
        source="pytest",
        reason=reason,
        orphan_proof_reason="owner_pid_missing",
        observed_process_start_token=None,
        observed_boot_id=None,
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


def _event_payload(
    transaction: HostTransaction, *, event_id: str
) -> dict[str, JsonValue]:
    """读取指定 EventLog row 的 payload JSON。

    :param transaction: Host transaction。
    :param event_id: EventLog id。
    :returns: payload JSON object。
    :raises AssertionError: 事件缺失或 payload 不是 JSON object 时抛出。
    """

    row = transaction.fetchone(
        "SELECT payload_json FROM event_log WHERE event_id = ?",
        (event_id,),
    )
    assert row is not None
    payload = json.loads(_required_text(row, "payload_json"))
    assert isinstance(payload, dict)
    return cast(dict[str, JsonValue], payload)


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
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_EVENT_TYPE_ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_CANCELLING = "RUN_CANCELLING"
_EVENT_TYPE_ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
