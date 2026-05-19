"""Host resolve_wait command 与 waiting resume 测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_TIMEOUT,
    ToolCancelledOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    OperationContext,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitRequest,
    RunStatus,
    WaitProviderStatusRef,
    WaitResolutionSource,
    resolve_wait,
)
from dayu.host.api import EnsureSessionRequest, HostCommandHandleOptions, WaitAdapterKey
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.memory import read_latest_memory_snapshot
from dayu.host.durable.liveness import HostInstanceIdentity, register_current_instance
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordStatus,
    DispatchRecordRow,
    RunStartReason,
    RunRow,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_dispatch_record_by_attempt_id,
    read_wait_record_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.admission import create_host_admission_service
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.memory_repair import ConversationMemoryProjectionCatchupPort
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.run_input import PolicySnapshot, create_no_tool_run_input_builder
from dayu.host.wait_adapter import WaitAdapterBinding, WaitExternalJobRefSource
from dayu.host.waiting import (
    DefaultHostToolAwaitingAcceptPort,
    ToolAwaitingAcceptCandidate,
    ToolAwaitingAcceptedAck,
    ResolveWaitResult,
    _resolve_created_event_ref,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_NOW = datetime(2026, 5, 16, 1, 2, 3, tzinfo=UTC)
_OBSERVED = datetime(2026, 5, 16, 1, 5, 7, tzinfo=UTC)
_OBSERVED_REPLAY = datetime(2026, 5, 16, 1, 6, 8, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "resolve-wait-test"})


@dataclass(slots=True)
class _FailingProjectionCatchup(ProjectionCatchupPort):
    """测试用失败 projection catch-up port。"""

    calls: int = 0

    def catch_up_projection(self) -> None:
        """记录调用并模拟 catch-up 失败。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出测试错误。
        """

        self.calls += 1
        raise RuntimeError("forced resolve wait projection catch-up failure")


def test_resolve_wait_completed_resumes_run_and_wakes_dispatch(
    tmp_path: Path,
) -> None:
    """completed outcome 关闭 wait 并创建 resume Attempt / dispatch record。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _completed_request("resolve-completed")

        snapshot = resolve_wait(host, seeded.wait_id, request)

        wait_record, dispatch_record, events = _read_resolution_state(
            host._transaction_runner(), seeded.wait_id, snapshot.current_attempt_id
        )
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id is not None
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert wait_record is not None
        assert wait_record.status is WaitRecordStatus.RESOLVED
        assert dispatch_record is not None
        assert [event.event_type for event in events[-4:]] == [
            "RESUME_REQUESTED",
            "TOOL_RESULT_ACCEPTED",
            "RUN_STARTED",
            "ATTEMPT_STARTED",
        ]
        assert events[-2].reason_json == '{"start_reason":"resume"}'
        request_for_resume = _build_resume_request(
            host._transaction_runner(), seeded.session_id, snapshot.current_attempt_id
        )
        assert any(
            isinstance(message.content, str)
            and "Accepted wait result fact:" in message.content
            and seeded.wait_id in message.content
            for message in request_for_resume.messages
        )
    finally:
        host.close()


def test_resolve_created_event_ref_fails_closed_for_missing_resume_start() -> None:
    """resolve wait resume 结果缺 started_event_id 时 fail closed。"""

    result = ResolveWaitResult(
        run=_run_row(started_event_id=None, started_event_sequence=None),
        dispatch_record=_dispatch_record_row(),
        idempotent_replay=False,
    )

    with pytest.raises(HostApiError) as error_info:
        _resolve_created_event_ref(result)

    assert error_info.value.code is HostApiErrorCode.INTERNAL_ERROR


def test_resolve_wait_survives_projection_catchup_failure(
    tmp_path: Path,
) -> None:
    """resolve_wait commit 后 projection catch-up 失败不影响恢复结果。"""

    host = create_host_command_handle(_options(tmp_path))
    projection = _FailingProjectionCatchup()
    host._admission_service = create_host_admission_service(
        host._transaction_runner(),
        projection_catchup_port=projection,
    )
    try:
        seeded = _seed_waiting_run(host)
        snapshot = resolve_wait(host, seeded.wait_id, _completed_request("resolve-catchup"))

        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id is not None
        assert projection.calls == 1
    finally:
        host.close()


def test_resolve_wait_committed_tool_fact_catches_up_memory(
    tmp_path: Path,
) -> None:
    """显式 concrete catch-up port 会投影 resolve_wait 工具事实。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: resolve_wait committed 工具事实未进入 memory 时抛出。
    """

    policy = default_memory_projection_policy()
    host = create_host_command_handle(_options(tmp_path))
    host._admission_service = create_host_admission_service(
        host._transaction_runner(),
        projection_catchup_port=ConversationMemoryProjectionCatchupPort(
            transaction_runner=host._transaction_runner(),
            policy=policy,
            batch_size=8,
        ),
    )
    try:
        seeded = _seed_waiting_run(host)

        snapshot = resolve_wait(
            host, seeded.wait_id, _completed_request("resolve-memory-catchup")
        )
        memory_snapshot = host._transaction_runner().run_read(
            lambda transaction: read_latest_memory_snapshot(
                transaction,
                session_id=seeded.session_id,
                consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                policy_digest=digest_memory_projection_policy(policy),
            )
        )

        assert snapshot.status is RunStatus.RUNNING
        assert memory_snapshot is not None
        assert len(memory_snapshot.snapshot.verified_facts) == 1
        assert memory_snapshot.snapshot.verified_facts[0].provenance.event_id in {
            row.event_id
            for row in _events_by_type(
                _events(host._transaction_runner()), "TOOL_RESULT_ACCEPTED"
            )
        }
    finally:
        host.close()


def test_resolve_wait_logs_ids_without_result_payload(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """resolve_wait 日志记录 wait / run ids，不记录 result payload。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 日志缺少字段或泄漏 result payload 时抛出。
    """

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        with caplog.at_level(VERBOSE_LOG_LEVEL, logger="dayu.host.waiting"):
            snapshot = resolve_wait(
                host, seeded.wait_id, _completed_request("resolve-logging")
            )

        assert snapshot.status is RunStatus.RUNNING
        assert "host.waiting.resolve_wait.accepted" in caplog.text
        assert "host.waiting.resolve_wait.committed" in caplog.text
        assert seeded.wait_id in caplog.text
        assert seeded.run_id in caplog.text
        assert '"answer": 42' not in caplog.text
        assert "result" not in caplog.text
    finally:
        host.close()


def test_resolve_wait_same_key_same_outcome_replays_with_different_observed_at(
    tmp_path: Path,
) -> None:
    """同 wait_id + idempotency_key + outcome 不因 observed_at 变化而冲突。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _completed_request("resolve-replay")
        replay_request = replace(request, observed_at=_OBSERVED_REPLAY)

        first = resolve_wait(host, seeded.wait_id, request)
        before_events = _events(host._transaction_runner())
        before_tool_results = _events_by_type(before_events, "TOOL_RESULT_ACCEPTED")
        second = resolve_wait(host, seeded.wait_id, replay_request)
        after_events = _events(host._transaction_runner())

        assert second.current_attempt_id == first.current_attempt_id
        assert after_events == before_events
        assert _events_by_type(after_events, "TOOL_RESULT_ACCEPTED") == (
            before_tool_results
        )
    finally:
        host.close()


def test_resolve_wait_same_key_different_outcome_conflicts(
    tmp_path: Path,
) -> None:
    """同 key 不同 outcome 返回 idempotency_conflict 且不追加事实。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _completed_request("resolve-conflict")
        conflict = replace(
            request,
            outcome=ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"answer": "changed"},
                    meta=None,
                ),
                payload_ref=None,
            ),
        )

        resolve_wait(host, seeded.wait_id, request)
        before_events = _events(host._transaction_runner())
        with pytest.raises(HostApiError) as exc_info:
            resolve_wait(host, seeded.wait_id, conflict)

        assert exc_info.value.code is HostApiErrorCode.IDEMPOTENCY_CONFLICT
        assert _events(host._transaction_runner()) == before_events
    finally:
        host.close()


def test_resolve_wait_failed_and_lost_close_run_without_resume_attempt(
    tmp_path: Path,
) -> None:
    """failed / lost outcome 收口 Run 且不创建 resume dispatch。"""

    failed_host = create_host_command_handle(_options(tmp_path / "failed"))
    lost_host = create_host_command_handle(_options(tmp_path / "lost"))
    try:
        failed_seeded = _seed_waiting_run(failed_host)
        failed = resolve_wait(
            failed_host,
            failed_seeded.wait_id,
            _failed_request("resolve-failed"),
        )
        lost_seeded = _seed_waiting_run(lost_host)
        lost = resolve_wait(
            lost_host,
            lost_seeded.wait_id,
            _lost_request("resolve-lost"),
        )

        failed_wait = _read_wait(failed_host._transaction_runner(), failed_seeded.wait_id)
        lost_wait = _read_wait(lost_host._transaction_runner(), lost_seeded.wait_id)
        assert failed.status is RunStatus.FAILED
        assert failed.current_attempt_id == failed_seeded.attempt_id
        assert failed_wait.status is WaitRecordStatus.FAILED
        assert lost.status is RunStatus.LOST
        assert lost.current_attempt_id == lost_seeded.attempt_id
        assert lost_wait.status is WaitRecordStatus.LOST
    finally:
        failed_host.close()
        lost_host.close()


def test_resolve_wait_lost_same_key_replays_terminal_snapshot(
    tmp_path: Path,
) -> None:
    """lost outcome 同 key 重放返回终态 snapshot 且不追加事实。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)
        request = _lost_request("resolve-lost-replay")

        first = resolve_wait(host, seeded.wait_id, request)
        before_events = _events(host._transaction_runner())
        second = resolve_wait(host, seeded.wait_id, request)
        after_events = _events(host._transaction_runner())

        assert first.status is RunStatus.LOST
        assert second.status is RunStatus.LOST
        assert second.current_attempt_id == first.current_attempt_id
        assert after_events == before_events
    finally:
        host.close()


def test_resolve_wait_tool_cancelled_resumes_as_resolved_wait(
    tmp_path: Path,
) -> None:
    """工具级 cancelled outcome 按 resolved wait 恢复，而不是取消 wait record。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_waiting_run(host)

        snapshot = resolve_wait(
            host,
            seeded.wait_id,
            _cancelled_request("resolve-cancelled-tool"),
        )

        wait_record = _read_wait(host._transaction_runner(), seeded.wait_id)
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert wait_record.status is WaitRecordStatus.RESOLVED
    finally:
        host.close()


class _SeededWaitingRun:
    """测试中创建的 waiting Run 引用。"""

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        dispatch_record_id: str,
        wait_id: str,
    ) -> None:
        """初始化 seeded waiting run 引用。

        :param session_id: Session id。
        :param run_id: Run id。
        :param attempt_id: Attempt id。
        :param execution_id: execution id。
        :param dispatch_record_id: dispatch record id。
        :param wait_id: wait record id。
        :returns: ``None``。
        """

        self.session_id = session_id
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.execution_id = execution_id
        self.dispatch_record_id = dispatch_record_id
        self.wait_id = wait_id


class _NeverCancelledToken:
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


def _run_row(
    *, started_event_id: str | None, started_event_sequence: int | None
) -> RunRow:
    """构造 resolve wait helper 测试用 RunRow。

    :param started_event_id: run started event id。
    :param started_event_sequence: run started event sequence。
    :returns: RunRow。
    """

    return RunRow(
        run_id="run-resolve-helper",
        session_id="session-resolve-helper",
        status=RunStatus.RUNNING,
        client_request_id="client-resolve-helper",
        input_event_id="event-input-resolve-helper",
        input_event_sequence=1,
        accepted_event_id="event-run-accepted-resolve-helper",
        accepted_event_sequence=2,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id="attempt-resolve-helper",
        source_run_id=None,
        source_run_relation=None,
        execution_target="target-resolve-helper",
        queue_policy="queue",
        created_at="2026-05-16T01:02:03.000000Z",
        updated_at="2026-05-16T01:02:03.000000Z",
        terminal_at=None,
    )


def _dispatch_record_row() -> DispatchRecordRow:
    """构造 resolve wait helper 测试用 DispatchRecordRow。

    :returns: DispatchRecordRow。
    """

    return DispatchRecordRow(
        dispatch_record_id="dispatch-resolve-helper",
        run_id="run-resolve-helper",
        attempt_id="attempt-resolve-helper",
        execution_id="execution-resolve-helper",
        status=DispatchRecordStatus.PENDING,
        worker_kind=WorkerKind.LOCAL,
        execution_target="target-resolve-helper",
        owner_host_instance_id=None,
        created_event_id="event-dispatch-created-resolve-helper",
        created_event_sequence=3,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=None,
        worker_accept_event_id=None,
        worker_accept_event_sequence=None,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at="2026-05-16T01:02:03.000000Z",
        updated_at="2026-05-16T01:02:03.000000Z",
        cancelled_at=None,
    )


def _options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造测试用 Host command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-resolve-wait-test",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _context(request_id: str = "trace-resolve") -> HostCallContext:
    """构造 Host call context。

    :param request_id: request id。
    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="resolve_wait",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase7",
            correlation_id=None,
        ),
    )


def _completed_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 completed resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitCompletedOutcome(
            result=ToolResultSuccess(ok=True, value={"answer": 42}, meta=None),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_OBSERVED,
    )


def _failed_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 failed resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error="provider_failed",
                message="provider failed",
                hint=None,
                meta=None,
            ),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_OBSERVED,
    )


def _lost_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造 lost resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitLostOutcome(
            reason_code="adapter_lost",
            message="adapter cannot confirm external job",
            provider_status_ref=WaitProviderStatusRef(
                adapter_key=WaitAdapterKey("poll:long-tool"),
                status_ref="provider-status-1",
                status_digest=sha256_digest_json({"status": "lost"}),
            ),
        ),
        source=WaitResolutionSource.POLL,
        observed_at=_OBSERVED,
    )


def _cancelled_request(idempotency_key: str) -> ResolveWaitRequest:
    """构造工具级 cancelled resolve wait request。

    :param idempotency_key: resolve wait 幂等键。
    :returns: resolve wait request。
    """

    return ResolveWaitRequest(
        context=_context(idempotency_key),
        idempotency_key=idempotency_key,
        outcome=ResolveWaitCancelledOutcome(
            result=ToolCancelledOutcome(
                reason=TOOL_CANCELLED_REASON_TIMEOUT,
                message="tool timed out",
                hint=None,
                meta=None,
            ),
            payload_ref=None,
        ),
        source=WaitResolutionSource.MANUAL,
        observed_at=_OBSERVED,
    )


def _seed_waiting_run(host: HostCommandHandle) -> _SeededWaitingRun:
    """创建已进入 WAITING/SUSPENDED 的 Run。

    :param host: Host command handle。
    :returns: seeded waiting run。
    """

    transaction_runner = host._transaction_runner()
    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="resolve", metadata=()),
    ).snapshot.session_id
    base = _SeededWaitingRun(
        session_id=session_id,
        run_id="run-resolve",
        attempt_id="attempt-resolve",
        execution_id="execution-resolve",
        dispatch_record_id="dispatch-resolve",
        wait_id="wait-pending",
    )
    _seed_active_run(transaction_runner, base)
    candidate = _awaiting_candidate(base)
    result = DefaultHostToolAwaitingAcceptPort(
        transaction_runner=transaction_runner
    ).accept_tool_awaiting(candidate)
    assert isinstance(result, ToolAwaitingAcceptedAck)
    return _SeededWaitingRun(
        session_id=base.session_id,
        run_id=base.run_id,
        attempt_id=base.attempt_id,
        execution_id=base.execution_id,
        dispatch_record_id=base.dispatch_record_id,
        wait_id=candidate.wait_id,
    )


def _seed_active_run(
    transaction_runner: HostTransactionRunner, seeded: _SeededWaitingRun
) -> None:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run 引用。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """写入 active Run 所需 durable rows。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-resolve-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-input-resolve",
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-resolve",
                idempotency_key="idem-resolve-input",
                policy_decision=None,
                reason=None,
                payload_json={
                    "display_text": "hello",
                    "operation_kind": "test",
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                client_request_id="client-resolve",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-resolve",
                run_started_event_id="event-run-started-resolve",
                attempt_started_event_id="event-attempt-started-resolve",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-resolve",
                execution_target="target-resolve",
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
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-16T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            lane_claim_id="claim-resolve",
            lane_owner_id="owner-resolve",
            lane_acquired_at="2026-05-16T01:02:03.000000Z",
            dispatching_at="2026-05-16T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-resolve",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
                local_worker_id="local-worker-resolve",
            ),
        )

    transaction_runner.run_write(_operation)


def _awaiting_candidate(seeded: _SeededWaitingRun) -> ToolAwaitingAcceptCandidate:
    """构造 awaiting accept candidate。

    :param seeded: seeded run。
    :returns: awaiting accept candidate。
    """

    digest = sha256_digest_json({"awaiting": seeded.run_id})
    binding = WaitAdapterBinding(
        tool_name="long_tool",
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        adapter_key=WaitAdapterKey("poll:long-tool"),
        resume_policy=WaitResumePolicy.POLL,
        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
    )
    await_spec = ToolAwaitSpec(
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        deadline=None,
        resume_token="external-job-1",
    )
    return ToolAwaitingAcceptCandidate(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        iteration_id="iteration-resolve",
        tool_call_id="tool-call-resolve",
        tool_name="long_tool",
        tool_schema_digest=sha256_digest_json({"schema": "long_tool"}),
        tool_identity_digest=sha256_digest_json({"identity": "long_tool"}),
        normalized_arguments_digest=sha256_digest_json({"arguments": "long_tool"}),
        await_spec=await_spec,
        snapshot_ref=None,
        binding=binding,
        external_job_ref=binding.external_job_ref(await_spec),
        wait_id=f"wait-{digest.removeprefix('sha256:')}",
        accept_idempotency_key=f"tool-await-{digest.removeprefix('sha256:')}",
        semantic_input_digest=digest,
    )


def _read_resolution_state(
    transaction_runner: HostTransactionRunner,
    wait_id: str,
    attempt_id: str | None,
) -> tuple[WaitRecordRow | None, DispatchRecordRow | None, tuple[EventLogRow, ...]]:
    """读取 resolve 后 wait、dispatch 与事件。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait record id。
    :param attempt_id: 当前 Attempt id。
    :returns: wait record、dispatch record 与全部事件。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[WaitRecordRow | None, DispatchRecordRow | None, tuple[EventLogRow, ...]]:
        """执行读取。

        :param transaction: Host transaction。
        :returns: wait record、dispatch record 与全部事件。
        """

        dispatch_record = (
            read_dispatch_record_by_attempt_id(transaction, attempt_id)
            if attempt_id is not None
            else None
        )
        return (
            read_wait_record_by_id(transaction, wait_id),
            dispatch_record,
            EventLogStore().read_events_after(transaction, 0, limit=100),
        )

    return transaction_runner.run_read(_operation)


def _read_wait(
    transaction_runner: HostTransactionRunner, wait_id: str
) -> WaitRecordRow:
    """读取 wait record 并断言存在。

    :param transaction_runner: Host transaction runner。
    :param wait_id: wait record id。
    :returns: wait record row。
    """

    row = transaction_runner.run_read(
        lambda transaction: read_wait_record_by_id(transaction, wait_id)
    )
    assert row is not None
    return row


def _build_resume_request(
    transaction_runner: HostTransactionRunner,
    session_id: str,
    attempt_id: str | None,
) -> AgentRunRequest:
    """把 resume dispatch 推进到 dispatching 并构造 Engine request。

    :param transaction_runner: Host transaction runner。
    :param session_id: Session id。
    :param attempt_id: resume Attempt id。
    :returns: AgentRunRequest；测试只检查 messages。
    """

    assert attempt_id is not None

    def _mark_dispatching(transaction: HostTransaction) -> DispatchRecordRow:
        """标记 resume dispatch 为 dispatching 并返回 row。

        :param transaction: Host transaction。
        :returns: dispatch record row。
        """

        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-16T01:05:07.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=attempt_id,
            owner_host_instance_id="host-resolve-test",
            lane_name="llm",
            lane_claim_id="claim-resume",
            lane_owner_id="owner-resume",
            lane_acquired_at="2026-05-16T01:05:07.000000Z",
            dispatching_at="2026-05-16T01:05:07.000000Z",
        )
        dispatch = read_dispatch_record_by_attempt_id(transaction, attempt_id)
        assert dispatch is not None
        return dispatch

    dispatch = transaction_runner.run_write(_mark_dispatching)
    builder = create_no_tool_run_input_builder(
        transaction_runner=transaction_runner,
        policy_snapshot=_policy_snapshot(),
    )
    return builder.build(
        AttemptDispatchSnapshot(
            session_id=session_id,
            run_id=dispatch.run_id,
            attempt_id=dispatch.attempt_id,
            execution_id=dispatch.execution_id,
            dispatch_record_id=dispatch.dispatch_record_id,
            execution_target=dispatch.execution_target,
            policy_snapshot_ref="policy-resolve-wait",
            cancellation_token=_token(),
        )
    )


def _token() -> CancellationToken:
    """构造测试用 cancellation token。

    :returns: 未取消 token。
    """

    return _NeverCancelledToken()


def _policy_snapshot() -> PolicySnapshot:
    """构造测试用 policy snapshot。

    :returns: PolicySnapshot。
    """

    return PolicySnapshot(
        runner_spec=RunnerSpec(
            provider="test",
            model="test-model",
            endpoint="https://example.invalid/v1",
            api_key_ref="test-key",
            headers={},
            supports_tool_calling=False,
            supports_streaming=False,
            supports_stream_usage=False,
            default_timeout_seconds=30.0,
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
        ),
        policy_snapshot_ref="policy-resolve-wait",
    )


def _events(transaction_runner: HostTransactionRunner) -> tuple[EventLogRow, ...]:
    """读取全部 EventLog rows。

    :param transaction_runner: Host transaction runner。
    :returns: EventLog rows。
    """

    return transaction_runner.run_read(
        lambda transaction: EventLogStore().read_events_after(
            transaction, 0, limit=100
        )
    )


def _events_by_type(
    events: tuple[EventLogRow, ...], event_type: str
) -> tuple[EventLogRow, ...]:
    """按 event type 过滤 EventLog rows。

    :param events: EventLog rows。
    :param event_type: 目标 event type。
    :returns: 匹配事件元组。
    """

    return tuple(event for event in events if event.event_type == event_type)
