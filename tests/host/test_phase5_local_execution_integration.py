"""Host Phase 5 本地执行 terminal closeout 集成测试。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    RunCancelledData,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import AttemptStatus, CancelMode, EnsureSessionRequest, RunStatus
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
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
    CancelActiveAttemptInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    request_active_attempt_cancel_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    RunStartReason,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.engine_ingest import (
    EngineEventCandidate,
    EngineEventIngestor,
    EngineIngestStatus,
    LocalEngineEnvelope,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "phase5-integration-test"})


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Engine run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回取消状态。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _WakeupSpy:
    """测试用 wakeup port。"""

    def __init__(self) -> None:
        """初始化 spy。

        :returns: ``None``。
        """

        self.promoted_session_ids: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """忽略 dispatch wakeup。

        :param record: pending dispatch record。
        :returns: ``None``。
        """

        del record

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: Session id。
        :returns: ``None``。
        """

        self.promoted_session_ids.append(session_id)


def test_clean_eof_without_terminal_closes_failed(tmp_path: Path) -> None:
    """clean EOF without terminal 收口为 FAILED，重复 closeout 会重试 promotion。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        wakeup = _WakeupSpy()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            wakeup_port=wakeup,
        )
        result = ingestor.close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        assert _payload(result.events[0])["reason"] == "stream_ended_without_terminal"
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.FAILED,
            AttemptStatus.FAILED,
        )
        duplicate = ingestor.close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )
        assert duplicate.status == EngineIngestStatus.DUPLICATE
        assert duplicate.promotion_triggered is True
        assert wakeup.promoted_session_ids == [
            seeded.session_id,
            seeded.session_id,
        ]


def test_stream_error_or_worker_crash_closes_lost(tmp_path: Path) -> None:
    """stream error / worker crash 收口为 LOST。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).close_worker_lost(
            _envelope(seeded),
            observed_at=_NOW,
            worker_lifecycle_signal="worker_crash",
            stream_error_code="broken_stream",
            last_observed_worker_event_index=1,
            last_accepted_event_id="event-preview-last",
        )

        assert [event.event_type for event in result.events] == [
            "ATTEMPT_LOST",
            "RUN_LOST",
        ]
        payload = _payload(result.events[0])
        assert payload["reason"] == "worker_lost_before_terminal"
        assert payload["worker_lifecycle_signal"] == "worker_crash"
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.LOST,
            AttemptStatus.LOST,
        )


def test_run_cancelled_after_active_cancel_closes_cancelled(tmp_path: Path) -> None:
    """active cancel 后的 run_cancelled 收口为 CANCELLED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _request_active_cancel(store.transaction_runner, seeded)
        candidate = EngineEventCandidate(
            envelope=_envelope(seeded),
            worker_event_index=2,
            engine_event=EngineEvent(
                occurred_at=_NOW,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                type=EngineEventType.RUN_CANCELLED,
                data=RunCancelledData(
                    reason="user_stop",
                    requested_at=_NOW,
                    accepted_at=_NOW,
                    finished_at=_NOW,
                ),
                metadata=None,
            ),
            observed_at=_NOW,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_CANCELLED",
            "RUN_CANCELLED",
        ]
        payload = _payload(result.events[0])
        assert payload["cancel_request_event_id"] == "event-cancel-requested-active"
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.CANCELLED,
            AttemptStatus.CANCELLED,
        )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store options。

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


def _seed_active_run(transaction_runner: HostTransactionRunner) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded run。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="phase5-local", metadata=()),
    ).snapshot.session_id
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-phase5-local",
        attempt_id="attempt-phase5-local",
        execution_id="execution-phase5-local",
        dispatch_record_id="dispatch-phase5-local",
    )

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-input-phase5-local",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=session_id,
                    run_id=seeded.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="USER_INPUT_ACCEPTED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id="client-phase5-local",
                    idempotency_key="idem-phase5-local-input",
                    policy_decision=None,
                    reason=None,
                    payload_json={"display_text": "hello"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-phase5-local",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-phase5-local",
                run_started_event_id="event-run-started-phase5-local",
                attempt_started_event_id="event-attempt-started-phase5-local",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-phase5-local",
                execution_target="target-phase5-local",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            lane_claim_id="claim-test",
            lane_owner_id="owner-test",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-phase5-local",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
            ),
        )

    transaction_runner.run_write(_operation)
    return seeded


def _request_active_cancel(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """把 active Run 推进到 CANCELLING。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        request_active_attempt_cancel_in_transaction(
            transaction,
            EventLogStore(),
            CancelActiveAttemptInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-requested-active",
                run_cancelling_event_id="event-run-cancelling-active",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel-active",
                idempotency_key="idem-cancel-active",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _envelope(seeded: _SeededRun) -> LocalEngineEnvelope:
    """构造 LocalEngineEnvelope。

    :param seeded: seeded run。
    :returns: envelope。
    """

    return LocalEngineEnvelope(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        dispatch_record_id=seeded.dispatch_record_id,
        worker_kind=WorkerKind.LOCAL,
        execution_target="target-phase5-local",
        local_worker_id="local-worker-phase5",
        cancellation_token=_NeverCancelledToken(),
    )


def _statuses(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunStatus, AttemptStatus]:
    """读取 Run / Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :returns: Run 与 Attempt 状态。
    """

    def _operation(transaction: HostTransaction) -> tuple[RunStatus, AttemptStatus]:
        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        return run.status, attempt.status

    return transaction_runner.run_read(_operation)


def _payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog payload。

    :param row: EventLog row。
    :returns: payload mapping。
    """

    value = cast(JsonValue, json.loads(row.payload_json))
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)
